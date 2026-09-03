---
目前完成的工作汇总：

已完成

1. Tushare EOD Gateway
- 新增统一、可测试的 `tushare_eod_gateway`，仅调用 stock_basic、daily、daily_basic、fina_indicator 和显式映射下的 index_daily。
- 所有事实包含 value、unit、as_of、source、source_status、freshness、field_availability 和 reason_code。
- endpoint 错误独立分类和降级；禁止 Tushare news 与 Eastmoney/AKShare/Sina/Tencent production fallback。

2. Company V2 公开页面集成
- 新增匿名安全 `/api/v2/company/{market}/{symbol}/eod` 路由。
- 公司页新增最近交易日盘后、估值和财务指标展示，并明确数据截至时间及非实时边界。
- 普通公开页面不再请求旧 debug/full 聚合；profile、history 和 EOD 独立失败，不清空整页。

3. AI 个股盘后研究
- 新增 `stock_eod_research` 确定性路由，支持贵州茅台名称与 600519 等代码解析。
- 回答仅组合 Tushare EOD 标准化事实与已持久化 CNINFO 事件，并逐项展示数据日期或报告期。
- 行业、主题和市场新闻继续在 Provider 调用前 fail-closed。

4. 验收与安全验证
- 000725.SZ 与 600519.SH 的四个白名单 Tushare endpoint 受控 live 验收全部成功。
- 后端相关回归 143 passed；完整前端套件 763 passed 且零 worker timeout；production build 通过。
- 未输出 Token、请求头、raw payload 或内部 trace；未调用 news、index_daily 或网页抓取 Provider。

---
下一步：你需要操作

第一步：审阅 Phase 7D-P0.2 独立提交的 Gateway 字段、单位和非实时文案。
第二步：如 Owner 批准，再将独立提交合入受控 release 分支；当前不得 push、merge 或部署。
第三步：行业与主题新闻继续保持 unavailable，直至存在单独批准的新闻来源。
