"""
RedisAnalysisRunRegistry — Redis 实现的分析运行注册表（M40-b）。

数据结构：
  ta:{env}:run:{run_id}        → Hash  （运行状态）
  ta:{env}:run:{run_id}:events → List  （事件历史，RPUSH + LTRIM）
  ta:{env}:run:{run_id}:eid    → 计数器（单调递增 event_id）
  ta:{env}:run:{run_id}:ch     → Pub/Sub channel（实时事件推送）

特性：
  - 跨进程可见：所有 worker 共享同一 Redis，run state / events 全局一致
  - after_event_id replay：基于 List 存储的历史事件，支持断线重连
  - cancel：跨进程：HSET cancel_requested=1 + Publish
  - TTL：每次 push_event / update_status 刷新，防止 orphan key
  - fail-fast：Redis 不可用时直接抛出，不静默 fallback memory

设计约束（M40-b）：
  - 不新增依赖（redis>=7.4.0 已在 pyproject.toml）
  - 不修改 SSE 事件协议
  - 不修改前端
  - Memory 模式为默认，Redis 模式需显式设置 ANALYSIS_RUN_REGISTRY=redis
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from redis.asyncio import Redis

from app.services.run_registry_protocol import (
    AnalysisRunRef,
    AnalysisRunRegistry,
    AnalysisRunSnapshot,
)

log = logging.getLogger(__name__)

# Terminal event types — same as analysis.py
_TERMINAL_EVENTS = frozenset({"report_ready", "analysis_failed", "cancelled"})


def _json_dumps(obj: Any) -> str:
    """JSON serialiser that handles datetime / UUID / plain dicts."""
    def _default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serialisable")
    return json.dumps(obj, ensure_ascii=False, default=_default)


class RedisAnalysisRunRegistry(AnalysisRunRegistry):
    """
    AnalysisRunRegistry 的 Redis 实现（M40-b）。

    每个 run 使用 4 个 Redis 键：
      Hash:    ta:{env}:run:{run_id}          (run state)
      List:    ta:{env}:run:{run_id}:events   (event history, RPUSH + LTRIM)
      String:  ta:{env}:run:{run_id}:eid      (monotonic event_id counter, INCR)
      PubSub:  ta:{env}:run:{run_id}:ch       (live event channel)
    """

    def __init__(
        self,
        redis:       Redis,
        ttl_seconds: int = 21600,
        event_maxlen: int = 200,
        env:         str = "development",
    ) -> None:
        self._redis       = redis
        self._ttl         = ttl_seconds
        self._event_maxlen = event_maxlen
        self._env         = env

    # ── Key helpers ───────────────────────────────────────────────────────────

    def _run_key(self, run_id: str) -> str:
        return f"ta:{self._env}:run:{run_id}"

    def _events_key(self, run_id: str) -> str:
        return f"ta:{self._env}:run:{run_id}:events"

    def _eid_key(self, run_id: str) -> str:
        return f"ta:{self._env}:run:{run_id}:eid"

    def _channel_key(self, run_id: str) -> str:
        return f"ta:{self._env}:run:{run_id}:ch"

    # ── create / read ─────────────────────────────────────────────────────────

    async def create_run(
        self,
        user_id:         str,
        market:          str,
        symbol:          str,
        analysis_scope:  str,
        workflow_engine: str = "custom_coordinator",
        output_language: str = "zh-CN",
    ) -> AnalysisRunRef:
        run_id = str(uuid.uuid4())
        now    = datetime.now(timezone.utc)
        now_s  = now.isoformat()

        mapping: dict = {
            "run_id":          run_id,
            "user_id":         user_id,
            "market":          market,
            "symbol":          symbol,
            "analysis_scope":  analysis_scope,
            "workflow_engine": workflow_engine,
            "output_language": output_language,
            "status":          "queued",
            "progress":        "0",
            "cancel_requested": "0",
            "created_at":      now_s,
            "updated_at":      now_s,
            # result_json / error / finished_at / latest_event_json absent until set
        }

        pipe = self._redis.pipeline()
        pipe.hset(self._run_key(run_id), mapping=mapping)
        pipe.expire(self._run_key(run_id), self._ttl)
        await pipe.execute()

        log.debug("RedisRunRegistry: created run %s", run_id[:8])
        return AnalysisRunRef(
            run_id          = run_id,
            user_id         = user_id,
            market          = market,
            symbol          = symbol,
            analysis_scope  = analysis_scope,
            workflow_engine = workflow_engine,
            output_language = output_language,
            created_at      = now,
        )

    async def get_run_snapshot(self, run_id: str) -> Optional[AnalysisRunSnapshot]:
        data: dict = await self._redis.hgetall(self._run_key(run_id))
        if not data:
            return None

        result: Optional[dict] = None
        if data.get("result_json"):
            try:
                result = json.loads(data["result_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        latest_event: Optional[dict] = None
        if data.get("latest_event_json"):
            try:
                latest_event = json.loads(data["latest_event_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        # progress: prefer dedicated field, fall back to latest_event
        try:
            progress = int(data.get("progress") or 0)
        except (ValueError, TypeError):
            progress = 0
        if progress == 0 and latest_event:
            try:
                progress = int(latest_event.get("progress") or 0)
            except (ValueError, TypeError):
                pass

        def _parse_dt(s: Optional[str]) -> Optional[datetime]:
            if not s:
                return None
            try:
                return datetime.fromisoformat(s)
            except (ValueError, TypeError):
                return None

        return AnalysisRunSnapshot(
            run_id          = data.get("run_id", run_id),
            user_id         = data.get("user_id", ""),
            market          = data.get("market", ""),
            symbol          = data.get("symbol", ""),
            analysis_scope  = data.get("analysis_scope", ""),
            workflow_engine = data.get("workflow_engine", ""),
            output_language = data.get("output_language", "zh-CN"),
            status          = data.get("status", "queued"),
            progress        = progress,
            latest_event    = latest_event,
            result          = result,
            error           = data.get("error") or None,
            created_at      = _parse_dt(data.get("created_at")) or datetime.now(timezone.utc),
            updated_at      = _parse_dt(data.get("updated_at")) or datetime.now(timezone.utc),
            finished_at     = _parse_dt(data.get("finished_at")),
        )

    # ── status / events ───────────────────────────────────────────────────────

    async def update_status(
        self,
        run_id: str,
        status: str,
        *,
        result: Optional[dict] = None,
        error:  Optional[str]  = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        mapping: dict = {"status": status, "updated_at": now}

        if result is not None:
            mapping["result_json"] = _json_dumps(result)
        if error is not None:
            mapping["error"] = error
        if status in ("completed", "failed", "cancelled"):
            mapping["finished_at"] = now
        if status == "cancelled":
            mapping["cancel_requested"] = "1"

        pipe = self._redis.pipeline()
        pipe.hset(self._run_key(run_id), mapping=mapping)
        pipe.expire(self._run_key(run_id), self._ttl)
        await pipe.execute()

    async def push_event(self, run_id: str, event: Optional[dict]) -> None:
        """
        event=None  → publish close-signal to channel (stream sentinel).
        event=dict  → stamp with event_id, append to history List, publish.
        """
        if event is None:
            # Close signal: only published to channel, NOT stored in List
            await self._redis.publish(
                self._channel_key(run_id),
                _json_dumps({"_close": True}),
            )
            return

        # Atomically obtain a unique, monotonically increasing event_id
        event_id: int = await self._redis.incr(self._eid_key(run_id))
        # event_id starts from 1 (INCR first call returns 1)

        stamped  = {**event, "event_id": event_id}
        stamped_json = _json_dumps(stamped)

        now = datetime.now(timezone.utc).isoformat()
        progress_val = event.get("progress", 0) or 0

        pipe = self._redis.pipeline()
        # Append to events List and trim to maxlen
        pipe.rpush(self._events_key(run_id), stamped_json)
        pipe.ltrim(self._events_key(run_id), -self._event_maxlen, -1)
        # Update run Hash: latest event info + progress
        pipe.hset(self._run_key(run_id), mapping={
            "latest_event_id":   event_id,
            "latest_event_json": stamped_json,
            "progress":          progress_val,
            "updated_at":        now,
        })
        # Refresh TTL for all keys
        pipe.expire(self._run_key(run_id),    self._ttl)
        pipe.expire(self._events_key(run_id), self._ttl)
        pipe.expire(self._eid_key(run_id),    self._ttl)
        await pipe.execute()

        # Publish AFTER pipeline (separate command — PUBLISH can't be in multi)
        await self._redis.publish(self._channel_key(run_id), stamped_json)

        log.debug("RedisRunRegistry: push_event [%s] %s eid=%s",
                  run_id[:8], event.get("event"), event_id)

    # ── replay ────────────────────────────────────────────────────────────────

    async def get_events_after(
        self,
        run_id:         str,
        after_event_id: Optional[int],
    ) -> list:
        raw_list = await self._redis.lrange(self._events_key(run_id), 0, -1)
        events: list = []
        for raw in raw_list:
            try:
                evt = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            eid = evt.get("event_id")
            if after_event_id is None or (eid is not None and eid > after_event_id):
                events.append(evt)
        # Events are stored in push order; sort by event_id for safety
        events.sort(key=lambda e: e.get("event_id", 0))
        return events

    # ── live stream ───────────────────────────────────────────────────────────

    async def subscribe_events(  # type: ignore[override]
        self, run_id: str
    ) -> AsyncGenerator[Optional[dict], None]:
        """
        Async generator that streams live events from Redis Pub/Sub.

        Strategy:
          1. SUBSCRIBE to channel FIRST (so we don't miss messages published
             between Phase-1 replay and now — they'll be in the pubsub buffer).
          2. Start a background task that reads from pubsub and puts into a
             local asyncio.Queue (same pattern as MemoryAnalysisRunRegistry).
          3. Check if run is already terminal → yield None and exit early.
          4. Yield events from local queue; yield None on sentinel.

        cleanup: finally block cancels the forwarding task and closes pubsub.
        """
        channel  = self._channel_key(run_id)
        local_q: asyncio.Queue = asyncio.Queue()
        pubsub   = self._redis.pubsub()
        fwd_task: Optional[asyncio.Task] = None

        try:
            # Step 1: subscribe before checking terminal state
            await pubsub.subscribe(channel)

            # Step 2: start background forwarder
            fwd_task = asyncio.create_task(
                self._read_pubsub_into_queue(pubsub, local_q),
                name=f"pubsub_fwd_{run_id[:8]}",
            )

            # Step 3: check if already terminal
            # (any events published before subscribe are buffered in pubsub)
            snap = await self.get_run_snapshot(run_id)
            if snap is not None and snap.is_terminal():
                yield None
                return

            # Step 4: stream live events
            while True:
                event = await local_q.get()
                yield event
                if event is None:
                    return

        finally:
            # Cancel forward task and wait for it to clean up pubsub
            if fwd_task and not fwd_task.done():
                fwd_task.cancel()
            if fwd_task:
                try:
                    await fwd_task
                except (asyncio.CancelledError, Exception):
                    pass
            # Close pubsub (the forwarding task does NOT close it —
            # generator owns the lifecycle)
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass

    async def _read_pubsub_into_queue(
        self,
        pubsub,
        local_q: asyncio.Queue,
    ) -> None:
        """
        Background task: poll pubsub and forward messages to local_q.
        On close-signal or task cancellation, puts None sentinel into local_q.
        Does NOT close the pubsub connection (generator finalizer owns it).
        """
        try:
            while True:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.1
                )
                if msg is None or msg.get("type") != "message":
                    continue
                try:
                    data: dict = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue

                if data.get("_close"):
                    # Close-signal: sentinel received
                    await local_q.put(None)
                    return

                await local_q.put(data)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.warning("RedisRunRegistry pubsub forwarder error: %s", exc)
        finally:
            # Always ensure the generator can unblock
            await local_q.put(None)

    # ── cancel ────────────────────────────────────────────────────────────────

    async def request_cancel(self, run_id: str) -> None:
        snap = await self.get_run_snapshot(run_id)
        if snap is None or snap.is_terminal():
            return

        now = datetime.now(timezone.utc).isoformat()

        # Set cancelled state in Hash
        await self._redis.hset(self._run_key(run_id), mapping={
            "status":           "cancelled",
            "cancel_requested": "1",
            "updated_at":       now,
            "finished_at":      now,
        })

        # Stamp and store a "cancelled" event
        event_id: int = await self._redis.incr(self._eid_key(run_id))
        stamped = {
            "event":     "cancelled",
            "run_id":    run_id,
            "message":   "用户取消了分析",
            "timestamp": now,
            "event_id":  event_id,
        }
        stamped_json = _json_dumps(stamped)

        pipe = self._redis.pipeline()
        pipe.rpush(self._events_key(run_id), stamped_json)
        pipe.ltrim(self._events_key(run_id), -self._event_maxlen, -1)
        pipe.hset(self._run_key(run_id), mapping={
            "latest_event_id":   event_id,
            "latest_event_json": stamped_json,
        })
        pipe.expire(self._run_key(run_id),    self._ttl)
        pipe.expire(self._events_key(run_id), self._ttl)
        pipe.expire(self._eid_key(run_id),    self._ttl)
        await pipe.execute()

        # Publish cancelled event then close-signal
        channel = self._channel_key(run_id)
        await self._redis.publish(channel, stamped_json)
        await self._redis.publish(channel, _json_dumps({"_close": True}))

    async def is_cancel_requested(self, run_id: str) -> bool:
        # decode_responses=True → returns str or None
        val: Optional[str] = await self._redis.hget(
            self._run_key(run_id), "cancel_requested"
        )
        return val == "1"
