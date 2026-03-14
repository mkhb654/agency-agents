"""CLI module re-export for the poetry script entry point.

The pyproject.toml defines ``hedge-fund = "hedge_fund.cli:main"``,
so this module simply re-exports ``main`` from ``hedge_fund.main``.
"""

from hedge_fund.main import main

__all__ = ["main"]
