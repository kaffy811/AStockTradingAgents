# 产品体验改进计划

> 版本：M30（2026-06-06）  
> 用途：记录已完成和计划中的体验改进，供面试展示与项目交接。

---

## 已完成

### M28-a — 综合分析页低风险修复（2026-06-06）

| 修复 | 状态 |
|------|------|
| `/industry` → `/industries` 路由黑屏修复 | ✅ 完成 |
| 按钮文案：生成综合分析 → 生成报告 | ✅ 完成 |
| 卡片标题：生成综合分析报告 → 生成分析报告 | ✅ 完成 |
| "快速示例："→"例如："轻量 hint | ✅ 完成 |
| AnalysisResultLayout"新建分析"按钮 | ✅ 完成 |

### M29 — 综合分析页体验增强（2026-06-06）

| 功能 | 状态 |
|------|------|
| recentSearches count 字段（向后兼容） | ✅ 完成 |
| getTopSearches(n) 高频搜索 Top N | ✅ 完成 |
| RecentSearchList 默认 5 条 / 展开 10 条 | ✅ 完成 |
| RecentSearchList count badge（>= 2 显示，>= 5 accent） | ✅ 完成 |
| DiscoveryPanel 高频搜索 Top 5 + fallback | ✅ 完成 |
| StockInputPanel 首次引导 glow（8s 自动消失） | ✅ 完成 |
| 单面报告统一增加"一、摘要"节 | ✅ 完成 |
| reportText.extractSummary 多匹配（一摘要/一核心摘要/二核心结论） | ✅ 完成 |
| AnalysisModeSelector 文案优化 | ✅ 完成 |

### M30 — 行业研究页重构与行业热度全览（2026-06-06）

| 功能 | 状态 |
|------|------|
| IndustryHeatOverviewCard — 行业热度全览网格 | ✅ 完成 |
| IndustryHotBlocksCard — 行业热门板块 | ✅ 完成 |
| 行业页首屏双卡布局（桌面并排，移动单列） | ✅ 完成 |
| 快速跳转股票详情下移至统计栏下方 | ✅ 完成 |
| 热门股默认 20 支（后端 limit le=50，default=20） | ✅ 完成 |
| DiscoveryPanel"行业机会"→"行业热度" | ✅ 完成 |
| IndustryHotBlocksCard 展开/收起（最多 20 条） | ✅ 完成 |
| 行业页全部入口联动 selectedCode（热格/热块/toolbar） | ✅ 完成 |

### M31 — 行业热度数据聚合与热门板块真实数据接入（2026-06-06）

| 功能 | 状态 |
|------|------|
| `IndustryInfoResponse` 扩展 hot_score / stock_count / up_count / down_count / avg_change_pct / amount / trade_date / score_version / data_quality | ✅ 完成 |
| `IndustryHotStockService.get_industry_hot_summary()` — GROUP BY industry_code 聚合 | ✅ 完成 |
| `GET /industries` 合并热度摘要，无快照行业返回 hot_score=null | ✅ 完成 |
| IndustryHeatOverviewCard tileTooltip 展示 hot_score / stock_count / avg_change_pct | ✅ 完成 |
| IndustryHotBlocksCard 每行展示 avg_change_pct（涨跌色）+ hot_score + stock_count | ✅ 完成 |
| 无 hot_score 数据时显示 EmptyState（已有快照才渲染排行） | ✅ 完成 |

---

## 后续计划（未实现）

### 行业热度相关

| 功能 | 说明 |
|------|------|
| 行业历史走势 K 线 | 需要历史行情数据；当前无此数据源，不伪造 |
| IndustryHotBlocksCard 热度排行 | 依赖上述 API；当前因无数据显示 EmptyState |
| 行业历史走势 K 线 | 需要历史行情数据；当前无此数据源，不伪造 |
| 独立路由 /industries/blocks | M31/M32 规划：点击"展示全部"后进入独立页 |
| 独立路由 /industries/:market/:code | M31/M32 规划：行业详情页 |

