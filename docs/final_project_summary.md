# TradingAgents — 项目技术全景

> 适用场景：面试技术说明、作品集展示、团队交接文档  
> 状态：M23 质量收口完成（2026-06-06）

---

## 一、项目一句话介绍

TradingAgents 是一个基于多 Agent 并行分析的 AI 股票研究工作台，支持 A 股与港股，生成包含技术面、基本面、同行对比与新闻面的综合研究报告，并提供数据质量评分、股票对比、行业研究、自选股工作台、报告中心与个人研究中心。

**定位**：研究辅助工具，不提供投资建议。

---

## 二、技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后端框架 | FastAPI + Python 3.12 | 异步 REST API，Pydantic 数据验证 |
| ORM | SQLAlchemy 2.x + Alembic | 数据库映射与版本化迁移 |
| 数据库 | Supabase PostgreSQL | 托管 PG，JWT 认证 |
| 缓存 | Redis 7 | 行情与分析结果缓存，TTL 控制 |
| LLM | OpenAI-compatible API | 报告生成，coordinator 汇总 |
| LLM 编排（灰度） | LangGraph | Send API fan-out + collect_node fan-in |
| 数据源 | AkShare / Sina / yfinance | 行情、基本面、新闻多源融合 |
| 前端框架 | Vue 3 Composition API（`<script setup>`） | 181 个模块，7 个主路由 |
| 构建工具 | Vite 5 | HMR 开发，生产 build |
| 状态管理 | Pinia | 认证 token / 打印 store |
| 路由 | Vue Router | SPA 路由 |
| Markdown | marked + DOMPurify | 渲染与 XSS 防护 |
| 图表 | lightweight-charts + 纯 SVG | K 线+MA+MACD+RSI / MiniTrend |
| 容器化 | Docker + docker-compose | 三容器：backend / frontend(Nginx) / Redis |

---

## 三、核心架构

### 3.1 多 Agent 分析链路

```
POST /analysis/v2/comprehensive
  → ComprehensiveAnalysisCoordinator（custom_coordinator 默认）
  → 或 LangGraphAnalysisRunner（engine=langgraph，灰度）
      ├── TechnicalAgent     → AkShare K 线 + MA + MACD + RSI
      ├── FundamentalAgent   → AkShare/Sina PE/PB/营收/利润
      ├── PeerComparisonAgent→ stock_industry_map + Hot Score
      └── NewsAgent          → AkShare 新闻（72h 窗口）
  → LLM coordinator 汇总 → result.report + sections + metadata
```

### 3.2 LangGraph 灰度对比

```
engine=langgraph → LangGraphAnalysisRunner
  graph: StateGraph(AgentState)
  Send API fan-out → 4 个 agent_node 并行
  collect_node fan-in → 等待全部完成汇总
  输出结构与 custom_coordinator 完全兼容
  A/B 对比：结构、质量、延迟三维验证通过
```

### 3.3 股票主数据（stock_master）

```
stock_master
├── market: CN / HK
├── symbol: 6 位 A 股代码 / 5 位港股代码
├── name:   中文股票名称
A 股覆盖：5,166 只（申万行业 CSV 回填）
搜索：ILIKE 精确匹配（优先）→ fallback AkShare real-time
```

### 3.4 行业热门股体系

```
industry_master (30 个申万一级行业)
  → stock_industry_map (5,166 条 A 股→行业映射)
  → industry_hot_stock_snapshot (每次 refresh 写入快照)
  Hot Score = log(成交额) × 0.4 + |涨跌幅| × 0.6
  GET /industries/{code}/hot_stocks → IndustryHotView
```

### 3.5 compareStorage 对比链路

```
localStorage tradingagents:compare_list:v1
  addCompareStock → { ok, reason, list }（duplicate/full 拒绝）
  dispatchCompareUpdated → CustomEvent 跨页面同步
  /compare?stocks=CN:000001,HK:00700（URL = source of truth）
  StockMiniTrend：纯 SVG polyline，close 归一化，area fill
```

---

## 四、数据库表

| 表名 | 说明 |
|------|------|
| `app_users` | 用户（JWT 认证） |
| `analysis_reports` | 保存的研究报告 |
| `watchlist_items` | 自选股（含 note） |
| `stock_master` | 股票主数据（搜索优先） |
| `industry_master` | 申万一级行业（30 条） |
| `stock_industry_map` | 股票 → 行业映射（5,166 条） |
| `industry_hot_stock_snapshot` | 动态热门股快照 |

Alembic revisions：多版本（baseline → add_stock_master → analysis_scope → …）

---

## 五、前端页面结构

