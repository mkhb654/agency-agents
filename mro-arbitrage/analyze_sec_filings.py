"""
analyze_sec_filings.py — Extract pricing intelligence from public company filings

TransDigm (TDG), HEICO (HEI), AerSale (ASLE), FTAI Aviation, AAR Corp
are publicly traded. Their filings reveal the exact pricing dynamics
of the aviation parts aftermarket.

Key intelligence:
- TransDigm's sole-source margins (50-60% EBITDA) = price ceiling you can undercut
- HEICO's PMA margins (26% EBITDA) = the floor for aftermarket alternatives
- AerSale's feedstock disclosures = what's being torn down
- FTAI's module factory = CFM56 arbitrage at industrial scale

USAGE:
    python analyze_sec_filings.py
"""

import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")


def build_competitive_intelligence():
    """Build competitive intelligence from public company data."""

    print("=" * 70)
    print("  COMPETITIVE INTELLIGENCE: Public Aviation Parts Companies")
    print("  Source: SEC filings, earnings calls, analyst reports")
    print("=" * 70)

    companies = {
        "TransDigm Group (TDG)": {
            "market_cap": "$77B+ (Mar 2026)",
            "revenue": "$7.9B (FY2025)",
            "aftermarket_revenue": "~55% of total (~$4.3B)",
            "ebitda_margin": "~53% aftermarket segment",
            "strategy": "Acquire sole-source aerospace parts companies, raise prices",
            "pricing_power": "Proprietary/sole-source parts with NO competition = 30-100% price increases",
            "key_insight": "TransDigm parts are the MOST OVERPRICED in aviation. Any part they sell is a PMA arbitrage target.",
            "arbitrage_signal": "If TransDigm sells a part, there's 50%+ margin being captured. Find or create a PMA alternative and undercut by 20-30% while still making 20-30% yourself.",
            "top_subsidiaries": [
                "Dukes Aerospace (fuel system components)",
                "Kirkhill (elastomeric seals, gaskets)",
                "Whippany Actuation (actuation systems)",
                "Hartwell (latches, locks, fittings)",
                "Marathon Norco (valves, regulators)",
                "AvtechTyee (connectors, harnesses)",
            ],
        },
        "HEICO Corporation (HEI)": {
            "market_cap": "$32B+ (Mar 2026)",
            "revenue": "$4.0B (FY2025)",
            "fsg_revenue": "~$2.2B (Flight Support Group)",
            "fsg_ebitda_margin": "~26%",
            "pma_parts_count": "19,000+ approved PMAs",
            "new_pma_per_year": "~500 new approvals annually",
            "pma_discount": "30-60% below OEM pricing",
            "strategy": "Create FAA-approved alternatives to expensive OEM parts",
            "key_insight": "HEICO is your PRICING BENCHMARK for aftermarket parts. Their prices represent the competitive floor.",
            "arbitrage_signal": "When HEICO enters a new PMA category, the OEM price for that part drops 10-30% within 12-24 months. Monitor new PMA filings as leading indicator.",
            "top_subsidiaries": [
                "Jet Avion (engine parts PMA)",
                "Helicoil (fasteners)",
                "Reinhold Industries (composites)",
                "Santa Barbara Infrared (sensors)",
                "Sierra Microwave Technology (electronics)",
            ],
        },
        "AerSale Inc (ASLE)": {
            "market_cap": "~$500M (Mar 2026)",
            "revenue": "$348M (FY2024)",
            "feedstock_investment": "$100M invested in aircraft feedstock (2025)",
            "win_rate": "1 in 10 bids for teardown feedstock",
            "strategy": "Buy whole aircraft, tear down, sell USM parts + engines",
            "key_insight": "AerSale's win rate (10%) shows how competitive the feedstock market is. Prices for whole aircraft being parted out are HIGH relative to parts-out value.",
            "arbitrage_signal": "AerSale's quarterly feedstock disclosures reveal which aircraft types are being acquired for teardown. This signals which parts will enter the USM market in 3-6 months.",
            "location": "Coral Gables, FL (your backyard)",
        },
        "FTAI Aviation (FTAI)": {
            "market_cap": "$16B+ (Mar 2026)",
            "revenue": "$2.1B (FY2025 estimate)",
            "engine_fleet": "1,000+ engines (primarily CFM56)",
            "module_factory_target": "1,000 modules in 2026",
            "aar_exclusive": "Exclusive CFM56 USM deal with AAR through 2030",
            "pma_jv": "Joint venture with Chromalloy for PMA engine parts",
            "margins": "35% current, targeting 50%+",
            "strategy": "Vertically integrated CFM56 empire: acquire engines, modularize, PMA parts, sell USM",
            "key_insight": "FTAI is doing at INDUSTRIAL SCALE what you're doing at deal level. Their earnings calls describe the exact CFM56 arbitrage playbook.",
            "arbitrage_signal": "FTAI's module approach (swap modules instead of full overhaul) is disrupting MRO pricing. MROs that can't match this speed lose customers = they need YOUR help sourcing modules.",
        },
        "AAR Corp (AIR)": {
            "market_cap": "~$3B (Mar 2026)",
            "revenue": "$2.6B (FY2025)",
            "distribution_segment": "Parts supply chain — $1.4B+ revenue",
            "government_pct": "~30% of revenue from US government",
            "strategy": "Parts distribution + MRO services + government contracts",
            "key_insight": "AAR is the largest independent MRO/distribution company. Their pricing on the distribution side IS the market benchmark for parts.",
            "arbitrage_signal": "AAR's exclusive deal with FTAI for CFM56 USM means they control a huge chunk of CFM56 parts flow. If you're sourcing CFM56 parts, you're eventually competing with AAR or buying from them.",
        },
    }

    for name, data in companies.items():
        print(f"\n┌{'─' * 68}┐")
        print(f"│  {name:^66}│")
        print(f"└{'─' * 68}┘")
        for key, value in data.items():
            if isinstance(value, list):
                print(f"  {key}:")
                for item in value:
                    print(f"    • {item}")
            else:
                label = key.replace("_", " ").title()
                print(f"  {label}: {value}")

    # Save competitive intelligence
    output_file = DATA_DIR / "competitive_intelligence.json"
    with open(output_file, "w") as f:
        json.dump(companies, f, indent=2, default=str)

    # Generate the pricing insight
    print(f"\n{'=' * 70}")
    print(f"  THE PRICING STACK (Where Your Arbitrage Lives)")
    print(f"{'=' * 70}")
    print(f"""
  Price ceiling: TransDigm sole-source parts (50-60% EBITDA margin)
  ─────────────────────────────────────────────────────────────────
  │  THIS IS WHERE YOU MAKE MONEY                                │
  │  Buy at HEICO/PMA prices, sell below TransDigm prices        │
  │  Or buy USM from teardowns, sell below OEM new                │
  │  20-40% margin in this band                                  │
  ─────────────────────────────────────────────────────────────────
  Price floor: HEICO PMA parts (26% EBITDA margin, 30-60% below OEM)
  ─────────────────────────────────────────────────────────────────
  Below floor: Scrap/uncertified parts (eBay $15 turbine blades)

  The wider the band between TransDigm's ceiling and HEICO's floor,
  the bigger your arbitrage opportunity for that specific part.

  TransDigm's sole-source subsidiaries tell you WHICH parts have
  the fattest margins. Those are your #1 PMA/USM targets.
    """)

    print(f"  Saved to {output_file}")
    return companies


if __name__ == "__main__":
    build_competitive_intelligence()