### M32 — 三主题系统与全局视觉变量改造（2026-06-06）

| 功能 | 状态 |
|------|------|
| `theme.js` — applyTheme / getStoredTheme / THEMES | ✅ 完成 |
| `variables.css` 三套 `html[data-theme]` 主题块 + 旧变量兼容别名 | ✅ 完成 |
| `settings.js` DEFAULTS 新增 `theme: 'light-holo'` | ✅ 完成 |
| `main.js` 启动时 applyTheme(getStoredTheme())，避免闪烁 | ✅ 完成 |
| `App.vue` 监听 SETTINGS_EVENT → applyTheme | ✅ 完成 |
| `ProfileSettingsPanel.vue` 三主题 segmented control，切换立即生效 | ✅ 完成 |
| `base.css` body 使用 --bg-page-gradient，.card 加 --shadow-card，.btn-primary 使用 --accent-gradient | ✅ 完成 |
| `TechnicalChartPanel.vue` CSS var 驱动 buildColors()，refreshChartColors() 实时刷新图表 | ✅ 完成 |
| `StockMiniTrend.vue` 使用 --up-color / --down-color / fill-opacity | ✅ 完成 |
| AppHeader / IndustryHeatOverviewCard / IndustryHotBlocksCard 硬编码 rgba → CSS var | ✅ 完成 |
| 188 modules，compileall PASS，无新依赖，无新 migration | ✅ 完成 |

### 主题与多语言（后续）

| 功能 | 说明 |
|------|------|
| 多语言 MVP（zh-CN + en） | ✅ M34 已实现：自定义 i18n.js + 6 locale 文件 |
| 全站逐组件深度视觉统一 | ✅ M33-a 已完成：全站 215 处 rgba → CSS var |

### 首页与综合分析

| 功能 | 说明 |
|------|------|
| AnalysisModeSelector 结果页快捷切换 | M32 规划 |
| Portfolio 组合分析 | 未规划 |
| Redis run registry | ✅ M40-b 已实现，M43 4-worker 16/16 PASS |

---

### M34 — UI 多语言 MVP（2026-06-07）

| 功能 | 状态 |
|------|------|
| 自定义 i18n.js 单例（`_locale = ref('zh-CN')`）+ 6 locale 文件 | ✅ 完成 |
| AppHeader / BottomTabBar / ComprehensiveAnalysisView 翻译 | ✅ 完成 |
| ProfileView + ProfileSettingsPanel 翻译 + 语言切换 selector | ✅ 完成 |
| 主 main.js 启动时读取 localStorage 防 FOUC | ✅ 完成 |
| fallback：未翻译键返回 zh-CN 值 | ✅ 完成 |
| 195 modules，compileall PASS，无新依赖 | ✅ 完成 |

### M35 — UI 多语言覆盖补齐（2026-06-07）

| 功能 | 状态 |
|------|------|
| HistoryView + ReportListCard / ReportFilterPanel / ReportCenterStats 翻译 | ✅ 完成 |
| WatchlistView + WatchlistStockCard / WatchlistToolbar / WatchlistStats 翻译 | ✅ 完成 |
| IndustryHotView + 全部 Industry 组件翻译 | ✅ 完成 |
| StockCompareView + 全部 Compare 组件翻译 | ✅ 完成 |
| ~55 alias 键，195 modules，build PASS | ✅ 完成 |

### M36 — AI 报告输出语言 output_language（2026-06-07）

