"""
TechnicalAnalystAgent — 技术面分析师。

调用链路：
  analyze(market, symbol)
    → StockDataService.get_kline_for_agent()       # 获取 K线（必须成功）
    → StockDataService.get_quote_optional()         # 获取实时报价（可选，失败不阻塞）
    → TechnicalIndicatorService.calculate()         # 计算技术指标
    → BaseLLMClient.chat()                          # 调用 LLM 生成报告
    → 返回 Markdown 技术面分析报告 (str)

设计原则：
  - 本 Agent 仅做技术面分析，严禁涉及基本面内容。
  - quote 不可用时，使用 K线最后一条 close 作为参考价，分析不中断。
  - amount_estimated 仅作弱参考，不得用于资金流向结论。
  - 不给出确定性投资建议。
  - 输出为标准 Markdown，章节结构固定。
"""

from __future__ import annotations

import logging

from app.llm.base import BaseLLMClient
from app.services.stock_data_service import stock_data_service
from app.services.technical_indicator_service import technical_indicator_service
from app.agents.language_utils import build_output_language_instruction

log = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的技术面分析师，专注于 A 股和港股市场的量化技术分析。

【严格禁止事项】
以下内容一律禁止，违反即为无效输出：
1. 禁止编造或推断任何基本面数据，包括但不限于：
   PE（市盈率）、PB（市净率）、ROE、净利润、营业收入、现金流、资产负债率、分红率、股东结构等。
   本报告没有这些数据，不得引用，不得捏造，不得以"通常情况下""行业一般"替代。
2. 禁止给出确定性的买卖建议或方向预测。
   严禁使用：必涨、必跌、稳赚、肯定上涨、一定下跌、强烈买入、强烈卖出、满仓、梭哈、抄底、
   逃顶、清仓、加仓、减仓推荐等表达。
3. 禁止把估算成交额（amount_estimated）当作真实成交额（amount）引用。
   amount_estimated 仅为粗略估算（均价×成交量），不代表交易所真实成交数据。
   不得基于估算额做"资金大幅流入""主力出货""大资金建仓"等强资金结论。
4. 禁止涉及新闻面、政策面、行业基本面、宏观经济分析内容。
5. 指标数据不足时（如 K线不满 60 根无法计算 MA60），须在报告中注明"数据不足，暂不评估"，
   不得捏造或估算。

【分析准则】
1. 只能基于用户提供的 K线数据和技术指标进行分析。
2. 分析结论必须忠实反映数据：数据显示下降趋势时，不可描述为上升趋势。
3. 本报告仅为技术面视角，不代表股票投资价值判断。

【数据说明】
- amount（成交额）：若有，为交易所真实成交数据，单位为元（CN）或港元（HK）。
- amount_estimated（估算成交额）：为粗略估算，公式 = (high+low)/2 × 成交量（已换算为股数）。
  可用于辅助判断成交量级别，但属于弱参考，不可作为资金流向的精确依据。
- CN kline volume 单位：手（1 手 = 100 股）。
- HK kline volume 单位：股。
- quote volume 单位：股。

【输出格式】
输出完整 Markdown，严格按以下结构，标题名称不得更改，不得新增或删除章节。
子章节统一使用三级标题（###）。

报告第一节必须是"摘要结论"，随后才是各详细章节：

### 摘要结论
- **本面结论**：偏强 / 偏弱 / 分歧 / 数据不足 / 需观察（从技术面角度选择最符合的一项）
- **一句话结果**：用一句话说明本次技术面分析最重要的发现。
- **正面信号**：1. ... 2. ...（列举 1-2 个积极的技术信号；无则写"当前无明显正面信号"）
- **风险信号**：1. ... 2. ...（列举 1-2 个需关注的技术风险；无则写"当前无明显风险信号"）
- **后续观察**：1. ... 2. ...（列举 1-2 个后续值得追踪的指标或价位）
- **数据可信度**：高 / 中 / 低，并简要说明原因（如 K 线数据来源、数据根数是否充足等）

### 一、行情概览
- 股票代码、市场
- 参考价格及来源（实时报价 或 K线最新收盘价（实时报价不可用））
- 统计区间（起止日期、K线根数）

### 二、均线与趋势
- MA5、MA10、MA20、MA60 当前值（数据不足时注明"数据不足，暂不评估"）
- 短期趋势（MA5 vs MA10）、中期趋势（MA10 vs MA20）
- 价格相对 MA20 和 MA60 的偏离百分比

