"""Peter Lynch Agent -- GARP investing, "buy what you know", stock categorization.

Classifies companies into Lynch's categories (slow grower, stalwart, fast grower,
cyclical, turnaround), computes PEG ratios, and estimates fair value using
earnings growth. LLM evaluates business understandability and category fit.
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
You are Peter Lynch, the legendary manager of the Fidelity Magellan Fund, which \
under your stewardship from 1977 to 1990 returned an average of 29.2% per year, \
making it the best-performing mutual fund in the world. You are the author of \
"One Up On Wall Street" and "Beating the Street," two of the most accessible \
and practical investment books ever written.

Your philosophy can be distilled into a deceptively simple idea: invest in what \
you know, at a reasonable price.

Your core principles:

1. **Buy What You Know.** The best investment ideas come from everyday life, not \
from Wall Street research reports. You found Taco Bell by eating there, Hanes by \
noticing L'eggs pantyhose at the supermarket, and Dunkin' Donuts by loving the \
coffee. An ordinary person who pays attention to products, trends, and services \
can spot great investments before the professionals. "Everyone has the brainpower \
to follow the stock market. If you made it through fifth-grade math, you can do it."

2. **The PEG Ratio.** Your signature metric. A stock's PE ratio divided by its \
earnings growth rate gives you the PEG ratio. A PEG below 1.0 means the stock \
is cheap relative to its growth. A PEG above 2.0 means you are overpaying. \
"The P/E ratio of any company that's fairly priced will equal its growth rate."

3. **Stock Categories.** You classify every stock into one of six categories, and \
your expectations and strategy differ for each:
   - **Slow Growers (Sluggards):** Large, mature companies growing at 2-5%. You \
     buy these for dividends, not appreciation. Utilities and old-line industrials.
   - **Stalwarts:** Solid companies growing at 10-12%. Not exciting but reliable. \
     Coca-Cola, Procter & Gamble. You expect 30-50% gains, then sell and rotate.
   - **Fast Growers:** Small, aggressive companies growing at 20-50%+. These are \
     the ten-baggers. The key is finding ones with a long runway of growth ahead.
   - **Cyclicals:** Companies whose earnings rise and fall with the business cycle. \
     Autos, airlines, steel. Timing is everything -- buy at the bottom of the cycle.
   - **Turnarounds:** Companies emerging from near-death experiences. Chrysler, \
     Penn Central. Huge payoffs if they survive; total loss if they don't.
   - **Asset Plays:** Companies sitting on valuable assets the market hasn't \
     recognised -- real estate, intellectual property, hidden subsidiaries.

4. **The Two-Minute Drill.** You should be able to explain your investment thesis \
in two minutes or less. If you can't, you don't understand the business well \
enough. "If you can't explain to a ten-year-old in two minutes or less why you \
own a stock, you shouldn't own it."

5. **Do Your Homework.** Despite the folksy exterior, your research is rigorous. \
You visit companies, talk to management, check the competition, and read the \
financials. You look at the balance sheet, the cash position, and the debt level.

6. **Institutional Ownership.** You prefer stocks with low institutional ownership \
-- these are the undiscovered gems that haven't been bid up by professional money \
managers. By the time every mutual fund owns it, the easy money has been made.

7. **Long-Term Perspective with Pragmatic Exit.** You hold your winners and cut \
your losers. You don't sell a stock because it's gone up 50%; you sell because \
the story has changed. "Selling your winners and holding your losers is like \
cutting the flowers and watering the weeds."

Your tone is warm, folksy, and accessible. You use everyday analogies, sports \
metaphors, and self-deprecating humour. You occasionally reference your Magellan \
Fund days and specific stocks that made you money. You are genuinely enthusiastic \
about individual stock-picking and believe the small investor has advantages over \
Wall Street institutions.

You must produce a JSON response with the following fields:
- signal: one of "bullish", "bearish", or "neutral"
- confidence: a float between 0.0 and 1.0
- reasoning: a concise paragraph (2-4 sentences) in your folksy, practical voice
"""


# ---------------------------------------------------------------------------
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _compute_peg_ratio(pe: float | None, earnings_growth: float | None) -> float | None:
    """PEG = PE / (earnings growth rate * 100). Returns None if not computable."""
    if pe is None or earnings_growth is None:
        return None
    growth_pct = earnings_growth * 100  # Convert 0.15 -> 15
    if growth_pct <= 0:
        return None  # PEG undefined for negative or zero growth
    return pe / growth_pct


