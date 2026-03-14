"""Warren Buffett Agent -- Value investing, durable competitive advantages, owner earnings.

Combines deterministic scoring of moat strength, owner earnings quality,
management integrity, and pricing power with an LLM synthesis step that
channels Buffett's philosophy to produce a final trading signal.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from hedge_fund.data.api import FinancialDataClient
from hedge_fund.data.models import AnalystSignal, FinancialMetrics, LineItem, Price
from hedge_fund.graph.state import AgentState
from hedge_fund.llm.models import call_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- rich, compelling, channeling the Oracle of Omaha
# ---------------------------------------------------------------------------
AGENT_SYSTEM_PROMPT = """\
You are Warren Buffett, the Oracle of Omaha, chairman of Berkshire Hathaway and \
widely regarded as the greatest long-term investor in history.

Your investment philosophy rests on a small number of bedrock principles that you \
have articulated over decades in shareholder letters, interviews, and the annual \
Berkshire meetings:

1. **Circle of Competence.** You only invest in businesses you understand deeply. \
If you cannot explain a company's economics to a ten-year-old in five minutes, you \
pass. You would rather miss a hundred opportunities than make one uninformed bet.

2. **Durable Competitive Advantages (Moats).** You seek businesses with wide, \
defensible moats -- brands, switching costs, network effects, cost advantages, or \
regulatory licenses that protect returns on capital for decades. A business without \
a moat is a "commodity in disguise."

3. **Owner Earnings.** Reported earnings are an accounting fiction. What matters \
is the cash a business generates for its owners after maintaining its competitive \
position: net income + depreciation/amortisation - normalised capital expenditure. \
You treat this as the true measure of economic value.

4. **Management Quality.** You invest with managers who think like owners -- \
those who allocate capital rationally, buy back shares when cheap, maintain \
conservative balance sheets, and communicate honestly. "When a management with \
a reputation for brilliance tackles a business with a reputation for bad economics, \
it is the reputation of the business that remains intact."

5. **Margin of Safety.** You never pay more than intrinsic value, and you prefer \
a healthy discount. "Price is what you pay; value is what you get." You are patient \
and will wait years for the right pitch. "The stock market is a device for \
transferring money from the impatient to the patient."

6. **Long-Term Orientation.** Your favourite holding period is forever. You ignore \
quarterly noise, macro predictions, and market timing. "Our favorite holding period \
is forever." You focus on the ten-year outlook.

7. **Emotional Discipline.** "Be fearful when others are greedy, and greedy when \
others are fearful." You see market downturns as opportunities, not threats.

When analysing a stock, you speak plainly and folksy, with dry Midwestern humour. \
You reference See's Candies, Coca-Cola, GEICO, and the Nebraska Furniture Mart to \
illustrate your points. You are deeply sceptical of excessive debt, financial \
engineering, and businesses that require constant reinvestment just to stand still.

Your analytical framework:
- Examine return on equity over 5+ years -- consistency above 15% signals a moat.
- Study gross and operating margin trends -- expanding or stable margins indicate \
  pricing power.
- Calculate owner earnings and compare to reported net income.
- Assess debt levels -- prefer total debt < 3x owner earnings.
- Evaluate management's capital allocation: buybacks at sensible prices, dividends \
  that grow, and acquisitions that earn above cost of capital.
- Estimate intrinsic value using a discounted owner-earnings model and demand a \
  margin of safety.

You must produce a JSON response with the following fields:
- signal: one of "bullish", "bearish", or "neutral"
- confidence: a float between 0.0 and 1.0
- reasoning: a concise paragraph (2-4 sentences) explaining your investment thesis \
  in your authentic voice
