# TradingAgents — 项目技术全景

> 适用场景：面试技术说明、作品集展示、团队交接文档  
> 状态：**C13-b Real-time Tool/RAG/Skill Event Streaming 完成（2026-06-22）**；C1–C13-b 全部完成，754/754 tests PASS

---

## 一、项目一句话介绍

TradingAgents 是一个 OpenClaw-inspired 金融智能 Agents 系统，包含两个核心层次：

1. **研究工作台（M1–M51）**：多 Agent 并行分析 AI 股票研究平台，支持 A 股与港股，生成包含技术面、基本面、同行对比与新闻面的综合研究报告，并提供数据质量评分、股票对比、行业研究、自选股工作台、报告中心与个人研究中心。

2. **Chat Copilot（C1–C13-b 全部完成）**：自然语言驱动的 Agent Orchestrator，通过 Tool Registry（9 只只读金融工具）、Action Tools + ConfirmationManager（3 类真实写操作，10 分钟超时/幂等保护）、**Financial Skills Layer（6 类研究技能：异动/风险/新闻/自选/行业/报告，均已集成 RAG）**、**Controlled Planner（RuleBasedPlanner + PlannerExecutor，6 种复合任务类型，最多 5 步）**、**Memory + Audit（结构化 session 记忆，注入检测，audit trail）**、**OpenClaw-style Skill Registry（6 SkillSpec JSON 文件，spec_loader，enabled/available gate，GET /chat/skills 技能发现 API）**、**Agent Evaluation + Capability Manifest（30 golden tasks，capability_manifest.md/.json，evaluate_chat_agent.py，readiness_checklist.md）**、**C11 RAG + Review Agents（内部数据检索，SourceReviewAgent/FreshnessReviewAgent/ConsistencyReviewAgent，可信度三级评级）**、**C11 Internal Agents（分析并保存报告 intent，外部渠道礼貌拒绝）**、**C11 Chat UX（ChatSessionSidebar，超时保护 15s/45s，停止按钮，ChatReasoningSteps）**、**C12 UX Refactor（即时 5 步 placeholder 研究步骤、2 列布局、5+换一换快捷问句、填入不自动发送、错误气泡）**、**C13-a SSE Streaming（asyncio.Queue + background Task + fetch+ReadableStream + answer_delta 打字机 + fallback）**、**C13-b 工具级实时流式（safe_emit + ToolRegistry tool_started/completed + RAG rag_retrieve/review 实时 + 6 Skills skill_started/completed + PlannerExecutor planner_step 事件 + Phase 5 dedup）** 实现完整 Agentic AI 研究体验。

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

---

## Phase M47 / M47-b 更新（2026-06-11）

### 首页 Dashboard 信息架构重排

**重排前（M26 冻结版）：**
- 右列上区：最近搜索（chip 风格，6 个）
- 右列下区：行业热股（1 个行业的个股列表，5 个）

**重排后（M47-b）：**
- 右列上区：行业热门板块（top 6 行业，hot_score 降序，含排名/涨跌幅/热度分）
- 右列下区：行业热股（1 个行业的个股列表，仍保留，compact）
- 下方独立区：RecentSearchList 组件保留（用户仍可访问历史搜索）

信息逻辑：左列=个人工作台（报告/自选），右列=市场数据（行业板块/热股）。

### 最新模块统计（M47-b）

| 维度 | 数量 |
|------|------|
| Vite 构建模块 | 195 |
| Alembic migration head | c5e9f12a3b87 |
| i18n 语言数 | 6（zh-CN / zh-TW / en-US / ja-JP / ko-KR / es-ES） |
| ind_blocks_* keys 覆盖 | 6/6 语言 ✅ |

---

## Phase M48 更新（2026-06-11）

### 行业模块交互能力（M48 补充）

| 功能 | 状态 | 说明 |
|------|------|------|
| 行业热股 Top 20 默认展示 | ✅ | IndustryHotView HOT_DISPLAY_DEFAULT=20 |
| 行业热股"查看更多" → Top 50 | ✅ M48 | expandedView toggle，无重新请求 |
| 热股"收起"复原 Top 20 | ✅ M48 | 顶部/底部双按钮 |
| 切换行业自动收起 | ✅ M48 | onIndustryChange reset |
| 股票数量不足时隐藏按钮 | ✅ M48 | v-if filteredItems > 20 |
| 行业块 loading 文字 | ✅ M48 | ind_loading_heat |
| 6 语言 ind_hot_* key 覆盖 | ✅ M48 | 9 个新 key 全语言 |

