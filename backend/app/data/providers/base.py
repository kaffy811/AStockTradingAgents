from abc import ABC, abstractmethod


SUPPORTED_MARKETS = {"CN", "HK"}


class BaseStockDataProvider(ABC):
    """
    Abstract interface for stock data providers.

    Rules:
    - No business / agent logic here.
    - Returns only plain Python dicts/lists (JSON-serializable).
    - Never returns a pandas DataFrame directly.
    - market must be "CN" (A-share) or "HK" (Hong Kong).
    """

    @abstractmethod
    def get_quote(self, market: str, symbol: str) -> dict:
        """
        Fetch the latest snapshot quote for a single stock.

        Args:
            market: "CN" or "HK"
            symbol: Stock code. CN: "600519" | HK: "00700" or "700"

        Returns:
            Dict with at minimum:
            {
                "symbol": str,
                "name": str,
                "price": float,
                "change_pct": float,   # percent, e.g. 1.23 means +1.23%
                "volume": float,
                ...provider-specific fields...
            }

        Raises:
            ValueError:   Unsupported market or invalid symbol.
            RuntimeError: Upstream data source failure.
        """
        ...

    @abstractmethod
    def get_kline(
        self,
        market: str,
        symbol: str,
        period: str = "daily",
        adjust: str = "",
        limit: int = 120,
    ) -> list[dict]:
        """
        Fetch historical OHLCV candlestick data.

        Args:
            market:  "CN" or "HK"
            symbol:  Stock code.
            period:  "daily" | "weekly" | "monthly"
            adjust:  ""  = unadjusted
                     "qfq" = forward-adjusted (前复权)
                     "hfq" = backward-adjusted (后复权)
            limit:   Max number of bars to return (most-recent first after sort).

        Returns:
            List of dicts, each with:
            {
                "date":   "YYYY-MM-DD",
                "open":   float,
                "high":   float,
                "low":    float,
                "close":  float,
                "volume": float,
            }

        Raises:
            ValueError:   Unsupported market or invalid symbol.
            RuntimeError: Upstream data source failure.
        """
        ...
