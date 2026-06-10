# TradingAgents — AI 多 Agent 股票研究助手

> 多 Agent 并行分析 · 技术面/基本面/同行对比/新闻面 · A 股与港股  
> 可保存、可导出、可分享的结构化研究报告 · 移动端 PWA 风格

---

## 项目简介

TradingAgents 是一个基于大语言模型的 AI 股票研究辅助系统。用户输入股票代码后，系统通过多路并行 Agent 分别采集行情、财务、行业对比与新闻信息，由 coordinator Agent 汇总生成结构化分析报告，并提供数据质量评分、报告管理、自选股工作台、行业研究与股票横向对比能力。

**本项目不提供投资建议，所有报告仅供研究参考。**

---

## 核心功能

| 功能模块 | 说明 |
|----------|------|
| 首页研究仪表盘 | HomeDashboardPanel：近期报告/自选快跳/最近搜索/行业热门/对比入口，一屏掌握研究动态 |
| 多 Agent 并行分析 | Technical / Fundamental / Peer / News 四路 Agent 同时运行，coordinator 汇总综合报告 |
| 分析维度选择 | comprehensive / technical_only / fundamental_only / peer_only / news_only / technical_fundamental |
| 股票搜索与身份确认 | stock_master 主数据表解析 A 股（6位）与港股（5位），StockIdentityCard 实时确认 |
| 股票详情页 | StockDashboardPanel（行情+行业+数据质量）+ K线图（轻量图表）+ 技术指标解读 + 新闻时间线 |
| K 线图表 | 1月/3月/6月/1年/周K/月K 切换，MA5/10/20/60 均线 toggle，MACD/RSI 子图 |
| 技术面解读 | TechnicalInsightCard：4维规则（均线/MACD/RSI/成交量），无投资判断文案 |
| 新闻时间线 | NewsTimelinePanel：影响摘要 + 分类筛选 chips + 时间线排列 |
| 股票对比 | StockCompareView：2～4只横向比较，行情/行业/最近报告/数据质量/近30日趋势迷你图 |
| 迷你趋势图 | StockMiniTrend：纯 SVG polyline，close 归一化，trend-up/down/neutral |
| 行业研究页 | IndustryHotView App 化：行业切换 + IndustryOverviewPanel + Hot Stats + 热门股卡片列表 |
| 自选股工作台 | WatchlistView：4统计卡 + 5维筛选 + 批量模式（批量删除/批量对比） + Note 编辑 |
| 报告中心 | HistoryView：4统计卡 + 5维筛选（市场/scope/时间范围） + 卡片化列表 + 报告详情 |
| 我的研究中心 | ProfileView：研究统计 + 活动记录 + 偏好设置 + 数据源说明 |
| 数据完整度评分 | 纯前端四维度，帮助用户理解报告边界，不依赖新 API |
| 报告操作闭环 | 保存/加自选/查历史/复制摘要/重新分析/Markdown 下载/PDF 打印 |
| LangGraph 灰度 | 开发者模式可切换引擎，默认仍为 custom_coordinator |
| compareStorage 对比链路 | localStorage + CustomEvent，URL query 为 source of truth |
| 移动端 PWA 风格 | BottomTabBar + safe-area 自适应，≤640px 响应式布局 |

---

## 技术栈

### 后端

- **Python 3.12** + **FastAPI** — 异步 RESTful API，Pydantic 数据验证
- **SQLAlchemy 2.x** + **Alembic** — ORM 与版本化数据库迁移
- **Supabase PostgreSQL** — 托管 PG，JWT 认证
- **Redis 7** — 行情与分析结果缓存，TTL 控制
- **AkShare / yfinance / Sina** — 行情、基本面、新闻多源融合
- **OpenAI-compatible LLM** — 报告生成，coordinator 汇总
- **LangGraph**（灰度）— Send API fan-out + collect_node fan-in

### 前端

- **Vue 3** Composition API + `<script setup>`
- **Vite 5** — 构建工具，HMR 开发，生产 build 195 modules
- **Vue Router** — SPA 路由（7个主要路由）
- **Pinia** — 认证 token / 打印 store
- **lightweight-charts** — K 线 + 均线 + MACD/RSI
- **marked + DOMPurify** — Markdown 渲染与 XSS 防护

---

## 架构亮点

### 多 Agent 分析链路

```
用户请求 → ComprehensiveAnalysisCoordinator
            ├── TechnicalAgent     (K线 + MA + MACD + RSI)
            ├── FundamentalAgent   (PE/PB/营收/利润)
            ├── PeerComparisonAgent(申万行业 + Hot Score)
            └── NewsAgent          (72h 新闻摘要)
         → LLM coordinator → 综合分析报告
         → 返回 { market, symbol, sections, metadata, data_quality }
```

### LangGraph 灰度对比

