"""Performance metrics for backtesting.

Computes risk-adjusted returns, drawdown analysis, and benchmark
comparisons from portfolio snapshots and trade history.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# Approximate trading days per year
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Point-in-time record of portfolio value."""

    date: str  # ISO format date string
    total_value: float
    cash: float
    long_value: float
    short_value: float
    num_positions: int


@dataclass(frozen=True)
class PerformanceMetrics:
    """Comprehensive performance metrics for a backtest run."""

    # Returns
    total_return: float  # as a decimal (0.10 = 10%)
    annualized_return: float  # CAGR
    monthly_returns: list[float] = field(default_factory=list)

    # Risk-adjusted
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Risk
    max_drawdown: float = 0.0  # as a decimal (0.10 = 10%)
    max_drawdown_start: str = ""
    max_drawdown_end: str = ""
    volatility: float = 0.0  # annualised

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Benchmark comparison (filled by compare_to_benchmark)
    benchmark_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dictionary for JSON output."""
        return {
            "total_return_pct": round(self.total_return * 100, 2),
            "annualized_return_pct": round(self.annualized_return * 100, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "max_drawdown_period": f"{self.max_drawdown_start} -> {self.max_drawdown_end}",
            "volatility_pct": round(self.volatility * 100, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate_pct": round(self.win_rate * 100, 1),
            "profit_factor": round(self.profit_factor, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
            "benchmark_return_pct": round(self.benchmark_return * 100, 2),
            "alpha_pct": round(self.alpha * 100, 2),
            "beta": round(self.beta, 3),
            "information_ratio": round(self.information_ratio, 3),
        }


def calculate_metrics(
    snapshots: Sequence[PortfolioSnapshot],
    trade_history: Sequence[Any],
    risk_free_rate: float = 0.045,
    initial_cash: float = 100_000.0,
) -> PerformanceMetrics:
    """Calculate comprehensive performance metrics from backtest results.

    Parameters
    ----------
    snapshots : Sequence[PortfolioSnapshot]
        Chronologically ordered portfolio snapshots (at least 2).
    trade_history : Sequence
        List of TradeRecord objects from the backtest.
    risk_free_rate : float
        Annualised risk-free rate for Sharpe/Sortino calculations.
    initial_cash : float
        Starting portfolio value.

    Returns
    -------
    PerformanceMetrics
    """
    if len(snapshots) < 2:
        return PerformanceMetrics(
            total_return=0.0,
            annualized_return=0.0,
            total_trades=len(trade_history),
        )

    values = np.array([s.total_value for s in snapshots], dtype=np.float64)

    # ---- Returns ----
    total_return = (values[-1] / initial_cash) - 1.0

    # Parse dates to calculate time span
    dates = [_parse_date(s.date) for s in snapshots]
    years = max((dates[-1] - dates[0]).days / 365.25, 1 / 365.25)

    # CAGR
    if values[-1] > 0 and initial_cash > 0:
        annualized_return = (values[-1] / initial_cash) ** (1.0 / years) - 1.0
    else:
        annualized_return = -1.0

    # Period returns (between snapshots)
    period_returns = np.diff(values) / values[:-1]
    monthly_returns = period_returns.tolist()

    # ---- Volatility ----
    if len(period_returns) > 1:
        # Estimate periods per year
        avg_days_per_period = max((dates[-1] - dates[0]).days / max(len(period_returns), 1), 1)
        periods_per_year = 365.25 / avg_days_per_period
        period_vol = float(np.std(period_returns, ddof=1))
        annualized_vol = period_vol * math.sqrt(periods_per_year)
    else:
        annualized_vol = 0.0
        periods_per_year = 12.0

    # ---- Sharpe Ratio ----
    if annualized_vol > 0:
        sharpe = (annualized_return - risk_free_rate) / annualized_vol
    else:
        sharpe = 0.0

    # ---- Sortino Ratio (downside deviation) ----
    downside_returns = period_returns[period_returns < 0]
    if len(downside_returns) > 0:
        downside_dev = float(np.std(downside_returns, ddof=1)) * math.sqrt(periods_per_year)
        sortino = (annualized_return - risk_free_rate) / downside_dev if downside_dev > 0 else 0.0
    else:
        sortino = 0.0

    # ---- Maximum Drawdown ----
    max_dd, dd_start_idx, dd_end_idx = _calculate_max_drawdown(values)
    dd_start_date = snapshots[dd_start_idx].date if dd_start_idx < len(snapshots) else ""
    dd_end_date = snapshots[dd_end_idx].date if dd_end_idx < len(snapshots) else ""

    # ---- Calmar Ratio ----
    calmar = annualized_return / max_dd if max_dd > 0 else 0.0

    # ---- Trade Statistics ----
    trade_stats = _calculate_trade_stats(trade_history)

    return PerformanceMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        monthly_returns=monthly_returns,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown=max_dd,
        max_drawdown_start=dd_start_date,
        max_drawdown_end=dd_end_date,
        volatility=annualized_vol,
        **trade_stats,
    )


def compare_to_benchmark(
    snapshots: Sequence[PortfolioSnapshot],
    benchmark_prices: Sequence[tuple[str, float]],
    risk_free_rate: float = 0.045,
) -> dict[str, float]:
    """Compare portfolio performance against a benchmark.

    Parameters
    ----------
    snapshots : Sequence[PortfolioSnapshot]
        Portfolio snapshots from the backtest.
    benchmark_prices : Sequence[tuple[str, float]]
        Chronologically ordered (date_str, price) pairs for the benchmark.
    risk_free_rate : float
        Annualised risk-free rate.

    Returns
    -------
    dict with keys: benchmark_return, alpha, beta, information_ratio,
    correlation, tracking_error.
    """
    if len(snapshots) < 2 or len(benchmark_prices) < 2:
        return {
            "benchmark_return": 0.0,
            "alpha": 0.0,
            "beta": 0.0,
            "information_ratio": 0.0,
            "correlation": 0.0,
            "tracking_error": 0.0,
        }

    # Portfolio returns
    port_values = np.array([s.total_value for s in snapshots], dtype=np.float64)
    port_returns = np.diff(port_values) / port_values[:-1]

    # Benchmark returns
    bench_values = np.array([p[1] for p in benchmark_prices], dtype=np.float64)

    # Align lengths (use the shorter of the two)
    min_len = min(len(port_returns), len(bench_values) - 1)
    port_returns = port_returns[:min_len]
    bench_returns = np.diff(bench_values[:min_len + 1]) / bench_values[:min_len]

    # Total benchmark return
    benchmark_total = (bench_values[-1] / bench_values[0]) - 1.0

    # Beta = Cov(rp, rb) / Var(rb)
    if len(port_returns) > 1 and np.var(bench_returns) > 0:
        covariance = float(np.cov(port_returns, bench_returns)[0][1])
        bench_var = float(np.var(bench_returns, ddof=1))
        beta = covariance / bench_var
    else:
        beta = 1.0

    # Portfolio total return
    port_total = (port_values[-1] / port_values[0]) - 1.0

    # Alpha (Jensen's alpha, simplified)
    # alpha = Rp - [Rf + beta * (Rb - Rf)]
    alpha = port_total - (risk_free_rate + beta * (benchmark_total - risk_free_rate))

    # Tracking error and information ratio
    excess_returns = port_returns - bench_returns
    tracking_error = float(np.std(excess_returns, ddof=1)) if len(excess_returns) > 1 else 0.0

    # Annualise tracking error
    dates = [_parse_date(s.date) for s in snapshots]
    avg_days = max((dates[-1] - dates[0]).days / max(len(port_returns), 1), 1)
    periods_per_year = 365.25 / avg_days
    tracking_error_annual = tracking_error * math.sqrt(periods_per_year)

    info_ratio = (
        float(np.mean(excess_returns)) * periods_per_year / tracking_error_annual
        if tracking_error_annual > 0
        else 0.0
    )

    # Correlation
    if len(port_returns) > 1:
        corr_matrix = np.corrcoef(port_returns, bench_returns)
        correlation = float(corr_matrix[0][1]) if not np.isnan(corr_matrix[0][1]) else 0.0
    else:
        correlation = 0.0

    return {
        "benchmark_return": benchmark_total,
        "alpha": alpha,
        "beta": beta,
        "information_ratio": info_ratio,
        "correlation": correlation,
        "tracking_error": tracking_error_annual,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _calculate_max_drawdown(values: np.ndarray) -> tuple[float, int, int]:
    """Calculate maximum drawdown from a series of portfolio values.

    Returns
    -------
    tuple of (max_drawdown, peak_index, trough_index)
    """
    if len(values) == 0:
        return 0.0, 0, 0

    peak = values[0]
    peak_idx = 0
    max_dd = 0.0
    dd_start = 0
    dd_end = 0

    for i in range(1, len(values)):
        if values[i] > peak:
            peak = values[i]
            peak_idx = i

        drawdown = (peak - values[i]) / peak if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown
            dd_start = peak_idx
            dd_end = i

    return max_dd, dd_start, dd_end


def _calculate_trade_stats(trade_history: Sequence[Any]) -> dict[str, Any]:
    """Extract trade win/loss statistics from trade records.

    Parameters
    ----------
    trade_history : Sequence
        List of TradeRecord objects (must have ``realized_pnl`` attribute).

    Returns
    -------
    dict with trade statistic keys suitable for unpacking into PerformanceMetrics.
    """
    # Only count trades that close positions (sell / cover) for win/loss
    closing_trades = [
        t for t in trade_history
        if hasattr(t, "action") and t.action in ("sell", "cover")
    ]

    total_trades = len(trade_history)
    if not closing_trades:
        return {
            "total_trades": total_trades,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
        }

    pnls = [getattr(t, "realized_pnl", 0.0) for t in closing_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    gross_profits = sum(wins) if wins else 0.0
    gross_losses = abs(sum(losses)) if losses else 0.0

    return {
        "total_trades": total_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": len(wins) / len(closing_trades) if closing_trades else 0.0,
        "profit_factor": gross_profits / gross_losses if gross_losses > 0 else float("inf"),
        "avg_win": gross_profits / len(wins) if wins else 0.0,
        "avg_loss": -(gross_losses / len(losses)) if losses else 0.0,
        "largest_win": max(wins) if wins else 0.0,
        "largest_loss": min(losses) if losses else 0.0,
    }


def _parse_date(date_str: str) -> date:
    """Parse an ISO format date string to a ``date`` object."""
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return date.today()
