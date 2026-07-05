# 00_current_audit.md — Stock Fundamental Service Phase 0 技术审计

> 生成时间：2026-07-04  
> 审计范围：仓库当前实现 vs 新规划 "股票基本面数据服务（Stock Fundamental Service）" 23+1 模块系统  
> **仅审计，不修改业务代码。**

---

## 一、仓库结构树（关键路径）

```
TradingAgents/
├── backend/
│   ├── app/
│   │   ├── agents/             # Chat Copilot Agent 层（已有，与新系统无关）
│   │   │   ├── chat_orchestrator.py
│   │   │   ├── chat_streaming.py
│   │   │   ├── chat_tools/     # Chat 工具注册表（9 只工具）
│   │   │   ├── chat_skills/    # Chat Skill Registry（6 只技能）
│   │   │   ├── chat_planner/   # RuleBasedPlanner + PlannerExecutor
│   │   │   ├── orchestrator/   # Multi-Agent Orchestrator（Phase 2E）
│   │   │   ├── fundamental_analyst.py
│   │   │   ├── technical_analyst.py
│   │   │   ├── peer_comparison_analyst.py
│   │   │   └── news_analyst.py
│   │   ├── core/
│   │   │   ├── config.py       # Settings（无 TUSHARE_TOKEN / ENABLE_AKSHARE）
│   │   │   ├── database.py     # PostgreSQL + Redis
│   │   │   └── security.py
│   │   ├── data/
│   │   │   └── providers/      # 现有数据源（均为 AkShare 系）
│   │   │       ├── akshare_provider.py      ← 主力 quote/kline
│   │   │       ├── fundamental_provider.py  ← AkShare 财报摘要
│   │   │       ├── sina_provider.py
│   │   │       ├── tencent_provider.py
│   │   │       ├── eastmoney_provider.py
│   │   │       ├── baostock_provider.py
│   │   │       ├── yfinance_provider.py
│   │   │       └── news_provider.py
│   │   ├── models/             # SQLAlchemy ORM（无财报表）
│   │   ├── routers/            # FastAPI 路由（无 /api/v1/modules 系列）
│   │   ├── services/
│   │   │   ├── cache_service.py          ← Redis TTL + stale 降级 ✓
│   │   │   ├── fundamental_data_service.py ← 快照骨架（AkShare，非 Tushare）
│   │   │   ├── stock_data_service.py
│   │   │   └── ...
│   │   ├── llm/                # DeepSeek client
│   │   └── main.py
│   ├── alembic/versions/       # 10 个 migration（无财报 schema）
│   ├── tests/                  # 83 个测试文件（全部 Chat Copilot 相关）
│   └── pyproject.toml          # 依赖：akshare ✓, redis ✓, tushare ✗, echarts ✗
├── frontend/
│   ├── src/
│   │   ├── views/              # 10 个页面（无 StockFundamentalView）
│   │   ├── components/         # 70 个组件（无 ModuleCard / ECharts 图表）
│   │   └── ...
│   └── package.json            # 依赖：lightweight-charts ✓, echarts ✗
├── docs/
│   ├── 00_current_audit.md     ← 本文件（Phase 0 新建）
│   ├── ✗ 01_architecture.md    ← 不存在
│   ├── ✗ 02_aggregation_design.md ← 不存在
│   ├── ✗ 03_cost_and_refresh.md   ← 不存在
│   ├── ✗ 04_compliance.md         ← 不存在
│   └── aicaibao               ← 参考 UI 截图（209KB 二进制，非 Markdown）
└── README.md                   # Chat Copilot 系统说明
```

---

## 二、前置状态：规划文档本身尚未创建

**阻塞项 B-0（最高优先级）**：

审计所依赖的 4 份规划文档均不存在于仓库中：

| 文档 | 状态 |
|------|------|
| `docs/01_architecture.md` | **不存在** |
| `docs/02_aggregation_design.md` | **不存在** |
| `docs/03_cost_and_refresh.md` | **不存在** |
| `docs/04_compliance.md` | **不存在** |

因此本审计以用户 Prompt 中描述的规划目标为基准，对仓库当前状态进行对标。

---

## 三、与规划目标的差距全表

### 3.1 后端核心架构

