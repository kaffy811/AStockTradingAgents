# TradingAgents — 简历与面试材料

---

## 一、80 字中文简历版

基于 FastAPI + Vue 3 + Supabase 构建的 AI 股票研究工作台。多 Agent 并行分析技术面、基本面、同行对比与新闻面，支持 A 股与港股，生成可保存、导出与分享的综合研究报告，集成申万行业热门股系统、数据完整度评分与自选股管理。

---

## 二、150 字中文简历版

**TradingAgents — AI 股票研究工作台**

基于 FastAPI + Vue 3 + Supabase PostgreSQL + Redis 构建的多 Agent 股票研究辅助系统，支持 A 股（沪深）与港股分析。

核心功能：多 Agent 并行分析（技术面 / 基本面 / 同行对比 / 新闻面），LLM 汇总生成综合研究报告；股票主数据表（stock_master，5,166 只 A 股）支持输入联想与身份确认；申万一级行业热门股系统（30 行业，Hot Score 动态计算）；纯前端数据完整度四维度评分；报告保存、自选股管理、多格式导出（Markdown / PDF / 剪贴板）；Docker + Alembic 部署就绪。

---

## 三、英文简历 Bullet Points

**TradingAgents — AI Stock Research Platform** | FastAPI · Vue 3 · PostgreSQL · Redis

- Built a multi-agent stock analysis system using FastAPI and Vue 3, with parallel agents for technical, fundamental, peer comparison, and news analysis, synthesized by an LLM coordinator into a structured research report
- Designed and populated a `stock_master` table (5,166 A-share stocks) enabling real-time search autocomplete and stock identity confirmation with market-aware symbol normalization (CN 6-digit / HK 5-digit)
- Implemented a Shenwanresearch industry classification system (30 Level-1 industries, 5,166 stock mappings) with dynamic Hot Score ranking based on trading volume and price change
- Created a client-side data quality scoring system (4 dimensions: technical / fundamental / peer / news) computed purely from API response metadata — no additional API calls required
- Containerized with Docker Compose (backend + Nginx frontend + Redis), managed DB schema with Alembic migrations, and built a CI-ready deploy smoke check script

---

## 四、面试 30 秒介绍

### 中文版

"TradingAgents 是我做的一个 AI 股票研究工作台，核心是多 Agent 并行分析架构——后端有四路 Agent 同时跑，分别负责技术面、基本面、同行对比和新闻，最后由一个 coordinator Agent 调用 LLM 汇总成综合报告。前端用 Vue 3 做，有股票搜索联想、K 线图表、行业热门股、数据完整度评分、报告保存导出这些完整功能。数据库用 Supabase PostgreSQL + Redis 缓存，Docker 部署就绪。支持 A 股和港股，整个项目从后端到前端我都独立完成的。"

### English Version

"TradingAgents is an AI-powered stock research platform I built end-to-end. The backend uses FastAPI with a multi-agent architecture — four parallel agents handle technical analysis, fundamentals, peer comparison, and news respectively, with an LLM coordinator synthesizing them into a comprehensive report. The frontend is built with Vue 3, featuring real-time stock search autocomplete, K-line charts, industry hot-stock discovery, a client-side data quality scoring system, and full report export capabilities. It uses Supabase PostgreSQL for persistence, Redis for caching, and is containerized with Docker Compose. It supports both A-share and Hong Kong stocks."

---

## 五、常见面试追问与参考回答

**Q：为什么选 FastAPI 而不是 Django/Flask？**  
A：FastAPI 的异步支持和 Pydantic 数据验证很适合这种多 Agent 并发场景。自动生成的 OpenAPI 文档也方便前后端联调，开发效率高。

**Q：多 Agent 是怎么并行的？**  
A：在 coordinator 中用 `asyncio.gather` 同时发起四路 Agent 任务，每路 Agent 独立采集数据并调用 LLM，coordinator 等待所有结果后再做最终汇总。失败的 Agent 会记录在 metadata 里，不会阻断其他路。

**Q：stock_master 的 5166 条数据怎么来的？**  
A：写了一个导入脚本，从申万研究所 API 拉取全量 A 股行业映射 CSV，通过 `INSERT ON CONFLICT DO UPDATE` 幂等 upsert 写入 PostgreSQL，支持 `--dry-run` 预览。

**Q：数据完整度评分怎么实现的？**  
A：纯前端计算，从 API 返回的 `result.sections`、`result.metadata.agents`、`result.metadata.warnings` 推导四个维度的 0-100 分，不新增 API 调用。评分规则基于各种降级、字段缺失、市场特殊情况进行扣分。

**Q：Redis 缓存是怎么用的？**  
A：行情 K 线数据和综合分析结果都会缓存，重复请求在 TTL 内直接命中缓存返回。降级时（stale 行情）会在 metadata.warnings 中记录，前端 DataQualitySummary 会扣分并给用户说明。

