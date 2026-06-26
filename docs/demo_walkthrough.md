# TradingAgents Demo 演示指南

> 状态：C5 Chat Copilot Action Tools + ConfirmationManager 完成（2026-06-18）  
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
  - 左列：最近报告（top 3）、自选快跳（top 4，含"批量对比"入口）
  - 右列：行业热门板块（top 6，按 hot_score 降序）、行业热股（compact）
  - 底部 compare bar（有对比列表时显示）
- 点击自选快跳"填入"或行业热门股 → 填入 StockInputPanel（不自动分析）
- 点击自选快跳"批量对比" → /watchlist?mode=compare，自动进入批量选择模式

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

### Step 13：Chat Copilot — Agentic AI 体验（60s）

- 点击 BottomTabBar 最右侧"Chat"tab，进入 `/chat`
- **演示异动分析场景：**
  - 输入："中船特气今天为什么涨了这么多？"
  - 展示 **ChatToolTrace**：resolve_stock → get_quote → get_kline_summary → get_latest_news（4 工具链）
  - 展示 **ChatResultCard**：行情摘要 + 新闻摘要 + 免责声明
- **演示加入自选场景：**
  - 输入："把中船特气加入我的自选股"
  - 展示 **ConfirmActionCard**：确认卡片
  - 说明：C4 阶段 mock confirmation；C5 阶段接入真实写操作
- **演示行业热点场景：**
  - 输入："今天哪些行业热度最高"
  - 展示 **ChatResultCard** industry_hot 卡片

**讲解要点：**
- Tool Registry 架构：BaseTool ABC → ToolResult → ToolRegistry，9 只工具，权限 4 级（read_only/write_user_data/long_running/sensitive）
- 写操作全部走 ConfirmationManager，永不自动执行
- 安全边界：所有 answer 含免责声明，禁止买入/卖出/持有/目标价
- OpenClaw-inspired 全链路：C5 Action Tools → C6 Financial Skills → C7 Planner → C8 Memory + Audit → **C9 OpenClaw-style Skill Registry ✅**
- "这是当前 Agent 可用金融技能列表（GET /chat/skills）—— 技能并非前端按钮，而是后端可注册、可发现、可禁用、可审计的 Agent 能力"
- SkillSpec JSON 文件化：每个技能声明 required_tools、safety_rules、enabled 状态，SkillRegistry 启动时校验工具可用性

### Step 14：SSE Streaming 演示（60s，C13-a 新增）

- **演示正常研究问题的流式响应：**
  - 输入："帮我分析一下贵州茅台的技术面"
  - 展示消息气泡**立即出现**（agent_started 事件触发）
  - 展示**研究步骤**逐步更新（intent_detected / skill_started 事件）
  - 展示 **tool_completed 事件**在工具执行后追加到步骤列表
  - 展示 **answer_delta**：答案文字逐块出现（打字机效果，25字/块）
  - 整个过程无需等待完整响应返回

- **演示 Stop 按钮：**
  - 输入较复杂问题并立即点击"停止"按钮
  - 展示响应立即中断（AbortController.abort() 取消 fetch + 后端 task 取消）

- **演示 Fallback：**
  - （可在 DevTools 中 block stream 端点触发）
  - 展示 fallback 提示（`chat_stream_fallback`）出现后切换为同步模式正常返回答案

**讲解要点：**
- SSE 使用 `fetch + ReadableStream`（不用 EventSource），原因：需要 POST 请求 + Authorization header
- 后端 asyncio.Queue + background Task 模式：task 持有 db session，generator 只从 queue 读 SSE 字符串
- `asyncio.shield(queue.get())` 防止 keepalive 超时取消底层 get 操作
- `event_callback` 可选参数透传到 process_message / SkillContext，失败静默，不影响主流程
- answer_delta payload 仅含最终 answer 文本分块，不含私有 CoT 或系统 prompt
- 禁用词覆盖流式响应（answer 已经过 Safety Guardrails 过滤）

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
3. **Chat Copilot Tool Registry**：BaseTool ABC → ToolResult → ToolRegistry，9 只只读金融工具，权限 4 级；OpenClaw-inspired C5–C9 路线图就绪
4. **stock_master 主数据表**：5,166 只 A 股 + 申万行业 CSV 映射，港股手工维护
5. **Hot Score 行业体系**：`log(成交额)×0.4 + |涨跌幅|×0.6` 动态计算
6. **数据质量评分**：纯前端四维度，帮助用户理解报告边界，不依赖新 API
7. **compareStorage 对比链路**：localStorage + CustomEvent 跨页面同步，URL query 为 source of truth
8. **移动端 PWA 风格**：BottomTabBar + safe-area 自适应，≤640px 单列布局

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

