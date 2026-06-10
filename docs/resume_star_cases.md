# TradingAgents — 简历 STAR 案例库

**用途：** 简历项目描述、求职面试、作品集展示  
**版本：** MVP v0.7，2026-05-29  

---

## 使用说明

- 每个 STAR 案例可独立引用，也可组合使用
- **Result 部分的数字均来自实际测试**，可在面试中直接引用
- 每个案例后附"一句话简历版"，可直接放入简历项目经历条目

---

## STAR A — 多 Agent 并行协调与 LLM 表达约束

### Situation
搭建一个 AI 股票分析系统，需要同时从技术面、基本面、同行对比、新闻四个维度生成综合报告。4 个 Agent 各自调用 LLM，串行执行总时延 60–120 秒，远超可接受的用户等待时间；同时 LLM 存在"放大局部结论"的问题（如把单一 ROE 指标扩展为"基本面极为稳健"），报告可信度不足。

### Task
设计 `ComprehensiveAnalysisCoordinator`，实现 4 Agent 并行执行；同时在系统提示中约束综合报告 LLM，使其只能整合子报告事实，不得新增断言。

### Action
- 使用 `asyncio.gather + asyncio.to_thread` 将 4 个 Agent（3 个同步 + 1 个 async）包装为协程并发执行，`asyncio.wait_for(timeout=300s)` 防超时挂起
- 设计 11 条系统提示规则：规则 7 包含 5 个子规则禁止放大行为，规则 11 列出禁止词汇（"多重压力叠加"、"极为稳健"等）及中性替代表达
- 每个 Agent 返回 `AgentStatus(status, message, duration)`，状态（success / failed / degraded）实时透出到前端

### Result
- **总时延从 120s 降至 35–45s（~3× 提升）**
- 综合报告经测试不出现子报告以外的新事实
- 4 个 Agent 独立可测试，任意 Agent 失败不影响其他维度继续输出

**一句话简历版：** 设计多 Agent 并行协调器，使用 asyncio.gather 将 4-LLM 串行流水线并发化，端到端时延从 120s 降至 35–45s（3× 提升），并通过系统提示规则约束 LLM 表达边界，消除报告过强断言。

---

## STAR B — 数据源 Fallback 链 + Redis 三层缓存

### Situation
系统依赖 AkShare、yfinance、EastMoney 等第三方数据源获取行情、基本面、新闻数据。本地开发环境下 AkShare `RemoteDisconnected`、yfinance `429 Too Many Requests` 频繁发生，每次请求都重新打上游，耗时 10–30 秒，且快速触发 rate limit，导致连续请求级联降级。

### Task
在不改变任何 API 响应结构的前提下，为行情、基本面、新闻三类热点数据建立 Redis 缓存层，Redis 不可用时自动降级到进程内缓存，保证业务零感知。

### Action
- 实现 `RedisCacheService`，通过 `asyncio.run_coroutine_threadsafe` 桥接 sync 调用与 async Redis 客户端，专为 `asyncio.to_thread` 场景设计
- 为 AkShare 失败写入 negative cache（TTL 300s），yfinance 429 写入 negative cache（TTL 600s），下次请求直接跳过已知失败的 provider
- 三层缓存各自覆盖：R1（FundamentalDataService）TTL 3600s、R2（StockCacheService 行情/K线）TTL 60s/600s、R3（NewsDataService）TTL 600s
- 五层降级链：Redis → 内存 → 上游 → stale cache → 空/降级响应

### Result
- **R1（基本面）：Redis HIT 速度比 3000–20000x**（full miss 10.6s → Redis HIT 0.001s）
- **R2（行情/K线）：速度比 ~400–600x**（quote 0.32s → 0.001s；kline 0.45s → 0.001s）
- **R3（新闻）：速度比 ~400x**（1.2s → 0.003s）
- Redis 不可用时：五层降级全链路 HTTP 200，API 响应结构零变化
- API 响应字段、类型、状态码与接入前完全一致

**一句话简历版：** 为 FastAPI 后端设计三层 Redis 缓存架构（行情/基本面/新闻），结合 negative cache 和五层降级链，热点数据响应提速 400–20000x，Redis 不可用时业务零感知，HTTP 200 始终保障。

---

## STAR C — 申万行业分类全量导入与动态同行发现

### Situation
同行对比 Agent 依赖硬编码 `PEER_MAP` 字典，只覆盖约 10 只股票，超过 5000 只 A 股的同行对比维度为空，报告质量大幅降低。尝试 AkShare 申万接口（`sw_index_third_cons`）时遭遇列数 mismatch、legulegu.com 504 超时、EastMoney ProxyError，在线接口方案全面失效。

