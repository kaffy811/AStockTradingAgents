# TradingAgents Chat Copilot — Tool Registry 规范

> 版本：Phase C9 完成  
> 日期：2026-06-18  
> 状态：C4 ✅ 9 只只读工具；C5 ✅ 3 只写操作工具；C6 ✅ 6 只 Skills；C7 ✅ Planner；C8 ✅ 审计字段；**C9 ✅ SkillSpec required_tools 字段在 SkillRegistry 初始化时与 ToolRegistry 交叉校验，缺失工具 → skill available=False**

---

## C4/C5 实现状态（2026-06-18）

| 工具 | 文件 | 复用服务 | 状态 |
|------|------|---------|------|
| resolve_stock_tool | chat_tools/stock_tools.py | IndustryClassificationService | ✅ 真实服务（C4） |
| get_quote_tool | chat_tools/stock_tools.py | stock_data_service.get_quote_optional | ✅ 真实服务（C4） |
| get_kline_summary_tool | chat_tools/stock_tools.py | stock_data_service.get_kline_for_agent | ✅ 真实服务（C4） |
| get_latest_news_tool | chat_tools/stock_tools.py | news_data_service.get_stock_news | ✅ 真实服务（C4） |
| get_industry_hot_tool | chat_tools/industry_tools.py | industry_hot_stock_service | ✅ 真实服务（C4） |
| get_industry_stocks_tool | chat_tools/industry_tools.py | industry_hot_stock_service | ✅ 真实服务（C4） |
| get_watchlist_tool | chat_tools/watchlist_tools.py | DB（WatchlistItem） | ✅ 真实服务（C4） |
| get_recent_reports_tool | chat_tools/report_tools.py | DB（AnalysisReport） | ✅ 真实服务（C4） |
| get_report_detail_tool | chat_tools/report_tools.py | DB（AnalysisReport） | ✅ 真实服务（C4） |
| add_to_watchlist_tool | chat_tools/action_tools.py | DB（WatchlistItem）savepoint 幂等 | ✅ 真实执行（C5） |
| create_analysis_run_tool | chat_tools/action_tools.py | get_run_registry + RealtimeAnalysisRunner | ✅ 真实执行（C5） |
| create_compare_selection_tool | chat_tools/action_tools.py | 纯 URL 构建，无 DB | ✅ 真实执行（C5） |

### C5 写操作工具关键实现细节

- **`execute_add_to_watchlist`**：先 SELECT 幂等检查，新增时用 `async with db.begin_nested()` savepoint 隔离 `IntegrityError`（并发竞争不破坏外层事务）
- **`execute_create_analysis_run`**：`get_llm_client()` + `get_run_registry().create_run()` + `asyncio.create_task(_background())` 异步后台执行
- **`execute_create_compare_selection`**：同步函数，拼接 `/compare?stocks=MARKET:SYMBOL` URL，无 DB 写入
- **`ConfirmationManager`**：`make_confirmation()` 生成 10 分钟到期的 pending dict，存入 `ChatMessage.confirmation` JSONB；Router confirm 端点执行 pending/expiry/idempotency 三重守卫

---

## 1. 设计原则

1. **最小权限**：工具只暴露当前用户有权访问的数据，不跨用户访问。
2. **只读优先**：能用只读工具完成的任务，不使用写操作工具。
3. **写操作必确认**：所有 `write_user_data` 和 `long_running` 工具必须经过 ConfirmationManager。
4. **现有服务复用**：工具内部调用现有 Service 层，不重复实现业务逻辑。
5. **错误透明**：工具返回结构化错误，不隐藏数据源失败（如 AkShare 超时）。
6. **参数校验**：工具入参必须经过 Pydantic 校验，拒绝非法参数。

---

## 2. 权限级别说明

| 级别 | 说明 | 是否需要确认 |
|------|------|------------|
| `read_only` | 只读查询，不修改任何状态 | 否 |
| `write_user_data` | 修改用户个人数据（自选股、对比列表等） | 是 |
| `long_running` | 触发异步长任务（如分析报告生成，30~120s） | 是 |
| `sensitive` | 高危操作（交易、系统配置等），MVP 永久禁用 | 禁用 |

---

## 3. Read-only Tools（只读工具）

---

### 3.1 `resolve_stock_tool`

**描述：** 将用户输入的股票名称、拼音缩写或代码解析为标准 `{market, symbol, name}` 结构。是所有其他股票工具的前置工具。

