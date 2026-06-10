"""
PeerComparisonService — 同行基本面对比数据服务（Phase 1）。

设计原则：
  - Phase 1 使用手动 PEER_MAP，不做自动行业识别。
  - 不调用 LLM，不写 PeerComparisonAgent。
  - 直接复用 FundamentalDataService.get_fundamentals()，不走 HTTP。
  - 单只 peer 失败不阻塞整体响应；失败项记录在 data_quality.missing_peers。
  - comparison_fields 带动态可用性标记，防止 Agent 误用空字段做对比。

Phase 2 升级路线（预留，不实现）：
  - Phase 3 接入 company.industry 后，可在 _resolve_peers() 中加自动行业识别。
  - PEER_MAP 作为 override，优先级高于自动识别。
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# ── 候选对比字段（固定，Phase 2 可扩展）─────────────────────────────────────────

_CANDIDATE_FIELDS: list[str] = [
    "valuation.pe",
    "valuation.pb",
    "profitability.roe",
    "profitability.gross_margin",
    "profitability.net_margin",
    "growth.revenue_growth_yoy",
    "growth.net_profit_growth_yoy",
    "financial_health.debt_ratio",
    "financial_health.operating_cashflow",
]

# ── 手动同行映射表（Phase 1）────────────────────────────────────────────────────
#
# 格式: (market, symbol) → [(market, symbol), ...]
# 升级路线: Phase 3 行业字段就绪后，可改为自动识别 + PEER_MAP 作为 override。

PEER_MAP: dict[tuple[str, str], list[tuple[str, str]]] = {
    # 贵州茅台 — 白酒板块龙头对比
    ("CN", "600519"): [
        ("CN", "000858"),  # 五粮液
        ("CN", "000568"),  # 泸州老窖
        ("CN", "600809"),  # 山西汾酒
        ("CN", "002304"),  # 洋河股份
    ],

    # 腾讯控股 Phase 1 peers（HK symbol 统一 5 位补零格式）:
    # 互联网平台/科技龙头粗略对比口径。
    # 阿里、美团、网易、百度与腾讯业务形态并不完全一致，
    # 因此后续 PeerComparisonAgent 必须提示「同行口径较粗，仅供参考」，
    # 不应做过强的横向估值或经营结论。
    ("HK", "00700"): [
        ("HK", "09988"),  # 阿里巴巴-W
        ("HK", "03690"),  # 美团-W
        ("HK", "09999"),  # 网易-S
        ("HK", "09888"),  # 百度集团-SW
    ],
}


def _normalize_symbol(market: str, symbol: str) -> str:
    """归一化股票代码。HK 统一为 5 位补零格式（700 → 00700）。"""
    if market.upper() == "HK":
        return symbol.strip().lstrip("0").zfill(5)
    return symbol.strip()

# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _get_nested(snapshot: dict, path: str) -> Any:
    """
    从嵌套 fundamentals 快照中按点分路径取值。

    示例：
        _get_nested(snap, "profitability.roe")  → float | None
        _get_nested(snap, "valuation.pe")       → float | None

    缺失层级或字段时返回 None，不抛异常。
    """
    section, _, field = path.partition(".")
    if not field:
        return snapshot.get(section)
    sub = snapshot.get(section)
    if not isinstance(sub, dict):
        return None
    return sub.get(field)


def _analyze_comparison_fields(
    target_entry: dict,
    peer_entries: list[dict],
    candidate_fields: list[str],
) -> dict:
    """
    分析每个候选字段在 target 和 peers 中的可用性，返回带标记的结构。

    字段含义：
      candidate       — 固定候选对比字段列表
      available       — target ✓ 且 ≥1 peer ✓（可用于对比）
      missing_in_target  — target 本身为 null
      missing_in_all  — target 和所有 peers 均为 null（完全不能用于对比）
      missing_in_any_peer — target ✓ 但 ≥1 peer 为 null（覆盖不完整，谨慎对比）

    注意：
      - available 和 missing_in_any_peer 可同时成立（部分 peers 有值，部分无）
      - peer_entries 为空时：available=[], missing_in_any_peer=[]
    """
    target_fund = target_entry.get("fundamentals") or {}

    available:           list[str] = []
    missing_in_target:   list[str] = []
    missing_in_all:      list[str] = []
    missing_in_any_peer: list[str] = []

    for field in candidate_fields:
        target_val  = _get_nested(target_fund, field)
        peer_vals   = [
            _get_nested((e.get("fundamentals") or {}), field)
            for e in peer_entries
        ]

        target_has      = target_val is not None
        peers_with_val  = [v for v in peer_vals if v is not None]
        any_peer_has    = bool(peers_with_val)

        # missing_in_target: target 本身缺失
        if not target_has:
            missing_in_target.append(field)

        # missing_in_all: target 和所有 peers 都缺失
        if not target_has and not any_peer_has:
            missing_in_all.append(field)

        # available: target 有值，且至少一个 peer 有值
        if target_has and any_peer_has:
            available.append(field)

        # missing_in_any_peer: target 有值，但至少一个 peer 缺失
        # （含"target 有值但所有 peers 无值"的极端情况）
        if target_has and len(peers_with_val) < len(peer_entries):
            missing_in_any_peer.append(field)

    return {
        "candidate":          list(candidate_fields),
        "available":          available,
        "missing_in_target":  missing_in_target,
        "missing_in_all":     missing_in_all,
        "missing_in_any_peer": missing_in_any_peer,
    }


def _build_stock_entry(market: str, symbol: str, snapshot: dict) -> dict:
    """将 fundamentals 快照包装为统一的 stock entry dict。"""
    name = (snapshot.get("company") or {}).get("name")
    return {
        "market":       market,
        "symbol":       symbol,
        "name":         name,
        "fundamentals": snapshot,
    }


def _build_message(
    peer_specs:           list[tuple[str, str]],
    missing_peers:        list[str],
    missing_in_all:       list[str],
    available:            list[str],
) -> str | None:
    """
    根据数据质量情况生成 data_quality.message。
    无问题时返回 None。
    """
    if not peer_specs:
        return "暂无同行配置，无法进行同行对比。"

    parts: list[str] = []

    if missing_peers:
        parts.append(
            f"以下同行数据获取失败，已跳过：{', '.join(missing_peers)}。"
        )

    if missing_in_all:
        field_str = "、".join(missing_in_all)
        parts.append(
            f"以下字段在 target 和所有 peers 中均缺失，"
            f"不适合用于同行对比：{field_str}。"
        )

    if not available:
        parts.append(
            "当前 target 与 peers 缺少可共同比较的基本面字段，"
            "本结果仅返回数据，不建议生成强同行对比结论。"
        )

    return " ".join(parts) if parts else None


# ── Service ───────────────────────────────────────────────────────────────────


class PeerComparisonService:
    """
    同行基本面对比服务（Phase 1：手动 PEER_MAP）。

    使用方式（router 层）：
        specs   = peer_comparison_service.get_peer_specs(market, symbol)
        results = await asyncio.gather(
            asyncio.to_thread(fundamental_data_service.get_fundamentals, market, symbol),
            *[asyncio.to_thread(fundamental_data_service.get_fundamentals, m, s)
              for m, s in specs],
            return_exceptions=True,
        )
        target_snap  = results[0]
        peer_results = list(results[1:])
        response = peer_comparison_service.assemble_response(
            market, symbol, target_snap, specs, peer_results
        )
    """

    def get_peer_specs(self, market: str, symbol: str) -> list[tuple[str, str]]:
        """
        返回该股票的同行 (market, symbol) 列表。
        未在 PEER_MAP 中配置时返回空列表（不报错）。
        HK symbol 查询前归一化为 5 位补零格式（700 / 00700 均可命中）。
        """
        mkt = market.upper()
        sym = _normalize_symbol(mkt, symbol)
        return list(PEER_MAP.get((mkt, sym), []))

    def get_peer_fundamentals(self, market: str, symbol: str) -> dict:
        """
        同步版本的全流程同行对比，供 PeerComparisonAnalystAgent 直接调用。

        内部用 ThreadPoolExecutor 并发拉取 target + peers（对标 router 层的
        asyncio.gather），FundamentalDataService 内有 TTL=3600s 缓存，
        命中缓存时几乎零延迟。
        """
        # 延迟导入避免循环依赖
        from app.services.fundamental_data_service import fundamental_data_service

        market = market.upper()
        peer_specs = self.get_peer_specs(market, symbol)
        all_specs  = [(market, symbol)] + peer_specs

        results_map: dict[tuple[str, str], Any] = {}

        with ThreadPoolExecutor(max_workers=min(len(all_specs), 6)) as pool:
            future_to_spec = {
                pool.submit(fundamental_data_service.get_fundamentals, m, s): (m, s)
                for m, s in all_specs
            }
            for future in as_completed(future_to_spec, timeout=120):
                spec = future_to_spec[future]
                try:
                    results_map[spec] = future.result()
                except Exception as exc:
                    results_map[spec] = exc

        target_snapshot = results_map.get((market, symbol))
        # get_fundamentals 正常不抛异常（返回空快照），极端情况下做一次直接调用兜底
        if isinstance(target_snapshot, Exception) or target_snapshot is None:
            log.warning(
                "get_peer_fundamentals: target 拉取失败 [%s/%s]，尝试直接调用。",
                market, symbol,
            )
            from app.services.fundamental_data_service import fundamental_data_service
            target_snapshot = fundamental_data_service.get_fundamentals(market, symbol)

        peer_results = [results_map.get(spec, RuntimeError(f"fetch failed {spec}"))
                        for spec in peer_specs]

        return self.assemble_response(
            market, symbol, target_snapshot, peer_specs, peer_results
        )

    def assemble_response(
        self,
        market:          str,
        symbol:          str,
        target_snapshot: dict,
        peer_specs:      list[tuple[str, str]],
        peer_results:    list[Any],  # dict | Exception，与 peer_specs 顺序对应
    ) -> dict:
        """
        将 target + peer 快照组装为完整同行对比响应。

        - 单只 peer 失败（Exception）：跳过，记入 missing_peers
        - null 字段保持 null，不填充默认值
        - comparison_fields 带动态可用性标记
        """
        target_entry = _build_stock_entry(market, symbol, target_snapshot)

        peer_entries:  list[dict] = []
        missing_peers: list[str]  = []

        for (pm, ps), result in zip(peer_specs, peer_results):
            key = f"{pm}/{ps}"
            if isinstance(result, Exception):
                log.warning(
                    "peer fundamentals failed [%s/%s]: %s", pm, ps, result
                )
                missing_peers.append(key)
            else:
                peer_entries.append(_build_stock_entry(pm, ps, result))

        # ── comparison_fields 动态可用性分析 ─────────────────────────────────
        cf = _analyze_comparison_fields(target_entry, peer_entries, _CANDIDATE_FIELDS)

        # ── data_quality ──────────────────────────────────────────────────────
        latest_report_dates: dict[str, str | None] = {}
        missing_fields_map:  dict[str, list[str]]  = {}

        for entry in [target_entry] + peer_entries:
            k    = f"{entry['market']}/{entry['symbol']}"
            fund = entry.get("fundamentals") or {}
            dq   = fund.get("data_quality") or {}
            latest_report_dates[k] = dq.get("latest_report_date")
            missing_fields_map[k]  = list(dq.get("missing_fields") or [])

        message = _build_message(
            peer_specs,
            missing_peers,
            cf["missing_in_all"],
            cf["available"],
        )

        return {
            "market":  market,
            "symbol":  symbol,
            "target":  target_entry,
            "peers":   peer_entries,
            "comparison_fields": cf,
            "data_quality": {
                "peer_source":          "manual_map",
                "latest_report_dates":  latest_report_dates,
                "missing_peers":        missing_peers,
                "missing_fields":       missing_fields_map,
                "message":              message,
            },
        }


    async def get_peer_fundamentals_dynamic(
        self,
        db:     AsyncSession,
        market: str,
        symbol: str,
    ) -> dict:
        """
        Async 版同行对比全流程，使用 DynamicPeerDiscoveryService。

        优先级（由 DynamicPeerDiscoveryService 内部处理）：
          1. PEER_MAP 手动 override（任何市场）
          2. CN 动态行业 Hot Top5
          3. 非 CN 且无 PEER_MAP → peers=[]
          4. CN 但无行业映射 → peers=[]
          5. CN 有行业但无热门股快照 → peers=[]

        返回结构与 assemble_response() 相同，data_quality 中额外包含：
          industry_code, industry_name, hot_stock_date, hot_score_version, fallback_reason
        """
        # 延迟导入避免循环依赖
        from app.services.dynamic_peer_discovery_service import dynamic_peer_discovery_service
        from app.services.fundamental_data_service import fundamental_data_service

        market = market.upper()
        symbol = symbol.strip()

        # ── Step 1: 发现同行 ─────────────────────────────────────────────────
        discovery = await dynamic_peer_discovery_service.discover_peers(db, market, symbol)

        # ── Step 2: 提取 peer_specs ──────────────────────────────────────────
        peer_specs: list[tuple[str, str]] = [
            (p["market"], p["symbol"]) for p in discovery.get("peers", [])
        ]

        # ── Step 3: 并发拉取基本面 ────────────────────────────────────────────
        all_specs = [(market, symbol)] + peer_specs
        all_results = await asyncio.gather(
            *[
                asyncio.to_thread(fundamental_data_service.get_fundamentals, m, s)
                for m, s in all_specs
            ],
            return_exceptions=True,
        )

        target_result = all_results[0]
        peer_results  = list(all_results[1:])

        # target 极端兜底（get_fundamentals 正常不抛异常）
        if isinstance(target_result, Exception) or target_result is None:
            log.warning(
                "get_peer_fundamentals_dynamic: target fetch failed [%s/%s]: %s",
                market, symbol, target_result,
            )
            target_result = await asyncio.to_thread(
                fundamental_data_service.get_fundamentals, market, symbol
            )

        # ── Step 4: 组装基础响应 ─────────────────────────────────────────────
        response = self.assemble_response(market, symbol, target_result, peer_specs, peer_results)

        # ── Step 5: 将 discovery data_quality 合并进响应 ─────────────────────
        disc_dq       = discovery.get("data_quality", {})
        disc_industry = discovery.get("industry")

        dq = response["data_quality"]
        dq["peer_source"]       = disc_dq.get("peer_source", "none")
        dq["industry_code"]     = disc_industry["industry_code"] if disc_industry else None
        dq["industry_name"]     = disc_industry["industry_name"] if disc_industry else None
        dq["hot_stock_date"]    = disc_dq.get("hot_stock_date")
        dq["hot_score_version"] = disc_dq.get("hot_score_version")
        dq["fallback_reason"]   = disc_dq.get("fallback_reason")

        # message 合并：discovery message 为同行来源说明；service message 为数据获取问题说明
        disc_msg = (disc_dq.get("message") or "").strip()
        svc_msg  = (dq.get("message") or "").strip()
        # "暂无同行配置" 是 assemble_response 的通用占位，discovery message 更具体，直接替换
        _generic_no_peer = "暂无同行配置，无法进行同行对比。"
        if disc_msg and svc_msg and svc_msg != _generic_no_peer:
            dq["message"] = f"{disc_msg} {svc_msg}"
        elif disc_msg:
            dq["message"] = disc_msg
        # else: 保留 svc_msg（discovery 无 message 时不覆盖）

        return response


peer_comparison_service = PeerComparisonService()
