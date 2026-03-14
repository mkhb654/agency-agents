"""Technical Analyst Agent (RULE-BASED, no LLM).

Fetches 6 months of daily price data and runs five independent strategies:

  1. **Trend Following** -- 20/50 EMA crossover + ADX strength
  2. **Mean Reversion** -- 20-period Bollinger Bands + z-score
  3. **Momentum** -- 1-month, 3-month, 6-month return analysis
  4. **Volatility** -- current vol vs historical percentile
  5. **Statistical** -- Hurst exponent estimation

Each strategy produces a signal in [-1, +1].  The final signal is a
weighted ensemble:

  trend 25% | mean-rev 20% | momentum 25% | vol 15% | stat 15%

All technical indicators are implemented from scratch using numpy.
"""

from __future__ import annotations

import datetime
import logging
import math
from typing import Any

import numpy as np
from rich.console import Console
from rich.table import Table

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import Price, SignalDirection
from hedge_fund.graph.state import AgentState

logger = logging.getLogger(__name__)
console = Console()

# ---------------------------------------------------------------------------
# Ensemble weights (must sum to 1.0)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "trend": 0.25,
    "mean_reversion": 0.20,
    "momentum": 0.25,
    "volatility": 0.15,
    "statistical": 0.15,
}

# ---------------------------------------------------------------------------
# Technical indicator helpers (pure numpy)
# ---------------------------------------------------------------------------


def _ema(data: np.ndarray, span: int) -> np.ndarray:
    """Compute exponential moving average with given span."""
    alpha = 2.0 / (span + 1)
    result = np.empty_like(data, dtype=np.float64)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _sma(data: np.ndarray, window: int) -> np.ndarray:
    """Simple moving average; first (window-1) values are NaN."""
    result = np.full_like(data, np.nan, dtype=np.float64)
    if len(data) < window:
        return result
    cumsum = np.cumsum(data)
    result[window - 1 :] = (cumsum[window - 1 :] - np.concatenate([[0], cumsum[: -window]])) / window
    return result