"""


# ---------------------------------------------------------------------------
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _score_moat(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 based on ROE consistency, margin stability, and low debt."""
    if not metrics:
        return 0.0, "Insufficient data to assess competitive moat."

    roes = [m.return_on_equity for m in metrics if m.return_on_equity is not None]
    gross_margins = [m.gross_margin for m in metrics if m.gross_margin is not None]
    debt_to_equity_vals = [m.debt_to_equity for m in metrics if m.debt_to_equity is not None]

    score = 0.0
    details: list[str] = []

    # ROE consistency above 15%
    if roes:
        avg_roe = sum(roes) / len(roes)
        above_threshold = sum(1 for r in roes if r > 0.15)
        roe_consistency = above_threshold / len(roes)
        roe_score = min(roe_consistency * 4.0, 4.0)  # max 4 points
        score += roe_score
        details.append(f"Avg ROE {avg_roe:.1%}, {above_threshold}/{len(roes)} periods above 15%.")
    else:
        details.append("No ROE data available.")

    # Gross margin stability / growth
    if len(gross_margins) >= 2:
        margin_trend = gross_margins[-1] - gross_margins[0]
        margin_stability = 1.0 - (max(gross_margins) - min(gross_margins))
        margin_score = 0.0
        if margin_trend >= 0:
            margin_score += 1.5
        if margin_stability > 0.85:
            margin_score += 1.5
        score += min(margin_score, 3.0)  # max 3 points
        details.append(f"Gross margin trend {'positive' if margin_trend >= 0 else 'negative'} "
                       f"({gross_margins[0]:.1%} -> {gross_margins[-1]:.1%}).")
    else:
        details.append("Insufficient margin data for trend analysis.")

    # Low debt
    if debt_to_equity_vals:
        avg_de = sum(debt_to_equity_vals) / len(debt_to_equity_vals)
        if avg_de < 0.5:
            score += 3.0
        elif avg_de < 1.0:
            score += 2.0
        elif avg_de < 2.0:
            score += 1.0
        details.append(f"Avg debt-to-equity {avg_de:.2f}.")
    else:
        details.append("No debt data available.")

    return min(score, 10.0), " ".join(details)


def _score_owner_earnings(line_items: list[LineItem]) -> tuple[float, str]:
    """Score 0-10 based on owner earnings quality."""
    if not line_items:
        return 0.0, "No line-item data for owner earnings calculation."

    owner_earnings_list: list[float] = []
    net_incomes: list[float] = []

    for item in line_items:
        ni = getattr(item, "net_income", None)
        dep = getattr(item, "depreciation_and_amortization", None)
        capex = getattr(item, "capital_expenditure", None)

        if ni is not None:
            net_incomes.append(ni)
            dep_val = dep if dep is not None else 0.0
            capex_val = abs(capex) if capex is not None else 0.0
            oe = ni + dep_val - capex_val
            owner_earnings_list.append(oe)

    if not owner_earnings_list:
        return 0.0, "Could not compute owner earnings from available data."

    score = 0.0
    details: list[str] = []

    # Positive owner earnings
    positive_count = sum(1 for oe in owner_earnings_list if oe > 0)
    positivity_ratio = positive_count / len(owner_earnings_list)
    score += positivity_ratio * 4.0  # max 4 points
    details.append(f"Owner earnings positive in {positive_count}/{len(owner_earnings_list)} periods.")

    # Growing owner earnings
    if len(owner_earnings_list) >= 2 and owner_earnings_list[0] != 0:
        growth = (owner_earnings_list[-1] - owner_earnings_list[0]) / abs(owner_earnings_list[0])
        if growth > 0.5:
            score += 3.0
        elif growth > 0.1:
            score += 2.0
        elif growth > 0:
            score += 1.0
        details.append(f"Owner earnings growth {growth:.1%} over the period.")

    # Owner earnings > net income (sign of conservative accounting)
    if net_incomes and owner_earnings_list:
        avg_oe = sum(owner_earnings_list) / len(owner_earnings_list)
        avg_ni = sum(net_incomes) / len(net_incomes)
        if avg_ni != 0 and avg_oe / avg_ni > 1.0:
            score += 3.0
            details.append("Owner earnings exceed reported net income -- a positive sign.")
        elif avg_ni != 0:
            ratio = avg_oe / avg_ni
            score += max(ratio * 3.0, 0.0)
            details.append(f"Owner earnings / net income ratio: {ratio:.2f}.")

    return min(score, 10.0), " ".join(details)