```
engine=langgraph → LangGraphAnalysisRunner
  Send API fan-out: 同时触发 4 个 agent_node
  collect_node fan-in: 等待全部完成后汇总
  输出结构与 custom_coordinator 完全兼容
  开发者可 A/B 对比两引擎的结果与延迟
```

### 股票主数据（stock_master）

```
stock_master
├── market: CN / HK
├── symbol: 6位 A 股 / 5位港股
├── name: 中文股票名称
A 股覆盖：5,166只（申万行业 CSV 回填）
搜索：ILIKE 精确 → fallback AkShare real-time
```

### 行业热门股体系

```
industry_master (30个申万一级行业)
  → stock_industry_map (5,166条 A股→行业映射)
  → industry_hot_stock_snapshot (每次 refresh 写入快照)
  Hot Score = log(成交额) × 0.4 + |涨跌幅| × 0.6
```

### compareStorage 对比链路

```
localStorage tradingagents:compare_list:v1
  addCompareStock → { ok, reason:'added'|'duplicate'|'full', list }
  dispatchCompareUpdated → CustomEvent 跨页面同步
  /compare?stocks=CN:000001,HK:00700 → URL 为 source of truth
```

---

## 快速启动

```bash
# 克隆项目
git clone <repo>
cd TradingAgents

# 后端
cd backend
cp .env.example .env        # 填写 DATABASE_URL, REDIS_URL, LLM_API_KEY 等
uv sync
uv run alembic upgrade head
# 导入行业数据（首次）
uv run python scripts/import_industry_map.py
uv run python scripts/import_stock_master.py
# 启动
uv run uvicorn app.main:app --reload --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev                  # http://localhost:3001
```

---

## Demo 路径

参见 [`docs/demo_walkthrough.md`](./demo_walkthrough.md)

推荐演示股票：
- `CN/000001`（平安银行）— 完整 A 股演示
- `CN/600519`（贵州茅台）— 知名标的，适合对比演示
- `HK/00700`（腾讯控股）— 港股特殊处理演示

---

## 已知限制

| 限制 | 说明 |
|------|------|
| 港股行业覆盖 | 不适用申万体系，同行/行业分析有限 |
| 港股基本面 | PE/PB 等字段覆盖有限，yfinance 备用 |
| 新闻时效性 | 依赖 AkShare 新闻接口，72h 时间窗口 |
| 行情非实时 | Redis TTL 缓存，非 WebSocket 推送 |
| industry refresh | 偶发 UniqueViolation（食品饮料/银行），28/30 行业正常 |
| LangGraph 灰度 | env 变量 `DEFAULT_ANALYSIS_ENGINE=langgraph` 可在 staging 灰度；生产保持 custom_coordinator（M42 G2 实现）|
| 非投资决策系统 | 报告仅供研究参考，不构成投资建议 |

---

## 后续低优先级路线

- [ ] LangGraph 升为生产默认（条件：staging 稳定 1-2 周）
- [ ] 港股行业体系扩展（依赖稳定数据源）
- [ ] 报告版本对比
- [ ] 更多市场支持（美股，需新数据源）

---

## 免责声明

本项目所有报告内容仅供研究参考，不构成任何投资建议。使用者应自行判断投资风险，项目作者不承担因使用本系统而产生的任何投资损失。

---

## SSE 实时分析进度（M25）

分析任务通过 `POST /analysis/runs` 创建后台任务，前端通过 `GET /analysis/runs/{id}/events` 订阅 SSE 事件流（使用 `fetch + ReadableStream`，非 `EventSource`，以支持 Authorization header）。

**事件类型**：`analysis_started` → `identity_resolved` → `agent_started/completed/failed` × N → `synthesis_started/completed` → `report_ready`

**可靠性特性**（M25-b）：
- 每个事件含单调递增 `event_id`；断线可携带 `?after_event_id=N` 重连 replay
- 前端内置 1 次重连（500ms 延迟）
- `reportReadyHandled` / `fallbackStarted` / `cancelRequested` 防重复保护
- 取消语义：abort-first（停止等待），不强制中断后台线程

**SSE 失败降级**：自动 fallback 到 `POST /analysis/comprehensive-v2` 阻塞接口。

---

## 双 Workflow Engine（M4-b / M42）

| Engine | 状态 | 触发方式 |
|--------|------|----------|
| `custom_coordinator`（默认） | ✅ 生产稳定 | 前端默认，无需传 engine 字段 |
| `langgraph`（env 灰度）| ✅ M42 G2 | `DEFAULT_ANALYSIS_ENGINE=langgraph` env + EngineSelector（dev mode）|

两种 engine 均支持 SSE 实时进度推送，Response shape 100% 兼容（M41 验证）。`metadata.workflow_engine` 字段标明所用引擎。

完整说明见 [docs/known_limitations.md](docs/known_limitations.md) 和 [docs/architecture_overview.md](docs/architecture_overview.md)。
