---
目前完成的工作汇总：

已完成

1. 确认并修复事件循环阻塞路径。
- 行情/K线异步路由、聊天行情/K线/新闻工具及 financial runtime 行情调用改为 asyncio.to_thread；同步缓存 loader 同样卸载。
- 已检查自选股、profile、新闻、行业分类/热股、同行及基本面链路；已有线程卸载和异步数据库调用保留。
- 同步缓存桥接在目标事件循环中立即返回降级值；等待超时取消 future，取消传播到 Redis 协程；调度失败关闭协程。真实 async 缓存异常计入已有断路器，不再被 sync 成功计数覆盖。
- Redis 明确 1 秒连接/读超时、32 个连接上限、零重试，启动探测失败清理客户端。没有线上证据证明此前存在池耗尽。

2. 独立加固东方财富与过期行情标识。
- 每次最多 1 次东方财富尝试、无重试、无重定向；quote/kline socket 总预算为 6/8 秒，connect 为 2 秒；关闭 Session/response。
- 每进程共享 4 并发上限、失败 endpoint 冷却 15 秒；满载立即走已有备用链，不排队或追加重试。
- 保留东方财富/新浪/腾讯/AkShare→stale→503 的既有契约。Redis 行情命中保留为进程内 stale 候选，内存回填 Redis 不重置完整 TTL。
- 修复 K 线代理缺失 price、遗漏默认 120 条和空复权缓存键。profile 和自选股保留来源/cached/stale/message；详情页、自选卡显示过期及来源。
- 502/RemoteDisconnected 的上游触发原因未知，不把它们归因为限流。

3. 修复前端非 JSON 错误及调试堆栈暴露路径。
- 通用 v1/v2 fetch 和已有密码认证接口统一安全解析 JSON，解析失败展示友好错误，保留 HTTP status，不传递正文或解析堆栈。
- 401/204 和有效 JSON 错误码契约保留；Google 登录功能原样保留，没有纳入补丁。
- 默认 DEBUG=false；production/staging 不启用 debug 响应，未处理异常返回安全 JSON 500，详细错误记服务日志。

4. 测试结果与可复现证据。
- 当前工作区相关后端回归：217 passed，5 warnings，47.14s。包含已有 Google 测试的兼容检查，不打包其源码或依赖修改。
- 最终新增后端回归：43 passed，1 warning，1.41s，覆盖桥接正常/误用/超时取消、Redis 故障、慢源并行 HTTP、备用/stale/503、聚合元数据、聊天卸载、东方财富并发/冷却及安全错误。
- 从本地 HEAD 导出干净副本、仅应用交付补丁：后端新测试 43 passed（1.74s），前端 70 files / 781 passed（5.98s），VITE_API_BASE=/api/v1 生产构建成功（948 modules，5.59s）。已证明补丁不依赖其他未提交功能。
- 工作区前端全量 781 passed；必要前端针对性 43 passed；生产构建成功。已有 Vite CJS/大 chunk 提示不影响构建。
- 扩展后端曾有 218 passed / 1 failed，失败为 test_c4_orchestrator.py::test_industry_intent，期望旧行业工具而当前获批新闻策略拒绝该请求。在还原本次修改的独立副本复现相同失败，未擅改该策略。详情、命令和中间失败修正记录见部署 README。
- APP_ENV=production DEBUG=true 验证实际 app.debug=False。补丁通过应用/逆应用/再应用校验；只读兼容检查能拒绝源码漂移，Compose 检查能拒绝 DEBUG=true/本地数据库且不输出密钥。

