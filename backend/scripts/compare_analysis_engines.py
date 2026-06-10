"""
compare_analysis_engines.py — Phase M4-b.5：LangGraph vs custom_coordinator 质量与延迟对比验证。

目标：
  同一股票、同一 analysis_scope 下，分别运行 custom_coordinator 与 LangGraph 路径，
  比较结构一致性、报告质量、执行延迟，形成灰度决策依据。

约束：
  - 不修改默认 engine（仍为 custom_coordinator）
  - 不修改前端
  - 不新增数据库 migration
  - 不修改旧接口 /analysis/comprehensive
  - 不保存测试报告到数据库（避免污染历史报告）
  - 不打印任何密钥、DATABASE_URL、SECRET_KEY、DEEPSEEK_API_KEY

运行方式：
  cd backend
  uv run python scripts/compare_analysis_engines.py
  uv run python scripts/compare_analysis_engines.py --market CN --symbol 000001 --scope technical_only
  uv run python scripts/compare_analysis_engines.py --full
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# ── app 层导入（只读，不修改）──────────────────────────────────────────────────
from app.agents.comprehensive_analysis_coordinator import ComprehensiveAnalysisCoordinator
from app.agents.langgraph_analysis_graph import LangGraphAnalysisRunner
from app.llm.factory import get_llm_client
from app.core.database import AsyncSessionLocal

# 屏蔽 SQLAlchemy / LangGraph INFO 噪声
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy.pool").setLevel(logging.ERROR)
logging.getLogger("langchain").setLevel(logging.ERROR)
logging.getLogger("langgraph").setLevel(logging.ERROR)
log = logging.getLogger("m4b5")

# ══════════════════════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════════════════════

# 延迟阈值（ratio = langgraph_elapsed / custom_elapsed）
_PERF_RATIO_THRESHOLDS: dict[str, float] = {
    "technical_only":        1.5,
    "fundamental_only":      1.5,
    "peer_only":             1.5,
    "news_only":             1.5,
    "technical_fundamental": 1.8,
    "comprehensive":         2.0,
}

# 默认测试 case（轻量，无 comprehensive）
_DEFAULT_CASES: list[tuple[str, str, str]] = [
    ("CN", "000001", "technical_only"),
    ("CN", "000001", "technical_fundamental"),
    ("CN", "000001", "news_only"),
    ("HK", "00700",  "technical_only"),
]

# --full 追加
_FULL_CASES: list[tuple[str, str, str]] = [
    ("CN", "000001", "comprehensive"),
    ("HK", "00700",  "comprehensive"),
]

# ══════════════════════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EngineResult:
    """单个 engine 的分析结果快照。"""
    engine:          str
    market:          str
    symbol:          str
    scope:           str
    elapsed:         float = 0.0
    ok:              bool  = False
    error_msg:       str   = ""

    # 响应字段
    stock_name:      str       = ""
    report:          str       = ""
    report_len:      int       = 0
    sections_keys:   list[str] = field(default_factory=list)
    agent_statuses:  dict[str, str] = field(default_factory=dict)
    workflow_engine: str       = ""
    analysis_scope:  str       = ""
    metadata_keys:   list[str] = field(default_factory=list)

    # 报告摘要
    report_title:    str = ""   # 第一行


@dataclass
class CaseResult:
    market:  str
    symbol:  str
    scope:   str
    custom:  EngineResult | None = None
    lg:      EngineResult | None = None

    structure_pass:      bool = False
    quality_pass:        bool = False
    performance_warning: bool = False

    structure_issues: list[str] = field(default_factory=list)
    quality_issues:   list[str] = field(default_factory=list)
    perf_ratio:       float = 0.0

    @property
    def verdict(self) -> str:
        if not self.structure_pass:
            return "FAIL"
        if not self.quality_pass or self.performance_warning:
            return "WARN"
        return "PASS"


# ══════════════════════════════════════════════════════════════════════════════
# 运行单次分析
# ══════════════════════════════════════════════════════════════════════════════

async def _run_custom(llm, db, market: str, symbol: str, scope: str) -> EngineResult:
    er = EngineResult(engine="custom_coordinator", market=market, symbol=symbol, scope=scope)
    t0 = time.perf_counter()
    try:
        coordinator = ComprehensiveAnalysisCoordinator(llm)
        result = await coordinator.analyze_scoped(db, market, symbol, scope)
        er.elapsed = time.perf_counter() - t0
        _fill_engine_result(er, result)
        er.ok = True
    except Exception as exc:
        er.elapsed = time.perf_counter() - t0
        er.error_msg = str(exc)
        log.error("custom_coordinator error [%s/%s] %s: %s", market, symbol, scope, exc)
    return er


async def _run_langgraph(llm, db, market: str, symbol: str, scope: str) -> EngineResult:
    er = EngineResult(engine="langgraph", market=market, symbol=symbol, scope=scope)
    t0 = time.perf_counter()
    try:
        runner = LangGraphAnalysisRunner(llm)
        result = await runner.analyze(db, market, symbol, scope)
        er.elapsed = time.perf_counter() - t0
        _fill_engine_result(er, result)
        er.ok = True
    except Exception as exc:
        er.elapsed = time.perf_counter() - t0
        er.error_msg = str(exc)
        log.error("langgraph error [%s/%s] %s: %s", market, symbol, scope, exc)
    return er


def _fill_engine_result(er: EngineResult, result: dict) -> None:
    er.stock_name      = result.get("stock_name", "") or ""
    er.report          = result.get("report", "") or ""
    er.report_len      = len(er.report)
    er.analysis_scope  = result.get("analysis_scope", "") or ""
    er.sections_keys   = sorted((result.get("sections") or {}).keys())
    metadata           = result.get("metadata") or {}
    er.metadata_keys   = sorted(metadata.keys())
    er.workflow_engine = metadata.get("workflow_engine", "") or ""
    agents             = metadata.get("agents") or {}
    er.agent_statuses  = {k: v.get("status", "?") if isinstance(v, dict) else str(v)
                          for k, v in agents.items()}
    # 取报告第一行（标题）
    first_line = er.report.strip().split("\n")[0] if er.report.strip() else ""
    er.report_title = first_line[:120]


# ══════════════════════════════════════════════════════════════════════════════
# 结构检查
# ══════════════════════════════════════════════════════════════════════════════

_REQUIRED_RESULT_KEYS  = {"market", "symbol", "stock_name", "report", "sections", "metadata", "analysis_scope"}
_REQUIRED_METADATA_KEYS = {"generated_at", "agents", "warnings", "analysis_scope", "workflow_engine"}
_REQUIRED_AGENT_KEYS   = {"technical", "fundamental", "peer_comparison", "news"}
_VALID_AGENT_STATUSES  = {"success", "failed", "timeout", "degraded", "skipped"}

_SCOPE_EXPECTED_SECTIONS: dict[str, set[str]] = {
    "technical_only":        {"technical"},
    "fundamental_only":      {"fundamental"},
    "peer_only":             {"peer_comparison"},
    "news_only":             {"news"},
    "technical_fundamental": {"technical", "fundamental"},
    "comprehensive":         {"technical", "fundamental", "peer_comparison", "news"},
}


def _check_structure(er: EngineResult, scope: str) -> list[str]:
    """返回结构问题列表（空 = 通过）。"""
    issues: list[str] = []
    tag = f"[{er.engine}]"

    if not er.ok:
        return [f"{tag} 调用失败: {er.error_msg}"]

    # 1. result dict keys（通过 fill 验证，这里检查关键字段是否非空）
    if not er.stock_name:
        issues.append(f"{tag} stock_name 为空")
    if not er.report:
        issues.append(f"{tag} report 为空")
    if not er.analysis_scope:
        issues.append(f"{tag} analysis_scope 为空")
    elif er.analysis_scope != scope:
        issues.append(f"{tag} analysis_scope={er.analysis_scope} 与输入 {scope} 不一致")

    # 2. metadata keys
    missing_meta = _REQUIRED_METADATA_KEYS - set(er.metadata_keys)
    if missing_meta:
        issues.append(f"{tag} metadata 缺少字段: {missing_meta}")

    # 3. workflow_engine
    expected_wf = {"custom_coordinator": "custom_coordinator", "langgraph": "langgraph"}[er.engine]
    if er.workflow_engine != expected_wf:
        issues.append(f"{tag} workflow_engine={er.workflow_engine!r}，期望 {expected_wf!r}")

    # 4. sections keys
    expected_sections = _SCOPE_EXPECTED_SECTIONS.get(scope, set())
    actual_sections   = set(er.sections_keys)
    missing_sec = expected_sections - actual_sections
    extra_sec   = actual_sections - expected_sections
    if missing_sec:
        issues.append(f"{tag} sections 缺少: {missing_sec}")
    if extra_sec:
        issues.append(f"{tag} sections 多出: {extra_sec}")

    # 5. agent statuses
    missing_agents = _REQUIRED_AGENT_KEYS - set(er.agent_statuses.keys())
    if missing_agents:
        issues.append(f"{tag} metadata.agents 缺少: {missing_agents}")
    for agent_key, status in er.agent_statuses.items():
        if status not in _VALID_AGENT_STATUSES:
            issues.append(f"{tag} metadata.agents[{agent_key}].status={status!r} 非法")

    # 6. report 内容健全性
    if er.report:
        if "undefined" in er.report:
            issues.append(f"{tag} report 包含 'undefined'")
        if "[object Object]" in er.report:
            issues.append(f"{tag} report 包含 '[object Object]'")
        # null 单词检查（仅独立出现，不误判中文"null"概率低）
        import re
        if re.search(r"\bnull\b", er.report):
            issues.append(f"{tag} report 包含裸 'null'")

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# 质量检查
# ══════════════════════════════════════════════════════════════════════════════

_IDENTITY_HINTS: dict[str, list[str]] = {
    "CN/000001": ["平安银行", "000001"],
    "HK/00700":  ["腾讯控股", "腾讯", "Tencent", "00700"],
}

_SCOPE_COVERAGE_HINTS: dict[str, list[str]] = {
    "technical_only":        ["仅覆盖技术面", "技术面", "技术分析"],
    "news_only":             ["仅覆盖新闻面", "新闻面", "新闻"],
    "fundamental_only":      ["仅覆盖基本面", "基本面", "基本面分析"],
    "peer_only":             ["仅覆盖同行对比", "同行对比", "同行比较"],
    "technical_fundamental": ["技术面与基本面", "技术面", "基本面"],
    "comprehensive":         ["核心摘要", "数据来源", "风险提示"],
}

_RISK_HINTS = ["风险提示", "不构成投资建议", "仅供研究参考"]


def _check_quality(er: EngineResult, market: str, symbol: str, scope: str) -> list[str]:
    """返回质量问题列表（空 = 通过）。"""
    issues: list[str] = []
    tag = f"[{er.engine}]"

    if not er.ok or not er.report:
        return []  # 结构失败时不再叠加质量问题

    report = er.report

    # 1. 股票身份
    key = f"{market}/{symbol}"
    hints = _IDENTITY_HINTS.get(key)
    if hints:
        if not any(h in report for h in hints):
            issues.append(f"{tag} 报告未包含股票身份（期望其一：{hints}）")

    # 2. 风险提示
    if not any(h in report for h in _RISK_HINTS):
        issues.append(f"{tag} 报告未包含风险提示")

    # 3. 覆盖范围
    coverage_hints = _SCOPE_COVERAGE_HINTS.get(scope, [])
    if coverage_hints and not any(h in report for h in coverage_hints):
        issues.append(f"{tag} {scope} 报告未体现覆盖范围（期望其一：{coverage_hints}）")

    # 4. technical_fundamental 不应声称覆盖同行与新闻面
    if scope == "technical_fundamental":
        if "同行对比" in report and "同行对比分析" in report:
            issues.append(f"{tag} technical_fundamental 报告疑似包含同行对比内容")
        if "新闻面分析" in report and "新闻分析报告" in report:
            issues.append(f"{tag} technical_fundamental 报告疑似包含新闻面内容")

    # 5. comprehensive 多维结构
    if scope == "comprehensive":
        expected_sections = ["核心摘要", "数据来源", "风险提示"]
        missing = [s for s in expected_sections if s not in report]
        if missing:
            issues.append(f"{tag} comprehensive 报告缺少章节标志: {missing}")

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# 单 case 执行
# ══════════════════════════════════════════════════════════════════════════════

async def run_case(
    llm,
    market: str,
    symbol: str,
    scope: str,
) -> CaseResult:
    cr = CaseResult(market=market, symbol=symbol, scope=scope)

    print(f"\n{'─'*70}")
    print(f"Case: {market}/{symbol}  scope={scope}")
    print(f"  Running custom_coordinator …", flush=True)

    async with AsyncSessionLocal() as db:
        cr.custom = await _run_custom(llm, db, market, symbol, scope)

    print(f"  Running langgraph …", flush=True)

    async with AsyncSessionLocal() as db:
        cr.lg = await _run_langgraph(llm, db, market, symbol, scope)

    # ── 结构检查 ────────────────────────────────────────────────────────────
    issues_c = _check_structure(cr.custom, scope)
    issues_l = _check_structure(cr.lg,     scope)
    cr.structure_issues = issues_c + issues_l
    cr.structure_pass   = len(cr.structure_issues) == 0

    # ── 质量检查 ────────────────────────────────────────────────────────────
    qissues_c = _check_quality(cr.custom, market, symbol, scope)
    qissues_l = _check_quality(cr.lg,     market, symbol, scope)
    cr.quality_issues = qissues_c + qissues_l
    cr.quality_pass   = len(cr.quality_issues) == 0

    # ── 延迟对比 ────────────────────────────────────────────────────────────
    if cr.custom.elapsed > 0 and cr.lg.elapsed > 0:
        cr.perf_ratio = cr.lg.elapsed / cr.custom.elapsed
        threshold = _PERF_RATIO_THRESHOLDS.get(scope, 2.0)
        cr.performance_warning = cr.perf_ratio > threshold

    return cr


# ══════════════════════════════════════════════════════════════════════════════
# 输出
# ══════════════════════════════════════════════════════════════════════════════

def _status_icon(ok: bool) -> str:
    return "✅" if ok else "❌"


def print_case_result(cr: CaseResult) -> None:
    c = cr.custom
    l = cr.lg

    print(f"\nCase:")
    print(f"  market/symbol:        {cr.market}/{cr.symbol}")
    print(f"  scope:                {cr.scope}")
    print(f"  custom_engine:        {c.workflow_engine if c else 'N/A'}")
    print(f"  langgraph_engine:     {l.workflow_engine if l else 'N/A'}")
    print(f"  custom_sections:      {c.sections_keys if c else []}")
    print(f"  langgraph_sections:   {l.sections_keys if l else []}")
    print(f"  custom_statuses:      {c.agent_statuses if c else {}}")
    print(f"  langgraph_statuses:   {l.agent_statuses if l else {}}")
    print(f"  custom_title:         {c.report_title if c else ''}")
    print(f"  langgraph_title:      {l.report_title if l else ''}")
    print(f"  custom_report_len:    {c.report_len if c else 0}")
    print(f"  langgraph_report_len: {l.report_len if l else 0}")
    print(f"  custom_elapsed:       {c.elapsed:.2f}s" if c else "  custom_elapsed:       N/A")
    print(f"  langgraph_elapsed:    {l.elapsed:.2f}s" if l else "  langgraph_elapsed:    N/A")
    ratio_str = f"{cr.perf_ratio:.2f}x" if cr.perf_ratio > 0 else "N/A"
    print(f"  ratio:                {ratio_str}")
    print(f"  structure_pass:       {_status_icon(cr.structure_pass)} {'' if cr.structure_pass else '← ' + '; '.join(cr.structure_issues[:3])}")
    print(f"  quality_pass:         {_status_icon(cr.quality_pass)} {'' if cr.quality_pass else '← ' + '; '.join(cr.quality_issues[:3])}")
    perf_warn = "⚠️  PERFORMANCE_WARNING" if cr.performance_warning else "—"
    print(f"  performance_warning:  {perf_warn}")
    verdict_icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[cr.verdict]
    print(f"  result:               {verdict_icon} {cr.verdict}")


def print_summary(results: list[CaseResult]) -> None:
    print(f"\n{'═'*70}")
    print("SUMMARY")
    print(f"{'═'*70}")

    total = len(results)
    passed = sum(1 for r in results if r.verdict == "PASS")
    warned = sum(1 for r in results if r.verdict == "WARN")
    failed = sum(1 for r in results if r.verdict == "FAIL")

    print(f"  total cases:          {total}")
    print(f"  PASS:                 {passed}")
    print(f"  WARN:                 {warned}")
    print(f"  FAIL:                 {failed}")

    # 汇总结构问题
    all_struct_issues = [i for r in results for i in r.structure_issues]
    print(f"\n  结构不兼容:            {'无' if not all_struct_issues else '是'}")
    for issue in all_struct_issues:
        print(f"    ⚠  {issue}")

    # 汇总质量问题
    all_quality_issues = [i for r in results for i in r.quality_issues]
    print(f"  质量明显下降:          {'无' if not all_quality_issues else '是'}")
    for issue in all_quality_issues:
        print(f"    ⚠  {issue}")

    # 汇总性能问题
    perf_warns = [(r.market, r.symbol, r.scope, r.perf_ratio) for r in results if r.performance_warning]
    print(f"  性能明显劣化:          {'无' if not perf_warns else '是'}")
    for market, symbol, scope, ratio in perf_warns:
        print(f"    ⚠  {market}/{symbol} {scope} ratio={ratio:.2f}x > {_PERF_RATIO_THRESHOLDS.get(scope, 2.0)}x")

    print()

    # 灰度建议
    all_pass_or_warn = all(r.verdict in {"PASS", "WARN"} for r in results)
    no_struct_issues = not all_struct_issues
    recommend_continue = all_pass_or_warn and no_struct_issues

    print(f"  建议继续灰度:          {'是' if recommend_continue else '否（存在 FAIL 或结构不兼容）'}")

    # M4-b.6 建议（所有 case 均 PASS，无质量/性能问题）
    recommend_m4b6 = (
        passed == total
        and not all_struct_issues
        and not all_quality_issues
        and not perf_warns
    )
    print(f"  建议进入 M4-b.6:       {'是（所有 case PASS，无结构/质量/性能问题）' if recommend_m4b6 else '否（存在 WARN 或 FAIL，建议继续观察）'}")
    print(f"  默认 engine:           custom_coordinator（未修改，前端无感知）")
    print()


# ══════════════════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> int:
    parser = argparse.ArgumentParser(description="M4-b.5: compare_analysis_engines")
    parser.add_argument("--market", default=None,  help="指定单个 market（需配合 --symbol --scope）")
    parser.add_argument("--symbol", default=None,  help="指定单个 symbol")
    parser.add_argument("--scope",  default=None,  help="指定单个 analysis_scope")
    parser.add_argument("--full",   action="store_true", help="加入 comprehensive 场景")
    args = parser.parse_args()

    # 构建 case 列表
    if args.market and args.symbol and args.scope:
        cases = [(args.market, args.symbol, args.scope)]
    else:
        cases = list(_DEFAULT_CASES)
        if args.full:
            cases.extend(_FULL_CASES)

    print(f"Phase M4-b.5: LangGraph vs custom_coordinator 对比验证")
    print(f"cases ({len(cases)}): {[(m, s, sc) for m, s, sc in cases]}")

    llm = get_llm_client()

    results: list[CaseResult] = []
    for market, symbol, scope in cases:
        cr = await run_case(llm, market, symbol, scope)
        print_case_result(cr)
        results.append(cr)

    print_summary(results)

    # 返回码：有 FAIL → 1
    return 0 if all(r.verdict != "FAIL" for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
