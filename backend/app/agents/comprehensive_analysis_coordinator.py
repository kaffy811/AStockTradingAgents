"""
ComprehensiveAnalysisCoordinator — 综合分析协调器（MVP，普通 Python class）。

调用链路：
  analyze(market, symbol)
    ├─ ThreadPoolExecutor(max_workers=4) 并行调用：
    │    ├─ TechnicalAnalystAgent.analyze()
    │    ├─ FundamentalAnalystAgent.analyze()
    │    ├─ PeerComparisonAnalystAgent.analyze()
    │    └─ NewsAnalystAgent.analyze()
    ├─ 汇总 sections（失败 section 记录错误说明）
    ├─ _build_synthesis_prompt()     # 各 section 按限制截断，注入约束
    └─ BaseLLMClient.chat()          # 综合摘要 LLM 调用
    → 返回 dict: {market, symbol, report, sections, metadata}

设计原则：
  - 不使用 LangGraph / LangChain。
  - 四个 Agent 并行运行，单个失败不阻塞整体。
  - 综合报告只整合子报告已有信息，不新增推断。
  - technical / fundamental / peer_comparison 子报告截断至 4000 字符；
    news 子报告截断至 3000 字符；完整内容在 sections 中保留。
  - 不给买卖建议，不编造缺失字段，结尾必须包含免责声明。
"""

from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import BaseLLMClient
from app.agents.technical_analyst import TechnicalAnalystAgent
from app.agents.fundamental_analyst import FundamentalAnalystAgent
from app.agents.peer_comparison_analyst import PeerComparisonAnalystAgent
from app.agents.news_analyst import NewsAnalystAgent

log = logging.getLogger(__name__)

# ── analysis_scope 常量 ───────────────────────────────────────────────────────

VALID_SCOPES: frozenset[str] = frozenset({
    "comprehensive",
    "technical_only",
    "fundamental_only",
    "peer_only",
    "news_only",
    "technical_fundamental",
})

VALID_OUTPUT_LANGUAGES: frozenset[str] = frozenset({
    "zh-CN", "en-US", "zh-TW", "ja-JP", "ko-KR", "es-ES",
})

OUTPUT_LANGUAGE_LABELS: dict[str, str] = {
    "zh-CN": "简体中文",
    "en-US": "English (US)",
    "zh-TW": "繁體中文",
    "ja-JP": "日本語",
    "ko-KR": "한국어",
    "es-ES": "Español",
}

SCOPE_AGENTS: dict[str, list[str]] = {
    "comprehensive":         ["technical", "fundamental", "peer_comparison", "news"],
    "technical_only":        ["technical"],
    "fundamental_only":      ["fundamental"],
    "peer_only":             ["peer_comparison"],
    "news_only":             ["news"],
    "technical_fundamental": ["technical", "fundamental"],
}

_SCOPE_REPORT_TITLES: dict[str, str] = {
    "technical_only":        "技术面分析报告",
    "fundamental_only":      "基本面分析报告",
    "peer_only":             "同行对比分析报告",
    "news_only":             "新闻面分析报告",
    "technical_fundamental": "技术面与基本面分析报告",
    "comprehensive":         "综合分析报告",
}

_SCOPE_DESCRIPTIONS: dict[str, str] = {
    "technical_only":        "技术面分析，不包含基本面、同行对比与新闻面内容",
    "fundamental_only":      "基本面分析，不包含技术面、同行对比与新闻面内容",
    "peer_only":             "同行对比分析，不包含技术面、基本面与新闻面内容",
    "news_only":             "新闻面分析，不包含技术面、基本面与同行对比内容",
    "technical_fundamental": "技术面与基本面分析，不包含同行对比与新闻面内容",
}

# 摘要段落中用于说明维度覆盖的简短描述
_SCOPE_SUMMARY_DIMS: dict[str, str] = {
    "technical_only":        "技术面维度（K 线、均线、成交量等行情数据）",
    "fundamental_only":      "基本面维度（财务与经营数据）",
    "peer_only":             "同行对比维度（行业横向基本面观察）",
    "news_only":             "新闻面维度（近 72 小时相关新闻）",
    "technical_fundamental": "技术面与基本面双维度",
}

# 传给综合 LLM 的每个结构化子摘要最大字符数。sections 仍保留完整子报告。
_SECTION_MAX_CHARS = 2200
_NEWS_SECTION_MAX_CHARS = 1800
_SYNTHESIS_PROMPT_MAX_CHARS = 9500

# 每个 Agent 超时（秒）
_AGENT_TIMEOUT = 300


# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位综合股票分析协调员，负责将技术面、基本面、同行对比、新闻面四份子报告的结构化证据摘要整合为简洁的综合分析报告。

【封闭证据集规则（必须严格遵守）】
- 用户消息的【分析目标】中包含"股票："字段，该字段是本次分析对象的完整标识（如"平安银行（CN/000001）"或"腾讯控股（HK/00700）"）。
- 只能总结四个子报告证据摘要中已经出现的事实。
- 不得新增任何数字，不得重新计算财务指标、技术指标或估值。
- 不得为新闻补充未出现的原因，不得生成新公司、同行、事件或指标。
- 不得把"可能/需观察/数据不足"改写成确定结论。
- 不得把不同时间范围的数据放在同一句直接比较。
- 不得把同行样本结果写成目标公司自身数据。
- 不得删除重要数据限制，不得虚构来源、URL、页码。
- 不得输出 chain of thought、内部推理、工具参数或执行轨迹。
- 股票名称、代码、market 必须与输入一致。

【严格禁止事项】
以下内容一律禁止，违反即为无效输出：
1. 禁止给出买入、卖出、持有建议。
   严禁使用：必涨、必跌、稳赚、强烈买入、强烈卖出、满仓、梭哈、保证收益、抄底、逃顶、
   清仓、加仓、减仓推荐等表达。
2. 禁止给出目标价或预测具体涨跌幅。
3. 禁止编造任何未在子报告中出现的数据，包括但不限于：
   PE、PB、ROE、净利润、营业收入、现金流、资产负债率、竞争对手、行业排名、护城河。
4. 子报告中标记为 [缺失]、[不可用]、null、"数据不足"、"暂不评价" 的字段，
   一律不得在综合报告中引用、推断或估算。
   - 当某字段在子报告中缺失时，必须使用以下表达方式之一：
     "当前数据源未返回 {字段名}，因此无法在本报告中展开"
     "由于 {字段名} 字段在本次数据获取中未能覆盖，此项暂不评价"
     "本次分析中该字段数据不可用"
   - 禁止写成"公司没有 PE/PB"或"该公司 PE 为零"等暗示公司本身缺陷的表达。
5. 某个 section 是错误说明（以 "[xxx 模块暂时不可用" 开头）时，
   综合报告必须明确说明该维度数据暂缺，不得假设该模块正常运行。
6. HK（港股）基本面数据不足时，综合报告必须说明分析受限。
7. 综合摘要只能整合，不得放大：
   - 不新增任何子报告中未出现的事实或数据；
   - 不扩大子报告的局部结论；
   - 不将局部信号概括为全局确定性判断；
   - 不将多个审慎信号合并成确定性结论；
   - 综合报告的结论不得比子报告更乐观或更悲观，只能审慎整合与呈现。
8. 同行配置为手动映射时（PEER_MAP），不得将对比结论当作严格行业结论。
9. 子报告可能经过长度截断，只能基于可见内容整合，不得补充未出现的数据。
10. 新闻面约束（严格执行）：
    - 新闻面要点只能整合新闻面子报告（子报告 4）中已给出的结论，不得编造新闻。
    - 不得引用新闻 section 中未出现的新闻事件、标题或来源。
    - 如果新闻 section 说明"暂无相关新闻数据"或"items 为空"，
      综合报告的新闻面要点必须明确写明"本时间窗口内暂无新闻数据"，不得补充任何新闻。
    - 如果新闻 section 提示"keyword search""关键词搜索"或"相关性可能较弱"，
      综合报告必须说明"港股新闻通过关键词搜索获取，新闻相关性需谨慎判断"。
    - 不得将新闻分析写成确定性利好或确定性利空。
    - 严禁使用：该新闻利好、该新闻利空、将推动股价上涨、将导致下跌、
      对股价形成确定性支撑、对股价形成确定性打压。
    - 只能使用中性表达：
      "可能影响市场情绪""需要继续观察""对短期关注度可能有影响"
      "仍需结合价格、成交量、基本面和后续公告观察""新闻解读存在不确定性"等。

11. 过强措辞约束（严格执行）：
    以下表达一律禁止直接使用，必须替换为括号内的审慎措辞：
    - "明确利好" → "可能对市场情绪有正面影响（仍需后续数据验证）"
    - "明确利空" → "可能对市场情绪有负面影响（仍需后续数据验证）"
    - "必然上涨 / 必然下跌" → "在当前可用数据范围内存在一定[上行/下行]压力"
    - "确定性机会 / 确定性风险" → "在当前样本范围内存在潜在机会/风险，仍需后续验证"
    - "强烈建议买入 / 卖出" → （完全禁止，不得以任何变体出现）
    其他过强表达亦应改为审慎版本，例如：
    "多重压力叠加" → "短期可能承受一定压力"
    "极为稳健" → "在当前可用数据范围内表现较为稳健"
    "明显领先" → "相对同行样本具备一定优势"
    "强劲" → "在当前可用数据中表现较好"
    "显著利好 / 显著利空" → "可能对市场情绪有一定影响（方向仍需观察）"

