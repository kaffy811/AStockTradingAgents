---
目前完成的工作汇总：

已完成

1. 收口财报比较请求中的证券索引重复扫描
- 在 `SecurityEntityResolver` 中加入进程级 immutable index snapshot、request-scoped memoization 和 rebuild singleflight。
- 新增 `security_index_cache_hit`、`security_index_cache_miss`、`security_index_rebuild`、`security_index_db_full_scan`、`security_index_version` 指标。
- warm resolver 路径可复用已有 snapshot，避免 Legacy Router、Context Builder、Comparison Skill、shadow 分别触发 CN/HK/US 全量扫描。
- rebuild 失败时保留旧有效 snapshot，不清空当前可用索引。

2. 收口 Chat context 多写
- 新增 `chat_memory.apply_memory_updates`，把 symbol、intent、report_id、output_language、task_state、pending_confirmation 合并为单次 context commit。
- `_write_memory_from_result` 改为一次性提交 memory 更新，避免同一 turn 多次 `SELECT chat_sessions` / `UPDATE session_metadata`。
- 增加 `context_version` 和基于原始 `session_metadata` 的 compare-and-swap；冲突时重读并按字段规则合并一次。

3. 修复五粮液比较数据 waterfall
- ReportComparisonSkill 改为 per-entity/per-metric 合并：正式报告结构化字段优先，缺失时使用 Company V2 snapshot/history。
- 一方 RAG chunk 不可用时不再导致整个比较失败；RAG 只作为原文解释和引用补充。
- 新增 `comparison_summary` 和 `per_entity` availability contract，准确记录 `requested_metric_count`、左右可用字段数、`common_metric_count`、period alignment 和 report text verification。

4. 清理比较展示与 metadata
- 比较标题固定为 `<公司名>：<年度>年年度报告`，不从 PDF title 重复拼接公司名。
- 去除展示层中文字符间空格，例如 `五 粮 液` 显示为 `五粮液`。
- assistant `msg_metadata` 增加 compact 持久化，只保留 trace/status/entities/source summary/tool summary 等小字段；不再写入完整 chunks、diagnostics、planner/compliance 大对象。

5. 测试与验证
- 新增/更新 resolver snapshot、singleflight、Company fallback、comparison contract、metadata compaction、memory single commit/CAS tests。
- Targeted backend tests passed。
- Backend default full passed：3274 passed, 15 skipped。
- Frontend Vitest passed：679 passed。
- Frontend build passed。

---
下一步：你需要操作

第一步：在真实浏览器同一会话重新执行：
1. 贵州茅台最新财报表现如何？
2. 那它和五粮液比呢

第二步：观察 SQL 日志确认：
- warm 请求不再出现多轮 CN/HK/US 全量证券索引扫描。
- `chat_sessions.session_metadata` 正常 comparison turn 最多一次 UPDATE。
- 五粮液 Company V2 fallback 被调用，回答中不再出现“五粮液整体无数据”。
- 比较标题无重复公司名，metadata 体积显著下降。

第三步：若真实 SQL 仍有重复扫描，优先检查应用是否重启后 index 尚未预热，或 Redis / in-process snapshot 是否因多 worker 进程隔离而分别构建。