| 规划要求 | 状态 | 现有替代 | 差距说明 |
|----------|------|----------|----------|
| `app/datasource/` 目录 | ❌ 缺失 | `app/data/providers/` | 需新建 Tushare 专用 datasource 层 |
| `app/tools/` 目录（17 个 tools） | ❌ 缺失 | `app/agents/chat_tools/`（9 个 chat 工具） | chat_tools 是对话驱动的，不等于财报模块工具 |
| `app/cache.py` | ❌ 缺失 | `app/services/cache_service.py` | 功能已有，只需按规划路径创建别名或迁移 |
| `app/aggregator/` | ❌ 缺失 | 无 | 完全空白，需从零实现 23+1 模块聚合层 |
| `app/agent/ai_analyst.py` | ❌ 缺失 | `app/agents/financial_agent.py`（报告型） | 存量是完整报告生成，规划要求是模块级 AI 解析 |
| `app/mcp_server.py` | ❌ 缺失 | 无 | MCP 服务器完全空白 |
| `sql/schema.sql` | ❌ 缺失 | Alembic migrations（无财报表） | 无 income / balance / cashflow / fina_indicator 表 |

### 3.2 数据源

| 规划要求 | 状态 | 现有 | 差距 |
|----------|------|------|------|
| Tushare Pro 主源 | ❌ 缺失 | 无 | `tushare` 未在 pyproject.toml 中，无 token 配置，无 client |
| AkShare 可选备源 | ⚠️ 部分 | `akshare_provider.py`（行情）+ `fundamental_provider.py`（财摘） | 无 `ENABLE_AKSHARE` 环境变量开关，AkShare 硬编码为唯一主源 |
| `ENABLE_AKSHARE=false` 运行路径 | ❌ 缺失 | 无 | `config.py` 中无此字段，所有 provider 无降级 guard |
| Tushare 限频 / 重试逻辑 | ❌ 缺失 | 无 | 当前 AkShare 调用也无限频保护 |
| daily_basic、income、balancesheet、cashflow、fina_indicator ETL | ❌ 缺失 | 无 | 无任何 ETL pipeline |

### 3.3 API 接口

| 规划要求 | 状态 | 现有路由 | 差距 |
|----------|------|----------|------|
| `GET /api/v1/modules` | ❌ 缺失 | `/stocks/search`、`/stocks/{m}/{s}/quote` 等 | 无模块注册表接口 |
| `GET /api/v1/stock/{code}/modules/{module_id}` | ❌ 缺失 | 无 | 无按模块懒加载接口 |
| `GET /api/v1/stock/{code}/overview` | ❌ 缺失 | `/stocks/{m}/{s}/profile`（部分覆盖） | 现有 profile 接口无统一响应包络 |
| 统一响应包络 | ❌ 缺失 | 各路由各自定义 schema | 无 `{ok, data, reason, stale, partial_errors, cached_at}` 规范 |
| Excel export | ❌ 缺失 | 无 | 无 openpyxl 依赖，无导出接口 |

### 3.4 23+1 模块覆盖

| 模块分类 | 规划数量 | 当前覆盖 | 备注 |
|----------|----------|----------|------|
| 确定性数据模块（21个） | 21 | 约 3-4 个（quote/kline/financial_abstract/peer） | 大量模块缺失（DuPont/现金流质量/股东/分红/行业排名等） |
| AI 分析模块 | 2（投资亮点+AI 解析） | 0（现有是综合报告不是模块） | 完整报告 ≠ 模块化 AI 解析 |
| 模块 registry | 1 | 0 | 无模块元数据注册表 |
| **合计** | **23+1** | **约 3-4** | **缺口：约 20 个模块** |

具体模块清单估算（参考 aicaibao 参考页面的典型 A 股财报分析页）：