### 三、量价变化
- 近期成交量变化（5 日均量 vs 20 日均量）
- 今日量能状态
- 量价配合情况（须基于数据判断，不得凭空描述）

### 四、短期风险
- 近 20 日高点（压力位参考）与低点（支撑位参考）
- 近 60 日高低点（若数据充足）
- 近 1 日、5 日、20 日涨跌幅

### 五、观察要点
- 列举 2-3 个值得关注的技术信号（只描述客观现象，不预测方向，不给出操作建议）

### 风险提示
仅供研究参考，不构成投资建议。技术面分析存在局限性，市场存在不确定性，\
投资者需自行判断并承担投资风险。\
"""


# ── Agent ─────────────────────────────────────────────────────────────────────

class TechnicalAnalystAgent:
    """
    技术面分析 Agent。

    Args:
        llm: 实现了 BaseLLMClient.chat() 的 LLM 客户端。
    """

    def __init__(self, llm: BaseLLMClient) -> None:
        self._llm = llm

    def analyze(
        self,
        market:          str,
        symbol:          str,
        output_language: str = "zh-CN",
    ) -> str:
        """
        生成 Markdown 技术面分析报告。

        Args:
            market:          "CN" 或 "HK"
            symbol:          股票代码，例如 "600519" / "700"
            output_language: 报告输出语言代码（默认 zh-CN）。
                             支持 zh-CN / en-US / zh-TW / ja-JP / ko-KR / es-ES。

        Returns:
            Markdown 格式的分析报告字符串。

        Raises:
            RuntimeError: 获取 K线失败（数据层异常）。
            ValueError:   market / symbol 参数非法。
        """
        market = market.upper()

        # ── Step 1: 获取 K线（必须成功）─────────────────────────────────────
        log.info("TechnicalAnalystAgent: fetching kline [%s/%s]", market, symbol)
        bars = stock_data_service.get_kline_for_agent(market, symbol, limit=120)

        # ── Step 2: 获取实时报价（可选，失败不阻塞）─────────────────────────
        quote = stock_data_service.get_quote_optional(market, symbol)
        if quote:
            log.info("TechnicalAnalystAgent: quote OK [%s/%s] price=%s",
                     market, symbol, quote.get("price"))
        else:
            log.warning(
                "TechnicalAnalystAgent: quote unavailable [%s/%s], "
                "falling back to last kline close",
                market, symbol,
            )

        # ── Step 3: 计算技术指标 ─────────────────────────────────────────────
        indicators = technical_indicator_service.calculate(bars)

        # ── Step 4: 组装用户 Prompt ──────────────────────────────────────────
        user_content = self._build_user_prompt(
            market, symbol, bars, quote, indicators,
            output_language=output_language,
        )

        # ── Step 5: 调用 LLM ─────────────────────────────────────────────────
        log.info("TechnicalAnalystAgent: calling LLM [%s/%s]", market, symbol)
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
        bars: list[dict],
        quote: dict | None,
        indicators: dict,
        output_language: str = "zh-CN",
    ) -> str:
        """将数据整理为结构化文本，供 LLM 阅读。output_language 控制报告语言。"""

        # ── 参考价格 ─────────────────────────────────────────────────────────
        if quote and quote.get("price") is not None:
            ref_price        = quote["price"]
            ref_price_source = "实时报价"
        else:
            ref_price        = bars[-1].get("close") if bars else None
            ref_price_source = "K线最新收盘价（实时报价不可用）"

        market_cn  = "A股" if market == "CN" else "港股"
        first_date = bars[0].get("date", "未知") if bars else "未知"
        last_date  = bars[-1].get("date", "未知") if bars else "未知"
        vol_unit   = "手" if market == "CN" else "股"

        # ── 实时报价区块 ──────────────────────────────────────────────────────
        if quote:
            currency = "港元" if market == "HK" else "元"
            q_lines = []
            for label, key in [("名称", "name"), ("今开", "open"), ("今高", "high"),
                                ("今低", "low"), ("昨收", "prev_close")]:
                if quote.get(key) is not None:
                    q_lines.append(f"  {label}: {quote[key]}")
            if quote.get("change") is not None:
                q_lines.append(f"  涨跌: {quote['change']}")
            if quote.get("change_pct") is not None:
                q_lines.append(f"  涨跌幅: {quote['change_pct']}%")
            if quote.get("volume") is not None:
                q_lines.append(f"  成交量: {quote['volume']:,} 股")
            if quote.get("amount") is not None:
                q_lines.append(
                    f"  成交额（真实）: {quote['amount']/1e8:.2f} 亿{currency}"
                )
            if quote.get("trade_time"):
                q_lines.append(f"  报价时间: {quote['trade_time']}")
            quote_block = "【实时报价】\n" + "\n".join(q_lines) if q_lines else (
                "【实时报价】\n  数据获取成功但字段为空"
            )
        else:
            quote_block = "【实时报价】\n  不可用，参考 K 线最新收盘价替代"

        # ── 技术指标区块 ──────────────────────────────────────────────────────
        def fmt(v: object, suffix: str = "") -> str:
            return f"{v}{suffix}" if v is not None else "数据不足"

        indicators_block = f"""\
