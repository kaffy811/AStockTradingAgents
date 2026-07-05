# 06 Frontend Render Contract — Fundamental Data Modules (Phase 2D)

> Version: 2D  
> Freeze date: 2026-07-05  
> Audience: Frontend engineers implementing the Fundamental Data page

---

## 1. Page Layout Suggestions

```
┌─────────────────────────────────────────────────────────────┐
│  Stock Header: name | price | change_pct | ts_code          │
├──────────────┬──────────────────────────────────────────────┤
│  Module      │  Module Content Area                         │
│  Sidebar     │                                              │
│  (by group)  │  [render based on render_type]               │
│              │                                              │
│  概览         │  [stale indicator if stale=true]             │
│  ├ 基础信息   │  [partial warning if partial=true]           │
│  └ 财报核心   │  [empty state if data=null]                  │
│              │                                              │
│  财务分析     │                                              │
│  ├ 估值分位   │                                              │
│  └ ...       │                                              │
│              │                                              │
│  [planned]   │                                              │
│  (locked)    │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

---

## 2. Module Sidebar: Render Order

1. Call `GET /api/v1/modules` once on page load (or stock change).
2. Filter: `display=true` AND `status !== "hidden"` (the API already does this).
3. Sort by `group_seq` ASC, then `seq` ASC within each group.
4. Group items under a group header using `group` string.
5. Planned modules (`status="planned"`) should be rendered as locked/greyed items with a lock icon.
6. Available modules (`status="available"` or `"legacy"`) are clickable.

### Group order

| group_seq | group |
|-----------|-------|
| 1 | 概览 |
| 2 | 财务分析 |
| 3 | 资产负债 |
| 4 | 同行对比 |
| 5 | 股东分红 |
| 6 | 事件观点 |
| 7 | 交易辅助 |
| 8 | AI分析 |

---

## 3. render_type → Component Mapping

| `render_type` | Suggested Component | Notes |
|--------------|--------------------|----|
| `metric_cards` | `MetricCardsPanel` | Grid of key-value cards. Use `field_labels` as labels. |
| `chart_table` | `ChartTablePanel` | Chart on top, sortable table below. Chart type from `chart_type`. |
| `table` | `DataTablePanel` | Table only. Sort by `table_primary_key` by default. |
| `timeline` | `TimelinePanel` | Vertical timeline. Sort by `table_primary_key` DESC. |
| `mixed` | `MixedPanel` | Custom layout mixing summary cards + timeline/table. |
| `ai_card` | `AiAnalysisCard` | Placeholder with "AI 解析" badge. |
| `placeholder` | `PlaceholderCard` | Locked card showing `description` + "敬请期待". |

---

## 4. chart_type → ECharts Option Type

| `chart_type` | ECharts series type | Notes |
|-------------|--------------------|----|
| `line` | `"line"` | Use smooth=true for trend lines |
| `bar` | `"bar"` | Standard bar chart |
| `stacked_bar` | `"bar"` with `stack: "total"` | Multiple series stacked |
| `area` | `"line"` with `areaStyle: {}` | Area chart |
| `pie` | `"pie"` | Pie chart (use for composition) |
| `donut` | `"pie"` with `radius: ["40%","70%"]` | Donut chart |
| `radar` | `"radar"` | Radar/spider chart |
| `timeline` | N/A — use CSS timeline | Not an ECharts type; render as HTML timeline |
| `none` | N/A | No chart; metric cards or table only |

---

## 5. null Value Handling

- **Field value is `null`**: Display `—` (em dash). Never display `"null"` or `"undefined"`.
- **`data` is `null`**: Show `meta.empty_state` (e.g. `"暂无数据"`) centered in the content area.
- **Series is empty array**: Show `meta.empty_state`.
- **Numeric zero**: Display `0` (not `—`). Zero is a valid value for many metrics.
- **`errors` non-empty + `partial=true`**: Data is available but incomplete. Show data with a warning banner listing `errors`.

---

## 6. unit_hints Usage

`unit_hints` is a dict mapping field names to unit strings.

**Display rule**: Append the unit string after the value with a space.

Examples:
```
pe_ttm: 28.5 → display: "28.5 倍"
change_pct: 0.85 → display: "0.85 %"
price: 1688.00 → display: "1688.00 元"
op_cycle: 158.7 → display: "158.7 天"
asset_turnover: 0.52 → display: "0.52 次/年"
```

For percentage fields (unit="%"), consider also rendering a colored bar at `value / 100` width.

When `unit_hints` is empty `{}` (legacy modules or planned), omit unit display.

---

## 7. field_labels Usage

`field_labels` maps field names → Chinese display labels.

**Usage**:
- **Table headers**: Use `field_labels[column_key]` as the `<th>` text.
- **Metric cards**: Use `field_labels[key]` as the card label.
- **Axis labels**: Use `field_labels[key]` for chart axis labels and tooltips.
- **Fallback**: If a field is not in `field_labels`, display the raw field name.

When `field_labels` is empty `{}` (legacy or planned modules), display raw field names.

---

## 8. partial / stale / error Display Rules

### stale = true
- Show a subtle indicator: clock icon + tooltip "数据可能已过期，实时源暂时不可用"
- Still render `data` normally — data is available, just potentially outdated
- Background color: slightly yellowed or a thin amber left-border

### partial = true
- Show a warning banner above the content: "部分数据不完整"
- Show `errors` array items as bullet points in the banner
- Still render all non-null fields normally
- Example: `errors: ["估值字段 pe_ttm/pb 暂不可用（Tushare daily 接口限额）"]`

### data = null (complete failure)
- Show `meta.empty_state` centered: "暂无数据"
- If `errors` is non-empty, show the first error below as a secondary caption
- Do not render any chart or table

### errors non-empty (with data)
- This is the `partial=true` case — handle with warning banner (see above)

---

## 9. Planned Module Placeholder Display

For modules where `status="planned"` or `render_type="placeholder"`:

```
┌─────────────────────────────────────────┐
│  🔒  同行业估值对比                      │
│                                         │
│  （计划中）同行业估值对比               │
│                                         │
│  敬请期待                               │
└─────────────────────────────────────────┘
```

- Dim the sidebar item (50% opacity)
- Show lock icon
- Clicking shows a toast: "该模块正在开发中，敬请期待"
- Do NOT call the API for planned modules

---

## 10. analyst_ratings Disclaimer (IMPORTANT)

The `analyst_ratings` module is derived from company self-disclosed **业绩预告** (performance forecast) filings — it is NOT based on securities analyst buy/sell ratings.

**Mandatory display rules**:
1. The module name must be displayed as **"业绩预告倾向"** or **"业绩预期汇总"** in user-facing copy. Never **"机构评级"** or **"研究报告"**.
2. Always render `data.data_note` field prominently at the bottom of the module.
3. The `data_note` text is: *"本模块基于业绩预告类型映射情绪倾向，非机构买卖评级，不代表投资建议。"*
4. `disclaimer_type="estimated"` — add an "estimated" badge.
5. Do NOT use language like "强烈推荐", "增持", "买入" anywhere near this module.

Same disclaimer rules apply to `announcements` (`disclaimer_type="estimated"`).

---

## 11. AI Module Future Slot

The `ai_analysis` module (seq=27, group=AI分析, group_seq=8) is a future slot for LLM-powered analysis.

- Render as a special card with a sparkle/AI icon
- Display `description`: "AI智能解析（计划中）"
- Show a "Coming Soon" badge
- Do NOT wire to any API call in current phase

---

## 12. Excel Export Button Placement

For modules where `supports_export=true`:

- Place an "导出 Excel" button in the top-right corner of the module content area
- Button should be subtle (secondary/outline style) to not distract from content
- Trigger: collect `data.series` or equivalent array, convert to Excel using a library (e.g. `xlsx`)
- Filename: `{module_key}_{symbol}_{YYYYMMDD}.xlsx`
- Use `field_labels` as Excel column headers

For modules where `supports_export=false` (e.g. `announcements`, `analyst_ratings`):
- Omit the export button entirely

---

## 13. default_limit Usage

`default_limit` specifies the default number of periods/records to show:

| Scenario | Behavior |
|----------|----------|
| `default_limit=1` | Show only the most recent record (e.g. snapshot) |
| `default_limit=8` | Show last 8 periods, with "查看更多" expand option |
| `default_limit=10` | Show last 10 records |
| `default_limit=0` | Placeholder — no data to show |

Implement a "查看更多" / "收起" toggle for modules with `default_limit < total_records`.

---

## 14. data_freshness Badge

Show a subtle freshness badge in the module header:

| `data_freshness` | Badge text | Badge color |
|-----------------|-----------|-------------|
| `realtime` | 实时 | green |
| `daily` | 每日 | blue |
| `quarterly` | 季度 | gray |
| `annual` | 年度 | gray |
| `static` | 静态 | light gray |
