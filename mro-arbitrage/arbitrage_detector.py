"""
arbitrage_detector.py — Find aviation parts arbitrage opportunities

Combines data from multiple free sources to identify where parts can be
sourced cheap and sold at market premium.

Arbitrage signals:
1. Government price vs market price gap (USAspending vs eBay/market)
2. High failure rate + low supply = price spike opportunity (SDR + Registry)
3. AD compliance deadline approaching = guaranteed demand spike
4. Fleet aging = increasing parts demand over time
5. PMA alternative exists but market hasn't adopted = price gap

USAGE:
    python arbitrage_detector.py
"""

import json
import os
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")


def load_usaspending_data():
    """Load government contract awards."""
    filepath = DATA_DIR / "usaspending_aviation_awards.json"
    if not filepath.exists():
        print("No USAspending data found. Run ingest_usaspending.py first.")
        return []

    with open(filepath) as f:
        awards = json.load(f)

    print(f"Loaded {len(awards)} USAspending awards")
    return awards


def load_fleet_data():
    """Load FAA fleet summary."""
    filepath = DATA_DIR / "faa_fleet_summary.csv"
    if not filepath.exists():
        print("No fleet data found. Run ingest_faa_registry.py first.")
        return {}

    fleet = {}
    with open(filepath) as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 4:
                model = parts[0].strip('"')
                count = int(parts[2]) if parts[2].isdigit() else 0
                avg_age = float(parts[3]) if parts[3] else 0
                fleet[model] = {"count": count, "avg_age": avg_age}

    print(f"Loaded fleet data for {len(fleet)} aircraft models")
    return fleet


def analyze_government_spending(awards):
    """Analyze government spending patterns for arbitrage signals."""
    print(f"\n{'=' * 70}")
    print(f"  ARBITRAGE SIGNAL 1: Government Spending Patterns")
    print(f"{'=' * 70}")

    if not awards:
        print("  No awards data to analyze.")
        return []

    opportunities = []

    # Group by recipient to find which companies dominate
    recipients = {}
    for a in awards:
        name = a.get("Recipient Name", "Unknown")
        amount = a.get("Award Amount", 0) or 0
        desc = a.get("Description", "")
        if name not in recipients:
            recipients[name] = {"total": 0, "count": 0, "descriptions": []}
        recipients[name]["total"] += amount
        recipients[name]["count"] += 1
        if desc:
            recipients[name]["descriptions"].append(desc[:200])

    # Find mid-tier suppliers (not Boeing/Lockheed — they're OEMs, not arbitrage targets)
    # Look for smaller companies doing parts/component work
    sorted_recipients = sorted(recipients.items(), key=lambda x: x[1]["total"])

    print("\n  Mid-tier aviation parts suppliers (arbitrage targets):")
    print("  These companies supply parts to the government — they're potential")
    print("  sourcing partners for your MRO parts brokerage.\n")

    mid_tier = []
    for name, data in sorted_recipients:
        # Filter: $1M-$500M range, not the mega-primes
        if 1_000_000 <= data["total"] <= 500_000_000:
            mid_tier.append((name, data))

    for name, data in mid_tier[:20]:
        print(f"    ${data['total']:>15,.0f}  ({data['count']} contracts)  {name}")
        # Show what they supply
        for desc in data["descriptions"][:2]:
            print(f"      → {desc[:100]}")

        opportunities.append({
            "type": "supplier_discovery",
            "company": name,
            "government_spend": data["total"],
            "contract_count": data["count"],
            "signal": "Mid-tier government supplier = potential sourcing partner",
        })

    return opportunities


