"""
RealtimeAnalysisRunner — SSE 实时进度推送分析运行器（M25-b：cancel 检查点）。

M25-b 新增：
  - _check_cancelled()：关键阶段检查 run.status，提前退出，不写 completed
  - 取消检查点：agent 阶段后、synthesis 前；synthesis 后、report_ready 前
  - 取消后推送 sentinel 通知 SSE handler 关闭流

M40-a 重构：
  - run_analysis(run_ref, registry, db) 替代 run_analysis(run, db)
  - 所有状态访问通过 AnalysisRunRegistry 方法（push_event / update_status / is_cancel_requested）
  - P0 Bug 修复：output_language 移至 _do_run() 开头（原代码在 line 188 定义但 line 149 已使用）

设计原则：
  - 不修改 ComprehensiveAnalysisCoordinator 及任何已有 Agent。
  - asyncio.as_completed 逐个 Agent 推送完成事件。
  - synthesis LLM 仍用 asyncio.to_thread。
  - AsyncSession 由调用方独立开启。
  - cancel 语义：停止等待，不中断已启动的 to_thread 线程。

事件类型：
  analysis_started / identity_resolved /
  agent_started / agent_completed / agent_failed /
  synthesis_started / synthesis_completed /
  report_ready / analysis_failed / cancelled
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import BaseLLMClient
from app.agents.technical_analyst import TechnicalAnalystAgent
from app.agents.fundamental_analyst import FundamentalAnalystAgent
from app.agents.peer_comparison_analyst import PeerComparisonAnalystAgent
from app.agents.news_analyst import NewsAnalystAgent
from app.agents.comprehensive_analysis_coordinator import (
    ComprehensiveAnalysisCoordinator,
    SCOPE_AGENTS,
    _SYSTEM_PROMPT,
    _AGENT_TIMEOUT,
    _build_metadata,
    _build_single_agent_report,
    _fallback_report,
)
from app.services.run_registry_protocol import AnalysisRunRef, AnalysisRunRegistry

log = logging.getLogger(__name__)

# ── Progress distribution ─────────────────────────────────────────────────────
_AGENT_PROGRESS_START = 18
_AGENT_PROGRESS_END   = 75


def _agent_done_progress(agent_index: int, total_agents: int) -> int:
    span = _AGENT_PROGRESS_END - _AGENT_PROGRESS_START
    pct  = _AGENT_PROGRESS_START + int(span * (agent_index + 1) / total_agents)
    return min(pct, _AGENT_PROGRESS_END)


# ── RealtimeAnalysisRunner ────────────────────────────────────────────────────

class RealtimeAnalysisRunner:
    """SSE-aware analysis runner. run_analysis() should be wrapped in create_task()."""

    def __init__(self, llm: BaseLLMClient) -> None:
        self._llm         = llm
        self._technical   = TechnicalAnalystAgent(llm)
        self._fundamental = FundamentalAnalystAgent(llm)
        self._peer        = PeerComparisonAnalystAgent(llm)
        self._news        = NewsAnalystAgent(llm)
        self._coordinator = ComprehensiveAnalysisCoordinator(llm)

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
            log.error("RealtimeAnalysisRunner fatal [%s]: %s", run_ref.run_id, exc)
            await self._emit(run_ref, registry, "analysis_failed", progress=0, error=str(exc))
            await registry.update_status(run_ref.run_id, "failed", error=str(exc))
            await registry.push_event(run_ref.run_id, None)

    # ── Cancel checkpoint helper ──────────────────────────────────────────────

    async def _check_cancelled(
        self,
        run_ref:  AnalysisRunRef,
        registry: AnalysisRunRegistry,
    ) -> bool:
        """
        Return True and push sentinel if run was externally cancelled.
        Call at key stages; if True, caller should return immediately.
        """
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
        # P0 Bug fix (M40-a): output_language must be defined at the top of _do_run,
        # before it is used in asyncio.create_task() further below.
        output_language = run_ref.output_language or "zh-CN"

        await registry.update_status(run_ref.run_id, "running")

        # Step 1: analysis_started
        await self._emit(run_ref, registry, "analysis_started", progress=5,
                         message=f"开始分析 {market}/{symbol}，scope={analysis_scope}")

        # Step 2: stock identity
        stock_name = await ComprehensiveAnalysisCoordinator._fetch_stock_name(
            db, market, symbol
        )
        stock_identity = (
            f"{stock_name}（{market}/{symbol}）" if stock_name
            else f"{market}/{symbol}"
        )
        await self._emit(run_ref, registry, "identity_resolved", progress=10,
                         stock_name=stock_name or "",
                         stock_identity=stock_identity)

        # ── CANCEL CHECK: before agents ───────────────────────────────────────
        if await self._check_cancelled(run_ref, registry):
            return

        # Step 3: parallel agents with as_completed emit
        agents_to_run = SCOPE_AGENTS.get(analysis_scope, SCOPE_AGENTS["comprehensive"])
        sections: dict  = {}
        statuses: dict  = {}

        all_agents = ["technical", "fundamental", "peer_comparison", "news"]
        for a in all_agents:
            if a not in agents_to_run:
                statuses[a] = {"status": "skipped", "message": "该维度未纳入本次分析范围"}

        for name in agents_to_run:
            await self._emit(run_ref, registry, "agent_started", agent=name,
                             message=f"正在运行 {name} Agent")

        tasks = [
            asyncio.create_task(
                self._run_named_agent(name, db, market, symbol, output_language),
                name=f"agent_{name}",
            )
            for name in agents_to_run
        ]

        completed_count = 0
        for coro in asyncio.as_completed(tasks):
            if await registry.is_cancel_requested(run_ref.run_id):
                for t in tasks:
                    t.cancel()
                break

            agent_name, agent_result = await coro
            completed_count += 1
            progress = _agent_done_progress(completed_count - 1, len(agents_to_run))

            if isinstance(agent_result, Exception):
                err_msg = str(agent_result)
                log.error("RealtimeAnalysisRunner: agent '%s' failed [%s]: %s",
                          agent_name, run_ref.run_id, err_msg)
                sections[agent_name] = f"[{agent_name} 模块暂时不可用：{err_msg}]"
                statuses[agent_name] = {"status": "failed", "message": err_msg}
                await self._emit(run_ref, registry, "agent_failed", agent=agent_name,
                                 progress=progress, error=err_msg)
            else:
                sections[agent_name] = agent_result
                statuses[agent_name] = {"status": "success", "message": None}
                await self._emit(run_ref, registry, "agent_completed", agent=agent_name,
                                 progress=progress, chars=len(agent_result))

        # ── CANCEL CHECK: after agents, before synthesis ──────────────────────
        if await self._check_cancelled(run_ref, registry):
            return

        # Step 4: synthesis
        await self._emit(run_ref, registry, "synthesis_started", progress=80,
                         message="正在整合多维度分析，调用大模型生成综合报告")

        _single_scopes = {"technical_only", "fundamental_only", "peer_only", "news_only"}
        try:
            if analysis_scope in _single_scopes:
                agent_key = agents_to_run[0]
                report = _build_single_agent_report(
                    stock_identity, analysis_scope, sections.get(agent_key, ""),
                    output_language=output_language,
                )
            elif analysis_scope == "technical_fundamental":
                report = await self._coordinator._synthesize_tech_fundamental(
                    market, stock_identity, sections, output_language=output_language,
                )
            else:
                synthesis_user = self._coordinator._build_synthesis_prompt(
                    market, symbol, sections, stock_identity,
                    output_language=output_language,
                )
                messages = [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": synthesis_user},
                ]
                try:
                    report = await asyncio.to_thread(
                        self._llm.chat, messages, temperature=0.3
                    )
                except Exception as exc:
                    log.error("RealtimeAnalysisRunner: synthesis LLM failed [%s]: %s",
                              run_ref.run_id, exc)
                    report = _fallback_report(market, symbol, sections, exc, stock_identity,
                                              output_language=output_language)
        except Exception as exc:
            log.error("RealtimeAnalysisRunner: synthesis phase failed [%s]: %s",
                      run_ref.run_id, exc)
            report = _fallback_report(market, symbol, sections, exc, stock_identity,
                                      output_language=output_language)

        await self._emit(run_ref, registry, "synthesis_completed", progress=95)

        # ── CANCEL CHECK: after synthesis, before writing completed ───────────
        if await self._check_cancelled(run_ref, registry):
            return

        # Step 5: result
        metadata = _build_metadata(market, sections, statuses)
        metadata["analysis_scope"]   = analysis_scope
        metadata["workflow_engine"]  = "custom_coordinator"
        metadata["output_language"]  = output_language

        full_result = {
            "market":          market,
            "symbol":          symbol,
            "stock_name":      stock_name or "",
            "report":          report,
            "sections":        sections,
            "metadata":        metadata,
            "analysis_scope":  analysis_scope,
            "output_language": output_language,
        }

        await registry.update_status(run_ref.run_id, "completed", result=full_result)
        await self._emit(run_ref, registry, "report_ready", progress=100, result=full_result)
        await registry.push_event(run_ref.run_id, None)  # sentinel

    # ── Named agent wrapper ────────────────────────────────────────────────────

    async def _run_named_agent(
        self,
        agent_name:      str,
        db:              AsyncSession,
        market:          str,
        symbol:          str,
        output_language: str = "zh-CN",
    ) -> tuple:
        try:
            if agent_name == "technical":
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._technical.analyze, market, symbol, output_language),
                    timeout=_AGENT_TIMEOUT,
                )
            elif agent_name == "fundamental":
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._fundamental.analyze, market, symbol, output_language),
                    timeout=_AGENT_TIMEOUT,
                )
            elif agent_name == "peer_comparison":
                result = await asyncio.wait_for(
                    self._peer.analyze_async(db, market, symbol, output_language),
                    timeout=_AGENT_TIMEOUT,
                )
            elif agent_name == "news":
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._news.analyze, market, symbol, 72, 10, output_language),
                    timeout=_AGENT_TIMEOUT,
                )
            else:
                raise ValueError(f"Unknown agent: {agent_name}")
            return agent_name, result
        except asyncio.TimeoutError:
            return agent_name, TimeoutError(
                f"Agent '{agent_name}' timed out after {_AGENT_TIMEOUT}s"
            )
        except Exception as exc:
            return agent_name, exc

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
        log.debug("RealtimeAnalysisRunner emit [%s] %s progress=%s",
                  run_ref.run_id, event_type, kwargs.get("progress", "—"))
