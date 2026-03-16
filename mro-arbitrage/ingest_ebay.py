"""
ingest_ebay.py — Scrape eBay aviation parts for REAL market transaction prices

eBay is the single best public source of actual aviation parts pricing:
- Active listings show current asking prices
- Sold/completed listings show ACTUAL transaction prices
- 50,000-100,000+ aviation parts listed at any time

We search for the high-demand components identified in our scorecard
to validate pricing estimates and find arbitrage gaps.

NOTE: For production use, switch to the eBay Browse API (free developer program).
This script uses web search as a quick validation approach.

USAGE:
    python ingest_ebay.py
"""

import json
import time
import urllib.request
import urllib.parse
import re
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")

# Components to validate pricing for (from our scorecard)
SEARCH_QUERIES = [
    {"query": "CFM56 turbine blade", "component": "Turbine Blades (HPT/LPT)", "category": "26439"},
    {"query": "aircraft APU Honeywell 131", "component": "APU", "category": "26435"},
    {"query": "CFM56 combustion liner", "component": "Combustion Liners", "category": "26439"},
    {"query": "aircraft fuel nozzle CFM56", "component": "Fuel Nozzles", "category": "26439"},
    {"query": "aircraft landing gear actuator", "component": "Landing Gear Actuators", "category": "26435"},
    {"query": "aircraft brake assembly Boeing", "component": "Brake Assemblies", "category": "26435"},
    {"query": "aircraft hydraulic pump Boeing", "component": "Hydraulic Pumps", "category": "26435"},
    {"query": "aircraft IDG generator integrated drive", "component": "Generators / IDGs", "category": "26435"},
    {"query": "aircraft FMS flight management system", "component": "FMS Units", "category": "26435"},
    {"query": "aircraft servo actuator flight control", "component": "Servo Actuators", "category": "26435"},
    {"query": "aircraft tire Goodyear Michelin", "component": "Tires", "category": "26435"},
    {"query": "aircraft pack valve air conditioning", "component": "Pack Valves / ACMs", "category": "26435"},
    {"query": "aircraft bleed air valve", "component": "Bleed Air Valves", "category": "26435"},
    {"query": "aircraft VHF transceiver Collins Rockwell", "component": "VHF Transceivers", "category": "26435"},
]


def search_ebay_prices(query, category="26435"):
    """
    Search eBay for aviation parts pricing using their web search.
    Returns parsed listing data.
    """
    # Build eBay search URL
    params = urllib.parse.urlencode({
        "_nkw": query,
        "_sacat": category,  # Aviation Parts & Accessories
        "_sop": 16,  # Sort by price + shipping: highest first
        "LH_BIN": 1,  # Buy It Now only (fixed prices, not auctions)
        "_ipg": 25,  # 25 results per page
    })
    url = f"https://www.ebay.com/sch/i.html?{params}"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Parse prices from the HTML
        prices = []
        # eBay uses data attributes and specific patterns for prices
        price_patterns = [
            r'\$([0-9,]+\.\d{2})',  # $1,234.56 format
            r'"price":"([0-9.]+)"',  # JSON price fields
        ]

        for pattern in price_patterns:
            matches = re.findall(pattern, html)
            for m in matches:
                try:
                    price = float(m.replace(",", ""))
                    if 10 < price < 5_000_000:  # Filter noise
                        prices.append(price)
                except ValueError:
                    continue

        # Count total results
        result_count_match = re.search(r'(\d[\d,]*)\s*results', html)
        result_count = int(result_count_match.group(1).replace(",", "")) if result_count_match else 0

        return {
            "query": query,
            "url": url,
            "result_count": result_count,
            "prices": sorted(set(prices)),
            "price_count": len(set(prices)),
        }

    except Exception as e:
        return {
            "query": query,
            "url": url,
            "result_count": 0,
            "prices": [],
            "price_count": 0,
            "error": str(e),
        }


