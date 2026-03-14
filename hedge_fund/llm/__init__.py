"""LLM integration for multi-provider model calls.

Public API:
    - :func:`get_llm` -- create a LangChain chat model for any supported provider.
    - :func:`call_llm` -- invoke the LLM with structured-output support and retry.
"""

from hedge_fund.llm.models import call_llm, get_llm

__all__ = ["call_llm", "get_llm"]