【冲突与降级规则】
- 基本面与新闻冲突时，写为不同维度信号，不互相覆盖。
- 技术面与基本面冲突时，明确"中长期与短期信号不一致"。
- 同行与基本面冲突时，若自身增长但低于同行，不得写成"表现优秀"。
- 数据日期不同，明确各自时间范围，不做同周期直接比较。
- 某个子报告缺失时，对应章节写"本次无可用数据"，不得补写。
- 子报告冲突时明确列出冲突，不强行统一。

【输出格式】
输出完整 Markdown，严格按以下结构，标题名称不得更改，不得新增或删除章节：

# 综合分析报告：{【分析目标】中"股票："字段的完整内容}

## 综合结论
第一段直接回答，必须以"本报告分析对象为 {股票字段完整内容}。"开头。

## 核心事实卡片
最多 5 条，只列子报告已经出现的关键事实；不要重复完整子报告。

## 基本面与财务
只整合基本面子报告；无数据时写"本次无可用数据"。

## 市场与技术
只整合技术面子报告；无数据时写"本次无可用数据"。

## 新闻与事件
只整合新闻面子报告；无数据时写"本次无可用数据"。

## 同行位置
只整合同行对比子报告；无数据时写"本次无可用数据"。

## 关键联动
只写不同维度之间已由子报告支持的联动或冲突；不强行统一。

## 主要风险
列风险，不列数据缺失。

## 数据限制
列数据缺失、字段覆盖、时间范围、截断、来源限制。必须保留子报告限制。