| # | 模块名 | Tushare 接口 | 当前状态 |
|---|--------|-------------|----------|
| 1 | 行情概览 daily_quote | `daily` / `daily_basic` | ⚠️ 部分（AkShare quote，非 Tushare） |
| 2 | 估值指标 valuation | `daily_basic` PE/PB/PS/market_cap | ⚠️ 部分（AkShare spot_em，字段不全） |
| 3 | 盈利能力 profitability | `fina_indicator` ROE/ROA/毛利率/净利率 | ⚠️ 部分（AkShare 财摘，字段有限） |
| 4 | 成长能力 growth | `fina_indicator` 收入/利润同比 | ⚠️ 部分（AkShare 财摘） |
| 5 | 财务健康 financial_health | `balancesheet` + `cashflow` | ⚠️ 部分（仅资产负债率 + 经营现金流） |
| 6 | 杜邦分析 dupont | `fina_indicator` | ❌ 缺失 |
| 7 | 现金流质量 cashflow_quality | `cashflow` | ❌ 缺失 |
| 8 | 股东结构 shareholders | `top10_holders` / `top10_floatholders` | ❌ 缺失 |
| 9 | 分红送股 dividend | `dividend` | ❌ 缺失 |
| 10 | 业绩预告 forecast | `forecast` | ❌ 缺失 |
| 11 | 业绩快报 express | `express` | ❌ 缺失 |
| 12 | 资产负债表 balance_sheet | `balancesheet` | ❌ 缺失 |
| 13 | 利润表 income | `income` | ❌ 缺失 |
| 14 | 现金流量表 cashflow_stmt | `cashflow` | ❌ 缺失 |
| 15 | 行业排名 industry_rank | SQL 分位计算 | ❌ 缺失 |
| 16 | 全市场分位 market_percentile | SQL 分位计算 | ❌ 缺失 |
| 17 | 技术指标 technical | `daily` MACD/RSI/KDJ | ⚠️ 部分（存量 technical_analyst） |
| 18 | 融资融券 margin | `margin_detail` | ❌ 缺失 |
| 19 | 龙虎榜 top_list | `top_list` | ❌ 缺失 |
| 20 | 限售解禁 lock_expire | `share_float` | ❌ 缺失 |
| 21 | 公司信息 company_info | `stock_basic` / `namechange` | ❌ 缺失 |
| AI-1 | 投资亮点与风险 ai_highlights | Claude API | ❌ 缺失（模块化） |
| AI-2 | AI 智能解析 ai_analyst | Claude API | ❌ 缺失（模块化） |
| 汇总 overview | 23+1 聚合接口 | — | ❌ 缺失 |

### 3.5 缓存与可靠性

| 规划要求 | 状态 | 详情 |
|----------|------|------|
| Redis TTL | ✅ 已有 | `cache_service.py` + `fundamental_data_service.py` 中 TTL=3600 |
| stale-on-error | ✅ 已有 | `_stale_get` 降级逻辑，标记 `data_quality.stale=true` |
| 字段 None 安全 | ⚠️ 部分 | `fundamental_data_service.py` 有部分 None 处理，但新模块尚未实现 |
| 上游失败不抛 500 | ✅ 已有 | `get_fundamentals` 有 try/except + stale fallback |
| ENABLE_AKSHARE=false 运行路径 | ❌ 缺失 | 无此开关，AkShare 失败会导致所有字段 null |
| Tushare 限频保护 | ❌ 缺失 | 无 rate limiter / retry with backoff |

### 3.6 前端

| 规划要求 | 状态 | 现有 | 差距 |
|----------|------|------|------|
| Vue3 生产结构 | ✅ 已有 | Vue 3 + Vite + Pinia + i18n | 非 demo.html，工程结构成熟 |
| ECharts | ❌ 缺失 | lightweight-charts（TradingView 风格 K 线） | 需新增 ECharts 依赖，实现财报图表 |
| 模块懒加载 | ❌ 缺失 | 无模块化页面 | StockDetailView 是静态聚合，非懒加载模块 |
| 模块导航 sidebar/tabs | ❌ 缺失 | 无 | 需新建 |
| 图表卡片（null 断点） | ❌ 缺失 | 无财报图表 | lightweight-charts 无 null 断点处理 |
| stale 提示 UI | ❌ 缺失 | 无 | 需新建 stale badge |
| partial 错误占位 | ❌ 缺失 | 无 | 需新建 module error card |
| 导出按钮 | ❌ 缺失 | PDF 打印按钮（报告型） | 无 Excel 导出 |
| 前端读取 `/api/v1/modules` | ❌ 缺失 | 无 | 需 API 先建 |

### 3.7 测试覆盖

| 规划要求 | 状态 | 现有 | 差距 |
|----------|------|------|------|
| 财报模块单元测试 | ❌ 缺失 | 83 个文件全部是 Chat Copilot 测试 | 无任何财报数据测试 |
| stale / partial_error 测试 | ❌ 缺失 | 无 | 需新建 |
| ENABLE_AKSHARE=false 测试 | ❌ 缺失 | 无 | 需新建 |
| Tushare mock 测试 | ❌ 缺失 | 无 | 需新建 |
| 真实集成测试 | ❌ 缺失 | 所有测试均使用 mock/patch | 需配置 Tushare token + 集成测试 |

---

## 四、高风险问题