**Q：港股和 A 股有什么不同处理？**  
A：港股代码是 5 位（带前导零，如 00700），不能 parseInt；申万行业体系不覆盖港股，所以 IndustryHotStocksPanel 对 HK 直接返回 EmptyState；基本面数据源也不同（yfinance fallback）。这些差异都在前后端都有专门处理。

---

## 六、M25 更新版（含 SSE + LangGraph）

### 中文 200 字版

**TradingAgents — AI 多 Agent 股票研究助手（M26 最终版）**

基于 FastAPI + Vue 3 + Supabase PostgreSQL 构建的多 Agent 股票研究辅助系统，支持 A 股与港股。

核心功能：4 路并行 Agent（技术面/基本面/同行对比/新闻面）+ LLM coordinator 汇总生成综合报告，支持 6 种分析范围（技术面、基本面、同行、新闻、技术+基本面、全量）；双 workflow engine 灰度：`custom_coordinator`（默认）与 LangGraph（开发者灰度），两者均支持 SSE 实时进度推送（fetch+ReadableStream，非 EventSource，以支持 Authorization header），含 event_id 断线重连、取消语义与重复保护；股票详情页（K 线/MACD/RSI/技术解读/新闻时间线）、自选股工作台、申万行业热门股（30 行业，Hot Score）、报告中心、股票对比（URL query 同步）、PWA 风格移动端。

Docker + Alembic 部署就绪，183 模块前端 build 通过，compileall 零错误。

### 英文版 Bullet Points（更新）

**TradingAgents — AI Multi-Agent Stock Research Platform** | FastAPI · Vue 3 · PostgreSQL · LangGraph · SSE

- Built a multi-agent stock analysis pipeline with 4 parallel agents (technical, fundamental, peer comparison, news) plus an LLM coordinator synthesizing a structured Markdown report; supports 6 analysis scopes and dual workflow engines (`custom_coordinator` default + LangGraph gray release)
- Implemented SSE real-time progress streaming using `fetch + ReadableStream` (not `EventSource`) to support Bearer auth headers; designed event replay via monotonic `event_id` and `after_event_id` reconnect, with 1-retry reconnect logic and `reportReadyHandled`/`fallbackStarted`/`cancelRequested` guard flags
- Integrated LangGraph (`StateGraph` + Send API fan-out) as a gray-release workflow engine; wrapped `graph.astream(stream_mode="updates")` to map node completions to the unified SSE event model without rewriting agent logic
- Built stock detail pages with lightweight-charts K-line charts, MACD/RSI indicators, rule-based technical insight cards, and news timeline panels; added Shenwanresearch industry hot-stock discovery (30 industries, Hot Score = log(volume)×0.4 + |change|×0.6)
- Designed client-side data quality scoring (4 dimensions, 0-100, no extra API calls) from `result.metadata.agents` and `warnings`; full report export (Markdown download, PDF print, clipboard copy)

### 面试 30 秒介绍（更新版）

**中文版**：  
"TradingAgents 是我做的一个 AI 多 Agent 股票研究工作台，核心是 4 路并行 Agent 加 LLM coordinator 的分析架构，支持 A 股和港股，6 种分析范围。M25 阶段我实现了 SSE 实时进度推送——用 fetch 替代 EventSource 支持 Bearer 认证，加了 event_id 断线重连、取消语义和重复保护。同时接入了 LangGraph 作为灰度 workflow engine，两者都走同一套 SSE 事件模型。前端 Vue 3，183 模块，股票详情有 K 线/MACD/RSI，还有自选股、行业热门股、报告中心、股票对比，移动端 PWA 风格。"

**English version**：  
"TradingAgents is an AI multi-agent stock research platform I built end-to-end. It runs 4 parallel agents — technical, fundamental, peer comparison, and news — with an LLM coordinator synthesizing a comprehensive report. In the latest phase I implemented SSE real-time progress streaming using fetch+ReadableStream instead of EventSource, since EventSource doesn't support Authorization headers. I added event_id-based reconnect, cancel semantics, and duplicate-handling guards. I also integrated LangGraph as a gray-release workflow engine — both engines use the same SSE event model. The frontend is Vue 3, 183 modules, with K-line charts, MACD/RSI, watchlist, industry hot stocks, report center, and stock comparison."

### 关键量化数字（面试准备）

| 数字 | 背景 |
|------|------|
| 183 | Vite 生产 build 模块数 |
| 5,166 | stock_master A 股覆盖数（申万 CSV 导入） |
| 30 | 申万一级行业数 |
| 6 | 分析范围（analysis_scope）选项数 |
| 2 | 双 workflow engine（custom_coordinator / langgraph） |
| 12 | SSE 事件类型数（analysis_started → report_ready 等）|
| 1 | SSE 断线自动重连次数（500ms delay，after_event_id replay）|
| b4d8e2f1a6c9 | 最新 Alembic migration head |
| 3 | cancel 检查点数量（agent 前/synthesis 前/report_ready 前）|
