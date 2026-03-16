"""
ingest_usaspending.py — Pull REAL aviation parts transaction prices from USAspending.gov

USAspending.gov API requires NO authentication. Returns actual contract award amounts
the US government paid for aviation parts — the closest to real transaction prices
you'll get from public data.

NAICS codes for aviation:
  336411 - Aircraft Manufacturing
  336412 - Aircraft Engine and Engine Parts Manufacturing
  336413 - Other Aircraft Parts and Auxiliary Equipment Manufacturing

PSC (Product Service Code) for parts:
  1560 - Airframe Structural Components
  1610 - Aircraft Propellers and Components
  1615 - Helicopter Rotor Blades/Drive Components
  1620 - Aircraft Landing Gear Components
  1630 - Aircraft Wheel and Brake Systems
  1640 - Aircraft Control/Drive Components
  1650 - Aircraft Hydraulic/Vacuum/De-icing Components
  1660 - Aircraft Air Conditioning/Heating/Pressurizing
  1670 - Aircraft Parachute/Cargo Tie Down Equipment
  1680 - Miscellaneous Aircraft Accessories/Components
  2810 - Gas Turbines and Jet Engines
  2815 - Gas Turbine Engines, Non-Aircraft
  2835 - Gas Turbine Engine Electrical/Starting Components
  2840 - Gas Turbine Engine Components
  2895 - Miscellaneous Engine Accessories

USAGE:
    python ingest_usaspending.py
"""

import json
import time
import os
from pathlib import Path
from datetime import datetime, timedelta

DATA_DIR = Path("data")

# Aviation-related PSC codes (Product Service Codes)
AVIATION_PSC_CODES = [
    "1560", "1610", "1615", "1620", "1630", "1640", "1650", "1660",
    "1670", "1680", "2810", "2815", "2835", "2840", "2895",
]

# Aviation NAICS codes
AVIATION_NAICS = ["336411", "336412", "336413"]

USASPENDING_API = "https://api.usaspending.gov/api/v2"


def fetch_awards_by_psc(psc_code, fiscal_year=2025, page=1, limit=100):
    """Fetch contract awards for a specific PSC code from USAspending API."""
    import urllib.request
    import urllib.error

    url = f"{USASPENDING_API}/search/spending_by_award/"

    payload = {
        "filters": {
            "time_period": [
                {
                    "start_date": f"{fiscal_year - 1}-10-01",
                    "end_date": f"{fiscal_year}-09-30"
                }
            ],
            "award_type_codes": ["A", "B", "C", "D"],  # Contracts only
            "psc_codes": [psc_code],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Total Outlays",
            "Description",
            "Contract Award Type",
            "Start Date",
            "End Date",
            "Awarding Agency",
            "Awarding Sub Agency",
            "recipient_id",
            "internal_id",
            "generated_internal_id",
        ],
        "page": page,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code} for PSC {psc_code}: {e.reason}")
        return None
    except Exception as e:
        print(f"  Error for PSC {psc_code}: {e}")
        return None