| 功能 | 状态 |
|------|------|
| ProfileSettingsPanel"报告输出语言"selector（独立于 UI 语言） | ✅ 完成 |
| 6 语言支持：zh-CN / en-US / zh-TW / ja-JP / ko-KR / es-ES | ✅ 完成 |
| backend synthesis prompt 末尾追加语言指令（仅非 zh-CN） | ✅ 完成 |
| single-agent 报告 wrapper 多语言（_SINGLE_AGENT_STRINGS） | ✅ 完成 |
| fallback 报告多语言（_FALLBACK_STRINGS） | ✅ 完成 |
| DB 列 `output_language VARCHAR(16) NOT NULL DEFAULT 'zh-CN'`（migration c5e9f12a3b87） | ✅ 完成 |
| ReportListCard / ReportDetailHeader output_language badge（非 zh-CN 时显示） | ✅ 完成 |
| 历史报告 getReport() 返回 output_language | ✅ 完成 |
| 195 modules，compileall PASS，alembic head PASS | ✅ 完成 |

---

## 后续计划（未实现）

### M37 — Agent-level 输出语言优化（已知限制）

> **背景**：M36 已完成 synthesis 类报告（comprehensive / technical_fundamental）的目标语言完整输出。
> single-agent 报告（technical_only / fundamental_only / peer_only / news_only）的 wrapper 结构已翻译，
> 但各 Agent 主体内容语言取决于 Agent 自身 prompt，目前仍输出中文。

| 优化项 | 说明 |
|--------|------|
| TechnicalAnalystAgent prompt 注入语言指令 | 接收 output_language 参数，在 system/user prompt 末尾追加【输出语言】 |
| FundamentalAnalystAgent prompt 注入语言指令 | 同上 |
| PeerComparisonAnalystAgent prompt 注入语言指令 | 同上 |
| NewsAnalystAgent prompt 注入语言指令 | 同上 |
| RealtimeAnalysisRunner 透传 output_language 至 _run_named_agent | 需修改 _run_named_agent 签名及各 agent.analyze() 方法 |
| LangGraph graph _agent_node 透传 output_language | 从 state 取 output_language，传至 agent.analyze() |

**优先级**：✅ 已完成（M37，2026-06-07）。

### M37 完成状态

| 优化项 | 状态 |
|--------|------|
| 新建 `language_utils.py` — normalize + build_instruction helper | ✅ 完成 |
| TechnicalAnalystAgent.analyze output_language 参数 + prompt 注入 | ✅ 完成 |
| FundamentalAnalystAgent.analyze output_language 参数 + prompt 注入 | ✅ 完成 |
| PeerComparisonAnalystAgent.analyze / analyze_async output_language 参数 | ✅ 完成 |
| NewsAnalystAgent.analyze output_language 参数 + prompt 注入（新闻标题原文保留） | ✅ 完成 |
| comprehensive_analysis_coordinator 三处调用点透传 | ✅ 完成 |
| RealtimeAnalysisRunner._run_named_agent 透传 | ✅ 完成 |
| LangGraph 4 个 node 函数从 state.output_language 读取透传 | ✅ 完成 |
| 旧调用向后兼容（默认 zh-CN，空指令，零 token 变化） | ✅ 验证 PASS |
| compileall / npm build / alembic | ✅ ALL PASS |

---

### M38 — 报告 Markdown 格式统一与可读性增强（2026-06-07）

| 功能 | 状态 |
|------|------|
| `language_utils.py` 新增 `REPORT_SECTION_LABELS`（13 键 × 6 语言）+ `report_label()` | ✅ 完成 |
| 4 个 Agent 子章节统一为三级标题（`###`），移除 Agent 自带顶级标题行 | ✅ 完成 |
| `reportText.js` `extractSummary()` 多语言摘要匹配（en-US / ja-JP / ko-KR / es-ES） | ✅ 完成 |
| `markdown.css` 新增 table / code / blockquote 样式 | ✅ 完成 |
| `print.css` 新增 print media 下 table / code / blockquote 覆盖 | ✅ 完成 |
| `exportMarkdown.js` scope 标题 + section 标签按 `output_language` 多语言本地化 | ✅ 完成 |
| `PrintReportView.vue` Agent 状态表头 + section 标题 + 提示文字多语言本地化 | ✅ 完成 |
| 195 modules，compileall PASS，零 migration，零新依赖 | ✅ ALL PASS |

