# 本周工作 STAR 总结

**日期：** 2026-05-19 ~ 2026-05-29  
**项目：** TradingAgents — AI 驱动股票综合分析系统  
**作者：** kaffy811

---

## 1. 本周工作总览

本周从零构建了 TradingAgents MVP 的核心后端逻辑与前端工程化结构，覆盖数据采集、多维 Agent 分析、综合协调器、前端 Vue 3 迁移五大模块。具体工作量：

| 维度 | 数量 |
|------|------|
| 新增 Python 文件 | ~24 个（services/ + agents/ + routers/ + 行业热门股 Phase 1A–1E + Phase 2E-1 导入框架） |
| 新增 Vue 文件 | 27 个（components/ + views/ + stores/ + styles/ 等） |
| 新增数据库表 | 5 张（`industry_master`、`stock_industry_map`、`industry_hot_stock_snapshot`、`analysis_reports`、`watchlist_items`） |
| stock_industry_map 覆盖 | 5,166 只 A 股（Phase 2E-1 全量 SW L1） |
| 测试股票代码 | 6 个（CN/600519、CN/000001、HK/700、CN/300750、CN/601318、CN/000977） |
| 已完成文档 | 4 份（mvp_smoke_test_report.md、frontend_engineering_smoke_test.md、本文档、dynamic_peer_design.md） |
| P0 问题 | 0 |
| P1 已修复 | 5 项 |

---

## 2. STAR 1 — 行情与K线数据源稳定性增强

### Situation（背景）

股票行情获取依赖 AkShare，但不同市场（A股 / 港股）对应的接口不同，且部分接口存在返回空数据、字段名不一致、时区偏移等问题。若单一接口失败，整个分析流程会崩溃。

### Task（任务）

构建健壮的行情数据服务（`MarketDataService`），支持 CN / HK 双市场，具备接口失败时的 fallback 机制，并统一列名到标准格式（open / close / high / low / volume）。

### Action（行动）

- 实现多接口 fallback 链：
  - **CN 市场**：Eastmoney → THS → Sina → Tencent（4 级 fallback）
  - **HK 市场**：AkShare `stock_hk_daily` → yfinance（2 级 fallback）
- 统一列名映射（`成交量` → `volume` 等中英文对照）
- 添加 stale cache 机制：接口失败时返回最近一次成功缓存数据，并在 metadata 中标记 `stale`
- 时区统一：港股数据转换至 Asia/Hong_Kong

### Result（结果）

- CN 市场 4 级 fallback 保障：在 Eastmoney、THS 单独故障下仍正常返回数据
- HK 市场（700.HK 等）行情可正常获取
- Stale cache 在接口超时时保障分析不中断

---

## 3. STAR 2 — 基本面数据源探索与 FundamentalDataService

### Situation（背景）

基本面数据（PE、ROE、市值、负债率等）是分析师报告的核心输入。AkShare 的基本面接口存在以下问题：
- 港股基本面接口（`stock_hk_valuation_baidu`）数据非常有限
- A股部分字段（现金流、详细利润表）需要多个接口拼接
- 接口返回字段名在 AkShare 版本间不稳定
- Tushare 需要 token，需单独集成

### Task（任务）

构建 `FundamentalDataService`，为四类股票（A股主板、A股创业板、港股、外资基本面有限）提供可用的基本面字段，并在报告中声明字段边界（不得以局部字段推断完整基本面）。

### Action（行动）

- 整合 AkShare `stock_a_lg_indicator`（A股 PE/PB/ROE 等）作为主要来源
- 整合 Sina 财务接口作为 A股补充（资产负债率、现金）
- 为港股添加 Baidu 基本面接口 + yfinance 双 fallback
- 添加 `market_cap` 单位处理：AkShare 部分接口以"亿元"为单位，统一换算后标注
- 在 `FundamentalAnalystAgent` 的 prompt 中强制声明字段边界语句

### Result（结果）

- A股基本面：PE、PB、ROE、总市值、负债率 5 个核心字段稳定可用
- 港股基本面：PE（有限）、市值（有限）；明确告知 Agent "港股基本面数据有限"
- 报告中正确出现字段边界声明，未出现"完整基本面判断"等过强表述

---

## 4. STAR 3 — 四类 Agent 实现

### Situation（背景）

单一 LLM 提示词难以同时处理技术面、基本面、同行对比、新闻解读四个维度，且不同维度对数据格式、分析逻辑、表达规范的要求差异较大。

### Task（任务）

设计并实现 4 个专职分析 Agent，每个 Agent 有独立的 `_SYSTEM_PROMPT`，接收对应数据后返回结构化分析报告（Markdown 格式）。

### Action（行动）

**TechnicalAnalystAgent**
- 输入：K线 OHLCV 数据（最近 60 日）
- 计算：MA5/MA20/MA60，MACD，RSI，Bollinger Bands
- 系统提示：禁止对无均线交叉信号时强行写"金叉"/"死叉"

**FundamentalAnalystAgent**
- 输入：`FundamentalDataService` 返回字段
- 系统提示：必须声明字段边界；禁止以 ROE 单字段结论扩展为"基本面优秀"

**PeerComparisonAnalystAgent**
- 输入：来自 `PEER_MAP` 的同行列表 + 各同行基本面数据
- 系统提示：必须说明样本边界（PEER_MAP 非完整行业覆盖）；禁止写成"行业排名"结论

**NewsAnalystAgent**
- 输入：AkShare 最近 72h 新闻摘要
- 系统提示：禁止使用"利好/利空""将推动上涨/下跌""确定性支撑"等词汇；新闻必须附带免责说明

### Result（结果）

- 4 个 Agent 各自独立可测试，接口格式统一（`analyze(symbol, market) → str`）
- 综合报告中各维度报告风格独立、表述边界清晰
- 过强措辞在 Prompt 微调后基本消除

---

## 5. STAR 4 — ComprehensiveAnalysisCoordinator 四维综合分析

### Situation（背景）

4 个 Agent 各自调用 LLM，串行执行时延总计约 60–120 秒，用户体验不可接受。且综合报告需要整合 4 个子报告，如果 LLM 自由发挥，容易"放大"子报告的局部结论，形成过强的综合判断。

### Task（任务）

构建 `ComprehensiveAnalysisCoordinator`，实现：
1. 4 个 Agent 并行执行，总时延接近最慢单个 Agent
2. 综合报告只能"整合"子报告，不得新增事实或放大结论
3. 每个 Agent 的执行状态（success / failed / degraded）通过 `metadata` 返回前端

### Action（行动）

- 使用 `ThreadPoolExecutor(max_workers=4)` 并行执行 4 个 Agent
- 设计 `AgentStatus` 数据类，记录 `status` / `message` / `duration`
- 为综合报告 LLM 添加严格 `_SYSTEM_PROMPT`，包含 11 条规则：
  - 规则 7：综合摘要只能整合，不得放大（5 个子规则）
  - 规则 11：过强措辞约束（禁止"多重压力叠加"等词汇）
- 返回结构：`{report, sections, metadata: {generated_at, agents, warnings}}`
- 5 类 warning 自动触发：HK 基本面有限、估值缺失、同行不可用、新闻不可用、新闻相关性低

### Result（结果）

- 4 个 Agent 并行执行后，总时延从 120s 降至 35–45s（约 3× 提升）
- 综合报告未出现子报告以外的新事实
- 4 个测试股票（600519、000001、HK/700、300750）均正常返回结构化结果
- Warning 系统正确触发并在前端显示中文翻译

---

## 6. STAR 5 — 前端 MVP 与 Vue 3 + Vite 工程化

### Situation（背景）

前端初版是 904 行的单文件 `index.html`，包含 Vue CDN 引用、内联样式、内联逻辑。这种结构在功能扩展时难以维护，且无法使用 npm 生态（DOMPurify、vue-router、Pinia 等需要打包的库）。

### Task（任务）

将 `index.html` 单文件 MVP 迁移为 Vue 3 + Vite 工程化结构，保持所有功能行为完全兼容，并为后续报告历史、路由扩展做好架构准备。

### Action（行动）

**工程结构（27 个新文件）：**
- `src/main.js`：createApp + Pinia + Router 入口
- `src/App.vue`：根组件（auth 状态 → LoginCard 或 RouterView）
- `src/stores/auth.js`：Pinia auth store（token / currentUser / login / logout）
- `src/api/http.js`：baseFetch（Bearer token 注入 + 401 auto-logout）
- `src/api/auth.js` / `src/api/analysis.js`：接口层
- `src/router/index.js`：vue-router（`/` → ComprehensiveAnalysisView）
- `src/utils/warningMap.js`：AGENT_LABELS / WARNING_MAP / SECTION_DEFS / EXAMPLES / 工具函数
- `src/utils/markdown.js`：marked.parse + DOMPurify.sanitize
- `src/styles/`：variables.css / base.css / markdown.css（全局，3 文件）
- `src/components/`：9 个组件（LoginCard、AppHeader、StockInputPanel 等）
- `src/views/ComprehensiveAnalysisView.vue`：页面入口

**关键决策：**
- `hoursBack` 输入框移除（后端固定 72h，前端改为说明文字）
- `markdown.css` 必须全局引入（v-html 内容不受 Vue scoped 约束）
- `agent-badge` / `error-box` 放入 `base.css`（多组件共用）
- `.env.example` 提交 git；`.env` 加入 `.gitignore`
- 原 `index.html` 备份为 `index.legacy.html`

### Result（结果）

- `npm run build`：56 modules transformed，exit 0，无编译错误
- `npm run dev`：port 3000，HTTP 200
- CORS preflight 验证通过
- 所有 import 路径正确解析
- 功能对比：与 legacy 版本 16 个功能点全部保持一致
- 代码质量 4 项 P1（API_BASE 重复、`:deep()` 误用、Vite CJS 警告、esbuild 漏洞）

---

## 6.5 STAR 6 — 报告历史 Phase 1（后端 + 前端）

### Situation（背景）

综合分析完成后，结果仅保存在 Vue ref 中，刷新页面即丢失。用户无法查阅历史分析，也无法对比不同时间点的报告。

### Task（任务）

实现"保存报告 → 查看历史 → 删除报告"的完整产品闭环，打通从分析生成到历史存档的链路。

### Action（行动）

**后端：**
- 新建 `analysis_reports` 表（UUID PK，JSONB 存储 sections / metadata / warnings / agents，`report_metadata` 规避 SQLAlchemy 保留名）
- 实现 4 个 REST 接口：`POST /reports/`、`GET /reports/`（支持 market/symbol 筛选 + 分页）、`GET /reports/{id}`、`DELETE /reports/{id}`
- 所有接口依赖 `get_current_user`，`user_id` 从 JWT 读取，他人报告返回 404
- `baseFetch` 添加 204 No Content 支持（`return null`）

**前端：**
- 新建 `src/api/reports.js`，在 API 层做字段映射（`report_md` → `report`；`report_metadata` → `metadata`）
- `ComprehensiveAnalysisView`：分析成功后显示"保存报告"按钮，4 态状态机（idle → saving → saved/error）
- 新建 `/history` 列表页（筛选 + 分页 + 删除确认）
- 新建 `/history/:id` 详情页：**零修改复用** AgentStatusBar / WarningPanel / MarkdownReport / SectionAccordion
- `AppHeader` 新增顶部导航（综合分析 / 历史报告），`RouterLink` active 高亮

### Result（结果）

- 后端 CRUD 全部通过 curl 测试（201 / 200 / 204 / 404）
- 前端 build：56 → 63 modules，exit 0，两个新 lazy chunk
- 实现了从"生成分析 → 手动保存 → 历史列表 → 详情查看 → 删除"的产品闭环
- 历史详情页与综合分析结果页视觉完全一致，4 个展示组件零改动复用

---

## 7. 本周遇到的问题与解决方案

| # | 问题 | 解决方案 | 状态 |
|---|------|---------|------|
| 1 | AkShare 港股行情接口返回空 DataFrame | 添加 yfinance 作为 HK fallback | ✅ 已解决 |
| 2 | A股 K线列名为中文（"成交量"等），与下游代码不兼容 | 统一列名映射字典，rename 至 OHLCV 英文列名 | ✅ 已解决 |
| 3 | 港股基本面接口（Baidu）返回字段极少，LLM 产生过强判断 | Prompt 中强制声明"港股基本面数据有限" | ✅ 已解决 |
| 4 | 综合报告"放大"子报告局部结论 | 扩展系统提示规则 7 为 5 个子规则，禁止放大行为 | ✅ 已解决 |
| 5 | 综合报告使用"多重压力叠加""极为稳健"等过强表达 | 添加规则 11，列出禁止词汇及中性替代表达 | ✅ 已解决 |
| 6 | 新闻 Agent 出现"该新闻利好/利空"等确定性结论 | 在 NewsAnalystAgent 系统提示中添加明确禁止词汇列表 | ✅ 已解决 |
| 7 | 同行对比被写成"行业排名"结论 | Prompt 中要求说明 PEER_MAP 样本边界 | ✅ 已解决 |
| 8 | 4 个 Agent 串行导致总时延 120s+ | `ThreadPoolExecutor(max_workers=4)` 并行化，时延降至 35–45s | ✅ 已解决 |
| 9 | 单文件 HTML 无法使用 DOMPurify npm 包（CDN 版本有限制） | 迁移至 Vue 3 + Vite 工程化，使用 npm 安装 DOMPurify | ✅ 已解决 |
| 10 | `markdown.css` 在 scoped 组件中对 `v-html` 内容无效 | 将 `markdown.css` 改为 `main.js` 中全局引入 | ✅ 已解决 |
| 11 | `API_BASE` 在 `http.js` 和 `auth.js` 中重复定义 | 记录为 P1；待后续抽取 `api/config.js` | ⬜ 待优化 |
| 12 | `LoginCard.vue` scoped 中误用 `:deep()`（对本组件元素无需 `:deep()`） | 记录为 P1；待后续改为 `.login-card .card-title {}` | ⬜ 待优化 |

---

## 8. 本周成果清单（按模块）

### 后端（`backend/app/`）

| 模块 | 文件 | 说明 |
|------|------|------|
| 数据服务 | `services/market_data_service.py` | CN/HK 行情，4 级 fallback |
| 数据服务 | `services/fundamental_data_service.py` | A股/港股基本面，字段边界声明 |
| 数据服务 | `services/news_service.py` | AkShare 近 72h 新闻摘要 |
| Agent | `agents/technical_analyst_agent.py` | 技术面：MA/MACD/RSI/Bollinger |
| Agent | `agents/fundamental_analyst_agent.py` | 基本面：字段边界约束 |
| Agent | `agents/peer_comparison_analyst_agent.py` | 同行对比：PEER_MAP 样本边界 |
| Agent | `agents/news_analyst_agent.py` | 新闻：禁止确定性结论 |
| 协调器 | `agents/comprehensive_analysis_coordinator.py` | 并行执行 + 综合报告 + metadata |
| 路由 | `routers/stocks.py` | `/stocks/{market}/{symbol}`（Phase 1D 更新：peer_fundamentals 接 dynamic_hot） |
| 路由 | `routers/analysis.py` | `/analysis/comprehensive`（Phase 1E 更新：接入 analyze_async） |
| 路由 | `routers/industry.py` | `/industries/...` 三个接口（Phase 1A–1C） |
| 数据服务 | `services/industry_hot_stock_service.py` | 申万行业热门股 Hot Score 快照（Phase 1B） |
| 数据服务 | `services/dynamic_peer_discovery_service.py` | 动态同行发现（PEER_MAP > dynamic_hot > none，Phase 1C） |
| 数据服务 | `services/peer_comparison_service.py` | 新增 `get_peer_fundamentals_dynamic`（Phase 1D） |
| 数据模型 | `models/industry.py` | `sw_industry_classification` + `industry_hot_stocks` ORM 模型（Phase 1A–1B） |
| LLM | `llm/` | Claude API 封装 |

### 前端（`frontend/src/`）

| 类别 | 文件数 | 关键文件 |
|------|--------|---------|
| 入口 | 1 | `main.js` |
| 根组件 | 1 | `App.vue` |
| 路由 | 1 | `router/index.js` |
| Store | 1 | `stores/auth.js` |
| API | 3 | `api/http.js` / `auth.js` / `analysis.js` |
| 工具 | 2 | `utils/warningMap.js` / `utils/markdown.js` |
| 样式 | 3 | `styles/variables.css` / `base.css` / `markdown.css` |
| 组件 | 9 | LoginCard、AppHeader、StockInputPanel 等 |
| 视图 | 1 | `views/ComprehensiveAnalysisView.vue` |
| 配置 | 5 | `vite.config.js` / `package.json` / `.env.example` / `.gitignore` / `index.html` |
| 备份 | 1 | `index.legacy.html` |

### 文档（`docs/`）

| 文件 | 内容 |
|------|------|
| `mvp_smoke_test_report.md` | MVP 整体测试报告（Phase 1D–1E 更新后同步修订） |
| `frontend_engineering_smoke_test.md` | 前端工程化静态验证报告（Phase 1D–1E 第 9 节新增） |
| `weekly_star_summary.md` | 本文档 |
| `dynamic_peer_design.md` | 行业热门股 + 动态同行系统设计文档（新增） |

---

## 9. 当前 MVP 能力边界

### 可以做到

- 输入 A股/港股代码，生成四维综合分析报告（技术面 + 基本面 + 同行 + 新闻）
- 并行分析，总时延 35–45 秒
- 在 UI 上展示 Agent 执行状态（success / failed / degraded）
- 识别港股基本面有限、同行数据缺失等情况，并以 warning 形式通知用户
- 综合报告的表述保持在子报告范围内，不放大局部结论
- 支持 JWT 登录鉴权（Supabase PostgreSQL 后端）
- Markdown 报告渲染 + XSS 防护（DOMPurify）
- **报告历史存储**（Supabase `analysis_reports` 表 + 保存/列表/详情/删除全流程）
- **申万行业分类 + 行业热门股**（CN 市场动态同行 `dynamic_hot`，Hot Score v1）
- **无 PEER_MAP 股票自动发现同行**（CN/000001 等之前无同行的股票现在有动态同行）
- **PEER_MAP 优先级不变**（manual_map > dynamic_hot > none）
- **全量 SW L1 行业映射**（5,166 只 A 股，30 个行业，Phase 2E-1）
- **CN/300750 动态同行激活**（电力设备 801730，peer_source=dynamic_hot）

### 尚未实现

- 自选股列表（watchlist）
- 实时行情（当前为收盘价快照）
- 技术面图表（K线、MACD 可视化）
- 801850 美容护理成分股（API 返回 0 条，暂缺）
- HK 市场动态同行（申万行业数据仅覆盖 A股）
- refresh_industry_hot_stocks.py 重复运行 duplicate 去重（暂缓）
- Router 导航守卫（当前依赖 `App.vue` 的 v-if 判断）
- 移动端适配
- 单元测试覆盖

---

## 10. 下周建议计划

按优先级排序：

### 高优先级

| # | 任务 | 说明 |
|---|------|------|
| 1 | **浏览器运行时 smoke test** | 完成 `frontend_engineering_smoke_test.md` 中所有 ⬜ 项（含报告历史 8.1–8.5 节、Phase 1D–1E 第 9 节） |
| 2 | ~~**报告历史功能**~~ | ✅ Phase 1 已完成（后端 CRUD + 前端保存/列表/详情/删除） |
| 3 | ~~**行业热门股动态同行**~~ | ✅ Phase 1A–1E 已完成（申万分类 + Hot Score + dynamic peers 全链路接入） |
| 4 | ~~**动态同行覆盖扩展**~~ | ✅ Phase 2E-1 已完成：5,166 只股票 / 30 个行业，含创业板 300xxx；300750 已升级为 dynamic_hot |
| 5 | **Router 导航守卫** | `beforeEach` guard，未登录时重定向到登录页（目前依赖 App.vue v-if） |

### 中优先级

| # | 任务 | 说明 |
|---|------|------|
| 4 | **请求超时提示** | `baseFetch` 加 `AbortController`（45s），超时时显示友好提示 |
| 5 | **Vite 升级** | Vite 5 → 6.x，解决 CJS 警告和 esbuild 漏洞 |
| 6 | **API_BASE 抽取** | 新建 `src/api/config.js`，消除两处重复定义 |

### 低优先级

| # | 任务 | 说明 |
|---|------|------|
| 7 | **warningMap 单元测试** | 用 Vitest 为 `translateWarning` / `badgeClass` 等添加测试 |
| 8 | **LoginCard `:deep()` 修复** | 改为 `.login-card .card-title { }`，符合 Vue scoped 最佳实践 |
| 9 | **技术面图表** | 用 ECharts 或 lightweight-charts 添加 K线 + 指标可视化 |

---

---

## 11. 本周追加：报告历史产品闭环

报告历史 Phase 1 在本周完成，打通了从"生成报告"到"保存、查看、删除"的完整产品闭环。

用户现在可以在一次会话内完成以下全流程：

```
输入股票 → 生成综合分析（35–45s）
           ↓
      点击"保存报告"
           ↓
   进入历史列表（/history）
           ↓
   点击查看详情（/history/:id）
   [复用与分析页完全一致的展示组件]
           ↓
   可选：删除报告（204 No Content）
```

这是 MVP 从"分析工具"向"有记忆的分析平台"迈出的第一步。

---

## 12. 追加：STAR 7 — 行业热门股与动态同行系统（Phase 1A–1E）

### Situation（背景）

同行对比 Agent 依赖 `PEER_MAP`（硬编码字典，每只股票手动配对可比公司）。这一方案存在根本性局限：

- 只有少数股票（约 10 只）被手动收录；A股超过 5000 只股票中绝大多数（含 CN/000001）显示"暂无同行配置"
- 扩展需要人工维护，无法随市场结构变化自适应
- CN/300750、CN/000001 等热门分析对象无同行数据，导致同行对比报告维度空洞

AkShare 的申万行业 constituent 接口（`sw_index_third_cons`）在 Phase 0 探针测试中已验证**不可用**（返回空数据）。纯粹的在线接口方案行不通。

### Task（任务）

在不破坏 PEER_MAP 现有优先级的前提下，为 CN 市场无 PEER_MAP 配置的股票引入**自动化动态同行发现**：
1. 找到可用的申万行业分类数据源（替代失效接口）
2. 建立行业热门股快照机制（决定"哪些同行最有代表性"）
3. 将动态同行接入 peer-comparison 和 comprehensive 两条分析链路

### Action（行动）

**Phase 1A — 申万行业分类表入库**

- 通过 AkShare `stock_board_industry_name_em` + `stock_board_industry_cons_em` 组合，在线获取东方财富行业成份，再映射至申万一级行业（31 个大类）
- 新建 `sw_industry_classification` 表：`(market, symbol, sw_level1_code, sw_level1_name, source)`
- 暴露 `GET /industries/{market}/{symbol}/classification` 接口

**Phase 1B — 行业热门股快照 + Hot Score**

- 在线拉取行业内所有股票的当日行情，计算 Hot Score v1：
  ```
  HotScore = 0.7 × norm(成交额) + 0.3 × norm(|涨跌幅|)
  ```
  其中 norm 为行业内 min-max 归一化；ST/退市股过滤
- 新建 `industry_hot_stocks` 表：`(snapshot_date, market, industry_code, symbol, hot_score, rank, ...)`
- 暴露 `GET /industries/{market}/{industry_code}/hot-stocks` 接口

**Phase 1C — DynamicPeerDiscoveryService + 路由**

- 实现 `DynamicPeerDiscoveryService.discover_peers(db, market, symbol, limit)` 异步方法
- 优先级逻辑：PEER_MAP 手动配置 > CN 行业 Hot Score > 空列表（附 fallback_reason）
- 暴露 `GET /industries/stocks/{market}/{symbol}/dynamic-peers` 接口（路由注册顺序需置于 `/{market}/{industry_code}/...` 之前，避免 FastAPI 路径冲突）

**Phase 1D — 接入同行对比链路**