## 后续观察
中性观察点，不写方向预测，不写买卖建议。
"""


# ── 协调器 ────────────────────────────────────────────────────────────────────

class ComprehensiveAnalysisCoordinator:
    """
    综合分析协调器 MVP。

    不依赖 LangGraph，使用 ThreadPoolExecutor(max_workers=4) 并行调用四个 Agent，
    最后调用 LLM 生成综合摘要。

    Args:
        llm: 实现了 BaseLLMClient.chat() 的 LLM 客户端。
             四个子 Agent 与综合摘要共用同一实例。
    """

    def __init__(self, llm: BaseLLMClient) -> None:
        self._llm         = llm
        self._technical   = TechnicalAnalystAgent(llm)
        self._fundamental = FundamentalAnalystAgent(llm)
        self._peer        = PeerComparisonAnalystAgent(llm)
        self._news        = NewsAnalystAgent(llm)

    # ── 主入口 ────────────────────────────────────────────────────────────────

    def analyze(self, market: str, symbol: str) -> dict:
        """
        生成综合分析报告。

        Args:
            market: "CN" 或 "HK"
            symbol: 股票代码

        Returns:
            {
                "market":   str,
                "symbol":   str,
                "report":   str,   # 综合摘要 Markdown
                "sections": {
                    "technical":       str,  # 完整子报告（或错误说明）
                    "fundamental":     str,
                    "peer_comparison": str,
                    "news":            str,
                },
                "metadata": {
                    "generated_at": str,
                    "agents":       {name: {"status": str, "message": str|None}, ...},
                    "warnings":     [str, ...],
                }
            }

        不会抛出异常；任何 Agent 失败均降级处理。
        """
        market = market.upper()
        log.info("ComprehensiveCoordinator: start [%s/%s]", market, symbol)

        # ── Step 1: 并行调用四个 Agent ─────────────────────────────────────
        sections, statuses = self._run_agents_parallel(market, symbol)

        # ── Step 2: 构建综合 Prompt ──────────────────────────────────────
        stock_identity = f"{market}/{symbol}"
        metadata = _build_metadata(market, sections, statuses)
        if _all_sections_unavailable(sections):
            report = _insufficient_data_report(stock_identity, sections)
            metadata["partial"] = True
            log.info("ComprehensiveCoordinator: all sections unavailable [%s/%s]", market, symbol)
            return {
                "market":   market,
                "symbol":   symbol,
                "report":   report,
                "sections": sections,
                "metadata": metadata,
            }

        synthesis_user = self._build_synthesis_prompt(market, symbol, sections, stock_identity)

        # ── Step 3: 综合 LLM 调用 ────────────────────────────────────────
        log.info("ComprehensiveCoordinator: calling synthesis LLM [%s/%s]", market, symbol)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": synthesis_user},
        ]
        try:
            report = self._llm.chat(messages, temperature=0.3)
        except Exception as exc:
            log.error("ComprehensiveCoordinator: synthesis LLM failed [%s/%s]: %s",
                      market, symbol, exc)
            report = _fallback_report(market, symbol, sections, exc)
        report, validation = _finalize_synthesis_report(
            report, sections, market, symbol, stock_identity
        )

        metadata["partial"] = _is_partial_analysis(sections, statuses)
        metadata["synthesis_validation"] = validation
        log.info("ComprehensiveCoordinator: done [%s/%s]", market, symbol)
        return {
            "market":   market,
            "symbol":   symbol,
            "report":   report,
            "sections": sections,
            "metadata": metadata,
        }

    # ── Async 入口（Phase 1E）────────────────────────────────────────────────
    #
    # 保留旧同步 analyze() 不改，新增 async 版本供 /analysis/comprehensive 路由使用。
    # peer_comparison 调用 PeerComparisonAnalystAgent.analyze_async(db, ...)，
    # 其余三个同步 Agent 通过 asyncio.to_thread 并发执行。

    # ── stock_name 查询 ──────────────────────────────────────────────────────────

    @staticmethod
    async def _fetch_stock_name(
        db: AsyncSession,
        market: str,
        symbol: str,
    ) -> str | None:
        """
        从 stock_master 查询股票中文名称。查询失败不抛异常，返回 None。

        精确匹配规则：
          CN: item["symbol"] == symbol
          HK: 5 位补零格式均视为同一只股票（lstrip("0") 比较）
        """
        try:
            from app.services.industry_classification_service import industry_classification_service
            items = await industry_classification_service.search_stocks(db, market, symbol, limit=3)
            for item in items:
                if market == "HK":
                    if item["symbol"].lstrip("0") == symbol.lstrip("0"):
                        return item["name"] or None
                else:
                    if item["symbol"] == symbol:
                        return item["name"] or None
        except Exception as exc:
            log.warning("_fetch_stock_name failed [%s/%s]: %s", market, symbol, exc)
        return None

    async def analyze_async(
        self,
        db:     AsyncSession,
        market: str,
        symbol: str,
    ) -> dict:
        """
        Async 版综合分析，供 /analysis/comprehensive 路由调用（Phase 1E）。

        peer_comparison 使用 DynamicPeerDiscoveryService（PEER_MAP > dynamic_hot）。
        technical / fundamental / news 仍为同步 Agent，通过 asyncio.to_thread 并发执行。
        """
        market = market.upper()
        log.info("ComprehensiveCoordinator.analyze_async: start [%s/%s]", market, symbol)

        # ── P6-b: 获取股票名称，构造完整标识 ─────────────────────────────────
        stock_name = await self._fetch_stock_name(db, market, symbol)
        if stock_name:
            stock_identity = f"{stock_name}（{market}/{symbol}）"
            log.info("ComprehensiveCoordinator.analyze_async: stock_name='%s'", stock_name)
        else:
            stock_identity = f"{market}/{symbol}"
            log.info("ComprehensiveCoordinator.analyze_async: stock_name not found, using symbol")

        sections, statuses = await self._run_agents_parallel_async(
            db, market, symbol, output_language="zh-CN",
        )

        metadata = _build_metadata(market, sections, statuses)
        if _all_sections_unavailable(sections):
            report = _insufficient_data_report(stock_identity, sections)
            metadata["partial"] = True
            log.info("ComprehensiveCoordinator.analyze_async: all sections unavailable [%s/%s]", market, symbol)
            return {
                "market":     market,
                "symbol":     symbol,
                "stock_name": stock_name or "",
                "report":     report,
                "sections":   sections,
                "metadata":   metadata,
            }

        synthesis_user = self._build_synthesis_prompt(market, symbol, sections, stock_identity)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": synthesis_user},
        ]

        log.info("ComprehensiveCoordinator.analyze_async: calling synthesis LLM [%s/%s]", market, symbol)
        try:
            # LLM.chat 是同步方法，在线程池里运行避免阻塞 event loop
            report = await asyncio.to_thread(self._llm.chat, messages, temperature=0.3)
        except Exception as exc:
            log.error(
                "ComprehensiveCoordinator.analyze_async: synthesis LLM failed [%s/%s]: %s",
                market, symbol, exc,
            )
            report = _fallback_report(market, symbol, sections, exc, stock_identity)
        report, validation = _finalize_synthesis_report(
            report, sections, market, symbol, stock_identity, stock_name=stock_name
        )

        metadata["partial"] = _is_partial_analysis(sections, statuses)
        metadata["synthesis_validation"] = validation
        log.info("ComprehensiveCoordinator.analyze_async: done [%s/%s]", market, symbol)
        return {
            "market":     market,
            "symbol":     symbol,
            "stock_name": stock_name or "",
            "report":     report,
            "sections":   sections,
            "metadata":   metadata,
        }

    async def _run_agents_parallel_async(
        self,
        db:              AsyncSession,
        market:          str,
        symbol:          str,
        output_language: str = "zh-CN",
    ) -> tuple[dict[str, str], dict[str, dict]]:
        """
        asyncio.gather 并发执行四个 Agent。

        - technical / fundamental / news：同步方法 → asyncio.to_thread
        - peer_comparison：async 方法 → 直接 await
        - 每个任务用 asyncio.wait_for(timeout=300) 控制超时
        - 任何单个 Agent 失败/超时不阻塞整体

        Returns:
            (sections, statuses)
        """
        _TIMEOUT = _AGENT_TIMEOUT  # 300s

        task_defs = [
            ("technical",
             asyncio.to_thread(self._technical.analyze, market, symbol, output_language)),
            ("fundamental",
             asyncio.to_thread(self._fundamental.analyze, market, symbol, output_language)),
            ("peer_comparison",
             self._peer.analyze_async(db, market, symbol, output_language)),
            ("news",
             asyncio.to_thread(self._news.analyze, market, symbol, 72, 10, output_language)),
        ]

        wrapped = [
            asyncio.wait_for(coro, timeout=_TIMEOUT)
            for _, coro in task_defs
        ]

        raw_results = await asyncio.gather(*wrapped, return_exceptions=True)

        sections: dict[str, str]   = {}
        statuses: dict[str, dict]  = {}

        for (name, _), result in zip(task_defs, raw_results):
            if isinstance(result, asyncio.TimeoutError):
                log.error(
                    "ComprehensiveCoordinator.analyze_async: section '%s' timeout after %ds",
                    name, _TIMEOUT,
                )
                sections[name] = (
                    f"[{name} 模块超时暂不可用：Agent 执行超过 {_TIMEOUT} 秒，"
                    "本次分析该维度数据缺失。]"
                )
                statuses[name] = {
                    "status":  "timeout",
                    "message": f"Agent timed out after {_TIMEOUT}s",
                }
            elif isinstance(result, Exception):
                log.error(
                    "ComprehensiveCoordinator.analyze_async: section '%s' failed: %s",
                    name, result,
                )
                sections[name] = f"[{name} 模块暂时不可用：{result}]"
                statuses[name] = {"status": "failed", "message": str(result)}
            else:
                sections[name] = result
                statuses[name] = {"status": "success", "message": None}
                log.info(
                    "ComprehensiveCoordinator.analyze_async: section '%s' OK (%d chars)",
                    name, len(result),
                )

        return sections, statuses

    # ── Scoped 分析入口（M4-a）────────────────────────────────────────────────

    async def analyze_scoped(
        self,
        db:              AsyncSession,
        market:          str,
        symbol:          str,
        analysis_scope:  str = "comprehensive",
        output_language: str = "zh-CN",
    ) -> dict:
        """
        按 analysis_scope 条件执行 Agent，供 /analysis/comprehensive-v2 路由调用。

        - 只调度 SCOPE_AGENTS[analysis_scope] 中的 Agent。
        - 未运行的 Agent 在 metadata.agents 中标记为 "skipped"。
        - 单 Agent scope（technical_only/fundamental_only/peer_only/news_only）跳过综合 LLM，
          直接包装为标准 Markdown 报告。
        - technical_fundamental 使用轻量合成 LLM。
        - comprehensive 行为与 analyze_async 完全一致。
        """
        market = market.upper()

        if analysis_scope not in VALID_SCOPES:
            raise ValueError(
                f"analysis_scope '{analysis_scope}' 不支持。"
                f"可选值：{sorted(VALID_SCOPES)}"
            )

        agents_to_run = SCOPE_AGENTS[analysis_scope]
        log.info(
            "ComprehensiveCoordinator.analyze_scoped: start [%s/%s] scope=%s agents=%s",
            market, symbol, analysis_scope, agents_to_run,
        )

        # ── 获取股票名称 ─────────────────────────────────────────────────────
        stock_name = await self._fetch_stock_name(db, market, symbol)
        stock_identity = (
            f"{stock_name}（{market}/{symbol}）" if stock_name
            else f"{market}/{symbol}"
        )

        # ── 只运行需要的 Agent ───────────────────────────────────────────────
        sections, statuses = await self._run_agents_scoped(
            db, market, symbol, agents_to_run, output_language=output_language,
        )

        # ── 补充 skipped 状态 ────────────────────────────────────────────────
        all_agents = ["technical", "fundamental", "peer_comparison", "news"]
        for agent in all_agents:
            if agent not in statuses:
                statuses[agent] = {
                    "status":  "skipped",
                    "message": "该维度未纳入本次分析范围",
                }

        # ── 构建 report ──────────────────────────────────────────────────────
        _single_scopes = {"technical_only", "fundamental_only", "peer_only", "news_only"}

        if analysis_scope in _single_scopes:
            agent_key = agents_to_run[0]
            report = _build_single_agent_report(
                stock_identity, analysis_scope, sections.get(agent_key, ""),
                output_language=output_language,
            )

        elif analysis_scope == "technical_fundamental":
            report = await self._synthesize_tech_fundamental(
                market, stock_identity, sections, output_language=output_language,
            )

        else:
            # comprehensive — full synthesis LLM (same as analyze_async)
            if _all_sections_unavailable(sections):
                report = _insufficient_data_report(stock_identity, sections)
            else:
                synthesis_user = self._build_synthesis_prompt(
                    market, symbol, sections, stock_identity, output_language=output_language,
                )
                messages = [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": synthesis_user},
                ]
                log.info(
                    "ComprehensiveCoordinator.analyze_scoped: calling synthesis LLM [%s/%s]",
                    market, symbol,
                )
                try:
                    report = await asyncio.to_thread(self._llm.chat, messages, temperature=0.3)
                except Exception as exc:
                    log.error(
                        "ComprehensiveCoordinator.analyze_scoped: synthesis LLM failed [%s/%s]: %s",
                        market, symbol, exc,
                    )
                    report = _fallback_report(market, symbol, sections, exc, stock_identity,
                                              output_language=output_language)
            report, validation = _finalize_synthesis_report(
                report, sections, market, symbol, stock_identity, stock_name=stock_name
            )

        metadata = _build_metadata(market, sections, statuses)
        metadata["analysis_scope"]   = analysis_scope
        metadata["workflow_engine"]  = "custom_coordinator"
        metadata["output_language"]  = output_language
        metadata["partial"]          = _is_partial_analysis(sections, statuses)
        if analysis_scope == "comprehensive":
            metadata["synthesis_validation"] = validation

        log.info(
            "ComprehensiveCoordinator.analyze_scoped: done [%s/%s] scope=%s",
            market, symbol, analysis_scope,
        )
        return {
            "market":         market,
            "symbol":         symbol,
            "stock_name":     stock_name or "",
            "report":         report,
            "sections":       sections,
            "metadata":       metadata,
            "analysis_scope": analysis_scope,
        }

    # ── _run_agents_scoped ────────────────────────────────────────────────────

    async def _run_agents_scoped(
        self,
        db:              AsyncSession,
        market:          str,
        symbol:          str,
        agents_to_run:   list[str],
        output_language: str = "zh-CN",
    ) -> tuple[dict[str, str], dict[str, dict]]:
        """
        只启动 agents_to_run 列表中的 Agent，其余不执行。
        返回 (sections, statuses)，key 仅包含实际运行的 Agent。
        """
        _TIMEOUT = _AGENT_TIMEOUT

        def _make_coro(name: str):
            if name == "technical":
                return asyncio.to_thread(
                    self._technical.analyze, market, symbol, output_language)
            if name == "fundamental":
                return asyncio.to_thread(
                    self._fundamental.analyze, market, symbol, output_language)
            if name == "peer_comparison":
                return self._peer.analyze_async(db, market, symbol, output_language)
            if name == "news":
                return asyncio.to_thread(
                    self._news.analyze, market, symbol, 72, 10, output_language)
            raise ValueError(f"Unknown agent: {name}")

        task_defs = [(name, _make_coro(name)) for name in agents_to_run]
        wrapped   = [asyncio.wait_for(coro, timeout=_TIMEOUT) for _, coro in task_defs]
        raw       = await asyncio.gather(*wrapped, return_exceptions=True)

        sections: dict[str, str]  = {}
        statuses: dict[str, dict] = {}

        for (name, _), result in zip(task_defs, raw):
            if isinstance(result, asyncio.TimeoutError):
                log.error(
                    "ComprehensiveCoordinator._run_agents_scoped: '%s' timeout after %ds",
                    name, _TIMEOUT,
                )
                sections[name] = (
                    f"[{name} 模块超时暂不可用：Agent 执行超过 {_TIMEOUT} 秒，"
                    "本次分析该维度数据缺失。]"
                )
                statuses[name] = {
                    "status":  "timeout",
                    "message": f"Agent timed out after {_TIMEOUT}s",
                }
            elif isinstance(result, Exception):
                log.error(
                    "ComprehensiveCoordinator._run_agents_scoped: '%s' failed: %s",
                    name, result,
                )
                sections[name] = f"[{name} 模块暂时不可用：{result}]"
                statuses[name] = {"status": "failed", "message": str(result)}
            else:
                sections[name] = result
                statuses[name] = {"status": "success", "message": None}
                log.info(
                    "ComprehensiveCoordinator._run_agents_scoped: '%s' OK (%d chars)",
                    name, len(result),
                )

        return sections, statuses

    # ── technical_fundamental 轻量合成 ────────────────────────────────────────

    async def _synthesize_tech_fundamental(
        self,
        market:          str,
        stock_identity:  str,
        sections:        dict[str, str],
        output_language: str = "zh-CN",
    ) -> str:
        """
        技术面 + 基本面的轻量合成报告（无需 full synthesis prompt）。
        如果 LLM 调用失败，返回降级报告。
        """
        tech_text = _trunc(sections.get("technical",   ""), "技术面", _SECTION_MAX_CHARS)
        fund_text = _trunc(sections.get("fundamental", ""), "基本面", _SECTION_MAX_CHARS)

        hk_note = (
            "\n注意：港股基本面数据覆盖有限，整合时请明确说明此限制。\n"
            if market == "HK" else ""
        )

        lang_label = OUTPUT_LANGUAGE_LABELS.get(output_language, "简体中文")
        lang_instruction = (
            f"\n【输出语言】请使用 {lang_label} 撰写报告，"
            "除股票名称、代码、专有名词、财务字段名称可保留原文外，其余均应使用该语言。\n"
        ) if output_language != "zh-CN" else ""

        prompt = f"""\
