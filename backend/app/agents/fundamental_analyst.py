"""
FundamentalAnalystAgent — 基本面快照分析师。

调用链路：
  analyze(market, symbol)
    → FundamentalDataService.get_fundamentals()   # 获取基本面快照（必须成功）
    → _build_user_prompt()                         # 将快照组装为结构化文本
    → BaseLLMClient.chat()                         # 调用 LLM 生成报告
    → 返回 Markdown 基本面分析报告 (str)

设计原则：
  - 只分析 fundamentals 快照中非 null 的字段，null 字段标记 [缺失]，不推断。
  - latest_report_date 必须在报告中披露，区分季报/中报/年报。
  - PE/PB 缺失时不评价估值水平。
  - industry/business_summary 缺失时不做行业分析。
  - HK 财报字段大多缺失时，生成"数据不足型报告"，不编造数据。
  - 不给确定性投资建议。
  - 输出为标准 Markdown，章节结构固定。
"""

from __future__ import annotations

import logging

from app.llm.base import BaseLLMClient
from app.services.fundamental_data_service import (
    FundamentalDataService,
    fundamental_data_service as _default_service,
)
from app.agents.language_utils import build_output_language_instruction

log = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的基本面分析师，专注于 A 股和港股市场的单股基本面快照分析。

【严格禁止事项】
以下内容一律禁止，违反即为无效输出：
1. 禁止编造或推断任何标记为 [缺失] 的字段，包括但不限于：
   PE（市盈率）、PB（市净率）、ROE、毛利率、净利率、营收增速、利润增速、
   现金流、资产负债率、行业分类、主营业务、护城河、管理层信息、竞争对手。
   标记为 [缺失] 的字段一律不得引用，不得估算，不得以"通常情况下"
   "行业一般""结合历史规律"等方式替代。
2. 禁止给出确定性买卖建议或方向预测。
   严禁使用：必涨、必跌、稳赚、强烈买入、强烈卖出、满仓、梭哈、
   抄底、逃顶、清仓、保证收益、一定获利等表达。
3. PE/PB 标记为 [缺失] 时，不得对估值水平做任何判断。
   "高估""低估""合理估值""相对低估"等表达均禁止。
4. industry 标记为 [缺失] 时，不得做行业横向对比或行业地位判断。
5. business_summary 标记为 [缺失] 时，不得分析商业模式、竞争优势或护城河。
6. 无同行数据时，不得进行任何同行比较。
7. 季报数据（报告期不以 12-31 结尾）不得写成"全年表现"或"全年数据"。
   必须使用"最新报告期数据显示""截至该报告期"等表达。
8. 港股（HK）财报字段大多标记为 [缺失] 时：
   不得编造任何港股财务指标（PE、ROE、现金流等）；
   应生成"数据不足型基本面报告"；
   应明确说明 HK 基本面数据源暂未完善，相关分析受到限制。

【分析准则】
1. 只能基于用户提供的 fundamentals 快照数据进行分析。
2. 分析结论必须忠实反映数据：数据显示下降时不能描述为增长。
3. 对缺失字段必须明确写"[字段] 数据缺失，暂不评价"，不得跳过不提。
4. 本报告仅为基本面快照视角，不代表股票投资价值的完整判断。

【字段单位说明】
- roe / gross_margin / net_margin / revenue_growth_yoy /
  net_profit_growth_yoy / debt_ratio：单位为 %。
  例如 54.27 表示 54.27%，不是 0.5427。
- operating_cashflow：单位为元（CNY）。展示时请换算为亿元。
  例如 26910000000 = 269.1 亿元。

【输出格式】
输出完整 Markdown，严格按以下结构，标题名称不得更改，不得新增或删除章节。
子章节统一使用三级标题（###）：

### 一、数据概览
- 股票代码、市场、公司名称
- 分析报告期（必须写出 latest_report_date 及报告类型：季报/中报/年报）
- 可用字段数量与缺失字段说明

### 二、盈利能力
- ROE（净资产收益率）—— 如缺失写"数据缺失，暂不评价"
- 毛利率（销售毛利率）—— 如缺失写"数据缺失，暂不评价"
- 净利率（销售净利率）—— 如缺失写"数据缺失，暂不评价"

### 三、成长能力
- 营收同比增长率 —— 如缺失写"数据缺失，暂不评价"
- 净利润同比增长率 —— 如缺失写"数据缺失，暂不评价"

### 四、财务安全与现金流
- 资产负债率 —— 如缺失写"数据缺失，暂不评价"
- 经营性现金流（换算为亿元展示）—— 如缺失写"数据缺失，暂不评价"

### 五、估值与数据缺口
- 说明 PE/PB/PS 等估值字段是否存在
- 如缺失，必须写"估值数据缺失，暂不评价估值水平"
- 汇总所有缺失字段