def analyze_fleet_aging(fleet):
    """Identify aircraft types with aging fleets = increasing parts demand."""
    print(f"\n{'=' * 70}")
    print(f"  ARBITRAGE SIGNAL 2: Aging Fleet = Growing Parts Demand")
    print(f"{'=' * 70}")

    if not fleet:
        print("  No fleet data to analyze.")
        return []

    opportunities = []

    # Find models with large fleets AND high average age
    aging_fleet = []
    for model, data in fleet.items():
        if data["count"] >= 50 and data["avg_age"] >= 20:
            aging_fleet.append((model, data))

    aging_fleet.sort(key=lambda x: x[1]["count"] * x[1]["avg_age"], reverse=True)

    print("\n  Aircraft with large, aging fleets (HIGH parts demand):\n")
    print(f"  {'Model':<40} {'Count':>8} {'Avg Age':>8}  Signal")
    print(f"  {'-'*40} {'-'*8} {'-'*8}  {'-'*30}")

    for model, data in aging_fleet[:25]:
        signal = ""
        if data["avg_age"] >= 30 and data["count"] >= 200:
            signal = "PRIME TARGET — large fleet, very old"
        elif data["avg_age"] >= 25 and data["count"] >= 100:
            signal = "HIGH DEMAND — aging fleet"
        elif data["avg_age"] >= 20:
            signal = "Growing demand"

        print(f"  {model:<40} {data['count']:>8,} {data['avg_age']:>7.1f}y  {signal}")

        if data["avg_age"] >= 25 and data["count"] >= 100:
            opportunities.append({
                "type": "aging_fleet",
                "model": model,
                "fleet_size": data["count"],
                "avg_age": data["avg_age"],
                "signal": f"Fleet of {data['count']} aircraft averaging {data['avg_age']:.0f} years old",
                "opportunity": "Parts demand increasing as fleet ages. Source common replacement parts.",
            })

    return opportunities


def analyze_market_structure():
    """Identify structural arbitrage opportunities in aviation parts market."""
    print(f"\n{'=' * 70}")
    print(f"  ARBITRAGE SIGNAL 3: Market Structure Opportunities")
    print(f"{'=' * 70}")

    opportunities = []

    # Known structural arbitrage patterns in aviation parts
    structural_opps = [
        {
            "type": "pma_arbitrage",
            "signal": "PMA parts are 30-60% cheaper than OEM",
            "description": (
                "FAA-approved PMA (Parts Manufacturer Approval) alternatives exist for many "
                "high-volume OEM parts. MROs often default to OEM parts out of habit or "
                "ignorance of PMA alternatives. Identifying parts where PMA exists but "
                "market hasn't adopted = instant arbitrage."
            ),
            "data_source": "FAA PMA Database (drs.faa.gov) + FlyPMA.com for cross-reference",
            "action": "Search PMA database for alternatives to high-demand OEM parts. "
                      "Source PMA parts at 30-60% discount. Sell to MROs at 10-20% below OEM price.",
            "margin": "20-40% gross margin",
        },
        {
            "type": "aog_premium",
            "signal": "AOG (Aircraft On Ground) parts command 2-5x premium",
            "description": (
                "When an aircraft is grounded waiting for a part, operators pay massive "
                "premiums for speed. A $5K part becomes $15K-$25K if delivered in 24 hours "
                "vs 2 weeks. The premium is for SPEED, not the part itself."
            ),
            "data_source": "SDR failure rates identify common AOG-causing parts",
            "action": "Stock the top 50 parts that cause AOG events. Sell at 2-5x with "
                      "guaranteed 24-48 hour delivery via EasyFlyers logistics.",
            "margin": "100-400% gross margin on AOG sales",
        },
        {
            "type": "ad_compliance",
            "signal": "Airworthiness Directives create mandatory demand with deadlines",
            "description": (
                "When the FAA issues an AD, operators MUST replace specific parts by a "
                "deadline. This creates predictable demand spikes. Parts needed for AD "
                "compliance often go into shortage, driving prices up."
            ),
            "data_source": "FAA AD database (drs.faa.gov) + Aircraft Registry for affected fleet size",
            "action": "Monitor new ADs. Cross-reference with fleet size. Source required "
                      "parts BEFORE demand spike. Sell at market rate as deadline approaches.",
            "margin": "15-50% depending on timing",
        },
        {
            "type": "teardown_spread",
            "signal": "Parted-out aircraft worth 2-4x whole aircraft value",
            "description": (
                "A grounded 737-800 might sell whole for $2M. But its CFM56-7B engines "
                "alone are worth $4-5M each. Landing gear, avionics, and 600+ components "
                "add another $2-5M. Total parts value: $10-15M vs $2M whole."
            ),
            "data_source": "Registry (identify grounded aircraft) + USAspending (component values)",
            "action": "Identify grounded aircraft via FlightAware/Registry. Calculate "
                      "component-level value. Connect teardown operators (Paul) with buyers.",
            "margin": "Intelligence fee: 5-10% of deal spread",
        },
        {
            "type": "geographic_arbitrage",
            "signal": "Same part: different prices in different markets",
            "description": (
                "A CFM56 engine in the US might trade at $4.5M. The same engine in "
                "Southeast Asia might trade at $3.8M due to local oversupply. Different "
                "markets have different supply/demand dynamics."
            ),
            "data_source": "eBay (US prices) + IATA SmartHub (global prices)",
            "action": "Monitor regional price differences. Buy where cheap, sell where "
                      "expensive. Use EasyFlyers' 20+ country logistics network.",
            "margin": "10-25% on geographic spread",
        },
        {
            "type": "condition_arbitrage",
            "signal": "Overhauled parts sell at 60-80% of new, but cost 20-30% to overhaul",
            "description": (
                "A new landing gear actuator: $50K. Used serviceable: $15K. Cost to "
                "overhaul the used one: $8K. Overhauled price: $35K. Buy used at $15K, "
                "overhaul for $8K ($23K total), sell overhauled at $35K. $12K profit."
            ),
            "data_source": "eBay (used prices) + MRO shop rates (from your contacts)",
            "action": "Source used serviceable parts cheap. Get them overhauled by MRO "
                      "partners (Sophia, Gary). Sell as overhauled at premium.",
            "margin": "30-50% after overhaul cost",
        },
    ]

    for i, opp in enumerate(structural_opps, 1):
        print(f"\n  Opportunity {i}: {opp['signal']}")
        print(f"  {'─' * 60}")
        print(f"  {opp['description']}")
        print(f"  Data: {opp['data_source']}")
        print(f"  Action: {opp['action']}")
        print(f"  Expected margin: {opp['margin']}")
        opportunities.append(opp)

    return opportunities