| 路由 | 视图 | 核心组件 | 说明 |
|------|------|----------|------|
| `/` | ComprehensiveAnalysisView | HomeDashboardPanel, HomeHeroPanel, StockInputPanel, AnalysisModeSelector, EngineSelector, DiscoveryPanel | 主分析页 + 研究仪表盘 |
| `/watchlist` | WatchlistView | WatchlistStats, WatchlistToolbar, WatchlistStockCard | 自选股工作台 |
| `/industry` | IndustryHotView | IndustryOverviewPanel, IndustryHotStats, IndustryToolbar, IndustryStockCard | 行业研究页 |
| `/history` | HistoryView | ReportCenterStats, ReportFilterPanel, ReportListCard | 报告中心 |
| `/me` | ProfileView | ProfileResearchStats, ProfileActivityPanel, ProfileSettingsPanel, DataSourceNoticePanel | 个人研究中心 |
| `/stocks/:market/:symbol` | StockDetailView | StockDashboardPanel, TechnicalChartPanel, TechnicalInsightCard, NewsTimelinePanel, StockDetailResearchPanel | 股票详情页 |
| `/compare` | StockCompareView | StockCompareSelector, StockCompareSummary, StockCompareTable, StockMiniTrend | 股票横向对比 |
| `/history/:id` | HistoryDetailView | ReportDetailHeader, ReportMetaSummary, AnalysisResultLayout | 报告详情 |
| `/print/report` | PrintReportView | — | 打印/PDF 导出 |

**前端 build：195 modules（Vite production）**

---

## 六、缓存与降级

| 场景 | 策略 |
|------|------|
| 行情 K 线 | Redis TTL 缓存，TTL 内命中直接返回 |
| 综合分析结果 | Redis 缓存，重复请求复用 |
| K 线无数据 | TechnicalChartPanel EmptyState + 重试 |
| 行情降级（stale） | metadata.warnings 记录，DataQualitySummary 标注 |
| 基本面字段缺失 | 报告中说明"字段缺失"，DataQualitySummary 扣分 |
| Agent 失败 | section 空，metadata.agents 记录 failed，其余路继续 |
| LLM 失败 | _fallback_report 兜底（5 章结构） |
| compare profile 失败 | _failed stub 不白屏，StockMiniTrend 不请求 kline |
| Dashboard 数据失败 | Promise.allSettled 任意失败不白屏 |

---

## 七、数据流（主分析路径）

```
用户输入 market/symbol
  → StockSearchBox 建议（stock_master ILIKE）
  → StockIdentityCard 确认（name 解析）
  → POST /analysis/v2/comprehensive
      → Redis 检查缓存（TTL 内直接返回）
      → 多 Agent 并行执行
      → 汇总 → 写 Redis → 返回前端
  → 前端渲染：
      TechnicalChartPanel  (GET /stocks/kline)
      StockDashboardPanel  (GET /stocks/{market}/{symbol}/profile)
      DataQualitySummary   (纯前端，从 result 计算)
      ResearchActionPanel  (POST /reports, POST /watchlist, clipboard)
  → 自动保存（if settings.auto_save_report）
```

---

## 八、部署方式

### 开发环境

```bash
# 后端
cd backend && uv run uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm run dev    # localhost:3001
```

### 容器环境

```bash
docker compose up --build
docker exec -it tradingagents-backend-1 alembic upgrade head
docker exec -it tradingagents-backend-1 python scripts/import_industry_map.py
docker exec -it tradingagents-backend-1 python scripts/import_stock_master.py
```

---

## 九、已知限制

| 限制 | 说明 |
|------|------|
| 港股行业覆盖 | 不适用申万体系，同行/行业分析有限 |
| 港股基本面 | PE/PB 等字段覆盖有限 |
| 新闻时效 | 72h 时间窗口，可能为空 |
| 行情非实时 | Redis TTL 缓存，非 WebSocket 推送 |
| industry refresh duplicate | 28/30 行业正常，食品饮料/银行偶发 UniqueViolation |
| LangGraph 灰度 | 仅开发者模式可用，默认仍为 custom_coordinator |
| 非投资决策系统 | 报告仅供研究参考，不构成投资建议 |

---

## 十、后续路线图

| 优先级 | 功能 |
|--------|------|
| 完成（M25-a/M40-a） | SSE 实时分析进度推送 + `AnalysisRunRegistry` 抽象层 + P0 Bug 修复 |
| 高 | WebSocket 实时推送（行情 tick 级别） |
| 高 | industry refresh duplicate 修复 |
| 中 | 港股行业体系扩展（恒生分类） |
| 中 | 股票历史报告版本对比 |
| 低 | LangGraph 正式升为默认引擎 |
| 低 | 美股市场支持 |
| 低 | 批量分析与定时任务 |

---

## 十一、免责声明

本项目所有报告内容仅供研究参考，不构成任何投资建议。使用者应自行判断投资决策，项目作者不承担因使用本系统而产生的任何投资损失。

---