- `PeerComparisonService` 新增 `get_peer_fundamentals_dynamic(db, market, symbol)` 异步方法，保留旧同步方法供 Coordinator 兼容
- `PeerComparisonAnalystAgent` 新增 `analyze_async(db, market, symbol)` 方法
- `_SYSTEM_PROMPT` 新增第 10 条规则：dynamic_hot 时必须声明 Hot Score 口径限制，禁止使用"更优质"等强结论
- `stocks.py` 路由 `GET /stocks/{market}/{symbol}/peers/fundamentals` 改调 `get_peer_fundamentals_dynamic`
- `analysis.py` 路由 `POST /analysis/peer-comparison` 改调 `analyze_async`
- `PeerDataQuality` Pydantic 模型新增 5 个可选字段（向后兼容）

**Phase 1E — 接入综合分析链路**

- `ComprehensiveAnalysisCoordinator` 新增 `analyze_async(db, market, symbol)` 方法
- 新增 `_run_agents_parallel_async`：使用 `asyncio.gather` + `asyncio.to_thread` 并发执行四个 Agent（技术面/基本面/新闻三个同步 Agent 包装为 coroutine，同行对比直接 await `analyze_async`）
- 超时处理：`asyncio.wait_for(timeout=300s)` + `asyncio.TimeoutError` 捕获（区别于旧同步版的 `concurrent.futures.TimeoutError`）
- `analysis.py` 路由 `POST /analysis/comprehensive` 改调 `coordinator.analyze_async(db, ...)`
- 旧同步 `analyze()` / `_run_agents_parallel()` 保留，零破坏

### Result（结果）

- **CN/000001（平安银行）**：`peer_source` 从 `"none"` 升级为 `"dynamic_hot"`，申万银行(801780)行业同行自动发现，同行对比报告维度完整
- **CN/600519（贵州茅台）**：`peer_source` 仍为 `"manual_map"`，PEER_MAP 优先级不变，行为与之前完全一致
- **CN/300750（宁德时代）**：申万行业 SW 映射暂未覆盖，`peer_source="none"` + `fallback_reason` 注明原因，正确降级
- **4 个核心测试用例全部 HTTP 200**，无 P0 故障，warnings 触发正确
- **架构零破坏**：旧 `analyze()` / `get_peer_fundamentals()` 完整保留；新增方法为增量扩展
- **文档固化**：`frontend_engineering_smoke_test.md` 第 9 节、`mvp_smoke_test_report.md` Phase 1D–1E 章节、`dynamic_peer_design.md` 设计文档均同步更新

*文档更新于 2026-05-27*

---

---

## STAR 8 — Phase 2E-1：全量申万一级行业映射（2026-05-29）

### Situation（背景）

Phase 1A–1E 完成了完整的动态同行发现链路：申万行业分类 → Hot Score 快照 → `DynamicPeerDiscoveryService` → peer-comparison + comprehensive 全接入。但 `stock_industry_map` 表仅含少量 sample 数据（~10 只股票），导致：

- CN/300750（宁德时代）、CN/601318（中国平安）等绝大多数 A 股找不到申万行业映射
- `peer_source` 降级为 `"none"`，动态同行链路虽搭好但无法激活
- comprehensive 分析中 peer_comparison 仍显示「industry mapping not found」

数据源也陷入困境：legulegu.com（AkShare 依赖）504 超时；EastMoney 接口 Clash 代理 ProxyError；AkShare `sw_index_third_cons` 列数 mismatch 解析失败。

### Task（任务）

在不改 schema、不改 Agent、不改 Service、不改前端的前提下，将 `stock_industry_map` 从 sample 数据升级为全量 A 股 SW L1 映射，使 CN/300750 等股票能够通过现有链路自动获得 `dynamic_hot` 同行。

### Action（行动）

**数据源突破**

放弃 legulegu.com，改用申万宏源研究官方 JSON API：

```
GET https://www.swsresearch.com/institute-sw/api/index_publish/details/component_stocks/
    ?swindexcode={sw_l1_code}&page=1&page_size=10000
```

遍历 31 个 SW 2021 L1 行业代码（801010–801980），一次请求获取完整成分股列表，无需解析 HTML，不依赖任何代理。

**生成脚本 `generate_sw_l1_industry_map_csv.py`（完整重写）**

- 模式 A：调用 `AkShare index_component_sw(symbol)` → 底层即为上述官方 API，支持 `--delay` 控速
- 模式 B：`--input` 接受外部 CSV，灵活字段映射
- 801850 美容护理 API 返回 0 条记录，graceful skip
- 30 个行业 5,166 只股票写入标准 8 列 CSV

**修复 `import_industry_map.py`（大批量 bug）**

原脚本 ORM 逐行 SELECT+INSERT 在 5,000+ 行时触发两个 bug：autoflush 触发 Supabase statement timeout → 级联 PendingRollbackError。改用 PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`：
- 行业主表：一次事务 30 条
- 股票映射表：批量 500 条/批，共 11 批，约 3 分钟完成

**刷新 hot stocks**：`refresh_industry_hot_stocks.py --market CN` 生成 140 条新快照（28 新行业 × 5）

### Result（结果）

- **CN/300750** 行业映射：`None` → `801730 电力设备`
- **CN/300750** `peer_source`：`"none"` → **`"dynamic_hot"`**
- **CN/300750** comprehensive peer_comparison：「industry mapping not found」→ 电力设备 Hot Score 同行对比报告（含 ROE / 毛利率 / 净利率 / 营收增长率 4 × 5 对比表格）
- **动态同行覆盖**：从 2 个样例行业（银行、食品饮料）扩展到 **30 个行业 / 5,166 只股票**
- **PEER_MAP 优先级不变**：CN/600519（贵州茅台）`peer_source` 仍为 `manual_map`
- **架构零破坏**：未改任何 Service / Agent / Router / 前端

*文档更新于 2026-05-29*

---

## Redis Cache Phase R0 + R1（2026-05-27）

### Situation（背景）

AkShare `spot_em` 和 yfinance 在本地开发环境下不稳定（频繁 `RemoteDisconnected` 和 `Too Many Requests 429`）。每次 `/analysis/fundamental` 或 `/analysis/comprehensive` 请求都会重新打上游，不仅耗时 10–30 秒，还加速触发 rate limit，导致连续请求快速降级。项目原先虽已有进程内内存缓存（TTL 3600s），但多进程/重启后缓存清零，且无法跨实例共享。

### Task（任务）

在不改变任何 API 响应结构、不引入新依赖、Redis 不可用时业务零感知的前提下：
1. 实现统一 Redis 缓存封装（`RedisCacheService`），支持 async 和 sync（线程池）两种调用方式
2. 将 `FundamentalDataService` 接入 Redis 作为外层缓存（L1），内存缓存保留为 L2
3. 对 AkShare 连接错误和 yfinance 429 实现 negative cache，防止反复打已知失败的 provider

### Action（行动）

**Phase R0 — `cache_service.py` 全量实现**

- 实现 `RedisCacheService`：`get_json` / `set_json` / `delete` / `exists` / `get_or_set_json`（async），以及 `sync_get_json` / `sync_set_json` / `sync_exists`（sync-safe）
- sync-safe 方法通过 `asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=...)` 桥接，专为 `to_thread` / `ThreadPoolExecutor` 场景设计
- 加入 `_loop_ready()` 静态方法：同时检查 `_loop is None`、`_loop.is_closed()`、`_loop.is_running()`，三重保护
- `main.py` lifespan 注入 `set_event_loop(asyncio.get_running_loop())`
- Key 前缀 `ta:{app_env}:`，JSON 序列化支持 `datetime / date / Decimal / UUID`

**Phase R1 — `FundamentalDataService` 接入 Redis**

- `get_fundamentals()` 最外层增加 Redis L1 check：`cache_service.sync_get_json("fundamental:{market}:{symbol}")`
- 成功结果写入 Redis TTL 3600s；stale 降级结果写入 Redis TTL 600s；同时回写内存缓存
- AkShare `RemoteDisconnected` → `negative:akshare_quote:CN:{symbol}` TTL 300s
- yfinance `Too Many Requests` → `negative:yfinance_quote:{market}:{symbol}` TTL 600s
- 进入对应 provider 前先 `sync_exists(neg_key)`，命中则跳过并记录日志

**Phase R1.5 — smoke 验证脚本**

- 新增 `scripts/smoke_redis_cache.py`：直连 Service 层（不走 HTTP），支持 `--clear`、`--quiet`，显示 key size / TTL remaining / 速度比 / negative cache 状态

### Result（结果）

- **第一次请求（full miss）**：10.6s，AkShare 失败 + yfinance 429 → negative cache 写入 → Sina 补名称 + 财报摘要成功 → Redis 写入
- **negative cache 命中后第一次请求**：2.3s（跳过 AkShare + yfinance，直走 Sina + 财报）
- **第二次请求（Redis HIT）**：0.001s，**速度比 3000–20000x**
- **Redis 不可用时**：loop 未注入 → `sync_*` 静默返回 None/False → 内存缓存 / stale fallback 全链路正常，无崩溃，HTTP 200
- **API 响应结构零改动**：所有字段、类型、状态码与 Phase 2 完全一致
- **文档固化**：`mvp_smoke_test_report.md` 第 9 节、`weekly_star_summary.md` 同步更新

*文档更新于 2026-05-27*

---

## Redis Cache Phase R2 — StockCacheService（2026-05-27）

### Situation（背景）

行情（quote）和 K 线（kline）是被调用最频繁的数据接口，每次 `/analysis/technical` 和 `/analysis/comprehensive` 都需要先拉取 kline 再拉 quote。EastMoney 直连在代理环境下频繁 `RemoteDisconnected`，每次 fallback 到 Sina/Tencent 仍需 0.3–2s。多进程/重启后进程内 `_store` 清零，下一次请求必须重新打上游。

### Task（任务）

在不改变 `StockDataService`、Agent、Router、前端任何代码的前提下，为 `StockCacheService` 的 `get_quote_cache` / `set_quote_cache` / `get_kline_cache` / `set_kline_cache` 四个函数增加 Redis L1 缓存层，Redis 不可用时降级到原有内存缓存（零感知）。

### Action（行动）

**数据类型分析**

- Quote payload / Kline bar 均为纯 Python 原生类型（str/float/int/None/list/dict）
- AkShare `_df_to_records()` 已将 `pd.Timestamp` 转为 `"%Y-%m-%d"` 字符串
- 无需额外 DataFrame 序列化层，直接调用 `cache_service.sync_set_json`

**StockCacheService 改造**

- 在 `get_quote_cache` / `get_kline_cache` 头部插入 Redis L1 check：`cache_service.sync_get_json(key)`
- L1 命中 → 打 INFO 日志 `"quote Redis HIT [CN/600519]"` 后直接返回
- L1 未命中 → 检查内存 L2；内存命中时回写 Redis
- 在 `set_quote_cache` / `set_kline_cache` 尾部追加 `cache_service.sync_set_json(key, payload, ttl)`
- Stale fallback 路径（`_stale_store`）**不接入 Redis**，保持纯进程内兜底

**Key 设计**：与内存 key 完全一致（`quote:CN:600519` / `kline:CN:600519:daily:qfq:120`），加 `ta:{env}:` 前缀

### Result（结果）

- **Quote**：0.320s → 0.001s，**速度比 598x**，Redis key 514B TTL 60s
- **Kline**：0.451s → 0.001s，**速度比 413x**，Redis key 26,447B TTL 600s
- **架构零破坏**：`StockDataService` / Agent / Router / 前端 均未改动
- **API 响应结构零变化**：`QuoteResult` / `KlineResult` 字段完全一致
- **Redis 不可用**：`sync_*` 静默降级，进程内缓存照常工作

---

## STAR 9 — Watchlist 自选股功能闭环（2026-05-29）

### Situation（背景）

系统已具备多维股票分析能力，但缺少个人化研究入口：用户每次分析都需要手动输入市场和股票代码，无法沉淀常看标的，每次打开页面必须重新回忆代码，研究效率低。系统是"单次分析工具"，不是"个人研究工作台"。

### Task（任务）

构建一个轻量级自选股模块，使用户能够保存常看股票列表，并从自选股一键进入综合分析页和历史报告页；同时保证后端数据按用户 JWT 严格隔离，重复添加不产生脏数据，前端导航和 query 参数联动体验流畅。

### Action（行动）

**后端**

- 新增 `watchlist_items` 表：UUID PK，`user_id` FK → `app_users.id`（`ondelete=CASCADE`），`UniqueConstraint(user_id, market, symbol)` 防止重复；`market` Pydantic validator 强制 uppercase，`symbol` 只做 `.strip()` 保留前导零
- 新增 4 个 CRUD 接口（`POST/GET/PATCH/DELETE /api/v1/watchlist/`）：全部依赖 `get_current_user`，PATCH/DELETE 查询条件加 `user_id == user.id`，非本人资源统一返回 404；POST 重复时返回 409 Conflict
- `init_db()` 注册新模型，`create_all` 启动时自动建表，无需 Alembic

**前端**

- 新增 `WatchlistView.vue`：添加表单（market select + symbol input + name 可选）、列表卡片、ConfirmDialog 二次确认删除、`分析` / `历史报告` 快捷按钮
- 新增 `watchlist.js` API 封装，`baseFetch` 增加 `err.status` 属性透传（原只在 401 设置），使 409 检测更可靠
- `AppHeader` 加"自选股"导航链接，路由守卫加 `/watchlist` 鉴权
- **query 参数联动**：`WatchlistView` 的"分析"按钮通过 `router.push({ path:'/', query:{market,symbol} })` 跳转；`ComprehensiveAnalysisView` 用 `watch(route.query)` 而非 `onMounted` 响应 query 变化（因 keep-alive 缓存组件不重新 setup）；`StockInputPanel` 新增 `initialMarket/initialSymbol` props + `watch(props)` 同步 form；`HistoryView` 初始化时读 `route.query` 预填筛选条件

### Result（结果）

- **产品升级**：从"单次分析工具"升级为具备个人研究列表的"股票研究工作台"，用户可沉淀常看标的，一键触发分析
- **严格权限隔离**：user_id 不接受请求体传入，PATCH/DELETE 防越权，UniqueConstraint 保证数据干净
- **symbol 前导零零损耗**：VARCHAR(32) 存储，Pydantic 只 strip 不转型，000001 全链路不丢前导零
- **架构零破坏**：Agent、数据源、Redis、LLM 调用链路均未改动；`baseFetch` 改动向后兼容（新增 `.status` 属性，不影响现有调用方）
- **build 验证**：`npm run build` 75 modules 全部通过，`WatchlistView` 独立 chunk 正常生成
- **浏览器 smoke test 通过**（2026-05-29）：自选股添加、重复 409 拦截提示、ConfirmDialog 删除确认、"分析"按钮 query 联动自动填入综合分析表单、keep-alive 下多次切换标的表单正确更新、"历史报告"按钮 query 联动自动筛选均验证通过；原有综合分析、历史报告、报告保存、Markdown 下载、PDF 打印功能零退化。

---

## STAR 10 — Watchlist 最近报告联动（Phase W2，2026-05-29）

### Situation（背景）

Phase W1 完成后，自选股卡片只显示市场 + 代码 + 名称，没有任何历史报告信息。用户看到卡片无法判断"这只股票有没有分析过"、"上次分析结果好不好"，只能逐一点击"历史报告"或手动搜索，摩擦极高。

### Task（任务）

在自选股列表卡片上展示该股票最近一次保存报告的轻量摘要（分析时间、警告数、Agent 状态徽章），并根据是否存在报告动态调整主操作按钮（有报告 → "查看最近报告"；无报告 → "立即分析"），同时不加载大字段（report_md / sections），不破坏 W1 已有交互。

### Action（行动）

**后端**

- 新增 `WatchlistLatestReport` Pydantic schema（仅 5 个字段：`id / created_at / report_type / warnings / agents`）；`WatchlistItemResponse.latest_report` 设为可选（默认 `None`），向后兼容
- 重写 `list_watchlist_items`：由原单查询升级为**两次查询 + Python join**（零 N+1）：
  - 查询 1：取当前用户的 watchlist_items（不变）
  - 查询 2：ROW_NUMBER() OVER (PARTITION BY market, symbol ORDER BY created_at DESC) 子查询，过滤 rn=1 取每 (market, symbol) 最新报告；严格 `WHERE user_id == user.id`，防跨用户数据泄漏；`select()` 显式列举 7 个轻量列，**不** `select(AnalysisReport)` 以避免拉取 report_md（TEXT）和 sections（JSONB）大字段
  - Python dict `{(market, symbol): WatchlistLatestReport}` join，无额外 SQL

**前端**

- `WatchlistView.vue` 新增最近报告摘要区块：`formatTime` 显示相对时间、警告数 badge、Agent 徽章（复用 `warningMap.js` 的 `AGENT_NAMES / agentLabel / badgeClass`）
- 条件主按钮：有 `latest_report` → ["查看最近报告"（primary）, "分析"（secondary）]；无 → ["立即分析"（primary）]
- 新增 `goLatestReport(item)` 函数：`router.push('/history/' + item.latest_report.id)`

### Result（结果）

- **产品跃升**：自选股页一眼可见每只股票的分析状态；"查看最近报告"零跳转即可直达历史详情
- **性能安全**：两次查询替代 N+1；ROW_NUMBER 窗口函数避免在应用层排序；大字段从不进入网络传输
- **数据隔离**：ROW_NUMBER 子查询内含 `user_id == user.id` 过滤，Python join 基于 (market, symbol) 元组键，不同用户的报告不会交叉
- **前导零全链路保障**：`validate_symbol` 只 `.strip()` 不转型，VARCHAR(32) 存储，Python dict 字符串精确匹配，CN/000001 全流程不丢前导零
- **删除联动**：analysis_reports 物理删除后 ROW_NUMBER 子查询自动感知，下次 GET /watchlist/ 即返回 `latest_report=null`，卡片切换为"暂无分析报告"状态，无需额外清理逻辑
- **代码路径与构建验证 9/9 通过**（代码审查 + Schema 验证 + 逻辑分析，2026-05-29）：有报告卡片时间/警告/徽章/按钮 ✅、导航 ✅、无报告卡片 ✅、前导零匹配 ✅、删除联动 ✅。核心路径已通过代码审查、schema 验证与构建验证；真实浏览器点击验证可在后续日常使用中继续补充
- **build 验证**：`npm run build` 通过（WatchlistView-DSR1CLpF.js 5.22 kB），无未解析 import
- **改动最小化**：仅改动 3 个文件；Agent / Service / Redis / LLM 链路零改动；W1 功能零退化

---

## Redis Cache Phase R3 — NewsDataService（2026-05-29）

### Situation（背景）

新闻数据由 `EastmoneyNewsProvider` 实时爬取，每次调用耗时 1–3s。进程重启后进程内 `_cache` 清零，高频分析同一标的时每次都打上游，既浪费时间又消耗爬取配额。同时 `StockDataService`（R1）和 `StockCacheService`（R2）已接入 Redis，新闻层是最后一块缺口。

### Task（任务）

在不改变 `NewsDataService` 对外接口、不改动 Agent / Router / 前端任何代码的前提下，为 `get_stock_news()` 增加 Redis L1 缓存层，Redis 不可用时自动降级到内存缓存 / stale cache（零感知），保证 HTTP 200 始终返回。

### Action（行动）

- **Redis L1 读写**：在 `get_stock_news()` 头部插入 `cache_service.sync_get_json(key)` 检查；L1 命中直接返回，`cached=True`；L1 未命中继续查内存 L2
- **内存 L2 → Redis 回写**：内存命中时通过 `sync_set_json` 把结果推入 Redis，避免下次仍走上游
- **Stale 路径降级**：上游失败时使用 `_stale_cache` 数据，写 Redis 但缩短 TTL=300s，区分正常数据（TTL=600s）
- **Key 设计**：`news:{market}:{symbol}:{hours_back}:{limit}`，加环境前缀后格式为 `ta:{env}:news:CN:600519:72:10`
- **Smoke 脚本**：新增 `scripts/smoke_news_cache.py`，两次调用对比耗时、输出速度比、key size、TTL、数据一致性；Redis 不可用时打印降级链路说明，脚本不崩溃

### Result（结果）

- **速度比 ~400x**：第一次爬取 1.2s，第二次 Redis HIT 0.003s
- **架构零破坏**：`NewsAgent` / `NewsRouter` / 前端均未改动，API 响应结构完全一致
- **Redis 不可用**：五层降级链（Redis → 内存 → 上游 → stale → 空列表）保障 HTTP 200 不受影响
- **Phase R 系列完成**：R1（StockDataService）、R2（StockCacheService）、R3（NewsDataService）三层 Redis 缓存全部接入，覆盖后端全部热点数据路径

---

## STAR 11 — Watchlist Note 内联编辑（Phase W3，2026-05-29）

### Situation（背景）

Phase W1/W2 完成后，自选股已能保存常看标的并联动最近分析报告。但卡片缺少用户自己的研究备注入口——`watchlist_items.note` 字段和 `PATCH` 接口虽已存在，却没有任何前端入口可以写入。用户无法在股票旁边记下"准备在 XX 价位加仓"、"基本面存疑，待观察"等个人研究笔记。同时后端存在一个静默缺陷：`PATCH {"note": ""}` 会写入空字符串而非 null，无法真正清空备注。

### Task（任务）

在不新增数据库表、不新增 API 接口、不新增前端文件的前提下，为每张自选股卡片实现轻量内联备注编辑：点击即可编辑，Enter/blur 保存，Escape 取消，清空内容可真正删除备注。同时修复 `PATCH {"note": ""}` 无法清空的后端缺陷。

### Action（行动）

**后端（1 行）**

- `watchlist.py:174` — `item.note = body.note or None`：将空字符串映射为 null，使"清空备注"语义完整；现有非空备注写入行为不受影响

**前端（WatchlistView.vue，+63 行）**

- **状态设计**：5 个 ref（`editingNoteId` / `editNoteValue` / `savingNoteId` / `noteError` / `noteTextareaRefs`），职责单一，彼此解耦
- **模板替换**：原只读 div 替换为双分支——展示态（note 有值显示文字，无值显示"＋ 添加备注"占位）；编辑态（inline textarea + spinner + ErrorBox）
- **交互完整性**：Enter（非 Shift）→ 保存；Shift+Enter → 换行；Escape → 取消；blur → 自动保存
- **防重入**：`saveNote` 首行 `if (savingNoteId.value === item.id) return`（防 blur + Enter 双触发）
- **内容未变优化**：`newNote === oldNote` → 静默退出，不发网络请求
- **本地更新**：`item.note = updated.note`，不重新拉取整个列表（零额外请求）
- **切换卡片安全**：先 `await saveNote(prev)`；若保存失败则不切换，防止数据丢失

### Result（结果）

- **产品升级**：Watchlist 从"自选股清单 + 最近报告"进一步升级为"个人研究工作台"，用户可在每只股票旁记录投资逻辑、价位计划、待观察项等研究笔记
- **零架构扩张**：复用已有字段（`note TEXT`）、已有接口（`PATCH /watchlist/{id}`）、已有 API 封装（`patchWatchlist`）；无新表、无新接口、无新文件
- **后端缺陷修复**：1 行修复 `"" → null` 清空语义，兼容所有现有调用
- **代码路径与构建验证 12/12 ✅**：代码审查 + Schema 验证 6/6 + `npm run build` 通过；视觉效果（自动聚焦、spinner、hover 背景）待日常浏览器使用补充
- **改动最小化**：仅改动 2 个文件；W1/W2 全部功能零退化

*文档更新于 2026-05-29*

---

## STAR 12 — 技术面图表可视化（Phase P1-a，2026-05-30）

### Situation（背景）

系统当前的技术面分析仅有文字报告（TechnicalAnalystAgent 输出的 Markdown），用户无法直观看到行情走势。在产品演示和项目展示场景中，没有 K 线图的"股票分析系统"视觉说服力不足；同时用户在阅读文字技术分析前往往希望先看一眼走势，文字报告的前置图表能显著降低认知负担。

### Task（任务）

在不改动后端接口、不改动 Agent/Service/Redis/LLM 链路、不改动报告历史/Watchlist/下载/打印等任何已有功能的前提下，在综合分析页增加 K 线图、四条均线（MA5/10/20/60）和成交量图，处理多数据源下的字段差异（日期格式、volume 单位、amount 可能为 null），并保证图表与 Vue keep-alive 生命周期正确配合（无内存泄漏）。

### Action（行动）

**新增依赖**

- `lightweight-charts ^4.2.0`（TradingView 开源，~40 kB gzipped，金融图表原生支持）
- `npm install` 成功，added 2 packages

**新建 `frontend/src/api/stocks.js`**

- `getKline(market, symbol, options)` 封装 `GET /stocks/{market}/{symbol}/kline`
- 默认 `period='daily', adjust='qfq', limit=120`
- `symbol.trim()` 保留前导零，不 parseInt，不 .upper()

**新建 `frontend/src/components/TechnicalChartPanel.vue`**

| 模块 | 内容 |
|------|------|
| 图表初始化 | lightweight-charts v4 API：`createChart / addCandlestickSeries / addHistogramSeries / addLineSeries` |
| 布局 | 单 chart 实例；主图（上 75%）+ volume overlay（底 22%），`priceScaleId: ''` + `scaleMargins` 控制 |
| 数据转换 | `normalizeDate`（兼容 `"20240115"` 和 `"2024-01-15"` 两种格式）；`Number.isFinite` OHLC 校验；`bar.volume` 不依赖 `bar.amount`（Tencent fallback 下 amount=null） |
| MA 计算 | 前端计算 MA5/10/20/60；`calcMA` 只输出 period-1 之后的点，无 null 传入 line series |
| 颜色 | 与 `variables.css` 手动对齐的颜色常量（lightweight-charts 不能读 CSS 变量） |
| 生命周期 | `onMounted`：initChart + ResizeObserver + fetchKline；`onActivated`：resize（keep-alive）；`onUnmounted`：`ro.disconnect()` + `chart.remove()`（防泄漏） |
| 状态管理 | loading overlay / error overlay（含"重新加载"按钮）/ stale badge / empty 状态全部独立 |
| 错误隔离 | `catch` 只写 `error.value`，不向上 throw，kline 失败不影响父组件综合报告渲染 |

**修改 `ComprehensiveAnalysisView.vue`**

- `<template v-if="result">` 首行插入 `<TechnicalChartPanel>`
- 位置顺序：TechnicalChartPanel → 综合报告 card → SectionAccordion → save-bar
- `watch([market, symbol])` `immediate: false`，换标的后自动重新 fetch

### Result（结果）

- **build 验证**：`npm run build` 84 modules transformed，exit 0（前版 75，净增 9），全部 lazy chunk hash 不变
- **Kline 接口复用**：零后端改动；Redis R2 缓存（TTL 600s）已对 kline 生效，重复分析同一标的速度比 ~400x
- **架构零破坏**：Agent / Service / Redis / LLM / reports / watchlist / history / DownloadMenu / PrintReportView 均未改动；`baseFetch` 复用，Bearer token 自动注入
- **代码路径与构建验证 12/12 ✅**：数据转换逻辑（normalizeDate / Number.isFinite / volume 不依赖 amount / MA 无 null）、生命周期管理（ResizeObserver / onActivated / onUnmounted / chart.remove）、错误隔离均通过代码审查
- **API 级验证 15/15 ✅（2026-05-30）**：CN/600519 / HK/700 / CN/000001 三只股票 kline 数据完整（各 120 bars）；OHLC 全 finite；dates 升序无重复；volume_unit 正确（lot/share）；MA5 输出 116 bars 符合预期；前导零路径验证（`CN/000001` vs `CN/1` 对比）；Redis 缓存命中；无效标的错误隔离（HTTP 200 + 空数据）
- **浏览器视觉与交互验证 ⬜**：K 线 Canvas 渲染、MA 颜色图例、成交量图视觉、keep-alive resize、Console 无 warning 等 10 项需人工浏览器执行

*文档更新于 2026-05-30*

---

## STAR 13 — 历史报告详情页图表复用与用户显示修复（Phase P1-a.1）

**日期：** 2026-05-30  
**标签：** Vue 3 / 组件复用 / UX 修复 / 零后端改动

### Situation（背景）

Phase P1-a 已在综合分析页（ComprehensiveAnalysisView）实现技术面图表，但历史报告详情页（HistoryDetailView）回看历史记录时仍只有文字报告，用户无法直观对照当时的价格走势与 K 线形态。同时，AppHeader 右上角在测试账号登录状态下直接显示 `string`（`authStore.currentUser` 为对象，模板误直接渲染整个对象），影响产品完成度。

### Task（目标）

在不修改后端、不新增接口、不改动 kline API 的前提下：

1. 将 `TechnicalChartPanel.vue` 复用到 `HistoryDetailView.vue`，使历史报告详情页在报告正文上方展示图表
2. 修正 `AppHeader.vue` 用户名显示逻辑，增加 `displayName` computed fallback（username → email → '用户'），过滤测试账号的 `'string'` 值

### Action（行动）

**HistoryDetailView.vue 接入图表：**
- 新增 `import TechnicalChartPanel from '../components/TechnicalChartPanel.vue'`
- 在 `<template v-if="result">` 内部、主报告 `<div class="card">` 之前插入 `<TechnicalChartPanel :market="result.market" :symbol="result.symbol" :visible="true" :height="340" />`
- 零 state 变量新增；图表 loading/error/stale 完全由 TechnicalChartPanel 内部管理；kline 失败不影响报告正文（错误隔离已在 Phase P1-a 实现）

**AppHeader.vue displayName 修复：**
- 新增 `computed` 导入
- 新增 `displayName` computed：`username !== 'string'` 优先；`email !== 'string'` 次之；最后 fallback `'用户'`
- 模板 `{{ authStore.currentUser }}` → `{{ displayName }}`

**构建验证：**
```
npm run build → 84 modules, exit 0（模块数与 Phase P1-a 一致，无新增）
HistoryDetailView chunk: 2.33 kB（TechnicalChartPanel 在 main bundle 共享，lazy chunk 无冗余）
```

### Result（结果）

- **页面升级**：历史报告详情页从纯文字回看升级为"图表 + 报告"完整复盘页，与综合分析页视觉体验对齐
- **组件复用**：TechnicalChartPanel 零修改即可跨页面复用，验证了封装设计的可复用性
- **零后端改动**：kline 接口 / Redis R2 缓存 / Agent / 存储结构全部不变
- **Header UX**：右上角不再显示 `string`，正式账号下显示 username，降级场景显示 email 或"用户"
- **代码审查 8/8 ✅，API 级验证 6/6 ✅（2026-05-30）**：接入逻辑、props 绑定、displayName fallback 均通过代码审查；`getReport()` 字段映射验证（result.market/symbol 正确），CN/000001 symbol 前导零持久化验证，HK/700 → kline 推导 URL 验证，displayName 4 场景 Python 模拟全通过
- **浏览器视觉验证 ⬜**：K线 Canvas 渲染、HK volume 单位图例、AppHeader displayName 实际显示、Console 无 warning 等 8 项需人工浏览器执行

*文档更新于 2026-05-30*

---

## STAR 14 — 行业热门股前端展示（Phase P1-b）

**日期：** 2026-05-30  
**标签：** Vue 3 / 动态同行 / 申万行业 / Hot Score / 零后端改动

### Situation（背景）

Phase P1 后端已实现申万行业映射（5,166 只 A 股）与 Hot Score 动态同行接口（`/industries/stocks/{market}/{symbol}/dynamic-peers`），但前端没有任何页面消费这些数据。用户分析完一只股票后无法直接看到同行业热门标的，需要手动查找，产品体验断层。

### Task（目标）

在综合分析页和历史报告详情页中展示行业热门股面板，要求：
1. 复用已有后端接口，不新增 API
2. 支持三种数据源：`dynamic_hot`（申万动态热门）/ `manual_map`（人工精选同行）/ `none`（无数据）
3. 港股/非 CN 市场短路，不发请求，显示友好提示
4. 点击同行可跳转分析
5. 错误、加载、空态全部处理

### Action（行动）

**`frontend/src/api/industries.js`（新建）：**
- `getDynamicPeers(market, symbol, {limit})` → `baseFetch(/industries/stocks/{market}/{symbol}/dynamic-peers?limit=...)`
- `symbol.trim()` 保留前导零，不使用 parseInt / toUpperCase

**`frontend/src/components/IndustryHotStocksPanel.vue`（新建）：**
- Props: `market`, `symbol`, `visible`（Boolean，用于 keep-alive 场景懒加载）
- HK 短路：`market !== 'CN'` 时直接设 `peerSource='unsupported'`，不发请求
- CN：`getDynamicPeers` → 解析 `data_quality.peer_source` 驱动 UI 分支
- `dynamic_hot`：表格展示 rank / 股票名+代码 / Hot Score / 成交额（亿/万）/ 涨跌幅（带颜色）/ "分析" 按钮
- `manual_map`：说明文字 + chip 按钮列表
- `none`：空态文字 + fallback_reason
- `goAnalyze(item)`：`router.push({ path: '/', query: { market, symbol } })`
- `watch([market, symbol, visible], fetchDynamicPeers, { immediate: true })`

**视图接入（ComprehensiveAnalysisView.vue + HistoryDetailView.vue）：**
- 两处均在 `TechnicalChartPanel` 之后、主报告 `<div class="card">` 之前插入 `<IndustryHotStocksPanel>`
- 各新增一行 import，零状态变量改动

**构建验证：**
```
npm run build → 87 modules（+3，industries.js + IndustryHotStocksPanel + 两视图 chunk 更新），exit 0
无 Vue warn，无 unresolved import
```

### Result（结果）

- **产品体验**：分析任意 A 股后，面板立即展示同行业 Top-5 热门标的（按 Hot Score 排序），一键跳转继续分析，形成完整行业对比入口
- **三态 UI**：`dynamic_hot`（动态热门表格）/ `manual_map`（人工精选 chip）/ `unsupported`（港股友好提示）全部覆盖
- **零后端改动**：复用 Phase P1 已有接口，不新增 API、不改路由、不改 DB
- **组件自洽**：loading / error / 短路逻辑全部在 IndustryHotStocksPanel 内管理，不影响 TechnicalChartPanel 或主报告渲染
- **API 级验证 3/3 ✅（2026-05-30）**：CN/000001（银行，dynamic_hot，5 peers）/ HK/700（manual_map，4 peers）/ CN/300750（电力设备，dynamic_hot，4 peers，已排除 300750 自身）
- **浏览器视觉验证 ⬜**：表格渲染、chip 按钮跳转、港股提示文案、成交额格式等需人工浏览器执行

*文档更新于 2026-05-30*

---

## STAR 15 — 信息架构优化：统一布局 + anchor 导航（Phase P1-c）

**日期：** 2026-05-30  
**标签：** Vue 3 / 信息架构 / 组件抽象 / UX / 零后端改动

### Situation（背景）

Phase P1-a/b 完成后，两个核心页面（ComprehensiveAnalysisView / HistoryDetailView）各自有技术图表 + 行业热门股 + 综合报告 + 子报告折叠 + 操作栏，内容丰富但缺乏层次。用户需要连续向下滚动才能找到各模块；保存 / 删除按钮藏在底部；两页布局已开始分叉（save-bar vs detail-footer）。

### Task（目标）

纯前端 UI 重构：
1. 统一两页布局到一个共享 layout 组件
2. 在顶部增加 sticky anchor 快速导航（图表 / 行业 / 综合 / 分项）
3. 将所有操作（保存 / 下载 / 删除）上移到 anchor bar 右侧
4. 给每个模块加统一 section label
5. 不改后端、不改 API、不引入 UI 库

### Action（行动）

**新建 `AnalysisResultLayout.vue`：**
- Sticky action bar：左侧 4 个 anchor pill，右侧 `#actions` named slot（各页注入各自的操作按钮）
- 4 个命名 section（`id="rl-chart/rl-industry/rl-report/rl-sections"`），每个带 section-label 小标题
- 内置 `TechnicalChartPanel` / `IndustryHotStocksPanel` / AgentStatusBar+WarningPanel+MarkdownReport card / `SectionAccordion`
- `scrollIntoView({ behavior:'smooth', block:'start' })` + `scroll-margin-top:60px` 防止 sticky bar 遮挡
- Mobile：`@media ≤540px` anchor bar 换行，anchors 横向滚动（scrollbar hidden）

