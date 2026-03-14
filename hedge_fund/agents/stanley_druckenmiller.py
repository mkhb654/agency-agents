"""Stanley Druckenmiller Agent -- Macro investing, follow the money, conviction sizing.

Analyses sector momentum, revenue acceleration, free cash flow yield, and
price trend strength. The LLM synthesizes a macro thesis and conviction level
in Druckenmiller's decisive, big-bet style.
"""

from __future__ import annotations

import logging
from typing import Any

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import AnalystSignal, FinancialMetrics, LineItem, Price
from hedge_fund.graph.state import AgentState
from hedge_fund.llm.models import call_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
AGENT_SYSTEM_PROMPT = """\
You are Stanley Druckenmiller, one of the most successful macro investors in \
history. Over 30 years at Duquesne Capital Management and as George Soros's \
chief strategist at the Quantum Fund, you delivered average annual returns \
exceeding 30% with no losing year. You helped Soros break the Bank of England \
in 1992, netting a billion dollars in a single trade.

Your investment philosophy is built on several key principles:

1. **Follow the Liquidity.** Money flows drive markets, not fundamentals alone. \
You watch central bank policy, credit conditions, and capital flows obsessively. \
"Earnings don't move the overall market; it's the Federal Reserve Board... focus \
on the central banks, and focus on the movement of liquidity."

2. **Bet Big When You're Right.** Position sizing is everything. When your \
analysis gives you high conviction, you concentrate your portfolio aggressively. \
"The way to build long-term returns is through preservation of capital and home \
runs... When you have tremendous conviction on a trade, you have to go for the \
jugular. It takes courage to be a pig."

3. **Cut Losses Ruthlessly.** You never let a losing position define your \
portfolio. "I've learned many things from George Soros, but perhaps the most \
significant is that it's not whether you're right or wrong that's important, but \
how much money you make when you're right and how much you lose when you're wrong."

4. **Top-Down, Then Bottom-Up.** You start with the macro picture -- interest \
rates, currency movements, economic cycles, geopolitics -- and then find the best \
individual securities to express your macro view. A great stock in a terrible \
sector will underperform; a mediocre stock in a raging bull sector will outperform.

5. **Revenue Acceleration.** At the company level, you look for revenue \
acceleration -- when the rate of revenue growth is itself increasing. This signals \
that a company is gaining market share, entering new markets, or benefiting from \
secular tailwinds. Decelerating revenue is often the first warning sign.

6. **Free Cash Flow Yield.** You want companies that generate real cash, not just \
accounting earnings. Free cash flow yield (FCF / market cap) tells you what you're \
actually getting for your money. High FCF yield with revenue acceleration is the \
sweet spot.

7. **Price Trend Strength.** You are not a pure fundamentalist. You pay attention \
to what the market is telling you through price action. A stock making new highs \
with strong volume is confirming the fundamental thesis. A stock breaking down \
despite good fundamentals is sending a warning. "I never, ever make an investment \
without also considering the technical picture."

8. **Macro Regime Awareness.** You adjust your entire approach based on the macro \
regime. In risk-on environments (easy money, strong growth), you are aggressive \
and long. In risk-off environments (tightening, recession), you reduce exposure, \
go to cash, or go short. "The most important thing in investing is knowing what \
environment you're in."

Your tone is direct, decisive, and supremely confident. You speak in terms of \
conviction levels, risk/reward asymmetries, and macro regimes. You reference \
interest rates, the Fed, currency markets, and sector rotations. You have no \
patience for indecision -- you either see a trade or you don't. When you see it, \
you size it aggressively.

You must produce a JSON response with the following fields:
- signal: one of "bullish", "bearish", or "neutral"
- confidence: a float between 0.0 and 1.0
- reasoning: a concise paragraph (2-4 sentences) in your decisive, conviction-driven voice
"""


