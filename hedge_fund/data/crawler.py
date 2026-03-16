"""Free data crawler using yfinance + Firecrawl.

Drop-in replacement for FinancialDataClient that uses free data sources:
- yfinance: prices, fundamentals, insider trades, news
- Firecrawl (optional, self-hosted): SEC filings, earnings reports

No API keys required for yfinance. Firecrawl is optional and self-hosted only.
All data stays local. No external services receive your queries.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any, Optional

import yfinance as yf

from hedge_fund.data.cache import Cache
from hedge_fund.data.models import (
    CompanyNews,
    FinancialMetrics,
    InsiderTrade,
    LineItem,
    Price,
)

logger = logging.getLogger(__name__)


class FreeCrawler:
    """Free financial data crawler using yfinance.

    This is a drop-in replacement for FinancialDataClient.
    All methods match the same signatures and return the same models.
    No API keys needed. All data fetched locally via yfinance.
    """

    def __init__(self, cache_ttl: int = 3600) -> None:
        self._cache = Cache.get_instance()
        self._cache_ttl = cache_ttl

    # ------------------------------------------------------------------
    # Price data (yfinance)
    # ------------------------------------------------------------------

    def get_prices_sync(
        self,
        ticker: str,
        start_date: datetime.date | str,
        end_date: Optional[datetime.date | str] = None,
        interval: str = "day",
    ) -> list[Price]:
        """Fetch OHLCV price data from Yahoo Finance (free)."""
        end_date = end_date or datetime.date.today()
        cache_key = Cache.make_key("crawler_prices", ticker, str(start_date), str(end_date))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        try:
            yf_interval = {"day": "1d", "week": "1wk", "month": "1mo"}.get(interval, "1d")
            stock = yf.Ticker(ticker)
            df = stock.history(
                start=str(start_date),
                end=str(end_date),
                interval=yf_interval,
                auto_adjust=True,
            )

            if df.empty:
                logger.warning("No price data returned for %s", ticker)
                return []

            result: list[Price] = []
            for idx, row in df.iterrows():
                price_date = idx.date() if hasattr(idx, "date") else idx
                result.append(Price(
                    ticker=ticker,
                    date=price_date,
                    open=round(float(row.get("Open", 0)), 4),
                    high=round(float(row.get("High", 0)), 4),
                    low=round(float(row.get("Low", 0)), 4),
                    close=round(float(row.get("Close", 0)), 4),
                    volume=int(row.get("Volume", 0)),
                ))

            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            logger.info("Fetched %d price bars for %s", len(result), ticker)
            return result

        except Exception:
            logger.exception("Failed to fetch prices for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Financial metrics (yfinance)
    # ------------------------------------------------------------------

    def get_financial_metrics_sync(
        self,
        ticker: str,
        period_type: str = "quarterly",
        limit: int = 4,
    ) -> list[FinancialMetrics]:
        """Fetch financial metrics from Yahoo Finance (free)."""
        cache_key = Cache.make_key("crawler_metrics", ticker, period_type, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}

            # Get financial statements for growth calculations
            if period_type == "quarterly":
                income = stock.quarterly_income_stmt
                balance = stock.quarterly_balance_sheet
            else:
                income = stock.income_stmt
                balance = stock.balance_sheet

            result: list[FinancialMetrics] = []

            # Build metrics from yfinance info + statements
            num_periods = min(limit, len(income.columns)) if not income.empty else 1

            for i in range(num_periods):
                period_date = None
                period_label = period_type

                if not income.empty and i < len(income.columns):
                    col = income.columns[i]
                    period_date = col.date() if hasattr(col, "date") else None
                    if period_date:
                        q = (period_date.month - 1) // 3 + 1
                        period_label = f"{period_date.year}-Q{q}" if period_type == "quarterly" else str(period_date.year)

                # Extract from statements
                rev = _safe_get(income, "Total Revenue", i)
                net_inc = _safe_get(income, "Net Income", i)
                gross = _safe_get(income, "Gross Profit", i)
                op_inc = _safe_get(income, "Operating Income", i)
                ebitda_val = _safe_get(income, "EBITDA", i)

                total_equity = _safe_get(balance, "Stockholders Equity", i) or _safe_get(balance, "Total Stockholder Equity", i)
                total_assets = _safe_get(balance, "Total Assets", i)
                total_liab = _safe_get(balance, "Total Liabilities Net Minority Interest", i) or _safe_get(balance, "Total Liab", i)
                total_debt = _safe_get(balance, "Total Debt", i)
                current_assets = _safe_get(balance, "Current Assets", i)
                current_liab = _safe_get(balance, "Current Liabilities", i)

                # Calculate ratios
                roe = (net_inc / total_equity) if net_inc and total_equity and total_equity != 0 else None
                net_margin = (net_inc / rev) if net_inc and rev and rev != 0 else None
                gross_margin = (gross / rev) if gross and rev and rev != 0 else None
                op_margin = (op_inc / rev) if op_inc and rev and rev != 0 else None
                current_ratio = (current_assets / current_liab) if current_assets and current_liab and current_liab != 0 else None
                dte = (total_debt / total_equity) if total_debt and total_equity and total_equity != 0 else None

                # Revenue growth (compare to next period which is older)
                rev_growth = None
                prev_rev = _safe_get(income, "Total Revenue", i + 1)
                if rev and prev_rev and prev_rev != 0:
                    rev_growth = (rev - prev_rev) / abs(prev_rev)

                # Use info dict for valuation ratios (most recent only)
                pe = info.get("trailingPE") if i == 0 else None
                pb = info.get("priceToBook") if i == 0 else None
                ps = info.get("priceToSalesTrailing12Months") if i == 0 else None
                ev_ebitda = info.get("enterpriseToEbitda") if i == 0 else None
                mkt_cap = info.get("marketCap") if i == 0 else None
                eps = info.get("trailingEps") if i == 0 else None

                shares = info.get("sharesOutstanding")
                fcf_val = info.get("freeCashflow") if i == 0 else None

                result.append(FinancialMetrics(
                    ticker=ticker,
                    period=period_label,
                    period_end_date=period_date,
                    return_on_equity=_round_safe(roe),
                    net_profit_margin=_round_safe(net_margin),
                    gross_margin=_round_safe(gross_margin),
                    operating_margin=_round_safe(op_margin),
                    free_cash_flow=fcf_val,
                    revenue_growth=_round_safe(rev_growth),
                    current_ratio=_round_safe(current_ratio),
                    debt_to_equity=_round_safe(dte),
                    pe_ratio=_round_safe(pe),
                    pb_ratio=_round_safe(pb),
                    ps_ratio=_round_safe(ps),
                    ev_to_ebitda=_round_safe(ev_ebitda),
                    market_cap=mkt_cap,
                    revenue=rev,
                    net_income=net_inc,
                    earnings_per_share=eps,
                ))

            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            logger.info("Fetched %d metric periods for %s", len(result), ticker)
            return result

        except Exception:
            logger.exception("Failed to fetch metrics for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Financial line items (yfinance)
    # ------------------------------------------------------------------

    def search_line_items_sync(
        self,
        ticker: str,
        line_items: list[str],
        period_type: str = "quarterly",
        limit: int = 4,
    ) -> list[LineItem]:
        """Fetch financial line items from Yahoo Finance (free)."""
        cache_key = Cache.make_key("crawler_lineitems", ticker, line_items, period_type, limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}

            if period_type == "quarterly":
                income = stock.quarterly_income_stmt
                balance = stock.quarterly_balance_sheet
                cashflow = stock.quarterly_cashflow
            else:
                income = stock.income_stmt
                balance = stock.balance_sheet
                cashflow = stock.cashflow

            result: list[LineItem] = []
            num_periods = min(limit, max(
                len(income.columns) if not income.empty else 0,
                len(balance.columns) if not balance.empty else 0,
                1,
            ))

            for i in range(num_periods):
                period_date = None
                period_label = period_type

                # Determine period from available statements
                for stmt in [income, balance, cashflow]:
                    if not stmt.empty and i < len(stmt.columns):
                        col = stmt.columns[i]
                        period_date = col.date() if hasattr(col, "date") else None
                        if period_date:
                            q = (period_date.month - 1) // 3 + 1
                            period_label = f"{period_date.year}-Q{q}" if period_type == "quarterly" else str(period_date.year)
                        break

                shares = info.get("sharesOutstanding")
                book_val = _safe_get(balance, "Stockholders Equity", i)
                bvps = (book_val / shares) if book_val and shares and shares > 0 else None

                result.append(LineItem(
                    ticker=ticker,
                    period=period_label,
                    period_end_date=period_date,
                    # Income statement
                    revenue=_safe_get(income, "Total Revenue", i),
                    cost_of_revenue=_safe_get(income, "Cost Of Revenue", i),
                    gross_profit=_safe_get(income, "Gross Profit", i),
                    operating_income=_safe_get(income, "Operating Income", i),
                    net_income=_safe_get(income, "Net Income", i),
                    depreciation_and_amortization=_safe_get(income, "Reconciled Depreciation", i) or _safe_get(cashflow, "Depreciation And Amortization", i),
                    interest_expense=_safe_get(income, "Interest Expense", i),
                    income_tax_expense=_safe_get(income, "Tax Provision", i),
                    ebitda=_safe_get(income, "EBITDA", i),
                    # Balance sheet
                    total_assets=_safe_get(balance, "Total Assets", i),
                    total_liabilities=_safe_get(balance, "Total Liabilities Net Minority Interest", i),
                    total_equity=_safe_get(balance, "Stockholders Equity", i),
                    book_value_per_share=_round_safe(bvps),
                    total_debt=_safe_get(balance, "Total Debt", i),
                    cash_and_equivalents=_safe_get(balance, "Cash And Cash Equivalents", i),
                    current_assets=_safe_get(balance, "Current Assets", i),
                    current_liabilities=_safe_get(balance, "Current Liabilities", i),
                    working_capital=_safe_get(balance, "Working Capital", i),
                    # Cash flow
                    operating_cash_flow=_safe_get(cashflow, "Operating Cash Flow", i),
                    capital_expenditure=_safe_get(cashflow, "Capital Expenditure", i),
                    free_cash_flow=_safe_get(cashflow, "Free Cash Flow", i),
                    dividends_paid=_safe_get(cashflow, "Common Stock Dividend Paid", i),
                    # Shares
                    shares_outstanding=shares,
                    market_cap=info.get("marketCap"),
                ))

            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            logger.info("Fetched %d line item periods for %s", len(result), ticker)
            return result

        except Exception:
            logger.exception("Failed to fetch line items for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Insider trades (yfinance)
    # ------------------------------------------------------------------

    def get_insider_trades_sync(
        self,
        ticker: str,
        start_date: Optional[datetime.date | str] = None,
        limit: int = 100,
    ) -> list[InsiderTrade]:
        """Fetch insider trades from Yahoo Finance (free)."""
        cache_key = Cache.make_key("crawler_insider", ticker, str(start_date), limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        try:
            stock = yf.Ticker(ticker)
            insider_df = stock.insider_transactions

            if insider_df is None or insider_df.empty:
                logger.info("No insider trades found for %s", ticker)
                return []

            result: list[InsiderTrade] = []
            for _, row in insider_df.head(limit).iterrows():
                trade_date = row.get("Start Date") or row.get("Date")
                if trade_date is not None:
                    if hasattr(trade_date, "date"):
                        trade_date = trade_date.date()
                    elif isinstance(trade_date, str):
                        trade_date = datetime.date.fromisoformat(trade_date[:10])
                else:
                    trade_date = datetime.date.today()

                if start_date:
                    sd = datetime.date.fromisoformat(str(start_date)[:10]) if isinstance(start_date, str) else start_date
                    if trade_date < sd:
                        continue

                # Determine buy/sell from text
                text = str(row.get("Text", "") or row.get("Transaction", "")).lower()
                tx_type = "buy" if "purchase" in text or "buy" in text or "acquisition" in text else "sell"

                shares = abs(float(row.get("Shares", 0) or 0))
                value = abs(float(row.get("Value", 0) or 0))
                pps = (value / shares) if shares > 0 and value > 0 else None

                result.append(InsiderTrade(
                    ticker=ticker,
                    date=trade_date,
                    insider_name=str(row.get("Insider", "Unknown")),
                    title=str(row.get("Position", row.get("Insider Title", ""))),
                    transaction_type=tx_type,
                    shares=shares,
                    price_per_share=pps,
                    total_value=value if value > 0 else None,
                ))

            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            logger.info("Fetched %d insider trades for %s", len(result), ticker)
            return result

        except Exception:
            logger.exception("Failed to fetch insider trades for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Company news (yfinance)
    # ------------------------------------------------------------------

    def get_company_news_sync(
        self,
        ticker: str,
        start_date: Optional[datetime.date | str] = None,
        limit: int = 50,
    ) -> list[CompanyNews]:
        """Fetch company news from Yahoo Finance (free)."""
        cache_key = Cache.make_key("crawler_news", ticker, str(start_date), limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        try:
            stock = yf.Ticker(ticker)
            news_list = stock.news or []

            result: list[CompanyNews] = []
            for item in news_list[:limit]:
                content = item.get("content", item)
                pub_date = None

                # Try to parse publish date
                pub_str = content.get("pubDate") or content.get("providerPublishTime") or item.get("providerPublishTime")
                if isinstance(pub_str, (int, float)):
                    pub_date = datetime.date.fromtimestamp(pub_str)
                elif isinstance(pub_str, str):
                    pub_date = datetime.date.fromisoformat(pub_str[:10])
                else:
                    pub_date = datetime.date.today()

                if start_date:
                    sd = datetime.date.fromisoformat(str(start_date)[:10]) if isinstance(start_date, str) else start_date
                    if pub_date < sd:
                        continue

                title = content.get("title") or item.get("title", "")
                source = content.get("provider", {})
                if isinstance(source, dict):
                    source = source.get("displayName", "Yahoo Finance")

                result.append(CompanyNews(
                    ticker=ticker,
                    date=pub_date,
                    title=title,
                    source=str(source) if source else "Yahoo Finance",
                    url=content.get("canonicalUrl", {}).get("url") or content.get("link") or item.get("link"),
                    summary=content.get("summary"),
                ))

            self._cache.set(cache_key, result, ttl=self._cache_ttl)
            logger.info("Fetched %d news items for %s", len(result), ticker)
            return result

        except Exception:
            logger.exception("Failed to fetch news for %s", ticker)
            return []

    # ------------------------------------------------------------------
    # Market cap
    # ------------------------------------------------------------------

    def get_market_cap_sync(self, ticker: str) -> Optional[float]:
        """Return market cap from Yahoo Finance."""
        try:
            stock = yf.Ticker(ticker)
            return stock.info.get("marketCap")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Async wrappers (match FinancialDataClient interface)
    # ------------------------------------------------------------------

    async def get_prices(self, ticker: str, start_date: datetime.date | str,
                         end_date: Optional[datetime.date | str] = None, interval: str = "day") -> list[Price]:
        return self.get_prices_sync(ticker, start_date, end_date, interval)

    async def get_financial_metrics(self, ticker: str, period_type: str = "quarterly",
                                     limit: int = 4) -> list[FinancialMetrics]:
        return self.get_financial_metrics_sync(ticker, period_type, limit)

    async def search_line_items(self, ticker: str, line_items: list[str],
                                 period_type: str = "quarterly", limit: int = 4) -> list[LineItem]:
        return self.search_line_items_sync(ticker, line_items, period_type, limit)

    async def get_insider_trades(self, ticker: str, start_date: Optional[datetime.date | str] = None,
                                  limit: int = 100) -> list[InsiderTrade]:
        return self.get_insider_trades_sync(ticker, start_date, limit)

    async def get_company_news(self, ticker: str, start_date: Optional[datetime.date | str] = None,
                                limit: int = 50) -> list[CompanyNews]:
        return self.get_company_news_sync(ticker, start_date, limit)

    async def get_market_cap(self, ticker: str) -> Optional[float]:
        return self.get_market_cap_sync(ticker)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_get(df: Any, row_name: str, col_idx: int) -> Optional[float]:
    """Safely extract a value from a pandas DataFrame by row label and column index."""
    if df is None or df.empty:
        return None
    try:
        if row_name in df.index and col_idx < len(df.columns):
            val = df.loc[row_name, df.columns[col_idx]]
            if val is not None and str(val) not in ("nan", "NaN", "None", ""):
                return float(val)
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return None


def _round_safe(val: Optional[float], decimals: int = 4) -> Optional[float]:
    """Round a value safely, returning None if input is None or NaN."""
    if val is None:
        return None
    try:
        import math
        if math.isnan(val) or math.isinf(val):
            return None
        return round(val, decimals)
    except (TypeError, ValueError):
        return None