def _categorize_stock(
    metrics: list[FinancialMetrics],
    line_items: list[LineItem],
) -> tuple[str, str]:
    """Categorize stock into one of Lynch's six categories. Returns (category, reasoning)."""
    earnings_growth_vals = [m.earnings_growth for m in metrics if m.earnings_growth is not None]
    revenue_growth_vals = [m.revenue_growth for m in metrics if m.revenue_growth is not None]
    roes = [m.return_on_equity for m in metrics if m.return_on_equity is not None]

    avg_eg = sum(earnings_growth_vals) / len(earnings_growth_vals) if earnings_growth_vals else None
    avg_rg = sum(revenue_growth_vals) / len(revenue_growth_vals) if revenue_growth_vals else None

    # Check for turnaround: negative earnings turning positive
    net_incomes = [getattr(item, "net_income", None) for item in line_items]
    net_incomes = [n for n in net_incomes if n is not None]
    if len(net_incomes) >= 3:
        early_negative = any(n < 0 for n in net_incomes[:len(net_incomes) // 2])
        recent_positive = net_incomes[-1] > 0 if net_incomes else False
        if early_negative and recent_positive:
            return "turnaround", "Was losing money, now profitable -- classic turnaround candidate."

    # Use growth rate to categorize
    growth = avg_eg if avg_eg is not None else avg_rg

    if growth is None:
        return "unknown", "Insufficient data to categorize."

    if growth > 0.25:
        return "fast_grower", f"Earnings growing at {growth:.0%} -- fast grower with multi-bagger potential."
    elif growth > 0.10:
        return "stalwart", f"Growing at {growth:.0%} -- solid stalwart, good for 30-50% gains."
    elif growth > 0.02:
        return "slow_grower", f"Growing at {growth:.0%} -- slow grower, dividend play at best."
    elif growth < -0.10:
        # Check if it's cyclical (volatile earnings but stable revenue)
        if avg_rg is not None and avg_rg > 0:
            return "cyclical", f"Earnings declining ({growth:.0%}) but revenue growing -- likely cyclical."
        return "turnaround", f"Earnings declining ({growth:.0%}) -- potential turnaround or value trap."
    else:
        return "slow_grower", f"Minimal growth ({growth:.0%}) -- slow grower."


def _score_peg(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 based on PEG ratio."""
    pe_values = [m.pe_ratio for m in metrics if m.pe_ratio is not None]
    eg_values = [m.earnings_growth for m in metrics if m.earnings_growth is not None]

    if not pe_values or not eg_values:
        return 0.0, "Insufficient data to compute PEG ratio."

    peg = _compute_peg_ratio(pe_values[-1], eg_values[-1])

    if peg is None:
        return 0.0, f"PEG not computable (PE={pe_values[-1]:.1f}, growth={eg_values[-1]:.1%})."

    score = 0.0
    details: list[str] = []

    if peg < 0.5:
        score = 10.0
        details.append(f"PEG {peg:.2f} -- deeply undervalued relative to growth. Peter Lynch would be excited!")
    elif peg < 1.0:
        score = 8.0
        details.append(f"PEG {peg:.2f} -- attractively valued. Growth available at a reasonable price.")
    elif peg < 1.5:
        score = 5.0
        details.append(f"PEG {peg:.2f} -- fairly valued.")
    elif peg < 2.0:
        score = 3.0
        details.append(f"PEG {peg:.2f} -- getting expensive for this growth rate.")
    else:
        score = 1.0
        details.append(f"PEG {peg:.2f} -- overvalued. Growth doesn't justify the price.")

    return score, " ".join(details)


def _score_fair_value(
    metrics: list[FinancialMetrics],
    line_items: list[LineItem],
    current_price: float | None,
) -> tuple[float, str]:
    """Score 0-10: Lynch fair value = earnings growth rate * EPS."""
    eg_values = [m.earnings_growth for m in metrics if m.earnings_growth is not None]
    eps_values = [getattr(item, "earnings_per_share", None) for item in line_items]
    eps_values = [e for e in eps_values if e is not None]

    if not eg_values or not eps_values or current_price is None:
        return 0.0, "Insufficient data for fair value calculation."

    latest_growth = eg_values[-1]
    latest_eps = eps_values[-1]

    if latest_eps <= 0 or latest_growth <= 0:
        return 0.0, f"Cannot compute fair value with EPS={latest_eps:.2f} and growth={latest_growth:.1%}."

    # Lynch fair value: growth rate (as %) * EPS
    fair_value = (latest_growth * 100) * latest_eps
    discount = (fair_value - current_price) / fair_value if fair_value > 0 else 0

    score = 0.0
    details: list[str] = [f"Lynch fair value: ${fair_value:.2f} vs price ${current_price:.2f}."]

    if current_price < fair_value * 0.5:
        score = 10.0
        details.append(f"Trading at {discount:.0%} discount -- a potential ten-bagger!")
    elif current_price < fair_value * 0.75:
        score = 7.0
        details.append(f"Nice {discount:.0%} discount to fair value.")
    elif current_price < fair_value:
        score = 5.0
        details.append(f"Slight discount ({discount:.0%}) to fair value.")
    elif current_price < fair_value * 1.25:
        score = 3.0
        details.append("Trading near or slightly above fair value.")
    else:
        score = 1.0
        details.append(f"Overvalued by {-discount:.0%} relative to Lynch fair value.")

    return score, " ".join(details)


def _score_institutional_ownership(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10: lower institutional ownership = better for discovery potential."""
    inst_own_vals = [m.institutional_ownership for m in metrics if m.institutional_ownership is not None]

    if not inst_own_vals:
        return 5.0, "No institutional ownership data -- assuming neutral."

    latest = inst_own_vals[-1]

    if latest < 0.20:
        return 10.0, f"Only {latest:.0%} institutional ownership -- undiscovered gem!"
    elif latest < 0.40:
        return 7.0, f"Institutional ownership {latest:.0%} -- relatively under-owned."
    elif latest < 0.60:
        return 5.0, f"Institutional ownership {latest:.0%} -- moderate coverage."
    elif latest < 0.80:
        return 3.0, f"Institutional ownership {latest:.0%} -- well-covered by Wall Street."
    else:
        return 1.0, f"Institutional ownership {latest:.0%} -- very crowded, easy money likely gone."


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def peter_lynch_agent(state: AgentState) -> dict[str, Any]:
    """Run Peter Lynch's GARP analysis on every ticker in state.

    Returns updated state with analyst signals keyed by ``peter_lynch``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]
    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        try:
            logger.info("Peter Lynch analysing %s ...", ticker)

            # -- 1. Fetch data ------------------------------------------------
            metrics: list[FinancialMetrics] = api.get_financial_metrics(ticker, limit=10)
            line_items: list[LineItem] = api.get_line_items(
                ticker,
                line_items=[
                    "net_income",
                    "earnings_per_share",
                    "revenue",
                ],
                limit=10,
            )
            prices: list[Price] = api.get_prices(ticker, limit=5)

            current_price: float | None = prices[-1].close if prices else None

            # -- 2. Deterministic scoring -------------------------------------
            category, category_reasoning = _categorize_stock(metrics, line_items)
            peg_score, peg_details = _score_peg(metrics)
            fv_score, fv_details = _score_fair_value(metrics, line_items, current_price)
            inst_score, inst_details = _score_institutional_ownership(metrics)

            total_score = (peg_score + fv_score + inst_score) / 3.0

            # -- 3. Build analysis summary ------------------------------------
            analysis_summary = (
                f"Ticker: {ticker}\n"
                f"Stock Category: {category.replace('_', ' ').title()}\n"
                f"Category Reasoning: {category_reasoning}\n"
                f"Overall Lynch Score: {total_score:.1f}/10\n\n"
                f"PEG Ratio ({peg_score:.1f}/10): {peg_details}\n"
                f"Fair Value ({fv_score:.1f}/10): {fv_details}\n"
                f"Institutional Ownership ({inst_score:.1f}/10): {inst_details}\n"
            )

            if current_price is not None:
                analysis_summary += f"\nCurrent Price: ${current_price:.2f}\n"

            # -- 4. LLM synthesis ---------------------------------------------
            llm_result = call_llm(
                system_prompt=AGENT_SYSTEM_PROMPT,
                user_message=(
                    f"Based on the following analysis, provide your investment signal "
                    f"for {ticker}. Consider the stock's category ({category}) and "
                    f"whether this is a business an ordinary person could understand "
                    f"and explain in two minutes. Respond with JSON containing "
                    f"'signal', 'confidence', and 'reasoning'.\n\n{analysis_summary}"
                ),
                response_model=AnalystSignal,
            )

            signals[ticker] = {
                "signal": llm_result.signal,
                "confidence": llm_result.confidence,
                "reasoning": llm_result.reasoning,
                "agent_scores": {
                    "category": category,
                    "peg": peg_score,
                    "fair_value": fv_score,
                    "institutional_ownership": inst_score,
                    "overall": total_score,
                },
            }
            logger.info(
                "Lynch on %s (%s): %s (confidence %.0f%%)",
                ticker,
                category,
                llm_result.signal,
                llm_result.confidence * 100,
            )

        except Exception:
            logger.exception("Peter Lynch agent failed on %s -- returning neutral.", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"peter_lynch": signals}}}
