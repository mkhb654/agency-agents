"""
dashboard.py — Master MRO Arbitrage Intelligence Dashboard

Combines all data sources into a single actionable view:
1. USAspending government contract pricing
2. SDR demand signals (component failure rates)
3. eBay market pricing validation
4. Fleet composition from FAA Registry
5. Arbitrage scoring

USAGE:
    python dashboard.py
"""

import json
import os
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")


def load_all_data():
    """Load all available data files."""
    data = {}

    files = {
        "awards": "usaspending_aviation_awards.json",
        "demand_signals": "demand_signals.json",
        "scorecard": "arbitrage_scorecard.json",
        "ebay_prices": "ebay_price_validation.json",
        "fleet_summary": "faa_fleet_summary.csv",
        "arbitrage_opps": "arbitrage_opportunities.json",
        "ad_demand": "ad_demand_analysis.json",
        "competitive_intel": "competitive_intelligence.json",
        "trade_flows": "trade_flow_analysis.json",
        "pma_landscape": "pma_landscape_research.json",
        "usitc_trade": "usitc_trade_data_analysis.json",
        "engine_research": "engine_maintenance_research.json",
        "storage_sources": "aircraft_storage_sources.json",
    }

    for key, filename in files.items():
        filepath = DATA_DIR / filename
        if filepath.exists():
            if filename.endswith(".json"):
                with open(filepath) as f:
                    data[key] = json.load(f)
            elif filename.endswith(".csv"):
                with open(filepath) as f:
                    data[key] = f.read()
            print(f"  Loaded {key}: {filepath}")
        else:
            print(f"  Missing {key}: {filepath}")
            data[key] = None

    return data