---

## Phase M49 更新（2026-06-11）

### 自选股与对比页联动能力（M49 补充）

| 功能 | 状态 | 说明 |
|------|------|------|
| 首页"批量对比"入口 | ✅ M49 | HomeDashboardPanel 自选快跳底部，≥2 只才显示 |
| /watchlist?mode=compare 自动 bulk 模式 | ✅ M49 | route.query.mode 检测 |
| 2-4 只批量勾选 → 对比 | ✅ M17 | WatchlistToolbar + handleCompare() |
| URL 驱动对比页加载 | ✅ M20 | /compare?stocks=CN:000001 |
| 研究工作台完整闭环 | ✅ M49 | 首页→自选→对比 全路径打通 |

---

## Phase C4 更新（2026-06-18）— Chat Copilot 真实只读工具接入完成

### TradingAgents Chat Copilot 当前能力（C4 已完成）

| 能力 | 阶段 | 说明 | 状态 |
|------|------|------|------|
| Chat UI（`/chat` 页面） | C2 | 消息列表 + 输入框 + 快捷 chips + 结果卡片 | ✅ 已完成 |
| Chat API（session + message） | C3 | 6 个接口，2 个 DB 表，mock orchestrator | ✅ 已完成 |
| 9 个只读查询工具 + Tool Registry | C4 | 行情/新闻/行业/报告/自选股真实服务接入 | ✅ 已完成 |
| Action Tools + ConfirmationManager | C5 | 3 类真实写操作（加自选/生成报告/创建对比），10 分钟超时，幂等保护 | ✅ 已实现 |
| Financial Skills Layer | C6 | 6 类研究技能（异动/风险/新闻/自选/行业/报告），SkillRegistry，4 层分发 | ✅ 已实现 |
| Controlled Planner（多步骤任务） | C7 | RuleBasedPlanner + PlannerExecutor，6 复合类型，最多 5 步，纯规则无 LLM | ✅ 已实现 |
| 结构化记忆层 | C8 | session_metadata JSONB，recent_symbols/queries/flagged_topics，fire-and-forget | ✅ 已实现 |
| 安全护栏 + Audit Trail | C8 | _TRADING_PATTERN 拦截 + injection guard + ToolResult duration_ms/started_at | ✅ 已实现 |
| SkillSpec Registry（可发现技能） | C9 | 6 个 SkillSpec JSON（c9_v1），spec_loader，enabled/available gate，GET /chat/skills | ✅ 已实现 |
| Agent Evaluation（能力验收） | C10 | 30 golden tasks（A-F），capability_manifest.json，evaluate_chat_agent.py，389/389 PASS | ✅ 已实现 |

### C4 实现的真实只读工具（9 个）

| 工具 | 复用服务 | 卡片类型 |
|------|---------|---------|
| resolve_stock_tool | IndustryClassificationService | — |
| get_quote_tool | stock_data_service | stock_summary |
| get_kline_summary_tool | stock_data_service | — |
| get_latest_news_tool | news_data_service | — |
| get_industry_hot_tool | industry_hot_stock_service | industry_hot |
| get_industry_stocks_tool | industry_hot_stock_service | — |
| get_watchlist_tool | DB（WatchlistItem） | watchlist_list |
| get_recent_reports_tool | DB（AnalysisReport） | report_list |
| get_report_detail_tool | DB（AnalysisReport） | — |

**核心设计原则：**
- 不是荐股机器人，是 agentic research copilot
- 现有页面能力封装为工具，Chat 作为统一入口
- 所有写操作需用户确认，全程可审计
- 永不输出买入/卖出/持有/目标价

**相关文档（C1 阶段新增，共 6 个）：**
- [`docs/chat_agent_prd.md`](chat_agent_prd.md) — 产品需求文档（10 场景 + MVP 范围）
- [`docs/chat_agent_architecture.md`](chat_agent_architecture.md) — 技术架构（Mermaid + 11 模块说明）
- [`docs/chat_agent_tool_spec.md`](chat_agent_tool_spec.md) — 工具清单（17 工具规范）
- [`docs/chat_agent_memory_design.md`](chat_agent_memory_design.md) — 记忆设计（3 层 + 安全注意）
- [`docs/chat_agent_safety_policy.md`](chat_agent_safety_policy.md) — 安全合规（金融边界 + 10 项安全测试）
- [`docs/chat_agent_build_plan.md`](chat_agent_build_plan.md) — 分阶段搭建计划（C2~C8）

