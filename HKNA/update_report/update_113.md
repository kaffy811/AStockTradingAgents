---
目前完成的工作汇总：

已完成

1. `backend/app/llm/deepseek_client.py` provider error normalization
- 新增类型安全的 `ProviderErrorRecord` 与 `NormalizedProviderError`。
- `APIConnectionError` / timeout 保留 transport 语义，`http_status=null`，不会读取不存在的 `status_code`。
- `APIStatusError` 才读取 HTTP status，并保留 401、429、5xx 的 retryability 语义。
- provider payload 与未知本地异常分别分类，所有对外文本不包含原始消息、headers、body 或 provider URL。

2. 非流式与流式错误路径闭环
- `DeepSeekClient.chat()` 使用安全规范化异常并通过 cause 保留原始异常。
- `_stream_generator()` 输出同一结构化安全记录，不再存在第二处 `APIError.status_code` 假设。

3. 单元与 report-chat 安全降级回归
- normalization suite：9 passed / 0 failed。
- DeepSeek/provider-control selection：10 passed / 0 failed / 174 deselected。
- report-chat trace/S8 suite：19 passed / 0 failed。
- 合并定向回归：36 passed / 0 failed。
- 验证 S6 不再出现 secondary AttributeError，S8 继续真实返回 `partial_success`。

4. 审计交付物
- 生成 `backend/docs/artifacts/company_agents_data_r3_3i2_8_4_provider_error_normalization.md`。
- 生成 `backend/docs/artifacts/company_agents_data_r3_3i2_8_4_provider_error_normalization.json`。
- 未执行真实 Q3/LLM 请求，未修改 production 环境，流量保持 `HOLD_1_PERCENT`。

---
下一步：你需要操作

第一步：审阅独立 commit 的白名单文件与 provider error contract。
第二步：如进入后续 release integration，由 owner 在隔离 candidate 中 replay 本 commit 并重新执行单次 runtime gate。
第三步：继续保持 `HOLD_1_PERCENT`；在 owner 审核前不要 push、merge、deploy 或扩流。
