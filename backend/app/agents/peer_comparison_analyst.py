"""
PeerComparisonAnalystAgent — 同行基本面对比分析师。

调用链路：
  analyze(market, symbol)
    → PeerComparisonService.get_peer_fundamentals()  # 并发拉取 target + peers
    → _build_user_prompt()                            # 组装结构化对比文本
    → BaseLLMClient.chat()                            # 调用 LLM 生成报告
    → 返回 Markdown 同行对比报告 (str)

设计原则：
  - 只分析 comparison_fields.available 中的字段。
  - missing_in_all / missing_in_target 字段明确标注禁止评价。
  - missing_in_any_peer 字段可谨慎描述，但必须说明覆盖不完整。
  - peers 为空 → 生成"暂无同行配置"报告，不编造同行。
  - available 为空 → 生成"无可比字段"报告，不强行对比。
  - HK 业务形态差异大的 peer set → 必须声明"同行口径较粗"。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import BaseLLMClient
from app.services.peer_comparison_service import (
    PeerComparisonService,
    peer_comparison_service as _default_service,
)
from app.agents.language_utils import build_output_language_instruction

log = logging.getLogger(__name__)

# ── 字段展示配置 ───────────────────────────────────────────────────────────────

# (路径, 中文名, 单位后缀)
_FIELD_META: dict[str, tuple[str, str]] = {
    "valuation.pe":                      ("市盈率 PE",        "倍"),
    "valuation.pb":                      ("市净率 PB",        "倍"),
    "profitability.roe":                 ("ROE 净资产收益率",  "%"),
    "profitability.gross_margin":        ("毛利率",           "%"),
    "profitability.net_margin":          ("净利率",           "%"),
    "growth.revenue_growth_yoy":         ("营收同比增长率",    "%"),
    "growth.net_profit_growth_yoy":      ("净利润同比增长率",  "%"),
    "financial_health.debt_ratio":       ("资产负债率",        "%"),
    "financial_health.operating_cashflow": ("经营现金流净额", "亿元"),
}

# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的基本面同行对比分析师，专注于 A 股和港股市场，\
生成审慎、中性的同行基本面对比报告。

【严格禁止事项】
1. 禁止分析或引用 [禁止评价 — 全体缺失] 标注的字段。这类字段 target 和所有 peers 均为 null，任何基于它们的结论都是编造。
2. 禁止分析或引用 [禁止评价 — target 缺失] 标注的字段。这类字段 target 自身为 null，无法对目标公司做任何相关判断。
3. 禁止编造：
   - PE / PB（未在可用字段中时）
   - 行业分类 / 主营业务 / 护城河 / 管理层
   - 同行公司名单（只能使用用户提供的 peers 列表）
   - 任何未在输入数据中出现的财务数字
4. 禁止将手动 PEER_MAP 当成严格行业分类。对港股（HK）或业务形态差异大的 peer set，必须在报告开头声明「同行口径较粗，仅供参考」。
5. 禁止给出买入/卖出/持有建议。严禁使用：必涨、必跌、稳赚、强烈买入、满仓、梭哈、保证收益、抄底、清仓。
6. 禁止使用「明显低估」或「明显高估」表达。估值比较只能使用：
   「估值水平相对偏高」「估值水平相对偏低」「仍需结合行业和基本面进一步判断」。
7. peers 为空时：不得编造任何同行，只能生成「暂无同行配置」型报告。
8. 可用字段为空时：不得强行对比，只能生成「当前缺少可共同比较字段」型报告。
9. 对 [覆盖不完整] 标注的字段：只能说明哪些 peers 缺失此数据，不得基于部分覆盖得出强结论。
10. 当 peer_source 为 "dynamic_hot" 时（同行来自申万行业 Hot Score 热门股）：
    - 必须在报告「对比样本说明」中明确写明：
      「本次同行来自同一申万一级行业内的 Hot Score 热门股。
        Hot Score 基于成交额（权重 0.7）与涨跌幅绝对值（权重 0.3）加权计算，
        代表市场关注度，不代表基本面质量或投资价值，不等同于严格的业务可比同行。」
    - 禁止使用"更优质"、"更值得投资"、"更值得买入"、"行业龙头"等强结论，
      除非输入财务数据（如 ROE、毛利率、净利率等）明确支持该判断。
    - 不得将 Hot Score 排名高解读为"基本面更强"或"更有投资价值"。
    - 横向基本面数值对比（PE/ROE/毛利率等）仍然允许，但结论必须限定在
      "在当前可用字段范围内的相对位置"，不得外推为全行业排名结论。

【分析准则】
1. 只能基于用户提供的 PeerComparisonService 数据进行分析。
2. 优先比较 「可用字段（available）」中的字段，按盈利/成长/财务安全/估值分组展开。
3. 对每个可用字段，应：① 列出各公司的数值；② 做横向比较；③ 指出目标公司在同组中的相对位置；④ 不做绝对判断。
4. 报告必须披露 latest_report_dates，并注明报告类型（季报/中报/年报）。
5. 结论必须忠实反映数据方向，数据显示下降时不能描述为增长。

【字段单位】
- PE/PB：倍
- roe / gross_margin / net_margin / revenue_growth_yoy / net_profit_growth_yoy / debt_ratio：%（已是百分比形式，不得再乘 100）
- operating_cashflow：已换算为亿元展示

【输出格式】
输出完整 Markdown，严格按以下结构，标题名称不得更改。
子章节统一使用三级标题（###）：

### 一、对比样本说明

### 二、可比字段概览

### 三、盈利能力对比

### 四、成长能力对比

### 五、财务安全与现金流对比

### 六、估值对比与缺失字段

### 七、观察要点

### 风险提示
仅供研究参考，不构成投资建议。\
"""

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _get_nested(snapshot: dict, path: str):
    section, _, field = path.partition(".")
    if not field:
        return snapshot.get(section)
    sub = snapshot.get(section)
    if not isinstance(sub, dict):
        return None
    return sub.get(field)