请基于以下技术面与基本面子报告，生成简洁的整合分析摘要报告。{hk_note}
分析对象：{stock_identity}

【子报告 1 — 技术面分析】
{tech_text}

---
【子报告 2 — 基本面分析】
{fund_text}

---
要求：
- 报告 Markdown 标题必须为：# 技术面与基本面分析报告：{stock_identity}
- 核心摘要第一句：本报告分析对象为 {stock_identity}，本次覆盖技术面与基本面分析。
- 禁止编造子报告中未出现的数据，禁止给买卖建议或目标价。
- 缺失字段明确说明不可用，不得推断。
- 末尾包含"风险提示：仅供研究参考，不构成投资建议。"
{lang_instruction}"""
        system = (
            "你是专业股票分析助手，负责整合技术面与基本面子报告，生成简洁的双维度分析摘要。"
            "严禁编造数据，不给投资建议，缺失字段明确说明，不得推断。"
        )
        try:
            return await asyncio.to_thread(
                self._llm.chat,
                [{"role": "system", "content": system},
                 {"role": "user",   "content": prompt}],
                temperature=0.3,
            )
        except Exception as exc:
            log.error(
                "ComprehensiveCoordinator._synthesize_tech_fundamental failed: %s", exc
            )
            return _fallback_report(
                market, "", sections, exc, stock_identity,
                title_override="技术面与基本面分析报告",
                output_language=output_language,
            )

    # ── 并行执行 ──────────────────────────────────────────────────────────────

    def _run_agents_parallel(
        self,
        market:          str,
        symbol:          str,
        output_language: str = "zh-CN",
    ) -> tuple[dict[str, str], dict[str, dict]]:
        """
        用 ThreadPoolExecutor 并行调用四个 Agent。

        Returns:
            (sections, statuses)
            - sections: 各 Agent 完整子报告（或错误说明字符串）
            - statuses: 各 Agent 执行状态 {"status": "success"|"timeout"|"failed", "message": str|None}
        """
        task_map = {
            "technical":       lambda: self._technical.analyze(market, symbol, output_language),
            "fundamental":     lambda: self._fundamental.analyze(market, symbol, output_language),
            "peer_comparison": lambda: self._peer.analyze(market, symbol, output_language),
            "news":            lambda: self._news.analyze(market, symbol, hours_back=72, limit=10, output_language=output_language),
        }

        sections: dict[str, str] = {}
        statuses: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {name: pool.submit(fn) for name, fn in task_map.items()}

            for name, future in futures.items():
                try:
                    sections[name] = future.result(timeout=_AGENT_TIMEOUT)
                    statuses[name] = {"status": "success", "message": None}
                    log.info(
                        "ComprehensiveCoordinator: section '%s' OK (%d chars)",
                        name, len(sections[name]),
                    )
                except FuturesTimeoutError:
                    log.error(
                        "ComprehensiveCoordinator: section '%s' timeout after %ds",
                        name, _AGENT_TIMEOUT,
                    )
                    sections[name] = (
                        f"[{name} 模块超时暂不可用：Agent 执行超过 {_AGENT_TIMEOUT} 秒，"
                        "本次分析该维度数据缺失。]"
                    )
                    statuses[name] = {
                        "status": "timeout",
                        "message": f"Agent timed out after {_AGENT_TIMEOUT}s",
                    }
                except Exception as exc:
                    log.error(
                        "ComprehensiveCoordinator: section '%s' failed: %s",
                        name, exc,
                    )
                    sections[name] = f"[{name} 模块暂时不可用：{exc}]"
                    statuses[name] = {"status": "failed", "message": str(exc)}

        return sections, statuses

    # ── 综合 Prompt 构建 ───────────────────────────────────────────────────────

    @staticmethod
    def _build_synthesis_prompt(
        market: str,
        symbol: str,
        sections: dict[str, str],
        stock_identity: str | None = None,
        output_language: str = "zh-CN",
    ) -> str:
        """
        将四个子报告先压缩为结构化证据摘要，再拼入 Prompt。
        sections 中原始内容不变；综合 LLM 只接收关键事实、数字、风险、限制与时间范围。

        stock_identity: 完整股票标识，如"平安银行（CN/000001）"；
                        None 时 fallback 为 "{market}/{symbol}"。
        output_language: 报告输出语言代码（默认 zh-CN）。
        """
        if stock_identity is None:
            stock_identity = f"{market}/{symbol}"

        summaries = {
            "technical": _build_section_summary(
                "technical", sections.get("technical", ""), _SECTION_MAX_CHARS
            ),
            "fundamental": _build_section_summary(
                "fundamental", sections.get("fundamental", ""), _SECTION_MAX_CHARS
            ),
            "peer_comparison": _build_section_summary(
                "peer_comparison", sections.get("peer_comparison", ""), _SECTION_MAX_CHARS
            ),
            "news": _build_section_summary(
                "news", sections.get("news", ""), _NEWS_SECTION_MAX_CHARS
            ),
        }

        truncated_any = any(summary["truncated"] for summary in summaries.values())
        truncation_note = (
            "\n注意：以下子报告已先压缩为结构化摘要。截断时已优先保留限制、来源、时间范围和关键数字；"
            "不得补充摘要中未出现的数据。\n"
            if truncated_any else ""
        )

        hk_note = (
            "\n⚠️ HK 港股补充约束：\n"
            "- 港股基本面数据源当前覆盖有限，综合报告必须说明这一限制。\n"
            "- 若同行 available 字段为空，不得强行做同行对比结论。\n"
            "- 可提及港股流动性、财报披露质量等风险，但不得编造具体事实。\n"
            "- 若新闻 section 提示 keyword search / 关键词搜索 / 相关性可能较弱，\n"
            "  不得将新闻结论当作确定性事实，必须说明港股新闻相关性需谨慎判断。\n"
            if market == "HK" else ""
        )

        lang_label = OUTPUT_LANGUAGE_LABELS.get(output_language, "简体中文")
        language_instruction = (
            f"\n\n【输出语言】\n"
            f"请使用 {lang_label} 撰写本次分析报告。"
            f"除股票名称、代码、公司专有名词、新闻标题、财务字段名称可保留原文外，"
            f"其余解释、章节标题、摘要、风险提示均应使用 {lang_label}。\n"
        ) if output_language != "zh-CN" else ""

        prompt = f"""\
请基于以下四份子报告，生成综合分析摘要报告。
{truncation_note}{hk_note}
【分析目标】
  股票：{stock_identity}
  市场：{market}
  代码：{symbol}

⚠️ 报告 Markdown 标题必须为：
# 综合分析报告：{stock_identity}

综合结论卡片中【一句话结论】必须以：
本报告分析对象为 {stock_identity}。开头

【事实边界】
- 以下四份"证据摘要"是封闭证据集。只能使用其中出现的事实、数字、公司、同行、事件、来源和限制。
- 不得新增任何数字；不得重新计算指标；不得把不同时间范围的数据放在同一句直接比较。
- 子报告缺失或状态为 unavailable/partial 时，对应章节必须写"本次无可用数据"或明确 partial。
- 输出不得包含 chain of thought、工具参数、traceback、secret、绝对路径、买卖指令或确定涨跌预测。

---
【子报告 1 — 技术面分析证据摘要】
{summaries["technical"]["text"]}

---
【子报告 2 — 基本面分析证据摘要】
{summaries["fundamental"]["text"]}

---
【子报告 3 — 同行对比分析证据摘要】
{summaries["peer_comparison"]["text"]}