def validate_scorecard_prices():
    """
    Search eBay for each component in our scorecard to validate pricing.
    Compare eBay market prices against our estimates.
    """
    DATA_DIR.mkdir(exist_ok=True)

    print("=" * 70)
    print("  EBAY AVIATION PARTS PRICE VALIDATION")
    print("  Checking real market prices against our estimates")
    print("=" * 70)

    # Load our scorecard estimates
    scorecard_file = DATA_DIR / "arbitrage_scorecard.json"
    if scorecard_file.exists():
        with open(scorecard_file) as f:
            scorecard = json.load(f)
        scorecard_prices = {s["component"]: s["mid_price"] for s in scorecard}
    else:
        scorecard_prices = {}

    results = []
    for item in SEARCH_QUERIES:
        print(f"\n  Searching: {item['query'][:50]}...", end=" ", flush=True)
        result = search_ebay_prices(item["query"], item.get("category", "26435"))

        if result.get("error"):
            print(f"Error: {result['error'][:50]}")
        else:
            prices = result["prices"]
            if prices:
                low = min(prices)
                high = max(prices)
                median = sorted(prices)[len(prices) // 2]
                avg = sum(prices) / len(prices)

                our_estimate = scorecard_prices.get(item["component"], 0)

                print(f"{len(prices)} prices found")
                print(f"    eBay range: ${low:,.0f} - ${high:,.0f}")
                print(f"    eBay median: ${median:,.0f}")
                if our_estimate > 0:
                    gap = ((our_estimate - median) / our_estimate * 100) if median > 0 else 0
                    print(f"    Our estimate: ${our_estimate:,.0f} | Gap: {gap:+.0f}%")

                result["component"] = item["component"]
                result["low_price"] = low
                result["high_price"] = high
                result["median_price"] = median
                result["avg_price"] = avg
                result["our_estimate"] = our_estimate
            else:
                print(f"No prices found ({result['result_count']} results)")
                result["component"] = item["component"]

        results.append(result)
        time.sleep(2)  # Rate limiting — be nice to eBay

    # Save results
    output_file = DATA_DIR / "ebay_price_validation.json"
    # Clean prices list for JSON (remove excessively long lists)
    for r in results:
        if "prices" in r and len(r["prices"]) > 50:
            r["prices"] = r["prices"][:50]

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Generate price comparison report
    print(f"\n{'=' * 70}")
    print(f"  PRICE VALIDATION SUMMARY")
    print(f"{'=' * 70}")
    print(f"\n  {'Component':<30}  {'Our Est':>10}  {'eBay Med':>10}  {'eBay Low':>10}  {'eBay High':>10}  {'Gap':>6}")
    print(f"  {'─'*30}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*6}")

    validated = 0
    for r in results:
        comp = r.get("component", "?")[:30]
        est = r.get("our_estimate", 0)
        med = r.get("median_price", 0)
        low = r.get("low_price", 0)
        high = r.get("high_price", 0)

        if med > 0:
            gap = ((est - med) / est * 100) if est > 0 else 0
            gap_str = f"{gap:+.0f}%"
            validated += 1
        else:
            gap_str = "N/A"

        est_str = f"${est:>9,}" if est > 0 else "N/A"
        med_str = f"${med:>9,}" if med > 0 else "N/A"
        low_str = f"${low:>9,}" if low > 0 else "N/A"
        high_str = f"${high:>9,}" if high > 0 else "N/A"

        print(f"  {comp:<30}  {est_str:>10}  {med_str:>10}  {low_str:>10}  {high_str:>10}  {gap_str:>6}")

    print(f"\n  Validated {validated}/{len(results)} components against eBay market data")
    print(f"  Results saved to {output_file}")

    return results


def find_ebay_arbitrage(results):
    """
    Identify specific arbitrage opportunities from eBay data.
    Look for: underpriced listings, price spreads, condition arbitrage.
    """
    print(f"\n{'=' * 70}")
    print(f"  EBAY ARBITRAGE OPPORTUNITIES")
    print(f"{'=' * 70}")

    opportunities = []
    for r in results:
        if not r.get("prices") or len(r["prices"]) < 3:
            continue

        prices = sorted(r["prices"])
        low = prices[0]
        high = prices[-1]
        median = prices[len(prices) // 2]

        # Arbitrage: buy at low, sell at median or above
        if high > low * 2:  # 2x spread = opportunity
            spread = high - low
            margin_pct = (spread / low) * 100

            opp = {
                "component": r.get("component", "Unknown"),
                "buy_price": low,
                "sell_price": median,
                "spread": median - low,
                "margin_pct": ((median - low) / low) * 100,
                "total_spread": spread,
                "max_margin_pct": margin_pct,
                "url": r.get("url", ""),
                "listings_found": len(prices),
            }
            opportunities.append(opp)

            print(f"\n  {opp['component']}")
            print(f"    Buy at: ${low:,.0f} | Sell at: ${median:,.0f} | Spread: ${opp['spread']:,.0f} ({opp['margin_pct']:.0f}%)")
            print(f"    Full range: ${low:,.0f} - ${high:,.0f} ({margin_pct:.0f}% max spread)")
            print(f"    Listings: {len(prices)}")

    if not opportunities:
        print("\n  No clear arbitrage opportunities found in current eBay data.")
        print("  This could mean: prices are efficient, or search needs refinement.")

    return opportunities


if __name__ == "__main__":
    results = validate_scorecard_prices()
    opportunities = find_ebay_arbitrage(results)
