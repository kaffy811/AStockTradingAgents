"""
Analysis Run Registry — 内存中运行状态追踪（M25-b：event_id + LRU 淘汰）。

每次 POST /analysis/runs 创建一个 AnalysisRun，通过 asyncio.Queue 向
GET /analysis/runs/{id}/events SSE 消费者推送进度事件。

M25-b 新增：
  - AnalysisRun.event_id_counter：每个事件分配单调递增 event_id
  - push_event 在事件 dict 中注入 event_id
  - progress / latest_event 属性方便 GET /runs/{id} 响应
  - MAX_RUNS 防止内存无限增长（LRU 淘汰最旧 terminal run）

M40-a 新增：
  - MemoryAnalysisRunRegistry — 实现 AnalysisRunRegistry ABC，供路由层和 Runner 使用
  - 模块级旧函数保留向后兼容（create_run / get_run / push_event / update_run_status）

设计原则：
  - 纯内存，无新依赖，无数据库写入。
  - 每次进程重启后 run 消失（实验性 MVP；生产可改为 Redis）。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from app.services.run_registry_protocol import (
    AnalysisRunRef,
    AnalysisRunRegistry,
    AnalysisRunSnapshot,
)


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_EVENTS_PER_RUN = 200
MAX_RUNS           = 200   # total in-memory runs; oldest terminal are evicted


# ── AnalysisRun dataclass ─────────────────────────────────────────────────────

@dataclass
class AnalysisRun:
    run_id:           str
    user_id:          str
    market:           str
    symbol:           str
    analysis_scope:   str
    workflow_engine:  str
    output_language:  str                   = "zh-CN"
    status:           str                   = "queued"
    result:           Optional[dict]        = None
    error:            Optional[str]         = None
    event_queue:      asyncio.Queue         = field(default_factory=asyncio.Queue)
    events:           list                  = field(default_factory=list)
    event_id_counter: int                   = field(default=0)
    created_at:       datetime              = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at:       datetime              = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    finished_at:      Optional[datetime]    = None

    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def progress(self) -> int:
        """Return the latest progress value seen in events, or 0."""
        for evt in reversed(self.events):
            if "progress" in evt:
                return int(evt["progress"])
        return 0

    @property
    def latest_event(self) -> Optional[dict]:
        return self.events[-1] if self.events else None


# ── In-memory registry ────────────────────────────────────────────────────────

_runs: dict[str, AnalysisRun] = {}


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def create_run(
    user_id:          str,
    market:           str,
    symbol:           str,
    analysis_scope:   str,
    workflow_engine:  str = "custom_coordinator",
    output_language:  str = "zh-CN",
) -> AnalysisRun:
    """Create and register a new AnalysisRun. Evicts old terminal runs if over limit."""
    _evict_if_needed()
    run = AnalysisRun(
        run_id           = str(uuid.uuid4()),
        user_id          = user_id,
        market           = market,
        symbol           = symbol,
        analysis_scope   = analysis_scope,
        workflow_engine  = workflow_engine,
        output_language  = output_language,
    )
    _runs[run.run_id] = run
    return run


def get_run(run_id: str) -> Optional[AnalysisRun]:
    return _runs.get(run_id)


def update_run_status(
    run:    AnalysisRun,
    status: str,
    *,
    result: Optional[dict] = None,
    error:  Optional[str]  = None,
) -> None:
    run.status     = status
    run.updated_at = datetime.now(timezone.utc)
    if result is not None:
        run.result = result
    if error is not None:
        run.error = error
    if status in ("completed", "failed", "cancelled"):
        run.finished_at = datetime.now(timezone.utc)


async def push_event(run: AnalysisRun, event: dict) -> None:
    """
    Stamp event with monotonically increasing event_id, append to run.events,
    and push the stamped copy to run.event_queue for live SSE delivery.
    """
    event_id = run.event_id_counter
    run.event_id_counter += 1
    stamped = {**event, "event_id": event_id}
    if len(run.events) < MAX_EVENTS_PER_RUN:
        run.events.append(stamped)
    await run.event_queue.put(stamped)


def _evict_if_needed() -> None:
    """Evict oldest terminal runs when at capacity."""
    if len(_runs) < MAX_RUNS:
        return
    terminal = [r for r in _runs.values() if r.is_terminal()]
    terminal.sort(key=lambda r: r.finished_at or r.created_at)
    to_remove = len(_runs) - MAX_RUNS + 1
    for run in terminal[:to_remove]:
        _runs.pop(run.run_id, None)


# ── MemoryAnalysisRunRegistry ─────────────────────────────────────────────────

class MemoryAnalysisRunRegistry(AnalysisRunRegistry):
    """
    AnalysisRunRegistry 的纯内存实现（M40-a）。

    内部复用模块级 _runs dict 和 AnalysisRun dataclass，
    通过 AnalysisRunRegistry ABC 对外暴露统一接口。
    """

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
        run = create_run(
            user_id         = user_id,
            market          = market,
            symbol          = symbol,
            analysis_scope  = analysis_scope,
            workflow_engine = workflow_engine,
            output_language = output_language,
        )
        return AnalysisRunRef(
            run_id          = run.run_id,
            user_id         = run.user_id,
            market          = run.market,
            symbol          = run.symbol,
            analysis_scope  = run.analysis_scope,
            workflow_engine = run.workflow_engine,
            output_language = run.output_language,
            created_at      = run.created_at,
        )

    async def get_run_snapshot(self, run_id: str) -> Optional[AnalysisRunSnapshot]:
        run = get_run(run_id)
        if run is None:
            return None
        return AnalysisRunSnapshot(
            run_id          = run.run_id,
            user_id         = run.user_id,
            market          = run.market,
            symbol          = run.symbol,
            analysis_scope  = run.analysis_scope,
            workflow_engine = run.workflow_engine,
            output_language = run.output_language,
            status          = run.status,
            progress        = run.progress,
            latest_event    = run.latest_event,
            result          = run.result,
            error           = run.error,
            created_at      = run.created_at,
            updated_at      = run.updated_at,
            finished_at     = run.finished_at,
        )

    # ── write ─────────────────────────────────────────────────────────────────

    async def update_status(
        self,
        run_id: str,
        status: str,
        *,
        result: Optional[dict] = None,
        error:  Optional[str]  = None,
    ) -> None:
        run = _runs.get(run_id)
        if run is None:
            return
        update_run_status(run, status, result=result, error=error)

    async def push_event(self, run_id: str, event: Optional[dict]) -> None:
        """
        event=None → push sentinel (stream-close signal) directly to queue.
        event=dict → stamp with event_id, append to history, push to queue.
        """
        run = _runs.get(run_id)
        if run is None:
            return
        if event is None:
            await run.event_queue.put(None)
            return
        await push_event(run, event)

    # ── events ────────────────────────────────────────────────────────────────

    async def get_events_after(
        self,
        run_id:         str,
        after_event_id: Optional[int],
    ) -> list:
        run = _runs.get(run_id)
        if run is None:
            return []
        if after_event_id is None:
            return list(run.events)
        return [
            e for e in run.events
            if e.get("event_id") is None or e["event_id"] > after_event_id
        ]

    async def subscribe_events(  # type: ignore[override]
        self, run_id: str
    ) -> AsyncGenerator[Optional[dict], None]:
        """
        Async generator: first drains buffered queue items (phase 2),
        then blocks for live events (phase 3).
        Yields None sentinel when stream closes.
        """
        run = _runs.get(run_id)
        if run is None:
            return
        # Phase 2: drain
        while True:
            try:
                event = run.event_queue.get_nowait()
                yield event
                if event is None:
                    return
            except asyncio.QueueEmpty:
                break
        # Phase 3: live
        while True:
            event = await run.event_queue.get()
            yield event
            if event is None:
                return

    # ── cancel ────────────────────────────────────────────────────────────────

    async def request_cancel(self, run_id: str) -> None:
        run = _runs.get(run_id)
        if run is None or run.is_terminal():
            return
        # Set terminal status
        run.status     = "cancelled"
        run.updated_at = datetime.now(timezone.utc)
        run.finished_at = datetime.now(timezone.utc)
        # Push stamped cancelled event
        event_id = run.event_id_counter
        run.event_id_counter += 1
        stamped: dict = {
            "event":     "cancelled",
            "run_id":    run_id,
            "message":   "用户取消了分析",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_id":  event_id,
        }
        if len(run.events) < MAX_EVENTS_PER_RUN:
            run.events.append(stamped)
        await run.event_queue.put(stamped)
        # Push sentinel
        await run.event_queue.put(None)

    async def is_cancel_requested(self, run_id: str) -> bool:
        run = _runs.get(run_id)
        return run is not None and run.status == "cancelled"