def generate_report(all_opportunities):
    """Generate the arbitrage opportunities report."""
    report_file = DATA_DIR / "arbitrage_opportunities.json"
    with open(report_file, "w") as f:
        json.dump(all_opportunities, f, indent=2, default=str)

    summary_file = DATA_DIR / "arbitrage_report.txt"
    with open(summary_file, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("  AVIATION MRO PARTS ARBITRAGE OPPORTUNITIES REPORT\n")
        f.write(f"  Generated: {datetime.now().isoformat()}\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total opportunities identified: {len(all_opportunities)}\n\n")

        by_type = {}
        for opp in all_opportunities:
            t = opp["type"]
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(opp)

        for t, opps in by_type.items():
            f.write(f"\n--- {t.upper().replace('_', ' ')} ({len(opps)} opportunities) ---\n\n")
            for opp in opps[:10]:
                for k, v in opp.items():
                    if k != "type":
                        f.write(f"  {k}: {v}\n")
                f.write("\n")

    print(f"\n{'=' * 70}")
    print(f"  REPORT GENERATED")
    print(f"{'=' * 70}")
    print(f"  Total opportunities: {len(all_opportunities)}")
    print(f"  JSON: {report_file}")
    print(f"  Text: {summary_file}")
    print(f"{'=' * 70}")


def main():
    print("=" * 70)
    print("  AVIATION MRO PARTS ARBITRAGE DETECTOR")
    print("  Powered by FREE government data sources")
    print("=" * 70)

    all_opportunities = []

    # Signal 1: Government spending patterns
    awards = load_usaspending_data()
    opps1 = analyze_government_spending(awards)
    all_opportunities.extend(opps1)

    # Signal 2: Aging fleet analysis
    fleet = load_fleet_data()
    opps2 = analyze_fleet_aging(fleet)
    all_opportunities.extend(opps2)

    # Signal 3: Structural market opportunities
    opps3 = analyze_market_structure()
    all_opportunities.extend(opps3)

    # Generate report
    generate_report(all_opportunities)


if __name__ == "__main__":
    main()