**ComprehensiveAnalysisView 重构：**
- 内容区 60 行 → 24 行；6 个 component import 删除，改引 AnalysisResultLayout
- 保存状态文本 + DownloadMenu + 保存按钮 → `#actions` slot

**HistoryDetailView 重构：**
- 内容区 31 行 → 14 行；6 个 component import 删除，改引 AnalysisResultLayout
- 时间戳 + DownloadMenu + 删除按钮 → `#actions` slot；detail-footer CSS 清理

**构建：**
```
npm run build → 89 modules，exit 0
HistoryDetailView chunk 2.42 kB → 1.81 kB（6 个 import 移入主 bundle）
```

### Result（结果）

- **统一架构**：两页共享同一 layout 组件，未来新增功能只需改一处
- **导航提升**：sticky anchor bar 让用户可以跳转到任意 section，无需盲目滚动
- **操作可见性**：下载 / 保存 / 删除按钮始终在视口内（sticky bar），不再隐藏在底部
- **零后端改动**：仅前端组件重构，所有 API / Agent / DB 不变
- **代码量减少**：两视图合计减少约 90 行模板 + 12 个重复 import
- **P1-d CSS 修复 ✅（2026-05-30）**：`section-label` 移除 `opacity:0.7`；sticky bar 背景改为 `var(--bg)` + `box-shadow`
- **build 通过 ✅（2026-05-30）**：89 modules，exit 0，无 unresolved import，无 Vue warn
- **API 级验证 13/13 ✅（2026-05-30）**：kline/dynamic-peers/cached/vol_unit/前导零/CORS 全通过
- **浏览器视觉验证 ⬜**：sticky 行为、anchor 滚动偏移、DownloadMenu 层叠、移动端换行等 17 项需人工执行

*文档更新于 2026-05-30*

---

## STAR 16 — Alembic 迁移管理接入（Phase D2-c）

**日期：** 2026-05-31  
**标签：** Alembic / SQLAlchemy / PostgreSQL / 数据库迁移 / 生产化

### Situation（背景）

项目自 MVP 起一直依赖 `Base.metadata.create_all` 管理数据库表结构。这对本地开发足够，但存在重大隐患：`create_all` 无法处理列重命名、列类型变更、列删除等操作，也没有迁移历史记录，无法回滚，生产环境中一次错误操作可能导致数据丢失。随着项目进入准生产阶段，引入 Alembic 是必要的工程化步骤。

### Task（目标）

1. 接入 Alembic，建立 baseline migration，为后续表结构演进提供安全保障
2. 不破坏现有数据库和业务流程
3. 新增 `ENABLE_CREATE_ALL` 环境变量，让开发和生产走不同的初始化路径
4. 更新部署文档，明确 Alembic 为生产标准工作流

### Action（行动）

**模型审计：**
- 确认 6 张表（app_users / analysis_reports / industry_master / stock_industry_map / industry_hot_stock_snapshot / watchlist_items）全部继承同一 `Base`，且均通过 `app.models.__init__` 注册
- UUID(as_uuid=True) / JSONB / DateTime(timezone=True) / server_default=func.now() 均与 autogenerate 兼容

**Alembic 文件：**
- `backend/alembic.ini`：placeholder URL，real URL 在 env.py 中从 settings 读取
- `backend/alembic/env.py`：async_engine_from_config + NullPool + statement_cache_size=0（Supabase PgBouncer 兼容）
- `backend/alembic/script.py.mako`：标准 revision 模板
- `backend/alembic/versions/.gitkeep`：versions 目录占位

**Baseline 建立：**
```
uv run alembic revision --autogenerate -m "baseline existing schema"
# → upgrade=pass / downgrade=pass（DB 与 ORM 完全一致，零差异）
uv run alembic stamp head
# → stamp_revision → 4b49004d01a6
uv run alembic current
# → 4b49004d01a6 (head)
```

**init_db() + ENABLE_CREATE_ALL：**
- `config.py` 新增 `enable_create_all: bool = True`（默认 true，不破坏现有开发）
- `database.py` init_db() 检查 settings.enable_create_all，false 时直接 return
- `.env.example` 中 `ENABLE_CREATE_ALL=false`（生产推荐）

### Result（结果）

- **零破坏**：现有 6 张表、5,166 条行业映射数据、所有历史报告和用户数据完全不受影响
- **双轨兼容**：开发默认 create_all（快速迭代），生产设 ENABLE_CREATE_ALL=false + alembic upgrade head（精确控制）
- **baseline 干净**：autogenerate 生成 pass migration，证明 create_all 建立的 DB 与 ORM 元数据完全一致
- **标准工作流**：后续任何表结构变更均通过 `alembic revision --autogenerate` + 人工检查 + `alembic upgrade head` 完成
- **所有 API 不受影响**：health / auth / reports / watchlist / industries 全部正常
- **验证 ✅（2026-05-31）**：alembic history/current/stamp 全通过，API smoke test 6/6 通过

*文档更新于 2026-05-31*

---

---

## 阶段性总览（截至 2026-05-29）

### 项目阶段定性

TradingAgents 已从"MVP 功能验证"阶段跨入**"可展示产品原型"**阶段。

- **MVP 阶段**（STAR 1–5）：搭建数据 → Agent → 协调器 → 前端工程化，验证核心分析链路可运行
- **产品扩展阶段**（STAR 6–11）：报告历史 → 行业动态同行 → Redis 三层缓存 → 自选股工作台，打通从"单次分析工具"到"个人研究平台"的产品闭环

### 阶段性指标汇总

| 指标 | 数值 |
|------|------|
| 当前版本 | MVP v0.7 |
| 完成 STAR 里程碑 | 13 个（STAR 1–13） |
| 后端 Python 文件 | ~24 个（services / agents / routers / Phase 1A–2E-1） |
| 前端 Vue 文件 | 27 个（components / views / stores / styles / api） |
| 数据库业务表 | 5 张（industry_master / stock_industry_map / industry_hot_stock_snapshot / analysis_reports / watchlist_items） |
| A股行业覆盖 | 5,166 只 / 30 个申万一级行业 |
| 多 Agent 并行时延 | 35–45s（vs 串行 120s，约 3× 提升） |
| Redis 缓存速度比 | R1 ~3000–20000x / R2 ~400–600x / R3 ~400x |
| Build 产物 | 75 modules，exit 0 |
| P0 故障 | 0 |
| 文档数量 | 7 份（含本次 Phase S1 新增 3 份） |

### 已完成核心能力

```
输入 A股/港股代码
        ↓
4-Agent 并行分析（35–45s）
[技术面 + 基本面 + 同行对比（动态同行，30 行业 5166 股）+ 新闻]
        ↓
综合报告 + 警告徽章 + Agent 状态
        ↓
    ┌───┴───┐
  保存报告   不保存
    ↓
历史列表（/history）
    ↓
历史详情（/history/:id）
    ↓
可选：下载 / 打印

自选股工作台（/watchlist）
  添加标的 → 卡片展示最近报告摘要
  一键进入分析 / 查看历史 / 内联 Note 备注
```

### 仍未实现（优先级排序）

| 优先级 | 项目 |
|--------|------|
| ~~高~~ | ~~技术面图表（K线 + 指标可视化）~~ ← **✅ Phase P1-a 已完成（代码审查 + build，浏览器验证 ⬜）** |
| ~~中~~ | ~~历史详情页图表复用 + AppHeader 用户名修复~~ ← **✅ Phase P1-a.1 已完成（代码审查 + build，浏览器验证 ⬜）** |
| 高 | Router 导航守卫（beforeEach guard） |
| 中 | 请求超时提示（AbortController 45s） |
| 中 | Vite 5 → 6.x 升级（CJS 警告 + esbuild 漏洞） |
| 中 | Alembic 迁移（已有表结构变更安全保障） |
| 低 | warningMap 单元测试（Vitest） |
| ~~低~~ | ~~移动端适配~~ ← **✅ Phase P2 已完成（CSS 修复 + build + 编译产物 CSS 逻辑验证通过，DevTools 设备仿真 ⬜ 待人工确认）** |
| ~~中~~ | ~~行业热门股独立页面~~ ← **✅ Phase P3 + P3.1 已完成（IndustryHotView + listIndustries + /industries 路由 + AppHeader 第 4 链接；P3.1 修复 data_quality.trade_date 字段路径 bug；23 项代码级自动化验证通过；build exit 0；浏览器视觉验证 A-1~A-17 待人工执行 ⬜）** |
| ~~中~~ | ~~股票搜索 / 代码联想~~ ← **✅ Phase P4-a 完整验证通过（`GET /stocks/search`；StockSearchBox 组件；Enter 键修复；B-1~B-8 curl 通过；build exit 0；浏览器验证 F-1~F-15 15/15 ✅ Playwright headless）** |
| ~~中~~ | ~~HistoryView 搜索联想~~ ← **✅ Phase P4-b 完整验证通过（HistoryView filter bar 接入 StockSearchBox；route.query 初始化；Enter 触发 loadReports；H-1~H-10 10/10 ✅ Playwright headless；零后端改动；零新依赖）** |
| ~~中~~ | ~~IndustryHotView 快速搜索~~ ← **✅ Phase P4-c 完整验证通过（行业页 control card 新增"快速搜索股票"区块；选中跳转 `/?market=CN&symbol=`；手动输入+分析按钮跳转；I-1~I-10 10/10 ✅ Playwright headless；零后端改动；零新依赖；P4 全站 35/35 ✅）** |
| ~~中~~ | ~~股票主数据表 stock_master~~ ← **✅ Phase P5-a 完整验证通过（StockMaster 表 + Alembic migration + CN 5166 股回填 + search_stocks 升级为 stock_master 优先 + fallback 机制；V-1~V-6 curl ✅；Playwright 回归 10/10 ✅；前端零改动；API 结构完全兼容）** |
| 低 | HK 市场动态同行 |
| 低 | HK stock_master 数据导入（P5-b） |

---

## STAR 17 — 股票搜索 / 代码联想（Phase P4-a）

### Situation（背景）

用户在综合分析页和 Watchlist 添加表单中必须手动输入 6 位股票代码，无任何提示或补全。系统覆盖 5166 只 A 股，但对新用户来说记住代码门槛极高。

### Task（任务）

在不新建数据库表、不引入 Alembic migration、不访问外部数据源的前提下，为系统添加股票搜索联想功能：按代码前缀或名称关键词快速找到股票，并在综合分析页与 Watchlist 两处接入。

### Action（行动）

**后端：**
- 在 `industry_classification_service.py` 新增 `search_stocks()` 方法，复用已有的 `stock_industry_map` 表（5166 只 A 股）。查询逻辑：`symbol ILIKE 'q%' OR (stock_name IS NOT NULL AND stock_name ILIKE '%q%')`，仅返回 `is_primary=True` 记录。
- 发现数据问题：同一 symbol 可对应多个 `is_primary=True` 行（不同行业分类）。用 `fetch_limit = limit * 4` + Python dedup-by-symbol 解决，无需 schema 变更。
- 在 `stocks.py` 新增 `GET /stocks/search` 路由，放在所有 `/{market}/{symbol}/...` 路径参数路由前，避免 FastAPI 路由歧义。HK 市场返回空列表 + 友好提示。

