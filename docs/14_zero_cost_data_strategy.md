# Zero-Cost Public Data Source Strategy (Phase 6A)

## Overview

Phase 6A introduces a **free data mode** that allows the TradingAgents financial research system to operate without any paid API subscriptions. When `DATA_MODE=free` is set, the system bypasses Tushare Pro entirely and uses public, zero-cost data sources.

## Data Sources

| Source | Cost | Coverage | Primary Use |
|--------|------|----------|-------------|
| **BaoStock** | Free | A-shares only | Financial ratios (quarterly) |
| **AkShare** | Free | CN/HK/US | Quote snapshots, cash flow |
| **Tushare Pro** | Paid | CN/HK | All financial statements (standard mode) |

### BaoStock Capabilities

BaoStock (`pip install baostock`) provides 6 financial data categories:

| Category | BaoStock API | Fields Available |
|----------|-------------|-----------------|
| 盈利能力 | `query_profit_data` | gpMargin, npMargin, roeAvg, epsTTM |
| 成长能力 | `query_growth_data` | YOYNI, YOYEPSBasic, YOYEquity, YOYAsset |
| 偿债能力 | `query_balance_data` | currentRatio, quickRatio, cashRatio, liabilityToAsset |
| 营运能力 | `query_operation_data` | NRTurnRatio, NRTurnDays, INVTurnRatio, CATurnRatio, AssetTurnRatio |
| 现金流量 | `query_cash_flow_data` | CFOToOR, CFOToNP, CFOToGr, ebitToInterest |
| 杜邦分析 | `query_dupont_data` | dupontROE, dupontPnitoni, dupontNitogr, dupontAssetTurn, dupontAssetStoEquity, dupontTaxBurden, dupontIntburden |

**Unit convention (validated 2026-07-06):** BaoStock returns profitability/growth ratios as **decimals** (0.52 = 52%). The `baostock_client` maps to internal schema with ×100 multiplication for `_pct` fields. Solvency ratios (current_ratio, quick_ratio) are returned as natural numbers and need no conversion.

**Limitations:** BaoStock does not provide real-time quotes, absolute monetary values (only ratios), HK/US stocks, or some advanced fields like ROIC, equity multiplier breakdown.

## Configuration

```env
# Enable free data mode (skips Tushare entirely)
DATA_MODE=free

# Enable BaoStock as primary source in free mode
ENABLE_BAOSTOCK=true

# Enable AkShare as fallback (optional, also used in standard mode)
ENABLE_AKSHARE=true

# Standard mode (default) — uses Tushare Pro
DATA_MODE=standard
```

## Fallback Chain

### Standard Mode (default)
```
Tushare Pro → AkShare (if ENABLE_AKSHARE=true) → err_envelope
```

### Free Mode
```
BaoStock (if ENABLE_BAOSTOCK=true) → AkShare (if ENABLE_AKSHARE=true) → err_envelope
```

The `DataEnvelope` contract is always honored: HTTP 200 is always returned. Failures surface as `partial=True` + `errors[]` in the response.

## Module Availability by Data Mode

Modules are tagged with a `data_mode` field in MODULE_CATALOG:

| `data_mode` value | Meaning |
|---|---|
| `any` | Available in all modes |
| `free_ok` | Available in free mode via BaoStock/AkShare |
| `standard_only` | Requires Tushare Pro (hidden in free mode) |

Use `get_available_modules(data_mode)` to get the filtered list.

### Modules Unavailable in Free Mode (`standard_only`)

- `announcements` — requires `tushare.forecast` and `tushare.express` APIs
- `analyst_ratings` — same dependency

### Modules Available in Free Mode (`free_ok`)

- `profitability` — gpMargin, npMargin, roeAvg (roa/roic not available)
- `growth` — YOYNI, YOYEPSBasic (revenue absolute values not available)
- `solvency` — currentRatio, quickRatio, cashRatio, liabilityToAsset
- `operation_capability` — NRTurnRatio, INVTurnRatio, AssetTurnRatio (payable_turn not available)
- `cashflow_quality` — CFOToOR (收现比), CFOToOI (净现比近似) only
- `dupont` — dupontROE, dupontNPI, dupontAssTurn, dupontAssMul (debt_to_assets not available)

## Frontend Behavior

When `source.actual` is `"baostock"` or `"akshare"`, the `DataSourceBanner` component shows a `free_source_limited` banner:

> "当前为公开免费数据源（BaoStock/AkShare），部分财务字段可能缺失或口径不一致，数据仅供参考。"

When a module's `data.removed === true`, it shows a `module_removed` banner.

## Report PDF Feature

A separate optional feature (`ENABLE_REPORT_PDF=true`) enables indexing of annual report PDFs from public sources. The `report_documents` table stores metadata; actual PDF collection requires a separate ETL job.

## Code Structure

```
backend/
  app/
    core/config.py                    — data_mode, enable_baostock, enable_report_pdf settings
    datasource/
      baostock_client.py              — BaoStockClient (Phase 6A, NEW)
    tools/fundamental/
      base.py                         — fetch_baostock(), _fetch_free_mode(), updated fetch_with_fallback()
      profitability.py                — fetch_baostock() mapping
      growth.py                       — fetch_baostock() mapping
      solvency.py                     — fetch_baostock() mapping
      operation_capability.py         — fetch_baostock() mapping
      cashflow_quality.py             — fetch_baostock() mapping
      dupont.py                       — fetch_baostock() mapping
      __init__.py                     — data_mode field, get_available_modules()
    models/
      report_document.py              — ReportDocument ORM model (Phase 6A, NEW)
    routers/
      fundamentals.py                 — GET /report_documents endpoint
  alembic/versions/
    2026_07_06_0001-c1d2e3f4a5b6_add_report_documents.py
frontend/
  src/components/fundamentals/
    DataSourceBanner.vue              — free_source_limited + module_removed banner types
```