```yaml
tool_name: resolve_stock_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  query: string       # 用户输入（"中船特气" / "688146" / "maotai" / "茅台"）
  market: string      # 可选，CN 或 HK（不提供则自动判断）

output_schema:
  found: boolean
  market: string      # CN / HK
  symbol: string      # 标准代码（6位，补零）
  name: string | null # 股票中文名
  candidates: list    # 多个匹配时返回候选列表（最多5个）
  error: string | null

error_handling:
  - 未找到：返回 found=false，candidates=[]，建议用户确认代码
  - 多匹配：返回候选列表，请用户选择
  - 数据库不可用：返回 error 说明

existing_service_mapping:
  - GET /stocks/search?market={market}&q={query}
  - IndustryClassificationService.search_stocks()
```

---

### 3.2 `get_quote_tool`

**描述：** 获取股票当日实时行情（价格、涨跌幅、成交量、成交额）。

```yaml
tool_name: get_quote_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string   # CN / HK
  symbol: string   # 标准6位代码

output_schema:
  market: string
  symbol: string
  name: string | null
  price: float | null          # 当前价格
  change_pct: float | null     # 涨跌幅（%）
  change_amount: float | null  # 涨跌额
  volume: float | null         # 成交量
  amount: float | null         # 成交额（元）
  high: float | null
  low: float | null
  open: float | null
  prev_close: float | null
  timestamp: string | null     # 行情时间
  cached: boolean
  stale: boolean
  error: string | null

error_handling:
  - AkShare 超时/失败：返回 stale=true 或 error 说明
  - 非交易日：返回最近交易日收盘价（stale=true）

existing_service_mapping:
  - GET /stocks/{market}/{symbol}/quote
  - StockDataService.get_quote()
```

---

### 3.3 `get_kline_summary_tool`

**描述：** 获取股票 K 线摘要（均线位置、近期涨幅、成交量趋势），而非完整 K 线数据。用于 Chat 场景的快速技术面判断，不用于渲染图表。

```yaml
tool_name: get_kline_summary_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string
  symbol: string
  period: string   # daily（默认）/ weekly / monthly
  count: int       # 最近N根K线，默认60，最大120

output_schema:
  market: string
  symbol: string
  period: string
  ma5: float | null
  ma10: float | null
  ma20: float | null
  ma60: float | null
  current_price: float | null
  price_vs_ma20_pct: float | null     # 价格偏离MA20百分比
  change_20d_pct: float | null        # 近20日涨跌幅
  change_60d_pct: float | null        # 近60日涨跌幅
  avg_volume_5d: float | null         # 近5日均量
  trend_signal: string                # bullish / bearish / neutral / insufficient_data
  data_bars: int                      # 实际数据根数
  error: string | null

error_handling:
  - 数据不足（< 20根）：trend_signal="insufficient_data"，返回可用字段
  - AkShare 超时：返回 error 说明

existing_service_mapping:
  - GET /stocks/{market}/{symbol}/kline
  - StockDataService.get_kline() + TechnicalIndicatorService.compute()
```

---

### 3.4 `get_fundamentals_tool`

**描述：** 获取股票基本面数据（估值、盈利能力、成长能力、财务安全、主营业务）。

```yaml
tool_name: get_fundamentals_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string
  symbol: string

output_schema:
  market: string
  symbol: string
  name: string | null
  industry: string | null
  business_summary: string | null
  valuation:
    pe: float | null
    pb: float | null
    market_cap: float | null
    market_cap_unit: string | null
  profitability:
    roe: float | null
    gross_margin: float | null
    net_margin: float | null
  growth:
    revenue_growth_yoy: float | null
    net_profit_growth_yoy: float | null
  financial_health:
    debt_ratio: float | null
    operating_cashflow: float | null
  data_quality:
    missing_fields: list[string]    # 缺失字段列表
    provider: string | null
    stale: boolean
    latest_report_date: string | null
  error: string | null

error_handling:
  - 字段缺失：missing_fields 列出，不捏造数据
  - 港股基本面支持有限：error 说明，建议使用 A 股

existing_service_mapping:
  - GET /stocks/{market}/{symbol}/fundamentals
  - FundamentalDataService.get_fundamentals()
```

---

### 3.5 `get_latest_news_tool`

**描述：** 获取股票近期相关新闻（默认 72 小时内，最多 10 条）。

