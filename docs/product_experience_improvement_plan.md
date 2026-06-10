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
