"""
supplier_directory.py — Build a sourcing partner directory from real contracts

Every company in the USAspending price database has PROVEN government
contracts for aviation parts. These are real suppliers with real capabilities.
This script extracts them into a contact-ready directory.

USAGE:
    python supplier_directory.py
    python supplier_directory.py "actuator"     # Filter by part type
"""

import json
import sys
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")


def build_directory(filter_term=None):
    """Build supplier directory from all available data."""

    # Load price database
    db_file = DATA_DIR / "parts_price_database.json"
    if not db_file.exists():
        print("No price database. Run build_price_db.py first.")
        return

    with open(db_file) as f:
        db = json.load(f)

    records = db.get("records", [])

    # Also load NAICS-level awards
    awards_file = DATA_DIR / "usaspending_aviation_awards.json"
    awards = []
    if awards_file.exists():
        with open(awards_file) as f:
            awards = json.load(f)

    print("╔" + "═" * 68 + "╗")
    print("║" + "  AVIATION PARTS SUPPLIER DIRECTORY".center(68) + "║")
    print("║" + "  Built from real government contract data".center(68) + "║")
    print("╚" + "═" * 68 + "╝")

    # Build supplier profiles
    suppliers = {}

    for r in records:
        name = r.get("recipient", "").strip()
        if not name:
            continue

        if filter_term and filter_term.lower() not in json.dumps(r).lower():
            continue

        if name not in suppliers:
            suppliers[name] = {
                "total_value": 0,
                "contract_count": 0,
                "parts": set(),
                "agencies": set(),
                "descriptions": [],
                "date_range": {"earliest": "9999", "latest": "0000"},
            }

        s = suppliers[name]
        s["total_value"] += r.get("amount", 0)
        s["contract_count"] += 1
        s["parts"].add(r.get("search_query", ""))
        if r.get("agency"):
            s["agencies"].add(r["agency"])
        if r.get("description"):
            s["descriptions"].append(r["description"][:100])
        if r.get("start_date"):
            if r["start_date"] < s["date_range"]["earliest"]:
                s["date_range"]["earliest"] = r["start_date"]
            if r["start_date"] > s["date_range"]["latest"]:
                s["date_range"]["latest"] = r["start_date"]

    # Also add from NAICS awards (broader contracts)
    for a in awards:
        name = a.get("Recipient Name", "").strip()
        if not name:
            continue
        if filter_term and filter_term.lower() not in json.dumps(a).lower():
            continue

        if name not in suppliers:
            suppliers[name] = {
                "total_value": 0,
                "contract_count": 0,
                "parts": set(),
                "agencies": set(),
                "descriptions": [],
                "date_range": {"earliest": "9999", "latest": "0000"},
            }

        s = suppliers[name]
        amount = a.get("Award Amount", 0) or 0
        s["total_value"] += amount
        s["contract_count"] += 1
        if a.get("Description"):
            s["descriptions"].append(a["Description"][:100])

    if filter_term:
        print(f"\n  Filtered by: '{filter_term}'")

    # Categorize suppliers by size
    mega = []      # > $1B
    large = []     # $100M - $1B
    mid = []       # $10M - $100M
    small = []     # $1M - $10M
    micro = []     # < $1M

    for name, data in suppliers.items():
        val = data["total_value"]
        entry = (name, data)
        if val >= 1_000_000_000:
            mega.append(entry)
        elif val >= 100_000_000:
            large.append(entry)
        elif val >= 10_000_000:
            mid.append(entry)
        elif val >= 1_000_000:
            small.append(entry)
        else:
            micro.append(entry)

    # Sort each tier
    for tier in [mega, large, mid, small, micro]:
        tier.sort(key=lambda x: x[1]["total_value"], reverse=True)

    # ---- OEMs / Primes (not sourcing targets, but competitive intelligence) ----
    if mega:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  OEM / PRIME CONTRACTORS (competitive intelligence)':^68}│")
        print(f"└{'─' * 68}┘")
        print(f"  These are your COMPETITORS for parts, not your suppliers.\n")
        for name, data in mega:
            print(f"  ${data['total_value']:>15,.0f}  {name}")

    # ---- Large Suppliers (potential partners at scale) ----
    if large:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  LARGE SUPPLIERS ($100M+) — Partner at scale':^68}│")
        print(f"└{'─' * 68}┘\n")
        for name, data in large:
            parts = ", ".join(list(data["parts"])[:3]) if data["parts"] else "Various"
            print(f"  ${data['total_value']:>13,.0f}  {name}")
            print(f"    Contracts: {data['contract_count']} | Parts: {parts[:50]}")
            if data["descriptions"]:
                print(f"    Work: {data['descriptions'][0][:60]}")
            print()

    # ---- Mid-Tier (YOUR SWEET SPOT for sourcing) ----
    if mid:
        print(f"\n┌{'─' * 68}┐")
        print(f"│  {'YOUR SOURCING SWEET SPOT ($10M-$100M)':^66}  │")
        print(f"│  {'These companies are big enough to have inventory,':^66}  │")
        print(f"│  {'small enough to do business with you directly':^66}  │")
        print(f"└{'─' * 68}┘\n")
        for name, data in mid:
            parts = ", ".join(list(data["parts"])[:3]) if data["parts"] else "Various"
            print(f"  ${data['total_value']:>13,.0f}  {name}")
            print(f"    Contracts: {data['contract_count']} | Parts: {parts[:50]}")
            if data["descriptions"]:
                print(f"    Work: {data['descriptions'][0][:60]}")
            print()

    # ---- Small Suppliers (nimble, relationship-based) ----
    if small:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  SMALL SUPPLIERS ($1M-$10M) — Nimble, relationship-based':^68}│")
        print(f"└{'─' * 68}┘\n")
        for name, data in small[:15]:
            parts = ", ".join(list(data["parts"])[:3]) if data["parts"] else "Various"
            print(f"  ${data['total_value']:>13,.0f}  {name}")
            print(f"    Parts: {parts[:60]}")

    # ---- Micro Suppliers (niche specialists) ----
    if micro:
        print(f"\n┌{'─' * 68}┐")
        print(f"│{'  NICHE SPECIALISTS (< $1M) — Deep expertise, specific parts':^68}│")
        print(f"└{'─' * 68}┘\n")
        for name, data in micro[:15]:
            parts = ", ".join(list(data["parts"])[:3]) if data["parts"] else "Various"
            desc = data["descriptions"][0][:60] if data["descriptions"] else ""
            print(f"  ${data['total_value']:>10,.0f}  {name}")
            if desc:
                print(f"    → {desc}")

    # ---- Summary ----
    print(f"\n{'═' * 70}")
    print(f"  DIRECTORY SUMMARY")
    print(f"{'═' * 70}")
    print(f"  Total suppliers found: {len(suppliers)}")
    print(f"  OEM/Primes: {len(mega)}")
    print(f"  Large ($100M+): {len(large)}")
    print(f"  Mid-tier ($10M-$100M): {len(mid)} ← YOUR TARGET")
    print(f"  Small ($1M-$10M): {len(small)}")
    print(f"  Niche (< $1M): {len(micro)}")
    print(f"{'═' * 70}")

    # Save directory
    dir_data = {}
    for name, data in suppliers.items():
        dir_data[name] = {
            "total_value": data["total_value"],
            "contract_count": data["contract_count"],
            "parts": list(data["parts"]),
            "agencies": list(data["agencies"]),
            "descriptions": data["descriptions"][:5],
        }

    output = DATA_DIR / "supplier_directory.json"
    with open(output, "w") as f:
        json.dump(dir_data, f, indent=2, default=str)
    print(f"  Directory saved to {output}")


if __name__ == "__main__":
    filter_term = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    build_directory(filter_term)