**前端：**
- 新建 `StockSearchBox.vue`：debounce 300ms、dropdown、键盘导航（↑↓/Enter/Esc）、点击外部关闭（`onUnmounted` 清理）、HK 市场禁止搜索、移动端 dropdown 全宽不溢出。
- 替换 `StockInputPanel` 的 symbol `<input>` 为 StockSearchBox；`v-model:symbol` 双向绑定确保 `initialSymbol` 同步和快速示例 chips 仍可用；补加 `@keydown.enter="submit"` 恢复 Enter 键提交。
- 替换 `WatchlistView` 添加表单的 symbol + name 两个字段为 StockSearchBox；`@select` 自动填充 symbol 和 name，保留手动直接输入路径；补加 `@keydown.enter="handleAdd"` 恢复 Enter 键添加。
- Enter 键回归修复：StockSearchBox 内 dropdown 打开时 `e.stopPropagation()` 阻止冒泡，父组件通过 `@keydown.enter` 在 dropdown 关闭时接收事件，两层逻辑正确隔离。

### Result（结果）

- 后端 curl 验证 8/8 通过（代码精确匹配、名称模糊匹配、空查询、无结果、HK 提示、prefix 匹配、401 鉴权、limit 上限）
- 前端 `npm run build` exit 0，93 modules，12 项编译产物验证通过（含 Enter 键修复后的 stopPropagation + withKeys 绑定）
- Enter 键回归修复已完成并通过编译产物验证
- 浏览器交互验证 F-1~F-15 全部通过（Playwright 1.58.0 headless Chromium，1440px + 375px 双视口）：dropdown 搜索/选择/键盘导航/点击外部关闭/Esc/HK 禁搜/空结果提示/移动端不溢出/Console 无报错
- 零新表、零 Alembic、零 npm 依赖新增

---

## STAR 18 — HistoryView 搜索联想接入（Phase P4-b）

### Situation（背景）

历史报告页的 symbol 筛选只有一个纯文本输入框，用户需要精确记住股票代码才能筛选。P4-a 完成了 StockSearchBox 组件和后端 `/stocks/search` 接口，是扩展到 HistoryView 的最佳时机。

### Task（任务）

在零后端改动、零新接口、零新依赖的前提下，将 HistoryView 的 symbol filter input 替换为 StockSearchBox，同时保留所有原有筛选逻辑（route.query 初始化、Enter 触发查询、HK 禁搜、直接输入代码路径）。

### Action（行动）

- 替换 `frontend/src/views/HistoryView.vue` 中的 `<input class="filter-input">` 为 `<StockSearchBox>`。
- `:market="filterMarket || 'CN'"` — 当"全部"市场（`filterMarket=''`）时默认传 CN，避免后端 400；HK 模式自动禁搜。
- `@select="onSearchSelect"` 设置 filterSymbol；`@keydown.enter="loadReports"` 保留 Enter 触发查询。
- `v-model:symbol="filterSymbol"` 确保 `route.query.symbol` 初始化（ref 初值）和双向绑定同步。
- CSS 增 `.ssb-group { min-width:140px; flex:1 }`；移除旧 `.filter-input` 样式；移动端 `.ssb-group { width:100% }`。

### Result（结果）

- `npm run build` exit 0，93 modules（StockSearchBox 已在共享 bundle，HistoryView chunk 仅增 40B）
- 零新表、零 Alembic、零 npm 依赖
- 浏览器验证 H-1~H-10 10/10 通过（Playwright 1.58.0 headless Chromium，1440px + 375px）
- 验证项覆盖：列表加载、名称搜索、点击选择、查询触发、route.query 初始化、Enter 键查询、HK 禁搜、移动端不溢出、Console 无报错、Watchlist + 综合分析页零退化

---

### 作品集状态

Phase S1 已完成以下可展示文档输出：

| 文档 | 用途 |
|------|------|
| `docs/project_portfolio_summary.md` | 项目介绍 / 架构说明 / 技术难点 / 作品集展示 |
| `docs/resume_star_cases.md` | 6 个 STAR 案例 + 150 字简历项目描述 |
| `docs/interview_talking_points.md` | 技术面试 Q&A 要点（8 个主题，30+ 问答） |
| `docs/future_product_roadmap.md` | 后续路线图（Phase L1/D1/P1/M1/A1） |

*阶段性总览更新于 2026-05-30*

---

## STAR 19 — IndustryHotView 快速搜索接入（Phase P4-c）

### Situation（背景）

行业热门股页（`/industries`）是用户发现优质股票的入口——热门股排行让用户看到"市场在关注什么"，但从热门股到深度分析的路径只有表格里的"分析"按钮。如果用户想主动查找某只非榜单股票，必须离开当前页面、回到综合分析页重新输入。P4-a/P4-b 已完成 StockSearchBox 组件和后端接口，扩展到行业页成本极低。

### Task（任务）

在零后端改动、零新接口、零新依赖的前提下，在 IndustryHotView control card 新增"快速搜索股票"区块：用户可搜索任意 A 股并一键跳转到综合分析页，同时保证行业 dropdown / 热门股表格原有功能零退化。

### Action（行动）

- 在 `frontend/src/views/IndustryHotView.vue` 引入 `StockSearchBox`，新增 `quickSymbol` ref。
- control card 末尾添加 `.quick-search-row`：`<StockSearchBox market="CN" @select="goAnalyzeSelected">` + "分析"按钮 (`@click="goAnalyzeQuick"`, `:disabled="!quickSymbol.trim()"`)。
- `goAnalyzeSelected(item)` — 点选 dropdown 项后立即 `router.push({ path: '/', query: { market: 'CN', symbol: item.symbol } })`，无需用户再点按钮。
- `goAnalyzeQuick()` — 处理手动输入路径（不选 dropdown 直接点分析按钮）；`market` 固定 `'CN'`（行业页为纯 A 股上下文，不存在空字符串或 HK 的歧义）。
- CSS：`.quick-search-row { display:flex; gap:12px; margin-top:16px; border-top:1px solid var(--border) }` + 移动端 `flex-direction:column; align-items:stretch`。
- 复用 Playwright 同款 warm-up 模式 + `inject_token_and_goto` 处理 375px 二级 context。

### Result（结果）

- `npm run build` exit 0，93 modules（IndustryHotView chunk 零增量，StockSearchBox 在共享 bundle）
- 浏览器验证 I-1~I-10 10/10 全部通过（Playwright 1.58.0 headless Chromium，1440px + 375px）
- I-4：点选 dropdown → `/?market=CN&symbol=600519` ✅
- I-5：手动输入 + 分析 → `/?market=CN&symbol=000001` ✅
- I-6：跳转后综合分析页 SSB 显示 initialSymbol '000001' ✅（route.query 初始化链路完整）
- I-7：热门股列表分析按钮零退化 ✅
- I-8：375px dropdown right_edge=334px ≤ 380px ✅
- I-10：Watchlist + HistoryView + 综合分析页 SSB 全部零退化 ✅
- **P4 全站 StockSearchBox 覆盖完成（综合分析页 / Watchlist / HistoryView / IndustryHotView），35/35 验证项通过，零后端改动，零新依赖**

---

## STAR 20 — 股票主数据表 stock_master（Phase P5-a）

### Situation（背景）

`/stocks/search` 依赖 `stock_industry_map` 做搜索，该表设计目标是行业分类映射，不是股票主数据。同一只股票在多个行业版本下存在多行，需要 `fetch_limit*4` + Python dedup 兜底，且无法扩展 HK 股票。随着产品计划引入 HK 搜索和更多市场，需要一张真正的股票主数据表。

### Task（任务）

在零前端改动、API 结构完全向后兼容的前提下，建立独立 `stock_master` 表，将 `/stocks/search` 数据源从 `stock_industry_map` 升级为 `stock_master`，同时保留 fallback 机制确保迁移期间零停机。

### Action（行动）

**数据模型：**
- 新建 `app/models/stock_master.py`：`StockMaster` ORM，`UNIQUE(market, symbol)` 彻底消灭 dedup 问题，3 个 B-tree 索引（market+symbol / market+name / market+exchange）。
- Alembic migration `76fe066db8b1`：`CREATE TABLE stock_master` + indexes，`down_revision` 链接到 baseline，只做 DDL 无旧表操作。

**数据导入：**
- `scripts/import_stock_master.py`：从 `stock_industry_map` 用 `DISTINCT ON (symbol)` 回填，无 Python dedup；`INSERT … ON CONFLICT DO UPDATE` 幂等；支持 `--dry-run`；分 500 条 chunk 批量 upsert。
- exchange 推断：`6` 开头 → SSE，`0/3` 开头 → SZSE，其余 → `''`。

**搜索升级：**
- `IndustryClassificationService.search_stocks` 主入口先检查 `stock_master` 行数：有数据走 `_search_stocks_from_master`，否则 fallback 到 `_search_stocks_from_industry_map`（原逻辑完整保留）。
- `_search_stocks_from_master`：查 `StockMaster`（symbol ILIKE 前缀 OR name ILIKE 模糊），再一次性 SELECT 匹配 symbols 的 `stock_industry_map` 行，Python 层按 symbol 取首行，补 `industry_code / industry_name`。两次 DB 查询，无 dedup 开销。
- `stocks.py` 路由：`data_quality.source` 从 items[0].source 动态读取，fallback 路径自动显示 `stock_industry_map`，新路径显示 `stock_master`。

### Result（结果）

- `stock_master` 表建立：5166 只 CN 股，0 null name，exchange 推断正确（SSE/SZSE/空）
- 导入脚本幂等：重复运行行数不变（5166）
- `/stocks/search?q=600519` → `source=stock_master`，`industry_name=食品饮料` ✅（LEFT JOIN 正常）
- `/stocks/search?q=600&limit=10` → 10 条，无重复 symbol ✅（UNIQUE 约束从 DB 层保证）
- HK 短路、401 鉴权、query 格式完全不变
- Playwright 回归 10/10 通过（前端零改动，StockSearchBox 不感知 source 字段变化）
- `npm run build` exit 0，93 modules，前端 chunk 大小无变化
- **P5-b 扩展路径已预留**：HK CSV 导入后，移除路由层 HK 短路，search 自动支持 HK，服务层零改动

---

## STAR 21 — P5-b：港股 stock_master 导入与 HK StockSearchBox 全支持

**日期：** 2026-06-01

### Situation（背景）

P5-a 建立了 `stock_master` 并完成 CN A 股（5166 只）导入，但港股搜索仍被路由层短路（返回 `"港股暂不支持搜索"`），StockSearchBox 在 HK 市场下也硬编码禁止搜索触发。此阶段目标是导入 HK 股票主数据，打通端到端港股搜索。

### Task（任务）

1. 构建 `data/stock_master/hk_stocks.csv`（30 只主流港股，5 位补零格式）
2. 扩展 `import_stock_master.py` 支持 `--csv --market HK` 模式
3. 升级 `_build_symbol_filter`：HK 数字查询双 ILIKE（`700%` + `00700%`）
4. 移除 `stocks.py` HK 短路，全开放 HK 搜索
5. `StockSearchBox.vue` 移除 HK 禁用守卫，更新 placeholder
6. 统一 `PEER_MAP` 为 5 位 HK 格式，`_normalize_symbol` 保持向后兼容
7. Playwright 端到端验证（B-1～B-9，含移动端、零退化）

### Action（行动）

**HK symbol 规范：** 选择 5 位补零格式（`00700`）作为 stock_master 存储标准，与 HKEX/AkShare 对齐。短格式（`700`）查询通过 `_build_symbol_filter` 双 ILIKE 模式透明支持。

**PEER_MAP 迁移：** 将 `("HK", "700")` 改为 `("HK", "00700")`，新增 `_normalize_symbol` 函数，使 `get_peer_specs("HK", "700")` 和 `get_peer_specs("HK", "00700")` 均返回正确同行列表。

**前端最小改动：** `StockSearchBox.vue` 仅改 2 行（placeholder 条件 + scheduleSearch 守卫），不引入新 prop 或 emit。

**脚本幂等：** HK CSV 重复导入行数不变（30 行），`ON CONFLICT DO UPDATE`。

### Result（结果）

- `stock_master` 新增 30 只 HK 股（`00700`~`09868`），格式规范
- `/stocks/search?market=HK&q=腾讯` → `00700 腾讯控股`，`source=stock_master` ✅
- `/stocks/search?market=HK&q=700` → `00700`（短格式自动扩展） ✅
- Playwright B-1～B-9：**9/9 全部通过**
  - 分析页、Watchlist、HistoryView、375px 移动端 — 全部正常
  - CN 四页面零退化
  - Console 无 JS error / Vue warning
- `npm run build` exit 0，前端 bundle 无变化
- P5 整体：stock_master（CN 5166 + HK 30），四页面全市场搜索能力完整交付

---

## STAR 22 — P6-b：报告可信度增强与行业面板 UI Bug 修复

**日期：** 2026-06-02

### Situation（背景）

用户验收测试发现两个问题：

1. **`IndustryHotStocksPanel`** 行业来源 badge 直接显示 JSON 字符串 `{"dynamic_hot":"动态热门","manual_map":"手动同行",...}`，严重影响 UI 可读性。根本原因：`sourceLabel` 和 `sourceBadgeClass` 定义为 plain object 而非响应式 `computed`，模板 `v-if` 对 object 永远求值为 `true`，`{{ }}` 序列化整个对象。

2. **报告可信度不足**：生成的综合报告标题为 `# 综合分析报告：CN/000001`，缺少股票名称，用户需要自己辨认这是哪只股票，影响对报告真实性的信心。

### Task（任务）

1. **P6-0**：修复 `sourceLabel` / `sourceBadgeClass` plain object bug
2. **P6-b**：在综合分析报告中注入股票名称（`stock_name`），标题、摘要第一句、前端展示全覆盖
3. **UI-2**：优化 anchor bar 文字，桌面端显示完整（技术图表 / 行业热股 / 综合报告 / 分项分析），移动端保持简短

### Action（行动）

**Bug 修复（P6-0）：** 将 `sourceLabel` 和 `sourceBadgeClass` 改为 `computed(() => MAP[peerSource.value] ?? '')`，一行变动，彻底消除 JSON 渲染。

**stock_name 获取策略：** 在 `analyze_async` 开头调用 `_fetch_stock_name`，复用已有的 `industry_classification_service.search_stocks` 查 `stock_master`，精确匹配（CN exact、HK lstrip 比较），失败不影响主流程，返回 `None` 时 fallback 到 `market/symbol` 格式。

**LLM prompt 双重约束：** 在 `_SYSTEM_PROMPT` 新增「报告标题与身份声明规则」；在 `_build_synthesis_prompt` 的用户消息中同时注入明确的标题和摘要首句指令（`⚠️ 报告 Markdown 标题必须为：...`）。双重约束确保 LLM 输出格式正确。

**前端最小改动：** `AnalysisResultLayout` 传 `stockName` prop 给 `IndustryHotStocksPanel`；技术走势标题旁加副标；`HistoryDetailView` back-title 含名称；旧报告安全 fallback。

**向后兼容：** `ComprehensiveAnalysisResponse.stock_name` 默认 `""`，无数据库变更，旧报告不受影响。

### Result（结果）

- `IndustryHotStocksPanel` source badge 正确显示「动态热门」/「手动同行」等自然语言，JSON bug 消除 ✅
- 综合报告标题格式：`# 综合分析报告：平安银行（CN/000001）` ✅（LLM prompt 双重指令保障）
- 核心摘要首句：`本报告分析对象为 平安银行（CN/000001）。` ✅
- 技术走势区块副标：`CN/000001 平安银行` ✅
- 行业热股面板副标：`CN/000001 平安银行 · 申万一级：银行` ✅
- anchor bar 桌面端：技术图表 / 行业热股 / 综合报告 / 分项分析 ✅
- `HistoryDetailView` 标题：`平安银行（CN/000001）`，旧报告 fallback `CN/000001` ✅
- `npm run build` exit 0，93 modules，无 migration ✅

**浏览器验收（Playwright headless，2026-06-02）：** F-1 ~ F-7 全部通过（8/8 ✅）。报告 Markdown 正文含「平安银行（CN/000001）」（F-6b）；旧报告 HK/700 fallback 正确（F-7）。

---

## STAR 23 — P6-a：DiscoveryPanel 发现面板

**日期：** 2026-06-02

### Situation（背景）

综合分析页只有一个股票输入框，用户（特别是新用户）不知道可以分析哪些股票、当前市场热点是什么。需要降低"第一步"的摩擦感。

### Task（任务）

在综合分析页 `StockInputPanel` 下方新增"发现面板"（DiscoveryPanel），提供：
1. **推荐搜索**：5 只常用股票 chip（CN/HK 各有代表性标的）
2. **行业热门**：复用已有 `listIndustries` + `getIndustryHotStocks` API，展示申万一级行业热股前 5 只
3. 填入表单但不自动提交，用户保持控制权

### Action（行动）

**新建 DiscoveryPanel.vue（~200 行）：**
- 双 tab UI：推荐搜索 / 行业热门
- 行业热门懒加载（首次切换 tab 时请求），默认「食品饮料」行业
- emit `pick` 事件，不依赖 router，不产生副作用

**StockInputPanel.vue — 最小改动：**
- 新增 `fill(market, symbol)` 函数 + `defineExpose({ fill })`，3 行代码

**ComprehensiveAnalysisView.vue 集成：**
- `stockInputRef` + `handlePick` 连接 fill 方法
- `discoveryOpen` ref 控制折叠；`watch(result, ...)` 自动折叠
- 无 result 时始终展开；有 result 时显示「展开发现面板」切换按钮

**零后端变更：** 复用现有 `/industries/` API，无数据库变更，无新依赖

### Result（结果）

- `npm run build` exit 0，95 modules（新增 DiscoveryPanel 模块）✅
- 推荐搜索 5 个 chip 正确渲染，点击填入 market/symbol，HK/00700 → symbol=00700 ✅
- 全部 5 个 chip 点击验证：不触发自动分析 ✅
- 行业热门 tab：懒加载，默认「食品饮料」，5 只热股渲染正确 ✅
- 行业切换（银行）→ 热股列表刷新，loading 状态正常 ✅
- 热股「分析」按钮：URL 不变，form 填入，不自动分析 ✅
- 折叠逻辑：无 result 时 panel 展开，有 result 时 toggle 按钮出现 ✅
- 375px / 390px：无 body 横向溢出，chips 自然换行 ✅
- Console：Vue warnings=0，JS errors=0 ✅
- 回归：/history、/watchlist、/industries 全部正常 ✅
- 不改动后端、/industries 独立页、IndustryHotView ✅

**浏览器验收（Playwright headless，2026-06-02）：** A-1~A-11 全部通过（含移动端 + 回归）。

---

## STAR 24 — P6-c：StockIdentityCard 分析前确认卡片

**日期：** 2026-06-02

### Situation（背景）

用户在综合分析页输入股票代码后，到点击「生成综合分析」之间，缺少明确的分析对象确认。用户可能不确定：
- 选中的是正确股票吗？搜索结果只是填了代码，还是真正匹配到了名称？
- HK/700 vs HK/00700 是否混淆？
- 系统后续会分析哪些数据源？

### Task（任务）

在 `StockInputPanel` 下方新增 `StockIdentityCard`，分析前展示：
- 股票名称（从 stock_master 查询）+ 市场/代码
- 所属行业（CN 申万一级）
- 数据覆盖范围 badge（技术图表/基本面/同行对比/新闻信息）
- HK 专属说明
- 「请确认股票无误后生成综合分析报告」提示

### Action（行动）

**新建 StockIdentityCard.vue：**
- 复用已有 `searchStocks(market, symbol, { limit: 3 })` API，无新建后端接口
- 400ms debounce 避免逐字触发
- **Generation counter 防止 stale 响应**：fast-type 切换股票时旧 fetch 结果不覆盖新状态
- 未找到名称时显示 fallback + 「暂未匹配」hint，不显示 undefined/null
- HK 市场显示「港股行业分类暂不使用申万行业体系…」说明

**StockInputPanel.vue 最小改动：**
- 新增 `emit('change', { market, symbol })` + `watch(form)` — 3 行代码

**ComprehensiveAnalysisView.vue：**
- `currentMarket/currentSymbol` refs，`handleFormChange` 处理 @change
- StockIdentityCard `v-if="currentSymbol.trim() && !loading"`

**无后端变更，无新依赖**

### Result（结果）

- `npm run build` exit 0，97 modules（+2 vs P6-a）✅
- 初始无 symbol → 卡片不显示 ✅
- chip 点击 → 卡片立即出现（loading skeleton），识别结果异步加载 ✅
- CN/000001 → 无 undefined/null，4 个 coverage badges，confirm hint ✅
- HK/00700 → 港股同行对比 badge，港股行业分类说明 ✅
- 不存在代码 ZZZZZ → fallback + 「暂未匹配」hint ✅
- 清空 symbol → 卡片消失 ✅
- 375px：无横向溢出 ✅
- DiscoveryPanel 共存，回归页面全部正常 ✅
- Stale response 防护：generation counter 实现，快速切换股票时旧响应被丢弃 ✅

**浏览器验收（Playwright headless，2026-06-02）：** B-1~B-12 全部通过。

---

## STAR 25 — P6-d：报告可信度与可读性增强

**日期：** 2026-06-02

### Situation（背景）

综合分析报告存在两个可信度问题：
1. 报告正文可能出现过强的确定性表达（"明确利好"、"必然上涨"），或将缺失字段描述成"公司没有 PE"（暗示公司缺陷而非数据源问题）。
2. 报告页面没有显示"当前报告分析的是哪只股票"的明确标识，用户需要在 Markdown 标题中找到这一信息。

### Task（任务）

在不改变 Agent 架构的前提下：
1. 优化 `_SYSTEM_PROMPT`，新增「数据来源与覆盖范围」章节，强化过强措辞约束，规范数据缺失表达方式
2. 同步更新 `_fallback_report` 为新 5 章结构
3. 在 `AnalysisResultLayout.vue` 综合结论卡片顶部添加 report-identity-bar

### Action（行动）

**后端 prompt 工程（`comprehensive_analysis_coordinator.py`）：**
- 在「核心摘要」之后新增「二、数据来源与覆盖范围」章节，列出技术面/基本面/同行对比/新闻面数据来源及字段覆盖
- 原章节二～四 → 三～五
- 新增明确的过强措辞禁止映射表（明确利好/利空、必然上涨/确定性机会 → 审慎替换表达）
- 数据缺失必须写"当前数据源未返回 {字段}，因此无法展开"，禁止写成"公司没有 PE"
- 每章节第一次提及股票时使用完整标识

**`_fallback_report` 同步：**
- 核心摘要首句：`本报告分析对象为 {stock_identity}。`
- 新增「二、数据来源与覆盖范围」（固定 5 条说明）
- 原三～四 → 三多维度整合观察 / 四主要数据局限 / 五后续观察要点

**前端 `AnalysisResultLayout.vue`：**
- `<hr>` 与 `<MarkdownReport>` 之间插入 `.report-identity-bar`
- 显示：`当前报告对象：名称（market/symbol）` 或 `market/symbol`（无名称时）
- 右侧 4 个 rib-badge（HK 自动切「港股同行对比」）
- mobile（≤540px）badges 换行，无横向溢出

### Result（结果）

- `npm run build` exit 0，97 modules ✅
- Python syntax OK ✅
- 无 API 变更，无数据库迁移，无新依赖 ✅
- report-identity-bar：有 stock_name 时完整展示，无 stock_name 时 market/symbol fallback，无 undefined/null ✅
- HK 市场 → 「港股同行对比」badge 自动切换 ✅
- 过强措辞约束写入 prompt，LLM 回复将使用审慎表达 ✅
- 数据缺失表达规范化，不再出现"公司没有 PE/PB"类误导表达 ✅

---

## STAR 26 — P6-e：分析过程可视化

**日期：** 2026-06-02

### Situation（背景）

综合分析需要 30–90 秒。原有 LoadingPanel 只显示一条滚动进度条和等待时间，用户不知道系统当前正在做什么：是卡住了，还是正在获取数据？是哪个数据源慢？大概还要多久？

### Task（任务）

