"""Cathie Wood Agent -- Disruptive innovation, exponential growth, 5-year time horizon.

Evaluates companies through the lens of ARK Invest's philosophy: breakthrough
technologies, platform economics, and exponential revenue trajectories.
Deterministic scoring on growth metrics plus LLM assessment of disruption potential.
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
You are Cathie Wood, founder, CEO, and CIO of ARK Investment Management, one of \
the most prominent advocates of disruptive innovation investing in modern finance.

Your investment philosophy is radically different from traditional value investing. \
You believe we are in the midst of an unprecedented convergence of technological \
platforms -- artificial intelligence, robotics, energy storage, genomics, and \
blockchain technology -- that will reshape every sector of the global economy over \
the next five to ten years. Most investors, anchored to backward-looking valuation \
metrics, dramatically underestimate the pace and magnitude of this transformation.

Your core principles:

1. **Disruptive Innovation.** You invest exclusively in companies that are the \
architects or primary beneficiaries of disruptive innovation. These are companies \
whose products and services create entirely new markets or radically transform \
existing ones. "Innovation solves problems. The bigger the problem, the bigger the \
opportunity."

2. **Wright's Law Over Moore's Law.** You believe cost declines are a function of \
cumulative production, not just time. As unit costs fall, demand rises \
exponentially. This virtuous cycle -- Wright's Law -- is the engine of disruption. \
You model cost curves obsessively and invest when the inflection point is near.

3. **Five-Year Time Horizon.** You do not care about the next quarter. Your models \
project five years forward, often forecasting 30-50% compound annual growth rates \
for the companies you invest in. Short-term volatility is noise; conviction in the \
long-term thesis is everything. "We welcome volatility because it gives us the \
opportunity to add to our highest-conviction names at lower prices."

4. **Convergence of Platforms.** The most explosive opportunities arise when \
multiple innovation platforms converge. An autonomous electric vehicle, for \
instance, sits at the intersection of AI, robotics, energy storage, and \
connectivity. You actively seek these multi-platform convergence plays.

5. **Revenue Growth Over Profitability.** In the early stages of disruption, \
revenue growth and market share acquisition matter far more than current \
profitability. Companies reinvesting aggressively in R&D, even at the expense of \
near-term earnings, are building the moats of the future.

6. **Total Addressable Market (TAM) Expansion.** You focus on companies where \
the TAM is expanding because the innovation is creating demand that did not \
previously exist. Traditional analysts who anchor to current market size miss \
the true opportunity by orders of magnitude.

7. **First Principles Research.** Your team operates from first principles, \
building proprietary models rather than relying on sell-side consensus. You \
embrace radical transparency, publishing your research and models openly.

Your speaking style is passionate, evangelical, and optimistic. You see every \
market correction as a buying opportunity. You reference exponential curves, \
cost declines, and TAM expansion in almost every sentence. You are unperturbed \
by criticism and believe deeply that innovation is the path to economic growth, \
social progress, and wealth creation.

When you are bearish, it is typically because a company is being disrupted rather \
than doing the disrupting, or because it is clinging to legacy business models \
that will be rendered obsolete.

You must produce a JSON response with the following fields:
- signal: one of "bullish", "bearish", or "neutral"
- confidence: a float between 0.0 and 1.0
- reasoning: a concise paragraph (2-4 sentences) explaining your innovation \
  thesis in your authentic voice
"""


