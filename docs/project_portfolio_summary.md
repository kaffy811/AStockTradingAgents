# TradingAgents — 项目作品集总结

**版本：** MVP v0.7  
**更新时间：** 2026-05-29  
**仓库状态：** 私有，代码已验证可运行

---

## 一、项目背景

散户投资者在做个股决策时，通常需要手动在多个平台之间切换（行情软件看技术面、研报网站查基本面、财经网站读新闻、行业报告了解同行），信息高度碎片化，且各平台的分析结论彼此割裂。

**TradingAgents** 的目标是：把技术面、基本面、同行对比、新闻四个维度的分析整合到一次调用中，由 AI Agent 完成信息汇总与报告撰写，让用户在 35–45 秒内获得结构化的综合分析报告。

---

## 二、核心技术问题

在构建过程中，遇到并解决了以下三个有代表性的工程问题：

### 1. 数据源稳定性问题

A股/港股行情、基本面、新闻数据分散在多个不稳定的第三方接口（AkShare、yfinance、Sina）。单一接口故障会导致整条分析链路崩溃。

**解决方案**：为每类数据设计 fallback 链（CN 行情：4 级 fallback；HK 行情：2 级；基本面：AkShare → Sina → stale cache）+ 三层 Redis 缓存（热点数据 Redis 命中率 >95%，速度比可达 400–3000x）。

### 2. 同行发现的可扩展性问题

同行对比 Agent 依赖手工维护的 `PEER_MAP` 字典，只覆盖约 10 只股票，超过 5000 只 A 股无法进行同行对比。

**解决方案**：建立申万一级行业分类数据库（5,166 只 A 股 / 30 个行业），实现基于行业热门股 Hot Score 的动态同行发现，优先级链为 `PEER_MAP > dynamic_hot > none`，不破坏已有手工配置。

### 3. 多 Agent 协调的延迟问题

4 个 Agent 分别调用 LLM，串行执行总时延 60–120 秒，用户体验不可接受。

**解决方案**：`ComprehensiveAnalysisCoordinator` 使用 `asyncio.gather + asyncio.to_thread` 并行执行 4 个 Agent，总时延降至 35–45 秒（约 3× 提升）。

---

## 三、系统架构

```
┌────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3 + Vite)                 │
│  ComprehensiveAnalysisView  HistoryView  WatchlistView         │
│  (27 个 Vue 文件，Pinia Auth，vue-router，DOMPurify)            │
└───────────────────────────┬────────────────────────────────────┘
                            │ REST API (JWT Bearer)
┌───────────────────────────▼────────────────────────────────────┐
│                     FastAPI Backend                            │
│                                                                │
│  routers/  analysis.py  stocks.py  watchlist.py               │
│            reports.py   industry.py                           │
│                                                                │
│  agents/   TechnicalAnalystAgent   FundamentalAnalystAgent     │
│            PeerComparisonAnalystAgent   NewsAnalystAgent       │
│            ComprehensiveAnalysisCoordinator                    │
│                                                                │
│  services/ StockDataService (R1)  StockCacheService (R2)       │
│            FundamentalDataService (R1)  NewsDataService (R3)   │
│            DynamicPeerDiscoveryService  IndustryHotStockService│
│                                                                │
│  Redis 3-layer cache (R1/R2/R3) — 5-tier fallback on miss     │
└───────────────────────────┬────────────────────────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
   Supabase PostgreSQL    Redis           Claude API
   (5 张业务表)         (缓存层)         (LLM 推理)
```

**技术栈**

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + SQLAlchemy 2.0 (async) |
| 数据库 | Supabase PostgreSQL |
| 缓存 | Redis（可选，不可用时自动降级） |
| LLM | Anthropic Claude API |
| 前端 | Vue 3 + Vite + Pinia + vue-router |
| 认证 | Supabase Auth + JWT |
| 数据源 | AkShare / yfinance / Sina / EastMoney |

---

## 四、核心功能

### 4.1 多维 AI 分析引擎

| Agent | 输入数据 | 输出 |
|-------|---------|------|
| TechnicalAnalystAgent | OHLCV 60日K线，MA5/20/60，MACD，RSI，Bollinger | 技术面分析报告（Markdown） |
| FundamentalAnalystAgent | PE/PB/ROE/总市值/负债率等（AkShare + Sina） | 基本面分析报告（含字段边界声明） |
| PeerComparisonAnalystAgent | PEER_MAP / dynamic_hot 同行基本面数据 | 同行对比报告（含样本边界声明） |
| NewsAnalystAgent | EastMoney 近 72h 新闻摘要 | 新闻解读（含免责声明，禁止确定性结论） |
| ComprehensiveAnalysisCoordinator | 4 个子报告 | 综合报告 + agents 状态 + warnings |

### 4.2 报告历史存档

- `analysis_reports` 表（UUID PK，JSONB 存储 sections / metadata / warnings / agents）
- 保存 → 列表查询（分页 + 筛选）→ 详情查看 → 删除 完整 CRUD
- 历史详情页复用分析页全部展示组件（零代码重复）