### Task
在不依赖任何代理、不改动 Agent/Router/前端代码的前提下，将申万一级行业分类全量数据导入数据库，使 CN 市场股票能自动获得动态同行；保留 PEER_MAP 手工配置的最高优先级不变。

### Action
- 放弃 AkShare 二次解析方案，改用申万宏源研究官方 JSON API（`swsresearch.com`），遍历 31 个 SW L1 行业代码，单次请求返回完整成分股 JSON，无代理依赖
- 发现 ORM 逐行 INSERT 在 5,000+ 条时触发 Supabase statement timeout 和级联 `PendingRollbackError`，改用 PostgreSQL upsert（`INSERT ... ON CONFLICT DO UPDATE`），500 条/批，~3 分钟稳定完成
- 实现 Hot Score v1：`0.7×norm(成交额) + 0.3×norm(|涨跌幅|)`，行业内 min-max 归一化
- 优先级链：`PEER_MAP > dynamic_hot > none`，已有手工配置股票（如 CN/600519）行为完全不变

### Result
- **5,166 只 A 股 / 30 个申万一级行业全量入库**（801850 美容护理官方返回 0 条，graceful skip）
- CN/300750（宁德时代）peer_source：`"none"` → **`"dynamic_hot"`**，同行对比报告激活
- CN/600519（贵州茅台）peer_source 仍为 `"manual_map"`，PEER_MAP 优先级零破坏
- Agent / Service / Router / 前端零改动，架构零破坏

**一句话简历版：** 突破 AkShare 申万接口全面失效的困境，通过官方 JSON API 将 5166 只 A 股完整导入申万一级行业分类表；实现基于 Hot Score 的动态同行发现，原先无法进行同行对比的 5000+ 只股票覆盖率提升至 30 个行业全覆盖。

---

## STAR D — 报告历史存档与前端组件复用

### Situation
综合分析结果仅保存在 Vue `ref` 中，刷新页面即丢失。用户无法查阅历史分析，无法对比不同时间点对同一股票的判断，系统是"单次分析工具"而非"有记忆的研究平台"。

### Task
在已有分析引擎的基础上，不改动任何 Agent/数据服务代码，实现完整的报告历史存档产品闭环（保存 → 列表 → 详情 → 删除），历史详情页与分析结果页视觉完全一致。

### Action
- 设计 `analysis_reports` 表：UUID PK，JSONB 存储 sections / metadata / warnings / agents（避免多表 JOIN），`report_metadata` 字段名规避 SQLAlchemy 保留名 `metadata`
- 实现 4 个 REST 接口：`user_id` 严格从 JWT 读取（不接受请求体），他人报告返回 404，`baseFetch` 增加 204 No Content 支持
- 历史详情页（`/history/:id`）**零修改**复用 AgentStatusBar / WarningPanel / MarkdownReport / SectionAccordion 四个组件，无任何条件判断或 prop 适配

### Result
- 后端 4 接口 curl 测试全部通过（201 / 200 / 204 / 404 / 权限隔离）
- 前端 build：56 → 63 modules，lazy chunk 正确分割
- 历史详情页与分析结果页视觉 100% 一致，4 个展示组件零代码改动复用
- 打通"生成分析 → 手动保存 → 历史列表 → 详情查看 → 删除"完整产品闭环

**一句话简历版：** 设计 JSONB-schema 报告历史存档方案，实现 POST/GET/DELETE 完整 CRUD，JWT user_id 严格隔离；前端历史详情页零修改复用分析结果页全部 4 个展示组件，打通个人研究平台完整产品闭环。

---

## STAR E — Vue 3 + Vite 工程化迁移

### Situation
前端初版是 904 行的单文件 `index.html`（Vue CDN + 内联逻辑 + 内联样式）。无法引入 npm 生态（DOMPurify CDN 版本不满足安全要求），报告 Markdown 存在 XSS 风险；功能扩展时维护成本急剧上升；无路由、无状态管理、无构建产物。

### Task
将 `index.html` 单文件迁移为 Vue 3 + Vite 工程化结构，保持所有功能行为完全兼容，并为报告历史、路由扩展、自选股等后续功能做好架构准备。

