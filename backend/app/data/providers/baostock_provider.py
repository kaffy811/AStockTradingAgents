"""
BaoStock stock data provider — A股 K线备用数据源（占位 stub）。

当前状态：接口占位，尚未激活。
原因：BaoStock 需要注册账号 + 额外 pip install baostock，
      且只覆盖 A股 kline，接入成本相对 yfinance 更高。
      StockDataService 遇到 NotImplementedError 会自动跳过，
      不会影响现有功能。

如需将来激活：
  1. pip install baostock
  2. 在 __init__() 中调用 bs.login()
  3. 在 __del__() / close() 中调用 bs.logout()
  4. 实现 _kline_cn() 中的查询逻辑
  5. 在 StockDataService.__init__() 中初始化并注册此 provider
"""

from app.data.providers.base import BaseStockDataProvider


class BaoStockDataProvider(BaseStockDataProvider):
    """
    BaoStock-backed provider — 当前为占位 stub。
    所有方法均抛出 NotImplementedError，StockDataService 会自动跳过。
    """

    def get_quote(self, market: str, symbol: str) -> dict:
        raise NotImplementedError(
            "BaoStock 不支持实时 quote，请使用 AkShare 或 yfinance。"
        )

    def get_kline(
        self,
        market: str,
        symbol: str,
        period: str = "daily",
        adjust: str = "",
        limit: int = 120,
    ) -> list[dict]:
        raise NotImplementedError(
            "BaoStock kline 尚未实现。激活步骤请参考文件顶部注释。"
        )