## 十二、部署准备状态（M24，2026-06-06）

| 部署要素 | 状态 | 说明 |
|----------|------|------|
| backend Dockerfile | ✅ | python:3.12-slim + uv，multi-layer cache |
| frontend Dockerfile | ✅ | node:20-alpine build → nginx:alpine runtime |
| docker-compose.yml | ✅ | 四服务：redis / migrate / backend / frontend |
| nginx.conf | ✅ | SPA routing + /api/v1/ reverse proxy + gzip + 静态资源 1y 缓存 |
| deploy_smoke_check.sh | ✅ | 9步自动验证，含 placeholder 检测、bundle 检查 |
| root .env.example | ✅ | 所有变量，仅 placeholder，有注释说明 |
| backend .env.example | ✅ | 同上，含 Supabase 连接说明 |
| frontend .env.example | ✅ | `VITE_API_BASE=http://localhost:8000/api/v1` |
| .gitignore | ✅ | 覆盖 .env / dist / node_modules / __pycache__ |
| Alembic HEAD | ✅ | b4d8e2f1a6c9，单 head，线性 5 revisions |
| npm run build | ✅ | 183 modules，exit 0（M25-a +2 modules） |
| compileall | ✅ | 无语法错误 |
| bash -n smoke script | ✅ | SYNTAX OK |

**引擎默认值：** `custom_coordinator`（生产默认）；`langgraph` 仅开发者模式灰度

**必需配置：**
- `DATABASE_URL` — Supabase Transaction Pooler（port 6543）
- `SECRET_KEY` — 64位随机字符串
- `DEEPSEEK_API_KEY` — DeepSeek LLM API Key

**部署文档：**
- [`deployment_guide.md`](./deployment_guide.md) — 快速部署指南
- [`deployment_docker.md`](./deployment_docker.md) — 详细 Docker 指南（506行）
- [`security_checklist.md`](./security_checklist.md) — 安全检查清单
- [`api_smoke_test_plan.md`](./api_smoke_test_plan.md) — API Smoke Test（T-01~T-12）

---

## 十三、SSE 实时分析进度（M25-a，2026-06-06）

| 要素 | 状态 | 说明 |
|------|------|------|
| analysis_run_registry.py | ✅ | 内存注册表，MAX_RUNS=200，LRU 淘汰 |
| realtime_analysis_runner.py | ✅ | asyncio.as_completed 逐 Agent 推送，12 种事件类型 |
| POST /analysis/runs | ✅ | 创建后台分析任务 |
| GET /analysis/runs/{id}/events | ✅ | text/event-stream SSE，心跳 15s |
| GET /analysis/runs/{id} | ✅ | 状态快照查询 |
| POST /analysis/runs/{id}/cancel | ✅ | 停止等待（cancel semantics） |
| subscribeAnalysisEvents | ✅ | fetch+ReadableStream（非 EventSource，支持 Auth header） |
| AnalysisProgressPanel realtime mode | ✅ | 5 Agent 格，"停止等待"按钮 |
| AnalysisEventTimeline | ✅ | Dev mode 事件日志，折叠，最多 20 条 |
| fallback: langgraph → 旧 API | ✅ | engine=langgraph 自动走 /comprehensive-v2 |
| fallback: SSE 错误 → 旧 API | ✅ | SSE 连接失败降级，用户无感 |
| nginx SSE headers | ✅ | proxy_cache off + X-Accel-Buffering: no |
| npm run build | ✅ | 183 modules，exit 0 |
| compileall | ✅ | 无语法错误 |

---

## M25-a/b/c SSE 实时进度架构（最终状态，2026-06-06）

### SSE 分析运行机制

```
POST /analysis/runs  →  create_run()  →  AnalysisRun (内存注册表)
  │  engine=custom_coordinator → RealtimeAnalysisRunner
  │  engine=langgraph          → LangGraphRealtimeRunner   ← M25-c 新增
  └─ asyncio.create_task(_background())

GET /analysis/runs/{id}/events  →  StreamingResponse(text/event-stream)
  Phase 1: replay history (after_event_id filter)
  Phase 2: drain buffered queue (dedup by event_id)
  Phase 3: live stream (heartbeat 15s)
  ← M25-b: event_id / after_event_id / 断线恢复

GET  /analysis/runs/{id}       → status + progress + latest_event + result
POST /analysis/runs/{id}/cancel → abort-first + backend cancel + sentinel
```

### LangGraphRealtimeRunner（M25-c）

```
graph.astream(stream_mode="updates")
  逐节点获取状态更新 → 手动 full_state 累积（annotated reducer fields）
  节点 → SSE 事件映射：
    _fetch_identity_node    → identity_resolved
    _prepare_scope_node     → agent_started ×N
    _technical/_fundamental/_peer/_news_node → agent_completed/failed
    最后 agent 完成         → synthesis_started (cancel checkpoint)
    _synthesis/_single_agent_report_node → synthesis_completed
    _finalize_node          → cancel checkpoint
    graph 完成后            → report_ready
  result shape 与 custom_coordinator 完全兼容
  metadata.workflow_engine = "langgraph"
```