### M40-a — Analysis Run Registry 抽象层 + P0 Bug 修复（2026-06-07）

| 功能 | 状态 |
|------|------|
| **P0 Bug 修复**：`realtime_analysis_runner._do_run()` `output_language` 前移至方法开头，消除 NameError | ✅ 完成 |
| 新建 `run_registry_protocol.py`：`AnalysisRunRef` / `AnalysisRunSnapshot` / `AnalysisRunRegistry` ABC（8 抽象方法） | ✅ 完成 |
| `analysis_run_registry.py` 新增 `MemoryAnalysisRunRegistry`（实现 ABC，旧模块级函数保留兼容） | ✅ 完成 |
| 新建 `run_registry_factory.py`：`get_run_registry()` 单例工厂 | ✅ 完成 |
| `realtime_analysis_runner.py` 重构：接受 `AnalysisRunRef + AnalysisRunRegistry`，零直接 Queue 访问 | ✅ 完成 |
| `langgraph_realtime_runner.py` 重构：同上 | ✅ 完成 |
| `analysis.py` 重构：全程通过 `get_run_registry()` 访问，消除 `AnalysisRun` 直接依赖 | ✅ 完成 |
| 外部行为与 M25-b/M25-c 完全一致（SSE 协议 / 响应 shape / cancel 语义 无变化） | ✅ 验证 PASS |
| compileall PASS，npm build 195 modules PASS，alembic head c5e9f12a3b87，零新依赖，零 migration | ✅ ALL PASS |

---

## Phase M47 / M47-b：综合分析页首页布局与行业热门数据扩容（2026-06-11）

### 改动摘要

**首页仪表盘布局优化：**
- 删除"最近报告"右侧重复的"最近搜索"小卡片（`HomeDashboardPanel.vue` 右列上区域）
- 下方大块 `RecentSearchList` 组件保留，用户仍可访问历史搜索
- 右上区域替换为"行业热门板块"，展示 top 6 行业（按 `hot_score` 降序）
- 信息架构更清晰：左列=个人数据（报告/自选），右列=市场数据（行业/热股）

**行业热门数据扩容：**
- `ComprehensiveAnalysisView.vue` 行业热股请求 limit 5 → 20
- `IndustryHotView.vue` `HOT_LIMIT` 已为 20（无需改动）
- 仪表盘 compact 视图仍 `slice(0, 5)` 保持页面简洁

**行业页 focus 行为：**
- 点击仪表盘行业行 → 路由到 `/industries?focus=<code>`
- 行业页读取 `route.query.focus`，选中对应行业并高亮滚动（1.8s 后消失）
- 新增 `data-industry-code` 属性到 `IndustryHotBlocksCard` 行按钮

**用户体验改善：**
- 行业名、`hot_score`、`avg_change_pct` 缺失均有兜底（`—` / `未知行业`）
- `hot_score` 统一 2 位小数（与行业页一致）
- 6 语言 `ind_blocks_*` + `ind_unknown` 全量补齐

---

## Phase M48：行业热股 Top 20/50 展开交互（2026-06-11）

**行业热股"查看更多/收起"：**
- 行业页（IndustryHotView）默认展示行业热股 Top 20，`HOT_LIMIT=50`（后端一次性返回 50）
- 点击"查看更多" → 展开到 Top 50，前端 slice 控制，无需重新请求
- 点击"收起" → 恢复 Top 20；底部也有收起按钮（展开超过 10 条时显示）
- 切换行业自动重置为收起状态
- 股票数量 ≤ 20 不显示"查看更多"按钮
- 股票列表标题显示 "热门股票 Top 20/50" + 实际展示计数

**首页 Loading Polish：**
- 行业热门板块 loading 状态增加文字："行业热度加载中…"（使用 `ind_loading_heat` key）
- 其他卡片 loading/empty/error 状态已在 M47-b 及更早阶段完善，无需改动

