---
目前完成的工作汇总：

已完成

1. Company V2 Redis/SWR 缓存
- 在 `cache_service` 上扩展了统一 Redis pattern delete 和短锁能力，没有新建第二套 Redis client。
- 在 `company_v2_snapshot_cache_service` 上实现了 SWR envelope、fresh/stale/expired 状态、刷新锁、主动失效和内存降级。
- 为 Company V2 full envelope、company profile、annual/quarterly history、reports list、industry hot 接入了版本化 cache key。

2. Company V2 页面模块化加载
- `CompanyV2View.vue` 不再用整页“加载中”阻塞首屏。
- profile/history/full envelope 独立请求并按到达顺序落地。
- 增加 profile、quote、financial module skeleton 和 15 秒超时重试提示。

3. 报告 UI 和状态收口
- 普通页面移除了报告文件数、年报片段数、向量片段数卡片。
- 报告摘要改为基于同一 persisted report list 计算“已发现 N 份官方报告，其中 M 份可分析”。
- report discover/manual/download/parse/RAG index 操作成功后会主动失效 Company V2/report 相关缓存。

4. 行情摘要去重
- 普通行情摘要只保留最新价、涨跌幅、换手率、总市值。
- 成交额不再出现在 Company V2 顶部行情摘要中。

5. 测试和验证
- 新增 D4 后端缓存测试，覆盖 key 隔离、SWR fresh/stale/expired、刷新锁、主动失效、报告 summary/list 同源。
- 新增 D4 前端测试，覆盖报告统计卡片移除、summary 同源、progressive skeleton、profile/history 独立落地。
- 后端 full pytest：3183 passed。
- 前端 vitest：658 passed。
- npm build：passed。

---
下一步：你需要操作

第一步：如需本地人工验收，启动后端和前端，然后打开 `/stocks/CN/000725`、`/stocks/CN/600519`、`/stocks/CN/601686`、`/stocks/CN/688549` 检查二次进入、报告列表和加载速度。

第二步：如需验证 Redis 命中，保持本地 Redis 运行，观察 `company_v2:*`、`company_profile:*`、`company_history:*`、`company_reports:*`、`industry_hot:*` keys。

第三步：MiniRacer/native crash 仍未做进程级隔离，本轮只保证错误不会长期污染 Redis。建议后续单独 Phase 做 AkShare/MiniRacer provider 子进程隔离。
