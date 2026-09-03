---
目前完成的工作汇总：

已完成

1. `backend/app/services/security_entity_resolver.py`
- 新增统一 `SecurityEntityResolver`，从 `StockMaster` 优先构建 CN/HK/US 证券实体索引，`StockIndustryMap` 作为兼容 fallback。
- 支持代码、ts_code、简称、全称、英文名、拼音字段、规范化名称和高置信模糊匹配。
- 增加 `security_entity_index:{market}:v1` 缓存 key，返回标准实体、confidence、match_type、ambiguity 和 candidates。

2. Agent/Skill 路由收口
- `ReportExplanationSkill`、`ReportComparisonSkill`、`ResolveStockTool`、RAG retriever 接入统一 resolver。
- 删除旧 `company_alias_resolver.py` 手写别名表。
- `FinancialAgent`、`official_report_search`、`chat_orchestrator`、`chat_skills/base` 保留显式 ticker/code 解析，中文名称解析交给 resolver 前置层。
- 修复中文相邻数字导致 `\b` 无法识别 `600519最新...`、`000858最近...` 的问题。

3. 会话上下文与比较意图
- 新增 `FinancialConversationContext`，统一 primary/secondary entity、active report、last intent/skill、time scope 和 pronoun 解析字段。
- 新增 `ComparisonIntentParser`，支持 2-5 个实体、比较维度、latest common annual 对齐和歧义澄清。
- 新增 `tool_capability_registry.py`，按 capability 注册 resolve/quote/profile/history/report/RAG/compare/news/technical 等能力。

4. 测试体系更新
- 新增全市场参数化 resolver 测试：100 个 CN、30 个 HK、30 个 US 自动样本，并覆盖 ST/歧义/前导零/英文 ticker。
- 更新旧同步测试：不再要求生产代码通过硬编码中文名表解析“茅台/五粮液/苹果/英伟达”，改为显式代码/ticker 或 resolver 专项测试。
- 新增静态检查，确认新 resolver/routing 关键路径不包含 `600519/000858/300750/000725` 样例硬编码。

5. 动态同行清理
- 移除 `peer_comparison_service.py` 中 Phase 1 手写 `PEER_MAP` 股票映射。
- `DynamicPeerDiscoveryService` 改为只基于行业分类与行业热门股快照发现同行。
- 清理 backend/app 中对 `PEER_MAP` 的生产文案引用，避免报告或 API 说明继续暴露旧手动映射口径。

6. 验证结果
- Targeted resolver/D6：`21 passed`
- 旧失败相关子集：`220 passed`
- Full backend：`3224 passed, 1 skipped`
- Frontend Vitest：`674 passed`
- `npm run build`：passed

---
下一步：你需要操作

第一步：如需严格清理全仓样例代码，继续处理旧 mock、文档示例、provider 示例和 CNINFO 既有 org-id 白名单；本轮已保证新实体解析/Agent 路由路径无样例股票特判，并移除了生产同行 PEER_MAP。

第二步：前端可接入证券联想 chip UI，调用现有股票搜索/后端 resolver 结果，将 canonical entity 随 chat 请求 metadata 发送；后端仍会独立校验。

第三步：建议提交信息：
`feat(chat): add market-wide entity resolution and contextual agent routing`