**i18n 补齐：**
- 新增 6 个 key：`ind_loading_heat`、`ind_hot_view_more`、`ind_hot_collapse`、`ind_hot_top_20`、`ind_hot_top_50`、`ind_hot_showing`
- 6 语言全覆盖（zh-TW/ja-JP/ko-KR/es-ES 在 M47-b i18n 块继续追加）

---

## Phase M49：自选股批量对比入口优化（2026-06-11）

**研究工作台闭环：**

首页"自选快跳"卡片底部增加"批量对比"入口（自选股 ≥ 2 只时显示）。点击后路由到 `/watchlist?mode=compare`，WatchlistView 读取 `route.query.mode` 并自动进入批量选择模式，用户勾选 2-4 只股票后点击"对比"直接跳转 `/compare?stocks=CN:000001,...`，StockCompareView 原生解析 URL 加载对比数据。

**功能闭环路径：**
```
首页自选快跳 → 点击"批量对比" 
  → /watchlist?mode=compare（自动进入批量模式）
  → 勾选 2-4 只 → 点击"对比"
  → /compare?stocks=CN:000001,CN:000002
  → StockCompareView 自动加载并展示多列对比
```

**重用已有基础设施（M17 已实现）：**
- `WatchlistToolbar`：批量选择 / 加入对比 / 清空选择 / 退出批量 按钮全部已有
- `WatchlistView.handleCompare()`：URL 构建逻辑已有
- `StockCompareView` URL query 解析：已有

**本阶段新增：**
- `route.query.mode=compare` → 自动进入 bulkMode
- HomeDashboardPanel "批量对比" 入口按钮 + `go-watchlist-compare` emit
- `dash_compare_bulk` i18n key（6 语言）

---

## Phase M50：A 股全量行业归类与行业页数据扩容（2026-06-11）

**根本原因修复：**
- `refresh_industry_hot_stocks.py` 历史以 `--top-n 5` 运行，快照只有 rank 1-5
- `rank <= limit` 过滤导致即使请求 limit=50 也只返回 5 条
- 重新运行 `--top-n 50`，30/30 行业全量写入 Top-50 快照
- 修复 candidates symbol 重复 bug（seen_syms set 去重）

**接口扩容：**
- `HotStockResponse` 新增 `total` 字段（行业在 stock_industry_map 中的真实成分股总数）
- 后端 `le=50` → `le=100`（为未来扩容留余量）
- 前端 `getIndustryHotStocks` 默认 limit `5` → `20`

**前端展示：**
- `industryTotal` computed 优先读 `hotData.value?.total`，回退 `filteredItems.length`
- 显示格式：`热门股票 显示 N / 行业总数`
- "查看更多" v-if 精确比较 `filteredItems.length > HOT_DISPLAY_DEFAULT`

---

## Phase M51：分析报告 Prompt 结构优化与结论摘要增强（2026-06-11）

**单面 Agent 结论先行结构（4 个 Agent）：**
- 4 个单面 Agent（技术/基本面/同行/新闻）的 `_SYSTEM_PROMPT` 输出格式均新增 `### 摘要结论` 为第一节
- 摘要结论包含：本面结论 / 一句话结果 / 正面信号 / 风险信号 / 后续观察 / 数据可信度
- 各 Agent 描述根据各自分析维度定制（K 线数据源 / 报告期类型 / 同行样本口径 / 新闻数量）

**综合报告结论卡片（comprehensive_analysis_coordinator）：**
- `_SYSTEM_PROMPT` 重构为 6 节：综合结论卡片 / 四面结论汇总 / 主要数据局限 / 后续观察清单 / 风险提示
- `## 一、综合结论卡片` 包含：综合判断 / 一句话结论 / 核心矛盾 / 正面因素 / 主要风险 / 后续观察重点 / 数据完整度
- `## 二、四面结论汇总` 下设 4 个三级标题（技术/基本面/同行/新闻结论）
- fallback 报告 / _FALLBACK_STRINGS 全部 6 语言更新为新节标题