---
【子报告 4 — 新闻面分析证据摘要】
{summaries["news"]["text"]}

---
请严格按照系统提示规定的 Markdown 报告结构输出，标题名称不得更改，不得新增或删除章节。\
综合报告只整合以上可见内容，不得推断或补充未出现的数据。\
新闻面要点只能引用子报告 4 中已有的结论，不得编造新闻。\
{language_instruction}"""
        return _truncate_prompt(prompt, _SYNTHESIS_PROMPT_MAX_CHARS)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

_SECTION_LABELS: dict[str, str] = {
    "technical": "技术面",
    "fundamental": "基本面",
    "peer_comparison": "同行对比",
    "news": "新闻面",
}

_KEY_FACT_PATTERNS = (
    "observed_facts", "analysis", "limitations", "watch_items",
    "观察", "事实", "结论", "摘要", "核心", "风险", "限制", "局限", "缺失",
    "不可用", "数据不足", "时间", "报告期", "来源", "source", "period",
    "date", "新闻", "事件", "同行", "样本", "PEER_MAP", "关键词搜索",
)

_DROP_LINE_PATTERNS = (
    "仅供研究参考", "不构成投资建议", "投资者需自行判断", "风险提示：",
    "免责声明", "```", "---",
)

_LIMITATION_PATTERNS = (
    "限制", "局限", "缺失", "不可用", "数据不足", "暂不评价", "未返回",
    "未能覆盖", "样本", "时间窗口", "报告期", "相关性", "截断", "partial",
    "超时", "暂时不可用", "coverage", "missing", "unavailable", "limited",
)

_RISK_PATTERNS = ("风险", "压力", "不确定", "波动", "下滑", "负面", "偏弱")
_NUMERIC_CONTEXT_PATTERNS = (
    "元", "亿元", "%", "pct", "倍", "日", "年", "月", "报告期", "收盘", "成交",
    "收入", "利润", "现金流", "ROE", "PE", "PB", "MA", "均线", "涨跌", "样本",
    "小时", "交易日", "同比", "环比", "margin", "revenue", "profit",
)
_SOURCE_PATTERN = re.compile(r"https?://[^\s)）]+")
_NUMBER_PATTERN = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:[.,]\d+)*(?:\.\d+)?%?")
_ABS_PATH_PATTERN = re.compile(r"(/Users/|/private/|/var/|/tmp/)[^\s)）]+")
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^'\"\s)）]+"
)
_TRACEBACK_PATTERN = re.compile(r"Traceback \(most recent call last\):[\s\S]*")

_FORBIDDEN_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("强烈买入", "不提供买卖建议"),
    ("强烈卖出", "不提供买卖建议"),
    ("买入建议", "研究观察"),
    ("卖出建议", "研究观察"),
    ("持有建议", "研究观察"),
    ("满仓", "仓位建议已省略"),
    ("梭哈", "仓位建议已省略"),
    ("保证收益", "收益不确定"),
    ("必涨", "走势不确定"),
    ("必跌", "走势不确定"),
    ("稳赚", "收益不确定"),
    ("抄底", "操作表述已省略"),
    ("逃顶", "操作表述已省略"),
    ("清仓", "操作表述已省略"),
    ("加仓", "操作表述已省略"),
    ("减仓推荐", "操作表述已省略"),
    ("确定涨幅", "确定性预测已省略"),
    ("明天一定上涨", "短期走势不确定"),
    ("明天一定下跌", "短期走势不确定"),
    ("chain of thought", "内部推理已省略"),
    ("内部思考过程", "内部推理已省略"),
    ("工具参数", "工具细节已省略"),
)


def _is_unavailable_text(text: str | None) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if stripped.startswith("[") and any(kw in stripped for kw in ("暂时不可用", "超时", "数据缺失")):
        return True
    unavailable_markers = (
        "暂无可用数据", "本次无可用数据", "所有工具数据为空",
        "items 为空", "暂无相关新闻数据", "暂无新闻数据",
    )
    return any(marker in stripped for marker in unavailable_markers) and len(stripped) < 260


def _all_sections_unavailable(sections: dict[str, str]) -> bool:
    expected = ("technical", "fundamental", "peer_comparison", "news")
    return all(_is_unavailable_text(sections.get(key, "")) for key in expected)


def _is_partial_analysis(sections: dict[str, str], statuses: dict[str, dict]) -> bool:
    if any(s.get("status") in {"failed", "timeout"} for s in statuses.values()):
        return True
    expected = ("technical", "fundamental", "peer_comparison", "news")
    return any(_is_unavailable_text(sections.get(key, "")) for key in expected)


def _clean_report_lines(text: str) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(drop in line for drop in _DROP_LINE_PATTERNS):
            continue
        compact = re.sub(r"\s+", " ", line)
        if compact in seen:
            continue
        seen.add(compact)
        lines.append(line)
    return lines


def _line_has_key_evidence(line: str) -> bool:
    if _NUMBER_PATTERN.search(line) and any(
        pattern.lower() in line.lower() for pattern in _NUMERIC_CONTEXT_PATTERNS
    ):
        return True
    return any(pattern.lower() in line.lower() for pattern in _KEY_FACT_PATTERNS)


def _prioritized_lines(lines: list[str]) -> list[str]:
    limitation_lines = [
        line for line in lines
        if any(pattern.lower() in line.lower() for pattern in _LIMITATION_PATTERNS)
    ]
    numeric_or_source_lines = [
        line for line in lines
        if (_NUMBER_PATTERN.search(line) or _SOURCE_PATTERN.search(line))
        and (
            _SOURCE_PATTERN.search(line)
            or any(pattern.lower() in line.lower() for pattern in _NUMERIC_CONTEXT_PATTERNS)
        )
        and line not in limitation_lines
    ]
    key_lines = [
        line for line in lines
        if _line_has_key_evidence(line)
        and line not in limitation_lines
        and line not in numeric_or_source_lines
    ]
    fallback_lines = [
        line for line in lines
        if line not in limitation_lines
        and line not in numeric_or_source_lines
        and line not in key_lines
    ]
    return limitation_lines + numeric_or_source_lines + key_lines + fallback_lines[:8]


def _fit_lines_without_splitting_units(lines: list[str], max_chars: int) -> tuple[str, bool]:
    output: list[str] = []
    total = 0
    truncated = False
    for line in lines:
        addition = len(line) + 1
        if total + addition > max_chars:
            truncated = True
            continue
        output.append(line)
        total += addition
    return "\n".join(output), truncated


def _build_section_summary(section_key: str, text: str, max_chars: int) -> dict[str, object]:
    label = _SECTION_LABELS.get(section_key, section_key)
    if _is_unavailable_text(text):
        return {
            "text": f"- 状态：unavailable\n- 说明：{(text or '本次无可用数据').strip()}",
            "truncated": False,
        }

    lines = _clean_report_lines(text)
    selected = _prioritized_lines(lines)
    fitted, truncated = _fit_lines_without_splitting_units(selected, max_chars)
    if not fitted:
        fitted = "本次无可用数据"
    if truncated:
        fitted += f"\n- 截断提示：{label}子报告较长，摘要已优先保留限制、来源、时间范围和关键数字。"
    return {"text": fitted, "truncated": truncated or len("\n".join(lines)) > max_chars}


def _truncate_prompt(prompt: str, max_chars: int) -> str:
    if len(prompt) <= max_chars:
        return prompt
    marker = "\n【全局截断提示】综合 prompt 已达到长度上限；各维度限制、来源、时间范围和关键数字已优先保留。\n"
    return prompt[: max_chars - len(marker)] + marker


_SYNTHESIS_HEADINGS: tuple[str, ...] = (
    "## 综合结论",
    "## 核心事实卡片",
    "## 基本面与财务",
    "## 市场与技术",
    "## 新闻与事件",
    "## 同行位置",
    "## 关键联动",
    "## 主要风险",
    "## 数据限制",
    "## 后续观察",
)


def _extract_numbers(text: str) -> set[str]:
    return {match.group(0) for match in _NUMBER_PATTERN.finditer(text or "")}


def _normalize_number_token(token: str) -> str:
    return token.replace(",", "")


def _allowed_numbers(sections: dict[str, str], symbol: str) -> set[str]:
    allowed: set[str] = {symbol, symbol.lstrip("0"), "0"}
    for text in sections.values():
        for number in _extract_numbers(text):
            allowed.add(number)
            allowed.add(_normalize_number_token(number))
    return {number for number in allowed if number}


def _section_lines(section_key: str, sections: dict[str, str], *, include_limits: bool = False) -> list[str]:
    text = sections.get(section_key, "")
    if _is_unavailable_text(text):
        return ["本次无可用数据"]
    lines = _prioritized_lines(_clean_report_lines(text))
    if include_limits:
        limited = [
            line for line in lines
            if any(pattern.lower() in line.lower() for pattern in _LIMITATION_PATTERNS)
        ]
        return limited[:6] or ["未发现额外数据限制"]
    selected: list[str] = []
    for line in lines:
        if any(pattern.lower() in line.lower() for pattern in _LIMITATION_PATTERNS):
            continue
        selected.append(line)
        if len(selected) >= 3:
            break
    return selected or ["本次无可用数据"]


def _risk_lines(sections: dict[str, str]) -> list[str]:
    risks: list[str] = []
    for text in sections.values():
        for line in _clean_report_lines(text):
            if any(pattern in line for pattern in _RISK_PATTERNS):
                risks.append(line)
            if len(risks) >= 5:
                return risks
    return risks or ["各维度风险需结合后续数据继续观察"]


def _limitation_lines(sections: dict[str, str]) -> list[str]:
    limits: list[str] = []
    for text in sections.values():
        for line in _clean_report_lines(text):
            if any(pattern.lower() in line.lower() for pattern in _LIMITATION_PATTERNS):
                limits.append(line)
    return _dedupe_lines(limits)[:10] or ["本次分析受限于子报告可用字段和时间范围"]


def _fact_card_lines(sections: dict[str, str]) -> list[str]:
    facts: list[str] = []
    for key in ("fundamental", "technical", "news", "peer_comparison"):
        if _is_unavailable_text(sections.get(key, "")):
            continue
        for line in _section_lines(key, sections):
            if line == "本次无可用数据":
                continue
            facts.append(line)
            if len(facts) >= 5:
                return facts
    return facts or ["本次可用子报告不足，核心事实卡片暂无法展开"]


def _extract_dates(text: str) -> set[str]:
    return set(re.findall(r"\d{4}(?:[-年]\d{1,2}(?:[-月]\d{1,2}日?)?)?", text or ""))


def _detect_conflicts(sections: dict[str, str]) -> list[str]:
    conflicts: list[str] = []
    fundamental = sections.get("fundamental", "")
    technical = sections.get("technical", "")
    news = sections.get("news", "")
    peer = sections.get("peer_comparison", "")

    if any(kw in fundamental for kw in ("稳定", "改善", "增长", "较好")) and any(
        kw in news for kw in ("负面", "处罚", "监管", "下滑", "风险")
    ):
        conflicts.append("基本面与新闻信号分属不同维度，财务数据稳定不覆盖新闻负面事件。")
    if any(kw in fundamental for kw in ("改善", "增长", "修复")) and any(
        kw in technical for kw in ("偏弱", "下行", "承压", "走弱")
    ):
        conflicts.append("中长期与短期信号不一致：基本面改善与技术趋势偏弱并存。")
    if any(kw in fundamental for kw in ("增长", "提升", "改善")) and any(
        kw in peer for kw in ("低于同行", "低于样本", "落后", "不及同行")
    ):
        conflicts.append("自身增长但低于同行样本，不应直接写为表现优秀。")

    date_groups = [
        _extract_dates(text) for text in (fundamental, technical, news, peer)
        if text and not _is_unavailable_text(text)
    ]
    unique_dates = set().union(*date_groups) if date_groups else set()
    if len(unique_dates) > 1:
        sample = "、".join(sorted(unique_dates)[:4])
        conflicts.append(f"各子报告时间范围不完全一致（{sample}），不做同周期直接比较。")
    return conflicts or ["未发现需要强行统一的跨维度冲突；后续仍需按维度分别观察。"]


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        compact = re.sub(r"\s+", " ", line).strip()
        if not compact or compact in seen:
            continue
        seen.add(compact)
        deduped.append(line.strip())
    return deduped


def _bulletize(lines: list[str], limit: int | None = None) -> str:
    selected = _dedupe_lines(lines)
    if limit is not None:
        selected = selected[:limit]
    return "\n".join(f"- {line}" for line in selected) if selected else "- 本次无可用数据"


def _coerce_synthesis_shape(
    report: str,
    sections: dict[str, str],
    stock_identity: str,
) -> tuple[str, bool]:
    required_title = f"# 综合分析报告：{stock_identity}"
    has_required_shape = report.strip().startswith(required_title) and all(
        heading in report for heading in _SYNTHESIS_HEADINGS
    )
    if has_required_shape:
        return report, False

    conclusion_line = (
        f"本报告分析对象为 {stock_identity}。本次综合分析仅基于四个子报告中的可见事实整理，"
        "若某维度缺失则不补写。"
    )
    shaped = f"""\
{required_title}

