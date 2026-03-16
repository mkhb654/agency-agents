"""
build_price_db.py — Build a parts pricing database from all free sources

Queries USAspending for specific aviation parts and builds a local
pricing reference database. This is your "price book" — when someone
asks "what's a turbine blade worth?", you have government transaction
data to back up your answer.

USAGE:
    python build_price_db.py
"""

import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")

# Comprehensive list of aviation parts to price
PART_SEARCHES = [
    # Engine components (highest value)
    "turbine blade aircraft engine",
    "combustion liner engine",
    "compressor blade aircraft",
    "fuel nozzle engine",
    "bearing engine aircraft",
    "oil seal engine aircraft",
    "turbine nozzle segment",
    "engine fan blade",
    "engine fuel control",
    "engine starter aircraft",
    "igniter plug aircraft engine",
    # Landing gear
    "landing gear actuator",
    "landing gear strut",
    "aircraft wheel assembly",
    "aircraft brake",
    "aircraft tire",
    "shimmy damper aircraft",
    # Flight controls
    "servo actuator aircraft",
    "flight control computer",
    "autopilot servo",
    "yaw damper",
    "aileron actuator",
    "elevator actuator",
    "rudder actuator",
    # Hydraulic
    "hydraulic pump aircraft",
    "hydraulic valve aircraft",
    "hydraulic reservoir aircraft",
    "hydraulic filter aircraft",
    # Avionics
    "flight management system FMS",
    "VHF transceiver aircraft",
    "transponder aircraft",
    "weather radar aircraft",
    "TCAS aircraft",
    "ADS-B aircraft",
    "radio altimeter aircraft",
    "GPS receiver aircraft",
    # APU / Power
    "auxiliary power unit APU",
    "generator aircraft IDG",
    "transformer rectifier aircraft",
    "battery aircraft",
    # Air systems
    "air conditioning pack valve",
    "bleed air valve aircraft",
    "pressurization controller",
    "oxygen regulator aircraft",
    # Structures
    "aircraft door assembly",
    "aircraft window",
    "leading edge slat",
    "trailing edge flap",
    # Propeller (GA)
    "propeller governor",
    "propeller blade",
    "propeller hub",
]


def search_usaspending(query, limit=5):
    """Search for a specific part in government contracts."""
    url = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    payload = {
        "filters": {
            "time_period": [{"start_date": "2020-10-01", "end_date": "2025-09-30"}],
            "award_type_codes": ["A", "B", "C", "D"],
            "keywords": [query],
        },
        "fields": [
            "Award ID", "Recipient Name", "Award Amount",
            "Description", "Start Date", "End Date",
            "Awarding Agency", "Awarding Sub Agency",
        ],
        "page": 1, "limit": limit,
        "sort": "Award Amount", "order": "desc",
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
        return []


def build_database():
    """Build the pricing database from USAspending queries."""
    DATA_DIR.mkdir(exist_ok=True)

    print("=" * 70)
    print("  BUILDING AVIATION PARTS PRICING DATABASE")
    print("  Source: USAspending.gov (real government transaction prices)")
    print("=" * 70)

    all_records = []
    parts_with_data = 0
    total_contract_value = 0

    for i, query in enumerate(PART_SEARCHES):
        print(f"  [{i+1}/{len(PART_SEARCHES)}] {query[:50]}...", end=" ", flush=True)

        results = search_usaspending(query, limit=5)

        if results:
            parts_with_data += 1
            for r in results:
                amount = r.get("Award Amount", 0) or 0
                total_contract_value += amount
                record = {
                    "search_query": query,
                    "award_id": r.get("Award ID", ""),
                    "recipient": r.get("Recipient Name", ""),
                    "amount": amount,
                    "description": r.get("Description", ""),
                    "start_date": r.get("Start Date", ""),
                    "end_date": r.get("End Date", ""),
                    "agency": r.get("Awarding Agency", ""),
                    "sub_agency": r.get("Awarding Sub Agency", ""),
                }
                all_records.append(record)

            amounts = [r.get("Award Amount", 0) or 0 for r in results if (r.get("Award Amount", 0) or 0) > 0]
            if amounts:
                print(f"{len(results)} contracts (${min(amounts):,.0f} - ${max(amounts):,.0f})")
            else:
                print(f"{len(results)} contracts")
        else:
            print("no contracts found")

        time.sleep(0.3)  # Rate limiting

    # Save full database
    db_file = DATA_DIR / "parts_price_database.json"
    with open(db_file, "w") as f:
        json.dump({
            "generated": datetime.now().isoformat(),
            "total_records": len(all_records),
            "parts_with_data": parts_with_data,
            "total_searches": len(PART_SEARCHES),
            "total_contract_value": total_contract_value,
            "records": all_records,
        }, f, indent=2, default=str)

    # Save as CSV for easy viewing
    csv_file = DATA_DIR / "parts_price_database.csv"
    with open(csv_file, "w") as f:
        f.write("search_query,recipient,amount,description,agency,start_date\n")
        for r in all_records:
            desc = r["description"].replace(",", ";").replace("\n", " ")[:100]
            recip = r["recipient"].replace(",", ";")[:40]
            f.write(
                f'"{r["search_query"]}","{recip}",{r["amount"]},'
                f'"{desc}","{r["agency"]}",{r["start_date"]}\n'
            )

    # Generate pricing summary
    print(f"\n{'=' * 70}")
    print(f"  PRICING DATABASE SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Parts searched: {len(PART_SEARCHES)}")
    print(f"  Parts with government pricing: {parts_with_data}")
    print(f"  Total contract records: {len(all_records)}")
    print(f"  Total contract value: ${total_contract_value:,.0f}")
    print(f"  Database saved: {db_file}")
    print(f"  CSV saved: {csv_file}")

    # Top suppliers across all parts
    suppliers = {}
    for r in all_records:
        name = r["recipient"]
        if name not in suppliers:
            suppliers[name] = {"total": 0, "count": 0, "parts": set()}
        suppliers[name]["total"] += r["amount"]
        suppliers[name]["count"] += 1
        suppliers[name]["parts"].add(r["search_query"])

    sorted_suppliers = sorted(suppliers.items(), key=lambda x: x[1]["count"], reverse=True)

    print(f"\n  Top Suppliers (by number of different parts):\n")
    for name, data in sorted_suppliers[:15]:
        parts_list = ", ".join(list(data["parts"])[:3])
        print(f"    {data['count']:>3} parts  ${data['total']:>14,.0f}  {name[:35]}")
        print(f"                                     → {parts_list[:50]}")

    print(f"\n{'=' * 70}")

    return all_records


if __name__ == "__main__":
    build_database()