### R-1【阻塞】规划文档缺失
`docs/01_architecture.md` 等 4 份文档未创建。后续 Phase 1-5 开发没有可对标的 spec。必须先生成规划文档，才能开始开发。

### R-2【阻塞】Tushare Pro 未集成
`tushare` 包未在 `pyproject.toml` 中，`config.py` 无 `TUSHARE_TOKEN`，无任何 Tushare client。Tushare 是规划主数据源，不集成则无法实现任何模块。

### R-3【高风险】AkShare 无 ENABLE_AKSHARE=false 开关
当前 AkShare 是硬编码的唯一数据源。规划要求 `ENABLE_AKSHARE=false` 时系统完整可运行，意味着必须先接入 Tushare Pro 作为主源，才能使 AkShare 真正变为"可选"。

### R-4【高风险】无限频保护
当前 AkShare / Tencent / Sina 等调用均无 rate limiter / retry with backoff。Tushare Pro 有严格的限频配额（普通 token 每分钟 500 次），无保护会导致生产事故。

### R-5【中风险】23+1 模块聚合层完全空白
`app/aggregator/` 不存在。模块化 API（`/api/v1/modules`）需要从零实现，涉及：模块元数据注册表、模块执行引擎、partial_error 收集、统一响应包络。工作量约为 3-5 天。

### R-6【中风险】前端与后端模块系统完全脱节
现有前端 `StockDetailView.vue` 是静态聚合页，不支持按需懒加载模块。实现规划目标需要新建独立的 `StockFundamentalView.vue` + 模块卡片组件系统，不能直接复用现有页面。

### R-7【中风险】ECharts 未引入
`package.json` 无 ECharts 依赖，现有图表全部基于 `lightweight-charts`（K 线专用库）。财报柱图/折线图/饼图需要 ECharts，两者不互换，需新增依赖并配置 null 断点处理。

### R-8【低风险】MySQL schema 规划与现有 PostgreSQL 不一致
规划 Phase 5 提到 "MySQL schema 对齐"，但当前使用 PostgreSQL + Alembic。建议继续使用 PostgreSQL + Alembic，不引入 MySQL，避免双数据库运维复杂度。如果确需 MySQL，需全栈迁移（asyncpg → aiomysql/asyncmy）。

---

## 五、已完成清单（可复用的存量能力）

| 能力 | 位置 | Phase 可复用 |
|------|------|-------------|
| Redis 缓存层（TTL + stale-on-error + sync/async 桥接） | `app/services/cache_service.py` | Phase 1 |
| PostgreSQL + Alembic 基础设施 | `app/core/database.py` + `alembic/` | Phase 5 ETL |
| AkShare 行情（quote/kline）provider | `app/data/providers/akshare_provider.py` | Phase 1（作为备源） |
| AkShare 财报摘要 provider（ROE/毛利率/净利率等） | `app/data/providers/fundamental_provider.py` | Phase 1（作为备源） |
| Sina/Tencent/Eastmoney quote provider | `app/data/providers/` | Phase 1（补充备源） |
| 快照骨架 + stale/None 安全模式 | `app/services/fundamental_data_service.py` | Phase 1（参考模式） |
| Settings / config 框架 | `app/core/config.py` | Phase 1（扩展） |
| FastAPI + Pydantic v2 框架 | `app/main.py` + `app/routers/` | Phase 1 |
| DeepSeek/LLM client | `app/llm/` | Phase 3 AI 模块 |
| Vue3 + Vite + Pinia + i18n 工程结构 | `frontend/` | Phase 4 |
| 6 语言 i18n 框架 | `frontend/src/locales/` | Phase 4 |
| 三套 CSS 主题变量 | `frontend/src/styles/` | Phase 4 |
| pytest 测试框架 | `backend/pyproject.toml` | Phase 1-5 |

---

## 六、缺失清单（必须新建）