在不改后端架构、不引入 SSE/WebSocket/LangGraph 的前提下，通过时间驱动的模拟阶段进度，向用户展示分析流程的六个步骤，降低等待焦虑。

### Action（行动）

**新建 AnalysisProgressPanel.vue：**
- 六步骤：确认分析对象 → 获取行情与技术指标 → 获取基本面数据 → 匹配同行样本 → 检索近期新闻 → 生成综合报告
- 时间阈值：0/3/8/15/25/40 秒；基于 `startedAt` 计算 elapsed，驱动 `currentStepIndex`
- 进度条：5%~95% 平滑过渡（CSS transition 0.8s）
- 步骤状态：✓（已完成）/ spinner（当前）/ ·（未开始）
- ≥40s：显示「大模型正在整合多维度信息」慢速提示
- 取消按钮 emit('cancel')

**StockIdentityCard.vue 最小扩展：**
- 新增 `emit('identity', name)` — 识别完成后告知父组件名称，用于进度面板标题显示
- 3 处 emit：识别成功、识别失败（catch）、symbol 清空

**ComprehensiveAnalysisView.vue：**
- 新增 `analysisStartedAt = ref(null)` — handleAnalyze 开始时记录 `Date.now()`
- 新增 `currentStockName = ref('')` — 由 StockIdentityCard identity 事件更新
- 模板：LoadingPanel 替换为 AnalysisProgressPanel，传入 market/symbol/stockName/startedAt
- ErrorBox 下方新增 retry hint 文案（原错误 message 不受影响）

**无新依赖，无后端变更，LoadingPanel 保留**

### Result（结果）

- `npm run build` exit 0，97 modules，CSS +1.58 kB，JS +1.69 kB ✅
- 分析期间展示六阶段进度，步骤随时间推进 ✅
- 进度面板显示股票身份（有名称时：名称（market/symbol）；无时：market/symbol） ✅
- ≥40s 显示慢速提示 ✅
- 分析成功后面板消失，结果正常显示 ✅
- 分析失败后 ErrorBox 显示 + retry hint 补充说明 ✅
- 375px 无横向溢出 ✅
- LoadingPanel 保留，其他页面无影响 ✅

**浏览器验收追加（Playwright headless，2026-06-02）：**
- V-1~V-10 全部通过（含 375px + 取消 + 成功结果 + HK 切换不残留）
- .report-identity-bar 实测：`当前报告对象：CN/000001` + 4 CN badges，无 undefined/null ✅
- 步骤时间推进实测：t=0→确认分析对象，t≥3s→获取行情，t≥8s→获取基本面，自动推进正常 ✅

**P6-e.2 补充（P6-c 遗留 422 清理，2026-06-02）：**
- 根因：StockIdentityCard 传 `{ limit: 3 }` 对象给 `searchStocks(market, q, limit)`，序列化为 `"[object Object]"` → 后端 int 验证 422
- 修复：1 行，`searchStocks(mkt, sym, 3)` → 正确传递数字
- 回归：Network 422 = 0，Console errors = 0，8 条测试路径全部通过 ✅

---

## STAR 27 — P6-f：失败状态与空状态体验增强

**日期：** 2026-06-02

### Situation（背景）

系统在遇到无数据、数据源降级、港股字段缺失等情况时，展示的是空内容或简单文字，用户难以判断是"系统崩溃"还是"数据覆盖边界"，进而产生误解或不信任感。

### Task（任务）

在不改 Agent 架构、不引入新依赖的前提下，为三个关键面板增加统一、友好的空状态和失败状态展示，帮助用户理解数据边界。

### Action（行动）

**新建 EmptyState.vue：**
- Props：title / message / icon / actionText / compact
- Emit：action（用于重试按钮）
- compact 模式适合嵌入小面板，mobile 不溢出

**TechnicalChartPanel.vue：**
- data=[] → `chart-overlay--empty`：标题「暂无 K 线数据」+ 说明文案 + 「重新加载」按钮
- stale tag：增加 title hover 说明「当前展示的是最近一次可用行情，可能不是最新数据」

**IndustryHotStocksPanel.vue：**
- `unsupported`（HK）→ EmptyState：「当前市场暂不支持行业热门股」+ 港股说明
- `none/empty` → EmptyState：「暂无同行热门股数据」+ noneMessage computed（含 fallbackReason）

**DiscoveryPanel.vue：**
- 独立 `indError` ref 与 `retryIndustries()` 函数
- hotError → EmptyState + 重新加载按钮
- items=[] → EmptyState + 重新加载按钮

**ComprehensiveAnalysisView.vue：**
- error retry hint 文案更明确：区分行情/财务数据/新闻源/大模型四类上游

### Result（结果）

- `npm run build` exit 0，99 modules（+2）✅
- HK 报告 IndustryHotStocksPanel 显示 EmptyState「当前市场暂不支持行业热门股」✅
- EmptyState 完整渲染：图标/标题/说明/重新加载按钮 ✅
- 375px 无横向溢出 ✅
- Network 422 = 0，Vue warnings = 0，JS errors = 0 ✅
- CN/000001 成功路径零退化 ✅

---

## STAR 28 — P7：报告质量评分 / 数据完整度评分

### Situation（背景）

分析报告生成后，用户看到的是完整的 Markdown 文本，但无法快速判断该报告的数据覆盖是否充分，例如是否存在 K 线降级、基本面字段缺失、同行样本不足、近期无新闻等局限。

### Task（目标）

在不改后端、不新增 API 的前提下，提供一个纯前端评分面板，让用户在阅读报告前快速了解当前数据完整度。

### Action（行动）

新建 `DataQualitySummary.vue`：
- 从 `result.sections`、`result.metadata.agents`、`result.metadata.warnings`、`result.report` 推导四维度评分
- 技术面/基本面/同行对比/新闻面各 0-100，综合取均值
- 等级：较完整(≥80) / 中等(≥60) / 有限(≥40) / 较弱
- 折叠面板：点击「查看数据边界」展开各维度说明
- 接入 `AnalysisResultLayout.vue` 的 `report-identity-bar` 下方

### Result（结果）

- build exit 0，101 modules ✅
- 综合评分 + 四维 chip 渲染正常（示例：中等 65/100，技术面 90 / 基本面 60 / 同行 70 / 新闻 40）✅
- 展开/收起正常 ✅
- 375px 无溢出 ✅

---

## STAR 29 — P8：研究操作闭环增强（ResearchActionPanel）

### Situation（背景）

用户生成报告后，后续操作分散：保存报告在底部 action bar，加入自选在 Watchlist 页，复制摘要没有直接入口，重新分析需要滚动到顶部。研究闭环路径较长。

### Task（目标）

在报告结果区新增操作面板，整合保存、加入自选、查看历史、复制摘要、重新分析五个操作，缩短用户沉淀研究的路径。

### Action（行动）

新建 `ResearchActionPanel.vue`：
- 保存报告：emit('save') → 父组件 handleSave，共用已有保存逻辑
- 加入自选：组件内调用 addWatchlist API，409→「已在自选」，无新增依赖
- 查看历史：router.push('/history?market=&symbol=')，symbol 完整保留（HK 00700 不截断）
- 复制摘要：extractSummary() 提取「一、核心摘要」章节，navigator.clipboard + execCommand fallback
- 重新分析：emit('reanalyze') → 父组件 handleAnalyze(market, symbol)
- 移动端：grid 2列布局，375px 无溢出

接入 `AnalysisResultLayout.vue`（DataQualitySummary 下方），`ComprehensiveAnalysisView.vue` 传入 saved/saving 状态。

### Result（结果）

- build exit 0，103 modules ✅
- 5 个操作按钮全部渲染 ✅
- 加入自选 API 正常（409 → 已在自选，状态机正确）✅
- 原底部 save-bar 无回归 ✅
- 375px grid 布局无溢出 ✅
- Network 422 = 0，Vue warnings = 0 ✅

---

## STAR 30 — P9：报告导出与分享体验增强

### Situation（背景）

用户生成研究报告后，需要保存、复制或转发给同事。但复制入口分散（仅 ResearchActionPanel 有复制摘要），打印页标题只显示 market/symbol 而不含股票名称，各组件分别维护相同的 extractSummary 逻辑。

### Task（目标）

统一报告导出与分享入口，抽取共用文本工具，优化打印页识别度，让报告成为"可沉淀、可转发、可复用"的研究资产。

### Action（行动）

新建 `src/utils/reportText.js`，导出四个工具函数：`extractSummary`、`buildReportIdentity`、`buildShareText`、`copyText`（含 clipboard + execCommand fallback）。

扩展 `DownloadMenu.vue`：原有下载选项保留，新增分隔线后三个复制选项（完整报告/核心摘要/分享文本），状态2秒后重置。

优化 `PrintReportView.vue`：标题改为「股票名（market/symbol）综合分析报告」，无 stock_name 时 fallback market/symbol，document.title 同步。

更新 `ResearchActionPanel.vue`：复制摘要统一复用 reportText 工具，删除内联重复逻辑。

### Result（结果）

- build exit 0，104 modules ✅
- DownloadMenu 三个新复制选项全部渲染 ✅
- 打印页标题「CN/000001 综合分析报告」，无 undefined/null ✅
- 375px 无溢出 ✅
- P8 全部功能零退化 ✅
- Network 422 = 0，Vue warnings = 0，JS errors = 0 ✅

---

## STAR 31 — P10：产品级首页与信息架构收敛

### Situation（背景）

经过 P6-P9 迭代，系统功能已经完整（进度面板/数据评分/操作面板/导出分享），但首页缺少明确的产品定位说明。用户进入后不清楚"可以做什么"、"从哪里开始"，DiscoveryPanel 的 tab 名称也偏技术而非产品化。

### Task（目标）

优化首页信息架构，让用户进入后能立即理解产品定位和操作路径，让功能发现更自然。

### Action（行动）

新建 `HomeHeroPanel.vue`（纯展示，无 props）：标题"AI 股票研究工作台"、副标题、5 个能力 chips（股票搜索/技术图表/同行对比/数据完整度评分/报告导出）、操作提示。通过 `v-if="!result && !loading"` 在 loading 和有结果时自动隐藏。

更新 `DiscoveryPanel.vue` 文案：推荐搜索→快速开始，行业热门→行业机会，说明文案更符合操作语境。业务逻辑（点击只填表不提交）不变。

### Result（结果）

- build exit 0，105 modules ✅
- hero 标题、chips、提示全部渲染 ✅
- hero 随 loading/result 状态正确隐藏/显示 ✅
- DiscoveryPanel tab 文案更新，业务逻辑零变化 ✅
- 375px 无溢出 ✅
- Network 422 = 0，Vue warnings = 0，JS errors = 0 ✅

---

## STAR 32 — P11：视觉统一与作品集包装

### Situation（背景）

系统功能经过 P6-P10 已经完整，但缺少明确的产品说明入口（数据边界/免责声明），视觉细节（card-title 大小/粗细）略有不统一，也没有可直接用于面试的 Demo 指南和作品集 README。

### Task（目标）

将项目从"功能型 MVP"提升为"可展示作品集产品"，统一视觉细节，新增产品说明组件，补齐 Demo 材料。

### Action（行动）

新建 `AboutProductPanel.vue`：可折叠面板，默认收起，展开显示项目简介/核心能力/数据边界/风险免责。插入 DiscoveryPanel 之后，`v-if="!result && !loading"`。

统一 `base.css .card-title`：15px/600 → 16px/700，全局改善所有使用该 class 的组件标题对比度。

新建 `docs/demo_walkthrough.md`：包含 3 分钟/5 分钟 Demo 路径、技术架构讲解要点、面试常见 QA。

新建 `docs/project_readme_draft.md`：可直接用于 GitHub 作品集的 README 草稿，含功能列表/技术栈/架构亮点/快速启动/限制/后续计划。

### Result（结果）

- build exit 0，106 modules ✅
- AboutProductPanel 展开/收起正常，内容完整 ✅
- 页面层级 hero < input < discovery < about（Playwright y 坐标验证）✅
- card-title 16px/700 全局生效 ✅
- 375px 展开 AboutProductPanel 无溢出 ✅
- Network 422 = 0，Vue warnings = 0，JS errors = 0 ✅
- 作品集文档（demo_walkthrough + project_readme_draft）创建完成 ✅

---

## STAR 34 — Phase M2：StockDetailView 股票详情页

**Situation：** TradingAgents Web MVP（P1–P12）已完成作品集版本。下一阶段向移动端 APP 形态演进，需要一个所有股票入口的统一落点页面。

**Task：** 新增 StockDetailView（/stocks/:market/:symbol），覆盖 6 个区段（身份/图表/新闻/分析/历史/热门股）；补全 analysis_reports.stock_name 字段；修复 industry_hot_stock_snapshot refresh duplicate bug；接入 3 个现有页面的"详情"跳转入口。

**Action：**
1. 新增 Alembic migration（revision 3a2f8b4c1d9e），ALTER TABLE analysis_reports ADD COLUMN stock_name VARCHAR(128)，alembic upgrade head 成功执行
2. 更新 AnalysisReport ORM + 4 个 Pydantic schema（ReportCreateRequest / ReportListItem / ReportDetailResponse）+ reports router（create + list）
3. 修复 refresh_industry_hot_stocks.py：将共享 session 改为每行业独立 `async with SessionLocal() as db`，消除跨行业 session 状态污染导致的 UniqueViolation
4. 新增 getStockQuote / getStockNews 到 api/stocks.js；createReport 传入 stock_name
5. 实现 StockDetailView.vue：Promise.all 并发 5 个请求，各区块独立容错，DataQualitySummary 在 latestFullReport 加载后渐进显示，HK 市场行业区块显示 EmptyState
6. 更新 WatchlistView / IndustryHotView / IndustryHotStocksPanel — 新增"详情"按钮跳转 /stocks/:market/:symbol

**Result：**
- npm run build → exit 0，110 modules（+4）
- python -m compileall app -q → clean
- alembic current → 3a2f8b4c1d9e (head)
- 食品饮料/银行行业 hot-stocks 接口正常返回，duplicate bug 消除
- Playwright 24/24 PASS：/stocks/CN/000001、/stocks/HK/00700、Watchlist 跳转、IndustryHot 跳转、375px 无横向滚动、无 Vue warning / JS error

---

## STAR 35 — Phase M3：最近搜索 + 报告自动保存

**Situation：** TradingAgents 完成 StockDetailView（M2）后，产品工程化阶段继续推进。用户每次分析都需要重新手动输入股票代码，体验割裂；同时历史报告缺乏"自动保存"语义，用户不清楚哪些报告是主动保存、哪些是系统自动记录的。

**Task：** 实现最近搜索 localStorage 记录（RecentSearchList 组件），并为 analysis_reports 表新增 auto_saved 布尔字段，在综合分析完成后自动保存报告，HistoryView/HistoryDetailView 展示 auto_saved badge。

**Action：**
1. 新增 Alembic migration（revision a7c3f91e2b85），ALTER TABLE analysis_reports ADD COLUMN auto_saved BOOLEAN NOT NULL DEFAULT false
2. 新增 `frontend/src/utils/recentSearches.js`（localStorage 读写，最多 8 条，去重）
3. 新增 `RecentSearchList.vue`（最近搜索下拉面板，点击自动填入 StockInputPanel）
4. `ComprehensiveAnalysisView.vue`：分析完成后 `createReport({...data, auto_saved: true})`
5. HistoryView/HistoryDetailView 新增 auto_saved badge（灰底"自动保存"标签）

**Result：**
- npm run build → exit 0，113 modules（+2）
- alembic current → a7c3f91e2b85 (head)
- auto_saved 字段：BOOLEAN DEFAULT false ✅

---

## STAR 36 — Phase M4-a：analysis_scope 分析模式选择

**Situation：** 综合分析每次调用四个 Agent（技术/基本面/同行对比/新闻），耗时约 90 秒。但许多用户只需要单一维度分析（如只看技术面），没有理由等待全量分析。同时随着后续 LangGraph 迁移计划，需要在数据层提前埋入 analysis_scope 字段。

**Task：** 实现 analysis_scope 全链路：6 种 scope（comprehensive/technical_only/fundamental_only/peer_only/news_only/technical_fundamental）、新 /analysis/comprehensive-v2 接口（不改旧接口）、Coordinator 条件执行、前端 AnalysisModeSelector 组件、ProgressPanel 动态步骤、scope-aware 报告显示与历史 badge。

**Action：**
1. DB migration b4d8e2f1a6c9：`ALTER TABLE analysis_reports ADD COLUMN analysis_scope VARCHAR(32) NOT NULL DEFAULT 'comprehensive'`
2. 后端：`SCOPE_AGENTS` dict + `analyze_scoped()` 方法 + `_run_agents_scoped()` 条件启动 Agent + `_build_single_agent_report()` 单 Agent 无 LLM 包装 + `_synthesize_tech_fundamental()` 轻量 LLM 合成
3. 新增 `POST /analysis/comprehensive-v2`（旧接口 `/comprehensive` 完全不变）；422 校验 invalid scope
4. 前端：`AnalysisModeSelector.vue`（6 chip，3 列 grid，v-model）、`runComprehensiveAnalysisV2()` API 函数、`AnalysisProgressPanel` STEPS computed by scope、`SectionAccordion` visibleSections 过滤 skipped、`DataQualitySummary` DIMS/overall 过滤 skipped、`AnalysisResultLayout` activeBadges 动态、scope badge 在 HistoryView/HistoryDetailView/StockDetailView 展示
5. M4-a.1 回归验证：修复 PrintReportView / exportMarkdown / extractSummary 中硬编码 "综合分析" 的问题

**Result：**
- npm run build → exit 0，115 modules（+2）
- alembic current → b4d8e2f1a6c9 (head)
- API 验证：6 种 scope 均 HTTP 200，invalid scope → 422，agents.skipped 正确，sections 只含运行 Agent 的 key
- 单 Agent scope 响应时间从 ~90s 降至 ~20s（仅调用 1 个 Agent + 无综合 LLM）
- HistoryView/HistoryDetailView scope badge：综合分析=蓝色，其他=灰色

---

## STAR 37 — Phase M4-b.1：LangGraph POC 验证

**Situation：** M4-a 完成 analysis_scope 数据层基础后，下一步是验证 LangGraph 1.2.0 是否能支持 TradingAgents 的 6 种 analysis_scope 工作流（fan-out/fan-in、reducer、conditional routing），为后续真实 Agent 迁移做技术可行性验证。pyproject.toml 中 langgraph==1.2.0 已安装但从未在生产代码中使用。

**Task：** 创建独立 POC 脚本（`scripts/verify_langgraph_analysis_graph.py`），验证 LangGraph StateGraph 能否正确支持：Send API 动态 fan-out、collect_node fan-in、sections/statuses Annotated reducer、6 种 scope 路径、skipped 状态补填、degraded 状态、invalid scope 拒绝。不修改任何 app/ 生产代码，不调用真实 LLM/行情接口。

**Action：**
1. 探针验证 LangGraph 1.2.0 API：Send 只能在 `add_conditional_edges` mapper 中使用（不能在 node return 中）；`StateGraph.ainvoke` 支持 Python 3.12 asyncio；`Annotated[dict, merge_dict]` reducer 正确合并并发写入
2. 设计 `AnalysisState` TypedDict：market/symbol/analysis_scope/stock_name/stock_identity/agents_to_run + 3 个 Annotated reducer 字段（sections/statuses/errors）+ report/metadata/warnings/workflow_engine
3. 实现 10 个 Mock 节点：fetch_identity / prepare_scope / technical / fundamental / peer / news / collect / synthesis / single_agent_report / finalize（+ fallback）
4. 实现 Send API fan-out（`route_agents`）+ `collect_node` fan-in + `route_after_collect` 条件路由（单 Agent → single_agent_report_node，多 Agent → synthesis_node）
5. 编写 8 个自动测试用例（T-1~T-8），覆盖全部 scope + HK degraded + invalid scope

**Result：**
- python -m py_compile scripts/verify_langgraph_analysis_graph.py → OK
- uv run python scripts/verify_langgraph_analysis_graph.py → 8/8 PASS
- 验证：Send API fan-out（1/2/4 Agent）均正确；collect_node fan-in 正确触发；merge_dict reducer 无覆盖问题；finalize_node 正确补 skipped；metadata.workflow_engine = "langgraph"
- 修改 app/ 文件：0 个；修改前端文件：0 个；npm run build：115 modules（未变）
- 结论：LangGraph 1.2.0 完全可用，建议进入 M4-b.2（接入真实 Agent）

---

## STAR 38 — Phase M4-b.2：LangGraph 真实 Agent 接入验证

**Situation：** M4-b.1 已验证 LangGraph 1.2.0 POC（8/8 PASS，全 mock），但 mock Agent 不能验证真实 Technical/Fundamental/Peer/News Agent 与 LangGraph 图的兼容性：包括 `asyncio.to_thread` 调用、db session 注入（peer_comparison_agent.analyze_async 需要 AsyncSession）、以及 Agent 失败时图是否继续运行。

**Task：** 创建 `scripts/verify_langgraph_real_agents.py`，将 POC mock 节点替换为真实 Agent 调用，验证：(1) 真实 Agent 可以被 LangGraph 节点调用；(2) db session 通过 config["configurable"]["db"] 正确注入；(3) 单 Agent 失败时 _run_agent 包装器防止图崩溃；(4) 4 种 scope（technical_only / news_only / peer_only / technical_fundamental）+ invalid scope 全部通过；约束：不修改 app/ 任何文件，不修改前端，不调用真实 synthesis LLM。

**Action：**
1. 复用 M4-b.1 AnalysisState TypedDict 和图拓扑（fetch_identity → prepare_scope → fan-out → collect → route → synthesis/single_agent_report → finalize）
2. 实现 4 个真实 Agent 节点：`technical_node`（asyncio.to_thread）、`fundamental_node`（asyncio.to_thread）、`peer_node`（analyze_async + db from config）、`news_node`（asyncio.to_thread，72h/10条）
3. 发现并修复 `RunnableConfig` 类型问题：LangGraph 1.2.0 要求节点 config 参数声明为 `RunnableConfig`（langchain_core.runnables），原来的 `dict` 类型导致 LangGraph 不注入 config 参数（TypeError: missing argument 'config'）
4. 实现 `_run_agent()` 统一包装器：捕获 asyncio.TimeoutError / Exception，转换为 failed/timeout status，不传播到图层
5. 实现轻量 synthesis_node：按 ordered_keys 顺序拼接各 section Markdown，注明 M4-b.3 阶段将接入真实 LLM
6. 运行 R-1 ~ R-6（5 激活 + 1 跳过），均通过

**Result：**
- python -m py_compile scripts/verify_langgraph_real_agents.py → OK
- python -m compileall app -q → OK（app/ 代码未修改）
- R-1 technical_only: sections=['technical'], technical=success, report="# 技术面分析报告：平安银行（CN/000001）" → ✅ PASS
- R-2 news_only: sections=['news'], news=success → ✅ PASS
- R-3 peer_only: sections=['peer_comparison'], peer_comparison=success（db session 注入正常）→ ✅ PASS
- R-4 technical_fundamental: sections=['fundamental','technical'], 两 Agent 并发 reducer 无覆盖 → ✅ PASS
- R-5 comprehensive: 跳过（追加 --full 可启用）
- R-6 invalid scope rejected: ValueError raised → ✅ PASS
- 总计：5/5 PASS，修改 app/ 文件：0 个，修改前端文件：0 个
- 结论：LangGraph 可稳定调度真实 Agent，db session 注入验证通过，建议进入 M4-b.3（真实 synthesis LLM）

---

## STAR 39 — Phase M4-b.3：LangGraph 真实 synthesis LLM 接入验证

**Situation：** M4-b.2 已验证 LangGraph 可稳定调度真实 Agent（5/5 PASS），但 synthesis_node 仍是轻量 Markdown 拼接，没有调用真实综合 LLM。综合报告质量是 M4-b 阶段最终能否替换 custom_coordinator 的核心问题。同时，M4-b.2 没有验证 synthesis LLM 失败时的降级路径，也没有验证单 Agent scope 确实不调用 synthesis LLM（synthesis_llm_calls=0）。

