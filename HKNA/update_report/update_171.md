目前完成的工作汇总：

已完成

1. `backend/docs/artifacts/beta_v1/e0/e0_20260915T013926Z/baseline_manifest.json`
- 冻结当前工作区 `release/demo-staging`、HEAD/tree、6 项历史 tracked 修改与 141 项审计前 untracked 文件。
- 分离记录 `c197e19…`、`9d05b077…` 本地候选及历史报告的生产版本 `dbf2073…`，没有混合成同一通过候选。

2. `capability_matrix.md`
- 审计公司资料、EOD、财务指标、年度/季度历史、实体切换、报告/RAG、行业主题、Chat 会话、自选及未实现的提醒/组合能力。
- 将首版建议限定为中文 A 股、盘后 EOD、可验证财务数据和已有研究记录；完整财报、行业新闻及 Chat 写操作保持关闭。

3. `api_contract_inventory.json`
- 沿 FastAPI mount、router 与前端 API wrapper 记录 beta 相关 HTTP/SSE 契约、鉴权、所有权、持久化、副作用和兼容风险。
- 明确当前同步 Chat 的 `completed` 不等于问题 `fulfilled`，Phase 8 action API 仅存在于后续候选。

4. `bug_inventory.json`
- 区分静态确认、历史问题和待复现风险。
- 首个 P0 为后端 session 初始化失败后进入硬编码 Chat mock；另记录当前 HEAD 的 `/api/v2` Nginx 契约缺口及已有后续修复提交。

5. 审计边界
- 未启动应用或测试，未访问生产、Provider、LLM、数据库或备份系统。
- 未修改业务代码、测试、配置、依赖和既有历史文件；仅新增 E0 审计材料及本更新记录。

---
下一步：你需要操作

第一步：Owner 明确 E1 的干净开发基线，优先评估包含已审 EOD/proxy 修复但不启用 Phase 8 写操作的候选链。

第二步：E1 仅移除生产 Chat mock fallback，并增加统一的 execution status / fulfillment / reason_code / request_id 兼容适配。

第三步：先用确定性组件测试复现 SSE→HTTP fallback、重复提交和切换会话，再决定 client_request_id 是否需要数据库唯一约束；未确认前 migration 记为 UNKNOWN。

第四步：继续关闭财报深度解读、行业新闻和 Chat 自选写入，后续分别取得运行、数据源、migration 与权限授权。
