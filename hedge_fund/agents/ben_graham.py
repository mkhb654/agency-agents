"""Benjamin Graham Agent -- Deep value, margin of safety, quantitative screens.

Applies Graham's strict quantitative criteria (Graham Number, net-net,
PE/PB thresholds, current ratio, earnings stability, dividend record)
and lets the LLM deliver the final judgment in Graham's scholarly voice.
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
# System prompt
# ---------------------------------------------------------------------------
AGENT_SYSTEM_PROMPT = """\
You are Benjamin Graham, the father of value investing and the author of \
"The Intelligent Investor" and "Security Analysis." You are a professor at \
Columbia Business School and the intellectual architect of the entire discipline \
of fundamental security analysis.

Your philosophy is grounded in several immovable principles:

1. **Margin of Safety.** This is the central concept of your entire framework. \
You never purchase a security unless its market price is substantially below your \
conservative estimate of intrinsic value. "The function of the margin of safety \
is, in essence, that of rendering unnecessary an accurate estimate of the future." \
A 30-50% discount to intrinsic value is your minimum requirement.

2. **Mr. Market.** You view the stock market as an emotional, manic-depressive \
business partner who offers to buy or sell shares at wildly varying prices every \
day. Sometimes Mr. Market is euphoric and offers absurdly high prices; other times \
he is despondent and sells for a pittance. The intelligent investor exploits \
Mr. Market's folly rather than being guided by it.

3. **Quantitative Screens.** You rely on strict, mathematical criteria to filter \
securities. You do not trust qualitative assessments or management promises. \
Numbers do not lie -- or at least, they lie less than people. Your key screens:
   - PE ratio below 15 (preferably below 10)
   - Price-to-book below 1.5
   - PE * PB product below 22.5
   - Current ratio above 2.0
   - Positive earnings for at least 5 consecutive years
   - Consistent dividend payments
   - Graham Number = sqrt(22.5 * EPS * Book Value Per Share)

4. **Net-Net Working Capital.** Your most stringent and most profitable screen: \
buy companies trading below their net current asset value (current assets minus \
ALL liabilities). These "cigar butt" investments may not be beautiful businesses, \
but they have one last profitable puff remaining.

5. **Defensive vs. Enterprising Investor.** You distinguish between the defensive \
investor (who seeks safety and minimal effort) and the enterprising investor (who \
does intensive research for superior returns). Your screens apply most rigorously \
to the defensive investor.

6. **Earnings Stability.** You insist on a demonstrated record of earnings. \
Speculation on future earnings is the province of the gambler, not the investor. \
"An investment operation is one which, upon thorough analysis, promises safety of \
principal and an adequate return. Operations not meeting these requirements are \
speculative."

Your tone is professorial, precise, and occasionally sardonic. You speak in \
carefully constructed paragraphs, cite data fastidiously, and have little patience \
for Wall Street's promotional excesses. You occasionally reference your experience \
during the 1929 crash and the subsequent Depression.

You must produce a JSON response with the following fields:
- signal: one of "bullish", "bearish", or "neutral"
- confidence: a float between 0.0 and 1.0
- reasoning: a concise paragraph (2-4 sentences) explaining your thesis in your \
  authentic analytical voice
