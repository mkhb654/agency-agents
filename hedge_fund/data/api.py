"""Financial data API client.

Provides both async (``httpx.AsyncClient``) and sync wrapper interfaces for
fetching financial data from https://api.financialdatasets.ai.

Features:
- Automatic retry with exponential backoff on HTTP 429 (rate-limited).
- Response parsing into strongly-typed Pydantic models.
- Integration with the in-memory :class:`~hedge_fund.data.cache.Cache`.
- Sync convenience methods for non-async call sites.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Optional, TypeVar

import httpx

from hedge_fund.config import get_settings
from hedge_fund.data.cache import Cache
from hedge_fund.data.models import (
    CompanyNews,
    FinancialMetrics,
    InsiderTrade,
    LineItem,
    Price,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.financialdatasets.ai"

# Maximum number of retry attempts on 429 / transient errors.
_MAX_RETRIES = 4
# Base delay in seconds (doubled on each retry).
_BASE_BACKOFF = 1.0

T = TypeVar("T")


class FinancialDataClient:
    """Async-first client for the Financial Datasets API.

    Parameters
    ----------
    api_key:
        Override the API key.  Falls back to ``FINANCIAL_DATASETS_API_KEY``
        from the environment / settings.
    cache_ttl:
        Default cache TTL in seconds for all endpoints.  ``0`` disables.
    timeout:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        timeout: float = 30.0,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.financial_datasets_api_key or ""
        self._cache_ttl = cache_ttl if cache_ttl is not None else settings.cache_ttl_seconds
        self._cache = Cache.get_instance()
        self._timeout = timeout
        self._async_client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_async_client(self) -> httpx.AsyncClient:
        """Lazily create and return the ``httpx.AsyncClient``."""
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=_BASE_URL,
                headers=self._build_headers(),
                timeout=self._timeout,
            )
        return self._async_client

    def _build_headers(self) -> dict[str, str]:
        """Construct HTTP headers for API requests."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def aclose(self) -> None:
        """Close the underlying async HTTP client."""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()

    async def __aenter__(self) -> FinancialDataClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Low-level request with retry
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with exponential-backoff retry on 429.

        Args:
            method: HTTP method (GET, POST, ...).
            path: URL path relative to the base URL.
            params: Query parameters.
            json_body: JSON body for POST requests.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            RuntimeError: After all retries are exhausted.
            httpx.HTTPStatusError: On non-retryable HTTP errors.
        """
        client = self._get_async_client()
        last_exc: Optional[Exception] = None
        delay = _BASE_BACKOFF

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                )
                if response.status_code == 429:
                    # Respect Retry-After header if present.
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else delay
                    logger.warning(
                        "Rate-limited (429) on %s %s, retrying in %.1fs (attempt %d/%d)",
                        method,
                        path,
                        wait,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    delay *= 2
                    continue

                response.raise_for_status()
                return response.json()  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_exc = exc
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise
            except httpx.TransportError as exc:
                logger.warning(
                    "Transport error on %s %s: %s (attempt %d/%d)",
                    method,
                    path,
                    exc,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                last_exc = exc
                await asyncio.sleep(delay)
                delay *= 2

        raise RuntimeError(
            f"All {_MAX_RETRIES} retries exhausted for {method} {path}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Price data
    # ------------------------------------------------------------------

    async def get_prices(
        self,
        ticker: str,
        start_date: datetime.date | str,
        end_date: Optional[datetime.date | str] = None,
        interval: str = "day",
    ) -> list[Price]:
        """Fetch daily OHLCV price data for *ticker*.

        Args:
            ticker: Stock ticker symbol (e.g. ``"AAPL"``).
            start_date: Inclusive start date.
            end_date: Inclusive end date (defaults to today).
            interval: Bar interval (``"day"``, ``"week"``, ``"month"``).

        Returns:
            List of :class:`Price` objects sorted by date ascending.
        """
        end_date = end_date or datetime.date.today()
        cache_key = Cache.make_key("get_prices", ticker, str(start_date), str(end_date), interval)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        params = {
            "ticker": ticker,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "interval": interval,
        }

        try:
            data = await self._request("GET", "/prices", params=params)
            prices_raw = data.get("prices", data) if isinstance(data, dict) else data
            if not isinstance(prices_raw, list):
                prices_raw = []
            result = [
                Price(
                    ticker=ticker,
                    date=p.get("date", p.get("time", "")),
                    open=p.get("open", 0),
                    high=p.get("high", 0),
                    low=p.get("low", 0),
                    close=p.get("close", 0),
                    volume=int(p.get("volume", 0)),
                )
                for p in prices_raw
            ]
            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            return result
        except Exception:
            logger.exception("Failed to fetch prices for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Financial metrics
    # ------------------------------------------------------------------

    async def get_financial_metrics(
        self,
        ticker: str,
        period_type: str = "quarterly",
        limit: int = 4,
    ) -> list[FinancialMetrics]:
        """Fetch financial metrics / valuation ratios for *ticker*.

        Args:
            ticker: Stock ticker symbol.
            period_type: ``"quarterly"``, ``"annual"``, or ``"ttm"``.
            limit: Maximum number of periods to return.

        Returns:
            List of :class:`FinancialMetrics` objects.
        """
        cache_key = Cache.make_key("get_financial_metrics", ticker, period_type, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        params: dict[str, Any] = {
            "ticker": ticker,
            "period": period_type,
            "limit": limit,
        }

        try:
            data = await self._request("GET", "/financial-metrics", params=params)
            items = data.get("financial_metrics", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                items = []
            result = [FinancialMetrics(ticker=ticker, **self._clean(m)) for m in items]
            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            return result
        except Exception:
            logger.exception("Failed to fetch financial metrics for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Financial line items (search)
    # ------------------------------------------------------------------

    async def search_line_items(
        self,
        ticker: str,
        line_items: list[str],
        period_type: str = "quarterly",
        limit: int = 4,
    ) -> list[LineItem]:
        """Search for specific financial statement line items.

        Args:
            ticker: Stock ticker symbol.
            line_items: List of line-item field names to retrieve
                (e.g. ``["revenue", "net_income", "total_assets"]``).
            period_type: ``"quarterly"``, ``"annual"``, or ``"ttm"``.
            limit: Maximum number of periods to return.

        Returns:
            List of :class:`LineItem` objects.
        """
        cache_key = Cache.make_key("search_line_items", ticker, line_items, period_type, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        json_body = {
            "ticker": ticker,
            "line_items": line_items,
            "period": period_type,
            "limit": limit,
        }

        try:
            data = await self._request("POST", "/financials/search/line-items", json_body=json_body)
            items = data.get("search_results", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                items = []
            result = [LineItem(ticker=ticker, **self._clean(li)) for li in items]
            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            return result
        except Exception:
            logger.exception("Failed to search line items for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Insider trades
    # ------------------------------------------------------------------

    async def get_insider_trades(
        self,
        ticker: str,
        start_date: Optional[datetime.date | str] = None,
        limit: int = 100,
    ) -> list[InsiderTrade]:
        """Fetch insider transactions for *ticker*.

        Args:
            ticker: Stock ticker symbol.
            start_date: Optional start date filter.
            limit: Maximum number of trades to return.

        Returns:
            List of :class:`InsiderTrade` objects.
        """
        cache_key = Cache.make_key("get_insider_trades", ticker, str(start_date), limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        params: dict[str, Any] = {"ticker": ticker, "limit": limit}
        if start_date:
            params["start_date"] = str(start_date)

        try:
            data = await self._request("GET", "/insider-trades", params=params)
            items = data.get("insider_trades", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                items = []
            result = [InsiderTrade(ticker=ticker, **self._clean(t)) for t in items]
            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            return result
        except Exception:
            logger.exception("Failed to fetch insider trades for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Company news
    # ------------------------------------------------------------------

    async def get_company_news(
        self,
        ticker: str,
        start_date: Optional[datetime.date | str] = None,
        limit: int = 50,
    ) -> list[CompanyNews]:
        """Fetch recent news articles for *ticker*.

        Args:
            ticker: Stock ticker symbol.
            start_date: Optional start date filter.
            limit: Maximum number of articles.

        Returns:
            List of :class:`CompanyNews` objects.
        """
        cache_key = Cache.make_key("get_company_news", ticker, str(start_date), limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        params: dict[str, Any] = {"ticker": ticker, "limit": limit}
        if start_date:
            params["start_date"] = str(start_date)

        try:
            data = await self._request("GET", "/news", params=params)
            items = data.get("news", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                items = []
            result = [CompanyNews(ticker=ticker, **self._clean(n)) for n in items]
            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            return result
        except Exception:
            logger.exception("Failed to fetch news for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Market cap (convenience)
    # ------------------------------------------------------------------

    async def get_market_cap(self, ticker: str) -> Optional[float]:
        """Return the latest market capitalisation for *ticker*, or ``None``.

        This is a convenience wrapper that pulls the most recent financial
        metrics record and extracts ``market_cap``.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Market cap in USD, or ``None`` if unavailable.
        """
        metrics = await self.get_financial_metrics(ticker, period_type="quarterly", limit=1)
        if metrics and metrics[0].market_cap is not None:
            return metrics[0].market_cap
        return None

    # ------------------------------------------------------------------
    # Sync wrappers
    # ------------------------------------------------------------------

    def get_prices_sync(
        self,
        ticker: str,
        start_date: datetime.date | str,
        end_date: Optional[datetime.date | str] = None,
        interval: str = "day",
    ) -> list[Price]:
        """Synchronous wrapper around :meth:`get_prices`."""
        return self._run_sync(self.get_prices(ticker, start_date, end_date, interval))

    def get_financial_metrics_sync(
        self,
        ticker: str,
        period_type: str = "quarterly",
        limit: int = 4,
    ) -> list[FinancialMetrics]:
        """Synchronous wrapper around :meth:`get_financial_metrics`."""
        return self._run_sync(self.get_financial_metrics(ticker, period_type, limit))

    def search_line_items_sync(
        self,
        ticker: str,
        line_items: list[str],
        period_type: str = "quarterly",
        limit: int = 4,
    ) -> list[LineItem]:
        """Synchronous wrapper around :meth:`search_line_items`."""
        return self._run_sync(self.search_line_items(ticker, line_items, period_type, limit))

    def get_insider_trades_sync(
        self,
        ticker: str,
        start_date: Optional[datetime.date | str] = None,
        limit: int = 100,
    ) -> list[InsiderTrade]:
        """Synchronous wrapper around :meth:`get_insider_trades`."""
        return self._run_sync(self.get_insider_trades(ticker, start_date, limit))

    def get_company_news_sync(
        self,
        ticker: str,
        start_date: Optional[datetime.date | str] = None,
        limit: int = 50,
    ) -> list[CompanyNews]:
        """Synchronous wrapper around :meth:`get_company_news`."""
        return self._run_sync(self.get_company_news(ticker, start_date, limit))

    def get_market_cap_sync(self, ticker: str) -> Optional[float]:
        """Synchronous wrapper around :meth:`get_market_cap`."""
        return self._run_sync(self.get_market_cap(ticker))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_sync(coro: Any) -> Any:
        """Run an async coroutine synchronously.

        If there is already a running event loop (e.g. inside Jupyter or
        an async framework), a new loop is created in a background thread.
        Otherwise ``asyncio.run`` is used directly.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return asyncio.run(coro)

    @staticmethod
    def _clean(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalise an API response dict for Pydantic model construction.

        - Converts camelCase keys to snake_case.
        - Strips internal keys (prefixed with ``_``).
        - Removes ``ticker`` (supplied separately by the caller).
        """
        cleaned: dict[str, Any] = {}
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            # camelCase -> snake_case
            snake_key = ""
            for i, ch in enumerate(k):
                if ch.isupper() and i > 0:
                    snake_key += "_"
                snake_key += ch.lower()
            cleaned[snake_key] = v
        cleaned.pop("ticker", None)
        return cleaned