---

## 七、未来演示路径：通过聊天完成股票研究任务（Phase C 规划）

> 本节为规划阶段，对应 Phase C2~C8，尚未实现。

### Chat Copilot 演示路径（5 分钟，规划版）

| # | 用户输入 | Agent 行动 | 展示重点 |
|---|---------|-----------|---------|
| 1 | "中船特气今天为什么大涨" | resolve_stock → get_quote → get_latest_news → 综合回答 | 自然语言 → 多工具编排 |
| 2 | "帮我生成一份综合分析报告" | 确认弹窗 → create_analysis_run → SSE 进度 → 报告摘要 | 写操作确认 + SSE 复用 |
| 3 | "这个报告里均线多头排列是什么意思" | get_report_detail → 提取技术面段落 → 通俗解释 | 历史报告追问能力 |
| 4 | "把它加入我的自选股" | 确认弹窗 → add_to_watchlist → 跳转链接 | 自然语言 → 写操作 → 现有页面落地 |
| 5 | "帮我对比 600519 和 000858" | 确认弹窗 → create_compare_selection → /compare URL | 多步骤 + 页面联动 |

### Chat Copilot 技术亮点说明（规划版）

**Agentic 设计**
> "Chat 不仅是聊天框，核心是 Agent 能调用工具、记忆上下文、执行多步骤任务，把结果落到现有页面和用户资产中。工具层直接复用现有 11 个后端 API，零重复实现。"

**安全与合规**
> "所有写操作必须用户确认，永不输出买入/卖出/持有建议。新闻等外部内容视为不可信，防止 prompt injection。工具白名单机制确保 LLM 无法调用未授权功能。"

**复用现有基础设施**
> "Chat API 的报告生成工具直接调用现有 /analysis/runs 接口，SSE 进度复用 AnalysisRunRegistry；认证复用 Bearer token；i18n 复用现有 6 语言系统——Chat 层没有重复造轮子。"

**记忆层**
> "三层记忆：短期记忆（消息历史，20轮窗口）、结构化记忆（最近股票/用户偏好/自选股快照，从 DB 加载）、任务状态记忆（Planner 执行状态，含 pending_action TTL）。记忆严格按 session_id + user_id 隔离。"


---

## 八、Chat Copilot C5 演示脚本（已实现，3-5 分钟）

> **适用范围：** Phase C5 + C5-b 完成后（2026-06-18）。写操作均为真实执行，ConfirmationManager 全状态追踪。

### 演示前准备

```bash
# 确保 Redis 运行（AnalysisRunRegistry）
redis-server &

# 后端（4 worker）
cd backend && uvicorn app.main:app --reload

# 前端
cd frontend && npm run dev
```

### 演示步骤（13 步，~4 分钟）

| # | 操作 | 说明 | 时长 |
|---|------|------|------|
| 1 | 打开 `/chat`，确认底部 Tab 高亮「聊天」 | C2 路由 + BottomTabBar | 10s |
| 2 | 输入「中船特气最近为什么涨这么多」 | anomaly 意图：resolve → quote → kline → news 四工具链 | 20s |
| 3 | 观察 tool_events 展开，展示工具调用链 | ToolProgressPanel 可折叠 | 10s |
| 4 | 输入「帮我生成 688146 的综合分析报告」 | report 意图 → ConfirmationCard 弹出 | 10s |
| 5 | 点击「确认」，观察 ConfirmationCard 状态变化：pending → executing → executed | C5 ConfirmationManager 完整生命周期 | 15s |
| 6 | analysis_run 卡片出现：展示 run_id、「查看报告中心」链接 | C5 ActionResult cards 渲染 | 10s |
| 7 | 点击「查看报告中心」→ 跳转 `/history` | 链路验证：报告中心 | 10s |
| 8 | 返回 `/chat`，输入「把它加入我的自选股」（或「把中船特气加入自选」） | watchlist_add 意图 → ConfirmationCard | 15s |
| 9 | 点击「确认」→ watchlist_action 卡片，already_exists=False | execute_add_to_watchlist 真实 DB 写入 | 10s |
| 10 | 重复步骤 8/9（幂等测试）→ watchlist_action 卡片，already_exists=True | 幂等保护，无重复插入 | 10s |
| 11 | 输入「帮我买入 688146」→ 安全拒绝消息 | C5-b 交易守卫，无 confirmation 弹出 | 10s |
| 12 | 输入「对比宁德时代和贵州茅台」→ compare_link 卡片 | create_compare_selection（同步，无 DB） | 10s |
| 13 | 点击「进入对比页」→ 跳转 `/compare?stocks=CN:300750,...` | 链路验证：对比页 | 10s |

