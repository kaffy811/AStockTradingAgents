# Phase 7D-P0.4 — Public Company Response Allowlist Remediation

## 结论

匿名 Company history 与 EOD 响应已改为正向公开字段投影，未知字段默认拒绝。公开 warning 文案仅来自本地固定映射，profile 异常不再回显异常原文。本阶段未修改 Tushare 数据获取、计算、缓存、新闻、全局鉴权或其他禁止范围。

## 修复范围

### History 正向白名单

`_public_financial_record` 现在必须同时获得已批准的模块名。只有六个公开财务模块及各模块明确列出的字段可以进入 `history/latest`：

- `profitability`: `period`, `roe`, `gross_margin`, `net_margin`, `net_profit`
- `growth`: `period`, `main_business_revenue`, `net_profit`, `net_profit_yoy`, `parent_net_profit_yoy`, `equity_yoy`, `asset_yoy`, `eps_yoy`
- `cashflow_quality`: `period`, `ocf_to_np`, `ocf_to_revenue`
- `solvency`: `period`, `current_ratio`, `quick_ratio`, `cash_ratio`, `debt_ratio`, `equity_multiplier`
- `operation_capability`: `period`, `asset_turnover`, `inventory_turnover`, `receivable_turnover`
- `dupont`: `period`, `roe`, `net_margin`, `asset_turnover`, `equity_multiplier`, `dupont_formula_status`

字段集合以当前 `CompanyV2Section.vue` 的真实消费字段为依据。未知模块、未知标量、未知 `None`、嵌套对象和列表均不会自动进入匿名响应。模块状态、原因码、期间类型、截断原因和来源也分别使用固定枚举或受控映射。

### Warning 安全契约

公开 warning 仅允许以下固定 code，并由本地映射生成通用中文文案：

```text
CFO_TO_NP_DENOMINATOR_SENSITIVE
DUPONT_FORMULA_MISMATCH
FIELD_CONFLICT
OUTLIER_REQUIRES_REVIEW
```

上游 `message` 永不复制。`field` 只有在属于当前模块公开字段白名单时才保留；`outlier_status` 只允许 `normal/extreme`。未知 warning code 被拒绝。

### EOD 最小公开 DTO

Gateway 内部结构和数据逻辑未改动。匿名 `/{market}/{symbol}/eod` route 在返回前执行独立正向投影：

- 只允许 `profile/quote/valuation/financial/index_comparison` 模块；
- 每个模块只允许既有业务字段；
- fact 只保留 `value`, `unit`, `as_of`, `source`, `source_status`, `freshness`, `field_availability`, `reason_code`；
- 模块只保留公开状态、来源、时间、字段可用性与安全原因码；
- 删除 `endpoint`, provider 原始 code/message、request metadata、raw 字段和未知顶层字段。

### Profile 异常硬化

公开 profile 成功响应和权限契约保持不变。异常响应固定为：

```json
{
  "ok": false,
  "error_code": "PUBLIC_PROFILE_UNAVAILABLE",
  "message": "公司资料暂不可用，请稍后重试。"
}
```

匿名响应不再包含 `str(exc)`。

## 负向验证

测试注入 `api_key`, `token`, `secret`, `password`, `debug_detail`, `trace`, `raw_payload`，以及随机未知字符串、数字、布尔值、`None`、嵌套 dict/list；全部被拒绝。

Warning 测试注入 provider URL、异常类名、内部路径、Token 形态文本和 raw body；匿名结果只包含固定本地文案。EOD 测试注入顶层 provider debug、模块 provider message 与未知 raw fact，并确认这些字段及 `endpoint` 均不存在。

匿名 history 回归仍为 HTTP 200，不返回 `AUTH_REQUIRED`。前端测试确认 allowlist history 的业务字段可正常读取，同时 unavailable 模块保持独立状态。

## 验证结果

- 新增/直接相关后端安全测试：33 passed，0 failed。
- 扩大 Company V2、CNINFO 与 EOD 后端相关回归：97 passed，0 failed。
- 完整前端低并发发布门禁：69 files，764 passed，0 failed，0 worker startup timeout。
- 前端 production build：通过，971 modules transformed。
- Python compile：通过。
- JSON 校验：通过。
- Secret scan：0 个真实敏感信息匹配。
- `git diff --check`：通过。

本阶段未调用 live Provider；继续复用 Phase 7D-P0.2 已持久化 runtime evidence。没有调用 Tushare news、AKShare、Eastmoney、Sina 或 Tencent。

## 变更边界

修改仅涉及：

```text
backend/app/routers/company_v2_debug.py
backend/tests/fundamental/test_phase7d_p0_1_public_company_history.py
backend/tests/fundamental/test_phase7d_p0_2_tushare_eod_gateway.py
frontend/src/tests/phase7dP01CompanyModuleIsolation.test.js
backend/docs/artifacts/phase7d_p0_4_public_response_allowlist.md
backend/docs/artifacts/phase7d_p0_4_public_response_allowlist_matrix.json
HKNA/update_report/update_140.md
```

未修改 Docker、依赖、lockfile、migration、Token、Tushare 数据逻辑、行情计算、新闻能力、RAG、numeric/citation validation 或全局鉴权。