def fetch_awards_by_naics(naics_code, fiscal_year=2025, page=1, limit=100):
    """Fetch contract awards for a specific NAICS code."""
    import urllib.request

    url = f"{USASPENDING_API}/search/spending_by_award/"

    payload = {
        "filters": {
            "time_period": [
                {
                    "start_date": f"{fiscal_year - 1}-10-01",
                    "end_date": f"{fiscal_year}-09-30"
                }
            ],
            "award_type_codes": ["A", "B", "C", "D"],
            "naics_codes": {"require": [naics_code]},
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Award Amount",
            "Total Outlays",
            "Description",
            "Contract Award Type",
            "Start Date",
            "End Date",
            "Awarding Agency",
            "Awarding Sub Agency",
        ],
        "page": page,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  Error for NAICS {naics_code}: {e}")
        return None


def fetch_spending_summary():
    """Get total spending summary for aviation parts categories."""
    import urllib.request

    url = f"{USASPENDING_API}/search/spending_by_category/psc/"

    payload = {
        "filters": {
            "time_period": [
                {"start_date": "2023-10-01", "end_date": "2025-09-30"}
            ],
            "award_type_codes": ["A", "B", "C", "D"],
            "naics_codes": {"require": ["336413"]},
        },
        "category": "psc",
        "limit": 50,
        "page": 1,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  Error fetching summary: {e}")
        return None


def ingest_all_aviation_awards():
    """Main ingestion function — pulls aviation parts contract data."""
    DATA_DIR.mkdir(exist_ok=True)
    all_awards = []
    total_value = 0

    print("=" * 60)
    print("  USAspending.gov — Aviation Parts Contract Awards")
    print("=" * 60)

    # Fetch by PSC codes (more granular — specific part categories)
    print("\n--- Fetching by PSC (Product Service Code) ---\n")
    for psc in AVIATION_PSC_CODES:
        print(f"  PSC {psc}...", end=" ", flush=True)
        result = fetch_awards_by_psc(psc, fiscal_year=2025, limit=100)

        if result and "results" in result:
            awards = result["results"]
            count = len(awards)
            value = sum(a.get("Award Amount", 0) or 0 for a in awards)
            total_value += value

            for a in awards:
                a["psc_code"] = psc
                a["source"] = "psc"

            all_awards.extend(awards)
            print(f"{count} awards, ${value:,.0f}")
        else:
            print("no data or error")

        time.sleep(0.5)  # Rate limiting

    # Fetch by NAICS codes (broader — all aviation manufacturing)
    print("\n--- Fetching by NAICS (Industry Code) ---\n")
    for naics in AVIATION_NAICS:
        print(f"  NAICS {naics}...", end=" ", flush=True)
        result = fetch_awards_by_naics(naics, fiscal_year=2025, limit=100)

        if result and "results" in result:
            awards = result["results"]
            count = len(awards)
            value = sum(a.get("Award Amount", 0) or 0 for a in awards)

            for a in awards:
                a["naics_code"] = naics
                a["source"] = "naics"

            # Don't double-count in total (overlap with PSC)
            all_awards.extend(awards)
            print(f"{count} awards, ${value:,.0f}")
        else:
            print("no data or error")

        time.sleep(0.5)

    # Save raw data
    output_file = DATA_DIR / "usaspending_aviation_awards.json"
    with open(output_file, "w") as f:
        json.dump(all_awards, f, indent=2, default=str)

    # Create summary CSV
    csv_file = DATA_DIR / "usaspending_aviation_summary.csv"
    with open(csv_file, "w") as f:
        f.write("award_id,recipient,amount,description,psc_code,naics_code,start_date,end_date,agency\n")
        for a in all_awards:
            award_id = a.get("Award ID", "").replace(",", " ")
            recipient = (a.get("Recipient Name") or "").replace(",", " ")
            amount = a.get("Award Amount", 0) or 0
            desc = (a.get("Description") or "").replace(",", " ").replace("\n", " ")[:200]
            psc = a.get("psc_code", "")
            naics = a.get("naics_code", "")
            start = a.get("Start Date", "")
            end = a.get("End Date", "")
            agency = (a.get("Awarding Agency") or "").replace(",", " ")
            f.write(f"{award_id},{recipient},{amount},{desc},{psc},{naics},{start},{end},{agency}\n")

    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total awards fetched: {len(all_awards)}")
    print(f"  Total contract value: ${total_value:,.0f}")
    print(f"  Raw JSON saved to: {output_file}")
    print(f"  Summary CSV saved to: {csv_file}")
    print(f"{'=' * 60}")

    return all_awards


def analyze_awards(awards):
    """Quick analysis of fetched awards."""
    if not awards:
        print("No awards to analyze.")
        return

    print(f"\n{'=' * 60}")
    print(f"  AWARD ANALYSIS")
    print(f"{'=' * 60}")

    # Top recipients
    recipients = {}
    for a in awards:
        name = a.get("Recipient Name", "Unknown")
        amount = a.get("Award Amount", 0) or 0
        recipients[name] = recipients.get(name, 0) + amount

    sorted_recipients = sorted(recipients.items(), key=lambda x: x[1], reverse=True)[:15]
    print("\n  Top 15 Recipients by Award Value:")
    for name, amount in sorted_recipients:
        print(f"    ${amount:>15,.0f}  {name}")

    # By PSC code
    psc_totals = {}
    for a in awards:
        psc = a.get("psc_code", "N/A")
        amount = a.get("Award Amount", 0) or 0
        if psc not in psc_totals:
            psc_totals[psc] = {"count": 0, "total": 0}
        psc_totals[psc]["count"] += 1
        psc_totals[psc]["total"] += amount

    PSC_NAMES = {
        "1560": "Airframe Structural Components",
        "1620": "Landing Gear Components",
        "1630": "Wheel & Brake Systems",
        "1640": "Control/Drive Components",
        "1650": "Hydraulic/Vacuum/De-icing",
        "1680": "Misc Aircraft Accessories",
        "2810": "Gas Turbine Jet Engines",
        "2840": "Gas Turbine Components",
        "2835": "Engine Electrical/Starting",
    }

    print("\n  Spending by Part Category (PSC):")
    for psc, data in sorted(psc_totals.items(), key=lambda x: x[1]["total"], reverse=True):
        if psc and psc != "N/A":
            name = PSC_NAMES.get(psc, psc)
            print(f"    PSC {psc} ({name}): {data['count']} awards, ${data['total']:,.0f}")

    # Award size distribution
    amounts = [a.get("Award Amount", 0) or 0 for a in awards if (a.get("Award Amount", 0) or 0) > 0]
    if amounts:
        amounts.sort()
        print(f"\n  Award Size Distribution:")
        print(f"    Min:    ${min(amounts):,.0f}")
        print(f"    Median: ${amounts[len(amounts)//2]:,.0f}")
        print(f"    Mean:   ${sum(amounts)/len(amounts):,.0f}")
        print(f"    Max:    ${max(amounts):,.0f}")

    # Save analysis
    analysis_file = DATA_DIR / "usaspending_analysis.txt"
    with open(analysis_file, "w") as f:
        f.write("USAspending Aviation Parts Analysis\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        f.write(f"Total awards: {len(awards)}\n")
        f.write(f"Total value: ${sum(amounts):,.0f}\n\n")
        f.write("Top Recipients:\n")
        for name, amount in sorted_recipients:
            f.write(f"  ${amount:>15,.0f}  {name}\n")

    print(f"\n  Analysis saved to: {analysis_file}")


if __name__ == "__main__":
    awards = ingest_all_aviation_awards()
    analyze_awards(awards)
