# 03_cost_and_refresh.md — 成本控制与刷新策略

> 版本：v1.0  
> 日期：2026-07-04

---

## 一、Tushare Pro 积分消耗模型

### 1.1 账户限额

| 等级         | 每分钟积分   | 每日积分      | 适用接口                                  |
|-------------|------------|-------------|------------------------------------------|
| 基础（免费）   | 500        | 无限         | daily, daily_basic, stock_basic           |
| 积分 2000    | 500        | 无限         | + income, balancesheet, cashflow          |
| 积分 5000    | 500        | 无限         | + fina_indicator, top10_holders, margin   |
| 积分 10000   | 500        | 无限         | + report_rc（研报评级）                   |

> **注意**：本服务以 **基础 + 积分 5000** 为设计基准。积分不足时接口会返回 40001 错误，由 TushareClient 自动降级到 AkShare（如开启）或返回 stale 缓存。

### 1.2 单次用户请求积分估算

| 场景                     | 调用接口                                          | 积分消耗 |
|------------------------|--------------------------------------------------|---------|
| 首屏快照（缓存命中）        | 无                                               | 0       |
| 首屏快照（缓存缺失）        | daily_basic × 1 + fina_indicator × 1             | 2       |
| 完整 23 模块（全缓存缺失）   | 约 8-10 次 API 调用                              | 8-10    |
| AI 模块                  | 依赖已缓存 M01-M10，追加 LLM 费用（非积分）         | 0       |

---

## 二、缓存 TTL 矩阵

| 模块         | 数据更新频率        | Redis 主 TTL | stale TTL | 刷新触发方式     |
|-------------|-------------------|-------------|-----------|----------------|
| M01 行情快照  | 实时（交易日 9:30-15:00） | 60s     | 300s      | 请求触发刷新    |
| M02 财务摘要  | 季报季（3/6/9/12月）    | 4h      | 48h       | 请求触发刷新    |
| M03 利润表   | 季报季                  | 4h      | 48h       | 请求触发刷新    |
| M04 资产负债  | 季报季                  | 4h      | 48h       | 请求触发刷新    |
| M05 现金流   | 季报季                  | 4h      | 48h       | 请求触发刷新    |
| M06 估值指标  | 每日收盘后               | 4h      | 24h       | 请求触发刷新    |
| M11-M12 同行对比 | 每日                | 1h      | 6h        | 请求触发刷新    |
| M13-M15 行业排名 | 每日（Phase 5 ETL） | 1h      | 6h        | Cron ETL 推送  |
| M16-M18 持股/分红 | 季报季/年报季       | 24h     | 7d        | 请求触发刷新    |
| M19 研报评级  | 不定期                  | 2h      | 12h       | 请求触发刷新    |
| M20 公告摘要  | 每日                    | 30m     | 2h        | 请求触发刷新    |
| M21 技术快照  | 每日                    | 4h      | 24h       | 请求触发刷新    |
| M22 资金流向  | 每日                    | 1h      | 6h        | 请求触发刷新    |
| M23 融资融券  | 每日                    | 4h      | 24h       | 请求触发刷新    |

---

## 三、速率限制器实现

采用**令牌桶**，无第三方库依赖，纯 asyncio：

```python
# app/datasource/tushare_client.py

class _TokenBucket:
    """
    500 tokens/min 令牌桶。
    - 每 120ms 补充 1 个 token（等效于 500/min）
    - burst = 20（允许短时间内连续 20 次调用）
    - 满桶上限 = 50（限制 burst 上限）
    - acquire() 超时 10s 返回 TushareRateLimitError
    """
    def __init__(self, rate_per_min: int = 500, burst: int = 20):
        self._rate = rate_per_min / 60.0   # tokens/sec
        self._capacity = min(burst, 50)
        self._tokens = float(self._capacity)
        self._last_refill = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float = 10.0):
        deadline = asyncio.get_event_loop().time() + timeout
        async with self._lock:
            while True:
                now = asyncio.get_event_loop().time()
                elapsed = now - self._last_refill
                self._tokens = min(
                    self._capacity,
                    self._tokens + elapsed * self._rate,
                )
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
                if now + wait > deadline:
                    raise TushareRateLimitError("acquire timeout")
                await asyncio.sleep(min(wait, 0.1))
```

---

## 四、LLM 成本控制（AI 模块）

AI 模块（M_AI）仅在用户显式点击"AI 智能解析"时触发：

| 项目             | 值                                               |
|----------------|--------------------------------------------------|
| LLM Provider   | DeepSeek（与 Chat Copilot 共用 client）           |
| 输入 token 上限  | ~4000 tokens（M01-M10 摘要文本拼接）              |
| 输出 token 上限  | ~1000 tokens（结构化 JSON：亮点/风险/评级）        |
| 每次调用估计费用  | DeepSeek-V4-Flash ~¥0.002（参考定价）             |
| 冷却限制         | 同一 symbol 同一用户 24h 内 AI 模块缓存，不重复调用 |

AI 模块输出格式（固定 JSON，不允许 markdown 自由文本）：
```json
{
  "highlights": ["...", "...", "..."],
  "risks": ["...", "...", "..."],
  "rating": "买入/持有/卖出/观望",
  "confidence": 0.72,
  "disclaimer": "本分析仅供参考，不构成投资建议。"
}
```

---

## 五、非交易时段行为

行情类模块（M01，M21）在非交易时段（收盘后/休市）：
- 返回最近一个交易日收盘数据
- `stale=true`（即使缓存未过期，也标记 stale 提示用户）
- 缓存 TTL 仍按正常策略（60s 内不重复请求 Tushare）

财务类模块（M02-M05）：TTL 4h 不受交易时段影响。

---

## 六、AkShare 作为备用的成本

AkShare 免费无积分限制，但：
- 接口响应较慢（P95 ~3s vs Tushare ~0.5s）
- 不保证数据一致性（不同接口数据口径可能不同）
- 爬取频率过高可能触发反爬（自我限制：非交易时段不超过 30 req/min）

开启建议：仅在 Tushare Token 积分不足时开启，生产环境默认 `ENABLE_AKSHARE=false`。

---

## 七、Phase 5 ETL 定时任务

| 任务             | 触发时间        | 涉及模块          | 说明                             |
|----------------|---------------|-----------------|----------------------------------|
| 财务数据入库      | 每季报截止日后   | M03/M04/M05     | Tushare income/balancesheet/cashflow → PostgreSQL |
| 行业排名重算      | 每交易日 17:00  | M13/M14/M15     | SQL PERCENT_RANK() over industry  |
| 全市场日频指标    | 每交易日 16:30  | M06/M21/M22/M23 | Tushare daily_basic → Redis 批量预热 |

ETL 脚本位置（Phase 5 实现）：`backend/scripts/etl_*.py`

---

## 八、监控与告警

关键指标（接入 Prometheus/Grafana，Phase 5）：
- `tushare_api_calls_total{status="ok|error"}`
- `tushare_rate_limit_waits_total`
- `fs_cache_hit_rate{module}`
- `fs_module_p95_latency_ms{module}`

Phase 1 先以 logging 代替，格式：
```
INFO datasource.tushare: call={func} symbol={symbol} elapsed={ms}ms status=ok|error
```
