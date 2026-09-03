# Modules Unavailable in Free Data Mode (Phase 6A)

This document lists the fundamental analysis modules that require paid Tushare Pro API access and are therefore not available when `DATA_MODE=free`.

## `standard_only` Modules

### `announcements` — 近期公告摘要

| Property | Value |
|----------|-------|
| `module_key` | `announcements` |
| `data_mode` | `standard_only` |
| `group` | 事件观点 |
| `status` | available (standard) / unavailable (free) |
| Aliases | `events` |

**Why unavailable in free mode:**

This module calls two Tushare Pro-only APIs:
- `tushare.forecast` — 业绩预告（需积分 ≥ 2000）
- `tushare.express` — 业绩快报（需积分 ≥ 2000）

These APIs are restricted to paid/high-credit Tushare accounts and return `权限不足` with free-tier tokens.

**No public alternative exists** for structured performance pre-announcement data. CNINFO provides PDF announcements, but structured field extraction requires the `ENABLE_REPORT_PDF` pipeline.

---

### `analyst_ratings` — 研报评级汇总

| Property | Value |
|----------|-------|
| `module_key` | `analyst_ratings` |
| `data_mode` | `standard_only` |
| `group` | 事件观点 |
| `status` | available (standard) / unavailable (free) |
| Aliases | `forecast_rating`, `rating` |

**Why unavailable in free mode:**

This module also depends on `tushare.forecast` and `tushare.express` for the underlying data that it maps to sentiment/type classifications. Despite the name suggesting "analyst ratings," the current implementation is based on Tushare's performance forecast data, not actual securities research reports.

**Note:** True analyst buy/sell ratings from securities firms are not available through any free public API. This limitation exists across all zero-cost data sources.

---

## Future Roadmap

When `ENABLE_REPORT_PDF=true` and the PDF collection pipeline is running, structured data from annual/semi-annual reports becomes available via the `report_documents` table. This could partially substitute for some `announcements` data in the future.

## Frontend Handling

In free mode, the `get_available_modules("free")` API will exclude `standard_only` modules from the module list. The frontend should:
1. Not render tabs for excluded modules
2. If a user navigates to a module URL directly, the DataSourceBanner shows `module_removed` banner: "该模块在当前数据源配置下不可用。"

## Checking Module Availability

```python
from app.tools.fundamental import get_available_modules

# Free mode — excludes announcements, analyst_ratings
free_modules = get_available_modules("free")

# Standard mode — includes all
std_modules = get_available_modules("standard")
```