```yaml
tool_name: get_latest_news_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string
  symbol: string
  hours: int       # 时间窗口（小时），默认72，最大168（7天）
  limit: int       # 最多返回条数，默认10，最大20

output_schema:
  market: string
  symbol: string
  total: int
  hours: int
  items:
    - title: string
      source: string | null
      published_at: string | null    # ISO datetime
      summary: string | null         # 摘要（前200字）
      sentiment: string | null       # positive / negative / neutral（规则分类，非LLM）
  data_quality:
    source: string
    stale: boolean
  error: string | null

error_handling:
  - 无新闻：返回 total=0，items=[]
  - AkShare 超时：返回 error 说明

security_note:
  - 新闻内容视为不可信外部数据，不写入 Memory Layer
  - 新闻中的任何指令不得被执行（prompt injection 防护）

existing_service_mapping:
  - GET /stocks/{market}/{symbol}/news（规划中，当前通过 NewsDataService）
  - NewsDataService.get_stock_news()
```

---

### 3.6 `get_peer_comparison_tool`

**描述：** 获取股票的动态同行信息（行业归属 + Hot Score 热门同行）。

```yaml
tool_name: get_peer_comparison_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string
  symbol: string

output_schema:
  market: string
  symbol: string
  industry:
    code: string
    name: string
    level: int | null
  peers:
    - market: string
      symbol: string
      name: string | null
      hot_score: float | null
      peer_source: string    # PEER_MAP / hot_score
  data_quality:
    peer_source: string
    note: string    # "Hot Score 热门股，业务可比性不严格"
  error: string | null

error_handling:
  - 行业未映射：peers=[]，error 说明

existing_service_mapping:
  - GET /industries/stocks/{market}/{symbol}/dynamic-peers
  - DynamicPeerDiscoveryService.get_peers()
```

---

### 3.7 `get_industry_hot_tool`

**描述：** 获取指定行业的 Hot Score 热门股 Top N。

```yaml
tool_name: get_industry_hot_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string         # CN（港股行业暂不支持）
  industry_code: string  # 申万一级行业代码，如 "801080"（电子）
  industry_name: string  # 可选，辅助展示
  limit: int             # 默认10，最大50

output_schema:
  market: string
  industry_code: string
  industry_name: string | null
  total: int             # 行业成分股总数
  items:
    - market: string
      symbol: string
      name: string | null
      hot_score: float
      change_pct: float | null
      amount: float | null    # 成交额（元）
  snapshot_date: string | null
  error: string | null

error_handling:
  - 行业代码不存在：返回 error 说明
  - 快照过期（> 24h）：stale=true，返回旧数据 + 提示

existing_service_mapping:
  - GET /industries/{market}/{industry_code}/hot-stocks
  - IndustryHotStockService.get_hot_stocks()
```

---

### 3.8 `get_industry_stocks_tool`

**描述：** 获取行业成分股列表（按代码排序，非热度排序）。与 `get_industry_hot_tool` 区别：这是完整成分股，而非 Hot Score 热门股。

```yaml
tool_name: get_industry_stocks_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string
  industry_code: string
  limit: int    # 默认20，最大100

output_schema:
  market: string
  industry_code: string
  industry_name: string | null
  total: int
  items:
    - market: string
      symbol: string
      name: string | null
  error: string | null

existing_service_mapping:
  - GET /industries/{market}/{industry_code}/constituents
  - IndustryClassificationService.get_constituents()
```

---

### 3.9 `get_recent_reports_tool`

**描述：** 获取当前用户的历史报告列表，支持按股票、范围、日期筛选。

```yaml
tool_name: get_recent_reports_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  market: string | null         # 筛选市场
  symbol: string | null         # 筛选股票
  analysis_scope: string | null # 筛选范围（comprehensive / technical_only 等）
  limit: int                    # 默认5，最大20

output_schema:
  total: int
  items:
    - id: string             # report_id
      market: string
      symbol: string
      stock_name: string | null
      analysis_scope: string
      created_at: string
      summary_snippet: string | null   # 前200字摘要
  error: string | null

security_note:
  - 严格限定当前用户数据，user_id 从 JWT 读取

existing_service_mapping:
  - GET /reports/?market=&symbol=&limit=
```

---

### 3.10 `get_report_detail_tool`

**描述：** 获取单份报告的完整内容（Markdown 全文 + 各 Agent 子报告）。

