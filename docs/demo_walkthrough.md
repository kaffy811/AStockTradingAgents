# TradingAgents Demo 演示指南

> 状态：M22 完成版（2026-06-06）  
> 定位：研究辅助工具，不提供投资建议。

---

## 一、Demo 准备

### 1.1 启动服务

```bash
# 后端（从项目根目录）
cd backend
uv run uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend
npm run dev
# 默认运行在 http://localhost:3001
```

### 1.2 登录测试账号

打开浏览器访问 `http://localhost:3001`，注册或使用测试账号登录。

### 1.3 推荐测试股票

| 股票 | 说明 | 特点 |
|------|------|------|
| CN/000001 | 平安银行（A股） | 基本面、同行数据完整，适合完整演示 |
| CN/600519 | 贵州茅台（A股） | 知名标的，数据覆盖好 |
| CN/000858 | 五粮液（A股） | 同行业对比演示（食品饮料） |
| HK/00700 | 腾讯控股（港股） | 演示 HK 市场特殊处理（行业不支持提示） |

---

## 二、3 分钟 Demo 路径

### Step 1：首页研究仪表盘（30s）

- 打开 `/`（首页），展示 **HomeHeroPanel**：
  - 标题"AI 多 Agent 股票研究助手"
  - chips：多 Agent 分析 / A 股 / 港股 / 技术图表 / 报告中心 / 自选研究
  - 底部风险提示："仅供研究参考，不构成投资建议。"
- 展示 **HomeDashboardPanel** 仪表盘（首屏无需分析即可看到）：
  - Stats bar：最近报告数 / 自选股数 / 最近搜索数 / 行业热门数
  - 最近报告、自选快跳、最近搜索 chips、行业热门 5 条
  - 底部 compare bar（有对比列表时显示）
- 点击自选快跳"填入"或行业热门股 → 填入 StockInputPanel（不自动分析）

### Step 2：搜索 CN/000001 并确认身份（20s）

- 在 StockInputPanel 输入 `000001`，市场选 `CN`
- 展示 **StockIdentityCard**：实时解析"平安银行"
- 说明：stock_master 主数据表搜索，防止用户输错代码

### Step 3：选择分析维度并开始分析（20s）

- 展示 **AnalysisModeSelector**：选择"仅技术面"快速演示，或"综合"完整演示
- 点击"开始分析"
- 展示 **AnalysisProgressPanel**：6 步进度模拟（确认分析对象 → 技术面 → 基本面 → 同行 → 新闻 → 生成报告）
- 说明：后端多 Agent 并行，进度面板是时间驱动模拟

### Step 4：展示分析报告（30s）

- 分析完成，展示 **AnalysisResultLayout**
- 指出 report identity bar：股票名称 + 分析维度 badge
- 指出 **DataQualitySummary**：综合评分 + 四维 chip（技术/基本面/同行/新闻）
- 指出 **AgentStatusBar** 和 **WarningPanel**（数据质量提示）
- 展示操作面板：加入自选 / 复制摘要 / 保存报告 / 打印

### Step 5：跳转股票详情页（20s）

- 点击报告 identity bar 或导航至 `/stocks/CN/000001`
- 展示 **StockDashboardPanel**：基本信息 + 行情 + 行业 + 数据质量三灯
- 展示 **TechnicalChartPanel**：K 线 + MA 均线，tab 切换 1月/3月/6月/1年
- 展示 **NewsTimelinePanel**：新闻时间线 + 影响摘要

---

## 三、5 分钟 Demo 路径（在 3 分钟基础上扩展）

### Step 6：股票详情页深度（30s）

- 在 `/stocks/CN/000001` 展示：
  - **TechnicalInsightCard**：MACD / RSI / 均线结构规则解读（无投资判断）
  - "加入对比"按钮 → 状态变为"已在对比"
  - "去对比页"按钮 → 跳转 /compare

### Step 7：股票对比页（45s）

- 进入 `/compare`，展示 **StockCompareView**
- **StockCompareSelector**：搜索添加 CN/600519 贵州茅台（现已有2只）
- 展示 **StockCompareSummary**：4 统计卡（已选数/行情可用/有报告/涉及行业）
- 展示 **StockCompareTable**：
  - 桌面表格：行情 / 行业 / 最近报告 / 数据质量三色点 / 近 30 日趋势迷你图
  - 说明 **StockMiniTrend**：纯 SVG 实现，trend-up/down/neutral 颜色
- 点击某只股票"分析" → 跳转首页填入

### Step 8：自选股研究工作台（45s）