### 4.3 自选股研究工作台（Watchlist）

- 添加/删除常看标的，UniqueConstraint 防重复，`symbol` VARCHAR(32) 保留前导零
- 每张卡片展示该股票最近一次报告摘要（时间、警告数、Agent 状态），ROW_NUMBER() 窗口函数 + Python join，无 N+1
- 一键跳转综合分析页（query 参数自动填入）/ 历史报告列表
- 内联 Note 编辑：点击 → textarea，Enter/blur 保存，Escape 取消，空内容清空 DB 字段

### 4.4 行业动态同行发现

- 申万一级行业分类：5,166 只 A 股 / 30 个行业，数据源来自 swsresearch 官方 JSON API
- Hot Score v1：`0.7×norm(成交额) + 0.3×norm(|涨跌幅|)`，行业内 min-max 归一化
- 优先级链：PEER_MAP（手工配置）> dynamic_hot（行业热门股）> none

### 4.5 三层 Redis 缓存

| 层级 | 服务 | TTL | 速度比 |
|------|------|-----|--------|
| R1 | FundamentalDataService | 3600s | ~3000–20000x |
| R2 | StockCacheService（行情/K线） | 60s / 600s | ~400–600x |
| R3 | NewsDataService | 600s | ~400x |

Redis 不可用时 5 层降级（Redis → 内存 → 上游 → stale → 空/降级响应），业务零感知。

---

## 五、关键技术难点与解决方案

### 5.1 申万行业接口全失效

**问题**：AkShare `sw_index_third_cons` 列数 mismatch；legulegu.com 504 超时；EastMoney Clash ProxyError。需要不依赖代理的全量数据源。

**解决**：改用申万宏源研究官方 JSON API（`swsresearch.com`），直接请求成分股 JSON，31 个行业各一次请求，获取 5,166 只股票，无 HTML 解析，无代理依赖。

### 5.2 大批量 ORM 写入的 autoflush/timeout 级联问题

**问题**：5,166 行 ORM 逐行 INSERT 触发 Supabase statement timeout，级联产生 `PendingRollbackError`，整批写入失败。

**解决**：改用 `INSERT INTO ... ON CONFLICT DO UPDATE`（PostgreSQL upsert），行业主表单事务 30 条，股票映射表 500 条/批，约 3 分钟稳定完成，可重复运行不产生 dirty data。

### 5.3 LLM 过强表达约束

**问题**：综合报告 LLM 会放大子报告局部结论（"多重压力叠加""极为稳健"），新闻 Agent 出现"利好/利空"等确定性结论。

**解决**：系统提示中明确列出禁止词汇 + 中性替代表达，综合报告规则 7（5 个子规则）禁止超出子报告事实范围，规则 11 约束措辞。经测试过强措辞基本消除。

### 5.4 Vue keep-alive + query 参数联动

**问题**：`ComprehensiveAnalysisView` 被 keep-alive 缓存后，路由跳转到 `/?market=CN&symbol=000001` 不触发 `onMounted`，自选股"分析"按钮无法自动填入表单。

**解决**：`ComprehensiveAnalysisView` 改用 `watch(() => route.query)` 监听 query 变化，`StockInputPanel` 新增 `initialMarket/initialSymbol` props + `watch(props)` 同步 form，keep-alive 下切换标的表单正确更新。

### 5.5 Redis 事件循环桥接（sync-safe 方法）

**问题**：`FundamentalDataService` / `StockCacheService` 运行在 `asyncio.to_thread`（同步线程），但 Redis 客户端是纯 async。直接 `asyncio.run()` 在已有 event loop 的线程中会报错。

**解决**：`RedisCacheService` 实现 `sync_*` 系列方法，通过 `asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=2)` 桥接；`main.py` lifespan 注入 `_loop = asyncio.get_running_loop()`；`_loop_ready()` 三重检查（is None / is_closed / is_running）。

---

## 六、最终成果

| 指标 | 数值 |
|------|------|
| 后端 Python 文件 | ~24 个（services / agents / routers + Phase 1A–1E + Phase 2E-1） |
| 前端 Vue 文件 | 27 个（components / views / stores / styles） |
| 数据库业务表 | 5 张（industry_master / stock_industry_map / industry_hot_stock_snapshot / analysis_reports / watchlist_items） |
| A股行业覆盖 | 5,166 只 A 股 / 30 个申万一级行业 |
| 并行分析时延 | 35–45 秒（vs 串行 120s，约 3× 提升） |
| Redis 速度比 | R1~3000–20000x / R2~400–600x / R3~400x |
| Build 产物 | 75 modules，全部 exit 0 |
| P0 故障 | 0 |
| 已完成 STAR 里程碑 | 11 个（STAR 1–11） |
| 当前版本 | MVP v0.7 |

---

## 七、当前限制

