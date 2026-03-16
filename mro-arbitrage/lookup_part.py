"""
lookup_part.py — Universal Part Number Intelligence Lookup

Given a part number, queries ALL available free sources and returns:
- Government pricing (USAspending)
- eBay market pricing
- Demand signals (SDR failure data)
- AD compliance requirements
- PMA alternatives (cheaper aftermarket options)
- NSN cross-reference (military equivalent)

This is the tool you use when Paul says "I have a CFM56-7B fuel nozzle"
or Sophia says "I need part number 2043T72P03".

USAGE:
    python lookup_part.py "CFM56 fuel nozzle"
    python lookup_part.py "2043T72P03"
    python lookup_part.py "landing gear actuator 737"
"""

import json
import sys
import time
import urllib.request
import urllib.parse
import re
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")


def search_usaspending(query, limit=10):
    """Search USAspending for government contracts matching this part."""
    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

    payload = {
        "filters": {
            "time_period": [
                {"start_date": "2020-10-01", "end_date": "2025-09-30"}
            ],
            "award_type_codes": ["A", "B", "C", "D"],
            "naics_codes": {"require": ["336413", "336412"]},
            "keywords": [query],
        },
        "fields": [
            "Award ID", "Recipient Name", "Award Amount",
            "Description", "Start Date", "End Date",
        ],
        "page": 1,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("results", [])
    except Exception as e:
        return [{"error": str(e)}]


def search_ebay(query, limit=10):
    """Search eBay for this part — get market pricing."""
    params = urllib.parse.urlencode({
        "_nkw": f"aircraft {query}",
        "_sacat": "26435",
        "LH_BIN": 1,
        "_sop": 16,
        "_ipg": limit,
    })
    url = f"https://www.ebay.com/sch/i.html?{params}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        prices = []
        for m in re.findall(r'\$([0-9,]+\.\d{2})', html):
            try:
                p = float(m.replace(",", ""))
                if 5 < p < 5_000_000:
                    prices.append(p)
            except ValueError:
                pass

        return {
            "prices": sorted(set(prices)),
            "url": url,
            "count": len(set(prices)),
        }
    except Exception as e:
        return {"prices": [], "error": str(e)}


def search_demand_signals(query):
    """Check our demand signal database for matching components."""
    signals_file = DATA_DIR / "demand_signals.json"
    if not signals_file.exists():
        return []

    with open(signals_file) as f:
        signals = json.load(f)

    query_lower = query.lower()
    matches = []
    for s in signals:
        # Match against component name, engine types, aircraft types
        searchable = json.dumps(s).lower()
        if any(word in searchable for word in query_lower.split()):
            matches.append(s)

    return matches


def search_ad_requirements(query):
    """Check if any active ADs require this part."""
    ad_file = DATA_DIR / "ad_demand_analysis.json"
    if not ad_file.exists():
        return []

    with open(ad_file) as f:
        ad_data = json.load(f)

    query_lower = query.lower()
    matches = []
    for ad in ad_data.get("ads", []):
        searchable = json.dumps(ad).lower()
        if any(word in searchable for word in query_lower.split()):
            matches.append(ad)

    return matches


def search_price_database(query):
    """Check our local price database built from USAspending."""
    db_file = DATA_DIR / "parts_price_database.json"
    if not db_file.exists():
        return []

    with open(db_file) as f:
        db = json.load(f)

    query_lower = query.lower()
    matches = []
    for r in db.get("records", []):
        searchable = (r.get("search_query", "") + " " + r.get("description", "")).lower()
        if any(word in searchable for word in query_lower.split() if len(word) > 2):
            matches.append(r)

    return matches


def search_suppliers(query):
    """Find suppliers for this part from our directory."""
    dir_file = DATA_DIR / "supplier_directory.json"
    if not dir_file.exists():
        return []

    with open(dir_file) as f:
        directory = json.load(f)

    query_lower = query.lower()
    matches = []
    for name, data in directory.items():
        searchable = json.dumps(data).lower() + " " + name.lower()
        if any(word in searchable for word in query_lower.split() if len(word) > 2):
            matches.append({"name": name, **data})

    # Sort by total value descending
    matches.sort(key=lambda x: x.get("total_value", 0), reverse=True)
    return matches


def search_nsn(query):
    """Look up NSN (National Stock Number) for cross-referencing."""
    # Use nsnlookup.com (free public tool)
    params = urllib.parse.urlencode({"q": query})
    url = f"https://www.nsnlookup.com/search?{params}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Extract NSN patterns (4-digit-2-digit-3-digit-4-digit)
        nsns = re.findall(r'(\d{4}-\d{2}-\d{3}-\d{4})', html)
        return {
            "nsns": list(set(nsns))[:10],
            "url": url,
        }
    except Exception as e:
        return {"nsns": [], "error": str(e)}


def search_scorecard(query):
    """Check our arbitrage scorecard for this component."""
    scorecard_file = DATA_DIR / "arbitrage_scorecard.json"
    if not scorecard_file.exists():
        return []

    with open(scorecard_file) as f:
        scorecard = json.load(f)

    query_lower = query.lower()
    matches = []
    for s in scorecard:
        if any(word in s.get("component", "").lower() for word in query_lower.split()):
            matches.append(s)

    return matches


def run_lookup(query):
    """Run full intelligence lookup for a part number or description."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + f"  PART INTELLIGENCE LOOKUP: {query[:40]}".ljust(68) + "║")
    print("║" + f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}".ljust(68) + "║")
    print("╚" + "═" * 68 + "╝")

    # 1. Check our scorecard
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  ARBITRAGE SCORECARD MATCH':^68}│")
    print(f"└{'─' * 68}┘")

    scorecard_matches = search_scorecard(query)
    if scorecard_matches:
        for s in scorecard_matches:
            print(f"  Component: {s['component']}")
            print(f"  Composite Score: {s['composite_score']}/100")
            print(f"  Market Price: ~${s['mid_price']:,}")
            print(f"  Est. Profit/Unit: ${s['estimated_profit_per_unit']:,}")
            print(f"  Best Strategy: {s['best_arbitrage_type'].replace('_', ' ').title()}")
            print(f"  Failure Rate: {s['failure_rate']}")
            print(f"  Aircraft: {', '.join(s.get('aircraft_types', []))}")
    else:
        print("  No scorecard match found. Component may not be in top 15.")

    # 2. Check demand signals
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  DEMAND SIGNAL':^68}│")
    print(f"└{'─' * 68}┘")

    demand_matches = search_demand_signals(query)
    if demand_matches:
        for d in demand_matches:
            print(f"  Component: {d['component']}")
            print(f"  Demand Score: {d['demand_score']}/100")
            print(f"  Failure Rate: {d['failure_rate']}")
            print(f"  Replacement: {d['replacement_frequency']}")
            print(f"  Price Range: {d['estimated_unit_price']}")
            print(f"  Signal: {d['arbitrage_signal']}")
    else:
        print("  No demand signal match. Run broader search terms.")

    # 3. Check AD requirements
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  AIRWORTHINESS DIRECTIVE REQUIREMENTS':^68}│")
    print(f"└{'─' * 68}┘")

    ad_matches = search_ad_requirements(query)
    if ad_matches:
        for ad in ad_matches:
            print(f"  AD {ad['ad_number']}: {ad['title'][:60]}")
            print(f"  Fleet Affected: {ad['fleet_affected']:,}")
            print(f"  Parts Required: {', '.join(ad['parts_required'])}")
            print(f"  Deadline: {ad['compliance_deadline']}")
            print(f"  Market Impact: ${ad['total_market_impact']:,}")
    else:
        print("  No active ADs found requiring this part.")

    # 4. Government pricing
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  GOVERNMENT CONTRACT PRICING (USAspending.gov)':^68}│")
    print(f"└{'─' * 68}┘")

    print(f"  Searching USAspending for '{query}'...", end=" ", flush=True)
    gov_results = search_usaspending(query, limit=5)

    if gov_results and not gov_results[0].get("error"):
        print(f"{len(gov_results)} contracts found")
        for g in gov_results[:5]:
            name = g.get("Recipient Name", "?")
            amount = g.get("Award Amount", 0) or 0
            desc = (g.get("Description") or "")[:60]
            print(f"    ${amount:>13,.0f}  {name[:30]}  {desc}")
    else:
        error = gov_results[0].get("error", "No results") if gov_results else "No results"
        print(f"  {error[:60]}")

    # 5. Local price database (from build_price_db.py)
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  PRICE DATABASE (Government Transactions)':^68}│")
    print(f"└{'─' * 68}┘")

    price_matches = search_price_database(query)
    if price_matches:
        print(f"  {len(price_matches)} matching contracts in database:\n")
        for p in price_matches[:5]:
            amt = p.get("amount", 0)
            recip = p.get("recipient", "?")[:35]
            desc = p.get("description", "")[:50]
            print(f"    ${amt:>13,.0f}  {recip}  {desc}")
    else:
        print("  No matches in local price database. Run build_price_db.py to expand.")

    # 6. Supplier directory
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  KNOWN SUPPLIERS (from government contracts)':^68}│")
    print(f"└{'─' * 68}┘")

    supplier_matches = search_suppliers(query)
    if supplier_matches:
        print(f"  {len(supplier_matches)} suppliers found:\n")
        for s in supplier_matches[:8]:
            val = s.get("total_value", 0)
            parts = ", ".join(s.get("parts", [])[:2])
            print(f"    ${val:>13,.0f}  {s['name'][:40]}")
            if parts:
                print(f"                    Parts: {parts[:50]}")
    else:
        print("  No suppliers found. Run supplier_directory.py to build directory.")

    # 7. eBay market pricing
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  EBAY MARKET PRICING':^68}│")
    print(f"└{'─' * 68}┘")

    print(f"  Searching eBay for '{query}'...", end=" ", flush=True)
    ebay_results = search_ebay(query)

    if ebay_results.get("prices"):
        prices = ebay_results["prices"]
        print(f"{len(prices)} prices found")
        print(f"    Low:    ${min(prices):>12,.2f}")
        print(f"    Median: ${prices[len(prices)//2]:>12,.2f}")
        print(f"    High:   ${max(prices):>12,.2f}")
        print(f"    URL: {ebay_results['url'][:65]}")
    else:
        print(ebay_results.get("error", "No listings found"))

    # 6. NSN cross-reference
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  NSN CROSS-REFERENCE':^68}│")
    print(f"└{'─' * 68}┘")

    print(f"  Looking up NSN for '{query}'...", end=" ", flush=True)
    nsn_results = search_nsn(query)

    if nsn_results.get("nsns"):
        print(f"{len(nsn_results['nsns'])} NSNs found")
        for nsn in nsn_results["nsns"][:5]:
            print(f"    NSN: {nsn}")
        print(f"    Lookup: {nsn_results['url'][:65]}")
    else:
        print(nsn_results.get("error", "No NSNs found"))

    # 7. Action recommendation
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  RECOMMENDATION':^68}│")
    print(f"└{'─' * 68}┘")

    if scorecard_matches:
        s = scorecard_matches[0]
        print(f"  This component ranks #{next((i+1 for i, sc in enumerate(search_scorecard('')) if sc['component'] == s['component']), '?')} in our arbitrage scorecard.")
        print(f"  Strategy: {s['best_arbitrage_type'].replace('_', ' ').title()}")
        print(f"  Expected profit: ${s['estimated_profit_per_unit']:,} per unit")
        print(f"\n  NEXT STEPS:")
        print(f"  1. Call Paul (Bangor) — ask if he has this in teardown inventory")
        print(f"  2. Check StockMarket.aero for current availability")
        print(f"  3. Get 5 IATA SmartHub FMV lookups to validate pricing")
        print(f"  4. Quote to Sophia/Gary at 15-20% markup")
    elif demand_matches:
        d = demand_matches[0]
        print(f"  Demand score: {d['demand_score']}/100 — {'HIGH' if d['demand_score'] >= 80 else 'MODERATE'} demand")
        print(f"  Failure rate: {d['failure_rate']}")
        print(f"  This part has strong replacement demand. Worth sourcing.")
    elif ad_matches:
        ad = ad_matches[0]
        print(f"  AD-DRIVEN DEMAND: {ad['fleet_affected']:,} aircraft need this part")
        print(f"  Market impact: ${ad['total_market_impact']:,}")
        print(f"  Deadline: {ad['compliance_deadline']}")
        print(f"  ACTION: Source this part NOW before deadline drives prices up")
    else:
        print(f"  No strong signals found for '{query}'.")
        print(f"  Try broader terms or check specific part numbers on:")
        print(f"  - StockMarket.aero (free)")
        print(f"  - IATA MRO SmartHub (5 free lookups/day)")
        print(f"  - PartsBase PartStore (free browsing)")

    print(f"\n{'═' * 70}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("Enter part number or description: ").strip()

    if not query:
        print("Usage: python lookup_part.py 'CFM56 fuel nozzle'")
        sys.exit(1)

    run_lookup(query)