- 进入 `/watchlist`，展示 **WatchlistView**
- 展示 **WatchlistStats**：4 统计卡（总数/多少有近期报告等）
- 展示 **WatchlistToolbar**：市场/行业/name 筛选 + 排序
- 进入批量模式：选 2 只以上 → "对比"按钮激活 → 跳转 /compare?stocks=
- 展示单卡 **WatchlistStockCard**：note 编辑 / 详情 / 分析 / 历史

### Step 9：行业研究页（45s）

- 进入 `/industry`，展示 **IndustryHotView**
- 展示 **IndustryToolbar**：行业下拉切换
- 展示 **IndustryOverviewPanel**：行业信息 + Hot Score 说明
- 展示 **IndustryHotStats**：4 统计卡（总数/上涨/下跌/平均分）
- 展示 **IndustryStockCard** 列表：rank badge 金银铜 / hot score / 涨跌幅
- 点击"分析" → 跳转首页

### Step 10：报告中心（30s）

- 进入 `/history`，展示 **HistoryView**
- 展示 **ReportCenterStats**：4 统计卡（总数/本周/综合/港股）
- 展示 **ReportFilterPanel**：5 维筛选（市场/scope/自动保存/时间范围/关键词）
- 展示 **ReportListCard**：卡片化报告列表，含操作（查看/详情/重新分析/删除）
- 进入某报告 → **HistoryDetailView**：ReportDetailHeader + ReportMetaSummary + 完整报告

### Step 11：我的研究中心（30s）

- 进入 `/me`，展示 **ProfileView**
- 展示 **ProfileResearchStats**：报告数/自选股数/分析次数等
- 展示 **ProfileActivityPanel**：最近报告列表 → 可跳 /history/:id；最近搜索 → 可跳详情
- 展示 **ProfileSettingsPanel**：默认市场/分析维度偏好/自动保存开关
- 展示 **DataSourceNoticePanel**：数据源说明与已知限制
- 展示开发者模式入口（localStorage tradingagents:dev_mode=true）→ EngineSelector 出现

### Step 12：LangGraph 灰度说明（30s，可选）

- 开发者模式下，首页出现 **EngineSelector**
- 可切换 `custom_coordinator`（默认）/ `langgraph`
- 说明：生产环境用户无此选项，默认始终为 custom_coordinator
- 说明 LangGraph 架构：Send API fan-out → collect_node fan-in，已通过 A/B 对比验证

---

## 四、面试讲解重点

### 技术架构

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 Composition API + Vite + Vue Router + Pinia |
| 后端 | FastAPI + SQLAlchemy + Pydantic |
| 数据库 | Supabase PostgreSQL + Alembic 迁移 |
| 缓存 | Redis（行情/分析结果 TTL） |
| LLM 编排 | custom_coordinator（默认）/ LangGraph（灰度） |
| 图表 | lightweight-charts（K线+MA）+ 纯 SVG MiniTrend |
| 部署 | Docker Compose（三容器：backend/frontend-nginx/redis） |

### 核心亮点

1. **多 Agent 并行分析**：Technical / Fundamental / Peer / News 四路 Agent，coordinator 汇总
2. **LangGraph 灰度**：Send API fan-out + collect_node fan-in，开发者可对比两引擎结果
3. **stock_master 主数据表**：5,166 只 A 股 + 申万行业 CSV 映射，港股手工维护
4. **Hot Score 行业体系**：`log(成交额)×0.4 + |涨跌幅|×0.6` 动态计算
5. **数据质量评分**：纯前端四维度，帮助用户理解报告边界，不依赖新 API
6. **compareStorage 对比链路**：localStorage + CustomEvent 跨页面同步，URL query 为 source of truth
7. **移动端 PWA 风格**：BottomTabBar + safe-area 自适应，≤640px 单列布局

### 数据源体系

- 行情 K 线：AkShare（A股）/ yfinance（港股备用）
- 基本面：AkShare / Sina 财务接口 / yfinance
- 新闻：AkShare 新闻接口（72 小时窗口）
- 行业分类：申万行业 CSV 映射（30 个一级行业）

---

## 五、常见问题回答

**Q：这是投资建议吗？**  
A：不是。系统仅供研究参考，不构成任何投资建议。所有报告均有风险提示，界面文案严格避免买卖建议类表达。

**Q：数据是实时的吗？**  
A：行情数据有 Redis TTL 缓存；新闻数据有 72 小时时间窗口；非 WebSocket 实时推送。

**Q：为什么有些字段缺失？**  
A：上游数据源字段覆盖有限，港股基本面字段尤其受限。DataQualitySummary 会明确说明当前报告的具体覆盖局限。

**Q：为什么港股行业分析较少？**  
A：港股不适用申万体系，行业映射仍在建设中。系统会主动提示"当前市场暂不支持行业热门股"。