---

## Phase M51 更新（2026-06-11）— 结论先行报告结构

### AI 报告生成能力（M51 补充）

| 功能 | 状态 | 说明 |
|------|------|------|
| 单面报告 `### 摘要结论` 首节 | ✅ M51 | 4 个 Agent 均在详情节前输出摘要结论 |
| 综合报告 `## 一、综合结论卡片` | ✅ M51 | 7 字段卡片：判断/结论/矛盾/正面/风险/观察/完整度 |
| `## 二、四面结论汇总` 结构化汇总 | ✅ M51 | 综合报告分 4 个 ### 子节呈现各维度结论 |
| language_utils.py 25 键扩容 | ✅ M51 | M51 新增 12 摘要/卡片字段键 × 6 语言 |
| 6 语言 fallback 报告节标题更新 | ✅ M51 | _FALLBACK_STRINGS 全量更新 |
| `extractSummary()` M51 路径新增 | ✅ M51 | zh-CN `摘要结论` / 综合 `综合结论卡片` / en-US 多变体 |
| en-US `### Summary & Conclusions` 变体修复 | ✅ M51-b | 4 个 `### Summary…` 变体 + 广播兜底，8/8 测试 PASS |
| 真实报告结构回归（CN/688146） | ✅ M51-b | comprehensive+4 单面 全部合规，可读性 4.8/5 |

---

## Chat Copilot 阶段成果表（C1–C13-b）

| Phase | 核心成果 | 测试 | 状态 |
|-------|---------|------|------|
| C1 | PRD + 架构设计（6 文档） | — | ✅ |
| C2 | Chat 前端 MVP（8 组件，6 语言，mock 场景） | — | ✅ |
| C3 | Chat API + Session/Message DB（migration d7e3a9b5c2f8）| — | ✅ |
| C4 | Read-only Tool Registry（9 工具，意图路由，11 tests）| 11 | ✅ |
| C5 | Action Tools + ConfirmationManager（3 写操作，33 tests）| 44 | ✅ |
| C6 | Financial Skills Layer（6 Skills，SkillRegistry，72 tests）| 116 | ✅ |
| C7 | Controlled Planner（RuleBasedPlanner + PlannerExecutor，6 复合，137 tests）| 253 | ✅ |
| C8 | Memory + Audit Hardening（chat_memory + chat_safety + ToolResult 审计，83 tests）| 317 | ✅ |
| C9 | SkillSpec Registry（6 JSON + spec_loader + GET /chat/skills，88 tests）| 317 | ✅ |
| C10 | Agent Evaluation（30 golden tasks + capability_manifest + evaluate_chat_agent，72 tests）| 389 | ✅ |
| C11 | Advisor Demo Package + RAG + E2E Hardening（scope key 修复/ChatReasoningSteps/硬超时 error card）| 489 | ✅ |
| C12 | UX Refactor（即时研究步骤/2列布局/5快捷问句+换一换/错误气泡/59 tests）| 548 | ✅ |
| C13-a | SSE Streaming（/messages/stream + asyncio.Queue + fetch+ReadableStream + answer_delta + fallback，56 tests）| 604 | ✅ |
| C13-b | Tool/RAG/Skill 实时事件流（safe_emit + ToolRegistry + RAG + 6 Skills + Planner + dedup，44 tests）| 648 | ✅ |

**当前总测试：754/754 PASS。0 新增 migration。0 新增依赖（C6–C13-b）。**

---

## 核心设计原则（最终版）

1. **不是荐股机器人** — 永不输出买入/卖出/持有/目标价/价格预测
2. **Agentic，不是聊天框** — Tool Registry + Skill Registry + Planner + Action Confirmation + Memory + Audit
3. **写操作必须确认** — ConfirmationManager 二阶段，用户永远可取消
4. **安全优先** — Safety Guard 在 Orchestrator 入口第一层，任何路由不能绕过
5. **可测试设计** — 所有模块 mock-based 单元测试，30 golden tasks 覆盖全链路
6. **声明式能力** — SkillSpec JSON 外置元数据，capability_manifest.json 机器可读
7. **零新依赖原则** — C6–C11 全部使用 stdlib，无新 pip 包依赖
