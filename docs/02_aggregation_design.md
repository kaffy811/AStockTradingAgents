# 02_aggregation_design.md — 聚合层与 32+1 模块设计

> 版本：v1.0  
> 日期：2026-07-04

---

## 一、模块全表（32+1）

| ID   | 模块名                  | 英文 Key               | 数据源（优先）  | 是否 LLM | Phase |
|------|------------------------|------------------------|---------------|---------|-------|
| M01  | 实时行情快照            | quote_snapshot          | Tushare daily_basic | 否   | 1     |
| M02  | 财务指标摘要            | financial_summary       | Tushare fina_indicator | 否 | 1     |
| M03  | 利润表营收利润趋势       | income_statement        | Tushare income  | 否      | 1     |
| M04  | 资产负债表关键指标       | balance_sheet           | Tushare balancesheet | 否 | 1     |
| M05  | 现金流量健康度          | cashflow_health         | Tushare cashflow | 否     | 1     |
| M06  | 估值指标               | valuation_multiples     | Tushare daily_basic | 否  | 2     |
| M07  | 成长性指标              | growth_metrics          | Tushare fina_indicator | 否 | 2  |
| M08  | 盈利质量               | profit_quality          | Tushare fina_indicator | 否 | 2  |
| M09  | 偿债能力               | solvency                | Tushare fina_indicator | 否 | 2  |
| M10  | 营运能力               | operating_efficiency    | Tushare fina_indicator | 否 | 2  |
| M11  | 同行业估值对比          | peer_valuation          | Tushare daily_basic | 否  | 2     |
| M12  | 同行业财务对比          | peer_financial          | Tushare fina_indicator | 否 | 2  |
| M13  | 行业排名-营收           | rank_revenue            | SQL percentile  | 否      | 5     |
| M14  | 行业排名-净利润         | rank_profit             | SQL percentile  | 否      | 5     |
| M15  | 行业排名-ROE            | rank_roe                | SQL percentile  | 否      | 5     |
| M16  | 大股东持股             | major_holders           | Tushare top10_holders | 否 | 2  |
| M17  | 股权结构               | equity_structure        | Tushare stk_holdertrade | 否 | 2 |
| M18  | 分红历史               | dividend_history        | Tushare dividend | 否     | 2     |
| M19  | 研报评级汇总           | analyst_ratings         | Tushare report_rc | 否    | 2     |
| M20  | 近期公告摘要           | announcements           | Tushare anns    | 否      | 2     |
| M21  | 技术面指标快照         | technical_snapshot      | Tushare daily   | 否      | 2     |
| M22  | 资金流向              | fund_flow               | AkShare (moneyflow) | 否  | 2     |
| M23  | 融资融券              | margin_trading          | Tushare margin  | 否      | 2     |
| AI   | AI 智能解析            | ai_analysis             | DeepSeek + M01-M10 | **是** | 3  |

**原则**：
- M01~M32 全部无 LLM，纯数据变换
- AI 模块（+1）仅在用户显式请求时调用，独立计费
- M13~M15（行业排名）必须通过 SQL percentile 函数计算，不允许 Python 遍历
- M22 资金流向：Tushare Pro 低积分账户可能无权，允许降级至 AkShare

---

## 二、DataEnvelope 规范

```python
from typing import Any, TypedDict

class DataEnvelope(TypedDict):
    ok: bool                    # True = 至少 data 不为 None
    data: Any | None            # 模块数据
    reason: str | None          # ok=False 时的原因描述
    stale: bool                 # True = 来自过期缓存（源暂不可用）
    partial_errors: list[str]   # ok=True 但某些子字段失败的描述
    cached_at: str | None       # ISO 8601，UTC+8；None = 直接从源获取
```

构建函数（位于 `app/aggregator/envelope.py`）：

```python
def ok_envelope(data, *, stale=False, cached_at=None, partial_errors=None) -> DataEnvelope
def err_envelope(reason, *, stale=False, cached_at=None) -> DataEnvelope
```

---

## 三、聚合器设计

### 3.1 FundamentalsAggregator

位置：`app/aggregator/fundamentals_aggregator.py`

