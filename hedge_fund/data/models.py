"""Financial data models used throughout the hedge fund application.

All models use Pydantic v2 for validation and serialization.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SignalDirection(str, Enum):
    """Direction of an analyst signal."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class AnalystSignal(BaseModel):
    """A signal produced by an analyst agent for a single ticker.

    This is the standard output format that every analyst agent must produce.
    """

    signal: SignalDirection = Field(description="Directional signal: bullish, bearish, or neutral")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the signal, 0.0 to 1.0")
    reasoning: str = Field(description="Human-readable explanation of the signal rationale")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Agent-specific detail data")


class Price(BaseModel):
    """Daily OHLCV price bar for a security."""

    ticker: str
    date: datetime.date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjusted_close: float | None = None

    class Config:
        frozen = True


class FinancialMetrics(BaseModel):
    """Quarterly or annual financial metrics / ratios for a company."""

    ticker: str
    period: str = Field(description="Period identifier, e.g. '2024-Q3' or '2024'")
    period_end_date: datetime.date | None = None
    currency: str = "USD"

    # Profitability
    return_on_equity: float | None = None
    net_profit_margin: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    free_cash_flow: float | None = None

    # Growth
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    fcf_growth: float | None = None

    # Liquidity & solvency
    current_ratio: float | None = None
    debt_to_equity: float | None = None
    quick_ratio: float | None = None
    interest_coverage: float | None = None

    # Valuation
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_to_ebitda: float | None = None
    market_cap: float | None = None

    # Revenue / earnings absolutes
    revenue: float | None = None
    net_income: float | None = None
    earnings_per_share: float | None = None


class FinancialLineItem(BaseModel):
    """Individual financial statement line item (income statement, balance sheet, cash flow)."""

    ticker: str
    period: str
    period_end_date: datetime.date | None = None
    currency: str = "USD"

    # Income statement
    revenue: float | None = None
    cost_of_revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    depreciation_and_amortization: float | None = None
    interest_expense: float | None = None
    income_tax_expense: float | None = None
    ebitda: float | None = None

    # Balance sheet
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None
    book_value_per_share: float | None = None
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    working_capital: float | None = None

    # Cash flow
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    free_cash_flow: float | None = None
    dividends_paid: float | None = None

    # Shares
    shares_outstanding: float | None = None
    market_cap: float | None = None


class InsiderTrade(BaseModel):
    """Record of an insider trade (buy or sell) for a given ticker."""

    ticker: str
    date: datetime.date
    insider_name: str
    title: str | None = None
    transaction_type: str = Field(description="'buy' or 'sell'")
    shares: float
    price_per_share: float | None = None
    total_value: float | None = None


class CompanyNews(BaseModel):
    """A news headline or article related to a company."""

    ticker: str
    date: datetime.date
    title: str
    source: str | None = None
    url: str | None = None
    summary: str | None = None
    sentiment: str | None = None


# ---------------------------------------------------------------------------
# Alias: the API layer and several agents import ``LineItem`` rather than
# ``FinancialLineItem``.  Keep both names pointing to the same class.
# ---------------------------------------------------------------------------
LineItem = FinancialLineItem


# ---------------------------------------------------------------------------
# Portfolio & risk models used by the graph state and decision agents
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """A single position in the portfolio."""

    ticker: str
    shares: float = 0.0
    avg_cost: float = 0.0
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.shares * (self.current_price - self.avg_cost)


class PortfolioState(BaseModel):
    """Snapshot of the portfolio at a point in time."""

    cash: float = Field(default=100_000.0, description="Available cash in USD")
    positions: dict[str, Position] = Field(default_factory=dict, description="Ticker -> Position")
    total_value: float = Field(default=100_000.0, description="Cash + market value of all positions")
    realized_pnl: float = Field(default=0.0, description="Cumulative realized P&L")


class RiskAssessment(BaseModel):
    """Risk assessment output from the risk manager agent."""

    ticker: str
    risk_score: float = Field(ge=0.0, le=1.0, description="Overall risk score 0-1 (1 = highest risk)")
    max_position_size: float = Field(description="Maximum recommended position size in USD")
    reasoning: str = Field(default="", description="Explanation of risk factors")
    risk_factors: dict[str, Any] = Field(default_factory=dict, description="Individual risk factor scores")