def render_dashboard(data):
    """Render the complete arbitrage intelligence dashboard."""

    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + "  MRO PARTS ARBITRAGE INTELLIGENCE DASHBOARD".center(68) + "║")
    print("║" + f"  {datetime.now().strftime('%Y-%m-%d %H:%M')} | Powered by FREE government data".center(68) + "║")
    print("╚" + "═" * 68 + "╝")

    # ---- Section 1: Data Sources Status ----
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  DATA SOURCES STATUS':^68}│")
    print(f"└{'─' * 68}┘")

    sources = [
        ("USAspending.gov", data.get("awards"), "Contract awards with pricing"),
        ("FAA SDR Analysis", data.get("demand_signals"), "Component failure/demand signals"),
        ("Arbitrage Scorecard", data.get("scorecard"), "Ranked opportunities"),
        ("eBay Price Validation", data.get("ebay_prices"), "Market price benchmarks"),
        ("FAA Fleet Data", data.get("fleet_summary"), "Aircraft registry analysis"),
    ]

    for name, loaded, desc in sources:
        status = "LOADED" if loaded else "MISSING"
        icon = "●" if loaded else "○"
        count = ""
        if loaded:
            if isinstance(loaded, list):
                count = f" ({len(loaded)} records)"
            elif isinstance(loaded, str):
                count = f" ({len(loaded.splitlines())} lines)"
        print(f"  {icon} {name:<30} {status:<8} {desc}{count}")

    # ---- Section 2: Top Arbitrage Opportunities ----
    scorecard = data.get("scorecard", [])
    if scorecard:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  TOP ARBITRAGE OPPORTUNITIES (by Composite Score)':^68}│")
        print(f"└{'─' * 68}┘")

        print(f"\n  {'#':>2}  {'Score':>5}  {'Component':<28}  {'Price':>9}  {'Profit':>9}  Strategy")
        print(f"  {'─'*2}  {'─'*5}  {'─'*28}  {'─'*9}  {'─'*9}  {'─'*18}")

        for i, s in enumerate(scorecard[:10], 1):
            strategy = s["best_arbitrage_type"].replace("_", " ").title()[:18]
            print(
                f"  {i:>2}  "
                f"{s['composite_score']:>5.1f}  "
                f"{s['component'][:28]:<28}  "
                f"${s['mid_price']:>8,}  "
                f"${s['estimated_profit_per_unit']:>8,}  "
                f"{strategy}"
            )

    # ---- Section 3: Government Contract Intelligence ----
    awards = data.get("awards", [])
    if awards:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  GOVERNMENT CONTRACT INTELLIGENCE':^68}│")
        print(f"└{'─' * 68}┘")

        # Top suppliers (excluding mega-primes)
        recipients = {}
        for a in awards:
            name = a.get("Recipient Name", "Unknown")
            amount = a.get("Award Amount", 0) or 0
            if name not in recipients:
                recipients[name] = {"total": 0, "count": 0}
            recipients[name]["total"] += amount
            recipients[name]["count"] += 1

        # Mid-tier suppliers ($10M - $500M) — your potential sourcing partners
        mid_tier = [(n, d) for n, d in recipients.items()
                    if 10_000_000 <= d["total"] <= 500_000_000]
        mid_tier.sort(key=lambda x: x[1]["total"], reverse=True)

        print(f"\n  Potential Sourcing Partners (mid-tier gov contractors):\n")
        for name, d in mid_tier[:10]:
            print(f"    ${d['total']:>13,.0f}  {name}")

        total_value = sum(a.get("Award Amount", 0) or 0 for a in awards)
        print(f"\n  Total aviation contract value tracked: ${total_value:,.0f}")
        print(f"  Total contractors: {len(recipients)}")
        print(f"  Mid-tier sourcing targets: {len(mid_tier)}")

    # ---- Section 4: Demand Signal Heatmap ----
    signals = data.get("demand_signals", [])
    if signals:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  PARTS DEMAND HEATMAP':^68}│")
        print(f"└{'─' * 68}┘\n")

        for s in signals[:10]:
            bar_len = s["demand_score"] // 5
            bar = "█" * bar_len + "░" * (20 - bar_len)
            aircraft = ", ".join(s.get("aircraft_types", [])[:3])
            print(f"  {bar} {s['demand_score']:>3}  {s['component']:<28} [{aircraft}]")

    # ---- Section 5: Market Price Intelligence ----
    ebay = data.get("ebay_prices", [])
    if ebay:
        validated = [e for e in ebay if e.get("median_price", 0) > 0]
        if validated:
            print(f"\n┌{'─' * 68}┐")
            print(f"│{'  MARKET PRICE INTELLIGENCE (eBay Validated)':^68}│")
            print(f"└{'─' * 68}┘")

            print(f"\n  {'Component':<25}  {'eBay Low':>10}  {'eBay Med':>10}  {'eBay High':>10}  {'Spread':>8}")
            print(f"  {'─'*25}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*8}")

            for e in validated:
                low = e.get("low_price", 0)
                med = e.get("median_price", 0)
                high = e.get("high_price", 0)
                spread = ((high - low) / low * 100) if low > 0 else 0
                print(
                    f"  {e.get('component', '?')[:25]:<25}  "
                    f"${low:>9,.0f}  "
                    f"${med:>9,.0f}  "
                    f"${high:>9,.0f}  "
                    f"{spread:>7,.0f}%"
                )

            print(f"\n  Key insight: eBay price ranges show massive spreads between")
            print(f"  uncertified/scrap parts and serviceable parts with 8130-3 tags.")
            print(f"  The CERTIFICATION is where the value is — same physical part,")
            print(f"  10-100x price difference based on paperwork.")

    # ---- Section 6: AD Demand Spikes ----
    ad_data = data.get("ad_demand")
    if ad_data and "ads" in ad_data:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  AIRWORTHINESS DIRECTIVE DEMAND SPIKES':^68}│")
        print(f"└{'─' * 68}┘")

        total_impact = ad_data.get("total_market_impact", 0)
        print(f"\n  Total AD-driven parts demand: ${total_impact:,.0f}\n")

        print(f"  {'AD Number':<16} {'Fleet':>6}  {'$/Unit':>10}  {'Total':>14}  Status")
        print(f"  {'─'*16} {'─'*6}  {'─'*10}  {'─'*14}  {'─'*8}")

        for ad in sorted(ad_data["ads"], key=lambda x: x["total_market_impact"], reverse=True):
            print(
                f"  {ad['ad_number']:<16} "
                f"{ad['fleet_affected']:>6}  "
                f"${ad['estimated_part_cost_per_unit']:>9,}  "
                f"${ad['total_market_impact']:>13,}  "
                f"{ad['status']}"
            )

        # Top parts needed
        parts = ad_data.get("parts_demand", {})
        if parts:
            top_parts = sorted(parts.items(), key=lambda x: x[1]["total_demand"], reverse=True)[:5]
            print(f"\n  Highest-demand parts from active ADs:")
            for part, info in top_parts:
                print(f"    {info['total_demand']:>6,} units needed: {part}")

    # ---- Section 7: PMA Arbitrage ----
    pma = data.get("pma_landscape")
    if pma and isinstance(pma, dict):
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  PMA DISRUPTION MAP':^68}│")
        print(f"└{'─' * 68}┘")

        mo = pma.get("market_overview", {})
        if isinstance(mo, dict):
            size = mo.get("global_pma_market_size_2024", "?")
            approvals = mo.get("us_pma_approvals_2023", "?")
            fleet = mo.get("aircraft_using_pma_parts_2023", "?")
            print(f"\n  PMA Market: {size} | US Approvals (2023): {approvals} | Fleet: {fleet}")

        opps = pma.get("actionable_arbitrage_opportunities", {})
        if isinstance(opps, dict):
            for key, opp in list(opps.items())[:3]:
                if isinstance(opp, dict):
                    desc = opp.get("description", key)
                    action = opp.get("action", "")
                    savings = opp.get("savings", "")
                    print(f"\n  {desc}")
                    if savings:
                        print(f"    Savings: {savings}")
                    if action:
                        print(f"    Action: {action[:70]}")

    # ---- Section 8: Geographic Arbitrage ----
    trade = data.get("trade_flows")
    if trade and isinstance(trade, dict):
        corridors = trade.get("arbitrage_corridors", [])
        if corridors:
            print(f"\n┌{'─' * 68}┐")
            print(f"│{'  GEOGRAPHIC ARBITRAGE CORRIDORS':^68}│")
            print(f"└{'─' * 68}┘\n")

            for c in corridors[:4]:
                margin = c.get("margin", "?")
                volume = c.get("volume", "?")
                print(f"  {c['corridor']:<40} Margin: {margin:<10} Vol: {volume}")

    # ---- Section 9: Competitive Intelligence ----
    comp = data.get("competitive_intel")
    if comp and isinstance(comp, dict):
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  PRICING STACK (Your Arbitrage Band)':^68}│")
        print(f"└{'─' * 68}┘")
        print(f"""
  CEILING: TransDigm sole-source (50-60% EBITDA) ← overpriced, target these
  ═══════════════════════════════════════════════
  YOUR BAND: Buy PMA/USM, sell below OEM (20-40% margin)
  ═══════════════════════════════════════════════
  FLOOR: HEICO PMA pricing (26% EBITDA, 30-60% below OEM)
  ───────────────────────────────────────────────
  SCRAP: Uncertified parts (eBay $15 turbine blades)""")

    # ---- Section 10: Action Items ----
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  IMMEDIATE ACTION ITEMS':^68}│")
    print(f"└{'─' * 68}┘")

    actions = [
        "1. CALL PAUL (Bangor) — Ask about APU and turbine blade inventory",
        "   He tears down aircraft. APUs = $150K profit/unit via overhaul.",
        "",
        "2. VISIT SOPHIA (Miami) — Get her top 10 hard-to-find parts list",
        "   Cross-reference with our demand scorecard. Source from Paul.",
        "",
        "3. REGISTER on StockMarket.aero (FREE) — See real-time availability",
        "   World's largest free aviation parts marketplace since 2006.",
        "",
        "4. REGISTER on IATA MRO SmartHub (FREE tier) — Validate FMVs",
        "   5 free part searches/day. Use to validate our pricing estimates.",
        "",
        "5. PULL USAspending data for SPECIFIC part numbers",
        "   Once Paul/Sophia give you part numbers, search government prices.",
        "",
        "6. SET UP eBay Browse API (free developer account)",
        "   Automated price monitoring for the top 15 components.",
    ]

    for action in actions:
        print(f"  {action}")

    # ---- Section 7: Revenue Projections ----
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  REVENUE PROJECTIONS (Conservative)':^68}│")
    print(f"└{'─' * 68}┘")

    projections = [
        ("Month 1-3", "Parts sourcing agent", "3-5 deals", "$5K-$25K margin", "$15K-$75K"),
        ("Month 3-6", "Scaled sourcing + AOG", "10-15 deals", "$5K-$50K margin", "$50K-$250K"),
        ("Month 6-12", "Platform + intelligence", "20+ deals", "$5K-$150K margin", "$200K-$500K"),
        ("Year 2", "Subscription + advisory", "5-10 clients", "$150K-$300K/yr each", "$750K-$3M ARR"),
    ]

    print(f"\n  {'Period':<15}  {'Model':<25}  {'Volume':<12}  {'Per Deal':<18}  Total")
    print(f"  {'─'*15}  {'─'*25}  {'─'*12}  {'─'*18}  {'─'*18}")
    for period, model, volume, margin, total in projections:
        print(f"  {period:<15}  {model:<25}  {volume:<12}  {margin:<18}  {total}")

    # ---- Footer ----
    print(f"\n{'═' * 70}")
    print(f"  Data sources: USAspending.gov | FAA Registry | FAA SDRs | eBay")
    print(f"  All data is FREE and publicly available")
    print(f"  Next update: Run 'python dashboard.py' to refresh")
    print(f"{'═' * 70}")


def save_report(data):
    """Save dashboard as text report."""
    import io
    import sys

    # Capture output
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    render_dashboard(data)
    sys.stdout = old_stdout

    report = buffer.getvalue()

    report_file = DATA_DIR / "dashboard_report.txt"
    with open(report_file, "w") as f:
        f.write(report)

    # Also print to screen
    print(report)
    print(f"\n  Report saved to {report_file}")


if __name__ == "__main__":
    print("  Loading data sources...")
    data = load_all_data()
    save_report(data)
