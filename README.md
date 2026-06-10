# TradingAgents — AI 多 Agent 股票研究助手

> 多 Agent 并行分析 · 技术面 / 基本面 / 同行对比 / 新闻面  
> A 股与港股 · SSE 实时进度 · 双 engine 灰度 · 多 worker Redis 支持  
> 6 种 UI 语言 · 6 种报告语言 · 3 套主题 · 移动端 PWA 风格

**本项目不提供投资建议，所有报告仅供研究参考。**

---

## 项目简介

TradingAgents 是一个基于大语言模型的 AI 股票研究辅助系统。用户输入股票代码后，系统通过多路并行 Agent 分别采集行情、财务、行业对比与新闻信息，由 synthesis LLM 汇总生成结构化分析报告，并通过 SSE 实时推送分析进度。系统支持报告保存、历史中心、自选股工作台、行业热度研究与股票横向对比。

---

## 核心功能

| 功能模块 | 说明 |
|----------|------|
| 多 Agent 并行分析 | Technical / Fundamental / Peer / News 四路 Agent 同时运行，synthesis LLM 汇总综合报告 |
| 分析维度选择 | comprehensive / technical_only / fundamental_only / peer_only / news_only / technical_fundamental |
| SSE 实时进度 | `analysis_started` → `agent_started/completed` × N → `report_ready`，事件 ID 单调递增，支持断线 replay |
| 双 workflow engine | custom_coordinator（默认稳定路径）+ LangGraph（Send API fan-out，env 灰度）|
| 双 Run Registry | Memory（dev / 单 worker）+ Redis（多 worker 生产，Pub/Sub + event replay）|
| 股票详情页 | Dashboard（行情+行业+数据质量）+ K 线（MACD/RSI）+ AI 技术解读 + 新闻时间线 |
| 报告中心 | 保存/搜索/筛选（市场/scope/时间范围）/详情/Markdown 导出/PDF 打印 |
| 自选股工作台 | 4 统计卡 + 5 维筛选 + 批量删除/批量对比 + Note 编辑 |
| 行业研究页 | 申万 30 个一级行业热度 + 热门股列表（Hot Score = 成交额对数 × 涨跌幅加权）|
| 股票对比 | 2-4 只横向比较，行情/行业/报告/数据质量/近30日趋势迷你图 |
| 多语言 UI | 6 种界面语言（zh-CN / zh-TW / en-US / ja-JP / ko-KR / de-DE）|
| 多语言 AI 报告 | output_language 独立于 UI 语言，Agent-level prompt 透传 |
| 三套主题 | light-holo / dark-dive / paper-lilac，`html[data-theme]` CSS 变量切换 |
| 移动端 PWA 风格 | BottomTabBar + safe-area 自适应，≤640px 响应式布局 |

---

## 技术栈

### 后端
- **Python 3.12 + FastAPI** — 异步 RESTful API，Pydantic v2 数据验证
- **SQLAlchemy 2.x + Alembic** — ORM 与版本化数据库迁移
- **PostgreSQL**（Supabase 托管）— 用户数据、报告历史、股票主数据
- **Redis 7** — AnalysisRunRegistry（多 worker 跨进程事件共享）、行情缓存
- **AkShare / yfinance / Sina** — 行情、基本面、新闻多源融合
- **OpenAI-compatible LLM** — 4 个 Agent + synthesis 报告生成
- **LangGraph**（灰度）— Send API fan-out + collect_node fan-in 并行 Agent

### 前端
- **Vue 3** Composition API + `<script setup>`
- **Vite 5** — 构建工具，生产 build 195 modules
- **Vue Router** — SPA 路由（8 个主要路由）
- **Pinia** — 认证 token / 打印 store
- **lightweight-charts** — K 线 + 均线 + MACD/RSI 子图
- **marked + DOMPurify** — Markdown 渲染与 XSS 防护

### 部署
- **Docker Compose** — redis / migrate / backend / frontend 四服务
- **Nginx** — 前端静态资源 + `/api/v1` 反向代理

---

## 架构亮点

### 1. AnalysisRunRegistry 抽象层

```
AnalysisRunRegistry (ABC)
  ├── MemoryAnalysisRunRegistry   ANALYSIS_RUN_REGISTRY=memory（默认）
  └── RedisAnalysisRunRegistry    ANALYSIS_RUN_REGISTRY=redis（多 worker 生产）
        ├── Hash   run:{id}:state      运行状态
        ├── List   run:{id}:events     事件历史（LPUSH + LTRIM，maxlen 500）
        ├── Key    run:{id}:event_cnt  单调递增事件 ID（INCR）
        └── PubSub run:{id}:channel    实时事件推送
```