# ---------------------------------------------------------------------------
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _score_sector_momentum(prices: list[Price]) -> tuple[float, str]:
    """Score 0-10 based on price trend strength and momentum."""
    if len(prices) < 20:
        return 5.0, "Insufficient price history for momentum analysis."

    score = 0.0
    details: list[str] = []

    current = prices[-1].close
    start = prices[0].close

    # Overall trend
    if start > 0:
        total_return = (current - start) / start
    else:
        total_return = 0.0

    # Short-term momentum (last 20% of data)
    short_idx = max(0, len(prices) - len(prices) // 5)
    short_start = prices[short_idx].close if prices[short_idx].close > 0 else current
    short_return = (current - short_start) / short_start if short_start > 0 else 0

    # Medium-term momentum (last 50% of data)
    mid_idx = len(prices) // 2
    mid_start = prices[mid_idx].close if prices[mid_idx].close > 0 else current
    mid_return = (current - mid_start) / mid_start if mid_start > 0 else 0

    # Scoring: positive momentum across timeframes
    if total_return > 0.30:
        score += 3.0
        details.append(f"Strong total return {total_return:.0%} over the full period.")
    elif total_return > 0.10:
        score += 2.0
        details.append(f"Positive total return {total_return:.0%}.")
    elif total_return > -0.10:
        score += 1.0
        details.append(f"Flat total return {total_return:.0%}.")
    else:
        details.append(f"Negative total return {total_return:.0%}.")

    if short_return > 0.05:
        score += 2.5
        details.append(f"Short-term momentum strong ({short_return:.1%}).")
    elif short_return > 0:
        score += 1.5
        details.append(f"Short-term momentum positive ({short_return:.1%}).")
    else:
        details.append(f"Short-term momentum negative ({short_return:.1%}).")

    if mid_return > 0.10:
        score += 2.5
        details.append(f"Medium-term momentum strong ({mid_return:.1%}).")
    elif mid_return > 0:
        score += 1.5
        details.append(f"Medium-term momentum positive ({mid_return:.1%}).")
    else:
        details.append(f"Medium-term momentum negative ({mid_return:.1%}).")

    # Trend consistency: % of days above simple moving average
    if len(prices) >= 50:
        sma_50_prices = [p.close for p in prices[-50:]]
        sma_50 = sum(sma_50_prices) / len(sma_50_prices)
        if current > sma_50:
            score += 2.0
            details.append(f"Trading above 50-period SMA (${sma_50:.2f}).")
        else:
            details.append(f"Trading below 50-period SMA (${sma_50:.2f}).")

    return min(score, 10.0), " ".join(details)


def _score_revenue_acceleration(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 based on whether revenue growth is accelerating or decelerating."""
    growth_rates = [m.revenue_growth for m in metrics if m.revenue_growth is not None]

    if len(growth_rates) < 2:
        return 5.0, "Insufficient revenue growth data for acceleration analysis."

    score = 0.0
    details: list[str] = []

    # Compute acceleration (change in growth rate)
    accelerations: list[float] = []
    for i in range(1, len(growth_rates)):
        accelerations.append(growth_rates[i] - growth_rates[i - 1])

    if not accelerations:
        return 5.0, "Cannot compute revenue acceleration."

    latest_accel = accelerations[-1]
    avg_accel = sum(accelerations) / len(accelerations)

    # Latest growth rate
    latest_growth = growth_rates[-1]
    if latest_growth > 0.20:
        score += 3.0
        details.append(f"Latest revenue growth {latest_growth:.1%} -- strong.")
    elif latest_growth > 0.05:
        score += 2.0
        details.append(f"Latest revenue growth {latest_growth:.1%} -- moderate.")
    elif latest_growth > 0:
        score += 1.0
        details.append(f"Latest revenue growth {latest_growth:.1%} -- sluggish.")
    else:
        details.append(f"Revenue declining {latest_growth:.1%}.")

    # Acceleration direction
    if latest_accel > 0.05:
        score += 4.0
        details.append(f"Revenue growth ACCELERATING (+{latest_accel:.1%} vs prior) -- Druckenmiller's sweet spot.")
    elif latest_accel > 0:
        score += 2.5
        details.append(f"Revenue growth slightly accelerating (+{latest_accel:.1%}).")
    elif latest_accel > -0.05:
        score += 1.0
        details.append(f"Revenue growth roughly stable ({latest_accel:+.1%}).")
    else:
        details.append(f"Revenue growth DECELERATING ({latest_accel:+.1%}) -- warning sign.")

    # Sustained acceleration
    accel_periods = sum(1 for a in accelerations if a > 0)
    accel_ratio = accel_periods / len(accelerations)
    if accel_ratio > 0.6:
        score += 3.0
        details.append(f"Accelerating in {accel_periods}/{len(accelerations)} periods -- sustained trend.")
    elif accel_ratio > 0.4:
        score += 1.5
        details.append("Mixed acceleration pattern.")
    else:
        details.append("Predominantly decelerating -- macro headwinds likely.")

    return min(score, 10.0), " ".join(details)


def _score_fcf_yield(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 based on free cash flow yield (FCF / market cap)."""
    fcf_yield_vals = [m.free_cash_flow_yield for m in metrics if m.free_cash_flow_yield is not None]

    if not fcf_yield_vals:
        # Try to compute from individual components
        fcf_per_share_vals = [m.free_cash_flow_per_share for m in metrics if m.free_cash_flow_per_share is not None]
        price_vals = [m.market_cap for m in metrics if m.market_cap is not None]
        if not fcf_per_share_vals:
            return 5.0, "No free cash flow yield data available."

    latest_yield = fcf_yield_vals[-1] if fcf_yield_vals else None

    if latest_yield is None:
        return 5.0, "Cannot compute FCF yield."

    score = 0.0
    details: list[str] = []

    if latest_yield > 0.10:
        score += 5.0
        details.append(f"FCF yield {latest_yield:.1%} -- very attractive cash generation.")
    elif latest_yield > 0.06:
        score += 4.0
        details.append(f"FCF yield {latest_yield:.1%} -- strong.")
    elif latest_yield > 0.03:
        score += 3.0
        details.append(f"FCF yield {latest_yield:.1%} -- reasonable.")
    elif latest_yield > 0.01:
        score += 1.5
        details.append(f"FCF yield {latest_yield:.1%} -- low.")
    elif latest_yield > 0:
        score += 0.5
        details.append(f"FCF yield {latest_yield:.1%} -- negligible.")
    else:
        details.append(f"Negative FCF yield {latest_yield:.1%} -- burning cash.")

    # FCF yield trend
    if len(fcf_yield_vals) >= 2:
        trend = fcf_yield_vals[-1] - fcf_yield_vals[0]
        if trend > 0.02:
            score += 3.0
            details.append("FCF yield improving -- cash generation strengthening.")
        elif trend > 0:
            score += 1.5
            details.append("FCF yield slightly improving.")
        elif trend > -0.02:
            score += 0.5
            details.append("FCF yield roughly stable.")
        else:
            details.append("FCF yield deteriorating.")

    # Consistency of positive FCF
    positive_count = sum(1 for y in fcf_yield_vals if y > 0)
    if positive_count == len(fcf_yield_vals):
        score += 2.0
        details.append("Consistently positive FCF -- reliable cash generator.")
    elif positive_count > len(fcf_yield_vals) * 0.7:
        score += 1.0
        details.append("Mostly positive FCF.")

    return min(score, 10.0), " ".join(details)


def _score_price_trend_strength(prices: list[Price]) -> tuple[float, str]:
    """Score 0-10 based on relative price performance and trend quality."""
    if len(prices) < 30:
        return 5.0, "Insufficient price data for trend strength analysis."

    score = 0.0
    details: list[str] = []

    closes = [p.close for p in prices]

    # Compute simple linear regression slope (normalised)
    n = len(closes)
    x_mean = (n - 1) / 2.0
    y_mean = sum(closes) / n

    numerator = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator > 0 and y_mean > 0:
        slope = numerator / denominator
        normalised_slope = (slope / y_mean) * 100  # % change per period
    else:
        normalised_slope = 0.0

    if normalised_slope > 0.3:
        score += 4.0
        details.append(f"Strong upward price trend (normalised slope {normalised_slope:.2f}%/period).")
    elif normalised_slope > 0.1:
        score += 3.0
        details.append(f"Moderate upward price trend ({normalised_slope:.2f}%/period).")
    elif normalised_slope > 0:
        score += 1.5
        details.append(f"Slight upward drift ({normalised_slope:.2f}%/period).")
    elif normalised_slope > -0.1:
        score += 0.5
        details.append(f"Flat to slightly declining ({normalised_slope:.2f}%/period).")
    else:
        details.append(f"Downward price trend ({normalised_slope:.2f}%/period).")

    # R-squared: how consistent is the trend?
    ss_res = sum((closes[i] - (y_mean + (numerator / denominator) * (i - x_mean))) ** 2
                 for i in range(n)) if denominator > 0 else 0
    ss_tot = sum((closes[i] - y_mean) ** 2 for i in range(n))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    if r_squared > 0.7:
        score += 3.0
        details.append(f"Very consistent trend (R-squared {r_squared:.2f}).")
    elif r_squared > 0.4:
        score += 2.0
        details.append(f"Moderately consistent trend (R-squared {r_squared:.2f}).")
    elif r_squared > 0.2:
        score += 1.0
        details.append(f"Noisy but directional (R-squared {r_squared:.2f}).")
    else:
        details.append(f"No clear trend (R-squared {r_squared:.2f}) -- choppy action.")

    # Higher highs check
    quarter = max(n // 4, 1)
    q1_high = max(closes[:quarter])
    q4_high = max(closes[-quarter:])
    if q4_high > q1_high:
        score += 3.0
        details.append("Making higher highs -- trend is intact.")
    elif q4_high > q1_high * 0.95:
        score += 1.5
        details.append("Highs roughly stable.")
    else:
        details.append("Failing to make new highs -- trend may be exhausted.")

    return min(score, 10.0), " ".join(details)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def stanley_druckenmiller_agent(state: AgentState) -> dict[str, Any]:
    """Run Stanley Druckenmiller's macro-focused analysis on every ticker in state.

    Returns updated state with analyst signals keyed by ``stanley_druckenmiller``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]
    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        try:
            logger.info("Stanley Druckenmiller analysing %s ...", ticker)

            # -- 1. Fetch data ------------------------------------------------
            metrics: list[FinancialMetrics] = api.get_financial_metrics(ticker, limit=10)
            line_items: list[LineItem] = api.get_line_items(
                ticker,
                line_items=[
                    "revenue",
                    "free_cash_flow",
                    "operating_cash_flow",
                    "capital_expenditure",
                ],
                limit=10,
            )
            prices: list[Price] = api.get_prices(ticker, limit=252)

            # -- 2. Deterministic scoring -------------------------------------
            momentum_score, momentum_details = _score_sector_momentum(prices)
            accel_score, accel_details = _score_revenue_acceleration(metrics)
            fcf_score, fcf_details = _score_fcf_yield(metrics)
            trend_score, trend_details = _score_price_trend_strength(prices)

            total_score = (momentum_score + accel_score + fcf_score + trend_score) / 4.0

            # -- 3. Build analysis summary ------------------------------------
            analysis_summary = (
                f"Ticker: {ticker}\n"
                f"Overall Druckenmiller Score: {total_score:.1f}/10\n\n"
                f"Sector Momentum ({momentum_score:.1f}/10): {momentum_details}\n"
                f"Revenue Acceleration ({accel_score:.1f}/10): {accel_details}\n"
                f"Free Cash Flow Yield ({fcf_score:.1f}/10): {fcf_details}\n"
                f"Price Trend Strength ({trend_score:.1f}/10): {trend_details}\n"
            )

            if prices:
                analysis_summary += f"\nCurrent Price: ${prices[-1].close:.2f}\n"

            # -- 4. LLM synthesis ---------------------------------------------
            llm_result = call_llm(
                system_prompt=AGENT_SYSTEM_PROMPT,
                user_message=(
                    f"Based on the following analysis, provide your macro-informed "
                    f"investment signal for {ticker}. Consider the overall market "
                    f"regime and whether the technical picture confirms or contradicts "
                    f"the fundamental setup. Size your conviction accordingly. "
                    f"Respond with JSON containing 'signal', 'confidence', and "
                    f"'reasoning'.\n\n{analysis_summary}"
                ),
                response_model=AnalystSignal,
            )

            signals[ticker] = {
                "signal": llm_result.signal,
                "confidence": llm_result.confidence,
                "reasoning": llm_result.reasoning,
                "agent_scores": {
                    "sector_momentum": momentum_score,
                    "revenue_acceleration": accel_score,
                    "fcf_yield": fcf_score,
                    "price_trend_strength": trend_score,
                    "overall": total_score,
                },
            }
            logger.info(
                "Druckenmiller on %s: %s (confidence %.0f%%)",
                ticker,
                llm_result.signal,
                llm_result.confidence * 100,
            )

        except Exception:
            logger.exception("Stanley Druckenmiller agent failed on %s -- returning neutral.", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"stanley_druckenmiller": signals}}}