**Q：LangGraph 和 custom_coordinator 有什么区别？**  
A：两者输出结构完全兼容，LangGraph 通过 Send API 实现节点级 fan-out，调试可观测性更好；custom_coordinator 是直接 Python 调用，延迟略低。默认使用 custom_coordinator，LangGraph 仍在灰度验证中。

**Q：分析一次要多久？**  
A：通常 30-90 秒，取决于数据源响应速度和 LLM API 延迟。进度面板会显示当前阶段和已用时长。

**Q：如何扩展到更多市场？**  
A：数据层新增 market adapter，stock_master 补充对应市场数据，PEER_MAP 扩展，LLM prompt 适配即可。

---

## 三、开发者模式 Demo（LangGraph + SSE）

> 前提：`localStorage.setItem('tradingagents:dev_mode','true')` 已设置，或本地 dev build

### 步骤

1. **开启 dev mode**  
   浏览器 Console：`localStorage.setItem('tradingagents:dev_mode','true')` → 刷新页面

2. **确认 EngineSelector 可见**  
   页面输入框下方出现"分析引擎"选择器，当前为 `custom_coordinator`

3. **切换至 LangGraph**  
   EngineSelector 选择 `langgraph`

4. **输入 CN/000001，选择 technical_only**  
   点击"开始分析"

5. **观察 ProgressPanel realtime 模式**  
   - 5 个 Agent 状态格：technical = running；fundamental/peer/news = skipped（`—`）；synthesis pending
   - 进度条从 5% → 18% → 80% → 95% → 100%

6. **观察 AnalysisEventTimeline**  
   展开"SSE 事件日志"，确认：
   - `analysis_started` message 含 `[LangGraph]`
   - `agent_started` / `agent_completed` (technical)
   - `synthesis_started` / `synthesis_completed`
   - `report_ready`
   - 每条事件有 `#N` event_id 和 `+Nms` elapsed

7. **报告渲染**  
   结果与 custom_coordinator 格式一致；`metadata.workflow_engine = langgraph` 可在 DevTools > Network 验证

8. **切回 custom_coordinator**  
   EngineSelector 切回 → 分析 → 确认 ProgressPanel 和 EventTimeline 正常

9. **取消测试**  
   分析进行中点击"停止等待"→ 确认显示"已停止等待"消息，不触发 fallback，ProgressPanel 消失

---

## 四、面试常见追问 Demo 重点

| 问题 | Demo 指向 |
|------|------|
| SSE 是怎么实现的？ | EventTimeline 展示 event_id / elapsed_ms，说明 fetch+ReadableStream |
| LangGraph 是什么？ | 切换 engine=langgraph，同样出 SSE 事件流，说明 graph.astream mapping |
| 取消是怎么工作的？ | 点击"停止等待"，说明 abort-first 不触发 fallback |
| 断线重连怎么测？ | 分析过程中断网 → 恢复 → 报告仍然完成（after_event_id replay） |
| 多 Agent 怎么并行？ | comprehensive 模式下 EventTimeline 可见 4 个 agent 几乎同时 started |

---

## 五、双 Engine 对比 Demo（M41 灰度决策场景）

演示 custom_coordinator 与 langgraph 引擎在同一场景下的可对比性，适用于面试或技术评审。

### 操作步骤

1. **启用开发者模式**  
   打开 localStorage：`tradingagents:dev_mode=true`（或在本地 DEV 环境直接可见 EngineSelector）

2. **选择 custom_coordinator**  
   搜索 CN/000001，scope=technical_fundamental，点击分析  
   记录：耗时 / SSE 事件数 / report 字数 / sections keys

3. **切换 langgraph**  
   相同标的、相同 scope，再次分析  
   记录同样指标

4. **对比要点**
   - SSE 事件序列：完全一致（`analysis_started → identity_resolved → agent_started ×2 → agent_completed ×2 → synthesis_started → synthesis_completed → report_ready`）
   - 耗时：LangGraph 约 0.9-1.1x（测试结果平均 0.97x）
   - Response shape：metadata / sections / report / output_language 字段完全一致
   - 唯一区分：`metadata.workflow_engine` 字段值不同

5. **面试说明要点**
   - custom_coordinator：手写并发（asyncio.gather），状态机简单可 debug
   - LangGraph：StateGraph + Send API fan-out / collect fan-in，可视化工作流，适合复杂 DAG
   - 两条路径共享同一 AnalysisRunRegistry ABC，SSE 协议透明
   - M40-c 验证：memory + Redis × custom + LangGraph 全部通过
   - M41 决策：LangGraph 满足 G2 灰度条件，已具备生产默认潜力

---

## 六、DEFAULT_ANALYSIS_ENGINE 环境变量灰度 Demo（M42 G2）

演示通过单一 env 变量在不重新部署代码的情况下灰度切换默认 engine，适用于 staging 验证场景。

