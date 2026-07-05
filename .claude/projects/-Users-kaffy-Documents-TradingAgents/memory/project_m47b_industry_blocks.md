---
name: Phase M47-b 行业热门板块收尾验证完成状态
description: M47-b 综合分析页行业热门板块收尾 — 所有验收项 PASS，195 modules
type: project
---

**完成状态：** M47-b 全部 22 项验收 PASS

## 核心改动

**HomeDashboardPanel.vue**
- 右列上区：删除最近搜索卡片 → 新增行业热门板块（top 6，hot_score 降序）
- `industryListError` prop → error 状态展示 ind_blocks_err
- `fmtScore` 1dp → 2dp（与 IndustryHotBlocksCard 一致）
- 行业名/hot_score/avg_change_pct 缺失均有兜底（`—` / `t('ind_unknown')`）

**ComprehensiveAnalysisView.vue**
- `dashIndustryList` + `dashIndustryListError` ref
- 行业列表按 hot_score desc 排序，top 6 传入 HomeDashboardPanel
- `onDashGoIndustryBlock(ind)` → `/industries?focus=<code>`
- hot stocks 请求 limit 5 → 20（仪表盘 compact 仍 slice(0,5)）

**IndustryHotBlocksCard.vue**
- `data-industry-code` 属性加入行按钮（供 focus DOM 查询）

**IndustryHotView.vue**
- 导入 `useRoute`、`watch`、`nextTick`
- `watch([industries.length, route.query.focus])` → 选中行业 + scrollIntoView + 高亮 1.8s
- CSS `:global(.industry-focus-highlight)` outline + background

## i18n
- zh-CN/en-US 新增 `ind_unknown` key
- zh-TW/ja-JP/ko-KR/es-ES 补齐 `ind_blocks_*`（7 个 key）+ `ind_unknown`

## 行业热股扩容
- IndustryHotView `HOT_LIMIT = 20`（M19 已有）
- ComprehensiveAnalysisView `limit: 20`（M47 新改）
- 仪表盘 compact 仍 `slice(0,5)`，行业页全量展示
- 数据不足 20 时前端展示实际数量，不伪造

## 静态验证
- npm run build: ✅ 195 modules
- python compileall: ✅ 0 errors
- alembic current: ✅ c5e9f12a3b87 (head)
- 零新依赖，零 migration

**Why:** M47 实现了行业热门板块替换，M47-b 补齐 fallback/error/i18n/focus 链路，形成完整可交付功能。
**How to apply:** 下阶段可继续行业热股数据扩充（申万 L3）或行业详情页功能。