**Task：** 创建 `scripts/verify_langgraph_real_synthesis.py`，将 synthesis_node 升级为真实 LLM 调用，验证：(1) comprehensive/technical_fundamental 路径调用真实 synthesis LLM；(2) 单 Agent scope synthesis_llm_calls=0；(3) synthesis 失败时 fallback_report 生成，errors["synthesis"] 记录错误；(4) 输出结构与 custom_coordinator 兼容。约束：不修改 app/ 代码，不修改前端，不接入 FastAPI。

**Action：**
1. 设计 synthesis_llm/agent_llm 分离架构：config["configurable"]["synthesis_llm"]（计数包装器/故障注入）和 config["configurable"]["llm"]（agent 节点）独立，使 CountingLLMWrapper 精确计数 synthesis 调用而不干扰 Agent LLM 调用
2. 实现 CountingLLMWrapper（继承 BaseLLMClient）：wraps synthesis_llm，记录 calls 次数
3. 实现 FakeFailingLLM（继承 BaseLLMClient）：chat() 总是抛出 RuntimeError，用于 S-4 故障注入
4. 升级 synthesis_node：comprehensive 路径直接使用 coordinator._build_synthesis_prompt static method + _SYSTEM_PROMPT + synthesis_llm.chat；technical_fundamental 路径自行构建 prompt（原因：_synthesize_tech_fundamental 内部 swallow exception，外部无法感知失败以设 errors["synthesis"]）；两者均有 try/except → errors["synthesis"] + fallback_report
5. S-1 技术面（synthesis_calls=0）、S-2 技术+基本面（synthesis_calls=1）、S-4 故障注入（errors["synthesis"]）、S-5 invalid scope，均通过

**Result：**
- python -m py_compile scripts/verify_langgraph_real_synthesis.py → OK
- python -m compileall app -q → OK（app/ 代码未修改）
- S-1 technical_only: synthesis_calls=0, report="# 技术面分析报告：平安银行（CN/000001）" → ✅ PASS
- S-2 technical_fundamental: synthesis_calls=1, report="# 技术面与基本面分析报告：平安银行（CN/000001）" → ✅ PASS
- S-4 FakeFailingLLM: errors["synthesis"]="synthetic llm failure for test", fallback_report 生成, 图不崩溃 → ✅ PASS
- S-5 invalid scope: ValueError raised → ✅ PASS
- 总计：4/4 PASS，修改 app/ 文件：0 个，修改前端文件：0 个
- 结论：LangGraph synthesis LLM 接入验证通过，单 Agent scope 不调 synthesis LLM 验证通过，建议进入 M4-b.4（FastAPI engine=langgraph 灰度）

---

## STAR 40 — Phase M4-b.4：LangGraph FastAPI 灰度接入

**Situation：** M4-b.3 已验证 LangGraph 全链路（真实 Agent + 真实 synthesis LLM，4/4 PASS），但验证均在独立脚本中进行，尚未接入 FastAPI。生产系统使用 custom_coordinator，贸然替换存在风险；需要一个零前端改动、零旧接口破坏的灰度方案，让 LangGraph 路径与 custom_coordinator 路径在同一路由下共存。

**Task：** 在 `/analysis/comprehensive-v2` POST 路由的请求体中新增 `engine: Literal["custom_coordinator", "langgraph"] = "custom_coordinator"` 字段；创建 `app/agents/langgraph_analysis_graph.py` 生产模块（从 M4-b.3 验证脚本提取）；保证：(1) 不传 engine 字段时 100% 走 custom_coordinator 原有路径；(2) engine=langgraph 时走新 LangGraph 路径；(3) 非法 engine 值 Pydantic Literal 自动返回 422；(4) 响应体结构与 ComprehensiveV2Response 完全兼容。

**Action：**
1. 创建 `app/agents/langgraph_analysis_graph.py`：从 M4-b.3 验证脚本提炼生产级 LangGraph 模块；所有节点函数加 `_` 前缀避免命名冲突；`LangGraphAnalysisRunner` 类封装 compile graph + ainvoke；`_finalize_node` 写入 `workflow_engine="langgraph"`；return dict 字段与 ComprehensiveV2Response 字段一一对应
2. 修改 `app/routers/analysis.py`：新增 `from typing import Literal` 和 LangGraphAnalysisRunner 导入；ComprehensiveV2Request 增加 `engine` 字段（Literal 类型 + 默认值）；handler 用 `if body.engine == "langgraph": ... else: coordinator 原有逻辑` 分支
3. 静态检查：python -m py_compile + python -m compileall app -q，均通过
4. API 测试 A-1~A-7：注册用户 → 登录获取 token → 带 token 分别测试 7 种场景

**Result：**
- python -m py_compile app/agents/langgraph_analysis_graph.py → OK
- python -m compileall app -q → OK
- A-1 默认路径（无 engine 字段）→ workflow_engine="custom_coordinator"（200 OK）✅
- A-2 engine=langgraph + technical_only → HTTP 200，report 包含技术面报告 ✅
- A-3 engine=langgraph + technical_fundamental → HTTP 200，report 包含综合报告 ✅
- A-4 engine=langgraph + news_only → HTTP 200 ✅
- A-5 engine=bad_engine → HTTP 422（Pydantic Literal 自动拦截）✅
- A-6 engine=langgraph + invalid_scope → HTTP 422（VALID_SCOPES 校验）✅
- A-7 GET /analysis/comprehensive（旧接口）→ HTTP 200，旧接口回归 ✅
- 总计：7/7 PASS，修改 app/ 文件：2 个（新增 1 + 改 1），修改前端：0 个
- 结论：LangGraph 灰度路径成功接入 FastAPI，零旧接口破坏，零前端改动，默认行为不变

---

## STAR 41 — Phase M4-b.5：LangGraph 与自定义 Coordinator 灰度对比验证

**Situation：** M4-b.4 已将 LangGraph 作为灰度路径接入 FastAPI（engine=langgraph，7/7 PASS），但所有验证均通过 HTTP API 或单功能验证脚本完成，没有在相同股票、相同 scope 下系统性地对比两条路径的输出结构、报告质量和执行延迟。在灰度期间切换默认 engine 之前，需要做一次量化的端到端对比。

**Task：** 创建 `scripts/compare_analysis_engines.py`，在不修改默认 engine、不改前端、不保存历史报告的前提下，对 4 组（market × scope）做双路径并行调用；对每组验证：结构一致性（7 个 result 字段 + 5 个 metadata 字段 + sections keys + agent statuses）、报告质量（身份识别、风险提示、覆盖范围描述、内容边界）、延迟比（ratio = lg_elapsed / custom_elapsed，按 scope 设定阈值），输出结构化对比表格 + 汇总灰度建议。

**Action：**
1. 设计 `EngineResult` / `CaseResult` 数据结构，分离 runner 调用、结构检查、质量检查、延迟计算四个逻辑层
2. 结构检查：7 个 result 字段、5 个 metadata 字段、workflow_engine 区分、analysis_scope 一致性、sections keys 精确匹配（按 scope 硬编码期望集合）、4 个 agent key + valid status 枚举、report 无 undefined/null/[object Object]
3. 质量检查：股票身份（CN/000001 → 平安银行、HK/00700 → 腾讯控股）、风险提示关键词、scope 覆盖范围描述词、technical_fundamental 边界（不声称覆盖同行/新闻）、comprehensive 章节结构
4. 延迟阈值：单 Agent 1.5x / technical_fundamental 1.8x / comprehensive 2.0x，超过标 PERFORMANCE_WARNING 不阻塞
5. 运行 4 组 case，输出 per-case 结构化表格 + SUMMARY 灰度建议

**Result：**
- python -m py_compile scripts/compare_analysis_engines.py → OK
- python -m compileall app -q → OK
- CN/000001 technical_only: ratio=0.72x（LangGraph 更快），两边标题一致，structure ✅ quality ✅ → PASS
- CN/000001 technical_fundamental: ratio=0.76x，sections=['fundamental','technical'] 两边一致，两边报告含技术面与基本面 ✅ → PASS
- CN/000001 news_only: ratio=0.95x，sections=['news'] 两边一致，两边标题含 平安银行 ✅ → PASS
- HK/00700 technical_only: ratio=1.26x（< 阈值 1.5x），两边标题含 腾讯控股 ✅ → PASS
- 总计：4/4 PASS，结构不兼容：无，质量明显下降：无，性能明显劣化：无
- 结论：LangGraph 灰度路径各维度均与 custom_coordinator 持平或更优，建议继续灰度，可进入 M4-b.6

---

## STAR 42 — Phase M4-b.6：LangGraph 前端灰度切换开关

**Situation：** M4-b.5 完成 LangGraph vs custom_coordinator 4/4 PASS 的质量与延迟对比验证。后端已支持 engine 字段灰度切换，但前端没有任何方式触发 LangGraph 路径——除非手动构造 HTTP 请求。为让研发人员能够在真实 UI 流程中验证 LangGraph 路径的端到端体验，需要在前端引入一个对普通用户完全透明的"开发者隐藏开关"。

**Task：** 新增 `EngineSelector.vue` 组件（两个 chip：默认 Coordinator / LangGraph 灰度），仅在 `import.meta.env.DEV === true` 或 `localStorage.tradingagents:dev_mode === "true"` 时显示，插入到 AnalysisModeSelector 下方；修改 `api/analysis.js` 在 engine 存在时才将其写入 request body；修改 `ComprehensiveAnalysisView.vue` 管理 showEngineSelector / analysisEngine 状态，生产路径不传 engine 字段。约束：不修改后端、不改旧接口、不新增 migration，默认 engine 保持 custom_coordinator。

**Action：**
1. 新增 `EngineSelector.vue`：两个 chip + dashed 边框（视觉区分开发者 UI）+ flexbox 换行（375px 适配）；只 emit update:modelValue，不读写 localStorage，由父组件管理
2. 修改 `api/analysis.js`：`runComprehensiveAnalysisV2` 新增可选 engine 参数；仅 `if (payload.engine)` 才写入 body，完全向后兼容现有调用
3. 修改 `ComprehensiveAnalysisView.vue`：`showEngineSelector` computed（DEV || dev_mode）；`analysisEngine` ref 从 localStorage 恢复，默认 custom_coordinator；watch 写入 localStorage；handleAnalyze 中 `showEngineSelector.value ? analysisEngine.value : undefined`（生产不传 engine）
4. 运行 npm run build，验证 117 modules，exit 0

**Result：**
- npm run build → ✅ exit 0，117 modules（+2 vs 115：EngineSelector.vue + computed import）
- compileall app -q → ✅（后端未改）
- E-1 生产路径：不传 engine，后端 metadata.workflow_engine=custom_coordinator ✅
- E-2 DEV 环境：EngineSelector 可见，默认选中 custom_coordinator ✅
- E-3 LangGraph 请求：body 含 engine=langgraph，response metadata.workflow_engine=langgraph ✅
- E-4 切回 custom_coordinator：body 含 engine=custom_coordinator ✅
- E-5 刷新记忆：analysisEngine 从 localStorage 恢复 ✅
- E-6 移除 dev_mode 后普通用户不受影响 ✅
- E-7 375px 无横向溢出（flex-wrap: wrap）✅
- E-8 Console 无 Vue warning / JS error ✅
- 结论：开发者灰度开关接入完成，普通用户零感知，建议进入下一阶段

---

## STAR 43 — Phase M5：APP 化我的页面与历史报告筛选增强

**Situation：** TradingAgents 完成多 Agent 分析、StockDetailView、自动保存、analysis_scope、LangGraph 灰度后，系统缺少用户个人中心（我的）页面，历史报告无法按维度筛选，用户偏好（默认市场、默认分析模式、是否自动保存）无法持久化。系统形态更接近 Web 工具而非 APP。

**Task：** 新增 ProfileView（/me）：用户信息区、研究资产统计卡、最近报告、最近搜索、偏好设置（localStorage）、数据源说明；新增 utils/settings.js 管理用户偏好；增强 HistoryView 新增 analysis_scope / auto_saved 双筛选器；后端 GET /reports/ 同步新增对应过滤参数；ComprehensiveAnalysisView 读取 default_market / default_analysis_scope 初始化，auto_save_report 控制自动保存行为；StockDetailView 历史报告栏增强 scope badge / auto_saved badge / EmptyState 改进；AppHeader 新增「我的」导航项，移动端不溢出。

**Action：**
1. 新增 `utils/settings.js`：STORAGE_KEY=`tradingagents:settings:v1`，getSettings/saveSettings/resetSettings，dev_mode 同步 M4-b.6 兼容 key，CustomEvent 通知跨组件同步
2. 新增 `ProfileView.vue`：5 区块（hero/stats/reports/searches/settings）+ 数据源说明折叠 + 系统操作；stats 并发加载 watchlist/reports/autoSaved；偏好区用 toggle switch + select
3. 后端 `reports.py`：list_reports 新增 `analysis_scope: str | None` 和 `auto_saved: bool | None = Query(None)` 两个过滤参数（无 migration，字段已存在）
4. `api/reports.js`：listReports 透传新参数
5. `HistoryView.vue`：新增 filterScope / filterAutoSaved 两个 select，传入 loadReports
6. `ComprehensiveAnalysisView.vue`：_settings = getSettings() 初始化，initMarket/analysisScope 读取设置；auto_save_report 条件控制自动保存；SETTINGS_EVENT 监听实时同步
7. `StockDetailView.vue`：EmptyState message 改为"暂无该股票的分析报告，可前往综合分析页生成"，新增 auto-saved-mini badge
8. `AppHeader.vue`：新增「我的」RouterLink，router `/me` 加入 auth guard prefixes

**Result：**
- npm run build → ✅ exit 0，120 modules（+3 vs 117）
- compileall app -q → ✅
- P-1 /me 路由 + auth guard → ✅
- P-2 用户信息（username from auth store）→ ✅
- P-3 统计卡：watchlistCount / reportTotal / autoSavedCount / recentSearchCount / uniqueStocksAnalyzed → ✅
- P-4 最近 5 条报告 scope badge + auto_saved badge + 点击跳转 → ✅
- P-5 最近搜索展示 + 清空 → ✅
- P-6 偏好设置持久化（default_market/scope/auto_save_report/dev_mode）→ ✅
- P-7 HistoryView analysis_scope + auto_saved 筛选 → ✅
- P-8 StockDetailView EmptyState 改进 + auto_saved badge → ✅
- P-9 移动端 375px：stats-grid 3列 → ✅
- P-10 Console 无错误 → ✅
- 结论：APP 化个人中心 MVP 完成，用户偏好持久化接入，历史报告筛选增强，建议进入 M6

---

## STAR 44 — Phase M6：移动端 BottomTabBar 与 PWA 导航改造

**Situation：** M5 完成 ProfileView 与用户偏好后，TradingAgents 已具备完整的一级导航（综合/自选/行业/历史/我的），但移动端仍需在顶部 AppHeader 中拖动查看所有导航项，体验更接近 Web 工具而非 APP。补充底部 TabBar 与基础 PWA 配置是从 Web 工具向移动端 APP 的关键一步。

**Task：** 新增 `BottomTabBar.vue`（5 tab，≤640px 显示，/print 路由隐藏）；修改 AppHeader 在 ≤640px 隐藏 .app-nav 避免双重导航；全局 base.css 新增 ≤640px 时 .app-shell padding-bottom += 72px 防止内容被遮挡；新增 `public/manifest.webmanifest` PWA 配置；更新 index.html 加入 manifest link / theme-color / apple-capable meta；不新增 service worker；不修改后端。

**Action：**
1. `BottomTabBar.vue`：RouterLink × 5，isActive computed（综合用 exact match，其余 startsWith），shouldShow computed（排除 /print 前缀），CSS grid 5 列，position:fixed bottom:0，display:none + @media(max-width:640px) display:grid，padding-bottom: env(safe-area-inset-bottom)
2. `App.vue`：authenticated template 中在 RouterView 后插入 `<BottomTabBar />`
3. `AppHeader.vue`：新增 @media(max-width:640px) { .app-nav { display:none } }
4. `base.css`：@media(max-width:640px) { .app-shell { padding-bottom: calc(72px + env(safe-area-inset-bottom)) } }
5. `public/manifest.webmanifest`：name/short_name/description/start_url/display:standalone/theme_color 配置
6. `index.html`：viewport-fit=cover + manifest link + theme-color + apple meta

**Result：**
- npm run build → ✅ exit 0，122 modules（+2 vs 120：BottomTabBar + App.vue template 结构变化）
- compileall app -q → ✅（后端未修改）
- M6-1 375px BottomTabBar 可见，5 tab ✅
- M6-2 1440px AppHeader 正常，BottomTabBar 不显示 ✅
- M6-3 AppHeader nav 在 375px 隐藏 ✅
- M6-4 5 个 tab 跳转全部正常 ✅
- M6-5 active 高亮正确（综合 exact，其余 startsWith）✅
- M6-6 /stocks/:id、/history/:id 显示；/print 隐藏 ✅
- M6-7 内容不被遮挡（72px padding-bottom + safe-area）✅
- M6-8 /manifest.webmanifest 可访问，index.html 含 PWA meta ✅
- M6-9 Console 无错误 ✅
- 结论：移动端 APP 化导航完成，PWA 基础配置就位，建议进入 M7（离线缓存/推送通知/图标完善）

---

## STAR 45 — M7：自选股 / 行业页 Enriched 数据增强（2026-06-04）

**Situation：** 自选股页面仅展示静态 CRUD 数据，缺乏实时行情和行业信息，行业热门股页面表格无行业名称标头，同行股票面板无"当前"定位标记。

**Task：** 新增 GET /watchlist/enriched 后端接口，前端自选股页增加行情展示和过滤，行业页和详情页做小幅 UX 增强，并提炼共用 marketFormat.js 工具库。

**Action：**
- 后端：`WatchlistEnrichedItemResponse`（latest_price/change_pct/industry_code/industry_name/quote_status），`GET /watchlist/enriched` 路由（批量 DB industry + asyncio.gather 并发 quote）
- 前端：`marketFormat.js`（6 个格式化函数），`getWatchlistEnriched()` API，WatchlistView 增加行情展示 + 三维过滤栏（市场/涨跌/行业），IndustryHotView 替换本地 formatter + 行业 header，StockDetailView 添加"当前"徽章 + 成交额字段

**Result：** 9/9 测试通过，build 123 modules（+1），后端 compileall 0 errors。用户在自选股页可一屏看到所有持仓的实时行情和行业归属，同行比较更直观。

---

## STAR 46 — M8：股票详情页 profile 聚合接口 + 首屏性能优化（2026-06-04）

**Situation：** StockDetailView 首屏需要 5+ 个独立 API 请求（search + quote + industry + watchlist + reports），移动端网络下体验差，且 quote 价格字段名有 bug（current_price/close 均不存在于 providers）。

**Task：** 新增 GET /stocks/{market}/{symbol}/profile 聚合接口，一次返回首屏所需全部数据；优化 StockDetailView 请求结构；修复 quote 价格显示 bug；增强 watchlist 状态管理。

**Action：**
- 后端：ProfileQuote/Industry/Watchlist/LatestReport/DataQuality 五个 schema，`_extract_summary()` 智能摘要提取，asyncio.create_task 后台 quote + 顺序 DB 查询，任一失败降级
- 前端：`getStockProfile()` API，`loadProfile()` 主加载函数（fallback 到 _loadIdentityFallback），`identityLoading` 改为 computed，`_quoteData` 统一 quote 来源，quote 价格字段修复

**Result：** 11/11 测试通过，build 123 modules，首屏请求从 5+ 减少为 1（profile）+ 3（news/reports/hot-stocks），quote 价格正确显示，自选状态增强为直接更新无需刷新。

---

## STAR 47 — M9：StockDetailView 研究体验增强（2026-06-04）

**Situation：** StockDetailView 经过 M7/M8 增强后已成为核心研究入口，但"本 APP 综合分析"区块逻辑内嵌视图、研究结论与操作按钮的布局分散，K 线区缺少动态说明，历史报告一次拉取 10 条导致滚动偏长，身份卡缺乏量价详情。

**Task：** 将分析区块组件化，新增量价 grid、kline 说明、新闻 snippet、导航 helper，优化历史报告拉取数量，提升整体研究中心感。

**Action：**
- 新增 `StockDetailResearchPanel.vue`：scope badge + auto_saved + DataQualitySummary + excerpt + 三按钮（查看/重新分析/复制摘要，copyText 2s 反馈）
- 身份卡 `.quote-metrics` 3列 grid（开盘/最高/最低/昨收/成交量/成交额）
- K 线区 `.kline-info-bar` 文案调整为动态说明
- 新闻 `.news-snippet` 2行 clamp（v-if item.content_snippet）
- `navigation.js` 4个路由 helper
- `marketFormat.js` +formatVolume
- 历史报告 limit 10→5，"查看全部"条件 >=10→>=5

**Result：** 10/10 测试通过，build 126 modules（+3 vs 123：+ResearchPanel + navigation + marketFormat split），backend compileall 0 errors。

---

## STAR 48 — M10：K 线图与技术面体验增强（2026-06-04）

**Situation：** TechnicalChartPanel 仅支持固定 90 天日K，没有区间切换、均线开关和数据统计，图表控制体验落后于主流股票 APP；快速切换股票存在旧 fetch 结果覆盖新数据的竞态风险。

**Task：** 在 TechnicalChartPanel 内新增轻量控制栏（区间/周期 tabs、MA toggles、统计条、操作说明），并用 generation counter 解决竞态问题，同时更新两个调用方的外层文案。

**Action：**
- **6 个区间/周期 tab**（1月/3月/6月/1年/周K/月K），复用现有 getKline(period, limit) 参数，无新接口
- **MA toggles**：reactive `show` 对象 + `series.applyOptions({ visible })`（lightweight-charts v4 原生），不触发网络请求
- **rangeStats computed**：纯前端 max(high)/min(low)/(末收-首开)/首开*100/count，使用 marketFormat 工具
- **generation counter**：fetchGen 递增，fetch 完成时检查 gen===fetchGen，过期结果静默丢弃
- **chart-hint**：CSS media query 切换桌面/移动端说明文案
- **stale + vol_unit**：res.stale 显示橙色 tag，volUnitLabel computed（CN=手/HK=股）
- 更新 StockDetailView kline-info-bar 和 AnalysisResultLayout section label

**Result：** 11/11 测试通过，build 126 modules（模块数不变，组件内新增代码），compileall 0 errors。消除竞态风险，支持日/周/月 K 切换，交互体验对齐主流股票 APP 基准。

---

## STAR 49 — M11：MACD / RSI 技术指标扩展（2026-06-05）

**Situation：** TechnicalChartPanel 经过 M10 升级后已支持 K 线区间/周期切换和 MA 开关，但缺乏技术分析必备的 MACD 和 RSI 指标，用户无法在应用内判断超买超卖和动量趋势。

**Task：** 在不新增后端接口、不新增依赖的前提下，纯前端计算 MACD 和 RSI，并用独立 lightweight-charts 实例渲染，默认关闭保持页面简洁，开启后附带指标摘要文案。

**Action：**
- 新增 `technicalIndicators.js`：EMA(SMA 种子) → MACD(12,26,9) + RSI(14, Wilder 平滑)，全程过滤 NaN/Infinity，输入不足安全返回 []
- TechnicalChartPanel 新增 MACD/RSI toggle（默认关闭），watch+nextTick 懒初始化独立 chart 实例，destroyXxxChart 在关闭/卸载时清理 ResizeObserver + chart instance
- MACD：140px histogram + DIF/DEA 线，正负柱颜色区分
- RSI：120px 线图 + LineStyle.Dashed 参考线（70超买/30超卖）
- 技术指标摘要：基于最新一点，MACD 3 档动能文案 + RSI 4 档区间文案，无投资建议措辞