### frontend SSE 订阅链路（M25-a/b/c）

```
ComprehensiveAnalysisView
  createAnalysisRun(engine?)       → POST /analysis/runs
  subscribeAnalysisEvents()        → fetch + ReadableStream（非 EventSource）
    _connect(): parse SSE, track lastEventId, detect terminalEvents
    reconnect: 1次，500ms delay，after_event_id=lastEventId
  guard flags: reportReadyHandled / fallbackStarted / cancelRequested / _isMounted
  cancel: abort first → API cancel（不触发 fallback）
  SSE 失败 → _runLegacyApi(engineParam)（保留 engine，fallback 到 /comprehensive-v2）
```

---

## 最终模块统计（M26）

| 维度 | 数量 |
|------|------|
| Vite 构建模块 | 183 |
| 前端路由（含子路由） | 11 |
| 后端 API 端点 | 20+ |
| Alembic migration head | b4d8e2f1a6c9 |
| 后端 Agent 类 | 4 + 2 coordinator + 2 realtime runner |
| Vue 组件 | 40+ |
| 文档文件 | 20 |

---

## 最终功能矩阵（M26 冻结）

### 分析能力

| 功能 | 状态 |
|------|------|
| comprehensive 全量分析 | ✅ |
| technical_only / fundamental_only / peer_only / news_only | ✅ |
| technical_fundamental | ✅ |
| custom_coordinator（默认） | ✅ |
| LangGraph（开发者灰度） | ✅ M25-c |
| SSE 实时进度推送 | ✅ M25-a |
| event_id / after_event_id 断线恢复 | ✅ M25-b |
| cancel 语义（abort-first） | ✅ M25-b |
| 重复保护 reportReadyHandled / fallbackStarted | ✅ M25-b |
| fallback 阻塞 API | ✅ |
| AnalysisRunRegistry ABC（内存/Redis 可切换） | ✅ M40-a |
| RedisAnalysisRunRegistry（多 worker 跨进程） | ✅ M40-b |
| SSE asyncio.shield 心跳 B1 修复 | ✅ M40-c |
| LangGraph 1.2.0 None 守卫 B2 修复 | ✅ M40-c |
| 14项运行时回归全通过 | ✅ M40-c |
| LangGraph 灰度决策（M41 G2 就绪） | ✅ M41：6/6 case 通过，ratio 0.97x，shape 100% 兼容 |
| DEFAULT_ANALYSIS_ENGINE env 灰度（M42）| ✅ M42：8/8 PASS，explicit > env > fallback，零前端改动 |

### 页面功能（完整列表见 final_delivery_checklist.md）

| 页面 | 状态 | 关键模块 |
|------|------|------|
| 综合分析首页 | ✅ | HomeHeroPanel/HomeDashboard/ProgressPanel/EventTimeline |
| 股票详情页 | ✅ | Dashboard/TechnicalChart/MACD/RSI/InsightCard/NewsTimeline |
| 自选股工作台 | ✅ | enriched/筛选/排序/批量/对比入口 |
| 行业热门股 | ✅ | IndustryOverview/HotStats/Toolbar/StockCard |
| 报告中心 | ✅ | Stats/FilterPanel/ListCard/DetailHeader/MetaSummary |
| 我的页面 | ✅ | ResearchStats/ActivityPanel/SettingsPanel |
| 股票对比页 | ✅ | Selector/Summary/Table/MiniTrend/URL同步 |
| BottomTabBar PWA | ✅ | ≤640px，manifest.webmanifest |

---

## 项目定位最终确认

**项目名称**：TradingAgents — AI 多 Agent 股票研究助手

**一句话定位**：面向 A 股与港股的 AI 多 Agent 股票研究系统，集成技术面、基本面、同行对比、新闻面与报告中心，支持自选股、行业热门股、股票详情、股票对比、SSE 实时分析进度与双 workflow engine 灰度（custom_coordinator 默认 / LangGraph 开发者灰度）。

**明确声明**：本系统不提供投资建议，所有报告仅供研究参考。

| Release Candidate 收口 — 4-worker Redis 多 worker 压测 | ✅ M43 |
| smoke_multi_worker_runs.py（8+8 runs, concurrency=4, CC+LG）| ✅ M43：16/16 PASS |
| M43 关键链路烟测（M43-1~M43-8）| ✅ M43：全 PASS |
| 文档一致性审查与修复（10 文档）| ✅ M43 |
| 已知限制最终确认（known_limitations.md）| ✅ M43 |