**language_utils.py 扩容：**
- `REPORT_SECTION_LABELS` 新增 12 键（M51 新摘要节标题 + 卡片字段标签），共 25 键 × 6 语言

**前端 extractSummary 兼容：**
- `reportText.js` `extractSummary()` 新增 M51 匹配路径（`### 摘要结论` / `一、综合结论卡片`）
- 保留全部旧路径（向后兼容历史报告）
- 6 语言均有 M51 新路径 + legacy 路径兜底

**静态验证：**
- compileall: ✅ 0 errors
- npm run build: ✅ 195 modules
- alembic current: ✅ c5e9f12a3b87 (head)，零新 migration，零新依赖

---

---

## Phase C1：Chat Copilot 产品方向（2026-06-12，规划阶段）

**新产品方向：TradingAgents Chat Copilot — 对话式 AI 研究助手**

在现有工作台基础上，新增 `/chat` 页面，通过自然语言完成股票研究任务。

**核心体验跃升：**

| 旧体验 | 新体验 |
|--------|--------|
| 用户在多个页面间切换完成研究 | 用户说出研究目标，Agent 调用工具完成任务 |
| 报告是静态页面，无法追问 | 可追问报告内容，Agent 解释指标含义 |
| 加入自选/对比需多次点击 | 一句话完成（含用户确认） |
| 新用户不知从何开始 | Chat 引导用户进入研究流程 |

**MVP 核心能力：**
1. 单股异动/风险分析（只读，无需确认）
2. 生成综合分析报告（long_running，需确认）
3. 解释历史报告（只读）
4. 加入/移除自选股（write，需确认）
5. 创建多股对比（write，需确认）
6. 行业热点查询（只读）
7. 新闻催化分析（只读）

**安全边界：**
- 永不输出买入/卖出/持有/目标价
- 所有写操作需用户显式确认
- 不支持真实交易

**实施阶段：** C2（Chat UI）→ C3（API）→ C4（只读工具）→ C5（写操作）→ C6（Skills 层）→ C7（Planner）→ C8（Memory + Audit）→ C9（OpenClaw Skill Registry）

**相关文档：**
- `docs/chat_agent_prd.md`
- `docs/chat_agent_architecture.md`
- `docs/chat_agent_tool_spec.md`
- `docs/chat_agent_memory_design.md`
- `docs/chat_agent_safety_policy.md`
- `docs/chat_agent_build_plan.md`
- `docs/chat_agent_skills.md`
- `docs/openclaw_inspired_roadmap.md`

---

## Phase C2：Chat Copilot 前端 MVP（2026-06-12，已完成）

**新增 Chat 页面（`/chat`）、8 个 Vue 组件、5 个 mock 场景、BottomTabBar 第 6 个 tab（213 modules）。**

| 组件 | 状态 |
|------|------|
| ChatCopilotView.vue — 主页面框架 | ✅ |
| ChatMessageList.vue — 消息列表 | ✅ |
| ChatInputBar.vue — 输入框 | ✅ |
| ChatResultCard.vue — 结构化结果卡片 | ✅ |
| ChatToolTrace.vue — 工具调用轨迹 | ✅ |
| ConfirmActionCard.vue — 写操作确认卡片 | ✅ |
| 6 语言 i18n 集成 | ✅ |
| BottomTabBar 第 6 个 tab（/chat） | ✅ |

---

## Phase C3：Chat API MVP（2026-06-12，已完成）

**后端 chat_sessions/chat_messages DB 表（migration d7e3a9b5c2f8），6 个 REST 端点，mock orchestrator。**

| 功能 | 状态 |
|------|------|
| chat_sessions + chat_messages Alembic migration | ✅ |
| POST/GET /chat/sessions | ✅ |
| POST /chat/sessions/{id}/messages | ✅ |
| GET /chat/sessions/{id}/messages | ✅ |
| Mock Orchestrator（5 场景） | ✅ |
| api/chat.js 前端 API 层 | ✅ |

