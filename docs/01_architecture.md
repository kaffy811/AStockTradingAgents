# 01_architecture.md — Stock Fundamental Service 系统架构设计

> 版本：v1.0  
> 日期：2026-07-04  
> 范围：后端服务架构 + 前端接入方式

---

## 一、系统定位

Stock Fundamental Service（股票基本面数据服务）是 TradingAgents 平台的第二条产品线，与现有 Chat Copilot 完全正交、互不干扰。

**核心目标**：
- 以结构化卡片展示 A 股 / 港股 / 美股的基本面数据（32 个确定性模块 + 1 个 AI 模块）
- 主数据源：Tushare Pro（付费 API，每分钟 500 积分限额）
- 备用数据源：AkShare（免费，通过 `ENABLE_AKSHARE=true` 开启，默认关闭）
- 绝对不调用 aicaibao.com 等 scraping 目标

---

## 二、分层架构

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + ECharts)                             │
│  StockFundamentalView — 32+1 懒加载模块卡片             │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP GET /api/v1/stocks/{market}/{symbol}/fundamentals/…
┌──────────────────▼──────────────────────────────────────┐
│  FastAPI Router  app/routers/fundamentals.py            │
│  - GET /snapshot            (聚合快照，<2s)             │
│  - GET /modules/{module}    (单模块按需加载)             │
│  - GET /modules             (全模块声明列表)             │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  Aggregator  app/aggregator/                            │
│  - FundamentalsAggregator.fetch(symbol, modules=[...])  │
│  - 并发 asyncio.gather，独立失败，DataEnvelope 包装      │
│  - envelope: {ok, data, reason, stale, partial_errors,  │
│               cached_at}                                │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│  Tools  app/tools/fundamental/                          │
│  每个模块一个 Tool 类，实现 fetch() → raw dict           │
│  tool 不做缓存，不做包装，只返回原始数据                  │
└──────────┬───────────────────────┬──────────────────────┘
           │ primary               │ fallback (ENABLE_AKSHARE=true)
┌──────────▼──────┐       ┌────────▼──────────────────────┐
│  Tushare Client  │       │  AkShare Client               │
│  app/datasource/ │       │  app/datasource/              │
│  tushare_client  │       │  akshare_client               │
│  - 令牌桶速率限制 │       │  - 仅在 ENABLE_AKSHARE=true   │
│  - 500 积分/分钟  │       │    时导入/调用                │
│  - asyncio.Lock  │       │  - 调用失败不影响 Tushare 路径│
└──────────┬───────┘       └───────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│  Redis Cache  (已有 cache_service.py)                   │
│  - key: fs:{symbol}:{module}:{market}                   │
│  - TTL: 按模块类型（行情 60s，财报 4h，年报 24h）        │
│  - stale-while-revalidate：TTL 过期后仍返回旧数据        │
└─────────────────────────────────────────────────────────┘
```

---

## 三、目录结构（Phase 1 新增）

```
backend/app/
├── datasource/                     ← NEW Phase 1
│   ├── __init__.py
│   ├── tushare_client.py           ← Tushare Pro client + 速率限制
│   └── akshare_client.py           ← AkShare 封装（ENABLE_AKSHARE guard）
├── aggregator/                     ← NEW Phase 1
│   ├── __init__.py
│   └── envelope.py                 ← DataEnvelope 类型定义 + 构建函数
├── tools/
│   └── fundamental/                ← NEW Phase 1（Phase 1 实现前 5 个）
│       ├── __init__.py
│       ├── base.py                 ← BaseFundamentalTool ABC
│       ├── quote_snapshot.py       ← M01 实时行情快照
│       ├── financial_summary.py    ← M02 财务指标摘要
│       ├── income_statement.py     ← M03 利润表营收利润趋势
│       ├── balance_sheet.py        ← M04 资产负债表关键指标
│       └── cashflow_health.py      ← M05 现金流量健康度
└── routers/
    └── fundamentals.py             ← NEW Phase 1（3 个端点）
```

---

## 四、速率限制设计

Tushare Pro 基础账户：每分钟 500 积分，单次 API 调用 = 1 积分（普通接口）。

采用**令牌桶**（Token Bucket）算法，使用 `asyncio.Semaphore` 实现：

```
每 60s 补充 500 个令牌
并发 acquire → 不超过 500 次/分钟
超出等待（不丢弃），最大等待 10s（超时返回 503）
```

实现位置：`app/datasource/tushare_client.py` → `TushareRateLimiter`

---

## 五、缓存策略

| 数据类型          | 模块                       | TTL     | stale-TTL |
|-----------------|---------------------------|---------|-----------|
| 实时行情          | M01 quote_snapshot         | 60s     | 300s      |
| 日频基础指标       | M02 financial_summary      | 4h      | 24h       |
| 季报财务数据       | M03/M04/M05                | 4h      | 48h       |
| 年度汇总          | M06+ valuation             | 4h      | 48h       |
| 行业排名          | M11-M15 industry ranking   | 1h      | 6h        |

cache key 格式：`fs:{market}:{symbol}:{module}:{version}`

---

## 六、ENABLE_AKSHARE 开关

```python
# .env
ENABLE_AKSHARE=false       # 默认，仅 Tushare
ENABLE_AKSHARE=true        # 开启 AkShare 作为 fallback

# 行为：
# ENABLE_AKSHARE=false → AkShare client 从不被导入，ENABLE_AKSHARE=false 必须让服务正常运行
# ENABLE_AKSHARE=true  → Tushare 失败后自动尝试 AkShare，写入相同 cache key 但 stale=True
```

---

## 七、API 响应规范

所有 `/fundamentals/` 端点均返回 `DataEnvelope`：

```json
{
  "ok": true,
  "data": { ... },
  "reason": null,
  "stale": false,
  "partial_errors": [],
  "cached_at": "2026-07-04T10:23:45+08:00"
}
```

失败场景：
- `ok=false` + `reason=<描述>` + `data=null`（完全失败）
- `ok=true` + `partial_errors=[...]`（部分字段失败，其他字段可用）
- `ok=true` + `stale=true`（返回缓存旧数据，源不可用）

---

## 八、与 Chat Copilot 的关系

两个系统**完全正交**，共用：
- FastAPI 应用实例（`app/main.py` 注册不同 router prefix）
- Redis 缓存基础设施（不同 key 命名空间）
- PostgreSQL 数据库（不同表，无外键约束）
- 认证中间件（相同 JWT）

不共用：
- 工具注册表（Chat Tools vs Fundamental Tools 完全独立）
- LLM 调用（Fundamental 23 个模块全部无 LLM；AI 模块走独立 `app/agent/ai_analyst.py`）
- 测试（独立目录 `tests/fundamental/`）

---

## 九、扩展路径

| Phase | 主要工作                                    |
|-------|---------------------------------------------|
| 1     | 基础设施 + 5 个核心工具 + 3 个端点          |
| 2     | 剩余 18 个确定性模块 + Excel 导出           |
| 3     | AI 模块（`app/agent/ai_analyst.py`）        |
| 4     | Vue3 前端（StockFundamentalView + ECharts） |
| 5     | ETL 管道（财报入库 + SQL 行业排名）          |