| 组件 | 说明 | Phase |
|------|------|-------|
| `docs/01_architecture.md` | 架构规划文档 | **B-0 前置** |
| `docs/02_aggregation_design.md` | 模块聚合设计 | **B-0 前置** |
| `docs/03_cost_and_refresh.md` | Tushare 积分成本 + 刷新策略 | **B-0 前置** |
| `docs/04_compliance.md` | 合规 + 免责声明规范 | **B-0 前置** |
| `app/datasource/tushare_client.py` | Tushare Pro client（限频 + 重试） | Phase 1 |
| `app/datasource/akshare_client.py` | AkShare client wrapper（ENABLE_AKSHARE 开关） | Phase 1 |
| `app/cache.py` | 统一缓存入口（或复用 cache_service） | Phase 1 |
| `app/tools/get_daily_quote.py` | 每日行情 tool | Phase 1 |
| `app/tools/get_financials.py` | 财务指标 tool | Phase 1 |
| `app/tools/get_valuation.py` | 估值指标 tool | Phase 1 |
| `app/tools/get_dupont.py` | 杜邦分析 tool | Phase 1 |
| `app/tools/get_cashflow_quality.py` | 现金流质量 tool | Phase 1 |
| `app/aggregator/registry.py` | 模块元数据注册表 | Phase 1 |
| `app/aggregator/modules.py` | 23+1 模块执行引擎 | Phase 1-2 |
| `app/aggregator/envelope.py` | 统一响应包络 schema | Phase 1 |
| `app/routers/fundamental.py` | `/api/v1/modules`、`/api/v1/stock/{code}/modules/{id}` | Phase 1 |
| 12 个缺失 tool（Phase 2） | shareholders/dividend/forecast/balance_sheet/income/... | Phase 2 |
| `app/agent/ai_analyst.py` | 模块级 AI 解析（非综合报告） | Phase 3 |
| `sql/schema.sql` | ETL 目标表 DDL（或 Alembic migration） | Phase 5 |
| ETL scripts | daily/income/balancesheet/cashflow/fina_indicator | Phase 5 |
| `frontend/src/views/StockFundamentalView.vue` | 新模块化财报页 | Phase 4 |
| `frontend/src/components/ModuleCard.vue` | 模块卡片基础组件 | Phase 4 |
| `frontend/src/components/ChartCard.vue` | ECharts 图表卡片（null 断点） | Phase 4 |
| ECharts 依赖 | `npm install echarts` | Phase 4 |
| `backend/pyproject.toml` tushare 依赖 | `tushare>=1.4.20` | Phase 1 |

---

## 七、必须先修的阻塞项（按优先级）

### B-0：创建 4 份规划文档
**无规划文档，无法对齐开发目标。必须首先创建：**
- `docs/01_architecture.md`：整体架构图、模块分层、接口规范
- `docs/02_aggregation_design.md`：23+1 模块定义、聚合逻辑、响应包络
- `docs/03_cost_and_refresh.md`：Tushare 积分用量估算、TTL 策略、刷新频率
- `docs/04_compliance.md`：数据来源声明、免责条款、aicaibao 禁止条款

### B-1：接入 Tushare Pro
```
# pyproject.toml 新增
tushare>=1.4.20

# config.py 新增
tushare_token: str | None = None
enable_akshare: bool = True  # ENABLE_AKSHARE=false 关停路径
```
无 Tushare，Phase 1 的 5 个核心 tools 均无主源，无法实现。

### B-2：实现统一响应包络
所有模块接口必须返回统一结构：
```json
{
  "ok": true,
  "module_id": "valuation",
  "data": { ... },
  "reason": null,
  "stale": false,
  "partial_errors": [],
  "cached_at": "2024-01-01T00:00:00Z"
}
```
无统一包络，前端无法实现通用懒加载卡片。

### B-3：建立 `app/tools/` 和 `app/aggregator/` 目录结构
这是 Phase 1-2 的骨架，必须先建才能并行开发多个模块。

---

## 八、Phase 1-5 开发建议

### Phase 1（最小闭环 — 建议 3 天）

**优先级顺序**：
1. 创建 4 份规划文档（B-0）
2. 安装 tushare 依赖，添加 `TUSHARE_TOKEN` + `ENABLE_AKSHARE` 到 config
3. 实现 `app/datasource/tushare_client.py`（限频 500次/分钟，指数退避 retry）
4. 实现 `app/datasource/akshare_client.py`（ENABLE_AKSHARE=false 开关）
5. 定义统一响应包络（`app/aggregator/envelope.py`）
6. 实现模块注册表（`app/aggregator/registry.py`）
7. 实现 5 个核心 tools：get_daily_quote / get_financials / get_valuation / get_dupont / get_cashflow_quality
8. 实现 3 个 API 端点：`GET /api/v1/modules`、`GET /api/v1/stock/{code}/modules/{module_id}`、`GET /api/v1/stock/{code}/overview`
9. 添加测试：5 tools × (主源/备源/stale/ENABLE_AKSHARE=false/None安全) = 25+ 测试

