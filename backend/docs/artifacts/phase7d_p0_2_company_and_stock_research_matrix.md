# Phase 7D-P0.2 — Company & Stock Research Matrix

| 能力 | 路由/消费者 | Provider | 状态语义 | 失败隔离 | Production fallback |
|---|---|---|---|---|---|
| 公司资料 | Company `/profile` + EOD `profile` | 既有可信 profile；Tushare `stock_basic` 补齐 | fulfilled/unavailable | 不受行情、估值、财务失败影响 | 无网页抓取 fallback |
| 最近交易日行情 | Company `/eod` `quote` | Tushare `daily` | EOD；明确 trade date | 仅 quote 卡片 unavailable | 不使用 Eastmoney |
| 估值与活跃度 | Company `/eod` `valuation` | Tushare `daily_basic` | EOD；字段级 availability | 仅 valuation 卡片 unavailable | 不使用 Eastmoney |
| 财务指标 | Company `/eod` `financial` | Tushare `fina_indicator` | 报告期；字段级 availability | 仅 financial 卡片 unavailable | 不使用网页 Provider |
| 指数对比 | Gateway 可选模块 | Tushare `index_daily` | 仅显式指数映射 | 无映射即不调用 | 不猜测指数 |
| 个股研究 | `stock_eod_research` | Tushare EOD + 已持久化 CNINFO | fulfilled/partial/unavailable/failed | 部分事实可独立展示 | 不使用模型记忆补数字 |
| 官方事件 | stock research 官方事件段 | 已持久化 CNINFO | 有证据才展示 | 无事件不影响 EOD 事实 | 不使用媒体新闻替代 |
| 行业/主题新闻 | source-governance gate | 无 approved source | unavailable | 在实体解析和 Provider 前 fail-closed | 禁止 Tushare news/网页抓取 |

## 路由优先级

1. 行业、市场、主题新闻语义首先 fail-closed。
2. 明确公告/财报披露问题继续进入 CNINFO official routes。
3. 可靠股票实体 + “近期情况、最近表现、估值、财务指标、ROE、盘后、收盘”等进入 `stock_eod_research`。
4. 无可靠实体时返回 unavailable，不猜测股票。

## 前端边界

- profile 始终独立展示。
- EOD 卡片只读取标准化 `modules.*.fields`。
- 标题为“最近交易日盘后数据”，并展示“数据截至 YYYY-MM-DD”“盘后数据可能延迟，不代表实时行情”。
- EOD 整体不可用显示“暂缺已验证的盘后数据”。
- history、EOD、旧 quote/debug、K 线与新闻的错误不会清空 profile。
