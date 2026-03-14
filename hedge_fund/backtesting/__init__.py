"""Backtesting engine for historical portfolio simulation.

Provides a complete backtesting framework including:
- BacktestEngine: orchestrates multi-period simulations
- BacktestPortfolio: tracks positions, cash, and margin
- PerformanceMetrics: comprehensive risk-adjusted return calculations
- Benchmark comparison against SPY or any other ticker
"""

from hedge_fund.backtesting.engine import BacktestEngine, BacktestResult
from hedge_fund.backtesting.metrics import PerformanceMetrics, calculate_metrics, compare_to_benchmark
from hedge_fund.backtesting.portfolio import BacktestPortfolio

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BacktestPortfolio",
    "PerformanceMetrics",
    "calculate_metrics",
    "compare_to_benchmark",
]