### 六、观察要点
- 列举 2-3 个值得关注的基本面信号（只描述客观现象，不预测方向，不给操作建议）
- 若数据严重不足，说明当前分析的主要限制

### 风险提示
仅供研究参考，不构成投资建议。基本面快照分析存在局限性，\
单期数据不代表长期趋势，市场存在不确定性，\
投资者需自行判断并承担投资风险。\
"""


# ── 报告期类型推断 ─────────────────────────────────────────────────────────────

def _report_type(date_str: str | None) -> str:
    if not date_str:
        return "未知"
    if date_str.endswith("-03-31"):
        return "一季报（Q1）"
    if date_str.endswith("-06-30"):
        return "中报/半年报（H1）"
    if date_str.endswith("-09-30"):
        return "三季报（Q3）"
    if date_str.endswith("-12-31"):
        return "年报（全年）"
    return "未知类型"


# ── Agent ─────────────────────────────────────────────────────────────────────

class FundamentalAnalystAgent:
    """
    基本面快照分析 Agent。

    Args:
        llm:    实现了 BaseLLMClient.chat() 的 LLM 客户端。
        svc:    FundamentalDataService 实例（不传则使用模块级单例）。
    """

    def __init__(
        self,
        llm: BaseLLMClient,
        svc: FundamentalDataService | None = None,
    ) -> None:
        self._llm = llm
        self._svc = svc or _default_service

    def analyze(
        self,
        market:          str,
        symbol:          str,
        output_language: str = "zh-CN",
    ) -> str:
        """
        生成 Markdown 基本面分析报告。

        Args:
            market:          "CN" 或 "HK"
            symbol:          股票代码
            output_language: 报告输出语言代码（默认 zh-CN）。

        Returns:
            Markdown 格式的分析报告字符串。

        Raises:
            RuntimeError: fundamentals 获取结构异常或 LLM 调用失败。
            ValueError:   market / symbol 参数非法。
        """
        market = market.upper()
        if market not in {"CN", "HK"}:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{market}'")
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol 不能为空")

        # ── Step 1: 获取基本面快照 ────────────────────────────────────────────
        log.info("FundamentalAnalystAgent: fetching fundamentals [%s/%s]", market, symbol)
        snapshot = self._svc.get_fundamentals(market, symbol)

        if not isinstance(snapshot, dict) or "data_quality" not in snapshot:
            raise RuntimeError(
                f"fundamentals 返回结构异常 [{market}/{symbol}]"
            )

        # ── Step 2: 组装用户 Prompt ───────────────────────────────────────────
        user_content = self._build_user_prompt(market, symbol, snapshot, output_language)

        # ── Step 3: 调用 LLM ──────────────────────────────────────────────────
        log.info("FundamentalAnalystAgent: calling LLM [%s/%s]", market, symbol)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        return self._llm.chat(messages, temperature=0.3)

    # ── 内部：构造用户 Prompt ─────────────────────────────────────────────────

    @staticmethod
    def _build_user_prompt(
        market: str,
        symbol: str,
        snapshot: dict,
        output_language: str = "zh-CN",
    ) -> str:
        """
        将 fundamentals 快照拆分为：
          available_fields — 非 null 的字段，可供 LLM 分析
          missing_fields   — null 的关键字段，LLM 必须标记为缺失
          data_quality     — 元信息（provider、report_date、message）
        output_language 控制报告语言。
        """
        dq       = snapshot.get("data_quality", {})
        company  = snapshot.get("company", {})
        val      = snapshot.get("valuation", {})
        prof     = snapshot.get("profitability", {})
        growth   = snapshot.get("growth", {})
        fh       = snapshot.get("financial_health", {})

        # ── 基本信息 ──────────────────────────────────────────────────────────
        market_cn       = "A股" if market == "CN" else "港股"
        company_name    = company.get("name") or "[缺失]"
        latest_date     = dq.get("latest_report_date")
        report_type_str = _report_type(latest_date)
        is_annual       = latest_date.endswith("-12-31") if latest_date else False

        # ── 字段分组 ──────────────────────────────────────────────────────────
        # 所有"关键基本面字段"的显示名、路径和单位
        _KEY_FIELDS: list[tuple[str, str, str | None]] = [
            # (显示名, snapshot路径, 单位说明)
            ("公司名称",             "company.name",                      None),
            ("所属行业",             "company.industry",                  None),
            ("主营业务",             "company.business_summary",          None),
            ("市盈率 PE",            "valuation.pe",                      "倍"),
            ("市净率 PB",            "valuation.pb",                      "倍"),
            ("市销率 PS",            "valuation.ps",                      "倍"),
            ("总市值",               "valuation.market_cap",              "元"),
            ("股息率",               "valuation.dividend_yield",          "%"),
            ("ROE 净资产收益率",      "profitability.roe",                 "%"),
            ("毛利率",               "profitability.gross_margin",        "%"),
            ("净利率",               "profitability.net_margin",          "%"),
            ("营收同比增长率",         "growth.revenue_growth_yoy",         "%"),
            ("净利润同比增长率",       "growth.net_profit_growth_yoy",      "%"),
            ("资产负债率",            "financial_health.debt_ratio",       "%"),
            ("经营活动现金流净额",     "financial_health.operating_cashflow","元 CNY"),
        ]

        def _get_val(path: str):
            parts = path.split(".")
            return snapshot.get(parts[0], {}).get(parts[1])

        available: list[str] = []
        missing:   list[str] = []

        for label, path, unit in _KEY_FIELDS:
            v = _get_val(path)
            if v is None:
                missing.append(f"  {label}（{path}）: [缺失]")
            else:
                # operating_cashflow: 换算为亿元
                if path == "financial_health.operating_cashflow":
                    display = f"{v / 1e8:.2f} 亿元（原始值 {v:.0f} 元）"
                elif unit == "%":
                    display = f"{v}%"
                elif unit == "元":
                    display = f"{v:,.0f} 元"
                else:
                    display = str(v)
                    if unit:
                        display += f" {unit}"
                available.append(f"  {label}（{path}）: {display}")

        # ── 已知 missing_fields（service 层计算的）────────────────────────────
        service_missing = dq.get("missing_fields") or []
        # 合并：service 报告的缺失但可能未在上面 _KEY_FIELDS 中展示
        extra_missing = [m for m in service_missing if not any(m in line for line in missing)]
        if extra_missing:
            for m in extra_missing:
                missing.append(f"  {m}: [缺失]（service 层报告）")

        # ── HK / 数据不足判断 ─────────────────────────────────────────────────
        financial_fields = [
            prof.get("roe"), prof.get("gross_margin"), prof.get("net_margin"),
            growth.get("revenue_growth_yoy"), growth.get("net_profit_growth_yoy"),
            fh.get("debt_ratio"), fh.get("operating_cashflow"),
        ]
        n_available_financial = sum(1 for v in financial_fields if v is not None)
        is_data_insufficient  = n_available_financial == 0

        # ── 数据来源说明 ──────────────────────────────────────────────────────
        sources_summary = ", ".join(set(dq.get("data_sources", {}).values())) or "无"
        dq_message = (dq.get("message") or "").strip()

        # ── 季报警告 ──────────────────────────────────────────────────────────
        period_warning = ""
        if latest_date and not is_annual:
            period_warning = (
                f"\n【重要】当前数据为{report_type_str}，"
                "不代表全年表现。分析中必须使用「最新报告期数据显示」等表达，"
                "不得写成「全年表现」或「年度数据」。"
            )

        # ── 数据不足警告（主要针对 HK）───────────────────────────────────────
        insufficient_warning = ""
        if is_data_insufficient:
            insufficient_warning = (
                "\n【数据不足警告】当前财报字段（ROE、毛利率、净利率、增速、"
                "资产负债率、现金流）全部缺失。"
                "请生成「数据不足型基本面报告」，"
                "明确说明当前市场的基本面数据源暂未完善，"
                "不得编造任何财务指标，不得以行业经验替代实际数据。"
            )

        # ── 组装 Prompt ───────────────────────────────────────────────────────
        available_block = "\n".join(available) if available else "  （无可用字段）"
        missing_block   = "\n".join(missing)   if missing   else "  （无缺失字段）"

        lang_instruction = build_output_language_instruction(output_language)

        return f"""\
请对以下股票进行基本面快照分析，仅基于所提供数据，严格遵守系统提示中的所有禁止事项。
{period_warning}{insufficient_warning}

【基本信息】
  市场: {market_cn}（{market}）
  代码: {symbol}
  公司名称: {company_name}

【报告期】
  latest_report_date: {latest_date or "未知"}
  报告类型: {report_type_str}
  说明: {"本数据为全年数据（年报）。" if is_annual else f"本数据为{report_type_str}，不代表全年表现。"}

【可用字段（非 null，可以分析）】
{available_block}

【缺失字段（null，不得编造，不得推断，必须逐项注明"数据缺失，暂不评价"）】
{missing_block}

【数据质量】
  provider: {dq.get('provider') or '未知'}
  data_sources: {sources_summary}
  stale: {dq.get('stale', False)}
{('  message: ' + dq_message) if dq_message else ''}

请严格按照系统提示规定的 Markdown 报告结构输出，章节标题不得更改，不得新增或删除章节。\
{lang_instruction}"""