"""


# ---------------------------------------------------------------------------
# Deterministic scoring helpers
# ---------------------------------------------------------------------------

def _compute_graham_number(eps: float | None, book_value_per_share: float | None) -> float | None:
    """Graham Number = sqrt(22.5 * EPS * BVPS). Returns None if inputs invalid."""
    if eps is None or book_value_per_share is None:
        return None
    if eps <= 0 or book_value_per_share <= 0:
        return None
    return math.sqrt(22.5 * eps * book_value_per_share)


def _score_valuation(
    metrics: list[FinancialMetrics],
    line_items: list[LineItem],
    current_price: float | None,
) -> tuple[float, str]:
    """Score 0-10 based on Graham's valuation criteria."""
    score = 0.0
    details: list[str] = []

    # PE ratio
    pe_values = [m.pe_ratio for m in metrics if m.pe_ratio is not None]
    if pe_values:
        latest_pe = pe_values[-1]
        if latest_pe < 10:
            score += 2.5
            details.append(f"PE ratio {latest_pe:.1f} -- deeply undervalued by Graham standards.")
        elif latest_pe < 15:
            score += 1.5
            details.append(f"PE ratio {latest_pe:.1f} -- within Graham's acceptable range.")
        elif latest_pe < 20:
            score += 0.5
            details.append(f"PE ratio {latest_pe:.1f} -- moderately overvalued.")
        else:
            details.append(f"PE ratio {latest_pe:.1f} -- exceeds Graham's threshold of 15.")
    else:
        details.append("No PE data available.")

    # Price to book
    pb_values = [m.price_to_book for m in metrics if m.price_to_book is not None]
    if pb_values:
        latest_pb = pb_values[-1]
        if latest_pb < 1.0:
            score += 2.5
            details.append(f"P/B {latest_pb:.2f} -- trading below book value.")
        elif latest_pb < 1.5:
            score += 1.5
            details.append(f"P/B {latest_pb:.2f} -- within Graham's limit.")
        elif latest_pb < 2.0:
            score += 0.5
            details.append(f"P/B {latest_pb:.2f} -- slightly above Graham's threshold.")
        else:
            details.append(f"P/B {latest_pb:.2f} -- well above the 1.5 ceiling.")
    else:
        details.append("No price-to-book data available.")

    # PE * PB < 22.5
    if pe_values and pb_values:
        pe_pb_product = pe_values[-1] * pb_values[-1]
        if pe_pb_product < 22.5:
            score += 2.0
            details.append(f"PE*PB product {pe_pb_product:.1f} < 22.5 -- passes Graham screen.")
        else:
            details.append(f"PE*PB product {pe_pb_product:.1f} -- fails the 22.5 ceiling.")

    # Graham Number vs current price
    eps_values = [getattr(item, "earnings_per_share", None) for item in line_items]
    eps_values = [e for e in eps_values if e is not None]
    bvps_values = [getattr(item, "book_value_per_share", None) for item in line_items]
    bvps_values = [b for b in bvps_values if b is not None]

    if eps_values and bvps_values and current_price:
        graham_num = _compute_graham_number(eps_values[-1], bvps_values[-1])
        if graham_num is not None:
            if current_price < graham_num * 0.7:
                score += 3.0
                details.append(
                    f"Graham Number ${graham_num:.2f} vs price ${current_price:.2f} -- "
                    f"large margin of safety ({(1 - current_price / graham_num):.0%} discount)."
                )
            elif current_price < graham_num:
                score += 2.0
                details.append(
                    f"Graham Number ${graham_num:.2f} vs price ${current_price:.2f} -- "
                    f"trading below intrinsic value."
                )
            else:
                details.append(
                    f"Graham Number ${graham_num:.2f} vs price ${current_price:.2f} -- "
                    f"stock trades above calculated intrinsic value."
                )

    return min(score, 10.0), " ".join(details)


def _score_net_net(line_items: list[LineItem], current_price: float | None) -> tuple[float, str]:
    """Score 0-10: net-net working capital analysis."""
    if not line_items:
        return 0.0, "No balance sheet data for net-net analysis."

    current_assets_vals = [getattr(item, "total_current_assets", None) for item in line_items]
    total_liabilities_vals = [getattr(item, "total_liabilities", None) for item in line_items]
    shares_vals = [getattr(item, "shares_outstanding", None) for item in line_items]

    ca = next((v for v in reversed(current_assets_vals) if v is not None), None)
    tl = next((v for v in reversed(total_liabilities_vals) if v is not None), None)
    shares = next((v for v in reversed(shares_vals) if v is not None and v > 0), None)

    if ca is None or tl is None or shares is None:
        return 0.0, "Insufficient data for net-net calculation."

    ncav_per_share = (ca - tl) / shares
    details_parts: list[str] = [f"NCAV per share: ${ncav_per_share:.2f}."]

    if ncav_per_share <= 0:
        return 0.0, " ".join(details_parts) + " Negative NCAV -- not a net-net candidate."

    if current_price is None:
        return 2.0, " ".join(details_parts) + " No price data to compare."

    discount = 1.0 - (current_price / ncav_per_share) if ncav_per_share > 0 else 0

    if current_price < ncav_per_share * 0.67:
        score = 10.0
        details_parts.append(
            f"Price ${current_price:.2f} is {discount:.0%} below NCAV -- classic Graham cigar butt!"
        )
    elif current_price < ncav_per_share:
        score = 7.0
        details_parts.append(f"Price ${current_price:.2f} below NCAV -- interesting net-net candidate.")
    elif current_price < ncav_per_share * 1.5:
        score = 3.0
        details_parts.append(f"Price ${current_price:.2f} moderately above NCAV.")
    else:
        score = 0.0
        details_parts.append(f"Price ${current_price:.2f} well above NCAV -- not a net-net.")

    return score, " ".join(details_parts)