切换只需设置 `ANALYSIS_RUN_REGISTRY=redis`，零代码改动。M43 压测：4-worker × 8 run × 2 engine = 16/16 PASS。

### 2. SSE 可靠性设计

- `asyncio.shield(pending_task)` 防止心跳超时取消 async generator（B1 bug fix）
- `event_id` 单调递增，断线可通过 `?after_event_id=N` replay 已发事件
- 前端使用 `fetch + ReadableStream`（EventSource 不支持 Authorization header）
- SSE 失败自动 fallback 到阻塞式 `POST /analysis/comprehensive-v2`

### 3. 双 Engine 灰度机制

```
优先级：explicit body.engine > DEFAULT_ANALYSIS_ENGINE env > "custom_coordinator"

custom_coordinator — 稳定基线，纯 Python，易 debug
langgraph          — Send API fan-out，并行 agent_node，shape 100% 兼容
                     设置 DEFAULT_ANALYSIS_ENGINE=langgraph 可在 staging 灰度
```

### 4. output_language 与 UI 语言解耦

UI 语言通过 `i18n.js` 控制界面文本，report `output_language` 独立透传至每个 Agent 的 system prompt。用户可在中文 UI 下生成英文/日文/韩文报告。

---

## 快速启动

```bash
git clone <repo>
cd TradingAgents

# 后端
cd backend
cp .env.example .env        # 填写 DATABASE_URL, REDIS_URL, DEEPSEEK_API_KEY 等
uv sync
uv run alembic upgrade head
# 首次导入基础数据
uv run python scripts/import_industry_map.py
uv run python scripts/import_stock_master.py
# 启动（单 worker 开发模式）
uv run uvicorn app.main:app --reload --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev                  # http://localhost:3001
```

---

## Docker 部署

```bash
cp .env.example .env
# 填写 DATABASE_URL, SECRET_KEY, DEEPSEEK_API_KEY

docker compose up -d redis
docker compose run --rm migrate
docker compose up -d backend frontend
```

Nginx 在 `:80` 提供服务，`/api/v1/*` 反向代理至 backend:8000。

---

## 关键环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | — | PostgreSQL 连接串（Supabase Transaction Pooler）|
| `REDIS_URL` | `redis://localhost:6379` | Redis 连接串 |
| `ANALYSIS_RUN_REGISTRY` | `memory` | `redis` 启用多 worker 跨进程状态共享 |
| `DEFAULT_ANALYSIS_ENGINE` | `custom_coordinator` | `langgraph` 可在 staging 灰度 LangGraph |
| `ANALYSIS_RUN_TTL_SECONDS` | `7200` | Run 状态 TTL（Redis 模式）|
| `ANALYSIS_RUN_EVENT_MAXLEN` | `500` | 单 run 最大事件数（超出淘汰最旧事件）|
| `DEEPSEEK_API_KEY` | — | LLM API key（或其他 OpenAI-compatible）|
| `SECRET_KEY` | — | JWT 签名密钥 |
| `DEBUG` | `false` | 开启调试模式 |

---

## 演示路径

参见 [`docs/demo_walkthrough.md`](docs/demo_walkthrough.md)

推荐演示股票：
- `CN/000001`（平安银行）— 完整 A 股演示，含技术面/基本面/新闻面
- `CN/600519`（贵州茅台）— 知名标的，适合行业对比演示
- `HK/00700`（腾讯控股）— 港股特殊处理演示

---

## 已知限制

完整列表见 [`docs/known_limitations.md`](docs/known_limitations.md)。主要：

- 分析耗时较长（technical_only 约 20-40s，comprehensive 约 60-180s，LLM 速度依赖）
- 港股行业体系不适用申万分类，同行/行业分析有限；股票主数据约 30 只主流港股
- `asyncio.to_thread` 无法强制取消已启动的同步 agent 线程；取消语义为"停止等待"
- Redis `event_maxlen`（默认 500）超出时，最旧事件被淘汰，replay 仅能回放保留事件
- 数据来源为 AkShare / Sina / yfinance 等第三方接口，稳定性不受控

---

## 免责声明

本项目所有报告内容仅供研究参考，不构成任何投资建议。使用者应自行判断投资风险，项目作者不承担因使用本系统而产生的任何投资损失。