## 综合结论
{conclusion_line}

## 核心事实卡片
{_bulletize(_fact_card_lines(sections), 5)}

## 基本面与财务
{_bulletize(_section_lines("fundamental", sections), 3)}

## 市场与技术
{_bulletize(_section_lines("technical", sections), 3)}

## 新闻与事件
{_bulletize(_section_lines("news", sections), 3)}

## 同行位置
{_bulletize(_section_lines("peer_comparison", sections), 3)}

## 关键联动
{_bulletize(_detect_conflicts(sections), 4)}

## 主要风险
{_bulletize(_risk_lines(sections), 5)}

## 数据限制
{_bulletize(_limitation_lines(sections), 10)}

## 后续观察
- 继续观察后续报告期、行情数据、新闻事件和同行样本变化。
- 若任一维度后续补齐数据，应以补齐后的子报告为准重新综合。
"""
    return shaped, True


def _remove_duplicate_paragraphs(report: str) -> tuple[str, int]:
    blocks = re.split(r"\n{2,}", report.strip())
    seen: set[str] = set()
    output: list[str] = []
    duplicates = 0
    for block in blocks:
        compact = re.sub(r"\s+", " ", block).strip()
        if compact in seen and not compact.startswith("#"):
            duplicates += 1
            continue
        seen.add(compact)
        output.append(block)
    return "\n\n".join(output) + "\n", duplicates


def _sanitize_forbidden_content(report: str) -> tuple[str, int]:
    count = 0
    sanitized = report
    for forbidden, replacement in _FORBIDDEN_REPLACEMENTS:
        if forbidden in sanitized:
            count += sanitized.count(forbidden)
            sanitized = sanitized.replace(forbidden, replacement)
    before = sanitized
    sanitized = _TRACEBACK_PATTERN.sub("执行异常细节已省略。", sanitized)
    sanitized = _SECRET_PATTERN.sub("secret 已省略", sanitized)
    sanitized = _ABS_PATH_PATTERN.sub("本地路径已省略", sanitized)
    if sanitized != before:
        count += 1
    return sanitized, count


def _remove_out_of_scope_sources(report: str, sections: dict[str, str]) -> tuple[str, int]:
    allowed_sources: set[str] = set()
    for text in sections.values():
        allowed_sources.update(match.group(0) for match in _SOURCE_PATTERN.finditer(text or ""))
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        url = match.group(0)
        if url in allowed_sources:
            return url
        removed += 1
        return "来源未提供"

    return _SOURCE_PATTERN.sub(replace, report), removed


def _remove_unsupported_numbers(
    report: str,
    sections: dict[str, str],
    symbol: str,
) -> tuple[str, int]:
    allowed = _allowed_numbers(sections, symbol)
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        token = match.group(0)
        normalized = _normalize_number_token(token)
        if token in allowed or normalized in allowed:
            return token
        removed += 1
        return "未提供数字"

    return _NUMBER_PATTERN.sub(replace, report), removed


def _ensure_identity(
    report: str,
    market: str,
    symbol: str,
    stock_identity: str,
    stock_name: str | None = None,
) -> tuple[str, int]:
    required_title = f"# 综合分析报告：{stock_identity}"
    changed = 0
    lines = report.splitlines()
    if not lines or not lines[0].startswith("# 综合分析报告："):
        lines.insert(0, required_title)
        changed += 1
    elif lines[0] != required_title:
        lines[0] = required_title
        changed += 1

    output = "\n".join(lines)
    if f"{market}/{symbol}" not in output:
        output = output.replace(
            "## 综合结论",
            f"## 综合结论\n本报告分析对象为 {stock_identity}。",
            1,
        )
        changed += 1
    if stock_name and stock_name not in output:
        output = output.replace(
            "## 综合结论",
            f"## 综合结论\n本报告分析对象为 {stock_identity}。",
            1,
        )
        changed += 1
    return output, changed


def _ensure_limitations(report: str, sections: dict[str, str]) -> tuple[str, int]:
    missing: list[str] = []
    for line in _limitation_lines(sections):
        if line != "本次分析受限于子报告可用字段和时间范围" and line not in report:
            missing.append(line)
    if not missing:
        return report, 0
    insertion = "\n".join(f"- {line}" for line in missing[:6])
    if "## 数据限制" not in report:
        return report + f"\n\n## 数据限制\n{insertion}\n", len(missing)
    return report.replace("## 数据限制", f"## 数据限制\n{insertion}", 1), len(missing)


def _finalize_synthesis_report(
    report: str,
    sections: dict[str, str],
    market: str,
    symbol: str,
    stock_identity: str,
    stock_name: str | None = None,
) -> tuple[str, dict[str, int | bool]]:
    shaped, shape_changed = _coerce_synthesis_shape(report or "", sections, stock_identity)
    shaped, identity_changes = _ensure_identity(shaped, market, symbol, stock_identity, stock_name)
    shaped, source_removals = _remove_out_of_scope_sources(shaped, sections)
    shaped, unsupported_numbers = _remove_unsupported_numbers(shaped, sections, symbol)
    shaped, safety_replacements = _sanitize_forbidden_content(shaped)
    shaped, missing_limits = _ensure_limitations(shaped, sections)
    shaped, duplicate_count = _remove_duplicate_paragraphs(shaped)

    validation = {
        "shape_coerced": shape_changed,
        "identity_corrections": identity_changes,
        "unsupported_number_count": unsupported_numbers,
        "out_of_scope_source_count": source_removals,
        "safety_violation_count": safety_replacements,
        "missing_limitation_count": missing_limits,
        "duplicate_section_count": duplicate_count,
    }
    return shaped, validation


def _insufficient_data_report(stock_identity: str, sections: dict[str, str]) -> str:
    statuses = [
        f"{_SECTION_LABELS.get(name, name)}：{(text or '本次无可用数据').strip()}"
        for name, text in sections.items()
    ]
    return f"""\
