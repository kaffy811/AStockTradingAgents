"""
app/services/field_compute_service.py — 字段级计算补齐（Phase 6N-6）

职责：
  - 接受一组 raw_fields（{field_name: value}），按 CORE_FIELDS 中的 formula/dependencies
    依次尝试计算所有 computed 字段；
  - 依赖字段缺失时返回 DataField.missing(reason_code=FIELD_MISSING_DEPENDENCY)；
  - 除 / 0 返回 DataField.missing(reason_code=FIELD_MISSING)；
  - 计算成功返回 DataField.computed(...)；
  - 不修改 raw_fields，只返回新计算字段集合。

使用方式：
    raw = {
        "latest_price": 1780.0,
        "total_share":  12581.0,   # 万股
        "net_profit":   23680e6,
        "revenue":      126e9,
        "operating_cashflow": 31e9,
    }
    results = FieldComputeService.compute_all(raw, as_of="2024-01-15")
    for df in results.values():
        print(df.field_name, df.value, df.status)
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.core_schema import CORE_FIELDS, FieldSpec, get_computed_fields
from app.models.data_field import DataField, DataFieldStatus, ReasonCode

log = logging.getLogger(__name__)


class FieldComputeService:
    """
    按 core_schema 中 computed=True 的字段定义，自动补齐可计算字段。

    所有方法均为静态方法，无状态，适合在任意上下文中调用。
    """

    # ── 字段计算函数映射 ──────────────────────────────────────────────────────
    # key = field_name，value = (deps, formula_fn)
    # formula_fn(deps_dict) → float | None（返回 None 表示不可计算）

    _FORMULAS: dict[str, tuple[list[str], Any]] = {}  # 由 _register_formulas() 填充

    @classmethod
    def _init_formulas(cls) -> None:
        if cls._FORMULAS:
            return  # already initialized

        def safe_div(a, b):
            if a is None or b is None or b == 0:
                return None
            return a / b

        cls._FORMULAS = {

            # 行情
            "change_pct": (
                ["close", "pre_close"],
                lambda d: safe_div(d["close"], d["pre_close"]) - 1 if d["close"] and d["pre_close"] else None,
            ),

            # 估值
            "market_cap": (
                ["latest_price", "total_share"],
                lambda d: d["latest_price"] * d["total_share"] * 10000
                if d["latest_price"] and d["total_share"] else None,
                # total_share 单位万股 → 元
            ),

            # 财务指标
            "gross_margin": (
                ["gross_profit", "revenue"],
                lambda d: safe_div(d["gross_profit"], d["revenue"]),
            ),
            "net_margin": (
                ["net_profit", "revenue"],
                lambda d: safe_div(d["net_profit"], d["revenue"]),
            ),
            "debt_ratio": (
                ["total_liabilities", "total_assets"],
                lambda d: safe_div(d["total_liabilities"], d["total_assets"]),
            ),
            "current_ratio": (
                ["current_assets", "current_liabilities"],
                lambda d: safe_div(d["current_assets"], d["current_liabilities"]),
            ),
            "asset_turnover": (
                ["revenue", "total_assets"],
                lambda d: safe_div(d["revenue"], d["total_assets"]),
            ),
            "ocf_to_np": (
                ["operating_cashflow", "net_profit"],
                lambda d: safe_div(d["operating_cashflow"], d["net_profit"]),
            ),
            "roe": (
                ["net_profit_parent", "total_equity"],
                lambda d: safe_div(d["net_profit_parent"], d["total_equity"]) * 100
                if d["net_profit_parent"] and d["total_equity"] else None,
            ),
            "roa": (
                ["net_profit", "total_assets"],
                lambda d: safe_div(d["net_profit"], d["total_assets"]) * 100
                if d["net_profit"] and d["total_assets"] else None,
            ),
            "dupont_equity_multiplier": (
                ["total_assets", "total_equity"],
                lambda d: safe_div(d["total_assets"], d["total_equity"]),
            ),
            "gross_profit": (
                ["revenue", "cost_of_revenue"],
                lambda d: d["revenue"] - d["cost_of_revenue"]
                if d["revenue"] is not None and d["cost_of_revenue"] is not None else None,
            ),
        }

    @classmethod
    def compute_all(
        cls,
        raw_fields: dict[str, Any],
        *,
        as_of: str = "",
        fiscal_period: str = "",
    ) -> dict[str, DataField]:
        """
        对 raw_fields 中的原始值，尝试计算所有 computed 字段。

        Args:
            raw_fields:    {field_name: value}，值为 None 表示该字段未获取到
            as_of:         数据对应日期
            fiscal_period: 财报期（如 20231231）

        Returns:
            {field_name: DataField}，仅包含 computed 字段；
            原始字段不在返回结果中。
        """
        cls._init_formulas()
        result: dict[str, DataField] = {}

        # 合并 raw_fields 和已计算字段（支持链式依赖）
        merged = dict(raw_fields)

        for spec in get_computed_fields():
            field_name = spec.name
            if field_name not in cls._FORMULAS:
                # No formula implementation — mark as not_implemented
                result[field_name] = DataField.missing(
                    field_name,
                    reason_code=ReasonCode.NOT_IMPLEMENTED,
                )
                continue

            deps, formula_fn = cls._FORMULAS[field_name]

            # Check all dependencies present
            missing_deps = [d for d in deps if merged.get(d) is None]
            if missing_deps:
                result[field_name] = DataField(
                    field_name=field_name,
                    value=None,
                    status=DataFieldStatus.MISSING,
                    source="computed",
                    formula=spec.formula,
                    dependencies=spec.dependencies,
                    reason_code=ReasonCode.FIELD_MISSING_DEPENDENCY,
                    provider_errors={d: "missing" for d in missing_deps},
                    as_of=as_of,
                    fiscal_period=fiscal_period,
                )
                continue

            try:
                deps_dict = {d: merged.get(d) for d in deps}
                value = formula_fn(deps_dict)
            except Exception as exc:
                log.warning("compute %s formula error: %r", field_name, exc)
                value = None

            if value is None:
                result[field_name] = DataField(
                    field_name=field_name,
                    value=None,
                    status=DataFieldStatus.MISSING,
                    source="computed",
                    formula=spec.formula,
                    dependencies=spec.dependencies,
                    reason_code=ReasonCode.FIELD_MISSING,
                    as_of=as_of,
                    fiscal_period=fiscal_period,
                )
            else:
                df = DataField.computed(
                    field_name=field_name,
                    value=value,
                    formula=spec.formula,
                    dependencies=spec.dependencies,
                    as_of=as_of,
                    fiscal_period=fiscal_period,
                )
                result[field_name] = df
                # Make computed value available for downstream dependencies
                merged[field_name] = value

        return result

    @classmethod
    def compute_one(
        cls,
        field_name: str,
        raw_fields: dict[str, Any],
        *,
        as_of: str = "",
        fiscal_period: str = "",
    ) -> DataField:
        """Compute a single field by name. Returns DataField.missing if not computable."""
        cls._init_formulas()
        all_computed = cls.compute_all(raw_fields, as_of=as_of, fiscal_period=fiscal_period)
        return all_computed.get(
            field_name,
            DataField.missing(field_name, ReasonCode.NOT_IMPLEMENTED),
        )

    @classmethod
    def completeness_score(cls, fields: dict[str, DataField]) -> float:
        """
        计算字段完整率（有值的字段数 / 总字段数）。
        返回 0.0 ~ 1.0。
        """
        if not fields:
            return 0.0
        has_value = sum(1 for f in fields.values() if f.has_value)
        return has_value / len(fields)
