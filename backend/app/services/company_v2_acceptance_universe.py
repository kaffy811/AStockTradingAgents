"""
app/services/company_v2_acceptance_universe.py — Phase 6T-E 跨股票验收样本定义

统一定义跨股票真实验收所使用的股票清单及每只股票的验收期望。
仅用于验收脚本和测试，不影响生产接口行为。

安全原则：
- 不提供投资建议
- expected_* 字段仅为验收下限，不用于伪造数据
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# special_accounting_type 允许值
SPECIAL_ACCOUNTING_TYPES = frozenset({
    "general_industrial",
    "bank",
    "insurer",
    "securities",
    "real_estate",
    "utility",
    "unknown",
})


@dataclass(frozen=True)
class AcceptanceStock:
    symbol: str
    market: str
    expected_exchange: str            # "上交所" | "深交所"
    expected_industry_type: str       # 描述性行业类型
    expected_min_annual_periods: int  # 期望最少年度期数（真实下限，不足即记录）
    expected_min_quarterly_periods: int
    special_accounting_type: str = "general_industrial"
    notes: str = ""

    def __post_init__(self) -> None:
        if self.special_accounting_type not in SPECIAL_ACCOUNTING_TYPES:
            raise ValueError(
                f"invalid special_accounting_type: {self.special_accounting_type!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Phase 6T-E 验收样本（8 只，覆盖不同交易所/行业/上市年限/会计口径）
ACCEPTANCE_UNIVERSE: list[AcceptanceStock] = [
    AcceptanceStock(
        symbol="600519", market="CN",
        expected_exchange="上交所",
        expected_industry_type="consumer",
        expected_min_annual_periods=8,
        expected_min_quarterly_periods=20,
        special_accounting_type="general_industrial",
        notes="贵州茅台：上市早（2001），高盈利高毛利消费行业",
    ),
    AcceptanceStock(
        symbol="000725", market="CN",
        expected_exchange="深交所",
        expected_industry_type="manufacturing_cyclical",
        expected_min_annual_periods=8,
        expected_min_quarterly_periods=20,
        special_accounting_type="general_industrial",
        notes="京东方A：制造业，周期性明显，历史数据长（1996）",
    ),
    AcceptanceStock(
        symbol="601686", market="CN",
        expected_exchange="上交所",
        expected_industry_type="manufacturing",
        expected_min_annual_periods=5,
        expected_min_quarterly_periods=15,
        special_accounting_type="general_industrial",
        notes="友发集团：已完成报告链路验证的基准股票（2020-12 上市）",
    ),
    AcceptanceStock(
        symbol="300750", market="CN",
        expected_exchange="深交所",
        expected_industry_type="high_growth_manufacturing",
        expected_min_annual_periods=5,
        expected_min_quarterly_periods=15,
        special_accounting_type="general_industrial",
        notes="宁德时代：创业板，2018 上市，高成长制造业",
    ),
    AcceptanceStock(
        symbol="688981", market="CN",
        expected_exchange="上交所",
        expected_industry_type="tech_manufacturing",
        expected_min_annual_periods=4,
        expected_min_quarterly_periods=12,
        special_accounting_type="general_industrial",
        notes="中芯国际：科创板，2020 上市，会计指标和估值特点不同",
    ),
    AcceptanceStock(
        symbol="601318", market="CN",
        expected_exchange="上交所",
        expected_industry_type="insurance",
        expected_min_annual_periods=6,
        expected_min_quarterly_periods=15,
        special_accounting_type="insurer",
        notes="中国平安：金融行业，财务口径特殊，部分通用工业指标不适用",
    ),
    AcceptanceStock(
        symbol="000001", market="CN",
        expected_exchange="深交所",
        expected_industry_type="bank",
        expected_min_annual_periods=6,
        expected_min_quarterly_periods=15,
        special_accounting_type="bank",
        notes="平安银行：银行业，流动比率/存货周转不应按普通制造业解释",
    ),
    AcceptanceStock(
        symbol="601728", market="CN",
        expected_exchange="上交所",
        expected_industry_type="telecom_utility",
        expected_min_annual_periods=3,
        expected_min_quarterly_periods=8,
        special_accounting_type="utility",
        notes="中国电信：2021-08 A股上市，不足5年，用于短历史与空图状态测试",
    ),
]

ACCEPTANCE_SYMBOLS: list[str] = [s.symbol for s in ACCEPTANCE_UNIVERSE]

_BY_SYMBOL: dict[str, AcceptanceStock] = {s.symbol: s for s in ACCEPTANCE_UNIVERSE}


def get_acceptance_stock(symbol: str) -> AcceptanceStock | None:
    """按代码查询验收样本定义（不存在返回 None）。"""
    return _BY_SYMBOL.get(str(symbol).split(".")[0])


def get_special_accounting_type(symbol: str) -> str:
    """返回股票的特殊会计口径类型；未定义时返回 unknown。"""
    stock = get_acceptance_stock(symbol)
    return stock.special_accounting_type if stock else "unknown"