【技术指标】
  K线根数: {indicators['bar_count']} 根（{first_date} → {last_date}）
  最新收盘: {fmt(indicators['latest_close'])}

  均线（收盘价均值）:
    MA5  = {fmt(indicators['ma5'])}
    MA10 = {fmt(indicators['ma10'])}
    MA20 = {fmt(indicators['ma20'])}
    MA60 = {fmt(indicators['ma60'])}

  价格偏离均线:
    相对 MA20: {fmt(indicators['price_vs_ma20_pct'], '%')}
    相对 MA60: {fmt(indicators['price_vs_ma60_pct'], '%')}

  涨跌幅:
    近  1 日: {fmt(indicators['return_1d_pct'],  '%')}
    近  5 日: {fmt(indicators['return_5d_pct'],  '%')}
    近 20 日: {fmt(indicators['return_20d_pct'], '%')}

  区间极值:
    近 20 日最高: {fmt(indicators['high_20d'])}  最低: {fmt(indicators['low_20d'])}
    近 60 日最高: {fmt(indicators['high_60d'])}  最低: {fmt(indicators['low_60d'])}

  成交量（单位: {vol_unit}）:
    今日:       {fmt(indicators['volume_latest'])}
    5 日均:     {fmt(indicators['volume_avg_5d'])}
    20 日均:    {fmt(indicators['volume_avg_20d'])}
    量比(5d/20d): {fmt(indicators['volume_ratio_5_20'])}  （>1 近期放量，<1 近期缩量）
    今日/5日均:   {fmt(indicators['volume_ratio_today'])}

  综合判断（仅供参考）:
    短期趋势（MA5/MA10）:  {indicators['short_term_trend']}
    中期趋势（MA10/MA20）: {indicators['medium_term_trend']}
    量能信号:              {indicators['volume_signal']}"""

        # ── 近 20 根 K线明细 ──────────────────────────────────────────────────
        recent = bars[-20:] if len(bars) >= 20 else bars
        kline_rows = []
        for b in recent:
            est = b.get("amount_estimated")
            # 标注 [估算] 避免 LLM 误认为真实数据
            est_str = f"{est/1e8:.2f}亿[估算]" if est is not None else "N/A"
            amt = b.get("amount")
            amt_str = f"{amt/1e8:.2f}亿[真实]" if amt is not None else "—"
            kline_rows.append(
                f"  {b.get('date')} | "
                f"开:{b.get('open')} 高:{b.get('high')} "
                f"低:{b.get('low')} 收:{b.get('close')} | "
                f"量:{b.get('volume')}{vol_unit} | "
                f"成交额:{amt_str} 估算额:{est_str}"
            )
        kline_block = "\n".join(kline_rows)

        lang_instruction = build_output_language_instruction(output_language)

        return f"""\
请对以下股票进行技术面分析，仅基于所提供的数据，严格遵守系统提示中的所有禁止事项。

【基本信息】
  市场: {market_cn}（{market}）
  代码: {symbol}
  参考价格: {ref_price}（来源: {ref_price_source}）

{quote_block}

{indicators_block}

【近 20 根日 K 线明细】
说明：成交额列中 [真实] 为交易所数据；[估算] 为 (high+low)/2 × 成交量（换算为股数）的粗略估算，
      不得基于估算额做资金流向的强结论。
列格式：日期 | 开高低收 | 成交量 | 成交额（真实） 估算额（粗略估算）
{kline_block}

请严格按照系统提示规定的 Markdown 报告结构输出，章节标题不得更改，不得新增或删除章节。\
{lang_instruction}"""