---

## Phase C4：Chat Tool Registry — 真实只读金融工具（2026-06-18，已完成）

**9 只只读工具接入真实服务，chat_orchestrator async，11/11 pytest PASS，213 modules（含 2 个 intent matcher bug 修复）。**

| 工具 | 数据源 | 状态 |
|------|--------|------|
| resolve_stock_tool | IndustryClassificationService | ✅ |
| get_quote_tool | stock_data_service | ✅ |
| get_kline_summary_tool | stock_data_service | ✅ |
| get_latest_news_tool | news_data_service | ✅ |
| get_industry_hot_tool | industry_hot_stock_service | ✅ |
| get_industry_stocks_tool | industry_hot_stock_service | ✅ |
| get_watchlist_tool | DB（WatchlistItem） | ✅ |
| get_recent_reports_tool | DB（AnalysisReport） | ✅ |
| get_report_detail_tool | DB（AnalysisReport） | ✅ |

**Bug 修复：**
- `_match_watchlist_add` 正则过宽导致"看看我的自选股"误匹配为 add 意图 → 收窄修复
- `_match_recent_report` 漏判"解释我最近一份报告"→ 扩展正则覆盖更多变体

**C5–C9 OpenClaw-inspired 后续规划已完成文档：** `openclaw_inspired_roadmap.md` + `chat_agent_skills.md`

---

## Phase C5：Action Tools + ConfirmationManager 真实执行（2026-06-18，已完成）

**3 类写操作工具从 Mock 升级为真实执行，ConfirmationManager 实现完整生命周期追踪，33/33 pytest PASS，213 modules（零迁移）。**

| 交付物 | 说明 |
|--------|------|
| `chat_confirmation.py` | `make_confirmation()` / `is_expired()` / `is_executable()`，10 分钟超时 |
| `chat_tools/action_tools.py` | `execute_add_to_watchlist` / `execute_create_analysis_run` / `execute_create_compare_selection` |
| `chat_service.update_confirmation_status()` | JSONB mutation + `flag_modified()` |
| `chat_orchestrator.process_confirm` async | 路由 3 类写操作，异常安全 |
| `chat.py` confirm endpoint | 状态/超时守卫，409 幂等拒绝，DB 状态追踪 |
| `ChatConfirmationCard.vue` | executing / failed / expired 三态 |
| `ChatResultCard.vue` | `watchlist_action` / `analysis_run` 新卡片类型 |
| 6 语言 locale | `chat_executing` / `chat_failed` / `chat_expired` |
| `test_c5_confirmation_manager.py` | 11 项单元测试（PASS） |
| `test_c5_action_tools.py` | 11 项单元测试（PASS） |

---

## Phase M51-b：真实报告回归与可读性验收（2026-06-12）

**测试股票：** CN/688146（中船特气）  
**测试结论：**

| 测试维度 | 结论 |
|---------|------|
| 结构合规 | ✅ 综合报告 `一、综合结论卡片` + 单面 `### 摘要结论` 全部到位 |
| 内容质量 | ✅ 7 字段卡片完整；数据缺失时如实标注，无捏造数据 |
| 投资建议规范 | ✅ 无买入/卖出/持有表述 |
| 前端摘要提取 | ✅ zh-CN 命中 `### 摘要结论`；en-US 修复后命中 `### Summary & Conclusions` |
| 可读性评分 | ✅ 综合 4.8/5（结论先行 5/5，信号清晰 5/5，边界说明 5/5） |

**en-US extractSummary 修复（`reportText.js`）：**
新增 4 个 `### Summary…` 变体匹配（`& Conclusions` / `& Conclusion` / `Conclusions` / 广播 `Summary`），解决 LLM 翻译变体导致摘要提取回落到样板文字的问题。  
验证：8/8 用例 PASS，195 modules build ✅。