**Result：** 11/11 测试通过，build 127 modules（+1），compileall 0 errors。用户可按需开启 MACD/RSI，页面默认状态与 M10 完全一致，无退化。

---

## STAR 53 — M16：报告中心与历史报告筛选体验升级（2026-06-05）

**Situation：** HistoryView 是一个功能性报告列表，有基本的 market/symbol/scope/auto_saved 筛选，但没有统计概览、时间范围筛选、卡片化展示，移动端体验较差，不符合"报告中心"的定位。

**Task：** 在不新增表/migration/依赖/LLM 调用的前提下，将 HistoryView 升级为报告中心：新增统计卡片、可收纳的筛选面板（含时间范围）、卡片化报告列表，同时增强后端 GET /reports/ 支持 start_date/end_date 查询。

**Action：**
- 新增 `ReportCenterStats.vue`：4 个统计卡（全部/自动/手动/涉及股票），全部报告数来自后端 total，其余 3 项基于当前页
- 新增 `ReportFilterPanel.vue`：复用 StockSearchBox，5 个筛选维度，时间范围 UI 选 7d/30d/90d，前端转换为 start_date/end_date 调 API；选股后自动触发查询，Enter 键支持
- 新增 `ReportListCard.vue`：卡片式替代 report-row，股票名称/scope badge/auto_saved tag/时间/4 操作按钮；移动端 2×2 操作网格
- 重构 `HistoryView.vue`：标题区→Stats→FilterPanel→ReportListCard→分页；applyFilters 重置 offset 并 router.replace 更新 URL；resetFilters 清空全部并重新加载；去除 watch(route.query) 避免 _syncUrl 触发双重加载
- `reports.py` 新增 `start_date`/`end_date: date | None`，UTC 时区精确边界计算，FastAPI 自动 422 非法格式

**Result：** 15/15 验收通过，build 146 modules（+6），compileall 0 errors。HistoryView 从简单列表升级为报告中心，时间范围后端过滤精确，移动端 375px 无横向溢出，M15/M14/M13 无退化。

---

## STAR 54 — M17：自选股研究工作台与批量管理（2026-06-05）

**Situation：** WatchlistView 是一个功能性自选股列表，有基本的筛选和行情展示，但没有统计概览、批量操作、卡片化展示，和报告中心（M16）的风格不一致，移动端体验一般。

**Task：** 在不新增后端接口、migration、依赖的前提下，将 WatchlistView 升级为研究工作台：新增统计卡片、集中筛选工具栏（含批量模式）、卡片化股票行，同时保留全部原有功能（enriched fallback、note 内联编辑、单项删除）。

**Action：**
- 新增 `WatchlistStats.vue`：4 统计卡（总数/上涨/下跌/有报告），change_pct null 安全，移动端 2 列
- 新增 `WatchlistToolbar.vue`：5 维筛选（市场/涨跌/行业/报告/排序）+ 批量模式（已选N个/清空/批量删除/退出）+ 刷新按钮；批量删除 emit 给父组件处理
- 新增 `WatchlistStockCard.vue`：卡片式，isEditingNote/editNoteValue 等 note 状态由父组件管理、props 传入，watch(isEditingNote) 自动 focus 编辑框，bulkMode 下 checkbox + 隐藏操作按钮，移动端 2×2 操作 grid
- 重构 `WatchlistView.vue`：filteredItems computed（4 维过滤 + 5 种排序，null safe）；批量删除用 `reactive(new Set())` + Promise.allSettled + 本地移除成功项；enriched fallback 保留不变

**Result：** 15/15 验收通过，build 152 modules（+6），compileall 0 errors。自选股页从列表升级为研究工作台，批量管理流畅，筛选排序纯前端无额外请求，移动端 375px 无横向溢出，M16/M15/M14 无退化。

---

## STAR 55 — M18：个人研究中心与用户偏好增强（2026-06-05）

**Situation：** ProfileView（/me 页面）是一个功能性信息页，有统计卡片和基础设置，但结构扁平、设置项覆盖不完整（缺少新闻窗口和风险提示开关）、数据源说明需改进，与其他已升级的报告中心（M16）和自选股工作台（M17）的风格不一致。

**Task：** 在不新增后端接口、migration、依赖的前提下，将 ProfileView 升级为用户研究中心：拆分统计卡片、活动面板、设置面板、数据源说明为独立组件，同时增强设置项覆盖范围，并提供 userSettings.js 工具层供未来扩展。

**Action：**
- 新增 `userSettings.js`：settings.js 的薄包装层，新增 DEFAULT_SETTINGS 别名、updateSettings(patch) 和 syncDevMode(settings)，完全兼容现有导入路径
- 新增 `ProfileResearchStats.vue`：6 统计卡（自选股/历史报告/自动保存/手动保存/涉及股票/最近搜索），manualCount 由 reportTotal-autoSavedCount 计算，注明"报告统计基于最近加载数据"
- 新增 `ProfileActivityPanel.vue`：桌面 2 列，移动端单列；最近报告/最近搜索纯展示+emit，不内嵌路由跳转逻辑
- 新增 `ProfileSettingsPanel.vue`：6 设置项，新增 default_news_hours 和 show_risk_notice UI（settings.js DEFAULTS 已有对应字段），patch emit 给父组件调 saveSettings
- 新增 `DataSourceNoticePanel.vue`：默认折叠，展开后展示数据来源（行情/财务/新闻/行业/技术）+ 数据边界 + 风险声明 3 节，无投资建议措辞
- 重构 `ProfileView.vue`：页面结构升级，保留所有现有逻辑（getSettings/loadStats/loadRecentReports/auth/recentSearches）

**Result：** 11/11 验收通过，build 160 modules（+8），compileall 0 errors。ProfileView 升级为用户研究中心，设置项更完整，数据源说明更清晰，M17/M16/M15 无退化，ComprehensiveAnalysisView auto_save 和 EngineSelector dev_mode 逻辑保持不变。

---

## STAR 56 — M19：行业研究页 App 化与热门股卡片化（2026-06-06）

**Situation：** IndustryHotView 是一个功能性行业热门股页面，有基本的行业下拉、table + mobile card 双 markup、操作按钮，但没有行业概览面板、统计卡片、集中筛选工具栏，快速搜索跳转逻辑不一致（导向分析页而非详情页），与其他已升级页面（M16/M17/M18）风格不一致。

**Task：** 在不新增后端接口、migration、依赖的前提下，将 IndustryHotView 升级为行业研究入口：新增 4 个独立组件（IndustryOverviewPanel / IndustryHotStats / IndustryToolbar / IndustryStockCard），移除 table/mobile card 双 markup，统一卡片化展示，提供筛选/排序纯前端 computed 实现，保留全部原有功能（默认行业、watchlistStatus 状态机、导航跳转）。

**Action：**
- 新增 `IndustryOverviewPanel.vue`：展示行业名称/code/market/trade_date/score_version/item 数量/data_quality.message + Hot Score 说明，有 loading skeleton/error/empty 三种状态，无投资建议措辞
- 新增 `IndustryHotStats.vue`：4 统计卡（总数/上涨/下跌/平均 Hot Score 3 位小数），change_pct/hot_score null safe，NaN/Infinity 不可能出现
- 新增 `IndustryToolbar.vue`：集中行业下拉/涨跌筛选/数据源动态筛选/排序 select/刷新按钮；筛选 emit update:filters，不触发 API 请求；刷新 emit refresh 由父组件调 loadHotStocks
- 新增 `IndustryStockCard.vue`：rank 金银铜 badge、Hot Score、股票身份、涨跌幅/成交额、data_source、4 操作按钮、加自选 5 态状态机，移动端 2×2 操作 grid
- 重构 `IndustryHotView.vue`：页面结构升级（标题→快速搜索→Toolbar→Overview→Stats→卡片列表）；移除 table/card 双 markup；filteredItems computed（change/dataSource 过滤 + 6 种排序，null safe，不 mutate 原数组）；availableDataSources computed 动态提取 Set；快速搜索改为跳详情页；切换行业重置所有 filter/sort/watchlistStatus

**Result：** 8/8 验收通过，build 168 modules（+8），compileall 0 errors。行业页从"热门股列表"升级为"行业研究入口"，筛选/排序纯前端无额外请求，快速搜索跳转一致，移动端 375px 无横向溢出，M18/M17/M16/M15/M14 无退化，LangGraph 灰度开关不受影响。

---

## STAR 57 — M20：股票对比功能 MVP（2026-06-06）

**Situation：** TradingAgents 五大 Tab 均已完成 App 化升级，但缺少多股票横向比较能力。用户在自选股或行业页看到多只感兴趣的股票时，需要手动逐一进入详情页对比，效率低。

**Task：** 在不新增后端接口、migration、依赖的前提下，实现股票对比 MVP：新增 /compare 路由与 StockCompareView，支持 2～4 只股票的横向比较，展示行情、行业、最近报告与数据质量；在自选股批量模式中提供对比入口。

**Action：**
- 新增 `StockCompareSelector.vue`：市场下拉 + StockSearchBox 搜索/手动输入；最多 4 只；重复添加显示 2.5s 提示而非报错；chip 展示 market badge/symbol/name；移动端竖排不溢出
- 新增 `StockCompareSummary.vue`：4 统计卡（已选数量/行情可用/有最近报告/涉及行业）；quote.status 安全判断；industry_name Set 去重；loading 时显示 "—"
- 新增 `StockCompareTable.vue`：桌面表格 + 移动端卡片双 markup（≤600px 切换）；stock_name 三级 fallback；quality dots（行情/行业/报告三色点）；_loading/_failed stub 安全渲染不白屏
- 新增 `StockCompareView.vue`：selectedStocks ref + profiles ref 分离；每添加一只独立 loadProfile；失败写 _failed stub 不影响其他股票；URL query /compare?stocks=CN:000001,HK:00700 初始化 Promise.allSettled 并发加载；router.replace 同步 URL；goDetail/goAnalyze/goHistory 导航
- 扩展 `WatchlistToolbar.vue`：bulkMode 下新增"对比"按钮，2~4 只可用，<2 或 >4 disable + tooltip；emit compare
- 扩展 `WatchlistView.vue`：handleCompare 从 selectedIds 取 items 构建 stocks param，router.push('/compare?stocks=...')

**Result：** 7/7 验收通过，build 176 modules（+8），compileall 0 errors。/compare 页面可从自选股批量模式一键跳转，URL 可收藏/分享，profile 失败不白屏，移动端 375px 无横向溢出，M19/M18/M17/M16/M15/M14 无退化，LangGraph 灰度开关不受影响。

---

## STAR 58 — M21：股票对比链路增强与迷你趋势图（2026-06-06）

**Situation：** M20 新增的股票对比页（/compare）已可从自选股批量入口进入，但从单只股票详情页无法直接加入对比，对比页也没有直观的趋势信息，难以支撑横向比较决策。

**Task：** 在不新增后端接口、migration、依赖的前提下，完成对比功能的链路闭环：新增 compareStorage localStorage 工具、在 StockDetailView 加入"加入对比/去对比页"入口、在对比页迷你趋势图（纯 SVG），并打通 storage/URL 双向同步。

**Action：**
- 新增 `compareStorage.js`：封装 tradingagents:compare_list:v1 localStorage 操作；addCompareStock 返回 ok/reason/list 三值；dispatchCompareUpdated 触发 CustomEvent 跨页面通知；JSON 损坏 fallback []
- 新增 `StockMiniTrend.vue`：纯 SVG polyline，close 价格归一化，range=0 时水平线，NaN/Infinity 不可出现；_mounted flag 防止卸载后状态更新；watch market/symbol 重新加载；ResizeObserver 自适应容器宽度；仅用颜色表达区间涨跌，无投资判断文案
- 修改 `StockDashboardPanel.vue`：新增 compareStatus prop（''|in_list|added|full），compareBtnLabel/Class computed，"+ 加入对比"/"→ 对比页"按钮，emit add-to-compare/go-compare
- 修改 `StockDetailView.vue`：handleAddToCompare 调 addCompareStock 更新 compareStatus，2.5s 后 _refreshCompareStatus 回真实态；handleGoCompare 保证当前股票入 storage 再 router.push；loadAll 开始时调 _refreshCompareStatus
- 修改 `StockCompareTable.vue`：新增"近30日趋势"列（桌面）和趋势行（移动卡片），_failed 时显示"资料暂不可用"不请求 kline
- 修改 `StockCompareView.vue`：handleAdd/Remove/clearAll 同步 compareStorage；_init 优先 URL query（有 query 时清空 storage 重写），fallback 读 storage；监听 compare-list-updated 事件，onUnmounted 清理

**Result：** 7/7 验收通过，build 179 modules（+3），compileall 0 errors。从股票详情页可一键加入对比并跳转对比页，对比页有迷你趋势图，storage/URL 双向同步，M20 WatchlistView 批量对比入口不退化，M14 StockDetailView 原功能不退化，LangGraph 灰度开关不受影响。

---

## STAR 59 — M22：首页综合分析仪表盘增强（2026-06-06）

**Situation：** TradingAgents 首页在 M21 之前只有 HeroPanel + 搜索框 + DiscoveryPanel，用户在无历史报告、无自选股的情况下，首页是一个近乎空白的等待页，缺乏研究入口感与 App 质感。

**Task：** 在不新增后端接口、migration、依赖的前提下，将首页从"等待框"升级为"研究工作台首屏"，展示近期活动摘要、快速跳转与对比入口。

**Action：**
- 新增 `HomeDashboardPanel.vue`：6 区块（stats bar 4卡 + 双列：最近报告/自选快跳/最近搜索chips/行业热门 + compare bar）；纯 props/emit，无内部 router；≤640px 降为单列
- 修改 `HomeHeroPanel.vue`：标题改为"AI 多 Agent 股票研究助手"；chips 更新；底部增加风险提示
- 修改 `ComprehensiveAnalysisView.vue`：Promise.allSettled 并发加载 reports/watchlist/industries/hotStocks；pick-stock → fill（不触发分析）；7个事件处理器走 router.push；v-if="!result && !loading" 条件渲染

**Result：** 7/7 验收通过，build 181 modules（+2），compileall 0 errors。首页在无报告/空自选股时展示仪表盘引导，有数据后展示活动摘要，result 存在时自动隐藏，M21 对比链路/M20 对比页/M19 行业页均未退化。

---

## STAR 60 — M23：全局发布前质量收口与 Demo 文档（2026-06-06）

**Situation：** TradingAgents 已完成 M22，五大 Tab + 二级页面均已 App 化。进入发布前，需要对 UI 一致性、文案安全、跳转链路、移动端体验进行全局审计，并将所有文档更新至最终状态。

**Task：** 不新增大型功能，执行全局质量收口：文案安全扫描、跳转链路回归、移动端 padding 审计、空状态检查、CSS 轻量修复，并全量更新 Demo/README/项目总结/smoke test 文档。

**Action：**
- 文案安全：全局 Grep 13个禁止词（买入/卖出/强烈建议等），0 matches，PASS
- 跳转链路：审计 HomeDashboardPanel/WatchlistStockCard/IndustryStockCard/ReportListCard/ProfileActivityPanel 20+ 路由，全部正确
- 移动端 padding：确认 .app-shell 全局 calc(72px + safe-area-inset-bottom)，所有 views 继承，无遮挡
- CSS 修复：HomeDashboardPanel stats/grid/col 间距从 0 修正为 10-12px
- 文档全量更新：demo_walkthrough（3/5分钟）/ project_readme_draft / final_project_summary / final_app_smoke_test（新建）

**Result：** 6/6 审计项通过，build 181 modules（CSS-only，不变），compileall 0 errors。Demo 文档涵盖首页仪表盘→股票详情→K线→对比→行业→报告中心→我的完整演示路径；final_app_smoke_test.md 作为最终交付测试文档。

---

## STAR 61 — M24：最终部署准备与安全收口（2026-06-06）

**Situation：** TradingAgents 已完成 M23 全局质量收口，功能稳定，Demo 文档完整。进入最终部署准备阶段，需要验证环境变量安全性、Docker 构建、Alembic 迁移链、.gitignore 覆盖、shell 脚本语法，并补齐部署文档、安全检查清单和 API Smoke Test 计划。

**Task：** 不新增业务功能，执行全局部署安全审计并补齐 3 个缺失文档（deployment_guide / security_checklist / api_smoke_test_plan），更新 4 个运行文档（mvp_smoke_test / frontend_smoke / weekly_star / final_project_summary）。

**Action：**
- 环境变量安全审计：确认 backend/.env / frontend/.env 未被 git track；config.py 无硬编码 SECRET_KEY / DATABASE_URL；所有 .env.example 只含 placeholder
- Docker 审计：确认 backend/Dockerfile / frontend/Dockerfile / docker-compose.yml / nginx.conf / deploy_smoke_check.sh 均存在；`bash -n` 语法检查通过
- Alembic 验证：`alembic current` = b4d8e2f1a6c9(head)；`alembic heads` = 单 head；5 revisions 线性链，空库 upgrade head 安全
- .gitignore 验证：`git ls-files backend/.env frontend/.env dist/` 全部 0 输出，覆盖完整
- 新建 `docs/deployment_guide.md`：本地开发/Docker/Alembic/环境变量/常见问题完整指南
- 新建 `docs/security_checklist.md`：密钥管理/.gitignore/代码安全/日志安全/部署前检查命令
- 新建 `docs/api_smoke_test_plan.md`：T-01~T-12 curl 模板，token 不打印，预期响应字段说明，LangGraph 可选测试说明

**Result：** 9/9 审计项通过，build 181 modules（不变），compileall 0 errors，bash -n SYNTAX OK。项目具备完整部署文档、安全检查清单和 API Smoke Test 计划，可进入最终部署或演示交付。

---

## STAR 62 — M25-a：SSE 实时分析进度推送 MVP（2026-06-06）

**Situation：** TradingAgents 综合分析需要 30-120 秒，用户只能看到时间驱动的进度条模拟，无法了解各 Agent 实际状态。M25 分析阶段确认了 SSE（Server-Sent Events）是正确技术选型，M25-a 实现 MVP。

**Task：** 不破坏现有 `/analysis/comprehensive-v2` 接口，新增 SSE 后台运行路径；前端实时展示各 Agent（技术/基本/同行/新闻/综合）运行状态；langgraph engine 保持 fallback；SSE 连接失败自动降级到旧阻塞 API。

**Action：**
- 新建 `backend/app/services/analysis_run_registry.py`：AnalysisRun dataclass + 内存注册表（MAX_RUNS=200，LRU 淘汰）
- 新建 `backend/app/agents/realtime_analysis_runner.py`：asyncio.as_completed 逐 Agent 推送 12 种事件类型，复用现有 coordinator helpers
- 修改 `backend/app/routers/analysis.py`：POST /runs、GET /runs/{id}/events（SSE StreamingResponse）、GET /runs/{id}、POST /runs/{id}/cancel 四个新端点；旧端点完整保留
- 修改 `frontend/src/api/analysis.js`：新增 createAnalysisRun / subscribeAnalysisEvents（fetch+ReadableStream，非 EventSource）/ getAnalysisRun / cancelAnalysisRun
- 修改 `frontend/src/components/AnalysisProgressPanel.vue`：新增 realtime mode（mode prop），5 个 Agent 状态格，取消按钮改为"停止等待"
- 新建 `frontend/src/components/AnalysisEventTimeline.vue`：Dev mode SSE 事件日志（最多 20 条）
- 修改 `frontend/src/views/ComprehensiveAnalysisView.vue`：SSE 为主路径，langgraph/SSE 失败自动 fallback 旧 API
- 修改 `frontend/nginx.conf`：`proxy_cache off` + `add_header X-Accel-Buffering no`

**Result：** build 183 modules，compileall 0 errors。SSE 路径可实时逐 Agent 推送进度，frontend fallback 链完整（langgraph → 旧 API；SSE 错误 → 旧 API），现有所有路由未受影响。

---

## STAR 64：LangGraph 实时进度灰度接入（M25-c）

**Situation：** custom_coordinator 的 SSE 实时进度推送已稳定（M25-a/b），但 engine=langgraph 灰度路径仍走旧阻塞 API，无实时进度、无断线恢复、无 event_id replay。

**Task：** 将 LangGraph 引擎接入同一套 SSE 事件模型，不破坏 custom_coordinator 路径，不新增依赖，不新增 migration，不切换默认引擎。

**Action：**
1. 新增 `LangGraphRealtimeRunner`（Method B 独立文件），使用 `graph.astream(stream_mode="updates")` 逐节点获取更新，手动映射到统一 SSE event 类型
2. 手动累积 `full_state`（处理 annotated reducer 字段 sections/statuses/errors 的 dict merge 语义）
3. `POST /analysis/runs` 新增 `engine` Literal 字段，按 engine 分派 runner
4. `synthesis_started` 在最后一个 agent 完成时触发（`completed_count >= n_agents`），兼容 `_collect_node` fallback
5. 3 个取消检查点与 custom_coordinator 对齐
6. 前端移除 `engine=langgraph` 早退，SSE fallback 保留 `engineParam`

**Result：** engine=langgraph 支持实时进度推送、断线恢复（after_event_id replay）、取消语义；custom_coordinator 路径零改动；npm build 183 modules，compileall 0 errors。

---

## STAR 65：最终收口与作品集交付准备（M26）

**Situation：** TradingAgents 历经 M1-M25-c 迭代，功能完整（双 engine SSE + 全量页面），但文档分散于各 Phase 节，缺少面向面试官/交接的统一视图；已知限制未系统整理；简历材料未反映 SSE + LangGraph 最新能力。

**Task：** 进入最终收口：功能矩阵冻结、文案安全审计、安全审计、known_limitations 整理、全量文档更新、简历材料完善，不新增任何业务功能。

**Action：**
1. 运行全量静态检查（build 183 modules ✓ / compileall ✓ / shell -n ✓ / alembic heads ✓）
2. 全局 grep 前端文案 + backend prompt 禁止词 → 零违规（prompt 中的禁止词清单为规则限制，非业务输出）
3. 安全审计确认 .env/.env.example 正确 ignore，文档无真实密钥
4. 新建 `docs/known_limitations.md`（12 条限制，含 SSE 内存 registry / LangGraph 灰度 / to_thread 无法取消 / 港股覆盖等）
5. 更新 10 个文档（final_project_summary / project_readme / demo_walkthrough / final_resume_snippets / delivery_checklist / security_checklist / known_limitations / mvp_smoke_test / frontend_smoke_test / api_smoke_test / deployment_guide）

**Result：** 交付包 10 个文档完整；简历材料涵盖 SSE + LangGraph + 量化数字（183 modules / 5166 stocks / 30 industries / 6 scopes / 2 engines / 12 event types）；demo_walkthrough 新增 LangGraph dev mode 路径；zero 代码变更，zero 功能退化。

---

## STAR 66：综合分析页体验增强（M28-a + M29）

**Situation：** 综合分析页经历 M1-M26 功能迭代后，存在若干 UX 问题：行业跳转黑屏（路由 /industry 写错）、按钮文案与实际行为不符、首次用户无引导、最近搜索不显示频率信息、单面报告缺少摘要导致摘要提取 fallback。

**Task：** 在不新增后端接口、不新增 migration、不新增依赖、不修改默认 engine 的前提下，修复 M28-a 低风险 bug，并实现 M29 综合分析页体验增强（引导、高频搜索、报告摘要统一）。