```yaml
tool_name: get_report_detail_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  report_id: string    # UUID

output_schema:
  id: string
  market: string
  symbol: string
  stock_name: string | null
  analysis_scope: string
  created_at: string
  report_md: string              # 完整 Markdown 报告
  sections: dict | null          # 各 Agent 子报告
  warnings: list[string] | null  # 数据质量警告
  agents: list[string] | null    # 参与 Agent 列表
  error: string | null

security_note:
  - 严格限定当前用户报告，他人 report_id 返回 error

existing_service_mapping:
  - GET /reports/{id}
```

---

### 3.11 `get_watchlist_tool`

**描述：** 获取当前用户自选股列表（带实时行情和最近报告）。

```yaml
tool_name: get_watchlist_tool
permission_level: read_only
requires_confirmation: false

input_schema:
  enriched: boolean    # 是否携带行情和最近报告，默认 true

output_schema:
  total: int
  items:
    - id: string
      market: string
      symbol: string
      name: string | null
      note: string | null
      latest_price: float | null
      change_pct: float | null
      latest_report_id: string | null
      latest_report_scope: string | null
  error: string | null

existing_service_mapping:
  - GET /watchlist/enriched（enriched=true）
  - GET /watchlist/（enriched=false）
```

---

## 4. Action Tools（写操作工具）

---

### 4.1 `create_analysis_run_tool`

**描述：** 为指定股票创建一次分析运行（生成报告）。这是最重要的 long_running 工具，需用户确认。

```yaml
tool_name: create_analysis_run_tool
permission_level: long_running
requires_confirmation: true
confirmation_message: "我将为 {stock_name}（{market}/{symbol}）生成 {scope} 分析报告（输出语言：{language}），通常需要 30~120 秒。是否确认？"

input_schema:
  market: string
  symbol: string
  stock_name: string | null         # 展示用
  scope: string                     # comprehensive / technical_only / fundamental_only / news_only / peer_only
  output_language: string           # zh-CN（默认）/ en-US / ja-JP 等，复用用户语言偏好
  engine: string | null             # 可选，custom_coordinator / langgraph，默认跟随 env 配置

output_schema:
  run_id: string
  status: string                    # pending / running / completed / failed
  report_id: string | null          # 完成后可用
  summary_snippet: string | null    # 综合结论卡片摘要（完成后）
  report_url: string | null         # /history/{report_id}
  error: string | null

progress_events:
  - run_started
  - agent_started (agent_name)
  - agent_completed (agent_name)
  - synthesis_started
  - run_completed
  - run_failed

error_handling:
  - LLM 不可用：error 说明，建议稍后重试
  - 数据源失败：警告说明，报告仍可生成（含数据不足说明）
  - 超时（> 180s）：自动标记 failed

existing_service_mapping:
  - POST /analysis/runs
  - GET /analysis/runs/{id}/events（SSE 进度）
  - GET /analysis/runs/{id}（状态查询）
```

---

### 4.2 `add_to_watchlist_tool`

**描述：** 将股票加入当前用户的自选股。

```yaml
tool_name: add_to_watchlist_tool
permission_level: write_user_data
requires_confirmation: true
confirmation_message: "我将把 {stock_name}（{market}/{symbol}）加入你的自选股，是否确认？"

input_schema:
  market: string
  symbol: string
  stock_name: string | null    # 展示用，存入 name 字段
  note: string | null          # 可选备注

output_schema:
  success: boolean
  watchlist_item_id: string | null
  already_exists: boolean      # true 表示已在自选股中（不重复添加）
  watchlist_url: string        # /watchlist
  error: string | null

error_handling:
  - 重复添加（409）：already_exists=true，友好提示
  - 认证失败：error 说明

existing_service_mapping:
  - POST /watchlist/
```

---

### 4.3 `remove_from_watchlist_tool`

**描述：** 将股票从当前用户自选股中移除。

```yaml
tool_name: remove_from_watchlist_tool
permission_level: write_user_data
requires_confirmation: true
confirmation_message: "我将把 {stock_name}（{market}/{symbol}）从你的自选股中移除，是否确认？"

input_schema:
  watchlist_item_id: string    # 需先通过 get_watchlist_tool 获取
  stock_name: string | null    # 展示用

output_schema:
  success: boolean
  error: string | null

error_handling:
  - 不存在（404）：返回 error，建议重新获取自选股列表

existing_service_mapping:
  - DELETE /watchlist/{id}
```

---

