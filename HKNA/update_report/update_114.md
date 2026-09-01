---
目前完成的工作汇总：

已完成

1. report-chat provider error trace category 传播
- 定位 `report_chat_copilot_agent` 宽泛异常分支将规范化 `connection` 覆盖成 `provider_error`。
- 新增 request-local allowlist helper，仅复制规范化错误记录中的安全分类、retryability、可选 HTTP status、reason code、provider code 与异常类型。
- `connection`、`http_status`、`provider_payload`、`local_client` 均可结构化进入 S6；旧未规范化异常保留 `provider_error` fallback。

2. trace 敏感信息边界
- 未规范化异常不再把原始 exception message 写入日志或 S6 trace。
- fake API key、Authorization header、provider URL 与 body marker 的测试均确认无泄漏。
- 用户 API 与 S8 仍保持安全 `partial_success`。

3. 测试与回归
- trace/category suite：24 passed / 0 failed。
- provider stream/non-stream suite：9 passed / 0 failed。
- D3、citation、numeric、derived fact 回归：28 passed / 0 failed。
- 合并定向门禁：61 passed / 0 failed。
- 未发起真实 Q3 或 LLM 请求。

4. 交付物
- 生成 `backend/docs/artifacts/company_agents_data_r3_3i2_8_6_provider_error_trace_category.md`。
- 生成 `backend/docs/artifacts/company_agents_data_r3_3i2_8_6_provider_error_trace_category.json`。
- 流量继续保持 `HOLD_1_PERCENT`。

---
下一步：你需要操作

第一步：审阅独立 commit 的四类 category 映射与 legacy fallback 安全边界。
第二步：如进入后续 integration candidate，只能在纯镜像隔离环境执行一次 Q3 runtime gate。
第三步：继续保持 `HOLD_1_PERCENT`，不要 push、merge、deploy 或扩流。
