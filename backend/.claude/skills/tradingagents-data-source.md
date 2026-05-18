# Skill: tradingagents-data-source
你是 TradingAgents 的金融数据工程师。

## 统一返回格式
get_fundamentals → {symbol,name,market,price,pe,pb,peg,roe,eps,debt_ratio,revenue_yoy,profit_yoy,source}
get_market_data  → {symbol,ohlcv:[...],indicators:{ma5,ma10,ma20,ma60,macd,signal,rsi,boll_upper,boll_mid,boll_lower},source}
get_news         → {symbol,news:[{title,summary,pub_time,sentiment}],source}

## Fallback 链
A股：AkShare → Tushare → BaoStock
港股：AkShare → yfinance → Finnhub
实现：for source_name, fetch_func in sources: try → return / except → continue → raise DataSourceError

## 关键 AkShare API
A股：stock_individual_info_em / stock_zh_a_hist(adjust="qfq") / stock_a_indicator_lg / stock_news_em
港股：stock_hk_spot_em / stock_hk_hist / yfinance Ticker("0700.HK")

## 技术指标（indicators.py）
输入：DataFrame(open/high/low/close/volume)
输出：追加 ma5/10/20/60 / macd+signal+macd_hist / rsi(14) / boll_upper+mid+lower(20,2)

## 港股代码处理
symbol.zfill(5) → AkShare格式
f"{symbol.lstrip('0')}.HK" → yfinance格式

## 缓存 TTL
fundamentals: 86400s / market: 3600s / news: 1800s

## 每个模块必须有 __main__ 入口
python -m app.data.china_stock 600519 A
python -m app.data.hk_stock 0700 HK

## 禁止
不在数据层调用 LLM / 不将 DataFrame 直传 Agent / 不跳过 Redis 缓存 / 不硬编码 Token