# 综合分析报告：{stock_identity}

## 综合结论
本报告分析对象为 {stock_identity}。本次四个子报告均无可用数据，无法生成综合分析正文。

## 核心事实卡片
- 本次无可用数据

## 基本面与财务
本次无可用数据

## 市场与技术
本次无可用数据

## 新闻与事件
本次无可用数据

## 同行位置
本次无可用数据

## 关键联动
本次无可用数据

## 主要风险
- 数据不足导致无法识别具体风险。

## 数据限制
{_bulletize(statuses, 10)}

## 后续观察
- 待基础行情、财务、新闻或同行数据恢复后重新生成综合分析。
"""

def _trunc(text: str, label: str, max_chars: int) -> str:
    """截断子报告，追加截断提示（供非静态方法使用）。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n...[{label} 报告已截断，以上为前 {max_chars} 字符]"


# 单 Agent 报告包装文本 — 按输出语言本地化
_SINGLE_AGENT_STRINGS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "h_summary":  "一、摘要",
        "h_subject":  "二、分析对象",
        "h_core":     "三、核心观察",
        "h_limits":   "四、数据边界",
        "h_risk":     "风险提示",
        "t_summary":  "本报告分析对象为 {identity}。本次仅覆盖{dim}，当前内容基于可用数据整理。以下内容用于帮助理解该维度下的主要观察点，仍需结合其他信息综合判断。",
        "t_subject":  "本报告分析对象为 {identity}，本次仅覆盖{desc}。",
        "t_limits":   "本报告仅覆盖上述单一维度，不构成完整综合分析。如需多维度研究，建议使用综合分析模式，结合技术面、基本面、同行对比与新闻面综合判断。",
        "t_risk":     "仅供研究参考，不构成投资建议。市场存在不确定性，投资者需自行判断并承担投资风险。",
    },
    "en-US": {
        "h_summary":  "I. Summary",
        "h_subject":  "II. Subject",
        "h_core":     "III. Key Observations",
        "h_limits":   "IV. Data Limitations",
        "h_risk":     "Risk Disclaimer",
        "t_summary":  "This report analyzes {identity}. Only {dim} is covered. Content is based on available data and should be considered alongside other information.",
        "t_subject":  "This report covers {identity}, limited to {desc}.",
        "t_limits":   "This report covers only the above dimension and does not constitute a comprehensive analysis. For multi-dimensional research, use comprehensive analysis mode.",
        "t_risk":     "For research reference only. Not investment advice. Markets are uncertain; investors should exercise independent judgment.",
    },
    "zh-TW": {
        "h_summary":  "一、摘要",
        "h_subject":  "二、分析對象",
        "h_core":     "三、核心觀察",
        "h_limits":   "四、數據邊界",
        "h_risk":     "風險提示",
        "t_summary":  "本報告分析對象為 {identity}。本次僅覆蓋{dim}，當前內容基於可用數據整理。以下內容用於幫助理解該維度下的主要觀察點，仍需結合其他資訊綜合判斷。",
        "t_subject":  "本報告分析對象為 {identity}，本次僅覆蓋{desc}。",
        "t_limits":   "本報告僅覆蓋上述單一維度，不構成完整綜合分析。如需多維度研究，建議使用綜合分析模式。",
        "t_risk":     "僅供研究參考，不構成投資建議。市場存在不確定性，投資者需自行判斷並承擔投資風險。",
    },
    "ja-JP": {
        "h_summary":  "I. 要約",
        "h_subject":  "II. 分析対象",
        "h_core":     "III. 主要観察",
        "h_limits":   "IV. データの限界",
        "h_risk":     "リスク免責事項",
        "t_summary":  "本レポートの分析対象は {identity} です。本回は{dim}のみを対象とし、利用可能なデータに基づいています。",
        "t_subject":  "本レポートは {identity} を対象とし、{desc}に限定されます。",
        "t_limits":   "本レポートは上記の単一次元のみをカバーし、総合的な分析ではありません。",
        "t_risk":     "研究参照のみを目的としており、投資アドバイスではありません。",
    },
    "ko-KR": {
        "h_summary":  "I. 요약",
        "h_subject":  "II. 분석 대상",
        "h_core":     "III. 핵심 관찰",
        "h_limits":   "IV. 데이터 한계",
        "h_risk":     "위험 고지",
        "t_summary":  "이 보고서의 분석 대상은 {identity}입니다. 이번에는 {dim}만 다루며, 가용 데이터를 기반으로 합니다.",
        "t_subject":  "이 보고서는 {identity}를 다루며, {desc}로 제한됩니다.",
        "t_limits":   "이 보고서는 위의 단일 차원만 다루며 종합 분석이 아닙니다.",
        "t_risk":     "연구 참조 목적으로만 제공됩니다. 투자 조언이 아닙니다.",
    },
    "es-ES": {
        "h_summary":  "I. Resumen",
        "h_subject":  "II. Objeto de Análisis",
        "h_core":     "III. Observaciones Clave",
        "h_limits":   "IV. Limitaciones de Datos",
        "h_risk":     "Aviso de Riesgo",
        "t_summary":  "Este informe analiza {identity}. Solo se cubre {dim}, basado en datos disponibles.",
        "t_subject":  "Este informe cubre {identity}, limitado a {desc}.",
        "t_limits":   "Este informe cubre solo la dimensión anterior y no constituye un análisis completo.",
        "t_risk":     "Solo para referencia de investigación. No es asesoramiento de inversión.",
    },
}


def _build_single_agent_report(
    stock_identity: str,
    analysis_scope: str,
    agent_content:  str,
    output_language: str = "zh-CN",
) -> str:
    """
    将单 Agent 子报告包装为标准 Markdown 报告（不调用综合 LLM）。
    用于 technical_only / fundamental_only / peer_only / news_only / technical_fundamental。
    output_language 控制包装文本的语言。
    """
    title   = _SCOPE_REPORT_TITLES.get(analysis_scope, "分析报告")
    desc    = _SCOPE_DESCRIPTIONS.get(analysis_scope, "单维度分析")
    dim     = _SCOPE_SUMMARY_DIMS.get(analysis_scope, desc)
    # fallback to zh-CN strings if language not mapped
    strs = _SINGLE_AGENT_STRINGS.get(output_language, _SINGLE_AGENT_STRINGS["zh-CN"])
    return f"""\
# {title}：{stock_identity}

## {strs['h_summary']}

{strs['t_summary'].format(identity=stock_identity, dim=dim)}

## {strs['h_subject']}

{strs['t_subject'].format(identity=stock_identity, desc=desc)}

## {strs['h_core']}

{agent_content}

## {strs['h_limits']}

{strs['t_limits']}

## {strs['h_risk']}

{strs['t_risk']}
"""


# ── Metadata 构建 ────────────────────────────────────────────────────────────

def _build_metadata(
    market: str,
    sections: dict[str, str],
    statuses: dict[str, dict],
) -> dict:
    """
    构建综合分析 metadata。

    Args:
        market:   "CN" 或 "HK"
        sections: 各 Agent 子报告文本
        statuses: 各 Agent 执行状态

    Returns:
        {
            "generated_at": ISO 8601 UTC 时间字符串,
            "agents":       {name: {"status": str, "message": str|None}, ...},
            "warnings":     [str, ...],
        }
    """
    warnings: list[str] = []

    # HK 数据覆盖受限
    if market == "HK":
        warnings.append("HK fundamentals coverage is limited.")

    # 估值字段缺失
    all_text = " ".join(sections.values())
    if "PE/PB 缺失" in all_text or "估值数据缺失" in all_text:
        warnings.append("valuation fields are missing.")

    # 同行对比不可用
    peer_text = sections.get("peer_comparison", "")
    if "暂无同行配置" in peer_text or "未配置同行" in peer_text:
        warnings.append("peer comparison is unavailable.")

    # 新闻数据不可用
    news_text = sections.get("news", "")
    if any(kw in news_text for kw in ("暂无相关新闻数据", "暂无新闻", "items 为空")):
        warnings.append("news data is unavailable.")

    # 新闻相关性受限（仅 HK keyword search）
    # 必须同时满足 market=="HK"，避免 CN 报告中出现"无keyword search提示"等字样误触发
    if market == "HK" and any(kw in news_text for kw in (
        "港股新闻通过关键词搜索", "HK news is fetched via",
        "keyword search", "关键词搜索", "相关性可能较弱",
    )):
        warnings.append("news relevance may be limited.")

    # Agent 失败 / 超时
    for name, s in statuses.items():
        if s["status"] in ("failed", "timeout"):
            warnings.append(f"{name} agent {s['status']}.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agents":       statuses,
        "warnings":     warnings,
    }