```python
class FundamentalsAggregator:
    async def fetch_snapshot(self, market, symbol) -> dict[str, DataEnvelope]:
        """并发拉取 M01+M02+M06（用于首屏快照卡片）"""

    async def fetch_module(self, market, symbol, module_key) -> DataEnvelope:
        """拉取单个模块，自动读/写缓存"""

    async def list_modules(self) -> list[dict]:
        """返回所有模块的 metadata（key, name_zh, phase, requires_llm）"""
```

### 3.2 并发策略

```python
results = await asyncio.gather(
    *[self.fetch_module(market, symbol, key) for key in snapshot_keys],
    return_exceptions=True,
)
```

- `return_exceptions=True`：单个模块失败不影响其他模块
- 每个模块独立 try/except，失败时返回 `err_envelope(reason=...)`
- 聚合器不对结果做 LLM 处理

### 3.3 缓存读写流程

```
fetch_module(market, symbol, module_key)
│
├─ [1] 读 Redis cache key = f"fs:{market}:{symbol}:{module_key}:v1"
│      ├─ cache HIT + not stale → 返回缓存 DataEnvelope（cached_at 填充）
│      ├─ cache HIT + stale → 启动后台刷新任务，立即返回旧数据（stale=True）
│      └─ cache MISS → 继续
│
├─ [2] 调用 Tool.fetch(market, symbol)
│      ├─ Tushare 成功 → 继续
│      └─ Tushare 失败 + ENABLE_AKSHARE=true → 尝试 AkShare
│
├─ [3] 写入 Redis（TTL 按模块配置）
│
└─ [4] 返回 ok_envelope(data)
```

---

## 四、工具基类 BaseFundamentalTool

位置：`app/tools/fundamental/base.py`

```python
from abc import ABC, abstractmethod
from app.aggregator.envelope import DataEnvelope

class BaseFundamentalTool(ABC):
    module_key: str                  # e.g. "quote_snapshot"
    cache_ttl_seconds: int           # 主 TTL
    stale_ttl_seconds: int           # stale 降级 TTL

    @abstractmethod
    async def fetch(self, market: str, symbol: str) -> dict:
        """从源拉取原始数据，返回 raw dict（不带 envelope）"""

    async def fetch_with_fallback(self, market: str, symbol: str) -> DataEnvelope:
        """调用 fetch()，失败时尝试 AkShare fallback（如果 ENABLE_AKSHARE）"""
```

---

## 五、模块分组与前端展示分区

```
首屏快照（M01+M02+M06）
│
├── 市场数据组（M01, M21, M22, M23）
│   实时价格、技术指标、资金流、融资融券
│
├── 财务报告组（M03, M04, M05）
│   利润表 / 资产负债 / 现金流
│
├── 盈利质量组（M07, M08, M09, M10）
│   成长性 / 盈利质量 / 偿债 / 营运
│
├── 估值与比较组（M06, M11, M12）
│   估值倍数 / 同行对比（估值+财务）
│
├── 行业排名组（M13, M14, M15）
│   SQL 百分位排名（Phase 5）
│
├── 股权与公司治理组（M16, M17, M18）
│   大股东 / 股权结构 / 分红
│
├── 市场情报组（M19, M20）
│   研报评级 / 公告摘要
│
└── AI 智能解析（AI）
    仅用户主动请求，走 app/agent/ai_analyst.py
```

---

## 六、partial_errors 规范

当模块可以返回部分数据时，`ok=True` 但 `partial_errors` 非空：

```json
{
  "ok": true,
  "data": {
    "revenue": 8.8e10,
    "net_profit": null
  },
  "reason": null,
  "stale": false,
  "partial_errors": ["net_profit: Tushare 返回 None，AkShare 未开启"],
  "cached_at": null
}
```

字段级失败规则：
- 数值字段解析失败 → `null` + 记录 partial_errors
- 整个 DataFrame 为空 → `ok=false`
- 网络超时 → `ok=false`（触发 stale 降级）

---

## 七、市场代码规范

| 参数 `market` | 说明     | Tushare ts_code 格式           |
|--------------|----------|-------------------------------|
| `CN`         | A 股沪深  | `{symbol}.SH` 或 `{symbol}.SZ` |
| `HK`         | 港股      | `{symbol}.HK`                  |
| `US`         | 美股      | `{symbol}` (原始 ticker)       |

`market + symbol → ts_code` 由 `tushare_client._to_ts_code()` 处理。

---

## 八、版本控制

cache key 包含版本号 `:v1`，当模块数据结构变更时递增版本号可立即清空旧缓存，无需 flush all。