### 4.4 `create_compare_selection_tool`

**描述：** 设置多股对比选择，并返回对比页跳转 URL。不修改数据库，仅构造 URL 参数。

```yaml
tool_name: create_compare_selection_tool
permission_level: write_user_data
requires_confirmation: true
confirmation_message: "我将打开股票对比页，对比 {stock_list_description}，是否确认？"

input_schema:
  stocks:              # 2~4 只股票
    - market: string
      symbol: string
      name: string | null

output_schema:
  success: boolean
  compare_url: string   # /compare?stocks=CN:600519,CN:000858
  stocks_count: int
  error: string | null

validation:
  - 最少2只，最多4只
  - 不支持混合市场（CN + HK，数据对比意义有限）

existing_service_mapping:
  - 前端路由 /compare?stocks= 参数（不调用后端接口）
```

---

### 4.5 `save_chat_note_tool`

**描述：** 将用户在对话中的关键观点保存为自选股备注。

```yaml
tool_name: save_chat_note_tool
permission_level: write_user_data
requires_confirmation: true
confirmation_message: "我将更新 {stock_name} 的自选股备注为："{note}"，是否确认？"

input_schema:
  watchlist_item_id: string
  note: string    # 最大200字

output_schema:
  success: boolean
  error: string | null

security_note:
  - 备注内容经过长度和字符校验（禁止 HTML / script 标签）

existing_service_mapping:
  - PATCH /watchlist/{id}（body: { note: "..." }）
```

---

### 4.6 `update_report_language_tool`

**描述：** 更新用户的 output_language 偏好（后续生成报告默认使用该语言）。这是写入 session 记忆的轻量操作，不修改数据库，仅更新 Memory Layer。

```yaml
tool_name: update_report_language_tool
permission_level: write_user_data
requires_confirmation: false    # 轻量偏好更新，无需确认

input_schema:
  output_language: string    # zh-CN / zh-TW / en-US / ja-JP / ko-KR / es-ES

output_schema:
  success: boolean
  message: string    # "后续生成报告将使用 English 输出"
  error: string | null

existing_service_mapping:
  - Memory Layer（session 结构化记忆，不调用后端接口）
```

---

## 5. 禁用工具（永久禁用）

以下工具在设计阶段列出但**永久禁用**，不在任何阶段实现：

| 工具名 | 禁用原因 |
|--------|---------|
| `execute_trade_tool` | 不支持真实交易 |
| `set_price_alert_tool` | 超出 MVP 范围 |
| `generate_price_target_tool` | 禁止目标价预测 |
| `generate_buy_sell_signal_tool` | 禁止投资建议 |
| `access_system_config_tool` | 禁止 Agent 修改系统配置 |
| `execute_shell_tool` | 禁止 Agent 执行 shell 命令 |

---

## 6. 工具调用错误码规范

| 错误码 | 含义 | Agent 处理策略 |
|--------|------|--------------|
| `tool_not_found` | 工具不存在 | 向用户说明，建议使用其他描述 |
| `param_validation_error` | 参数不合法 | 向用户说明缺少哪个参数 |
| `data_source_timeout` | 数据源超时 | 向用户说明，建议稍后重试 |
| `data_source_empty` | 数据源返回空 | 如实说明数据不可用 |
| `auth_error` | 认证失败 | 提示用户重新登录 |
| `permission_denied` | 权限不足（访问他人数据） | 返回友好错误 |
| `tool_disabled` | 工具已禁用（sensitive 级别） | 说明功能不可用 |
| `confirmation_required` | 写操作需确认 | 自动进入确认流程 |
| `confirmation_timeout` | 确认超时（5分钟） | 说明操作已取消 |
| `already_exists` | 重复操作（如已在自选股） | 友好提示，无需再次确认 |

---

## 7. 工具调用审计日志格式

每次工具调用生成一条审计日志（JSON Lines 格式，写入后端日志）：

```json
{
  "ts": "2026-06-12T10:30:00+08:00",
  "session_id": "sess_abc123",
  "user_id": "usr_xyz",
  "tool_name": "add_to_watchlist_tool",
  "tool_params": { "market": "CN", "symbol": "688146", "stock_name": "中船特气" },
  "permission_level": "write_user_data",
  "confirmation_required": true,
  "confirmed_at": "2026-06-12T10:30:05+08:00",
  "result_status": "success",
  "error": null,
  "duration_ms": 250
}
```