def _fmt_value(path: str, v) -> str:
    """将字段值格式化为带单位的字符串。"""
    if v is None:
        return "[缺失]"
    _, unit = _FIELD_META.get(path, ("", ""))
    if path == "financial_health.operating_cashflow":
        return f"{v / 1e8:.2f} 亿元"
    if unit == "%":
        return f"{v}%"
    if unit:
        return f"{v} {unit}"
    return str(v)


# ── Agent ─────────────────────────────────────────────────────────────────────


class PeerComparisonAnalystAgent:
    """
    同行基本面对比 Agent。

    Args:
        llm: 实现了 BaseLLMClient.chat() 的 LLM 客户端。
        svc: PeerComparisonService 实例（不传则使用模块级单例）。
    """

    def __init__(
        self,
        llm: BaseLLMClient,
        svc: PeerComparisonService | None = None,
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
        生成 Markdown 同行基本面对比报告。

        Args:
            output_language: 报告输出语言代码（默认 zh-CN）。

        Raises:
            ValueError:   market / symbol 参数非法。
            RuntimeError: LLM 调用失败。
        """
        market = market.upper()
        if market not in {"CN", "HK"}:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{market}'")
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol 不能为空")

        log.info("PeerComparisonAnalystAgent: fetching peer data [%s/%s]", market, symbol)
        snapshot = self._svc.get_peer_fundamentals(market, symbol)

        if not isinstance(snapshot, dict) or "comparison_fields" not in snapshot:
            raise RuntimeError(
                f"peer_comparison_service 返回结构异常 [{market}/{symbol}]"
            )

        user_content = self._build_user_prompt(market, symbol, snapshot, output_language)

        log.info("PeerComparisonAnalystAgent: calling LLM [%s/%s]", market, symbol)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        return self._llm.chat(messages, temperature=0.3)

    async def analyze_async(
        self,
        db:              AsyncSession,
        market:          str,
        symbol:          str,
        output_language: str = "zh-CN",
    ) -> str:
        """
        Async 版同行对比分析。使用 DynamicPeerDiscoveryService 获取同行（PEER_MAP > dynamic_hot）。

        供支持 AsyncSession 的 router 调用。

        Args:
            output_language: 报告输出语言代码（默认 zh-CN）。

        Raises:
            ValueError:   market / symbol 参数非法。
            RuntimeError: LLM 调用失败 / 数据结构异常。
        """
        market = market.upper()
        if market not in {"CN", "HK"}:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{market}'")
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol 不能为空")

        log.info("PeerComparisonAnalystAgent.analyze_async: fetching peer data [%s/%s]", market, symbol)
        snapshot = await self._svc.get_peer_fundamentals_dynamic(db, market, symbol)

        if not isinstance(snapshot, dict) or "comparison_fields" not in snapshot:
            raise RuntimeError(
                f"get_peer_fundamentals_dynamic 返回结构异常 [{market}/{symbol}]"
            )

        user_content = self._build_user_prompt(market, symbol, snapshot, output_language)

        log.info("PeerComparisonAnalystAgent.analyze_async: calling LLM [%s/%s]", market, symbol)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        # LLM.chat 是同步方法，在线程池里运行避免阻塞 event loop
        return await asyncio.to_thread(self._llm.chat, messages, temperature=0.3)

    # ── 内部：构造用户 Prompt ─────────────────────────────────────────────────

    @staticmethod
    def _build_user_prompt(
        market: str,
        symbol: str,
        snapshot: dict,
        output_language: str = "zh-CN",
    ) -> str:
        cf       = snapshot.get("comparison_fields", {})
        dq       = snapshot.get("data_quality", {})
        target   = snapshot.get("target", {})
        peers    = snapshot.get("peers", [])

        available        = cf.get("available", [])
        missing_in_target = cf.get("missing_in_target", [])
        missing_in_all   = cf.get("missing_in_all", [])
        missing_in_any_peer = cf.get("missing_in_any_peer", [])
        candidate        = cf.get("candidate", [])

        target_name = target.get("name") or symbol
        market_cn   = "A股" if market == "CN" else "港股"

        # ── 特殊场景标志 ─────────────────────────────────────────────────────
        no_peers       = len(peers) == 0
        no_available   = len(available) == 0
        # HK 或 peers 业务差异大（PEER_MAP 注释中已标注"粗略对比"）
        is_hk          = market == "HK"

        # dynamic_hot 相关字段
        peer_source     = dq.get("peer_source", "unknown")
        fallback_reason = dq.get("fallback_reason")
        industry_name   = dq.get("industry_name")
        hot_stock_date  = dq.get("hot_stock_date")

        # ── 对比样本说明块 ────────────────────────────────────────────────────
        peer_names_str = "、".join(
            f"{p.get('name') or p.get('symbol')}（{p.get('market')}/{p.get('symbol')}）"
            for p in peers
        ) if peers else "（无）"

        # 行业 / 热门股快照信息（dynamic_hot 时展示）
        industry_line = ""
        if industry_name:
            industry_line = f"\n  申万行业：{industry_name}"
            if dq.get("industry_code"):
                industry_line += f"（{dq.get('industry_code')}）"
        hot_date_line = ""
        if hot_stock_date:
            hot_date_line = f"\n  Hot Score 快照日期：{hot_stock_date}"
            if dq.get("hot_score_version"):
                hot_date_line += f"（版本 {dq.get('hot_score_version')}）"

        # ── 报告期信息 ────────────────────────────────────────────────────────
        lrd_map = dq.get("latest_report_dates") or {}
        lrd_lines = []
        for k, v in lrd_map.items():
            if v:
                suffix = v[-5:]  # "-MM-DD"
                rtype  = ("年报" if suffix == "12-31"
                           else "一季报" if suffix == "03-31"
                           else "中报/半年报" if suffix == "06-30"
                           else "三季报" if suffix == "09-30"
                           else "未知类型")
                lrd_lines.append(f"    {k}: {v}（{rtype}）")
            else:
                lrd_lines.append(f"    {k}: 未知")
        lrd_block = "\n".join(lrd_lines) if lrd_lines else "    （无报告期信息）"

        # ── 字段可用性概览 ────────────────────────────────────────────────────
        avail_str    = "、".join(
            f"{_FIELD_META.get(f, (f,''))[0]}（{f}）" for f in available
        ) if available else "（无可用字段）"
        miss_all_str = "、".join(
            f"{_FIELD_META.get(f, (f,''))[0]}（{f}）" for f in missing_in_all
        ) if missing_in_all else "（无）"
        miss_tgt_str = "、".join(
            f"{_FIELD_META.get(f, (f,''))[0]}（{f}）" for f in missing_in_target
            if f not in missing_in_all
        ) or "（无）"
        miss_peer_str = "、".join(
            f"{_FIELD_META.get(f, (f,''))[0]}（{f}）" for f in missing_in_any_peer
        ) if missing_in_any_peer else "（无）"

        # ── 各字段横向数据表 ─────────────────────────────────────────────────
        all_entries = [target] + peers

        def _field_table(fields: list[str], label: str) -> str:
            if not fields:
                return f"  {label}：（无）"
            lines = [f"  {label}（只有这些字段允许横向对比，其余禁止）："]
            for field in fields:
                cn_name, _ = _FIELD_META.get(field, (field, ""))
                # 覆盖不完整标注
                incomplete = field in missing_in_any_peer
                note       = " [覆盖不完整 — 部分 peers 缺失，只能谨慎描述]" if incomplete else ""
                lines.append(f"  ▸ {cn_name}（{field}）{note}")
                for entry in all_entries:
                    role = "target" if entry is target else "peer"
                    ename = entry.get("name") or entry.get("symbol")
                    v     = _get_nested(entry.get("fundamentals") or {}, field)
                    lines.append(f"      {ename}（{role}）: {_fmt_value(field, v)}")
            return "\n".join(lines)

        def _missing_table(fields: list[str], label: str, note: str) -> str:
            if not fields:
                return f"  {label}：（无）"
            lines = [f"  {label}（{note}）："]
            for field in fields:
                cn_name, _ = _FIELD_META.get(field, (field, ""))
                lines.append(f"    - {cn_name}（{field}）")
            return "\n".join(lines)

        avail_table   = _field_table(available, "可用字段（available）")
        miss_all_table = _missing_table(
            missing_in_all,
            "全体缺失字段（missing_in_all）",
            "禁止评价 — target 和所有 peers 均为 null",
        )
        miss_tgt_table = _missing_table(
            [f for f in missing_in_target if f not in missing_in_all],
            "target 独有缺失字段（missing_in_target）",
            "禁止评价目标公司该字段 — target 自身为 null",
        )

        # ── 特殊场景警告 ──────────────────────────────────────────────────────
        warnings: list[str] = []

        if no_peers:
            if fallback_reason:
                warnings.append(
                    f"【暂无同行警告】当前股票无可用同行数据，原因：{fallback_reason}。"
                    "请生成「暂无同行」型报告，不得编造任何同行公司，不得虚构对比数据。"
                )
            else:
                warnings.append(
                    "【暂无同行配置警告】当前股票未在 PEER_MAP 中配置同行，"
                    "peers 列表为空。请生成「暂无同行配置」型报告，"
                    "不得编造任何同行公司，不得虚构对比数据。"
                )

        if no_available:
            warnings.append(
                "【无可比字段警告】comparison_fields.available 为空，"
                "当前缺少 target 和任何 peer 共同具备的字段。"
                "请生成「当前缺少可共同比较字段」型报告，"
                "明确说明原因，不得强行对比。"
            )

        if is_hk:
            warnings.append(
                "【港股对比口径警告】当前为港股（HK）分析，"
                "PEER_MAP 中的同行是互联网/科技龙头的粗略对比口径，"
                "业务形态差异较大。报告必须在「对比样本说明」中声明：「同行口径较粗，仅供参考」，"
                "不应做过强的横向估值或经营结论。"
            )

        if peer_source == "dynamic_hot":
            ind_str  = f"（申万行业：{industry_name}）" if industry_name else ""
            date_str = f"，快照日期 {hot_stock_date}" if hot_stock_date else ""
            warnings.append(
                f"【动态热门股同行警告{ind_str}】本次同行来自同一申万一级行业内的 Hot Score 热门股{date_str}，"
                "不代表严格的业务可比同行口径。"
                "Hot Score 基于成交额（权重 0.7）与涨跌幅绝对值（权重 0.3）加权计算，"
                "代表市场关注度，不代表基本面质量或投资价值。"
                "报告必须在「对比样本说明」中明确说明此口径限制。"
                "禁止使用「更优质」「更值得投资」「更值得买入」「行业龙头」等强结论，"
                "除非输入财务数据（ROE、毛利率等）明确支持该判断。"
                "不得将 Hot Score 排名高解读为「基本面更强」或「更有投资价值」。"
            )

        warning_block = "\n\n".join(warnings) if warnings else ""

        # ── data_quality 说明 ─────────────────────────────────────────────────
        svc_message   = (dq.get("message") or "").strip()
        missing_peers_str = "、".join(dq.get("missing_peers") or []) or "无"

        lang_instruction = build_output_language_instruction(output_language)

        return f"""\
请对以下同行基本面数据进行分析，严格遵守系统提示中的所有禁止事项。
{warning_block}

【对比样本】
  目标股：{target_name}（{market_cn} {market}/{symbol}）
  同行：{peer_names_str}
  对比数据源：{peer_source}{industry_line}{hot_date_line}
  获取失败的同行：{missing_peers_str}

【报告期（必须在报告中披露）】
{lrd_block}

【字段可用性概览】
  可用字段（available，可以横向对比）：{avail_str}
  全体缺失（missing_in_all，禁止评价）：{miss_all_str}
  target 独有缺失（missing_in_target，禁止评价目标股）：{miss_tgt_str}
  部分 peer 缺失（missing_in_any_peer，谨慎描述）：{miss_peer_str}

【横向对比数据（只允许分析 available 字段）】

{avail_table}

{miss_all_table}

{miss_tgt_table}

【data_quality 说明】
  peer_source: {dq.get('peer_source', '未知')}
{('  message: ' + svc_message) if svc_message else ''}

请严格按照系统提示规定的 Markdown 结构输出报告，\
章节标题不得更改，不得新增或删除章节。\
{lang_instruction}"""