**总计：~4 分钟**，留 1 分钟演示 ConfirmationCard 「取消」分支（步骤 8 重做，点「取消」，状态变 `cancelled`）。

### 技术亮点讲解词（C5 版）

**ConfirmationManager 设计**
> "写操作不直接执行，而是生成 pending confirmation dict 存入 ChatMessage.confirmation JSONB 字段（零 migration）。Router confirm 端点执行三重守卫：status != pending → 409 幂等拒绝；is_expired → 写 DB expired 状态，不执行；confirmed=false → 写 DB cancelled。整个生命周期 pending/executing/executed/cancelled/failed/expired 全部可追踪。"

**savepoint 幂等设计**
> "execute_add_to_watchlist 先 SELECT 检查，新增时用 SQLAlchemy `async with db.begin_nested()` 创建 savepoint。IntegrityError（并发竞争）只回滚 savepoint，外层事务保持，后续 update_confirmation_status 和 save_assistant_message 正常执行。这是对比简单 db.rollback() 的关键区别。"

**Vue 3 深层响应式**
> "confirmation 是嵌套在 messages 数组里的 dict，直接赋值 `origMsg.confirmation.status = 'executing'` 不会触发深层 watcher。修复是对象替换：`origMsg.confirmation = { ...origMsg.confirmation, status: 'executing' }`，Vue 检测到对象引用变化，prop 更新正确触发。"

**模块级 import 与可测试性**
> "action_tools.py 把 get_llm_client / get_run_registry / RealtimeAnalysisRunner 放在模块顶部 import（非函数内局部 import），这是 pytest `patch()` 能工作的前提。函数内 import 会让 patch 目标路径失效，单元测试无法隔离真实服务调用。"


---

## 九、Chat Copilot C6 Skills 演示脚本（已实现，3-4 分钟）

> **适用范围：** Phase C6 完成后（2026-06-18）。展示 SkillRegistry 路由与 6 只 Financial Skills。

### 演示步骤（10 步，~3.5 分钟）

| # | 输入 | 走哪个 Skill | 展示重点 | 时长 |
|---|------|------------|---------|------|
| 1 | 「中船特气最近为什么涨这么多」 | StockAnomalySkill（priority=40）| 4 工具链：resolve→quote→kline→news；结构化 Markdown（异动摘要/关键发现/后续观察） | 20s |
| 2 | 展开 tool_events 面板 | — | ChatToolTrace 展示 4 个工具调用链，含 status 图标 | 10s |
| 3 | 「帮我重点看中船特气的风险」 | RiskFirstSkill（priority=35）| 风险优先输出：技术面风险 + 新闻面风险 + 数据缺口 | 20s |
| 4 | 「688146 最近新闻有什么实质影响」 | NewsCatalystSkill（priority=45）| 区分已发生事实/市场预期/未兑现风险 | 15s |
| 5 | 「看看我的自选股，哪些需要关注」 | WatchlistReviewSkill（priority=20）| 巡检最多 5 只，生成研究线索；空自选股→引导添加 | 20s |
| 6 | 「今天哪些行业值得重点研究」 | IndustryHotspotSkill（priority=30）| 行业热度排行 + 研究线索（不说"值得买"） | 15s |
| 7 | 「解释我最近一份报告的结论」 | ReportExplanationSkill（priority=10）| 报告摘要+核心结论+风险（不复制原文） | 15s |
| 8 | 「帮我买入688146」 | 安全守卫（不走 Skill）| Safety Guard 优先拦截，无 confirmation 弹出 | 10s |
| 9 | 「帮我生成688146综合报告」 | Action Intent（不走 Skill）| C5 ConfirmationCard 正常弹出 | 10s |
| 10 | 「把中船特气加入自选」 | Action Intent（不走 Skill）| C5 watchlist confirmation 正常执行 | 10s |