5. 工作区保护及可审阅交付。
- 首先检查 Git 状态；保留已有 Google 登录及所有未提交修改。过程中检测到其他并行任务新增修改，保持其内容，补丁只提取本次增量。没有执行 reset、checkout、提交、推送或生产操作。
- 候选补丁：[market-io.patch](../../deployment/market-io-fix-v1/market-io.patch)。文件/校验和：[manifest.json](../../deployment/market-io-fix-v1/manifest.json)。部署与回滚：[README.md](../../deployment/market-io-fix-v1/README.md)。只读脚本：check_compatibility.py、check_compose.py。
- 本地基线 HEAD：98c111b684cb19de0e0e92cb46e1d675ef3e8d0a。未知服务器当前版本；补丁已验证两个本地源码变体，但没有声称线上兼容已通过。实际服务器源码不同会拒绝应用，需基于该源码重整、重测。
- 本次变更的 21 个文件（清单不含部署说明及本报告）：
- `backend/app/agents/chat_tools/stock_tools.py`
- `backend/app/agents/financial_runtime/tool_runtime.py`
- `backend/app/core/config.py`
- `backend/app/core/database.py`
- `backend/app/data/providers/eastmoney_provider.py`
- `backend/app/main.py`
- `backend/app/models/watchlist_item.py`
- `backend/app/routers/stocks.py`
- `backend/app/routers/watchlist.py`
- `backend/app/services/cache_service.py`
- `backend/app/services/stock_cache_service.py`
- `backend/app/services/stock_data_service.py`
- `frontend/src/api/auth.js`
- `frontend/src/api/companyV2.js`
- `frontend/src/api/http.js`
- `frontend/src/api/response.js`
- `frontend/src/components/StockDashboardPanel.vue`
- `frontend/src/components/WatchlistStockCard.vue`
- `frontend/src/views/StockDetailView.vue`
- `backend/tests/test_market_io_resilience.py`
- `frontend/src/tests/marketApiErrors.test.js`

6. 根因边界与剩余限制。
- 确认代码缺陷：同循环同步等待、异步方法直接同步 I/O、缓存超时未取消、聚合丢失 stale 信息、前端直接 JSON 解析和默认调试响应。代码与模拟测试支持这些机制，未取得线上调用栈，不能声称唯一线上根因。
- 第三方 AkShare 部分函数缺少统一硬超时，to_thread 不能强制终止线程，原代理绕过修改进程环境的问题未重构；极慢源仍可占线程。requests total 不覆盖 DNS/持续小流量响应的绝对墙钟时长；未宣称整条备用链硬截止。
- 冷却/并发与 stale 缓存均有进程边界；重启不保证旧缓存持久保留，stale 沿用原有无最大陈旧年龄策略，返回时明确标记非实时。
- 未验证真实东方财富、线上 Redis 压测、生产镜像构建、完整后端全库和人工浏览器视觉。未修改生产环境、Supabase、PostgreSQL 或 Redis 容器。

---
下一步：你需要操作

第一步：核对服务器当前源码及三份实际配置。
- `/opt/tradingagents` 执行 git rev-parse HEAD / git status --short；上传 `deployment/market-io-fix-v1` 到服务器 `/tmp/market-io-fix-v1`，运行 `python3 /tmp/market-io-fix-v1/check_compatibility.py /opt/tradingagents`。若不匹配，先基于实际源码重整补丁与测试，不强制覆盖。
- 依据 README 使用项目名 aastock-mvp 和 docker-compose.yml、docker-compose.staging.yml、docker-compose.mvp-server.yml 检查 effective config，确认 DEBUG=false、Supabase 不变。本地缺少第三份配置，本地 staging 与线上定义不同，不能覆盖线上 Compose。

第二步：备份并仅更新两个服务。
- 完整可执行命令见部署 README：备份白名单源码、三份配置、实际运行 backend/frontend 镜像；应用补丁，按当前服务器源码版本复测；使用现有三份配置 build backend frontend，再 up -d --no-deps --no-build backend frontend。
- 不运行 migrate、down、--remove-orphans 或全量 up；不重建数据库、不切换数据库，不替换环境文件。更新前后核对 PostgreSQL/Redis 容器 ID 不变。

第三步：验收并保留回滚路径。
- 检查健康、行情/K线/新闻/profile/自选股/行业接口、stale/来源、不可用 JSON 503、非 JSON 友好提示；慢行情期间观察其他请求与缓存日志。
- 回滚按 README：逆向校验并应用本补丁，使用备份镜像 override 与相同三份线上配置执行 up -d --no-deps --no-build backend frontend；不操作数据库。若有后续源码改动，停止自动逆补丁并逐文件审阅备份。