**关键约束**：
- ENABLE_AKSHARE=false 时，5 个 tool 必须仍能返回（即使部分字段 null + reason）
- 不允许 Tushare 调用超过 500次/分钟（需 rate limiter）
- 财报字段缺失时返回 `null + reason`，不编造

### Phase 2（完整模块 — 建议 4 天）

**优先级顺序**：
1. 补齐 17 个核心 tools（见缺失清单，shareholders/dividend/forecast/balance_sheet/income 等）
2. 实现 `app/aggregator/modules.py` 覆盖全部 23+1 个模块
3. partial_error 收集（某模块失败不影响其他模块）
4. ENABLE_AKSHARE=false 全链路测试
5. Excel export（openpyxl，所有模块数据导出）

**注意**：
- 行业排名和全市场分位必须走 SQL 聚合（不能在 Python 层遍历）
- 每个 tool 必须有 stale 和 reason 字段

### Phase 3（AI Agent — 建议 2 天）

**优先级顺序**：
1. 实现 `app/agent/ai_analyst.py`（模块级，非综合报告）
2. AI 输出结构化 JSON（不是 Markdown 字符串）
3. 24h 缓存（AI 调用成本高，不可每次请求都调用）
4. Claude 不可用时确定性模块正常返回
5. 输出必须包含"仅供参考，不构成投资建议"

**与现有 Chat Copilot 的关系**：现有 `financial_agent.py` 是报告型，不能直接复用。新的 `ai_analyst.py` 应是模块级、结构化输出（JSON）、有独立缓存策略。

### Phase 4（前端 — 建议 3 天）

**优先级顺序**：
1. 安装 ECharts：`npm install echarts`
2. 新建 `StockFundamentalView.vue`（独立页面，不修改现有 StockDetailView）
3. 实现通用 `ModuleCard.vue`（骨架屏 + stale badge + partial error 占位）
4. 实现 `ChartCard.vue`（ECharts wrapper，null 断点处理）
5. 实现模块导航（Sidebar/Tab，读取 `/api/v1/modules`）
6. 按需懒加载每个模块（Intersection Observer / Vue suspense）
7. 导出按钮

**关键约束**：
- 前端不得硬编码 23+1 个模块，必须读取 `GET /api/v1/modules` 动态渲染
- ECharts 配置必须处理 `null` 断点（`connectNulls: false`）
- 不允许一次性请求所有模块（懒加载）

### Phase 5（ETL 和生产化 — 建议 3 天）

**优先级顺序**：
1. 设计 ETL 目标表 schema（Alembic migration，非新增 MySQL）：
   - `ts_daily`、`ts_daily_basic`、`ts_income`、`ts_balancesheet`、`ts_cashflow`、`ts_fina_indicator`
2. 实现 ETL pipeline（Tushare → PostgreSQL，date 范围增量更新）
3. 行业排名/全市场分位改为 SQL PERCENTILE_CONT / RANK（不走 Python 遍历）
4. 缓存失效联动（ETL 完成后 Redis key 失效或更新）
5. 输出 cron 任务说明（daily ETL 建议 18:00 收盘后执行）

---

## 九、审计结论

| 维度 | 评分 | 说明 |
|------|------|------|
| 规划文档完整性 | 0/10 | 4 份规划文档均不存在 |
| 数据源覆盖度 | 2/10 | 无 Tushare，AkShare 无开关 |
| 模块完整度 | 1/10 | 约 3-4/23+1 个模块部分覆盖 |
| API 接口 | 1/10 | 无 `/api/v1/modules` 系列 |
| 统一响应包络 | 0/10 | 不存在 |
| 缓存可靠性 | 6/10 | Redis TTL + stale 已有，无限频保护 |
| 测试覆盖 | 0/10 | 83 个测试全部 Chat Copilot，无财报测试 |
| 前端模块系统 | 1/10 | Vue3 工程成熟，无财报模块 UI |
| **综合** | **1.5/10** | **基础设施可复用，业务逻辑从零开始** |

**结论**：当前仓库是一个成熟的 Chat Copilot + 综合分析报告系统，与新规划的"模块化财报分析服务"在架构上是正交的两个系统。现有代码不能直接复用为新系统，必须在现有基础设施（PostgreSQL/Redis/FastAPI/Vue3）之上，从 `app/datasource/`、`app/tools/`、`app/aggregator/` 开始全新构建，同时保持与现有 Chat Copilot 系统的共存（不改动现有路由/服务/组件）。

---

*本文档由 Phase 0 审计自动生成，不含任何业务代码修改。*