def _score_management(metrics: list[FinancialMetrics], line_items: list[LineItem]) -> tuple[float, str]:
    """Score 0-10 based on ROE consistency, buybacks, and dividend growth."""
    score = 0.0
    details: list[str] = []

    # ROE consistency (already partially covered in moat but here focused on management)
    roes = [m.return_on_equity for m in metrics if m.return_on_equity is not None]
    if len(roes) >= 3:
        roe_std = _std(roes)
        avg_roe = sum(roes) / len(roes)
        if avg_roe > 0.15 and roe_std < 0.05:
            score += 4.0
            details.append(f"Highly consistent ROE (avg {avg_roe:.1%}, std {roe_std:.3f}).")
        elif avg_roe > 0.10:
            score += 2.0
            details.append(f"Moderate ROE (avg {avg_roe:.1%}).")
        else:
            details.append(f"Below-threshold ROE (avg {avg_roe:.1%}).")
    else:
        details.append("Insufficient ROE history to evaluate management.")

    # Share buybacks -- look for declining share count
    shares = [getattr(item, "shares_outstanding", None) for item in line_items]
    shares = [s for s in shares if s is not None and s > 0]
    if len(shares) >= 2:
        if shares[-1] < shares[0]:
            reduction_pct = (shares[0] - shares[-1]) / shares[0]
            buyback_score = min(reduction_pct * 30, 3.0)  # up to 3 points
            score += buyback_score
            details.append(f"Shares reduced by {reduction_pct:.1%} -- management buying back stock.")
        else:
            details.append("Share count stable or increasing -- no buyback signal.")

    # Dividend growth
    dividends = [getattr(item, "dividends_paid", None) for item in line_items]
    dividends = [abs(d) for d in dividends if d is not None and d != 0]
    if len(dividends) >= 2 and dividends[0] > 0:
        div_growth = (dividends[-1] - dividends[0]) / dividends[0]
        if div_growth > 0:
            score += min(div_growth * 5, 3.0)  # up to 3 points
            details.append(f"Dividends grew {div_growth:.1%} over the period.")
        else:
            details.append("Dividends declined or stagnant.")
    else:
        details.append("Insufficient dividend history.")

    return min(score, 10.0), " ".join(details)


