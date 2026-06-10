# Tools

根据文档的核心原则：**前三个分析师 Agent 可以调用外部数据 Tools；后两个决策 Agent（交易员、风控）不授权任何数据 Tools，只读前面产出的报告。**

![截屏2026-05-18 下午8.20.27.png](Tools/%E6%88%AA%E5%B1%8F2026-05-18_%E4%B8%8B%E5%8D%888.20.27.png)

---

### 用代码说明 Tool 长什么样

在 LangChain 里，Tool 就是一个加了 `@tool` 装饰器的普通 Python 函数：

python

`# app/tools/fundamentals_tools.py
from langchain_core.tools import tool
from app.data.china_stock import get_fundamentals_from_akshare

@tool
def get_stock_fundamentals(symbol: str, market: str) -> dict:
    """获取股票基本面数据，包括 PE、PB、ROE、EPS、资产负债率等财务指标。
    symbol: 股票代码，如 '600519'（A股）或 '0700'（港股）
    market: 市场类型，'A' 或 'HK'
    """
    return get_fundamentals_from_akshare(symbol, market)`

装饰器做了两件事：把函数名和 docstring 变成 LLM 能读懂的"工具说明"，让 LLM 知道这个工具干什么用、要传什么参数。

---

### Agent 如何被分配 Tools

python

`# app/agents/fundamentals.py
from langchain_openai import ChatOpenAI   # 换成 DeepSeek 也一样
from langchain.agents import create_tool_calling_agent, AgentExecutor

# 只给基本面分析师授权它需要的 Tools
fundamentals_tools = [
    get_stock_fundamentals,   # Tool A
    get_financial_ratios,     # Tool B
    calculate_dcf_valuation,  # Tool C
]

llm = ChatOpenAI(...)  # 或 DeepSeek
agent = create_tool_calling_agent(llm, fundamentals_tools, prompt)
executor = AgentExecutor(agent=agent, tools=fundamentals_tools)`

技术面分析师则只拿到 `[get_ohlcv_history, calculate_indicators, generate_technical_signals]`，完全看不到基本面数据的 Tools。这就是职责边界的实现方式。

---

### 完整 Tools 清单（按 Agent 分组）

| Agent | Tool 名称 | 调用的底层数据源 |
| --- | --- | --- |
| 基本面分析师 | `get_stock_fundamentals` | AkShare / Tushare / BaoStock |
| 基本面分析师 | `get_financial_ratios` | AkShare `stock_a_indicator_lg` |
| 基本面分析师 | `calculate_dcf_valuation` | 纯本地计算（Pandas），无外部 API |
| 技术面分析师 | `get_ohlcv_history` | AkShare `stock_zh_a_hist` |
| 技术面分析师 | `calculate_indicators` | 纯本地计算（Pandas/Numpy） |
| 技术面分析师 | `generate_technical_signals` | 纯本地规则逻辑 |
| 大盘分析师 | `get_index_data` | AkShare `stock_zh_index_daily` |
| 大盘分析师 | `calculate_market_breadth` | AkShare 涨跌家数接口 |
| 大盘分析师 | `get_vix_volatility` | AkShare VIX 或历史波动率计算 |
| 新闻情绪分析师 | `get_stock_news` | AkShare `stock_news_em` |
| 新闻情绪分析师 | `analyze_sentiment` | 本地规则或调 LLM 打情感标签 |
| 交易员 | **无 Tools** | 只读 LangGraph State |
| 风控主管 | **无 Tools** | 只读 LangGraph State |