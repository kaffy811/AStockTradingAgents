# Agent Architecture

## Overview

TradingAgents uses a layered agent architecture. Each agent is a self-contained class that:
- Accepts a `BaseLLMClient` at construction (dependency injection)
- Exposes a single `analyze(market, symbol) -> str` method
- Returns a Markdown report
- Has no direct knowledge of routing, auth, or database concerns

```
FastAPI Router (analysis.py)
  └── asyncio.to_thread(agent.analyze)
        └── TechnicalAnalystAgent
              ├── StockDataService.get_kline_for_agent()   # required
              ├── StockDataService.get_quote_optional()    # optional
              ├── TechnicalIndicatorService.calculate()
              └── BaseLLMClient.chat()
```

---

## Currently Implemented

### TechnicalAnalystAgent

**Module:** `app/agents/technical_analyst.py`  
**Backward-compat alias:** `app/agents/market_analyst.py` → `MarketAnalystAgent`

**Endpoint:**
- `POST /api/v1/analysis/technical` ← **recommended**
- `POST /api/v1/analysis/market`    ← deprecated alias, identical behaviour

**Input data:**
| Source | Data | Required |
|---|---|---|
| `StockDataService.get_kline_for_agent()` | 120 daily bars (OHLCV + amount_estimated) | Yes — failure raises RuntimeError → HTTP 503 |
| `StockDataService.get_quote_optional()` | Real-time price, volume, amount | No — None is handled gracefully |
| `TechnicalIndicatorService.calculate()` | MA5/10/20/60, returns, volume ratios, trend signals | Derived from kline |

**Output:** Markdown report with fixed structure:
```
## 技术面分析报告
### 一、行情概览
### 二、均线与趋势
### 三、量价变化
### 四、短期风险
### 五、观察要点
### 风险提示
```

**Quote fallback behaviour:**  
When `get_quote_optional()` returns `None`, the agent:
1. Uses the last kline bar's `close` as the reference price
2. Labels it in the report as "K线最新收盘价（实时报价不可用）"
3. Continues analysis without interruption

**What this agent CAN do:**
- Moving average analysis (MA5/10/20/60)
- Trend identification (short-term, medium-term)
- Volume pattern analysis (放量/缩量/平量)
- Price range / support-resistance reference
- Multi-period return summary (1d / 5d / 20d)

**What this agent CANNOT do (hard prohibition in system prompt):**
- Fundamental analysis (PE, PB, ROE, net profit, cash flow, balance sheet metrics)
- News / macro / policy analysis
- Certain directional investment recommendations
- Use `amount_estimated` as a basis for strong money-flow conclusions

**`amount_estimated` usage rule:**  
Kline bars include `amount_estimated` (rough estimate via `(high+low)/2 × volume_in_shares`).  
The system prompt explicitly instructs the LLM:
> 不得基于 amount_estimated 做资金大幅流入/流出、主力建仓/出货等强资金结论。

---

## Technical Indicator Service

**Module:** `app/services/technical_indicator_service.py`

Pure-Python, JSON-safe. No pandas / numpy.

| Indicator | Description |
|---|---|
| `ma5` / `ma10` / `ma20` / `ma60` | Simple moving average of close prices |
| `price_vs_ma20_pct` / `price_vs_ma60_pct` | Price deviation from MA (%) |
| `return_1d_pct` / `return_5d_pct` / `return_20d_pct` | Multi-period price return |
| `high_20d` / `low_20d` / `high_60d` / `low_60d` | Range extremes (support/resistance reference) |
| `volume_avg_5d` / `volume_avg_20d` | Average volume |
| `volume_ratio_5_20` | 5-day avg / 20-day avg — >1 means recent increase |
| `volume_ratio_today` | Today's volume / 5-day avg |
| `short_term_trend` | MA5 vs MA10 → 上升 / 下降 / 横盘 / 数据不足 |
| `medium_term_trend` | MA10 vs MA20 → 上升 / 下降 / 横盘 / 数据不足 |
| `volume_signal` | 近期放量 / 近期缩量 / 量能平稳 / 单日明显放量 / 数据不足 |

Graceful degradation: if kline has fewer bars than a window requires, that indicator returns `None`. The LLM is instructed to label these as "数据不足，暂不评估".

---

## FundamentalDataService (data layer — not an Agent)

**Module:** `app/services/fundamental_data_service.py`  
**Provider:** `app/data/providers/fundamental_provider.py`  
**Endpoint:** `GET /api/v1/stocks/{market}/{symbol}/fundamentals`  
**Contract:** `docs/fundamental_data_contract.md`

This is a **data layer service**, not an agent. It returns a structured JSON snapshot.
It has no LLM dependency and no `analyze()` method.

### Phase Coverage

