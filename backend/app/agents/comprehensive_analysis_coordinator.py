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

# 传给综合 LLM 的子报告最大字符数（technical / fundamental / peer_comparison）
_SECTION_MAX_CHARS = 4000
# 新闻子报告最大字符数（稍短，避免综合 prompt 过长）
_NEWS_SECTION_MAX_CHARS = 3000

# 每个 Agent 超时（秒）
_AGENT_TIMEOUT = 300


# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位综合股票分析协调员，负责将技术面、基本面、同行对比、新闻面四份子报告整合为简洁的综合分析摘要。

【报告标题与身份声明规则（必须严格遵守）】
- 用户消息的【分析目标】中包含"股票："字段，该字段是本次分析对象的完整标识（如"平安银行（CN/000001）"或"腾讯控股（HK/00700）"）。
- 报告 Markdown 第一行标题必须使用该完整标识，格式为：
    # 综合分析报告：{股票字段完整内容}
  例如：# 综合分析报告：平安银行（CN/000001）
- 综合结论卡片中【一句话结论】必须以"本报告分析对象为 {股票字段完整内容}。"开头，随后一句话概括综合判断。
- 如果股票字段内容仅为"市场/代码"格式（即无中文名称），则保持该格式，不得凭空添加名称。
- 正文每个章节第一次提及本股票时，必须使用完整标识（含中文名，如已提供），后续可简称。

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

【输出格式】
输出完整 Markdown，严格按以下结构，标题名称不得更改，不得新增或删除章节：

# 综合分析报告：{【分析目标】中"股票："字段的完整内容}

## 一、综合结论卡片
- **综合判断**：偏强 / 偏弱 / 分歧 / 数据不足 / 需观察（基于四面信号综合选择最符合的一项）
- **一句话结论**：本报告分析对象为 {股票字段完整内容}。（随后用一句话概括综合判断，不得超过 30 字）
- **核心矛盾**：若各维度信号存在分歧，列举主要矛盾点（1-2 条）；若方向基本一致，写"各维度信号方向基本一致"。
- **正面因素**：1. ... 2. ...（各维度中的正面观察，限 2-3 条，只引用子报告已有内容）
- **主要风险**：1. ... 2. ...（各维度中的风险信号，限 2-3 条，只引用子报告已有内容）
- **后续观察重点**：1. ... 2. ...（2-3 个中性后续观察点，不写方向预测，不写操作建议）
- **数据完整度**：说明本次分析覆盖哪些维度、哪些字段缺失，以及对结论可信度的影响。

## 二、四面结论汇总

### 1. 技术面结论
提炼技术面子报告的 1-3 个关键技术信号，不得引入基本面或新闻面数据。

### 2. 基本面结论
提炼基本面子报告的主要发现，缺失字段不得评价。
必须声明字段边界："在当前可用字段范围内""由于估值/行业字段缺失，基本面判断有限"等。

### 3. 同行对比结论
提炼同行对比子报告的主要发现，说明目标公司相对可比样本的相对位置。
无同行时说明"暂无可用同行数据"；样本来源须明确（PEER_MAP 手动配置 或 动态热门股）。

### 4. 新闻面结论
提炼新闻面子报告的关键结论。
- 暂无新闻数据时，写"本时间窗口内暂无新闻数据"。
- HK 关键词搜索结果须说明相关性需谨慎判断。
- 不得编造新闻，只能整合 section 中已有结论。

## 三、主要数据局限
列出本次分析缺失或受限的关键字段及原因（含新闻时间窗口限制和数据源覆盖）。

## 四、后续观察清单
2～3 个中性观察点，不写方向预测，不写操作建议。

## 风险提示
仅供研究参考，不构成投资建议。技术面、基本面、同行对比与新闻面分析均存在局限性，\
市场存在不确定性，投资者需自行判断并承担投资风险。\
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
        synthesis_user = self._build_synthesis_prompt(market, symbol, sections)

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

        metadata = _build_metadata(market, sections, statuses)
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

        metadata = _build_metadata(market, sections, statuses)
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

        metadata = _build_metadata(market, sections, statuses)
        metadata["analysis_scope"]   = analysis_scope
        metadata["workflow_engine"]  = "custom_coordinator"
        metadata["output_language"]  = output_language

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
        将四个子报告截断后拼入 Prompt。
        technical / fundamental / peer_comparison 截断至 4000 字符；
        news 截断至 3000 字符。
        截断时追加截断提示，sections 中原始内容不变。

        stock_identity: 完整股票标识，如"平安银行（CN/000001）"；
                        None 时 fallback 为 "{market}/{symbol}"。
        output_language: 报告输出语言代码（默认 zh-CN）。
        """
        if stock_identity is None:
            stock_identity = f"{market}/{symbol}"
        def _truncate(text: str, label: str, max_chars: int) -> str:
            if len(text) <= max_chars:
                return text
            return (
                text[:max_chars]
                + f"\n\n...[{label} 报告已截断，以上为前 {max_chars} 字符]"
            )

        tech_text  = _truncate(sections.get("technical", ""),       "技术面",   _SECTION_MAX_CHARS)
        fund_text  = _truncate(sections.get("fundamental", ""),     "基本面",   _SECTION_MAX_CHARS)
        peer_text  = _truncate(sections.get("peer_comparison", ""), "同行对比", _SECTION_MAX_CHARS)
        news_text  = _truncate(sections.get("news", ""),            "新闻面",   _NEWS_SECTION_MAX_CHARS)

        truncated_any = any([
            len(sections.get("technical",       "")) > _SECTION_MAX_CHARS,
            len(sections.get("fundamental",     "")) > _SECTION_MAX_CHARS,
            len(sections.get("peer_comparison", "")) > _SECTION_MAX_CHARS,
            len(sections.get("news",            "")) > _NEWS_SECTION_MAX_CHARS,
        ])
        truncation_note = (
            "\n⚠️ 注意：以下子报告经过长度截断，请只基于可见内容整合，"
            "不得补充截断部分未出现的数据。\n"
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

        return f"""\
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

---
【子报告 1 — 技术面分析】
{tech_text}

---
【子报告 2 — 基本面分析】
{fund_text}

---
【子报告 3 — 同行对比分析】
{peer_text}

---
【子报告 4 — 新闻面分析】
{news_text}

---
请严格按照系统提示规定的 Markdown 报告结构输出，标题名称不得更改，不得新增或删除章节。\
综合报告只整合以上可见内容，不得推断或补充未出现的数据。\
新闻面要点只能引用子报告 4 中已有的结论，不得编造新闻。\
{language_instruction}"""


# ── 工具函数 ─────────────────────────────────────────────────────────────────

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
