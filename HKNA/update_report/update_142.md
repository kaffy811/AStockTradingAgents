---
目前完成的工作汇总：

已完成

1. Phase 7D-P0.7-A 主题 fail-closed
- 创建独立提交 `4434fc60feb652a7806d286f54c2175b979cbb4b`。
- exact Q4 与 11 个主题变体均由受控路由直接返回 unavailable。
- 个股 EOD 正向对照未被主题规则误伤。
- 响应稳定包含 fulfillment、reason_code、scope、sources、as_of、limitations、requires_symbol。

2. A 测试与镜像
- 后端组合测试 68 passed；完整前端 764 passed，0 worker timeout。
- backend/frontend 纯镜像构建成功，OCI revision 为 A 完整 SHA。
- 串行 Q1 通过；Q2 验收脚本语法错误。遵守无重试要求，Q3/Q4 未继续，A 判定 HOLD_WITH_EVIDENCE。

3. Phase 7D-P0.7-B 只读归因
- 5dad722、P0.5、A 三个环境均复现 7 failed / 15 passed。
- 分类为 PRE_EXISTING_TEST_INFRA；具体机制为 fixture contract drift。
- fixture patch 的 DeepSeekClient 目标正确，但未满足 client 创建前的 ai_api_key 配置 guard，mock 未被调用。
- B 未修改 Report RAG、全局 numeric validator、allow-set 或测试断言，live Provider 调用为 0。

---
下一步：你需要操作

第一步：Owner 决定是否授权一次新的纯镜像 Q1–Q4 门禁；当前不得把 A 标记为 READY。
第二步：如需修复既有 Report RAG 测试，仅授权测试 fixture/config 最小变更，不修改业务 validator 或断言。
第三步：继续保持不 push、不 merge、不部署、不执行 migration 或扩流。