def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Compute True Range series."""
    tr = np.empty(len(high), dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, len(high)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return tr


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """Compute the latest ADX value."""
    n = len(high)
    if n < period * 2:
        return 0.0

    tr = _true_range(high, low, close)

    plus_dm = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    def _wilder_smooth(arr: np.ndarray, p: int) -> np.ndarray:
        out = np.zeros(len(arr), dtype=np.float64)
        out[p] = np.sum(arr[1 : p + 1])
        for i in range(p + 1, len(arr)):
            out[i] = out[i - 1] - out[i - 1] / p + arr[i]
        return out

    atr_smooth = _wilder_smooth(tr, period)
    plus_dm_smooth = _wilder_smooth(plus_dm, period)
    minus_dm_smooth = _wilder_smooth(minus_dm, period)

    plus_di = np.zeros(n, dtype=np.float64)
    minus_di = np.zeros(n, dtype=np.float64)
    for i in range(period, n):
        if atr_smooth[i] != 0:
            plus_di[i] = 100.0 * plus_dm_smooth[i] / atr_smooth[i]
            minus_di[i] = 100.0 * minus_dm_smooth[i] / atr_smooth[i]

    dx = np.zeros(n, dtype=np.float64)
    for i in range(period, n):
        denom = plus_di[i] + minus_di[i]
        if denom != 0:
            dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / denom

    adx_arr = _wilder_smooth(dx, period)
    valid = adx_arr[adx_arr > 0]
    return float(valid[-1]) if len(valid) > 0 else 0.0


def _bollinger_bands(
    close: np.ndarray, period: int = 20, num_std: float = 2.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (upper, middle, lower) Bollinger Bands."""
    middle = _sma(close, period)
    std = np.full_like(close, np.nan, dtype=np.float64)
    for i in range(period - 1, len(close)):
        std[i] = np.std(close[i - period + 1 : i + 1], ddof=1)
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def _hurst_exponent(series: np.ndarray, max_lag: int = 20) -> float:
    """Estimate Hurst exponent via rescaled range (R/S) method.

    H > 0.5 => trending; H = 0.5 => random walk; H < 0.5 => mean-reverting.
    """
    n = len(series)
    if n < max_lag * 2:
        return 0.5

    lags = range(2, min(max_lag + 1, n // 2))
    rs_values: list[float] = []
    lag_values: list[float] = []

    for lag in lags:
        num_sub = n // lag
        if num_sub < 1:
            continue
        rs_list: list[float] = []
        for j in range(num_sub):
            sub = series[j * lag : (j + 1) * lag]
            mean_sub = np.mean(sub)
            deviations = sub - mean_sub
            cumdev = np.cumsum(deviations)
            r = float(np.max(cumdev) - np.min(cumdev))
            s = float(np.std(sub, ddof=1))
            if s > 0:
                rs_list.append(r / s)
        if rs_list:
            rs_values.append(float(np.mean(rs_list)))
            lag_values.append(float(lag))

    if len(rs_values) < 3:
        return 0.5

    log_lags = np.log(lag_values)
    log_rs = np.log(rs_values)
    coeffs = np.polyfit(log_lags, log_rs, 1)
    hurst = float(coeffs[0])
    return max(0.0, min(1.0, hurst))


# ---------------------------------------------------------------------------
# Strategy implementations -- each returns (signal_value, confidence, reason)
# ---------------------------------------------------------------------------


def _strategy_trend(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> tuple[float, float, str]:
    """Trend Following: 20/50 EMA crossover + ADX strength."""
    if len(close) < 50:
        return 0.0, 0.3, "Insufficient data for trend analysis (need 50+ bars)"

    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    adx_value = _adx(high, low, close, 14)

    current_ema20 = ema20[-1]
    current_ema50 = ema50[-1]
    ema_diff_pct = (current_ema20 - current_ema50) / current_ema50 if current_ema50 != 0 else 0

    # Base signal from crossover
    raw_signal = max(-1.0, min(1.0, ema_diff_pct * 10))

    # ADX modulates confidence
    if adx_value > 40:
        adx_multiplier = 1.3
        adx_note = f"very strong trend (ADX={adx_value:.0f})"
    elif adx_value > 25:
        adx_multiplier = 1.0
        adx_note = f"confirmed trend (ADX={adx_value:.0f})"
    elif adx_value > 15:
        adx_multiplier = 0.6
        adx_note = f"weak trend (ADX={adx_value:.0f})"
    else:
        adx_multiplier = 0.3
        adx_note = f"no trend (ADX={adx_value:.0f})"

    signal = max(-1.0, min(1.0, raw_signal * adx_multiplier))
    confidence = min(1.0, abs(signal) * 0.5 + 0.3)
    direction = "bullish" if signal > 0 else "bearish"
    reason = (
        f"Trend: EMA20={current_ema20:.2f} {'>' if current_ema20 > current_ema50 else '<'} "
        f"EMA50={current_ema50:.2f} ({ema_diff_pct:+.2%}), {adx_note} -> {direction} ({signal:+.2f})"
    )
    return signal, confidence, reason


def _strategy_mean_reversion(close: np.ndarray) -> tuple[float, float, str]:
    """Mean Reversion: Bollinger Bands + z-score."""
    if len(close) < 20:
        return 0.0, 0.3, "Insufficient data for mean reversion (need 20+ bars)"

    upper, middle, lower = _bollinger_bands(close, 20, 2.0)
    current_price = close[-1]
    current_upper = upper[-1]
    current_lower = lower[-1]
    current_mid = middle[-1]

    if np.isnan(current_mid) or np.isnan(current_upper):
        return 0.0, 0.2, "Bollinger Bands not yet computed"

    window = close[-20:]
    mean_val = float(np.mean(window))
    std_val = float(np.std(window, ddof=1))
    z_score = (current_price - mean_val) / std_val if std_val > 0 else 0

    if current_price < current_lower:
        band_range = current_upper - current_lower
        signal = min(1.0, (current_lower - current_price) / band_range * 2) if band_range > 0 else 0.5
        reason_dir = "oversold"
    elif current_price > current_upper:
        band_range = current_upper - current_lower
        signal = max(-1.0, (current_upper - current_price) / band_range * 2) if band_range > 0 else -0.5
        reason_dir = "overbought"
    else:
        band_range = current_upper - current_lower
        if band_range > 0:
            position = (current_price - current_lower) / band_range
            signal = -(position - 0.5) * 0.5
        else:
            signal = 0.0
        reason_dir = "within bands"

    confidence = min(1.0, abs(z_score) * 0.25 + 0.2)
    reason = (
        f"Mean Rev: price={current_price:.2f}, BB=[{current_lower:.2f}, {current_mid:.2f}, "
        f"{current_upper:.2f}], z={z_score:+.2f}, {reason_dir} -> ({signal:+.2f})"
    )
    return signal, confidence, reason


def _strategy_momentum(close: np.ndarray) -> tuple[float, float, str]:
    """Momentum: 1-month, 3-month, 6-month returns."""
    n = len(close)
    periods = {"1m": 21, "3m": 63, "6m": 126}
    signals: list[float] = []
    parts: list[str] = []

    for label, period in periods.items():
        if n > period:
            ret = close[-1] / close[-period] - 1
            sig = max(-1.0, min(1.0, ret * 5))
            signals.append(sig)
            parts.append(f"{label}={ret:+.1%}")
        else:
            parts.append(f"{label}=N/A")

    if not signals:
        return 0.0, 0.2, "Insufficient data for momentum analysis"

    avg_signal = sum(signals) / len(signals)
    agreement = sum(1 for s in signals if (s > 0) == (avg_signal > 0)) / len(signals)
    confidence = min(1.0, agreement * 0.4 + abs(avg_signal) * 0.3 + 0.1)
    direction = "bullish" if avg_signal > 0 else "bearish" if avg_signal < 0 else "neutral"
    reason = f"Momentum: {', '.join(parts)} -> {direction} ({avg_signal:+.2f})"
    return avg_signal, confidence, reason


def _strategy_volatility(close: np.ndarray) -> tuple[float, float, str]:
    """Volatility: current vol vs historical percentile."""
    if len(close) < 63:
        return 0.0, 0.3, "Insufficient data for volatility analysis (need 63+ bars)"

    log_returns = np.diff(np.log(close))
    window = 20
    vol_series: list[float] = []
    for i in range(window, len(log_returns) + 1):
        vol = float(np.std(log_returns[i - window : i], ddof=1)) * math.sqrt(252)
        vol_series.append(vol)

    if len(vol_series) < 10:
        return 0.0, 0.2, "Not enough volatility history"

    current_vol = vol_series[-1]
    vol_arr = np.array(vol_series)
    percentile = float(np.sum(vol_arr < current_vol) / len(vol_arr))

    if percentile < 0.30:
        signal = 0.5 * (0.30 - percentile) / 0.30
        regime = "low vol"
    elif percentile > 0.70:
        signal = -0.5 * (percentile - 0.70) / 0.30
        regime = "high vol"
    else:
        signal = 0.0
        regime = "normal vol"

    confidence = min(1.0, abs(percentile - 0.5) * 2 * 0.5 + 0.2)
    reason = (
        f"Volatility: annualised={current_vol:.1%}, percentile={percentile:.0%}, "
        f"regime={regime} -> ({signal:+.2f})"
    )
    return signal, confidence, reason


def _strategy_statistical(close: np.ndarray, trend_signal: float, mr_signal: float) -> tuple[float, float, str]:
    """Statistical: Hurst exponent guides which regime signal to trust.

    H > 0.6 -> trending, amplify trend signal
    H < 0.4 -> mean-reverting, amplify mean reversion signal
    H ~ 0.5 -> random walk, low confidence neutral
    """
    log_returns = np.diff(np.log(close)) if len(close) > 1 else np.array([])
    if len(log_returns) < 40:
        return 0.0, 0.2, "Insufficient data for Hurst estimation"

    hurst = _hurst_exponent(log_returns, max_lag=min(40, len(log_returns) // 3))

    if hurst > 0.6:
        signal = trend_signal * min(1.0, (hurst - 0.5) * 5)
        regime = "trending"
        confidence = min(1.0, (hurst - 0.5) * 2 + 0.3)
    elif hurst < 0.4:
        signal = mr_signal * min(1.0, (0.5 - hurst) * 5)
        regime = "mean-reverting"
        confidence = min(1.0, (0.5 - hurst) * 2 + 0.3)
    else:
        signal = 0.0
        regime = "random walk"
        confidence = 0.2

    reason = f"Statistical: Hurst={hurst:.3f}, regime={regime} -> ({signal:+.2f})"
    return signal, confidence, reason


# ---------------------------------------------------------------------------
# Per-ticker analysis & ensemble
# ---------------------------------------------------------------------------


def _analyse_ticker(ticker: str, api: FinancialDataClient) -> dict[str, Any]:
    """Run all 5 technical strategies and produce an ensemble signal."""
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=180)
    prices: list[Price] = api.get_prices_sync(ticker, start_date, end_date)

    if len(prices) < 30:
        logger.warning("Only %d price bars for %s -- returning neutral", len(prices), ticker)
        return {
            "signal": "neutral",
            "confidence": 0.15,
            "reasoning": f"Only {len(prices)} price bars available for {ticker}; need at least 30.",
            "agent_scores": {"bars": len(prices)},
        }

    # Sort chronologically (oldest first)
    prices.sort(key=lambda p: p.date)

    close = np.array([p.close for p in prices], dtype=np.float64)
    high = np.array([p.high for p in prices], dtype=np.float64)
    low = np.array([p.low for p in prices], dtype=np.float64)

    # Run strategies
    trend_sig, trend_conf, trend_reason = _strategy_trend(close, high, low)
    mr_sig, mr_conf, mr_reason = _strategy_mean_reversion(close)
    mom_sig, mom_conf, mom_reason = _strategy_momentum(close)
    vol_sig, vol_conf, vol_reason = _strategy_volatility(close)
    stat_sig, stat_conf, stat_reason = _strategy_statistical(close, trend_sig, mr_sig)

    # Weighted ensemble
    ensemble_signal = (
        WEIGHTS["trend"] * trend_sig
        + WEIGHTS["mean_reversion"] * mr_sig
        + WEIGHTS["momentum"] * mom_sig
        + WEIGHTS["volatility"] * vol_sig
        + WEIGHTS["statistical"] * stat_sig
    )

    ensemble_confidence = (
        WEIGHTS["trend"] * trend_conf
        + WEIGHTS["mean_reversion"] * mr_conf
        + WEIGHTS["momentum"] * mom_conf
        + WEIGHTS["volatility"] * vol_conf
        + WEIGHTS["statistical"] * stat_conf
    )
    ensemble_confidence = round(min(1.0, max(0.1, ensemble_confidence)), 2)

    if ensemble_signal > 0.15:
        signal = "bullish"
    elif ensemble_signal < -0.15:
        signal = "bearish"
    else:
        signal = "neutral"

    reasoning_lines = [
        f"Technical ensemble for {ticker} ({len(prices)} bars, {prices[0].date} to {prices[-1].date}):",
        f"  {trend_reason}  [weight={WEIGHTS['trend']:.0%}]",
        f"  {mr_reason}  [weight={WEIGHTS['mean_reversion']:.0%}]",
        f"  {mom_reason}  [weight={WEIGHTS['momentum']:.0%}]",
        f"  {vol_reason}  [weight={WEIGHTS['volatility']:.0%}]",
        f"  {stat_reason}  [weight={WEIGHTS['statistical']:.0%}]",
        f"Ensemble signal: {ensemble_signal:+.3f} -> {signal.upper()}",
    ]

    # Rich table display
    table = Table(title=f"Technicals: {ticker}", show_header=True)
    table.add_column("Strategy", style="cyan")
    table.add_column("Signal", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Weight", justify="right")
    table.add_row("Trend Following", f"{trend_sig:+.2f}", f"{trend_conf:.0%}", f"{WEIGHTS['trend']:.0%}")
    table.add_row("Mean Reversion", f"{mr_sig:+.2f}", f"{mr_conf:.0%}", f"{WEIGHTS['mean_reversion']:.0%}")
    table.add_row("Momentum", f"{mom_sig:+.2f}", f"{mom_conf:.0%}", f"{WEIGHTS['momentum']:.0%}")
    table.add_row("Volatility", f"{vol_sig:+.2f}", f"{vol_conf:.0%}", f"{WEIGHTS['volatility']:.0%}")
    table.add_row("Statistical", f"{stat_sig:+.2f}", f"{stat_conf:.0%}", f"{WEIGHTS['statistical']:.0%}")
    table.add_row(
        "[bold]Ensemble[/bold]",
        f"[bold]{ensemble_signal:+.3f}[/bold]",
        f"[bold]{ensemble_confidence:.0%}[/bold]",
        "100%",
    )
    console.print(table)

    return {
        "signal": signal,
        "confidence": ensemble_confidence,
        "reasoning": "\n".join(reasoning_lines),
        "agent_scores": {
            "ensemble_signal": round(ensemble_signal, 4),
            "trend": round(trend_sig, 4),
            "mean_reversion": round(mr_sig, 4),
            "momentum": round(mom_sig, 4),
            "volatility": round(vol_sig, 4),
            "statistical": round(stat_sig, 4),
            "bars": len(prices),
            "date_range": f"{prices[0].date} to {prices[-1].date}",
        },
    }


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------


def technicals_agent(state: AgentState) -> dict[str, Any]:
    """Technical Analyst -- multi-strategy ensemble technical analysis.

    Runs trend following, mean reversion, momentum, volatility, and
    statistical (Hurst exponent) strategies on 6 months of daily price
    data.  Produces a weighted ensemble signal for each ticker.

    Parameters
    ----------
    state : AgentState
        Must contain ``state["data"]["tickers"]``.

    Returns
    -------
    dict
        Partial state update: ``{"data": {"analyst_signals": {"technicals": ...}}}``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]

    console.rule("[bold green]Technical Analyst[/bold green]")
    logger.info("Technicals agent running for tickers: %s", tickers)

    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        console.print(f"\n[bold]Analysing {ticker}...[/bold]")
        try:
            signals[ticker] = _analyse_ticker(ticker, api)
        except Exception:
            logger.exception("Error in technicals agent for %s", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"technicals": signals}}}