def _score_financial_strength(metrics: list[FinancialMetrics]) -> tuple[float, str]:
    """Score 0-10: current ratio, debt levels."""
    score = 0.0
    details: list[str] = []

    current_ratios = [m.current_ratio for m in metrics if m.current_ratio is not None]
    if current_ratios:
        latest_cr = current_ratios[-1]
        if latest_cr >= 2.0:
            score += 5.0
            details.append(f"Current ratio {latest_cr:.2f} -- meets Graham's 2.0 minimum.")
        elif latest_cr >= 1.5:
            score += 3.0
            details.append(f"Current ratio {latest_cr:.2f} -- adequate but below the 2.0 ideal.")
        elif latest_cr >= 1.0:
            score += 1.0
            details.append(f"Current ratio {latest_cr:.2f} -- marginal liquidity.")
        else:
            details.append(f"Current ratio {latest_cr:.2f} -- worrisome liquidity position.")
    else:
        details.append("No current ratio data available.")

    debt_to_equity_vals = [m.debt_to_equity for m in metrics if m.debt_to_equity is not None]
    if debt_to_equity_vals:
        latest_de = debt_to_equity_vals[-1]
        if latest_de < 0.5:
            score += 5.0
            details.append(f"D/E {latest_de:.2f} -- conservative balance sheet.")
        elif latest_de < 1.0:
            score += 3.0
            details.append(f"D/E {latest_de:.2f} -- moderate leverage.")
        elif latest_de < 2.0:
            score += 1.0
            details.append(f"D/E {latest_de:.2f} -- above-average leverage.")
        else:
            details.append(f"D/E {latest_de:.2f} -- excessive debt, Graham would disapprove.")
    else:
        details.append("No debt-to-equity data available.")

    return min(score, 10.0), " ".join(details)