| 限制项 | 说明 |
|--------|------|
| 仅支持收盘价快照 | 无实时行情推送（WebSocket/SSE） |
| 无技术面图表 | K线、MACD、RSI 仅有数值，无可视化 |
| HK 市场动态同行 | 申万行业数据仅覆盖 A 股，港股仍依赖 PEER_MAP |
| 801850 美容护理 | swsresearch API 返回 0 条成分股，暂缺该行业动态同行 |
| 无单元测试 | 逻辑验证依赖 smoke test 脚本和代码审查 |
| 移动端适配 | 当前布局仅针对桌面浏览器优化 |
| Alembic 迁移 | 新表使用 `create_all`；已有表结构修改需引入 Alembic |

---

## 八、后续计划

按优先级：

1. **技术面图表**：ECharts 或 lightweight-charts 实现 K线 + 指标可视化
2. **Router 导航守卫**：`beforeEach` guard，未登录重定向（当前依赖 App.vue v-if）
3. **请求超时提示**：`AbortController`（45s），超时友好提示
4. **Vite 5 → 6.x 升级**：解决 CJS 警告和 esbuild 漏洞
5. **warningMap 单元测试**：Vitest 覆盖核心工具函数
6. **HK 市场同行扩展**：探索港股行业分类数据源

---

## 九、后续架构演进：从自定义 Coordinator 到 LangGraph

> **当前状态**：项目采用**自定义多 Agent Coordinator**，未使用 LangGraph 或任何工作流框架。LangGraph 是下一阶段的计划引入目标。

### 9.1 当前架构（MVP v0.7）

```
POST /analysis/comprehensive
        ↓
ComprehensiveAnalysisCoordinator.analyze_async()
        ↓
asyncio.gather(
    to_thread(technical_agent.analyze),
    to_thread(fundamental_agent.analyze),
    to_thread(news_agent.analyze),
    peer_agent.analyze_async(),
)
        ↓
综合报告 LLM 调用
        ↓
返回 {report, sections, metadata, warnings, agents}
```

**技术栈**：FastAPI + 自定义 Coordinator + `asyncio.gather / asyncio.to_thread`

**优势**：
- 实现简单，无额外框架依赖
- 调试路径直接，错误栈清晰
- 4 Agent 完全并行，时延控制在 35–45s

### 9.2 当前局限

| 局限项 | 具体表现 |
|--------|---------|
| 状态不可持久化 | 一次请求内部状态（Agent 输出、中间结果）仅存内存；请求结束即销毁，无法断点恢复 |
| 条件分支有限 | 当前是"4 Agent 全部并行"的固定流程；无法基于技术面结果动态决定是否跳过或加深某个 Agent |
| 失败重试不标准化 | 单个 Agent 失败仅做 `try/except` 捕获并标记 `failed`；无自动重试、超时退避、部分重跑机制 |
| 无法可视化工作流 | Agent 的执行图只存在于代码中；无法在 UI 或监控系统中可视化当前执行到哪一步 |
| Human-in-the-loop 困难 | 当前无法在中间步骤暂停、等待用户确认后继续（例如：基本面 Agent 提示"数据质量低，是否继续？"） |

### 9.3 LangGraph 目标状态

引入 LangGraph 后，Coordinator 的核心概念映射为：

| 当前概念 | LangGraph 对应 |
|---------|---------------|
| `analyze_async()` 整体流程 | `StateGraph` |
| 单个 Agent（`TechnicalAnalystAgent` 等） | `Node` |
| Agent 输出传递给综合报告 | `Edge` |
| 基于 Agent 状态决定下一步 | `Conditional Edge` |
| 报告中间状态 | `State`（TypedDict） |
| 断点恢复 / 部分重跑 | `Checkpoint`（`MemorySaver` / `PostgresSaver`） |
| 用户确认继续 | `Human-in-the-loop`（`interrupt_before` / `interrupt_after`） |

**目标能力**：
- 技术面 Agent 完成后，可根据信号强弱决定是否触发加深分析（Conditional Edge）
- 支持断点续跑：LLM 超时后可从最后一个成功的 Node 重试，不重新执行已完成的 Agent
- 工作流状态可持久化到 PostgreSQL（Supabase 直接复用），支持异步轮询和历史回放
- Human-in-the-loop：在数据质量极差时暂停，等待用户确认是否继续生成报告

### 9.4 迁移策略

**核心原则：不直接替换旧接口，新增 v2 接口并行运行。**

```
# 保留（不改动）
POST /api/v1/analysis/comprehensive        ← 当前自定义 Coordinator

# 新增（LangGraph 版本，Phase L1）
POST /api/v1/analysis/comprehensive-v2    ← LangGraph StateGraph
```

迁移步骤：
1. **Phase L1-a**：将现有 4 个 Agent 包装为 LangGraph Node，State 定义为当前 `metadata` dict 的 TypedDict 形式
2. **Phase L1-b**：添加 `Checkpoint`，验证断点恢复行为
3. **Phase L1-c**：添加第一个 `Conditional Edge`（技术面信号强度 → 决定是否加深分析）
4. **Phase L1-d**：在监控和日志稳定后，逐步将前端流量切换到 `-v2` 接口
5. 旧接口在过渡期保留，不强制弃用

---

*文档更新于 2026-05-29*