# ── 降级报告文本（LLM 调用失败时按语言本地化）────────────────────────────────
_FALLBACK_STRINGS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "title":      "综合分析报告",
        "h_summary":  "一、综合结论卡片",
        "t_summary":  "- **综合判断**：数据不足\n- **一句话结论**：本报告分析对象为 {identity}。综合摘要生成失败（LLM 调用异常：{exc}），以下为各子模块状态。",
        "h_sources":  "二、四面结论汇总",
        "t_sources":  (
            "- 技术面：akshare 历史行情数据\n"
            "- 基本面：akshare/Sina/yfinance 财务字段（字段覆盖视数据源返回而定）\n"
            "- 同行对比：手动配置 PEER_MAP 样本\n"
            "- 新闻面：AkShare 新闻接口（时间窗口内数据）\n"
            "- 注：综合 LLM 模块当前不可用，具体字段覆盖详见各子报告"
        ),
        "h_multi":    "子模块执行状态",
        "h_limits":   "三、主要数据局限",
        "t_limits":   "综合摘要模块暂时不可用，请参阅 sections 中各子报告的完整内容。",
        "h_followup": "四、后续观察清单",
        "t_followup": "暂无（等综合 LLM 恢复后重试）。",
        "h_risk":     "风险提示",
        "t_risk":     "仅供研究参考，不构成投资建议。技术面、基本面、同行对比与新闻面分析均存在局限性，市场存在不确定性，投资者需自行判断并承担投资风险。",
    },
    "en-US": {
        "title":      "Comprehensive Analysis Report",
        "h_summary":  "I. Synthesis Conclusion Card",
        "t_summary":  "- **Overall Judgment**: Insufficient Data\n- **One-line Conclusion**: This report covers {identity}. Synthesis generation failed (LLM error: {exc}). Below is the status of each sub-module.",
        "h_sources":  "II. Four-Dimension Summary",
        "t_sources":  (
            "- Technical: AkShare historical quotes\n"
            "- Fundamental: AkShare/Sina/yfinance financial fields (coverage depends on data source)\n"
            "- Peer comparison: manually configured PEER_MAP samples\n"
            "- News: AkShare news API (within time window)\n"
            "- Note: Synthesis LLM module is currently unavailable; see individual sections."
        ),
        "h_multi":    "Sub-module Execution Status",
        "h_limits":   "III. Data Limitations",
        "t_limits":   "Synthesis module is temporarily unavailable. Please refer to individual sub-reports.",
        "h_followup": "IV. Follow-up Checklist",
        "t_followup": "None available (retry after synthesis LLM recovers).",
        "h_risk":     "Risk Disclaimer",
        "t_risk":     "For research reference only. Not investment advice. All analysis dimensions have limitations. Markets are uncertain; investors should exercise independent judgment.",
    },
    "zh-TW": {
        "title":      "綜合分析報告",
        "h_summary":  "一、綜合結論卡片",
        "t_summary":  "- **綜合判斷**：數據不足\n- **一句話結論**：本報告分析對象為 {identity}。綜合摘要生成失敗（LLM 調用異常：{exc}），以下為各子模塊狀態。",
        "h_sources":  "二、四面結論彙總",
        "t_sources":  (
            "- 技術面：AkShare 歷史行情數據\n"
            "- 基本面：AkShare/Sina/yfinance 財務字段\n"
            "- 同行對比：手動配置 PEER_MAP 樣本\n"
            "- 新聞面：AkShare 新聞接口\n"
            "- 注：綜合 LLM 模塊當前不可用"
        ),
        "h_multi":    "子模塊執行狀態",
        "h_limits":   "三、主要數據局限",
        "t_limits":   "綜合摘要模塊暫時不可用，請參閱各子報告完整內容。",
        "h_followup": "四、後續觀察清單",
        "t_followup": "暫無（等綜合 LLM 恢復後重試）。",
        "h_risk":     "風險提示",
        "t_risk":     "僅供研究參考，不構成投資建議。市場存在不確定性，投資者需自行判斷並承擔投資風險。",
    },
    "ja-JP": {
        "title":      "総合分析レポート",
        "h_summary":  "I. 総合結論カード",
        "t_summary":  "- **総合判断**: データ不足\n- **一言結論**: 本レポートは {identity} を分析対象とします。総合要約生成に失敗しました（LLMエラー：{exc}）。各サブモジュールの状況は以下の通りです。",
        "h_sources":  "II. 四次元結論サマリー",
        "t_sources":  (
            "- テクニカル：AkShare 歴史データ\n"
            "- ファンダメンタル：AkShare/Sina/yfinance 財務データ\n"
            "- 同業比較：手動設定 PEER_MAP\n"
            "- ニュース：AkShare ニュース API\n"
            "- 注：総合 LLM モジュールは現在利用不可"
        ),
        "h_multi":    "サブモジュール実行状況",
        "h_limits":   "III. データ制限",
        "t_limits":   "総合要約モジュールは一時的に利用できません。各サブレポートを参照してください。",
        "h_followup": "IV. フォローアップチェックリスト",
        "t_followup": "なし（総合 LLM 回復後に再試行）。",
        "h_risk":     "リスク免責事項",
        "t_risk":     "研究参照のみを目的としており、投資アドバイスではありません。",
    },
    "ko-KR": {
        "title":      "종합 분석 보고서",
        "h_summary":  "I. 종합 결론 카드",
        "t_summary":  "- **종합 판단**: 데이터 부족\n- **한 줄 결론**: 이 보고서의 분석 대상은 {identity}입니다. 종합 요약 생성에 실패했습니다（LLM 오류：{exc}）。각 하위 모듈 상태는 아래와 같습니다.",
        "h_sources":  "II. 4차원 결론 요약",
        "t_sources":  (
            "- 기술: AkShare 역사 데이터\n"
            "- 기본: AkShare/Sina/yfinance 재무 데이터\n"
            "- 동종 비교: 수동 구성 PEER_MAP\n"
            "- 뉴스: AkShare 뉴스 API\n"
            "- 참고: 종합 LLM 모듈 현재 이용 불가"
        ),
        "h_multi":    "하위 모듈 실행 상태",
        "h_limits":   "III. 데이터 제한",
        "t_limits":   "종합 요약 모듈을 임시로 사용할 수 없습니다. 각 하위 보고서를 참조하세요.",
        "h_followup": "IV. 후속 체크리스트",
        "t_followup": "없음 (LLM 복구 후 재시도).",
        "h_risk":     "위험 고지",
        "t_risk":     "연구 참조 목적으로만 제공됩니다. 투자 조언이 아닙니다.",
    },
    "es-ES": {
        "title":      "Informe de Análisis Integral",
        "h_summary":  "I. Tarjeta de Conclusión Integral",
        "t_summary":  "- **Juicio General**: Datos Insuficientes\n- **Conclusión en Una Línea**: Este informe analiza {identity}. La generación del resumen falló (error LLM: {exc}). Estado de cada submódulo:",
        "h_sources":  "II. Resumen de Cuatro Dimensiones",
        "t_sources":  (
            "- Técnico: datos históricos de AkShare\n"
            "- Fundamental: campos financieros de AkShare/Sina/yfinance\n"
            "- Comparación: muestras PEER_MAP manuales\n"
            "- Noticias: API de noticias AkShare\n"
            "- Nota: módulo LLM de síntesis no disponible"
        ),
        "h_multi":    "Estado de los Submódulos",
        "h_limits":   "III. Limitaciones de Datos",
        "t_limits":   "El módulo de resumen no está disponible. Consulte los subinformes individuales.",
        "h_followup": "IV. Lista de Seguimiento",
        "t_followup": "Ninguno (reintente tras recuperar el módulo LLM).",
        "h_risk":     "Aviso de Riesgo",
        "t_risk":     "Solo para referencia de investigación. No es asesoramiento de inversión.",
    },
}


def _fallback_report(
    market:          str,
    symbol:          str,
    sections:        dict[str, str],
    exc:             Exception,
    stock_identity:  str | None = None,
    title_override:  str | None = None,
    output_language: str        = "zh-CN",
) -> str:
    """综合 LLM 调用失败时的降级 Markdown 报告。按 output_language 本地化。"""
    if stock_identity is None:
        stock_identity = f"{market}/{symbol}"
    strs = _FALLBACK_STRINGS.get(output_language, _FALLBACK_STRINGS["zh-CN"])
    title = title_override or strs["title"]
    section_summary = "\n".join(
        f"- **{name}**：{'正常生成' if not text.startswith('[') else '暂不可用'}"
        for name, text in sections.items()
    )
    return f"""\
# {title}：{stock_identity}

## {strs['h_summary']}

{strs['t_summary'].format(identity=stock_identity, exc=exc)}

## {strs['h_sources']}

{strs['t_sources']}

## {strs['h_multi']}

{section_summary}

## {strs['h_limits']}

{strs['t_limits']}

## {strs['h_followup']}

{strs['t_followup']}

## {strs['h_risk']}

{strs['t_risk']}
"""
