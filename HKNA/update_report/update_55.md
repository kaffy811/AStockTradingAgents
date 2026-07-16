---
目前完成的工作汇总：

已完成

1. `backend/app/agents/chat_orchestrator.py`
- 新增 `chat_entity_pipeline_version=d6_3`。
- 每轮请求在 SkillRegistry 之前解析当前 raw query，不再依赖旧 conversation context 或 effective query。
- 将 `raw_query`、`effective_query`、`resolved_entities`、`primary_entity`、`record_count_by_market`、`index_version`、`failure_reason` 注入 `SkillContext.metadata`。
- 修复显式公司名未进入 ReportExplanationSkill 的 payload 断点。

2. `backend/app/agents/chat_skills/report_explanation_skill.py`
- 输入优先级调整为 payload `primary_entity`、payload `resolved_entities[0]`、financial context、raw query 显式代码/名称、resolver fallback、memory fallback。
- 有 symbol 但无 report_id 时继续调用 ReportChatCopilotAgent，由报告选择链路自动选择最新正式报告。
- 缺实体失败改为 `ENTITY_NOT_RESOLVED`，不再伪装为上下文不足。
- entity failure 不再触发“数据部分完整”前缀；同时保留 RAG event contract。

3. `backend/app/services/security_entity_resolver.py`
- resolver index 升级到 `v2_d6_3`，避免旧 Redis `security_entity_index:*:v1` 覆盖新索引。
- 空 index 缓存不再直接长期命中，会重新加载 StockMaster。
- 增加连续中文名称匹配，支持“贵州茅台最新财报表现如何”这类无空格句子。
- resolver response 增加 `index_version` 和 `record_count_by_market`。

4. `backend/app/agents/central_planning_agent.py`
- 修复 trace 重复：`ReportChatCopilotAgent` 不再作为两个 task 显示。
- 财报分析 trace 统一为一个 Agent，描述阶段为“定位正式财报 / 检索证据 / 生成分析”。
- 财报比较 trace 统一为 `MultiCompanyFinancialComparisonAgent` 单 Agent。

5. `backend/app/agents/chat_skills/registry.py`
- failed/error 状态不再追加 data boundary 前缀，避免 ENTITY_NOT_RESOLVED 时出现“数据部分完整”。

6. 测试
- 新增 `backend/tests/fundamental/test_phase6u_d6_3_report_entity_resolution.py`。
- 覆盖连续中文 CN/HK/US 名称解析、100 个 CN 样本嵌入句子解析、empty index rebuild、payload primary_entity、缺 report_id 自动进入 agent、ENTITY_NOT_RESOLVED 无 partial 前缀。
- 前端新增同一 Agent dispatch 去重测试。
- Targeted backend：`31 passed`。
- 相关 backend 回归：`165 passed, 15 warnings`。
- Full backend：`3239 passed, 1 skipped, 337 warnings`。
- Frontend Vitest：`675 passed`。
- `npm run build`：passed。

7. 真实 StockMaster 验证
- `stock_master` 中存在 CN/600519：`name=贵州茅台`、`exchange=SSE`、`asset_type=stock`、`status=active`、`source=sw_industry_map`。
- 当前数据库记录数：CN 5166，HK 30。
- resolver 对“贵州茅台最新财报表现如何？”返回 `600519.SH`，`match_type=continuous_name_match`，`index_version=v2_d6_3`。

---
下一步：你需要操作

第一步：重启后端进程，确认日志或 debug metadata 中出现 `chat_entity_pipeline_version=d6_3`，排除旧进程。

第二步：在全新浏览器会话验证：
`贵州茅台最新财报表现如何？`、`五粮液最新财报表现如何？`、`宁德时代最新年报如何？`。

第三步：确认普通 UI 中 `ReportChatCopilotAgent` 只出现一次，且 ENTITY_NOT_RESOLVED 不再显示“数据部分完整”。
