"""Data models and API integration for financial data ingestion.

Uses FreeCrawler (yfinance, free) when no FINANCIAL_DATASETS_API_KEY is set.
Falls back to the paid FinancialDataClient when a key is configured.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hedge_fund.config import get_settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hedge_fund.data.api import FinancialDataClient
    from hedge_fund.data.crawler import FreeCrawler


def get_data_client() -> FinancialDataClient | FreeCrawler:
    """Return the appropriate data client based on configuration.

    If FINANCIAL_DATASETS_API_KEY is set, uses the paid API.
    Otherwise, uses the free yfinance-based crawler.
    """
    settings = get_settings()
    if settings.financial_datasets_api_key:
        from hedge_fund.data.api import FinancialDataClient
        logger.info("Using paid FinancialDataClient (API key configured)")
        return FinancialDataClient()
    else:
        from hedge_fund.data.crawler import FreeCrawler
        logger.info("Using free FreeCrawler (yfinance) — no API key needed")
        return FreeCrawler(cache_ttl=settings.cache_ttl_seconds)