### Action
- 拆分为 27 个文件：入口 / 路由 / Pinia store / API 层 / 工具函数 / 全局样式 / 9 个组件 / 1 个视图
- `baseFetch` 统一封装 Bearer token 注入、401 自动登出、非 2xx 错误统一转 `ApiError`（携带 `status` 属性，使 `catch (e) { if (e.status === 409) }` 成为可能）
- `markdown.css` 改为 `main.js` 全局引入（v-html 内容不受 Vue scoped 约束）
- `warningMap.js` 统一管理 AGENT_NAMES / WARNING_MAP / SECTION_DEFS / EXAMPLES / 工具函数，多页面共享零重复

### Result
- `npm run build`：56 modules，exit 0，无编译错误
- 与 legacy 版本 16 个功能点全部行为一致
- 后续 W1（自选股）、W2（最近报告联动）、W3（Note 内联编辑）均在此架构上零阻力扩展
- XSS 防护：所有 Markdown 内容通过 `DOMPurify.sanitize()` 后 `v-html` 渲染

**一句话简历版：** 将 904 行单文件 HTML/Vue CDN 应用迁移至 Vue 3 + Vite 工程化架构（27 文件、Pinia、vue-router），引入 DOMPurify 修复 XSS 风险；baseFetch 统一鉴权与错误处理，为后续 4 个功能迭代提供零阻力扩展基础。

---

## STAR F — Watchlist 自选股研究工作台

### Situation
分析系统已具备多维报告能力，但缺少个人化研究入口：用户每次都需手动输入市场和代码，无法沉淀常看标的。分析结果与已有历史报告数据也无法在同一入口关联浏览，用户需要在多个页面之间手动切换。

### Task
构建自选股模块，实现保存常看标的 + 一键进入分析 + 展示最近报告摘要 + 内联 Note 备注，形成"个人研究工作台"体验；后端严格按 JWT user_id 隔离数据，不破坏任何已有功能。

### Action
- `watchlist_items` 表：`UniqueConstraint(user_id, market, symbol)` 防重复，`symbol` VARCHAR(32) 只做 `.strip()` 保留前导零（CN/000001 全链路不丢零）
- 最近报告联动：ROW_NUMBER() OVER (PARTITION BY market, symbol ORDER BY created_at DESC) 子查询取每 (market, symbol) 最新报告，2 次查询 + Python dict join，无 N+1；显式列举 7 个轻量列，不拉取 report_md / sections 大字段
- Note 内联编辑：5 个 Vue ref（editingNoteId / editNoteValue / savingNoteId / noteError / noteTextareaRefs），防重入（blur + Enter 双触发），内容未变静默退出，本地直接更新 `item.note` 不重新拉取列表；后端 1 行修复 `"" → null`（`body.note or None`）
- query 参数联动：`watch(() => route.query)` 替代 `onMounted` 响应 keep-alive 场景下的路由切换

### Result
- 产品升级：从"单次分析工具" → "具备个人研究列表的股票研究工作台"
- 最近报告联动：自选股卡片一眼可见每只股票分析状态，"查看最近报告"直达历史详情
- **build 验证**：75 modules，WatchlistView 独立 chunk，exit 0
- W1/W2/W3 合计：仅改动 5 个文件，无新增数据库表、无新增 API 接口（W3）

**一句话简历版：** 设计并实现 Watchlist 自选股研究工作台（W1-W3），包括 ROW_NUMBER 窗口函数驱动的最近报告联动、内联 Note 编辑（防重入 + 本地乐观更新）、keep-alive 兼容的 query 参数联动；后端 JWT 严格隔离，无 N+1，全程不破坏已有功能。

---

## 附：可直接放进简历的一段项目描述（150 字）

**TradingAgents — AI 多维股票分析平台**（个人项目，2026）

使用 FastAPI（Python）+ Vue 3 + Supabase PostgreSQL 从零构建的 AI 股票分析平台。核心特性：① 设计 4-Agent 并行协调器（asyncio.gather），将综合分析时延从 120s 降至 35–45s（3× 提升）；② 三层 Redis 缓存架构，热点数据命中速度比 400–20000x，Redis 不可用时五层降级保障零感知；③ 整合 5,166 只 A 股申万一级行业分类，实现基于 Hot Score 的动态同行发现，同行对比覆盖率从 10 只扩展至全市场 30 个行业；④ 完整自选股研究工作台，ROW_NUMBER 窗口函数驱动最近报告联动，内联 Note 编辑实现个人研究笔记沉淀。项目当前 MVP v0.7，P0 故障 0，已完成 11 个 STAR 里程碑。

---

*文档更新于 2026-05-29*