| Phase | Status | CN Fields | HK Fields |
|---|---|---|---|
| **Phase 1** | Done | `company.name`, `valuation.pe/pb` (AkShare spot), `market_cap` (yfinance optional) | `company.name` only |
| **Phase 2** | Done | + `profitability.roe/gross_margin/net_margin`, `growth.revenue_growth_yoy/net_profit_growth_yoy`, `financial_health.debt_ratio/operating_cashflow` | unchanged |
| **Phase 3** | Planned | + `company.industry/business_summary`, `valuation.ps/dividend_yield` | HK pe/pb/financial ratios |

### Data Sources (Phase 2)

| Source | Interface | Fields |
|---|---|---|
| AkShare `stock_zh_a_spot_em()` | Quote endpoint | name, pe, pb |
| AkShare `stock_financial_abstract_ths()` | THS quarterly summary | roe, gross_margin, net_margin, revenue_growth_yoy, net_profit_growth_yoy, debt_ratio |
| AkShare `stock_financial_cash_ths()` | THS cash flow | operating_cashflow (元) |
| yfinance `fast_info` | Optional fallback | market_cap only |

### Failure Behaviour

- Any single source failure → that source's fields are `null` in `missing_fields`
- Partial success is normal (e.g. quote OK but THS unavailable)
- Stale cache returned if all live sources fail and a prior snapshot exists
- HTTP 200 always — never 5xx from data failures

### Cache TTL

3600 seconds (1 hour). Financial ratios update quarterly; hourly cache is appropriate.

---

### FundamentalAnalystAgent

**Module:** `app/agents/fundamental_analyst.py`  
**Backward-compat alias:** none

**Endpoints:**
- `POST /api/v1/analysis/fundamental` ← recommended

**Input data:**
| Source | Data | Required |
|---|---|---|
| `FundamentalDataService.get_fundamentals()` | Structured fundamentals snapshot | Yes — `null` fields handled gracefully |

**Output:** Markdown report with fixed structure:
```
## 基本面分析报告
### 一、基本信息
### 二、估值指标
### 三、盈利能力
### 四、成长性
### 五、财务健康
### 六、数据质量说明
### 风险提示
```

**Hard prohibitions (enforced in system prompt):**
- Do not invent values for `null` fields
- Do not judge PE/PB if those fields are `null`
- Do not describe industry/business if `company.industry` / `business_summary` is `null`
- Do not call quarterly data "全年表现" unless `latest_report_date` ends in `12-31`
- Do not give directional investment recommendations
- HK stocks: all financial ratios are `null` — state data unavailability, do not fabricate

See full contract in `docs/fundamental_data_contract.md`.

---

## Planned Agents (not yet implemented)

The following agents are planned for future phases. Each will follow the same `BaseLLMClient` injection pattern and `analyze(market, symbol) -> str` interface.

### NewsAnalystAgent
**Module (planned):** `app/agents/news_analyst.py`  
**Data sources:** Financial news API, announcement scraper  
**Output:** Sentiment summary, key event extraction, risk keywords  

### PeerComparisonAgent
**Module (planned):** `app/agents/peer_comparison.py`  
**Data sources:** Industry kline / financial data for peer companies  
**Output:** Relative strength, valuation percentile within sector  

### RiskManagerAgent
**Module (planned):** `app/agents/risk_manager.py`  
**Data sources:** Outputs from Technical / Fundamental / News agents  
**Output:** Synthesised risk assessment, position sizing guidance (ranges, not exact values)  

---

## LangGraph Integration Plan

When multiple agents are available, a LangGraph coordinator will orchestrate them:

```
LangGraph Graph: StockAnalysisGraph
  State: { market, symbol, kline, quote, tech_report, fund_report, news_report, risk_report }

  Nodes (each is one agent's analyze()):
    fetch_data          → StockDataService
    technical_analysis  → TechnicalAnalystAgent
    fundamental_analysis→ FundamentalAnalystAgent    (parallel with technical)
    news_analysis       → NewsAnalystAgent           (parallel with technical)
    risk_assessment     → RiskManagerAgent           (after all analysis nodes)
    synthesise_report   → CoordinatorAgent

  Entry: fetch_data
  Edges: fetch_data → [technical, fundamental, news] (parallel fan-out)
         [technical, fundamental, news] → risk_assessment
         risk_assessment → synthesise_report
         synthesise_report → END
```

The FastAPI router (`analysis.py`) will call `graph.ainvoke(state)` and return the synthesised report. Individual agent endpoints remain available for single-agent queries.

---

## Adding a New Agent — Checklist

1. Create `app/agents/<name>.py` with class `<Name>Agent(BaseLLMClient)`
2. Add `analyze(market, symbol) -> str` method
3. Add a system prompt with explicit prohibition section
4. Add a new route in `app/routers/analysis.py` (or a new router file)
5. Register the route in `app/routers/__init__.py` if a new router file
6. Add a section to this document
