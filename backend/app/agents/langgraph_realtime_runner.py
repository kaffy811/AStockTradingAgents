"""
LangGraphRealtimeRunner — LangGraph SSE 实时进度推送运行器（M25-c）。

策略：
  - 使用 graph.astream(stream_mode="updates") 逐节点流式获取状态更新
  - 手动累积 full_state（处理 annotated reducer 字段 sections/statuses/errors）
  - 将 LangGraph 节点名映射到统一 SSE 事件模型
  - 3 个取消检查点（与 RealtimeAnalysisRunner 对齐）
  - result shape 与 custom_coordinator 完全兼容
  - metadata.workflow_engine = "langgraph"

M40-a 重构：
  - run_analysis(run_ref, registry, db) 替代 run_analysis(run, db)
  - 所有状态访问通过 AnalysisRunRegistry 方法

事件映射：
  _fetch_identity_node   → analysis_started (预先) + identity_resolved
  _prepare_scope_node    → agent_started × N
  _technical/fundamental/peer/news_node → agent_completed / agent_failed
  (全部 agent 完成后)    → synthesis_started  [cancel checkpoint]
  _synthesis_node / _single_agent_report_node → synthesis_completed
  _finalize_node         → [cancel checkpoint]
  (graph 完成后)         → report_ready

注意：
  - _collect_node 返回 {} 不做映射（用"最后一个 agent 完成"触发 synthesis_started）
  - 未使用 astream_events（节点级 updates 已足够）
  - cancel 语义：停止等待，不强制中断已启动的 asyncio 任务
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.langgraph_analysis_graph import build_analysis_graph
from app.services.run_registry_protocol import AnalysisRunRef, AnalysisRunRegistry

log = logging.getLogger(__name__)

# ── Progress distribution (mirrors RealtimeAnalysisRunner) ────────────────────
_AGENT_PROGRESS_START = 18
_AGENT_PROGRESS_END   = 75


def _agent_done_progress(agent_index: int, total_agents: int) -> int:
    span = _AGENT_PROGRESS_END - _AGENT_PROGRESS_START
    pct  = _AGENT_PROGRESS_START + int(span * (agent_index + 1) / total_agents)
    return min(pct, _AGENT_PROGRESS_END)


# ── Node → agent key mapping ──────────────────────────────────────────────────
_NODE_TO_AGENT: dict = {
    "_technical_node":   "technical",
    "_fundamental_node": "fundamental",
    "_peer_node":        "peer_comparison",
    "_news_node":        "news",
}

# Fields that use _merge_dict reducer in AnalysisState
_MERGE_DICT_KEYS = frozenset({"sections", "statuses", "errors"})


def _merge_updates(full_state: dict, updates: dict) -> None:
    """Apply a node's output updates to the accumulated full_state dict.
    LangGraph 1.x may yield None for conditional-edge pass-through nodes; skip gracefully.
    """
    if not updates:
        return
    for k, v in updates.items():
        if k in _MERGE_DICT_KEYS and isinstance(v, dict):
            existing = dict(full_state.get(k) or {})
            existing.update(v)
            full_state[k] = existing
        else:
            full_state[k] = v


# ── LangGraphRealtimeRunner ───────────────────────────────────────────────────

class LangGraphRealtimeRunner:
    """SSE-aware LangGraph runner. run_analysis() should be wrapped in create_task()."""

    def __init__(self, llm) -> None:
        graph     = build_analysis_graph()
        self._app = graph.compile()
        self._llm = llm

    # ── Public entry ──────────────────────────────────────────────────────────

    async def run_analysis(
        self,
        run_ref:  AnalysisRunRef,
        registry: AnalysisRunRegistry,
        db:       AsyncSession,
    ) -> None:
        try:
            await self._do_run(run_ref, registry, db)
        except asyncio.CancelledError:
            await self._emit(run_ref, registry, "cancelled", progress=0, message="分析已取消")
            await registry.update_status(run_ref.run_id, "cancelled")
            await registry.push_event(run_ref.run_id, None)
        except Exception as exc:
            log.error("LangGraphRealtimeRunner fatal [%s]: %s", run_ref.run_id, exc)
            await self._emit(run_ref, registry, "analysis_failed", progress=0, error=str(exc))
            await registry.update_status(run_ref.run_id, "failed", error=str(exc))
            await registry.push_event(run_ref.run_id, None)

    # ── Cancel checkpoint helper ──────────────────────────────────────────────

    async def _check_cancelled(
        self,
        run_ref:  AnalysisRunRef,
        registry: AnalysisRunRegistry,
    ) -> bool:
        if await registry.is_cancel_requested(run_ref.run_id):
            await registry.push_event(run_ref.run_id, None)
            return True
        return False

    # ── Core pipeline ─────────────────────────────────────────────────────────

    async def _do_run(
        self,
        run_ref:  AnalysisRunRef,
        registry: AnalysisRunRegistry,
        db:       AsyncSession,
    ) -> None:
        market          = run_ref.market
        symbol          = run_ref.symbol
        analysis_scope  = run_ref.analysis_scope
        output_language = run_ref.output_language or "zh-CN"

        await registry.update_status(run_ref.run_id, "running")

        # Step 1: analysis_started
        await self._emit(run_ref, registry, "analysis_started", progress=5,
                         message=f"开始分析 {market}/{symbol}，scope={analysis_scope} [LangGraph]")

        # ── CANCEL CHECK: before graph ────────────────────────────────────────
        if await self._check_cancelled(run_ref, registry):
            return

        initial_state: dict = {
            "market":          market,
            "symbol":          symbol,
            "analysis_scope":  analysis_scope,
            "output_language": output_language,
            "stock_name":      "",
            "stock_identity":  "",
            "agents_to_run":   [],
            "sections":        {},
            "statuses":        {},
            "errors":          {},
            "report":          "",
            "metadata":        {},
            "warnings":        [],
            "workflow_engine": "",
        }

        config = {
            "configurable": {
                "llm": self._llm,
                "db":  db,
            }
        }

        # Accumulated full state (handles annotated reducer fields manually)
        full_state:    dict      = dict(initial_state)
        agents_to_run: list      = []
        completed_count           = 0
        synthesis_announced       = False   # guard against double synthesis_started

        async for node_update in self._app.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            # Per-node cancel check
            if await registry.is_cancel_requested(run_ref.run_id):
                await registry.push_event(run_ref.run_id, None)
                return

            for node_name, updates in node_update.items():
                # Accumulate state (LangGraph 1.x may yield None for routing nodes)
                if updates is None:
                    continue
                _merge_updates(full_state, updates)

                # ── identity_resolved ──────────────────────────────────────
                if node_name == "_fetch_identity_node":
                    stock_name     = updates.get("stock_name", "")
                    stock_identity = updates.get("stock_identity", f"{market}/{symbol}")
                    await self._emit(run_ref, registry, "identity_resolved", progress=10,
                                     stock_name=stock_name,
                                     stock_identity=stock_identity)

                # ── agent_started ×N ──────────────────────────────────────
                elif node_name == "_prepare_scope_node":
                    agents_to_run = list(updates.get("agents_to_run") or [])
                    for agent in agents_to_run:
                        await self._emit(run_ref, registry, "agent_started", agent=agent,
                                         message=f"正在运行 {agent} Agent")

                # ── agent_completed / agent_failed ────────────────────────
                elif node_name in _NODE_TO_AGENT:
                    agent_key  = _NODE_TO_AGENT[node_name]
                    completed_count += 1
                    n_agents   = len(agents_to_run) if agents_to_run else 1
                    progress   = _agent_done_progress(completed_count - 1, n_agents)

                    agent_status_info = updates.get("statuses", {}).get(agent_key, {})
                    if agent_status_info.get("status") in ("failed", "timeout"):
                        err_msg = agent_status_info.get("message", "未知错误")
                        await self._emit(run_ref, registry, "agent_failed", agent=agent_key,
                                         progress=progress, error=err_msg)
                    else:
                        section_text = updates.get("sections", {}).get(agent_key, "")
                        await self._emit(run_ref, registry, "agent_completed", agent=agent_key,
                                         progress=progress, chars=len(section_text))

                    # All agents done → synthesis_started
                    if completed_count >= n_agents and not synthesis_announced:
                        synthesis_announced = True
                        # ── CANCEL CHECK: after agents, before synthesis ────
                        if await self._check_cancelled(run_ref, registry):
                            return
                        await self._emit(run_ref, registry, "synthesis_started", progress=80,
                                         message="正在整合多维度分析，调用大模型生成综合报告")

                # ── synthesis_started fallback via _collect_node ──────────
                elif node_name == "_collect_node":
                    if not synthesis_announced:
                        synthesis_announced = True
                        if await self._check_cancelled(run_ref, registry):
                            return
                        await self._emit(run_ref, registry, "synthesis_started", progress=80,
                                         message="正在整合多维度分析，调用大模型生成综合报告")

                # ── synthesis_completed ───────────────────────────────────
                elif node_name in ("_synthesis_node", "_single_agent_report_node"):
                    await self._emit(run_ref, registry, "synthesis_completed", progress=95)

                # ── finalize: cancel check only ───────────────────────────
                elif node_name == "_finalize_node":
                    if await self._check_cancelled(run_ref, registry):
                        return

        # ── Build final result from accumulated state ─────────────────────────
        result = {
            "market":          market,
            "symbol":          symbol,
            "stock_name":      full_state.get("stock_name", ""),
            "report":          full_state.get("report", ""),
            "sections":        dict(full_state.get("sections") or {}),
            "metadata":        full_state.get("metadata", {}),
            "analysis_scope":  analysis_scope,
            "output_language": output_language,
        }

        await registry.update_status(run_ref.run_id, "completed", result=result)
        await self._emit(run_ref, registry, "report_ready", progress=100, result=result)
        await registry.push_event(run_ref.run_id, None)  # sentinel

    # ── Emit helper ───────────────────────────────────────────────────────────

    async def _emit(
        self,
        run_ref:    AnalysisRunRef,
        registry:   AnalysisRunRegistry,
        event_type: str,
        **kwargs,
    ) -> None:
        event = {
            "event":     event_type,
            "run_id":    run_ref.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        await registry.push_event(run_ref.run_id, event)
        log.debug("LangGraphRealtimeRunner emit [%s] %s progress=%s",
                  run_ref.run_id, event_type, kwargs.get("progress", "—"))