def _score_earnings_stability(line_items: list[LineItem]) -> tuple[float, str]:
    """Score 0-10: positive earnings consistency and dividend record."""
    score = 0.0
    details: list[str] = []

    # Earnings stability: positive for 5+ years
    earnings = [getattr(item, "net_income", None) for item in line_items]
    earnings = [e for e in earnings if e is not None]

    if earnings:
        positive_count = sum(1 for e in earnings if e > 0)
        total = len(earnings)
        if positive_count == total and total >= 5:
            score += 5.0
            details.append(f"Positive earnings in all {total} periods -- excellent stability.")
        elif positive_count == total:
            score += 4.0
            details.append(f"Positive earnings in all {total} periods (fewer than 5 available).")
        elif positive_count / total >= 0.8:
            score += 2.0
            details.append(f"Positive earnings in {positive_count}/{total} periods -- mostly stable.")
        else:
            details.append(f"Positive earnings in only {positive_count}/{total} periods -- unstable.")
    else:
        details.append("No earnings data to evaluate stability.")

    # Dividend record
    dividends = [getattr(item, "dividends_paid", None) for item in line_items]
    dividends = [d for d in dividends if d is not None]
    dividend_payers = sum(1 for d in dividends if d != 0)

    if dividends:
        if dividend_payers == len(dividends) and len(dividends) >= 5:
            score += 5.0
            details.append(f"Consistent dividend payer across all {len(dividends)} periods.")
        elif dividend_payers == len(dividends):
            score += 4.0
            details.append(f"Dividend payer in all {len(dividends)} periods (fewer than 5).")
        elif dividend_payers > 0:
            ratio = dividend_payers / len(dividends)
            score += ratio * 3.0
            details.append(f"Dividends paid in {dividend_payers}/{len(dividends)} periods.")
        else:
            details.append("No dividends paid -- Graham preferred dividend-paying stocks.")
    else:
        details.append("No dividend data available.")

    return min(score, 10.0), " ".join(details)


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def ben_graham_agent(state: AgentState) -> dict[str, Any]:
    """Run Benjamin Graham's deep-value quantitative analysis on every ticker.

    Returns updated state with analyst signals keyed by ``ben_graham``.
    """
    data: dict[str, Any] = state["data"]
    tickers: list[str] = data["tickers"]
    api = FinancialDataClient()
    signals: dict[str, Any] = {}

    for ticker in tickers:
        try:
            logger.info("Benjamin Graham analysing %s ...", ticker)

            # -- 1. Fetch data ------------------------------------------------
            metrics: list[FinancialMetrics] = api.get_financial_metrics(ticker, limit=10)
            line_items: list[LineItem] = api.get_line_items(
                ticker,
                line_items=[
                    "net_income",
                    "earnings_per_share",
                    "book_value_per_share",
                    "total_current_assets",
                    "total_liabilities",
                    "shares_outstanding",
                    "dividends_paid",
                ],
                limit=10,
            )
            prices: list[Price] = api.get_prices(ticker, limit=5)

            current_price: float | None = prices[-1].close if prices else None

            # -- 2. Deterministic scoring -------------------------------------
            val_score, val_details = _score_valuation(metrics, line_items, current_price)
            nn_score, nn_details = _score_net_net(line_items, current_price)
            fs_score, fs_details = _score_financial_strength(metrics)
            es_score, es_details = _score_earnings_stability(line_items)

            total_score = (val_score + nn_score + fs_score + es_score) / 4.0

            # -- 3. Build analysis summary ------------------------------------
            analysis_summary = (
                f"Ticker: {ticker}\n"
                f"Overall Graham Score: {total_score:.1f}/10\n\n"
                f"Valuation ({val_score:.1f}/10): {val_details}\n"
                f"Net-Net Analysis ({nn_score:.1f}/10): {nn_details}\n"
                f"Financial Strength ({fs_score:.1f}/10): {fs_details}\n"
                f"Earnings Stability ({es_score:.1f}/10): {es_details}\n"
            )

            if current_price is not None:
                analysis_summary += f"\nCurrent Price: ${current_price:.2f}\n"

            # -- 4. LLM synthesis ---------------------------------------------
            llm_result = call_llm(
                system_prompt=AGENT_SYSTEM_PROMPT,
                user_message=(
                    f"Based on the following quantitative analysis, provide your "
                    f"investment judgment for {ticker}. Respond with JSON containing "
                    f"'signal', 'confidence', and 'reasoning'.\n\n{analysis_summary}"
                ),
                response_model=AnalystSignal,
            )

            signals[ticker] = {
                "signal": llm_result.signal,
                "confidence": llm_result.confidence,
                "reasoning": llm_result.reasoning,
                "agent_scores": {
                    "valuation": val_score,
                    "net_net": nn_score,
                    "financial_strength": fs_score,
                    "earnings_stability": es_score,
                    "overall": total_score,
                },
            }
            logger.info(
                "Graham on %s: %s (confidence %.0f%%)",
                ticker,
                llm_result.signal,
                llm_result.confidence * 100,
            )

        except Exception:
            logger.exception("Benjamin Graham agent failed on %s -- returning neutral.", ticker)
            signals[ticker] = {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": f"Analysis failed for {ticker}; defaulting to neutral.",
                "agent_scores": {},
            }

    return {"data": {"analyst_signals": {"ben_graham": signals}}}