**总计：~3.5 分钟**

### 技术亮点讲解词（C6 版）

**SkillRegistry 设计**
> "SkillRegistry 持有 6 个 BaseSkill 实例，按 priority 排序（值越小优先级越高）。select_skill() 遍历 can_handle()，首个匹配的 Skill 获得执行权。这比随机 if/elif 链可维护——新增一个 Skill 只需实现 can_handle + run，register 一次即可。"

**Orchestrator 4 层优先级**
> "process_message 有 4 层分发：1) 交易安全守卫（永远第一）→ 2) Action 意图（加自选/生成报告/对比）→ 3) SkillRegistry（6 只研究 Skills）→ 4) C4 直接工具 fallback。Skills 不会抢走 Action 意图，也无法绕过安全守卫。"

**SkillContext 依赖注入**
> "SkillContext 是 Skill 获取外部依赖的唯一入口：db、user_id、tool_registry。这让 Skill 完全可测试——测试只需 mock tool_registry.call，不需要真实数据库或外部 API。module-level import 是关键：确保 patch() 能正确定位目标。"

**Skill 工具失败降级**
> "每个 Skill 对工具失败有明确处理：kline 失败 → 说明'K 线数据不足'，news 失败 → 说明'暂无新闻数据'，整体不崩溃。这遵循 OpenClaw 的 Graceful Degradation 原则——局部数据缺失不影响其他维度的研究输出。"

---

## 十、Chat Copilot C7 Controlled Planner 演示路径

> **适用范围：** Phase C7 完成后（2026-06-18）。展示 RuleBasedPlanner 复合任务检测与 PlannerExecutor 多步执行。

### 演示步骤（6 步，~3 分钟）

| # | 输入 | 触发类型 | 展示重点 | 时长 |
|---|------|---------|---------|------|
| 1 | 「688146为什么涨这么多然后重点看风险」 | anomaly_then_risk | metadata.planner_used=True；步骤摘要：异动分析→风险研究→综合结论 | 25s |
| 2 | 展开 tool_events 面板 | — | 来自两个 Skills 的工具调用链合并显示 | 10s |
| 3 | 「解释这份报告并告诉我主要风险」 | report_then_risk | ReportExplanationSkill → RiskFirstSkill → 最终摘要 | 20s |
| 4 | 「688146为什么涨这么多顺便加自选」 | research_then_action | Planner 先运行 StockAnomalySkill → 再弹出 add_watchlist confirmation | 25s |
| 5 | 确认自选股添加 | — | ConfirmationManager 执行写操作，卡片显示成功 | 10s |
| 6 | 「比较宁德时代和紫金矿业然后帮我生成报告」 | compare_then_report | Planner 弹出对比确认 + 澄清步骤（请指定为哪只股票生成报告） | 20s |

**总计：~3 分钟**

### 技术亮点讲解词（C7 版）

**RuleBasedPlanner 设计原则**
> "Planner 采用纯正则规则，无 LLM 参与——两个信号：连接词检测（然后/之后/并且/如果等）和多意图信号计数（≥2 个意图域同时出现）。无 LLM 的好处：响应时间降为零（纯正则匹配），行为完全可预测，100% 单元可测试。"

**Orchestrator 6 层分发**
> "C7 新增第 3 层 Planner，分发优先级：1) Safety Guard → 2) Action 意图 → 3) Controlled Planner（复合任务）→ 4) SkillRegistry（单步研究）→ 5) C4 fallback → 6) Default。Planner 在 Action 层之后，确保明确的加自选/生成报告意图不被 Planner 劫持。"

**PlannerExecutor 安全边界**
> "action step 在 PlannerExecutor 里永远只调用 make_confirmation()，绝不执行写操作。真正的写操作只发生在用户点击确认后，经由 ConfirmationManager 的独立生命周期（pending→executing→executed）来管理。这是一个关键的安全约束：Planner 的'规划'不能绕过确认流程。"

**多步骤结果聚合**
> "_synthesize() 从所有 skill_results 中提取关键行 —— 综合结论（第一个 Skill 的前 4 行）、主要风险（第二个 Skill 的前 3 行）、后续观察（所有 Skill 的编号观察项）—— 组装成 ## 多步骤研究摘要 格式。每个 Skill 的输出互为补充，Planner 把它们变成一个连贯的研究叙事。"

