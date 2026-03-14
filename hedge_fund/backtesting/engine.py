"""Backtesting engine for the AI hedge fund.

Orchestrates multi-period simulations by:
1. Generating date windows across the backtest range.
2. Calling the hedge fund's agent graph for each window.
3. Executing resulting trade decisions against simulated market prices.
4. Recording snapshots and computing performance metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional, Sequence

from hedge_fund.backtesting.metrics import (
    PerformanceMetrics,
    PortfolioSnapshot,
    calculate_metrics,
    compare_to_benchmark,
)
from hedge_fund.backtesting.portfolio import (
    BacktestPortfolio,
    InsufficientFundsError,
    InsufficientSharesError,
    TradeRecord,
)
from hedge_fund.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Container for all outputs of a backtest run."""

    metrics: PerformanceMetrics
    snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    trade_history: list[TradeRecord] = field(default_factory=list)
    portfolio_summary: dict[str, Any] = field(default_factory=dict)
    benchmark_comparison: dict[str, float] = field(default_factory=dict)
    tickers: list[str] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = 100_000.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise the full result to a dictionary."""
        return {
            "tickers": self.tickers,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_cash": self.initial_cash,
            "final_value": self.snapshots[-1].total_value if self.snapshots else self.initial_cash,
            "metrics": self.metrics.to_dict(),
            "benchmark": self.benchmark_comparison,
            "portfolio": self.portfolio_summary,
            "num_snapshots": len(self.snapshots),
            "num_trades": len(self.trade_history),
        }


class BacktestEngine:
    """Run historical backtests using the AI hedge fund agent pipeline.

    Parameters
    ----------
    initial_cash : float
        Starting cash balance in USD.
    margin_requirement : float
        Margin requirement fraction for short positions.
    max_position_pct : float
        Maximum single-position size as a fraction of portfolio value.
    risk_free_rate : float
        Annualised risk-free rate for metric calculations.
    """

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        margin_requirement: float = 0.5,
        max_position_pct: float = 0.25,
        risk_free_rate: float = 0.045,
    ) -> None:
        self.portfolio = BacktestPortfolio(
            initial_cash=initial_cash,
            margin_requirement=margin_requirement,
            max_position_pct=max_position_pct,
        )
        self.trade_history: list[TradeRecord] = []
        self.portfolio_snapshots: list[PortfolioSnapshot] = []
        self.risk_free_rate = risk_free_rate
        self.initial_cash = initial_cash
        self._progress_callback: Optional[callable] = None

    def set_progress_callback(self, callback: callable) -> None:
        """Register a callback for progress updates.

        The callback signature is ``callback(step: int, total: int, message: str)``.
        """
        self._progress_callback = callback

    def _emit_progress(self, step: int, total: int, message: str) -> None:
        """Emit a progress event if a callback is registered."""
        if self._progress_callback:
            try:
                self._progress_callback(step, total, message)
            except Exception:
                pass  # Never let callback errors break the backtest
        logger.info("[%d/%d] %s", step, total, message)

    def run(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        step_months: int = 1,
        selected_analysts: Optional[list[str]] = None,
        model_name: str = "gpt-4.1",
        model_provider: str = "openai",
    ) -> BacktestResult:
        """Run the backtest over the specified date range.

        Parameters
        ----------
        tickers : list[str]
            Stock tickers to analyse and trade.
        start_date : str
            Start date in ISO format (YYYY-MM-DD).
        end_date : str
            End date in ISO format (YYYY-MM-DD).
        step_months : int
            Number of months to advance between analysis windows.
        selected_analysts : list[str], optional
            Which analyst agents to use.  ``None`` means all available.
        model_name : str
            LLM model identifier.
        model_provider : str
            LLM provider name.

        Returns
        -------
        BacktestResult
            Complete backtest results with metrics and trade log.
        """
        logger.info(
            "Starting backtest: tickers=%s, range=%s to %s, step=%d months",
            tickers, start_date, end_date, step_months,
        )

        # Generate date windows
        windows = self._generate_date_windows(start_date, end_date, step_months)
        if not windows:
            logger.warning("No date windows generated for range %s -> %s", start_date, end_date)
            return BacktestResult(
                metrics=PerformanceMetrics(total_return=0.0, annualized_return=0.0),
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                initial_cash=self.initial_cash,
            )

        total_steps = len(windows)
        self._emit_progress(0, total_steps, "Backtest initialised")

        # Record initial snapshot
        initial_prices = self._fetch_prices(tickers, start_date)
        self._record_snapshot(start_date, initial_prices)

        for step_idx, (window_start, window_end) in enumerate(windows, start=1):
            self._emit_progress(
                step_idx, total_steps,
                f"Analysing window {window_start} -> {window_end}",
            )

            try:
                # Get current prices for this window
                current_prices = self._fetch_prices(tickers, window_end)
                if not current_prices:
                    logger.warning("No price data for %s on %s, skipping", tickers, window_end)
                    continue

                # Run the hedge fund agent pipeline
                decisions = self._run_analysis(
                    tickers=tickers,
                    start_date=window_start,
                    end_date=window_end,
                    current_prices=current_prices,
                    selected_analysts=selected_analysts,
                    model_name=model_name,
                    model_provider=model_provider,
                )

                # Execute trade decisions
                for decision in decisions:
                    self._execute_trade(decision, current_prices, window_end)

                # Record snapshot after trades
                self._record_snapshot(window_end, current_prices)

            except Exception as exc:
                logger.error(
                    "Error in backtest window %s -> %s: %s",
                    window_start, window_end, exc,
                    exc_info=True,
                )
                # Record snapshot even on error to maintain continuity
                try:
                    fallback_prices = self._fetch_prices(tickers, window_end)
                    self._record_snapshot(window_end, fallback_prices or {})
                except Exception:
                    pass

        self._emit_progress(total_steps, total_steps, "Backtest complete")

        # Calculate performance metrics
        metrics = calculate_metrics(
            snapshots=self.portfolio_snapshots,
            trade_history=self.trade_history,
            risk_free_rate=self.risk_free_rate,
            initial_cash=self.initial_cash,
        )

        # Compare to benchmark
        benchmark_comparison = self._run_benchmark_comparison(start_date, end_date)

        # Build final portfolio summary
        final_prices = self._fetch_prices(tickers, end_date)
        portfolio_summary = self.portfolio.summary(final_prices or {})

        return BacktestResult(
            metrics=metrics,
            snapshots=self.portfolio_snapshots,
            trade_history=self.trade_history,
            portfolio_summary=portfolio_summary,
            benchmark_comparison=benchmark_comparison,
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            initial_cash=self.initial_cash,
        )

    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    def _execute_trade(
        self,
        decision: dict[str, Any],
        current_prices: dict[str, float],
        trade_date: str,
    ) -> Optional[TradeRecord]:
        """Execute a single trade decision against the portfolio.

        Parameters
        ----------
        decision : dict
            Must contain ``action``, ``ticker``, and ``quantity`` keys.
        current_prices : dict[str, float]
            Current market prices.
        trade_date : str
            ISO date string for the trade.

        Returns
        -------
        TradeRecord or None if the trade was skipped.
        """
        action = decision.get("action", "hold").lower()
        ticker = decision.get("ticker", "")
        quantity = int(decision.get("quantity", 0))

        if action == "hold" or quantity <= 0:
            return None

        price = current_prices.get(ticker)
        if price is None or price <= 0:
            logger.warning("No valid price for %s, skipping %s", ticker, action)
            return None

        record: Optional[TradeRecord] = None

        try:
            if action == "buy":
                # Auto-size if quantity exceeds what we can afford
                max_shares = self.portfolio.calculate_position_size(
                    ticker, price, current_prices,
                )
                shares = min(quantity, max_shares)
                if shares > 0:
                    record = self.portfolio.buy(ticker, shares, price)

            elif action == "sell":
                pos = self.portfolio.positions.get(ticker)
                if pos:
                    shares = min(quantity, int(pos["shares"]))
                    if shares > 0:
                        record = self.portfolio.sell(ticker, shares, price)

            elif action == "short":
                record = self.portfolio.short(ticker, quantity, price)

            elif action == "cover":
                pos = self.portfolio.short_positions.get(ticker)
                if pos:
                    shares = min(quantity, int(pos["shares"]))
                    if shares > 0:
                        record = self.portfolio.cover(ticker, shares, price)

            else:
                logger.warning("Unknown action '%s' for %s", action, ticker)

        except (InsufficientFundsError, InsufficientSharesError) as exc:
            logger.warning("Trade rejected: %s", exc)
            return None
        except Exception as exc:
            logger.error("Trade execution error: %s", exc, exc_info=True)
            return None

        if record is not None:
            record.date = trade_date
            self.trade_history.append(record)
            logger.info(
                "Executed %s %s x%d @ $%.2f on %s",
                record.action.upper(), record.ticker, record.shares,
                record.price, trade_date,
            )

        return record

    # ------------------------------------------------------------------
    # Analysis integration
    # ------------------------------------------------------------------

    def _run_analysis(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        current_prices: dict[str, float],
        selected_analysts: Optional[list[str]],
        model_name: str,
        model_provider: str,
    ) -> list[dict[str, Any]]:
        """Run the hedge fund agent graph and return trade decisions.

        This method attempts to import and invoke ``run_hedge_fund`` from the
        graph module.  If the graph is not available (e.g., during development
        or unit testing), it falls back to an empty decision list.

        Returns
        -------
        list[dict]
            Each dict has keys: action, ticker, quantity, confidence, reasoning.
        """
        try:
            from hedge_fund.graph.workflow import run_hedge_fund  # type: ignore[import-not-found]

            portfolio_state = self.portfolio.to_state()

            # Update position current prices
            for ticker in portfolio_state.positions:
                if ticker in current_prices:
                    portfolio_state.positions[ticker].current_price = current_prices[ticker]
            for ticker in portfolio_state.short_positions:
                if ticker in current_prices:
                    portfolio_state.short_positions[ticker].current_price = current_prices[ticker]

            result = run_hedge_fund(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                portfolio=portfolio_state,
                selected_analysts=selected_analysts,
                model_name=model_name,
                model_provider=model_provider,
            )

            # Extract decisions from the graph result.
            # run_hedge_fund returns either:
            #   - A dict with a "decisions" key (list or dict)
            #   - A dict mapping ticker -> TradeDecision directly
            #   - A list of trade decision dicts/objects
            if isinstance(result, dict):
                # Check for a "decisions" sub-key first
                decisions_raw = result.get("decisions", result)

                parsed: list[dict[str, Any]] = []

                if isinstance(decisions_raw, list):
                    items = decisions_raw
                elif isinstance(decisions_raw, dict):
                    # Could be {ticker: TradeDecision} or {ticker: {action, ...}}
                    items = list(decisions_raw.values())
                else:
                    items = []

                for d in items:
                    if isinstance(d, dict):
                        parsed.append({
                            "action": d.get("action", "hold"),
                            "ticker": d.get("ticker", ""),
                            "quantity": d.get("quantity", 0),
                            "confidence": d.get("confidence", 0),
                            "reasoning": d.get("reasoning", ""),
                        })
                    else:
                        parsed.append({
                            "action": getattr(d, "action", "hold"),
                            "ticker": getattr(d, "ticker", ""),
                            "quantity": getattr(d, "quantity", 0),
                            "confidence": getattr(d, "confidence", 0),
                            "reasoning": getattr(d, "reasoning", ""),
                        })

                return parsed

            elif isinstance(result, list):
                return [
                    {
                        "action": getattr(d, "action", d.get("action", "hold") if isinstance(d, dict) else "hold"),
                        "ticker": getattr(d, "ticker", d.get("ticker", "") if isinstance(d, dict) else ""),
                        "quantity": getattr(d, "quantity", d.get("quantity", 0) if isinstance(d, dict) else 0),
                        "confidence": getattr(d, "confidence", d.get("confidence", 0) if isinstance(d, dict) else 0),
                        "reasoning": getattr(d, "reasoning", d.get("reasoning", "") if isinstance(d, dict) else ""),
                    }
                    for d in result
                ]

            return []

        except ImportError:
            logger.warning(
                "Graph module not available. Returning empty decisions. "
                "Ensure hedge_fund.graph.state is implemented."
            )
            return []
        except Exception as exc:
            logger.error("Agent analysis failed: %s", exc, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def _fetch_prices(self, tickers: list[str], as_of_date: str) -> dict[str, float]:
        """Fetch closing prices for the given tickers on or before ``as_of_date``.

        Tries the Financial Datasets API client first, falls back to a
        simple data stub for testing.

        Returns
        -------
        dict[str, float]
            Mapping of ticker -> closing price.
        """
        prices: dict[str, float] = {}

        try:
            from hedge_fund.data.api import FinancialDataClient  # type: ignore[import-not-found]

            client = FinancialDataClient()

            for ticker in tickers:
                try:
                    # Look back up to 10 days to find a trading day
                    target = date.fromisoformat(as_of_date)
                    lookback_start = (target - timedelta(days=10)).isoformat()

                    price_data = client.get_prices(
                        ticker=ticker,
                        start_date=lookback_start,
                        end_date=as_of_date,
                    )
                    if price_data:
                        # Use the most recent available price
                        latest = max(price_data, key=lambda p: p.date if hasattr(p, "date") else "")
                        prices[ticker] = latest.close if hasattr(latest, "close") else float(latest.get("close", 0))
                    else:
                        logger.warning("No price data for %s on %s", ticker, as_of_date)
                except Exception as exc:
                    logger.warning("Price fetch failed for %s: %s", ticker, exc)

        except ImportError:
            logger.warning(
                "FinancialDataClient not available. "
                "Price data will be empty. Implement hedge_fund.data.api."
            )

        return prices

    def _run_benchmark_comparison(
        self, start_date: str, end_date: str, benchmark_ticker: str = "SPY"
    ) -> dict[str, float]:
        """Fetch benchmark prices and compare performance.

        Parameters
        ----------
        start_date : str
            Backtest start date.
        end_date : str
            Backtest end date.
        benchmark_ticker : str
            Benchmark ticker symbol (default SPY for S&P 500).

        Returns
        -------
        dict[str, float]
            Benchmark comparison metrics.
        """
        if len(self.portfolio_snapshots) < 2:
            return {}

        try:
            from hedge_fund.data.api import FinancialDataClient  # type: ignore[import-not-found]

            client = FinancialDataClient()
            price_data = client.get_prices(
                ticker=benchmark_ticker,
                start_date=start_date,
                end_date=end_date,
            )
            if not price_data:
                return {}

            benchmark_prices: list[tuple[str, float]] = [
                (
                    p.date.isoformat() if hasattr(p.date, "isoformat") else str(p.date),
                    p.close if hasattr(p, "close") else float(p.get("close", 0)),
                )
                for p in sorted(price_data, key=lambda x: x.date if hasattr(x, "date") else "")
            ]

            return compare_to_benchmark(
                snapshots=self.portfolio_snapshots,
                benchmark_prices=benchmark_prices,
                risk_free_rate=self.risk_free_rate,
            )

        except ImportError:
            logger.warning("Cannot run benchmark comparison: data client not available")
            return {}
        except Exception as exc:
            logger.warning("Benchmark comparison failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Snapshot recording
    # ------------------------------------------------------------------

    def _record_snapshot(self, as_of_date: str, current_prices: dict[str, float]) -> None:
        """Record a point-in-time portfolio snapshot."""
        total_value = self.portfolio.get_total_value(current_prices)
        long_value = self.portfolio.get_long_value(current_prices)
        short_value = self.portfolio.get_short_value(current_prices)

        snapshot = PortfolioSnapshot(
            date=as_of_date,
            total_value=total_value,
            cash=self.portfolio.cash,
            long_value=long_value,
            short_value=short_value,
            num_positions=len(self.portfolio.positions) + len(self.portfolio.short_positions),
        )
        self.portfolio_snapshots.append(snapshot)

    # ------------------------------------------------------------------
    # Date window generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_date_windows(
        start_date: str, end_date: str, step_months: int
    ) -> list[tuple[str, str]]:
        """Generate a list of (window_start, window_end) date pairs.

        Each window advances by ``step_months`` months.  The final window
        may be shorter if the remaining period is less than a full step.

        Parameters
        ----------
        start_date : str
            ISO date string for the backtest start.
        end_date : str
            ISO date string for the backtest end.
        step_months : int
            Number of months per analysis window.

        Returns
        -------
        list[tuple[str, str]]
            Ordered list of (start, end) ISO date strings.
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        if start >= end:
            return []

        windows: list[tuple[str, str]] = []
        current_start = start

        while current_start < end:
            # Advance by step_months
            month = current_start.month + step_months
            year = current_start.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1

            # Handle day overflow (e.g., Jan 31 + 1 month)
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            day = min(current_start.day, max_day)

            window_end = date(year, month, day)

            if window_end > end:
                window_end = end

            windows.append((current_start.isoformat(), window_end.isoformat()))
            current_start = window_end

        return windows

    def reset(self) -> None:
        """Reset the engine to its initial state for a new backtest run."""
        self.portfolio = BacktestPortfolio(
            initial_cash=self.initial_cash,
            margin_requirement=self.portfolio.margin_requirement,
            max_position_pct=self.portfolio.max_position_pct,
        )
        self.trade_history.clear()
        self.portfolio_snapshots.clear()