# ---------------------------------------------------------------------------
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _score_revenue_growth(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 based on revenue growth rate (higher is better, targeting >25%)."""
    growth_rates = [m.revenue_growth for m in metrics if m.revenue_growth is not None]

    if not growth_rates:
        return 0.0, "No revenue growth data available."

    latest_growth = growth_rates[-1]
    avg_growth = sum(growth_rates) / len(growth_rates)
    details: list[str] = []
    score = 0.0

    # Latest growth rate
    if latest_growth > 0.50:
        score += 5.0
        details.append(f"Latest revenue growth {latest_growth:.1%} -- hyper-growth territory!")
    elif latest_growth > 0.25:
        score += 4.0
        details.append(f"Latest revenue growth {latest_growth:.1%} -- strong innovation-stage growth.")
    elif latest_growth > 0.15:
        score += 2.5
        details.append(f"Latest revenue growth {latest_growth:.1%} -- moderate growth.")
    elif latest_growth > 0.05:
        score += 1.0
        details.append(f"Latest revenue growth {latest_growth:.1%} -- below disruption threshold.")
    else:
        details.append(f"Latest revenue growth {latest_growth:.1%} -- stagnant or declining.")

    # Growth acceleration
    if len(growth_rates) >= 2:
        if growth_rates[-1] > growth_rates[-2]:
            score += 2.5
            details.append("Revenue growth is accelerating -- positive inflection.")
        elif growth_rates[-1] > growth_rates[-2] * 0.9:
            score += 1.0
            details.append("Revenue growth roughly stable.")
        else:
            details.append("Revenue growth decelerating -- potential concern.")

    # Average growth
    if avg_growth > 0.25:
        score += 2.5
        details.append(f"Average revenue growth {avg_growth:.1%} over the period.")
    elif avg_growth > 0.10:
        score += 1.5
        details.append(f"Average revenue growth {avg_growth:.1%} -- moderate trajectory.")
    else:
        details.append(f"Average revenue growth {avg_growth:.1%} -- not disruptive pace.")

    return min(score, 10.0), " ".join(details)


def _score_rd_intensity(line_items: list[LineItem]) -> tuple[float, str]:
    """Score 0-10 based on R&D spending as percentage of revenue."""
    rd_ratios: list[float] = []

    for item in line_items:
        rd = getattr(item, "research_and_development", None)
        revenue = getattr(item, "revenue", None)
        if rd is not None and revenue is not None and revenue > 0:
            rd_ratios.append(abs(rd) / revenue)

    if not rd_ratios:
        return 0.0, "No R&D data available to assess innovation investment."

    latest_ratio = rd_ratios[-1]
    avg_ratio = sum(rd_ratios) / len(rd_ratios)
    score = 0.0
    details: list[str] = []

    # R&D intensity level
    if latest_ratio > 0.20:
        score += 5.0
        details.append(
            f"R&D at {latest_ratio:.1%} of revenue -- massive innovation investment."
        )
    elif latest_ratio > 0.10:
        score += 3.5
        details.append(f"R&D at {latest_ratio:.1%} of revenue -- significant R&D commitment.")
    elif latest_ratio > 0.05:
        score += 2.0
        details.append(f"R&D at {latest_ratio:.1%} of revenue -- moderate investment.")
    else:
        score += 0.5
        details.append(f"R&D at {latest_ratio:.1%} of revenue -- low innovation spend.")

    # R&D trend
    if len(rd_ratios) >= 2:
        if rd_ratios[-1] > rd_ratios[0]:
            score += 3.0
            details.append("R&D intensity increasing -- company doubling down on innovation.")
        elif rd_ratios[-1] > rd_ratios[0] * 0.9:
            score += 1.5
            details.append("R&D intensity stable.")
        else:
            details.append("R&D intensity declining -- concerning for a would-be disruptor.")

    # Sustained high R&D
    if avg_ratio > 0.15:
        score += 2.0
        details.append(f"Sustained high avg R&D ratio {avg_ratio:.1%}.")

    return min(score, 10.0), " ".join(details)


def _score_tam_expansion(metrics: list[FinancialMetrics], line_items: list[LineItem]) -> tuple[float, str]:
    """Score 0-10 as a proxy for TAM expansion using revenue scale + growth acceleration."""
    score = 0.0
    details: list[str] = []

    revenues = [getattr(item, "revenue", None) for item in line_items]
    revenues = [r for r in revenues if r is not None and r > 0]

    if len(revenues) >= 3:
        # Revenue scale growth (proxy for TAM capture)
        total_growth = (revenues[-1] - revenues[0]) / revenues[0] if revenues[0] > 0 else 0
        if total_growth > 2.0:
            score += 5.0
            details.append(f"Revenue tripled+ over the period ({total_growth:.0%} growth) -- massive TAM capture.")
        elif total_growth > 1.0:
            score += 4.0
            details.append(f"Revenue doubled+ ({total_growth:.0%} growth) -- strong TAM penetration.")
        elif total_growth > 0.5:
            score += 2.5
            details.append(f"Revenue grew {total_growth:.0%} -- moderate TAM expansion.")
        elif total_growth > 0:
            score += 1.0
            details.append(f"Revenue grew {total_growth:.0%} -- limited TAM evidence.")
        else:
            details.append("Revenue declining -- no TAM expansion signal.")

        # Growth acceleration (revenue growth rate increasing = TAM expanding)
        growth_rates: list[float] = []
        for i in range(1, len(revenues)):
            if revenues[i - 1] > 0:
                growth_rates.append((revenues[i] - revenues[i - 1]) / revenues[i - 1])

        if len(growth_rates) >= 2:
            if growth_rates[-1] > growth_rates[0]:
                score += 3.0
                details.append("Growth rate accelerating -- TAM expanding faster than linear.")
            else:
                score += 1.0
                details.append("Growth rate stable or decelerating.")
    else:
        details.append("Insufficient revenue history for TAM analysis.")

    # Operating leverage as additional signal
    op_margins = [m.operating_margin for m in metrics if m.operating_margin is not None]
    if len(op_margins) >= 2:
        margin_improvement = op_margins[-1] - op_margins[0]
        if margin_improvement > 0.05:
            score += 2.0
            details.append("Operating margins expanding -- platform economics emerging.")
        elif margin_improvement > 0:
            score += 1.0
            details.append("Slight operating margin improvement.")
        else:
            details.append("Operating margins not yet expanding.")

    return min(score, 10.0), " ".join(details)


def _score_gross_margin_trajectory(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 based on gross margin trajectory (improving = positive signal)."""
    gross_margins = [m.gross_margin for m in metrics if m.gross_margin is not None]

    if len(gross_margins) < 2:
        return 0.0, "Insufficient gross margin data."

    score = 0.0
    details: list[str] = []

    latest = gross_margins[-1]
    earliest = gross_margins[0]
    trend = latest - earliest

    # Absolute level
    if latest > 0.70:
        score += 4.0
        details.append(f"Gross margin {latest:.1%} -- software-like economics.")
    elif latest > 0.50:
        score += 3.0
        details.append(f"Gross margin {latest:.1%} -- strong unit economics.")
    elif latest > 0.30:
        score += 2.0
        details.append(f"Gross margin {latest:.1%} -- moderate.")
    else:
        score += 0.5
        details.append(f"Gross margin {latest:.1%} -- thin, hardware-like margins.")

    # Trajectory
    if trend > 0.10:
        score += 4.0
        details.append(f"Margins expanding +{trend:.1%} -- Wright's Law cost declines in action.")
    elif trend > 0.03:
        score += 3.0
        details.append(f"Margins expanding +{trend:.1%} -- positive trajectory.")
    elif trend > -0.03:
        score += 1.5
        details.append("Margins roughly stable.")
    else:
        details.append(f"Margins contracting {trend:.1%} -- cost pressures.")

    # Consistency of improvement
    improving_periods = sum(
        1 for i in range(1, len(gross_margins)) if gross_margins[i] >= gross_margins[i - 1]
    )
    improvement_ratio = improving_periods / (len(gross_margins) - 1)
    if improvement_ratio > 0.7:
        score += 2.0
        details.append("Consistent margin improvement across periods.")
    elif improvement_ratio > 0.5:
        score += 1.0
        details.append("Mixed margin trajectory.")

    return min(score, 10.0), " ".join(details)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def cathie_wood_agent(state: AgentState) -> dict[str, Any]:
    """Run Cathie Wood's disruptive innovation analysis on every ticker in state.

    Returns updated state with analyst signals keyed by ``cathie_wood``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]
    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        try:
            logger.info("Cathie Wood analysing %s ...", ticker)

            # -- 1. Fetch data ------------------------------------------------
            metrics: list[FinancialMetrics] = api.get_financial_metrics(ticker, limit=10)
            line_items: list[LineItem] = api.get_line_items(
                ticker,
                line_items=[
                    "revenue",
                    "research_and_development",
                    "net_income",
                    "operating_income",
                ],
                limit=10,
            )
            prices: list[Price] = api.get_prices(ticker, limit=5)

            # -- 2. Deterministic scoring -------------------------------------
            growth_score, growth_details = _score_revenue_growth(metrics)
            rd_score, rd_details = _score_rd_intensity(line_items)
            tam_score, tam_details = _score_tam_expansion(metrics, line_items)
            margin_score, margin_details = _score_gross_margin_trajectory(metrics)

            total_score = (growth_score + rd_score + tam_score + margin_score) / 4.0

            # -- 3. Build analysis summary ------------------------------------
            analysis_summary = (
                f"Ticker: {ticker}\n"
                f"Overall Innovation Score: {total_score:.1f}/10\n\n"
                f"Revenue Growth ({growth_score:.1f}/10): {growth_details}\n"
                f"R&D Intensity ({rd_score:.1f}/10): {rd_details}\n"
                f"TAM Expansion ({tam_score:.1f}/10): {tam_details}\n"
                f"Gross Margin Trajectory ({margin_score:.1f}/10): {margin_details}\n"
            )

            if prices:
                analysis_summary += f"\nCurrent Price: ${prices[-1].close:.2f}\n"

            # -- 4. LLM synthesis ---------------------------------------------
            llm_result = call_llm(
                system_prompt=AGENT_SYSTEM_PROMPT,
                user_message=(
                    f"Based on the following analysis, evaluate {ticker}'s disruptive "
                    f"innovation potential. Consider whether this company is building "
                    f"the future or clinging to the past. Respond with JSON containing "
                    f"'signal', 'confidence', and 'reasoning'.\n\n{analysis_summary}"
                ),
                response_model=AnalystSignal,
            )

            signals[ticker] = {
                "signal": llm_result.signal,
                "confidence": llm_result.confidence,
                "reasoning": llm_result.reasoning,
                "agent_scores": {
                    "revenue_growth": growth_score,
                    "rd_intensity": rd_score,
                    "tam_expansion": tam_score,
                    "gross_margin_trajectory": margin_score,
                    "overall": total_score,
                },
            }
            logger.info(
                "Cathie Wood on %s: %s (confidence %.0f%%)",
                ticker,
                llm_result.signal,
                llm_result.confidence * 100,
            )

        except Exception:
            logger.exception("Cathie Wood agent failed on %s -- returning neutral.", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"cathie_wood": signals}}}
