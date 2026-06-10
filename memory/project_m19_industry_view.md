---
name: Phase M19 行业研究页 App 化完成状态
description: IndustryOverviewPanel/IndustryHotStats/IndustryToolbar/IndustryStockCard 新增，IndustryHotView 全面重排，168 modules，M19-1~M19-8 PASS
type: project
---

Phase M19 完成，build 168 modules (+8 vs M18 的 160)，compileall 通过。

**新增文件：**
- `frontend/src/components/IndustryOverviewPanel.vue` — 行业概览（名称/code/trade_date/score_version/item数量/data_quality.message/loading/error/empty）
- `frontend/src/components/IndustryHotStats.vue` — 4 统计卡（总数/上涨/下跌/平均 Hot Score），change_pct/hot_score null safe
- `frontend/src/components/IndustryToolbar.vue` — 行业下拉/涨跌筛选/数据源动态筛选/排序/刷新；筛选不触发 API
- `frontend/src/components/IndustryStockCard.vue` — 排名 badge/股票身份/涨跌幅/成交额/data_source/4操作按钮/加自选5态状态机

**修改文件：**
- `frontend/src/views/IndustryHotView.vue` — 全面重排，移除 table+card 双 markup，统一 IndustryStockCard

**关键实现：**
- filteredItems computed：change/dataSource 过滤 + 6 种排序（null safe，不 mutate 原数组）
- availableDataSources computed：从 hotData.items 动态提取 Set
- 切换行业：重置 filters/sortKey/'all'/'rank' + 清空 watchlistStatus
- 快速搜索：从 goAnalyze 改为 goDetail（/stocks/CN/{symbol}）

**Why:** 统一 App 化风格，与 M16/M17/M18 一致；筛选纯前端，减少 API 请求  
**How to apply:** 后续如需扩展行业功能（如 HK 行业），只需在 IndustryToolbar market 下拉增加选项并在 IndustryHotView 传 MARKET prop；filteredItems 逻辑不需改动
