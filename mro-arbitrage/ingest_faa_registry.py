"""
ingest_faa_registry.py — Download and parse FAA Aircraft Registry

Downloads the full US aircraft registry (370K+ aircraft) and analyzes
fleet composition by make/model/engine type. This is your market sizing:
how many of each aircraft type are flying = demand for their parts.

Data refreshed daily at 11:30 PM CT by the FAA.

USAGE:
    python ingest_faa_registry.py
"""

import csv
import io
import os
import zipfile
from collections import Counter
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")
REGISTRY_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
REGISTRY_ZIP = DATA_DIR / "ReleasableAircraft.zip"


def download_registry():
    """Download the FAA aircraft registry ZIP file."""
    import urllib.request

    DATA_DIR.mkdir(exist_ok=True)

    # Check if already downloaded today
    if REGISTRY_ZIP.exists():
        mod_time = datetime.fromtimestamp(os.path.getmtime(REGISTRY_ZIP))
        if mod_time.date() == datetime.now().date():
            print(f"Registry already downloaded today ({mod_time}). Using cached version.")
            return True

    print(f"Downloading FAA Aircraft Registry from {REGISTRY_URL}...")
    print("(~60MB, may take a minute)")

    try:
        urllib.request.urlretrieve(REGISTRY_URL, REGISTRY_ZIP)
        size_mb = os.path.getsize(REGISTRY_ZIP) / (1024 * 1024)
        print(f"Downloaded: {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"Error downloading registry: {e}")
        return False


def parse_registry():
    """Parse the aircraft registry and return structured data."""
    if not REGISTRY_ZIP.exists():
        print("Registry ZIP not found. Run download first.")
        return None, None, None

    print("Parsing FAA Aircraft Registry...")

    aircraft = []
    engines = {}
    models = {}

    with zipfile.ZipFile(REGISTRY_ZIP, "r") as zf:
        file_list = zf.namelist()
        print(f"  Files in ZIP: {file_list}")

        # Parse MASTER file (main aircraft records)
        master_file = [f for f in file_list if "MASTER" in f.upper()][0]
        with zf.open(master_file) as f:
            content = f.read().decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                # Clean field names (FAA uses trailing spaces)
                clean = {k.strip(): v.strip() if v else "" for k, v in row.items()}
                aircraft.append(clean)

        # Parse ENGINE reference
        engine_files = [f for f in file_list if "ENGINE" in f.upper()]
        if engine_files:
            with zf.open(engine_files[0]) as f:
                content = f.read().decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    clean = {k.strip(): v.strip() if v else "" for k, v in row.items()}
                    code = clean.get("CODE", "")
                    if code:
                        engines[code] = clean

        # Parse ACFTREF (aircraft model reference)
        acft_files = [f for f in file_list if "ACFTREF" in f.upper()]
        if acft_files:
            with zf.open(acft_files[0]) as f:
                content = f.read().decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    clean = {k.strip(): v.strip() if v else "" for k, v in row.items()}
                    code = clean.get("CODE", "")
                    if code:
                        models[code] = clean

    print(f"  Parsed {len(aircraft)} aircraft records")
    print(f"  Parsed {len(engines)} engine types")
    print(f"  Parsed {len(models)} aircraft models")

    return aircraft, engines, models


def analyze_fleet(aircraft, engines, models):
    """Analyze fleet composition for market sizing."""
    if not aircraft:
        return

    print(f"\n{'=' * 60}")
    print(f"  FAA AIRCRAFT REGISTRY ANALYSIS")
    print(f"{'=' * 60}")

    # Filter to active/valid aircraft
    active = [a for a in aircraft if a.get("STATUS CODE", "") in ["V", "A", ""]]
    print(f"\n  Total registered: {len(aircraft)}")
    print(f"  Active/Valid: {len(active)}")

    # Status breakdown
    status_counts = Counter(a.get("STATUS CODE", "Unknown") for a in aircraft)
    print(f"\n  Status breakdown:")
    status_names = {
        "V": "Valid", "A": "Valid (Triennial)", "D": "Deregistered",
        "E": "Expired", "M": "Multiple", "R": "Revoked",
        "S": "Suspended", "T": "Transfer", "X": "Expired Dealer",
        "Z": "Cert Terminated", "N": "Non-US",
    }
    for status, count in status_counts.most_common(10):
        name = status_names.get(status, status)
        print(f"    {name} ({status}): {count:,}")

    # Aircraft type breakdown
    type_map = {"1": "Glider", "2": "Balloon", "3": "Blimp", "4": "Fixed Wing Single",
                "5": "Fixed Wing Multi", "6": "Rotorcraft", "7": "Weight-shift",
                "8": "Powered Parachute", "9": "Gyroplane", "H": "Hybrid Lift"}
    type_counts = Counter(a.get("TYPE AIRCRAFT", "?") for a in active)
    print(f"\n  Aircraft types (active):")
    for typ, count in type_counts.most_common():
        name = type_map.get(typ, typ)
        print(f"    {name}: {count:,}")

    # Engine type breakdown
    engine_type_map = {"0": "None", "1": "Reciprocating", "2": "Turbo-prop",
                       "3": "Turbo-shaft", "4": "Turbo-jet", "5": "Turbo-fan",
                       "6": "Ramjet", "7": "2 Cycle", "8": "4 Cycle",
                       "9": "Unknown", "10": "Electric", "11": "Rotary"}
    eng_counts = Counter(a.get("TYPE ENGINE", "?") for a in active)
    print(f"\n  Engine types (active):")
    for eng, count in eng_counts.most_common():
        name = engine_type_map.get(eng, eng)
        print(f"    {name}: {count:,}")

    # Top manufacturers (by MFR MDL CODE lookup)
    mfr_counts = Counter()
    for a in active:
        code = a.get("MFR MDL CODE", "")
        if code and code in models:
            mfr = models[code].get("MFR", "Unknown")
            mfr_counts[mfr] += 1
        else:
            mfr_counts["Unknown"] += 1

    print(f"\n  Top 20 Manufacturers (active fleet):")
    for mfr, count in mfr_counts.most_common(20):
        print(f"    {count:>7,}  {mfr}")

    # Top aircraft models
    model_counts = Counter()
    for a in active:
        code = a.get("MFR MDL CODE", "")
        if code and code in models:
            m = models[code]
            model_name = f"{m.get('MFR', '?')} {m.get('MODEL', '?')}"
            model_counts[model_name] += 1

    print(f"\n  Top 30 Aircraft Models (active fleet):")
    for model, count in model_counts.most_common(30):
        print(f"    {count:>7,}  {model}")

    # Age distribution
    current_year = datetime.now().year
    ages = []
    for a in active:
        yr = a.get("YEAR MFR", "")
        if yr and yr.isdigit():
            age = current_year - int(yr)
            if 0 <= age <= 100:
                ages.append(age)

    if ages:
        ages.sort()
        print(f"\n  Fleet Age Distribution:")
        print(f"    Average age: {sum(ages)/len(ages):.1f} years")
        print(f"    Median age:  {ages[len(ages)//2]} years")
        print(f"    0-10 years:  {sum(1 for a in ages if a <= 10):,}")
        print(f"    11-20 years: {sum(1 for a in ages if 11 <= a <= 20):,}")
        print(f"    21-30 years: {sum(1 for a in ages if 21 <= a <= 30):,}")
        print(f"    31-40 years: {sum(1 for a in ages if 31 <= a <= 40):,}")
        print(f"    40+ years:   {sum(1 for a in ages if a > 40):,}")

    # Save fleet summary as CSV
    fleet_csv = DATA_DIR / "faa_fleet_summary.csv"
    with open(fleet_csv, "w") as f:
        f.write("model,manufacturer,count,avg_age\n")
        for model_name, count in model_counts.most_common(200):
            # Calculate avg age for this model
            model_ages = []
            for a in active:
                code = a.get("MFR MDL CODE", "")
                if code and code in models:
                    m = models[code]
                    name = f"{m.get('MFR', '?')} {m.get('MODEL', '?')}"
                    if name == model_name:
                        yr = a.get("YEAR MFR", "")
                        if yr and yr.isdigit():
                            model_ages.append(current_year - int(yr))
            avg_age = sum(model_ages) / len(model_ages) if model_ages else 0
            mfr = model_name.split(" ")[0] if " " in model_name else model_name
            f.write(f'"{model_name}","{mfr}",{count},{avg_age:.1f}\n')

    print(f"\n  Fleet summary saved to: {fleet_csv}")

    # Save full active registry as CSV (for later use)
    active_csv = DATA_DIR / "faa_active_aircraft.csv"
    if active:
        fieldnames = list(active[0].keys())
        with open(active_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(active)
        print(f"  Active aircraft CSV saved to: {active_csv}")

    return model_counts, mfr_counts


if __name__ == "__main__":
    if download_registry():
        aircraft, engines, models = parse_registry()
        if aircraft:
            analyze_fleet(aircraft, engines, models)
