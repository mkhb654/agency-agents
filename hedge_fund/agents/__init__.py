"""Agent registry for the AI hedge fund.

Defines the execution order and configuration for all analyst agents.
Each agent is categorised as one of:
  - ``investor_persona``: agents that emulate a famous investor's style
  - ``analytical``: quantitative / data-driven analysis agents
  - ``decision``: portfolio-level decision-making agents

The ``ANALYST_ORDER`` list determines the sequence in which agents execute
inside the LangGraph pipeline.  ``ANALYST_CONFIG`` maps each agent's
identifier to its metadata and callable.
"""

from __future__ import annotations

from typing import Any, Callable

from hedge_fund.agents.ben_graham import ben_graham_agent
from hedge_fund.agents.cathie_wood import cathie_wood_agent
from hedge_fund.agents.fundamentals import fundamentals_agent
from hedge_fund.agents.macro import macro_agent
from hedge_fund.agents.michael_burry import michael_burry_agent
from hedge_fund.agents.peter_lynch import peter_lynch_agent
from hedge_fund.agents.sentiment import sentiment_agent
from hedge_fund.agents.stanley_druckenmiller import stanley_druckenmiller_agent
from hedge_fund.agents.technicals import technicals_agent
from hedge_fund.agents.valuation import valuation_agent
from hedge_fund.agents.warren_buffett import warren_buffett_agent

# ---------------------------------------------------------------------------
# Execution order -- agents run in this sequence within the analysis graph.
# ---------------------------------------------------------------------------

ANALYST_ORDER: list[str] = [
    "fundamentals",
    "technicals",
    "sentiment",
    "valuation",
    "macro",
    "warren_buffett",
    "ben_graham",
    "cathie_wood",
    "michael_burry",
    "peter_lynch",
    "stanley_druckenmiller",
]

# ---------------------------------------------------------------------------
# Agent configuration registry
# ---------------------------------------------------------------------------

ANALYST_CONFIG: dict[str, dict[str, Any]] = {
    "fundamentals": {
        "name": "Fundamentals Analyst",
        "description": (
            "Rule-based scoring of profitability, growth, financial health, "
            "and valuation metrics across the last 4 quarters."
        ),
        "function": fundamentals_agent,
        "category": "analytical",
    },
    "technicals": {
        "name": "Technical Analyst",
        "description": (
            "Rule-based multi-strategy technical analysis using trend following, "
            "mean reversion, momentum, volatility, and statistical signals."
        ),
        "function": technicals_agent,
        "category": "analytical",
    },
    "sentiment": {
        "name": "Sentiment Analyst",
        "description": (
            "Hybrid agent combining insider-trade scoring with LLM-powered "
            "news headline sentiment analysis."
        ),
        "function": sentiment_agent,
        "category": "analytical",
    },
    "valuation": {
        "name": "Valuation Analyst",
        "description": (
            "Rule-based intrinsic value estimation using DCF, owner-earnings, "
            "EV/EBITDA relative, and residual-income models."
        ),
        "function": valuation_agent,
        "category": "analytical",
    },
    "macro": {
        "name": "Macro Analyst",
        "description": (
            "LLM-powered macroeconomic analysis evaluating sector momentum, "
            "interest-rate sensitivity, currency exposure, and commodity dependency."
        ),
        "function": macro_agent,
        "category": "analytical",
    },
    # ------------------------------------------------------------------
    # Investor persona agents
    # ------------------------------------------------------------------
    "warren_buffett": {
        "name": "Warren Buffett",
        "description": (
            "Value investing agent scoring moat strength, owner earnings, "
            "management quality, and pricing power."
        ),
        "function": warren_buffett_agent,
        "category": "investor_persona",
    },
    "ben_graham": {
        "name": "Benjamin Graham",
        "description": (
            "Deep value agent applying Graham Number, net-net analysis, "
            "PE/PB screens, and margin-of-safety criteria."
        ),
        "function": ben_graham_agent,
        "category": "investor_persona",
    },
    "cathie_wood": {
        "name": "Cathie Wood",
        "description": (
            "Disruptive innovation agent evaluating revenue growth, R&D intensity, "
            "TAM expansion, and gross margin trajectory."
        ),
        "function": cathie_wood_agent,
        "category": "investor_persona",
    },
    "michael_burry": {
        "name": "Michael Burry",
        "description": (
            "Contrarian agent detecting overvaluation, debt risk, cash-flow divergence, "
            "and bubble indicators."
        ),
        "function": michael_burry_agent,
        "category": "investor_persona",
    },
    "peter_lynch": {
        "name": "Peter Lynch",
        "description": (
            "GARP agent computing PEG ratios, categorising stocks, estimating "
            "fair value, and assessing institutional ownership."
        ),
        "function": peter_lynch_agent,
        "category": "investor_persona",
    },
    "stanley_druckenmiller": {
        "name": "Stanley Druckenmiller",
        "description": (
            "Macro investing agent analysing sector momentum, revenue acceleration, "
            "FCF yield, and price trend strength."
        ),
        "function": stanley_druckenmiller_agent,
        "category": "investor_persona",
    },
}


def get_agent_function(agent_id: str) -> Callable[..., dict[str, Any]]:
    """Return the callable for *agent_id*, raising ``KeyError`` if unknown."""
    return ANALYST_CONFIG[agent_id]["function"]
