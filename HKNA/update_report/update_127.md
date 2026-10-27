---
目前完成的工作汇总：

已完成

1. `phase7c0_existing_news_lineage_audit.md`
- 完成现有个股、行业、主题、市场、热点与官方公告/报告调用链的静态来源审计。
- 确认股票新闻真实上游为 AKShare 封装的东方财富公开网页搜索，不是仓库可证明的授权新闻 API。
- 记录入口、route、service、provider、host、字段、缓存/快照、异常与 fallback、文件行号。

2. `phase7c0_existing_news_source_matrix.json`
- 建立机器可读来源矩阵，并将每个来源唯一归入 `approved`、`owner_review_required`、`research_only` 或 `disabled`。
- 保持 Tushare `news=permission_denied`，未购买、未接入、未触发 Provider。

3. `phase7c0_agent_news_reuse_decision.md`
- 明确个股、行业、主题产业链、市场与官方公告事件的 Agent 复用边界。
- 明确无批准行业新闻源时必须返回 `unavailable`，不得索要股票代码绕行，不得虚构新闻。

4. 运行边界
- 本轮未修改业务代码，未执行 live 抓取，未触发 AKShare/Eastmoney/Sina/Tencent/Tushare/CNINFO Provider。
- 未 commit、push、merge、部署、执行 migration 或扩流；未输出敏感配置和用户数据。

---
下一步：你需要操作

第一步：Owner 审阅 `backend/docs/artifacts/phase7c0_existing_news_source_matrix.json`，书面确认可授权供应商与允许范围。
第二步：在任何业务改造前，确认 AI Research Copilot 的 approved 新闻源；若没有，保持行业/主题/市场新闻为 `unavailable`。
第三步：另行立项实现来源快照字段、Agent fail-closed 和 research-only 隔离；本轮不要部署现有新闻工具用于生产事实输出。

