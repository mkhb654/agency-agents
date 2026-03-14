"""Portfolio simulation for backtesting.

Tracks long/short positions, cash, margin usage, and realised gains
throughout a backtest run.  Designed for use by BacktestEngine but also
usable standalone for unit-testing trade logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from hedge_fund.data.models import Position, PortfolioState

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Immutable record of an executed trade."""

    date: str
    ticker: str
    action: str  # buy, sell, short, cover
    shares: int
    price: float
    total_value: float
    realized_pnl: float = 0.0

    @property
    def is_profitable(self) -> bool:
        """Return True if the trade generated a positive realised P&L."""
        return self.realized_pnl > 0.0


class InsufficientFundsError(Exception):
    """Raised when a buy/short cannot be funded."""


class InsufficientSharesError(Exception):
    """Raised when selling/covering more shares than held."""


class BacktestPortfolio:
    """Simulated portfolio that tracks positions, cash, and margin.

    Parameters
    ----------
    initial_cash : float
        Starting cash balance in USD.
    margin_requirement : float
        Fraction of short notional that must be held as margin (0-1).
    max_position_pct : float
        Maximum fraction of total portfolio value for a single position.
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        margin_requirement: float = 0.5,
        max_position_pct: float = 0.25,
    ) -> None:
        self.initial_cash: float = initial_cash
        self.cash: float = initial_cash
        self.margin_requirement: float = margin_requirement
        self.max_position_pct: float = max_position_pct

        # {ticker: {"shares": int, "cost_basis": float, "avg_price": float}}
        self.positions: dict[str, dict[str, float]] = {}
        self.short_positions: dict[str, dict[str, float]] = {}
        self.margin_used: float = 0.0

        # Realised gains tracked per ticker and by side
        self.realized_gains: dict[str, dict[str, float]] = {
            "long": {},
            "short": {},
        }

    # ------------------------------------------------------------------
    # Core trade operations
    # ------------------------------------------------------------------

    def buy(self, ticker: str, shares: int, price: float) -> TradeRecord:
        """Open or add to a long position.

        Parameters
        ----------
        ticker : str
            Stock ticker.
        shares : int
            Number of shares to buy (must be > 0).
        price : float
            Per-share execution price.

        Returns
        -------
        TradeRecord
            Record of the executed trade.

        Raises
        ------
        InsufficientFundsError
            If cash is insufficient for the purchase.
        ValueError
            If *shares* or *price* is non-positive.
        """
        if shares <= 0:
            raise ValueError(f"shares must be positive, got {shares}")
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")

        cost = shares * price
        if cost > self.cash:
            raise InsufficientFundsError(
                f"Cannot buy {shares} shares of {ticker} at ${price:.2f} "
                f"(cost=${cost:,.2f}, cash=${self.cash:,.2f})"
            )

        self.cash -= cost

        if ticker in self.positions:
            pos = self.positions[ticker]
            old_shares = pos["shares"]
            old_cost = pos["cost_basis"]
            new_shares = old_shares + shares
            new_cost = old_cost + cost
            pos["shares"] = new_shares
            pos["cost_basis"] = new_cost
            pos["avg_price"] = new_cost / new_shares
        else:
            self.positions[ticker] = {
                "shares": float(shares),
                "cost_basis": cost,
                "avg_price": price,
            }

        logger.info("BUY  %s x%d @ $%.2f = $%.2f", ticker, shares, price, cost)
        return TradeRecord(
            date="",
            ticker=ticker,
            action="buy",
            shares=shares,
            price=price,
            total_value=cost,
        )

    def sell(self, ticker: str, shares: int, price: float) -> TradeRecord:
        """Reduce or close a long position.

        Parameters
        ----------
        ticker : str
            Stock ticker.
        shares : int
            Number of shares to sell (must be > 0).
        price : float
            Per-share execution price.

        Returns
        -------
        TradeRecord
            Record of the executed trade including realised P&L.

        Raises
        ------
        InsufficientSharesError
            If the position holds fewer shares than requested.
        """
        if shares <= 0:
            raise ValueError(f"shares must be positive, got {shares}")
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")

        if ticker not in self.positions:
            raise InsufficientSharesError(f"No long position in {ticker}")

        pos = self.positions[ticker]
        if shares > pos["shares"]:
            raise InsufficientSharesError(
                f"Cannot sell {shares} shares of {ticker} "
                f"(only hold {int(pos['shares'])})"
            )

        avg_price = pos["avg_price"]
        proceeds = shares * price
        cost_portion = shares * avg_price
        realized_pnl = proceeds - cost_portion

        self.cash += proceeds
        pos["shares"] -= shares
        pos["cost_basis"] -= cost_portion

        # Track realised gains
        self.realized_gains["long"].setdefault(ticker, 0.0)
        self.realized_gains["long"][ticker] += realized_pnl

        # Remove position if fully closed
        if pos["shares"] <= 0:
            del self.positions[ticker]

        logger.info(
            "SELL %s x%d @ $%.2f = $%.2f (P&L: $%.2f)",
            ticker, shares, price, proceeds, realized_pnl,
        )
        return TradeRecord(
            date="",
            ticker=ticker,
            action="sell",
            shares=shares,
            price=price,
            total_value=proceeds,
            realized_pnl=realized_pnl,
        )

    def short(self, ticker: str, shares: int, price: float) -> TradeRecord:
        """Open or add to a short position.

        Margin is reserved equal to ``shares * price * margin_requirement``.

        Parameters
        ----------
        ticker : str
            Stock ticker.
        shares : int
            Number of shares to short (must be > 0).
        price : float
            Per-share execution price.

        Returns
        -------
        TradeRecord

        Raises
        ------
        InsufficientFundsError
            If margin capacity is insufficient.
        """
        if shares <= 0:
            raise ValueError(f"shares must be positive, got {shares}")
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")

        notional = shares * price
        required_margin = notional * self.margin_requirement

        if required_margin > self.cash:
            raise InsufficientFundsError(
                f"Cannot short {shares} shares of {ticker} at ${price:.2f} "
                f"(margin=${required_margin:,.2f}, cash=${self.cash:,.2f})"
            )

        # Reserve margin from cash
        self.cash -= required_margin
        self.margin_used += required_margin

        # Credit proceeds (held as collateral internally)
        # In a real brokerage the short-sale proceeds stay with the broker.
        # Here we model it as: cash goes down by margin, position tracks the
        # obligation.  The gain/loss is realised on cover.

        if ticker in self.short_positions:
            pos = self.short_positions[ticker]
            old_shares = pos["shares"]
            old_cost = pos["cost_basis"]
            new_shares = old_shares + shares
            new_cost = old_cost + notional
            pos["shares"] = new_shares
            pos["cost_basis"] = new_cost
            pos["avg_price"] = new_cost / new_shares
        else:
            self.short_positions[ticker] = {
                "shares": float(shares),
                "cost_basis": notional,
                "avg_price": price,
            }

        logger.info(
            "SHORT %s x%d @ $%.2f (margin=$%.2f)",
            ticker, shares, price, required_margin,
        )
        return TradeRecord(
            date="",
            ticker=ticker,
            action="short",
            shares=shares,
            price=price,
            total_value=notional,
        )

    def cover(self, ticker: str, shares: int, price: float) -> TradeRecord:
        """Reduce or close a short position (buy-to-cover).

        Parameters
        ----------
        ticker : str
            Stock ticker.
        shares : int
            Number of shares to cover (must be > 0).
        price : float
            Per-share execution price.

        Returns
        -------
        TradeRecord
            Record of the executed trade including realised P&L.

        Raises
        ------
        InsufficientSharesError
            If the short position holds fewer shares than requested.
        """
        if shares <= 0:
            raise ValueError(f"shares must be positive, got {shares}")
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")

        if ticker not in self.short_positions:
            raise InsufficientSharesError(f"No short position in {ticker}")

        pos = self.short_positions[ticker]
        if shares > pos["shares"]:
            raise InsufficientSharesError(
                f"Cannot cover {shares} shares of {ticker} "
                f"(only short {int(pos['shares'])})"
            )

        avg_price = pos["avg_price"]
        cover_cost = shares * price
        original_notional = shares * avg_price

        # P&L = (entry price - exit price) * shares  (profit when price drops)
        realized_pnl = (avg_price - price) * shares

        # Release margin proportionally
        margin_per_share = avg_price * self.margin_requirement
        margin_released = shares * margin_per_share
        self.margin_used = max(0.0, self.margin_used - margin_released)

        # Return margin + P&L to cash
        self.cash += margin_released + realized_pnl

        # Track realised gains
        self.realized_gains["short"].setdefault(ticker, 0.0)
        self.realized_gains["short"][ticker] += realized_pnl

        pos["shares"] -= shares
        pos["cost_basis"] -= original_notional

        if pos["shares"] <= 0:
            del self.short_positions[ticker]

        logger.info(
            "COVER %s x%d @ $%.2f (P&L: $%.2f)",
            ticker, shares, price, realized_pnl,
        )
        return TradeRecord(
            date="",
            ticker=ticker,
            action="cover",
            shares=shares,
            price=price,
            total_value=cover_cost,
            realized_pnl=realized_pnl,
        )

    # ------------------------------------------------------------------
    # Valuation helpers
    # ------------------------------------------------------------------

    def get_total_value(self, current_prices: dict[str, float]) -> float:
        """Calculate net liquidation value given current market prices.

        Parameters
        ----------
        current_prices : dict[str, float]
            Mapping of ticker -> current price.

        Returns
        -------
        float
            Net portfolio value (cash + longs - short obligations + margin held).
        """
        long_value = sum(
            pos["shares"] * current_prices.get(ticker, pos["avg_price"])
            for ticker, pos in self.positions.items()
        )

        # Short P&L: we owe the current value but have margin locked.
        # Net short value = margin_used - current short obligation
        short_obligation = sum(
            pos["shares"] * current_prices.get(ticker, pos["avg_price"])
            for ticker, pos in self.short_positions.items()
        )
        # Unrealised short P&L: we sold at avg_price, owe at current price
        short_entry_value = sum(
            pos["shares"] * pos["avg_price"]
            for pos in self.short_positions.values()
        )
        unrealized_short_pnl = short_entry_value - short_obligation

        return self.cash + long_value + self.margin_used + unrealized_short_pnl

    def get_long_value(self, current_prices: dict[str, float]) -> float:
        """Return the total market value of all long positions."""
        return sum(
            pos["shares"] * current_prices.get(ticker, pos["avg_price"])
            for ticker, pos in self.positions.items()
        )

    def get_short_value(self, current_prices: dict[str, float]) -> float:
        """Return the total market value (obligation) of all short positions."""
        return sum(
            pos["shares"] * current_prices.get(ticker, pos["avg_price"])
            for ticker, pos in self.short_positions.items()
        )

    def get_total_realized_pnl(self) -> float:
        """Return total realised P&L across all closed positions."""
        long_pnl = sum(self.realized_gains["long"].values())
        short_pnl = sum(self.realized_gains["short"].values())
        return long_pnl + short_pnl

    # ------------------------------------------------------------------
    # Position sizing helper
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        ticker: str,
        price: float,
        current_prices: dict[str, float],
        target_pct: Optional[float] = None,
    ) -> int:
        """Calculate the maximum number of shares that can be purchased.

        Respects both cash constraints and the max single-position size limit.

        Parameters
        ----------
        ticker : str
            Stock ticker.
        price : float
            Per-share price.
        current_prices : dict[str, float]
            Current market prices for portfolio valuation.
        target_pct : float, optional
            Target allocation as a fraction of portfolio value.
            Defaults to ``self.max_position_pct``.

        Returns
        -------
        int
            Maximum whole shares that can be bought.
        """
        if price <= 0:
            return 0

        portfolio_value = self.get_total_value(current_prices)
        pct = target_pct if target_pct is not None else self.max_position_pct

        # Max position size by portfolio limit
        max_by_portfolio = portfolio_value * pct

        # Subtract existing exposure
        existing_exposure = 0.0
        if ticker in self.positions:
            existing_exposure = self.positions[ticker]["shares"] * price

        available_allocation = max(0.0, max_by_portfolio - existing_exposure)
        max_by_cash = self.cash

        max_notional = min(available_allocation, max_by_cash)
        return int(max_notional // price)

    # ------------------------------------------------------------------
    # State serialisation
    # ------------------------------------------------------------------

    def to_state(self) -> PortfolioState:
        """Convert current portfolio to a ``PortfolioState`` Pydantic model.

        This is used to pass portfolio state into LangGraph agent nodes.
        """
        positions: dict[str, Position] = {}
        for ticker, pos in self.positions.items():
            positions[ticker] = Position(
                ticker=ticker,
                shares=pos["shares"],
                avg_entry_price=pos["avg_price"],
                current_price=pos["avg_price"],  # will be refreshed by caller
            )

        short_positions: dict[str, Position] = {}
        for ticker, pos in self.short_positions.items():
            short_positions[ticker] = Position(
                ticker=ticker,
                shares=-pos["shares"],  # negative for short
                avg_entry_price=pos["avg_price"],
                current_price=pos["avg_price"],
            )

        return PortfolioState(
            cash=self.cash,
            positions=positions,
            short_positions=short_positions,
            margin_used=self.margin_used,
            realized_gains=self.get_total_realized_pnl(),
        )

    def summary(self, current_prices: dict[str, float]) -> dict:
        """Return a human-readable summary dictionary."""
        total_value = self.get_total_value(current_prices)
        return {
            "total_value": round(total_value, 2),
            "cash": round(self.cash, 2),
            "long_positions": {
                t: {
                    "shares": int(p["shares"]),
                    "avg_price": round(p["avg_price"], 2),
                    "current_price": round(current_prices.get(t, p["avg_price"]), 2),
                    "market_value": round(p["shares"] * current_prices.get(t, p["avg_price"]), 2),
                    "unrealized_pnl": round(
                        p["shares"] * (current_prices.get(t, p["avg_price"]) - p["avg_price"]), 2
                    ),
                }
                for t, p in self.positions.items()
            },
            "short_positions": {
                t: {
                    "shares": int(p["shares"]),
                    "avg_price": round(p["avg_price"], 2),
                    "current_price": round(current_prices.get(t, p["avg_price"]), 2),
                    "unrealized_pnl": round(
                        (p["avg_price"] - current_prices.get(t, p["avg_price"])) * p["shares"], 2
                    ),
                }
                for t, p in self.short_positions.items()
            },
            "margin_used": round(self.margin_used, 2),
            "realized_pnl": round(self.get_total_realized_pnl(), 2),
            "return_pct": round(((total_value / self.initial_cash) - 1) * 100, 2),
        }

    def __repr__(self) -> str:
        return (
            f"BacktestPortfolio(cash=${self.cash:,.2f}, "
            f"longs={len(self.positions)}, shorts={len(self.short_positions)})"
        )