### 场景 A：staging=langgraph，普通用户不感知

```bash
# 启动 staging 服务（一行 env 差异）
DEFAULT_ANALYSIS_ENGINE=langgraph uvicorn app.main:app --port 8000

# 普通用户请求（不含 engine 字段）
curl -X POST .../analysis/runs \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"symbol":"000001","market":"CN","analysis_scope":"technical_only"}'
# → metadata.workflow_engine = "langgraph"（staging 走新路径）
```

生产用户请求结构完全一致（普通用户请求体不含 engine）。

### 场景 B：开发者模式显式覆盖（优先于 env）

```bash
# env=langgraph，但开发者手动选 custom_coordinator
curl -X POST .../analysis/runs \
  -d '{"symbol":"000001","market":"CN","analysis_scope":"technical_only","engine":"custom_coordinator"}'
# → metadata.workflow_engine = "custom_coordinator"（显式覆盖 env）
```

### 面试说明要点

- 零代码改动，一行 env 实现灰度，rollback = 改 env，比改代码 + 部署快得多
- `_resolve_analysis_engine()` helper 体现防御性编程（invalid env → fallback，不崩服务）
- G2 灰度 + Docker Compose 注释配置：DevOps 友好，文档驱动
- 优先级链：`explicit body.engine > DEFAULT_ANALYSIS_ENGINE > "custom_coordinator"`

---

## M43 RC：5 分钟演示路径（面试 / 产品 demo 标准版）

### 路径顺序（5 分钟内完成）

| # | 操作 | 耗时 | 说明 |
|---|------|------|------|
| 1 | 打开首页，指向 HomeDashboardPanel 6 区块 | 20s | 说明系统整体覆盖：A 股/港股/6 语言/3 主题 |
| 2 | 切换主题（light-holo → dark-dive → paper-lilac）| 15s | 三套 CSS 变量实时切换，0 FOUC |
| 3 | 语言切换 zh-CN → en-US | 10s | 说明 i18n 覆盖 11 组件 |
| 4 | 搜索 "000001"，进入股票详情页 | 20s | Dashboard/K 线/MACD+RSI/AI 解读/新闻时间线 |
| 5 | 点击"开始综合分析"，选择 technical_only | 20s | SSE 实时进度条启动 |
| 6 | 等待 agent_started / agent_completed 事件流更新 | 60s | 边看进度边讲 SSE + Registry 架构 |
| 7 | 报告生成后，展示 Markdown 格式、导出按钮 | 20s | output_language 与 UI 语言独立 |
| 8 | 进入报告中心，展示 FilterPanel 5 维筛选 | 20s | scope/auto_saved/date_range 筛选 |
| 9 | 进入自选股工作台，批量操作 + 股票对比 | 20s | WatchlistToolbar → StockCompareView |
| 10 | 回首页，打开 dev 模式，切换 engine=langgraph | 15s | 同一接口双引擎灰度，shape 100% 兼容 |

**总计**：~4 分钟，留 1 分钟答问。

---

## 技术亮点讲解词（面试版）

### SSE 可靠性设计
> "前端使用 fetch + ReadableStream 替代 EventSource，原因是 EventSource 不支持 Authorization 头。断线恢复通过 after_event_id 参数从服务端 replay 已发事件，协议层零状态丢失。"

### Registry 抽象层
> "AnalysisRunRegistry 是一个 ABC，MemoryAnalysisRunRegistry 用于单 worker 开发，RedisAnalysisRunRegistry 用于多 worker 生产。切换只需 ANALYSIS_RUN_REGISTRY=redis，零代码改动。M43 压测：4 worker × 8 run 并发，16/16 PASS。"

### 双 Engine 灰度
> "custom_coordinator 是稳定基线，LangGraph 是并行实现的 Send API fan-out 版本。M41 对比验证：response shape 100% 兼容（Python set diff = ∅），性能比 0.97x。M42 实现 DEFAULT_ANALYSIS_ENGINE env 变量，一行切换 staging 默认，不需要改代码也不需要重新部署。"

### asyncio.shield 心跳修复
> "SSE 心跳原本用 asyncio.wait_for(gen.__anext__(), timeout=15)。TimeoutError 会取消底层 coroutine，触发 async generator cleanup 关闭流。修复是 asyncio.shield(pending_task)——shield 保护 task 不被外层超时取消，心跳超时只是 yield 一次 ': heartbeat\\n\\n'，流保持打开。"

### output_language 独立设计
> "AI 报告输出语言和 UI 语言是两个独立设置。前者通过 output_language 字段透传给每个 Agent 的 system prompt；后者通过自定义 i18n.js 控制界面文本。两者互不干扰，用户可以看中文 UI 但生成英文报告。"