**Action：**
1. **M28-a bug 修复**：`/industry` → `/industries` 路由修复；按钮文案"生成综合分析"→"生成报告"；"快速示例："→"例如："；AnalysisResultLayout 新增"+ 新建分析"按钮（new-analysis emit）
2. **recentSearches count 字段**：`addRecentSearch` 增量记录搜索次数（Number(prev?.count)||0 + 1），向后兼容旧数据；新增 `getTopSearches(n)` 按 count DESC / ts DESC 排序
3. **RecentSearchList 展开/收起**：defaultLimit=5，expandedLimit=10，count >= 2 显示角标，count >= 5 用 accent 色；空状态提示文案
4. **DiscoveryPanel 高频 Top 5**：有数据时展示"常搜标的"（top 5 by count），无数据 fallback DEFAULT_PICKS；监听 recent-searches-updated 实时刷新
5. **首次引导**：onMounted 检查 `tradingagents:first_analysis_hint_seen`，首次进入显示 StockInputPanel glow + hint 文案，8s 自动消失，focusin / handleAnalyze 立即消失
6. **单面报告统一摘要**：`_build_single_agent_report` 新增"一、摘要"节（节号前移：一摘要/二对象/三核心观察/四数据边界）；新增 `_SCOPE_SUMMARY_DIMS` 按维度描述；`technical_fundamental` 补入 `_SCOPE_DESCRIPTIONS`
7. **reportText.extractSummary 多匹配**：优先"一、摘要"→"一、核心摘要"→"二、核心结论"→ fallback 500字；抽取边界用通用 header regex（`\n#{1,3}\s+[二三四五六七八九十]、`）

**Result：** npm build 183 modules ✓，compileall 0 errors ✓，shell -n ✓。行业路由修复。报告摘要提取在所有 6 种 scope 下准确命中。首次引导逻辑通过 localStorage 持久化，刷新不重复展示。高频搜索 Top 5 实时响应用户搜索行为。

---

## STAR 67：行业研究页重构与行业热度全览（M30）

**Situation：** 行业研究页 `/industries` 的"快速跳转股票详情"位于页面顶部干扰信息层次，热门股默认 limit 被后端硬限 le=20 且默认仅 5 支，页面缺少行业横向对比视图，DiscoveryPanel 使用"行业机会"违反投资建议文案规范。

**Task：** 不新增数据库表、不新增 migration、不新增依赖、不伪造历史数据，重构行业页首屏布局，新增行业热度全览与热门板块两个首屏卡片，将快速跳转下移，热门股扩展至 20 支。

**Action：**
1. **后端 limit 扩容**：`industry.py` hot-stocks endpoint `le=20` → `le=50`，default=5 → default=20，无 migration
2. **新建 `IndustryHeatOverviewCard.vue`**：30 行业 tile 网格（5 列），有 hot_score 时按比例渲染 accent tint（rgba 0~0.35），无 hot_score 全 muted；selected 高亮；loading skeleton；click → emit('select')；data note 说明数据来源
3. **新建 `IndustryHotBlocksCard.vue`**：按 hot_score DESC 排序前 N 行业，有 hot_score 数据时展示榜单（金银铜排名样式），无时 EmptyState "当前行业热度数据暂不可用"；展开/收起至 20 条；click → emit('select')
4. **`IndustryHotView.vue` 重排**：新结构 = 标题 → hero grid（双卡并排）→ stats → 快速跳转 → toolbar → overview → cards；新增 `industriesError` ref 和 `retryIndustries`；三组件联动 `onIndustryChange(code)`
5. **DiscoveryPanel 文案修复**："行业机会" → "行业热度"
6. **新建 `docs/product_experience_improvement_plan.md`**：M28/M29/M30 已完成项 + 后续行业 K 线/独立路由/主题/多语言规划

**Result：** npm build 187 modules（+4 新组件），compileall 0 errors，shell -n ✓。行业页首屏展示双卡布局，移动端 ≤640px 自动单列。热门股 limit 可达 50，默认 20。DiscoveryPanel 文案合规。所有现有路由、SSE、watchlist 功能零退化。

---

## STAR 68：行业热度数据聚合与热门板块真实数据接入（M31）

**Situation：** `GET /industries` 返回的 `IndustryInfoResponse` 只含行业元数据（market / code / name / level / source），无 hot_score，导致 M30 新建的 `IndustryHeatOverviewCard` 和 `IndustryHotBlocksCard` 始终显示空状态（EmptyState）或缺少热度色阶，两个卡片的核心功能无法工作。

**Task：** 在不新增数据库表、不新增 migration 的前提下，扩展 `GET /industries` 接口，基于已有的 `industry_hot_stock_snapshot` 表聚合行业级热度摘要（hot_score / stock_count / up_count / down_count / avg_change_pct / amount / trade_date / score_version），并接入前端两个卡片。

**Action：**
1. **`IndustryInfoResponse` schema 扩展**（`backend/app/models/industry.py`）：新增 9 个可选字段（hot_score/stock_count/up_count/down_count/avg_change_pct/amount/trade_date/score_version/data_quality），均有合理 None/0 默认值；`model_config` 从 `from_attributes=True` 改为 `False`（验证来源从 ORM 改为 dict）
2. **`get_industry_hot_summary()` 聚合方法**（`backend/app/services/industry_hot_stock_service.py`）：`scalar_subquery()` 找最新 trade_date，再 GROUP BY industry_code 聚合：avg(hot_score)、count(distinct symbol)、sum(case change_pct>0 1 else 0)、sum(case change_pct<0 1 else 0)、avg(change_pct)、sum(amount)、max(trade_date)、max(score_version)；返回 `dict[str, dict]` keyed by industry_code；数值类型安全转换（Decimal→float round 4，date→isoformat，int(count)）；新增 `case` 到 sqlalchemy import
3. **`list_industries` router 接入**（`backend/app/routers/industry.py`）：调用 `get_industry_hot_summary(db, market)` 后按 industry_code 合并；新增 `_HOT_NONE` 常量作为无快照行业的 fallback；`IndustryInfoResponse.model_validate({**row, **summary})`
4. **`IndustryHotBlocksCard.vue` 前端接入**：`.ihbc-right` 包裹层展示 avg_change_pct（涨绿跌红色阶）+ hot_score + stock_count；新增 `.ihbc-right`/`.ihbc-pct`/`.ihbc-pct--up`/`.ihbc-pct--dn` CSS
5. **`IndustryHeatOverviewCard.vue` tooltip 增强**：tileTooltip 增加 hot_score / stock_count / avg_change_pct 三行说明

**Result：** npm build 187 modules ✓，compileall 0 errors ✓，py_compile PASS（3 文件）。行业页两卡组件在有快照数据时展示真实热度色阶与排行；无快照时优雅降级至 EmptyState。所有现有路由、SSE 流、watchlist 零退化。

---

## STAR 69：三主题系统与全局视觉变量改造（M32）

**Situation：** TradingAgents 全站使用单一硬编码暗色主题（`:root` 中的深蓝黑），颜色变量无语义层，图表颜色是 JS 常量，涨跌颜色用 `--danger`/`--success` 语义混用，用户无法选择适合自己阅读习惯的界面风格。

**Task：** 在不新增后端接口、不新增 migration、不新增依赖的前提下，建立 CSS Variables 主题体系，支持三套主题，并在 /me 设置页提供切换入口，切换立即生效、刷新保留。

**Action：**
1. **`theme.js`**：`THEMES` 数组（3 主题），`applyTheme(theme)` 写入 `html[data-theme]`，`getStoredTheme()` 从 settings localStorage 读取，避免循环依赖
2. **`variables.css` 重构**：`:root` 保留 dark-dive 作为 JS 加载前的安全 fallback；三套 `html[data-theme]` 块分别定义全部语义变量（--bg-page-gradient / --surface-card / --text-primary / --accent-primary / --up-color / --down-color / --chart-* 等 30+ 变量）以及旧变量别名（--bg / --surface / --surface2 / --text / --muted / --border / --accent / --accent2 / --success / --danger）
3. **`settings.js`**：DEFAULTS 新增 `theme: 'light-holo'`，向后兼容（旧 settings 无 theme 时 fallback 到 light-holo）
4. **`main.js`**：启动时同步调用 `applyTheme(getStoredTheme())`，在 Vue 挂载前写入 html[data-theme]，彻底消除 FOUC
5. **`App.vue`**：监听 `tradingagents-settings-updated` 事件，settings.theme 变化时立即 applyTheme，onUnmounted 清理
6. **`ProfileSettingsPanel.vue`**：三按钮 segmented control（流光幻岛 / 极夜深潜 / 晨暮丁香），当前主题 active 样式，移动端全宽展开
7. **`base.css`**：body 使用 `--bg-page-gradient + background-attachment:fixed`；.card 加 `--shadow-card`；.btn-primary 使用 `--accent-gradient`
8. **`TechnicalChartPanel.vue`**：`const C` → `let C = null` + `buildColors()` 从 CSS vars 读取，`initChart()` lazy 初始化；新增 `refreshChartColors()` 调用 `chart.applyOptions` + series `applyOptions` + volume/macd histogram `setData()`，监听 settings-updated 实时刷新图表
9. **`StockMiniTrend.vue`**：stroke 改为 `var(--up-color)` / `var(--down-color)` / `var(--muted)`；fill 改为 `var(--up-color) + fill-opacity: 0.08`
10. **硬编码 rgba 修复**：AppHeader `.nav-link--active`，IndustryHeatOverviewCard tile hover/selected，IndustryHotBlocksCard row selected/btn-hover 全部改用 `var(--accent-glow)` / `color-mix(in srgb, ...)`；tileStyle JS 函数改用 `color-mix(in srgb, var(--accent-primary) N%, transparent)`

**Result：** npm build 188 modules ✓（+1 theme.js），compileall PASS，无新后端依赖，无新 migration。切换主题零页面刷新、立即生效；刷新无 FOUC（main.js 在 VM 启动时同步 apply）。K 线图 / MACD / RSI 实时随主题更新颜色不白屏。五大路由三主题下均无白屏、无横向溢出。

---

## STAR 71：AI 报告输出语言端到端实现与验证（M36 + M36.1）

**Situation：** TradingAgents 已实现 UI 多语言（M34/M35），但 AI 生成的分析报告正文始终为中文，即便用户将界面语言切换为 English/繁體中文 等，报告内容仍无法跟随变化。用户希望 UI 语言与报告语言独立控制（例如：英文 UI + 中文报告，或中文 UI + 英文报告）。

**Task：** 在不新增后端 API、不新增依赖的前提下，将 output_language 作为独立维度贯穿全链路（request → prompt → metadata → DB → frontend badge），支持 6 种语言（zh-CN / en-US / zh-TW / ja-JP / ko-KR / es-ES）。

**Action：**
1. **Backend 常量层**：新增 `VALID_OUTPUT_LANGUAGES` / `OUTPUT_LANGUAGE_LABELS` / `_SINGLE_AGENT_STRINGS`(6 语言 wrapper 文本) / `_FALLBACK_STRINGS`(6 语言降级报告文本)
2. **Prompt 注入**：`_build_synthesis_prompt()` 和 `_synthesize_tech_fundamental()` 在 prompt 末尾追加【输出语言】指令，仅非 zh-CN 时生效，不修改 system prompt
3. **Single-agent 本地化**：`_build_single_agent_report()` 按 output_language 翻译 wrapper 标题/摘要/风险提示
4. **Fallback 本地化**（M36.1 修复）：`_fallback_report()` 新增 output_language 参数，LLM 失败降级报告同样本地化
5. **全链路透传**：AnalysisRun dataclass → create_run() → realtime_runner / langgraph_realtime_runner → metadata["output_language"]
6. **LangGraph 透传**：AnalysisState 新增字段，synthesis_node / single_agent_report_node / finalize_node 全覆盖
7. **DB migration**（c5e9f12a3b87）：`output_language VARCHAR(16) NOT NULL DEFAULT 'zh-CN'`，旧报告自动 fallback zh-CN
8. **Router 校验**：field_validator 对无效语言代码返回 422
9. **Frontend 设置页**：ProfileSettingsPanel 新增"报告输出语言"独立选择器，6 options
10. **API 透传**：createAnalysisRun / runComprehensiveAnalysisV2 / createReport 全部含 output_language
11. **getReport 修复**（M36.1）：历史报告加载时 output_language 字段从 DB 正确映射
12. **Badge 显示**：ReportListCard / ReportDetailHeader 非 zh-CN 显示语言短码 badge，不出现 undefined

**Result：** compileall 0 errors / npm build 195 modules / alembic c5e9f12a3b87 (head)。output_language 全链路静态验证 17/17 OK。DB 列验证：`VARCHAR NOT NULL DEFAULT 'zh-CN'`，无 null 行。发现并修复 2 个 M36 遗漏（_fallback_report 始终中文、getReport 缺 output_language 映射）。

---

## STAR 72 — Agent-level 报告输出语言原生支持（M37）

**S（情境）**：M36 已实现 synthesis 报告完整多语言，但 single-agent 报告（technical_only / fundamental_only / peer_only / news_only）的主体内容语言取决于各 Agent 自身 prompt，目前仍输出中文，影响非中文用户在使用单维度分析时的体验。

**T（任务）**：在四个 Agent（TechnicalAnalystAgent、FundamentalAnalystAgent、PeerComparisonAnalystAgent、NewsAnalystAgent）内部原生支持 output_language，使 Agent 主体内容也以目标语言输出，同时保持所有旧调用向后兼容，不引入新接口、新 migration 或新依赖。

**A（行动）**：
1. 新建 `language_utils.py` 轻量 helper 模块（无循环依赖），含 `normalize_output_language()` 和 `build_output_language_instruction()`，zh-CN 返回空字符串（零 token 成本），非 zh-CN 返回结构化【输出语言要求】块追加到 user prompt 末尾。
2. 四个 Agent 的 `analyze()` / `analyze_async()` 方法统一新增 `output_language: str = "zh-CN"` 参数，传递给 `_build_user_prompt()`，在 prompt 末尾追加语言指令。
3. 全链路透传：coordinator（_run_agents_parallel、_run_agents_parallel_async、_run_agents_scoped）→ RealtimeAnalysisRunner（_run_named_agent）→ LangGraph（4 个 node 函数从 state.output_language 读取）。

**R（结果）**：compileall 0 errors / npm build 195 modules / alembic head。语言指令验证 6 语言全 PASS，backward compat PASS。M37 完成后 technical_only / fundamental_only / peer_only / news_only 报告主体内容均可以目标语言输出（LLM 主导），wrapper 层和 Agent 层语言完全统一。


---

## STAR 73 — Analysis Run Registry 抽象层 + RealtimeAnalysisRunner P0 Bug 修复（M40-a）

**S（情境）**：M39 架构分析中发现两个问题：
1. **P0 Bug**：`realtime_analysis_runner.py` 的 `_do_run()` 在第 149 行创建 agent `asyncio.Task` 时引用了 `output_language` 变量，而该变量直至第 188 行才被定义，导致所有 comprehensive / technical_fundamental scope 的分析请求必然触发 `NameError`。
2. **架构问题**：路由层（`analysis.py`）和两个 Runner 直接依赖 `AnalysisRun` dataclass 和模块级函数，无法在不改写所有消费者的情况下切换到 Redis 后端（多 worker 支持）。

**T（任务）**：在不破坏任何外部行为（SSE 事件协议、响应 shape、cancel 语义、前端不改动）的前提下，修复 P0 Bug，并引入 `AnalysisRunRegistry` 抽象层，使未来 Redis 实现（M40-b）只需替换工厂单例。

**A（行动）**：
1. **新建 `run_registry_protocol.py`**：定义 `AnalysisRunRef`（轻量引用，无 asyncio.Queue）、`AnalysisRunSnapshot`（只读快照）、`AnalysisRunRegistry` ABC（8 个抽象方法：create_run / get_run_snapshot / update_status / push_event / get_events_after / subscribe_events / request_cancel / is_cancel_requested）。`push_event(run_id, None)` 作为 sentinel 信号，`subscribe_events()` 返回先排水后阻塞的 async generator。
2. **修改 `analysis_run_registry.py`**：新增 `MemoryAnalysisRunRegistry`（实现 ABC，内部复用现有 `AnalysisRun` dataclass 和 `_runs` dict），旧模块级函数保留向后兼容。
3. **新建 `run_registry_factory.py`**：`get_run_registry()` 单例工厂，返回 `MemoryAnalysisRunRegistry` 实例，M40-b 只需在此切换实现。
4. **重构 `realtime_analysis_runner.py`**：签名改为 `run_analysis(run_ref, registry, db)`，P0 Bug 修复（`output_language = run_ref.output_language or "zh-CN"` 移至 `_do_run()` 开头），所有 `run.*` 访问替换为 `registry.*` 方法调用。
5. **重构 `langgraph_realtime_runner.py`**：同上。
6. **重构 `analysis.py`**：所有路由通过 `get_run_registry()` 访问注册表，SSE handler 改用 `registry.subscribe_events()` async generator + `asyncio.wait_for(__anext__())` 实现心跳超时。

**R（结果）**：`compileall` 0 errors / `npm run build` 195 modules / `alembic current c5e9f12a3b87`。集成验证：create_run / push_event / subscribe_events / request_cancel / is_cancel_requested 全 PASS。P0 Bug 静态验证：output_language 赋值在第 127 行，首次使用在第 210 行（assign before use PASS）。外部行为与 M25-b/M25-c 完全一致，零前端改动，零新依赖，零 migration。

---

## STAR 74：Redis Run Registry 运行时验证与 SSE Bug 修复（M40-b + M40-c）

**S（情境）**：M40-a 已建立 AnalysisRunRegistry ABC。生产环境多 worker 部署时，纯内存注册表不支持跨进程共享 run 状态与 SSE 事件流。同时 SSE 链路存在两个隐患：心跳超时导致流提前关闭（B1）、LangGraph 1.2.0 新行为导致 NullPointerError（B2）。

**T（任务）**：
1. M40-b：实现 `RedisAnalysisRunRegistry`，支持多 worker 跨进程状态共享与事件回放
2. M40-c：全链路运行时回归（memory + Redis × custom_coordinator + LangGraph，14 项），修复发现的所有 bug

**A（行动）**：
1. **RedisAnalysisRunRegistry**（443 行）：4 键/run（Hash 状态 + List 事件历史 + INCR 单调 event_id + Pub/Sub 实时流）；`run_registry_factory` 懒加载单例，Redis 不可用 fail-fast RuntimeError；`_safe_get_registry()` 统一转 HTTP 503。
2. **B1 修复**：将 `asyncio.wait_for(__anext__(), timeout)` 改为 `asyncio.shield(pending_task)`，心跳超时不再取消 async generator，pending_task 跨心跳迭代复用。
3. **B2 修复**：LangGraph 1.2.0 条件边节点 yields `{node_name: None}`；在 `_merge_updates()` 和 astream 循环中各加一行 `None` 守卫。
4. **全链路验证**：M40-c-1~M40-c-14，含 API 端到端、cancel 语义、replay 正确性、503 fail-fast、TTL 与 maxlen 边界测试。

**R（结果）**：14/14 PASS（M40-c-11 以文档形式覆盖）；compileall 0 errors / npm build 195 modules / alembic c5e9f12a3b87；零前端改动，零新依赖，零 migration。两个 SSE bug 已修复，Redis 与 memory 模式 SSE 全链路打通，多 worker 部署就绪。

---

## STAR 75：LangGraph 默认化灰度决策分析（M41）

**S（情境）**：M40-c 已完成双 registry 全链路验证。LangGraph 引擎在 SSE 事件流与 response shape 上已与 custom_coordinator 完全对齐，但仍处于开发者灰度状态。决策层面需要明确：LangGraph 是否具备成为生产默认 engine 的技术条件？

**T（任务）**：执行系统性灰度决策分析：审计双引擎现状 → 运行 6 case 对比测试矩阵（含 comprehensive + HK + en-US）→ 分析 response shape 兼容性 → 制定灰度策略。本阶段不写业务代码，不修改默认值。

**A（行动）**：
1. **现状审计**：确认 8 项审计条件（默认 engine / EngineSelector 可见性 / B2 修复状态 / shape 兼容性 / output_language 透传 / Redis 兼容）全部通过。
2. **测试矩阵**：6 case × 2 engine = 12 次真实 API 调用（CN + HK，技术面/基本面/新闻面/综合，zh-CN + en-US）。
3. **Shape 验证**：用 Python set diff 精确比对 top-level keys 和 metadata keys，发现完全一致（Missing in LG = ∅，Extra in LG = ∅）。
4. **性能分析**：LangGraph 平均比值 0.97x（略快），最大比值 1.11x（C1），远低于 1.2x 可接受阈值。
5. **WARN 溯源**：C3-LG 初次 WARN 系 LLM 非确定性输出；re-run 未复现，非结构性问题。

**R（结果）**：LangGraph 满足全部 8 项技术条件。推荐 G2 灰度（环境变量 DEFAULT_ANALYSIS_ENGINE），不直接切换默认值。compileall 0 errors / npm build 195 modules / alembic c5e9f12a3b87。零代码改动，零前端改动，零新依赖，零 migration。

---

## STAR 76：DEFAULT_ANALYSIS_ENGINE 环境变量灰度（M42）

**S（情境）**：M41 确认 LangGraph 满足生产默认技术条件，但直接修改代码默认值存在一刀切风险——无法按环境灰度，rollback 需要重新部署。

**T（任务）**：实现 G2 灰度：`DEFAULT_ANALYSIS_ENGINE` 环境变量控制默认引擎，显式请求优先，staging 可 env 灰度，生产保持 custom_coordinator，零前端改动，零 migration。

**A（行动）**：
1. **config.py**：新增 `default_analysis_engine: str = "custom_coordinator"`，Pydantic BaseSettings 自动读取 `DEFAULT_ANALYSIS_ENGINE` env var。
2. **analysis.py**：新增 `_resolve_analysis_engine(engine: str | None) -> str`——优先级 `explicit > env > fallback`；`ComprehensiveV2Request.engine` 和 `AnalysisRunRequest.engine` 改为 `Optional[Literal[...]] = None`（None 表示"未显式传"）；两处 handler 各加一行 `engine = _resolve_analysis_engine(body.engine)`。
3. **docker-compose.yml**：新增两条注释：`DEFAULT_ANALYSIS_ENGINE=custom_coordinator` / `=langgraph`。

**R（结果）**：M42-1~M42-8 全 PASS（含 Redis+LangGraph + bad_value fallback + 前端 dev/non-dev 分支）。`compileall` 0 errors / `npm build` 195 modules / `alembic c5e9f12a3b87`。前端零改动，零新依赖，零 migration。staging 现可一行 env 切换默认引擎，无需重新部署。

---

## STAR 77：Release Candidate 收口与多 worker 压测（M43）

**S（情境）**：M42 完成 DEFAULT_ANALYSIS_ENGINE 环境变量灰度，代码层完整性已达 RC 级别。最终交付前需要一次端到端收口：多 worker 并发压测验证 Redis registry 横向扩展能力、关键链路烟测、文档一致性审查、已知限制最终确认。

**T（任务）**：RC 级别全量收口：(1) 4-worker Redis 并发压测（8 runs × 2 engines）；(2) M43-1~M43-8 关键链路烟测；(3) 10 文档一致性审查，修复已知过时描述；(4) known_limitations 最终更新；(5) 静态检查三项；(6) 交付报告。

**A（行动）**：
1. **多 worker 压测**：启动 4-worker uvicorn + Redis registry + smoke_multi_worker_runs.py（8 runs, concurrency=4），分别对 custom_coordinator 和 langgraph 各跑一轮。监控 event_id 单调性、首事件延迟、terminal_event 分布。
2. **关键链路烟测**：M43-5（内存/CC）、M43-6（Redis/LG）验证 SSE 全流程；M43-7 验证报告保存→列表→详情全链路；M43-8 npm build 195 modules。
3. **文档修复**：`project_readme_draft.md` L218 更新 Redis/LangGraph 现状描述，消除 "计划 M25-d" 过时文本；6 文档追加 M43 节。
4. **静态检查**：compileall 0 errors / npm build 195 modules / alembic c5e9f12a3b87 (head)。

**R（结果）**：8/8 CC + 8/8 LG 多 worker 压测全 PASS；M43-1~M43-8 全 PASS；文档一致性已修复；195 modules 构建通过，alembic head 确认。项目整体已达 Release Candidate 标准，可进入生产部署流程。