---

## 十一、C8–C10 综合演示脚本（官方推荐路线，Phase C11）

> **版本：** C11 整理（2026-06-20）  
> **适用：** Phase C10 完成后正式演示。含 4 条路线，总时长约 12 分钟。  
> **推荐演示股票：** CN/688146（中船特气）— 异动、风险、多步骤 Planner 效果最佳。

---

### Route A：基础 Agent 研究能力（约 3 分钟）

**目标：** 展示单步 Skill 路由、Tool Trace、免责声明。

| # | 操作 | 讲解词 |
|---|------|--------|
| 1 | 打开 `/chat`，展示 ChatContextPanel 技能列表 | "右侧是 Agent 技能列表，来自后端 GET /chat/skills，不是前端硬编码。" |
| 2 | 输入：`中船特气最近为什么涨这么多？` | 发送后约 2-3 秒返回结果 |
| 3 | 展开 Tool Trace | "Agent 自动调用了 resolve_stock → get_quote → get_kline_summary → get_latest_news，用户无需指定工具。" |
| 4 | 指出 StockAnomalySkill | "这条消息路由到了 StockAnomalySkill，因为 '为什么涨' 匹配了异动意图信号。" |
| 5 | 指出底部免责声明 | "_仅供研究参考，不构成投资建议。_ 这是系统硬编码的，每条答案都有。" |
| 6 | 输入：`帮我买入688146` | "看看安全守卫..." |
| 7 | 展示拒绝响应 | "买入意图被 _TRADING_PATTERN 拦截，不调用任何工具，直接返回研究边界说明。" |

---

### Route B：Planner + Risk 多步骤研究（约 4 分钟）

**目标：** 展示 RuleBasedPlanner 复合意图检测、PlannerExecutor 顺序执行、两步结果聚合。

| # | 操作 | 讲解词 |
|---|------|--------|
| 1 | 输入：`帮我分析中船特气为什么涨，然后重点看风险` | "关键词是'然后'—— 这是复合连接词。" |
| 2 | 等待结果（约 4-5 秒） | |
| 3 | 指出答案结构 | "答案包含两个部分：异动分析 + 风险梳理。这是 Planner 执行两步的结果。" |
| 4 | 展开 Tool Trace | "Step 1：StockAnomalySkill（4 个工具）。Step 2：RiskFirstSkill（3 个工具）。两步合计 7 次工具调用。" |
| 5 | 解释 Planner | "RuleBasedPlanner 是纯正则规则，无 LLM。'然后' + 异动信号 + 风险信号 → anomaly_then_risk 计划。零延迟，行为完全可预测。" |
| 6 | 指出 metadata | "OrchestratorResult.metadata 中有 skill_spec_version=c9_v1，记录了技能版本。" |

---

### Route C：Action + Confirmation（约 3 分钟）

**目标：** 展示写操作确认流程、ConfirmationManager、watchlist_action card。

| # | 操作 | 讲解词 |
|---|------|--------|
| 1 | 输入：`把中船特气加入自选` | |
| 2 | 展示确认卡（ConfirmationCard） | "Agent 不会直接执行写操作。它先返回一张确认卡，等待用户明确同意。" |
| 3 | 指出确认卡内容 | "卡片显示：股票信息 + 操作说明 + '是否确认' + 10 分钟超时提示。" |
| 4 | 点击「确认」 | |
| 5 | 展示成功卡片 | "后端执行 POST /watchlist，返回 watchlist_action card，操作可回溯。" |
| 6 | 说明安全设计 | "写操作永远是二阶段：pending → confirmed。用户点确认前什么都不会改变。这是 OpenClaw Action Layer 的核心设计。" |
| 7 | 跳转自选股页 | "点击卡片上的'查看自选股'跳转到 /watchlist，刚加入的股票已在列表中。" |

---

### Route D：SkillSpec 技能发现（约 2 分钟）

**目标：** 展示 OpenClaw-style Skill Registry、SkillSpec JSON 元数据、GET /chat/skills。

