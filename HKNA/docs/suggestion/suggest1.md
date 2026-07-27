# HKNA 产品验收报告 1

## 1. 本次验收范围

本次针对简历/成果材料需要补充的量化指标做证据回看，检查了 Git 提交记录、`docs/mvp_smoke_test_report.md`、`docs/frontend_engineering_smoke_test.md`、`docs/resume_star_cases.md`、`HKNA/update_report/update_21.md`、`HKNA/update_report/update_93.md`、RAG JSON artifacts、后端 router 与前端 views。

## 2. 已完成内容盘点

- 4 Agent 并行综合分析已落地并有时延记录。
- Memory/Redis 双 run registry、SSE event replay、多 worker 状态共享已落地。
- 财报 RAG 索引、检索、引用校验与多报告隔离已落地。
- 后端、前端均有全量自动化测试记录。
- 当前静态盘点为 109 个 HTTP route decorators、11 个顶层 Vue 业务页面。

## 3. 数据验收

### 3.1 新闻数据

- 本次指标回看未发现可用于量化新闻入库量、周新增量或新闻检索命中率的统一 artifact。
- 新闻 Agent 与新闻页面能力存在，但不能据此推断实际新闻数据规模。
- 当前状态：功能存在，数据规模指标待补。

### 3.2 股票数据

- `stock_master` 已记录覆盖 5,166 只 A 股及 30 个申万一级行业。
- 数据可用于搜索、行业热门股与同行发现。
- 本次没有重新调用外部行情源；这里只验收仓库既有记录，不代表实时行情可用率。

## 4. 功能验收

- 多 Agent 报告：已完成并可用；串行约 120s，并行约 35–45s，约 3× 提升。
- SSE 重连：已完成；Redis `after_event_id` 回放 3/3 正确，多 worker LangGraph 记录 event_id 无重复。
- Redis 多 worker：已完成；4 workers、两种 engine 各 8 runs，共 16/16 通过。该记录是并发 run 数，不应表述为底层 Redis socket 连接数。
- 自动化测试：后端 4,975 passed、0 failed、15 live-service skipped；前端 688/688 passed、0 failed。
- RAG：4 份活跃持久化报告共 1,217 chunks；601686 的 8 问多报告评估 retrieval hit rate=100%、citation page accuracy=100%、cross-report leakage=0。
- 接口与页面：静态统计 109 个 FastAPI route decorators、11 个顶层 Vue views。
- API fallback：已实现多类 fallback，但未找到同口径改造前/后的请求成功率，不能使用“82% → 97%”。
- 用户成效：未找到实际内部用户数、WAU 或节省工时记录，不能虚构。

## 5. 当前产品阶段判断

系统已进入 Release Candidate / 灰度验收阶段，技术链路与自动化质量证据充分；产品使用成效和部分运行指标仍缺统一 telemetry。

## 6. 下一步任务部署

- P0：为 API 请求记录 primary/fallback、success、latency、provider、error_category，形成同口径前后对比。
- P0：为 SSE 记录 reconnect_attempt、reconnect_success、replayed_event_count、duplicate_event_count。
- P1：为 RAG 记录 document/chunk 总量、top_k、hit、search_mode、BM25 fallback 次数。
- P1：压测同时记录 Redis `INFO clients` 的 connected_clients/blocked_clients/maxclients，而不只记录并发 run。
- P2：增加匿名用户/活跃/报告生成次数及“传统研究耗时 vs 系统耗时”问卷埋点。

## 7. 注意事项

- 不把 fallback rate 当作 API 请求成功率。
- 不把 16 个并发 run 当作 16 个 Redis TCP 连接。
- RAG 100% 命中来自 8 个固定问题的小样本评估，不代表线上总体命中率。
- 109 是源码中的路由声明数，11 是顶层 view 文件数，不等同于所有子模块/组件数。
- 用户数和节省工时必须来自真实账户、访问日志或用户研究。

## 8. 当前最建议立即推进的一步

新增统一的验收指标采集脚本，在一次可复现 run 中同时输出 API fallback、SSE reconnect、Redis clients、RAG search mode 和测试结果，作为简历数字的唯一来源。

## 9. 附录

- `docs/mvp_smoke_test_report.md`：M43 4-worker、16 runs 与 event_id 结果。
- `docs/frontend_engineering_smoke_test.md`：SSE replay 3/3。
- `docs/resume_star_cases.md`：120s → 35–45s。
- `HKNA/update_report/update_93.md`：后端 4,975 passed，前端 688/688。
- `backend/docs/artifacts/company_v2_rag_persistence_phase6tj1.json`：4 active documents，chunk 数为 211/299/311/396。
- `backend/docs/artifacts/company_v2_601686_multi_report_rag_eval_phase6te3.json`：8 问、retrieval hit rate 1.0、citation page accuracy 1.0。