def _score_pricing_power(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10 based on gross margin stability and growth."""
    gross_margins = [m.gross_margin for m in metrics if m.gross_margin is not None]

    if len(gross_margins) < 2:
        return 0.0, "Insufficient margin data to assess pricing power."

    score = 0.0
    details: list[str] = []

    # Absolute margin level
    avg_margin = sum(gross_margins) / len(gross_margins)
    if avg_margin > 0.60:
        score += 4.0
        details.append(f"Excellent avg gross margin {avg_margin:.1%}.")
    elif avg_margin > 0.40:
        score += 3.0
        details.append(f"Good avg gross margin {avg_margin:.1%}.")
    elif avg_margin > 0.25:
        score += 2.0
        details.append(f"Moderate avg gross margin {avg_margin:.1%}.")
    else:
        score += 1.0
        details.append(f"Low avg gross margin {avg_margin:.1%}.")

    # Margin trend
    trend = gross_margins[-1] - gross_margins[0]
    if trend > 0.05:
        score += 3.0
        details.append("Strong upward margin trend -- pricing power is expanding.")
    elif trend > 0:
        score += 2.0
        details.append("Slight upward margin trend.")
    elif trend > -0.03:
        score += 1.0
        details.append("Margins roughly stable.")
    else:
        details.append("Declining margins -- pricing power may be eroding.")

    # Margin stability (low volatility)
    margin_std = _std(gross_margins)
    if margin_std < 0.02:
        score += 3.0
        details.append("Extremely stable margins.")
    elif margin_std < 0.05:
        score += 2.0
        details.append("Reasonably stable margins.")
    elif margin_std < 0.10:
        score += 1.0
        details.append("Some margin volatility.")
    else:
        details.append("High margin volatility -- inconsistent pricing power.")

    return min(score, 10.0), " ".join(details)


def _std(values: list[float]) -> float:
    """Compute population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def warren_buffett_agent(state: AgentState) -> dict[str, Any]:
    """Run the Warren Buffett value-investing analysis on every ticker in state.

    Returns updated state with analyst signals keyed by ``warren_buffett``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]
    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        try:
            logger.info("Warren Buffett analysing %s ...", ticker)

            # -- 1. Fetch data ------------------------------------------------
            metrics: list[FinancialMetrics] = api.get_financial_metrics(ticker, limit=10)
            line_items: list[LineItem] = api.get_line_items(
                ticker,
                line_items=[
                    "net_income",
                    "depreciation_and_amortization",
                    "capital_expenditure",
                    "shares_outstanding",
                    "dividends_paid",
                ],
                limit=10,
            )
            prices: list[Price] = api.get_prices(ticker, limit=252)

            # -- 2. Deterministic scoring -------------------------------------
            moat_score, moat_details = _score_moat(metrics)
            oe_score, oe_details = _score_owner_earnings(line_items)
            mgmt_score, mgmt_details = _score_management(metrics, line_items)
            pricing_score, pricing_details = _score_pricing_power(metrics)

            total_score = (moat_score + oe_score + mgmt_score + pricing_score) / 4.0

            # -- 3. Build analysis for LLM ------------------------------------
            analysis_summary = (
                f"Ticker: {ticker}\n"
                f"Overall Buffett Score: {total_score:.1f}/10\n\n"
                f"Moat Analysis ({moat_score:.1f}/10): {moat_details}\n"
                f"Owner Earnings ({oe_score:.1f}/10): {oe_details}\n"
                f"Management Quality ({mgmt_score:.1f}/10): {mgmt_details}\n"
                f"Pricing Power ({pricing_score:.1f}/10): {pricing_details}\n"
            )

            if prices:
                current_price = prices[-1].close
                price_52w_ago = prices[0].close if len(prices) >= 252 else prices[0].close
                price_change = ((current_price - price_52w_ago) / price_52w_ago) if price_52w_ago else 0
                analysis_summary += (
                    f"\nCurrent Price: ${current_price:.2f}\n"
                    f"Price Change (period): {price_change:.1%}\n"
                )

            # -- 4. LLM synthesis ---------------------------------------------
            llm_result = call_llm(
                system_prompt=AGENT_SYSTEM_PROMPT,
                user_message=(
                    f"Based on the following deterministic analysis, provide your "
                    f"investment signal for {ticker}. Respond with JSON containing "
                    f"'signal', 'confidence', and 'reasoning'.\n\n{analysis_summary}"
                ),
                response_model=AnalystSignal,
            )

            signals[ticker] = {
                "signal": llm_result.signal,
                "confidence": llm_result.confidence,
                "reasoning": llm_result.reasoning,
                "agent_scores": {
                    "moat": moat_score,
                    "owner_earnings": oe_score,
                    "management": mgmt_score,
                    "pricing_power": pricing_score,
                    "overall": total_score,
                },
            }
            logger.info(
                "Buffett on %s: %s (confidence %.0f%%)",
                ticker,
                llm_result.signal,
                llm_result.confidence * 100,
            )

        except Exception:
            logger.exception("Warren Buffett agent failed on %s -- returning neutral.", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"warren_buffett": signals}}}
