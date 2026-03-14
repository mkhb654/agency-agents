"""Risk Manager Agent — pure rule-based (no LLM).

Performs quantitative risk analysis per ticker and computes position limits
based on volatility regime, correlation exposure, Value at Risk, and maximum
drawdown.  The output constrains what the portfolio manager is allowed to do.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np

from hedge_fund.config import get_settings
from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import PortfolioState, Price, RiskAssessment
from hedge_fund.graph.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TRADING_DAYS_PER_YEAR = 252
_VAR_CONFIDENCE_Z = 1.6449  # z-score for 95% confidence
_LOOKBACK_YEARS = 1  # lookback for volatility percentile ranking
_DEFAULT_MAX_POSITION_PCT = 0.25  # fallback if regime calc fails


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_daily_returns(prices: list[Price]) -> np.ndarray:
    """Compute daily log returns from a sorted price series.

    Parameters
    ----------
    prices:
        Price bars sorted by date ascending.

    Returns
    -------
    np.ndarray
        Array of daily log returns (length = len(prices) - 1).
    """
    if len(prices) < 2:
        return np.array([], dtype=np.float64)
    closes = np.array([p.close for p in prices], dtype=np.float64)
    # Guard against zero / negative prices
    closes = np.where(closes > 0, closes, np.nan)
    log_returns = np.diff(np.log(closes))
    return log_returns[~np.isnan(log_returns)]


def _annualized_volatility(daily_returns: np.ndarray) -> float:
    """Annualize the standard deviation of daily returns.

    Returns
    -------
    float
        Annualized volatility as a decimal (e.g. 0.25 = 25%).
    """
    if len(daily_returns) < 2:
        return 0.0
    return float(np.std(daily_returns, ddof=1) * math.sqrt(_TRADING_DAYS_PER_YEAR))


def _volatility_percentile(
    daily_returns: np.ndarray,
    window: int = 21,
) -> float:
    """Compute the percentile rank of the trailing *window*-day volatility
    relative to all rolling windows in the full series.

    Returns
    -------
    float
        Percentile in [0, 100].
    """
    if len(daily_returns) < window + 1:
        return 50.0  # not enough data — assume median

    rolling_vols: list[float] = []
    for i in range(window, len(daily_returns) + 1):
        segment = daily_returns[i - window : i]
        rolling_vols.append(float(np.std(segment, ddof=1)))

    if not rolling_vols:
        return 50.0

    current_vol = rolling_vols[-1]
    rank = sum(1 for v in rolling_vols if v <= current_vol) / len(rolling_vols) * 100.0
    return rank


def _classify_volatility_regime(annualized_vol: float) -> str:
    """Classify into low / normal / high / extreme regimes.

    Regime boundaries (annualized):
      - low:     < 15%
      - normal:  15% – 25%
      - high:    25% – 40%
      - extreme: > 40%

    Returns
    -------
    str
        One of ``"low"``, ``"normal"``, ``"high"``, ``"extreme"``.
    """
    if annualized_vol < 0.15:
        return "low"
    elif annualized_vol < 0.25:
        return "normal"
    elif annualized_vol < 0.40:
        return "high"
    else:
        return "extreme"


def _regime_max_position_pct(regime: str) -> float:
    """Max single-position size as a fraction of portfolio equity.

    Returns
    -------
    float
        Position cap fraction.
    """
    return {
        "low": 0.25,
        "normal": 0.20,
        "high": 0.10,
        "extreme": 0.05,
    }.get(regime, _DEFAULT_MAX_POSITION_PCT)


def _compute_correlation_adjustment(
    ticker_returns: np.ndarray,
    portfolio_returns: dict[str, np.ndarray],
) -> float:
    """Compute a multiplicative adjustment based on average correlation with
    existing portfolio positions.

    Returns
    -------
    float
        Multiplier in [0.7, 1.1].
    """
    if not portfolio_returns:
        return 1.0

    correlations: list[float] = []
    for other_ticker, other_returns in portfolio_returns.items():
        # Align lengths
        min_len = min(len(ticker_returns), len(other_returns))
        if min_len < 5:
            continue
        a = ticker_returns[-min_len:]
        b = other_returns[-min_len:]
        corr_matrix = np.corrcoef(a, b)
        corr = float(corr_matrix[0, 1])
        if not np.isnan(corr):
            correlations.append(abs(corr))

    if not correlations:
        return 1.0

    avg_corr = float(np.mean(correlations))

    if avg_corr > 0.7:
        return 0.7  # high correlation penalty
    elif avg_corr < 0.3:
        return 1.1  # low correlation bonus
    else:
        return 1.0


def _compute_parametric_var(
    daily_returns: np.ndarray,
    position_value: float,
) -> float:
    """Compute 1-day 95% parametric Value at Risk.

    Parameters
    ----------
    daily_returns:
        Array of daily log returns.
    position_value:
        Current notional value of the position in USD.

    Returns
    -------
    float
        VaR in USD (positive number = potential loss).
    """
    if len(daily_returns) < 2 or position_value == 0.0:
        return 0.0
    sigma = float(np.std(daily_returns, ddof=1))
    mu = float(np.mean(daily_returns))
    var = abs(position_value) * (_VAR_CONFIDENCE_Z * sigma - mu)
    return max(var, 0.0)


def _compute_max_drawdown(prices: list[Price]) -> float:
    """Compute maximum peak-to-trough drawdown from a price series.

    Returns
    -------
    float
        Drawdown as a percentage (0-100).
    """
    if len(prices) < 2:
        return 0.0

    closes = np.array([p.close for p in prices], dtype=np.float64)
    peak = closes[0]
    max_dd = 0.0

    for close in closes[1:]:
        if close > peak:
            peak = close
        drawdown = (peak - close) / peak if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown

    return max_dd * 100.0


def _compute_risk_score(
    volatility_regime: str,
    max_drawdown_pct: float,
    var_pct_of_equity: float,
    avg_correlation: float,
) -> float:
    """Compute a composite risk score from 0 (safe) to 100 (extreme).

    Each factor contributes a weighted sub-score:
      - Volatility regime:  30%
      - Max drawdown:       30%
      - VaR % of equity:    25%
      - Correlation risk:   15%
    """
    regime_scores = {"low": 10, "normal": 35, "high": 65, "extreme": 95}
    vol_score = regime_scores.get(volatility_regime, 50)

    dd_score = min(max_drawdown_pct * 2.0, 100.0)
    var_score = min(var_pct_of_equity * 10.0, 100.0)
    corr_score = avg_correlation * 100.0

    composite = vol_score * 0.30 + dd_score * 0.30 + var_score * 0.25 + corr_score * 0.15
    return round(min(max(composite, 0.0), 100.0), 1)


# ---------------------------------------------------------------------------
# Main risk analysis function
# ---------------------------------------------------------------------------


def _analyze_ticker(
    ticker: str,
    prices: list[Price],
    portfolio: PortfolioState,
    portfolio_returns: dict[str, np.ndarray],
    total_equity: float,
) -> dict[str, Any]:
    """Run the full risk analysis pipeline for a single ticker.

    Returns a dict suitable for constructing a :class:`RiskAssessment`.
    """
    settings = get_settings()

    daily_returns = _compute_daily_returns(prices)
    ann_vol = _annualized_volatility(daily_returns)
    vol_percentile = _volatility_percentile(daily_returns)
    regime = _classify_volatility_regime(ann_vol)

    # --- Position limit ---
    base_pct = _regime_max_position_pct(regime)
    corr_adj = _compute_correlation_adjustment(daily_returns, portfolio_returns)
    adjusted_pct = base_pct * corr_adj

    # Cap against config-level maximum
    max_pct = min(adjusted_pct, settings.max_position_size_pct)
    max_position_value = total_equity * max_pct

    # Subtract current exposure in this ticker
    current_long_value = 0.0
    current_short_value = 0.0
    if ticker in portfolio.positions:
        current_long_value = abs(portfolio.positions[ticker].market_value)
    if ticker in portfolio.short_positions:
        current_short_value = abs(portfolio.short_positions[ticker].market_value)
    current_exposure = current_long_value + current_short_value
    remaining_limit = max(max_position_value - current_exposure, 0.0)

    # --- VaR ---
    position_value = current_long_value - current_short_value  # net
    current_var = _compute_parametric_var(daily_returns, position_value)

    # --- Drawdown ---
    max_drawdown_pct = _compute_max_drawdown(prices)

    # --- Correlation risk ---
    avg_corr = 0.0
    if portfolio_returns:
        corrs: list[float] = []
        for other_returns in portfolio_returns.values():
            min_len = min(len(daily_returns), len(other_returns))
            if min_len < 5:
                continue
            a = daily_returns[-min_len:]
            b = other_returns[-min_len:]
            c = np.corrcoef(a, b)[0, 1]
            if not np.isnan(c):
                corrs.append(abs(float(c)))
        if corrs:
            avg_corr = float(np.mean(corrs))

    # --- Risk score ---
    var_pct = (current_var / total_equity * 100.0) if total_equity > 0 else 0.0
    risk_score = _compute_risk_score(regime, max_drawdown_pct, var_pct, avg_corr)

    # --- Warnings ---
    warnings: list[str] = []
    if regime in ("high", "extreme"):
        warnings.append(f"Elevated volatility regime ({regime}): annualized vol = {ann_vol:.1%}")
    if max_drawdown_pct > 20.0:
        warnings.append(f"Significant max drawdown observed: {max_drawdown_pct:.1f}%")
    if vol_percentile > 80:
        warnings.append(f"Volatility at {vol_percentile:.0f}th percentile of 1-year range")
    if avg_corr > 0.7:
        warnings.append(f"High avg correlation with portfolio ({avg_corr:.2f})")
    if var_pct > 5.0:
        warnings.append(f"1-day 95% VaR is {var_pct:.1f}% of equity")
    if remaining_limit <= 0:
        warnings.append("Position limit fully consumed — no additional exposure allowed")

    return {
        "remaining_position_limit": round(remaining_limit, 2),
        "current_var": round(current_var, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "volatility_regime": regime,
        "correlation_risk": round(avg_corr, 4),
        "risk_score": risk_score,
        "warnings": warnings,
        # Extra detail for downstream consumers
        "_detail": {
            "annualized_volatility": round(ann_vol, 4),
            "volatility_percentile": round(vol_percentile, 1),
            "base_position_pct": round(base_pct, 4),
            "correlation_adjustment": round(corr_adj, 4),
            "effective_position_pct": round(max_pct, 4),
            "current_exposure_usd": round(current_exposure, 2),
        },
    }


# ---------------------------------------------------------------------------
# LangGraph node function
# ---------------------------------------------------------------------------


def risk_manager_agent(state: AgentState) -> dict[str, Any]:
    """LangGraph node: evaluate risk for every ticker and emit position limits.

    This agent is **purely rule-based** — it makes no LLM calls.

    Reads from state
    ----------------
    - ``data.tickers``      : list[str]
    - ``data.start_date``   : str (ISO date)
    - ``data.end_date``     : str (ISO date)
    - ``data.portfolio``    : dict (serialised PortfolioState)

    Writes to state
    ---------------
    - ``data.risk_assessment`` : dict[str, dict]  — per-ticker risk output
    """
    data: dict[str, Any] = state.get("data", {})
    tickers: list[str] = data.get("tickers", [])
    end_date_str: str = data.get("end_date", str(date.today()))
    start_date_str: str = data.get("start_date", "")

    # Parse dates — for risk, we want at least 1 year of history
    try:
        end_dt = date.fromisoformat(end_date_str)
    except (ValueError, TypeError):
        end_dt = date.today()

    if start_date_str:
        try:
            start_dt = date.fromisoformat(start_date_str)
        except (ValueError, TypeError):
            start_dt = end_dt - timedelta(days=365)
    else:
        start_dt = end_dt - timedelta(days=365)

    # Ensure at least 1 year of lookback for volatility ranking
    min_start = end_dt - timedelta(days=_LOOKBACK_YEARS * 365)
    if start_dt > min_start:
        start_dt = min_start

    # Reconstruct portfolio state
    portfolio_raw = data.get("portfolio", {})
    if isinstance(portfolio_raw, dict):
        try:
            portfolio = PortfolioState(**portfolio_raw)
        except Exception:
            logger.warning("Could not parse portfolio state; using default.")
            portfolio = PortfolioState()
    elif isinstance(portfolio_raw, PortfolioState):
        portfolio = portfolio_raw
    else:
        portfolio = PortfolioState()

    total_equity = portfolio.total_equity
    if total_equity <= 0:
        total_equity = portfolio.cash  # fallback

    logger.info(
        "Risk manager analyzing %d tickers | equity=$%.2f | window=%s to %s",
        len(tickers),
        total_equity,
        start_dt,
        end_dt,
    )

    # Fetch price data for all tickers
    client = FinancialDataClient()
    ticker_prices: dict[str, list[Price]] = {}
    ticker_returns: dict[str, np.ndarray] = {}

    for ticker in tickers:
        prices = client.get_prices(ticker, start_date=start_dt, end_date=end_dt)
        # Sort by date ascending
        prices = sorted(prices, key=lambda p: p.date)
        ticker_prices[ticker] = prices
        ticker_returns[ticker] = _compute_daily_returns(prices)

    # Also collect returns for existing portfolio positions not in tickers
    all_held = set(portfolio.positions.keys()) | set(portfolio.short_positions.keys())
    for held_ticker in all_held:
        if held_ticker not in ticker_returns:
            prices = client.get_prices(held_ticker, start_date=start_dt, end_date=end_dt)
            prices = sorted(prices, key=lambda p: p.date)
            ticker_returns[held_ticker] = _compute_daily_returns(prices)

    client.close()

    # Run per-ticker analysis
    risk_assessment: dict[str, dict[str, Any]] = {}

    for ticker in tickers:
        prices = ticker_prices.get(ticker, [])
        # Build portfolio returns *excluding* the current ticker for correlation
        other_returns = {t: r for t, r in ticker_returns.items() if t != ticker and len(r) > 0}

        try:
            assessment = _analyze_ticker(
                ticker=ticker,
                prices=prices,
                portfolio=portfolio,
                portfolio_returns=other_returns,
                total_equity=total_equity,
            )
            risk_assessment[ticker] = assessment
            logger.info(
                "Risk [%s]: regime=%s, limit=$%.0f, VaR=$%.0f, drawdown=%.1f%%",
                ticker,
                assessment["volatility_regime"],
                assessment["remaining_position_limit"],
                assessment["current_var"],
                assessment["max_drawdown_pct"],
            )
        except Exception:
            logger.exception("Risk analysis failed for %s — using conservative defaults", ticker)
            risk_assessment[ticker] = {
                "remaining_position_limit": 0.0,
                "current_var": 0.0,
                "max_drawdown_pct": 0.0,
                "volatility_regime": "extreme",
                "correlation_risk": 0.0,
                "risk_score": 100.0,
                "warnings": [f"Risk analysis failed for {ticker}; blocking all new exposure."],
            }

    # Merge into state
    updated_data = {**data, "risk_assessment": risk_assessment}
    return {"data": updated_data}