| # | 操作 | 讲解词 |
|---|------|--------|
| 1 | 展示 ChatContextPanel 技能区域 | "右侧 'Agent 技能' 区域列出了当前可用技能，含 enabled/available 状态。" |
| 2 | 用 curl 或 API 工具调用 `GET /chat/skills`（需 Bearer token） | "这些数据来自后端的 SkillSpec JSON 文件。" |
| 3 | 展示返回的 JSON | "每个技能有 name / enabled / required_tools / permission_level / safety_rules / version=c9_v1。" |
| 4 | 打开 `specs/stock_anomaly.json` | "这是 StockAnomalySkill 的声明式配置。技能不是 if/elif，而是可注册、可发现、可禁用、可审计的能力单元。" |
| 5 | 说明 enabled gate | "`enabled=false` 的技能不会出现在 select_skill() 结果中，运行时可调用 `set_skill_enabled()` 动态禁用，无需重启服务。" |

---

### 技术问答速查（演示中可能被追问）

| 问题 | 30 秒回答 |
|------|----------|
| "这和 ChatGPT 有什么区别？" | ChatGPT 是通用 LLM。TradingAgents 是针对金融研究的 Agentic 系统：有工具白名单、技能注册表、受控 Planner、写操作确认、安全护栏、30 golden tasks 验收。 |
| "为什么 Planner 不用 LLM？" | 金融场景确定性比灵活性重要。规则 Planner 零延迟、行为可预测、100% 可单元测试。后续可升级为 LLM-assisted Planner，但执行层保持规则控制。 |
| "系统稳定吗？" | 389/389 tests PASS，30 golden tasks 覆盖全部 6 层能力，evaluation script 可复现。 |
| "会不会给出投资建议？" | 不会。`_TRADING_PATTERN` 在 Orchestrator 入口拦截买入/卖出/目标价，所有答案有硬编码免责声明。 |

---

### 快速启动演示环境

```bash
# 后端
cd backend
uv run uvicorn app.main:app --reload --port 8000

# 前端（另一终端）
cd frontend
npm run dev   # http://localhost:3001

# 验证测试
cd backend
uv run pytest tests/ -q          # 447/447 PASS
uv run python scripts/evaluate_chat_agent.py --suite all  # 30/30 PASS
```

---

## 第十二节：C11-b 演示路线（RAG / Internal Agents / Chat UX）

### Route E — RAG 可信度审查（3 min）

1. 输入 `中船特气最近为什么涨这么多？`
2. 等待 StockAnomalySkill 返回，展开工具调用 trace
3. 找到 `rag_retrieve`（检索文档数）和 `rag_review`（可信度评级）两个事件
4. 查看答案末尾的 **资料来源与可信度** 小节
5. 讲解要点：RAG 不依赖向量数据库，使用现有 ToolRegistry，rule-based 三审，无幻觉风险

### Route F — 分析并保存报告 Intent（2 min）

1. 输入 `分析 688146 并保存到历史报告`
2. 展示确认卡（`create_analysis_run` + `save_to_history=true`）
3. 讲解要点：比"生成综合报告"多了 save_to_history 参数，演示 orchestrator intent 分离

### Route G — 外部渠道礼貌拒绝（1 min）

1. 输入 `把报告发到我的邮箱`
2. 展示拒绝回复："暂不支持向外部渠道推送"
3. 展示 `docs/external_agent_channels_design.md` 说明未来设计路线

### Route H — Chat UX 展示（2 min）（C12 更新）

1. 展示 ChatSessionSidebar（历史对话列表，新建/切换/删除 session）
2. 展示 **研究步骤**（ChatReasoningSteps，有 running/pending 步骤时自动展开）
3. 输入一个耗时请求，展示 15s soft timeout 提示 + 停止按钮
4. 展示 QuickActions：**5 条快捷问句 + "换一换"循环切换**（C12 精简自 4 组 × 4 题）
5. 点击快捷问句：**填入输入框但不自动发送**（用户可继续编辑）

### Route I — C12 即时研究步骤演示（1 min）

1. 输入任意股票问题（如 `中船特气最近为什么涨这么多？`）
2. 观察：发送后 **100ms 内** 立即显示 5 个 placeholder 研究步骤：
   - 问题分析（running）/ RAG 资料检索 / 资料审查 / 工具调用 / 结论生成（均 pending）
3. API 响应后：placeholder 替换为真实 tool_events，动画流入
4. 讲解要点：用户感知到 AI 正在"思考"，无空白等待感
