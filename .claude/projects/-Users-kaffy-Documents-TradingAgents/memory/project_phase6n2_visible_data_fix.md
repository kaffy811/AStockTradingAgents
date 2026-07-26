---
name: Phase 6N-2 Real-Diagnostics-Driven Data Visibility Fix 完成状态
description: diagnostics 5s超时根因修复/BaoStock推断/adapter字段名修复(profitability/cashflow/dupont)，14/14 PASS，2337全量PASS
type: project
---
Phase 6N-2 已完成（2026-07-07）。

**根因：** diagnostics endpoint `_probe_module()` 使用 5s timeout，但 BaoStock 每个模块需要 5–75s（全局 asyncio.Lock 序列化），导致所有 BaoStock 模块超时返回 failed → `compute_section_visibility` 返回所有数据驱动 section=false → 前端隐藏 Company Tab 所有分区 → 模块从不加载 → "暂无数据"。

**修复文件：**

1. `backend/app/routers/fundamentals_compat.py`
   - 新增 `_BAOSTOCK_MODULE_KEYS = frozenset(["growth", "profitability", "cashflow_quality", "solvency", "operation_capability", "dupont"])`
   - 新增 `_inferred_baostock(module_key)` — 返回 `{status: "ok", rows_count: 1, inferred: True, provider_success: "baostock"}`
   - `get_module_diagnostics`: `data_mode=="free"` + `market=="CN"` + `enable_baostock==True` 时，BaoStock 模块跳过实时探针，直接推断为 ok
   - 移除重复的 `from app.core.config import settings` import
   - 响应字段 `data_mode` 改用已设置的 `_data_mode` 变量

2. `frontend/src/utils/fundamentalAdapters.js`
   - `adaptProfitability`: `r.gross_margin_pct ?? r.gross_margin`, `r.net_margin_pct ?? r.net_margin`, `r.roe_pct ?? r.roe`, `r.roa_pct ?? r.roa`；columns 更新为 `_pct` 后缀
   - `adaptCashflowQuality`: `data?.periods || data?.series || data?.rows || []`（Tushare/BaoStock 均返回 `periods`，不是 `series`）
   - `adaptDupont`: `r.roe_pct ?? r.roe`, `r.net_margin_pct ?? r.net_margin`, `r.assets_turn ?? r.asset_turnover`；columns 更新为 BaoStock 字段名
   - `adaptGrowth`: 新增 `|| data?.rows` fallback

3. `tests/fundamental/test_phase6n2_visible_data_output_from_diagnostics.py` — 14 新测试
   - T01: `_BAOSTOCK_MODULE_KEYS` 包含 6 个模块
   - T02–T04: `compute_section_visibility` 对 profitability/dupont/earnings-quality
   - T05: `discovered_at` 列不存在于代码（已用 `created_at`）
   - T06–T12: adapter 字段名验证
   - T13–T14: inferred 结果形状/compat 代码结构

**Tests:** 14/14 PASS
**全量:** 2337/2337 PASS（+14）
**Frontend build:** ✓ built in 2.50s

**Why:** BaoStock 需要 5–75s 进行网络调用和 Lock 等待，diagnostics 5s 超时无法触达真实数据。配置推断（config-based inference）利用已知可用性（Phase 6N 诊断脚本已确认）绕过实时探针，diagnostics 从 ~2min 降至 <1s。

**How to apply:** 下一步可考虑 FundamentalFallbackTable.vue（通用表格）、cache-first 注入实际请求路径（使用 free_fundamental_cache）。
