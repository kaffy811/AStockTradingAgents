---
目前完成的工作汇总：

已完成

1. 在隔离分支修复明确证券标识的优先路由：当前轮 `CN/`、裸六码及 `.SZ/.SH` 标识在会话记忆、页面上下文、通用 Skill、工具和 LLM 之前进入受控 EOD 路径。
2. 扩展公司资料、EOD、收盘价、行情、估值、PE、PB、ROE 与财务指标意图，并保留官方公告/CNINFO 与行业主题 fail-closed 边界。
3. 修复交易所后缀校验绕过；错误 `.SZ/.SH` 后缀不再被当作裸代码接受。
4. EOD 回答补充 Company Profile、标准 Tushare 代码及经证据验证的报告期元数据；未改变请求级或全局 numeric validator 规则。
5. 新增受控 Tushare 数据形状 fixture、标识解析矩阵、跨轮双向串标、跨会话、无历史、错误后缀、未知代码、官方报告优先与主题 fail-closed 测试。
6. 后端相关测试 90 项、前端完整测试 769 项及 production build 均通过；没有进行 live Provider 调用、push、merge 或部署。

下一步：你需要操作

1. Owner 只读审阅本候选的路由优先级、变更范围和测试证据。
2. 审阅通过后再单独授权 merge、push 与部署；本阶段不包含这些操作。
---
