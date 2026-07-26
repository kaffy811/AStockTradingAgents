# Manual E2E Checklist — TradingAgents

**Purpose:** Regression checklist for QA before each release. Run in a browser with backend running.

---

## 0. Prerequisites

- Backend running on `http://localhost:8000` (or staging URL)
- Frontend running on `http://localhost:3000` (`npm run dev`)
- At least one valid user token in localStorage (`ta_token`)
- Tushare token configured (or acknowledged to be absent for partial mode)

---

## 1. Stock Detail Page Renders

| # | Action | Expected |
|---|--------|----------|
| 1.1 | Navigate to `/stocks/CN/600519` | Page loads, name shows "贵州茅台" |
| 1.2 | Navigate to `/stocks/CN/000725` | Page loads, name shows "京东方" |
| 1.3 | Navigate to `/stocks/CN/600186` | Page loads, name shows "荷花莲" or code |
| 1.4 | Check dashboard panel | Quote price or "—" shown, watchlist button present |
| 1.5 | K-line chart area | Chart section renders (may be loading) |

---

## 2. Five Tabs Exist and Switch

| # | Action | Expected |
|---|--------|----------|
| 2.1 | Check tab bar on stock detail | 5 tabs: 技术面解读 / 相关新闻 / 同行业对比 / 公司 / 历史报告 |
| 2.2 | Click 相关新闻 tab | News timeline renders or empty state shown |
| 2.3 | Click 同行业对比 tab | Peer list or empty state shown |
| 2.4 | Click 历史报告 tab | Research panel + history list renders |
| 2.5 | Click 技术面解读 tab | Insight card renders (may be loading) |

---

## 3. Company Tab Lazy Loads

| # | Action | Expected |
|---|--------|----------|
| 3.1 | Load stock detail page, do NOT click 公司 tab | CompanyFundamentalsPanel not in DOM (lazy not triggered) |
| 3.2 | Click 公司 tab | Loading indicator appears briefly, then financial panels render |
| 3.3 | Switch away and back to 公司 | Data already loaded — no re-fetch flash |

---

## 4. DataSourceBanner / No Token State

| # | Action | Expected |
|---|--------|----------|
| 4.1 | Remove TUSHARE_TOKEN from backend env, restart | DataSourceBanner or 503 note shows in Company Tab |
| 4.2 | Token absent: basic panels | Quote and news may still load (fallback sources) |
| 4.3 | Token present | Banner hidden or not shown |

---

## 5. Left Nav Exists and Scrolls

| # | Action | Expected |
|---|--------|----------|
| 5.1 | Desktop (≥641px): check AppHeader | Navigation links visible: 分析/历史/自选/行业/Chat/我的 |
| 5.2 | Mobile (≤640px): check bottom bar | BottomTabBar visible, AppHeader nav hidden |
| 5.3 | Mobile: tab bar scrolls horizontally | All 6 tabs accessible via swipe |

---

## 6. P0 Panels Show or Show Reason

| # | Action | Expected |
|---|--------|----------|
| 6.1 | Stock dashboard panel | Shows name + quote OR skeleton loading state |
| 6.2 | Technical chart panel | K-line chart renders after data loads |
| 6.3 | Company Tab — snapshot panel | Data table or "503 Tushare unavailable" message |
| 6.4 | Empty watchlist | EmptyState component shown (not blank) |
| 6.5 | No industry data | EmptyState with icon shown in 同行业对比 tab |

---

## 7. AI Strip — Refresh Button

| # | Action | Expected |
|---|--------|----------|
| 7.1 | Navigate to `/` (综合分析页) | AI analysis form visible |
| 7.2 | Submit analysis for 600519 | Progress/streaming visible |
| 7.3 | Report renders | Markdown content displayed |
| 7.4 | Click refresh / re-analyze | New analysis triggered |

---

## 8. Export Works

| # | Action | Expected |
|---|--------|----------|
| 8.1 | Open a completed report | Export buttons visible |
| 8.2 | Click "导出 Markdown" | .md file downloads |
| 8.3 | Click "导出 Excel" (if present) | .xlsx file downloads |
| 8.4 | Click "打印" | Print dialog opens with formatted content |

---

## 9. Mobile Viewport

| # | Action | Expected |
|---|--------|----------|
| 9.1 | Set viewport to 375px width | Layout does not overflow horizontally |
| 9.2 | Stock detail page | Tab bar scrolls horizontally without wrapping |
| 9.3 | Forms (analysis page) | Inputs stack vertically, readable |
| 9.4 | BottomTabBar | Visible at bottom, does not overlap content |

---

## 10. Stock Switch Clears Old Data

| # | Action | Expected |
|---|--------|----------|
| 10.1 | Load `/stocks/CN/600519` | Page shows 贵州茅台 data |
| 10.2 | Navigate to `/stocks/CN/000725` | Previous stock name clears, new name loads |
| 10.3 | Company tab (if visited before) | `companyTabVisited` resets — placeholder shown until tab clicked |
| 10.4 | K-line chart | Chart re-draws for new symbol |

---

## Sign-off

| Tester | Date | Result |
|--------|------|--------|
| | | PASS / FAIL |
