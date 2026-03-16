"""
run_all.py — Run the complete MRO Arbitrage Intelligence Pipeline

Executes all data ingestion, analysis, and reporting in sequence.
One command to refresh everything.

USAGE:
    python run_all.py
"""

import subprocess
import sys
import time
from datetime import datetime

SCRIPTS = [
    ("ingest_usaspending.py", "Pulling government contract pricing..."),
    ("ingest_sdr.py", "Analyzing component failure demand signals..."),
    ("monitor_ads.py", "Monitoring Airworthiness Directive demand spikes..."),
    ("ingest_ebay.py", "Validating prices against eBay market data..."),
    ("arbitrage_detector.py", "Running arbitrage detection..."),
    ("dashboard.py", "Generating master dashboard..."),
]


def run_pipeline():
    print("=" * 70)
    print("  MRO ARBITRAGE INTELLIGENCE — FULL PIPELINE")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = []
    for script, description in SCRIPTS:
        print(f"\n  [{len(results)+1}/{len(SCRIPTS)}] {description}")
        start = time.time()

        try:
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True, text=True, timeout=300,
            )
            elapsed = time.time() - start
            status = "OK" if result.returncode == 0 else "FAIL"
            results.append((script, status, elapsed))
            print(f"  → {status} ({elapsed:.1f}s)")

            if result.returncode != 0:
                print(f"  Error: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            results.append((script, "TIMEOUT", elapsed))
            print(f"  → TIMEOUT ({elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.time() - start
            results.append((script, "ERROR", elapsed))
            print(f"  → ERROR: {e}")

    print(f"\n{'=' * 70}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'=' * 70}")
    print(f"\n  {'Script':<30} {'Status':>8} {'Time':>8}")
    print(f"  {'─'*30} {'─'*8} {'─'*8}")
    for script, status, elapsed in results:
        print(f"  {script:<30} {status:>8} {elapsed:>7.1f}s")

    total_time = sum(r[2] for r in results)
    passed = sum(1 for r in results if r[1] == "OK")
    print(f"\n  {passed}/{len(results)} scripts passed in {total_time:.0f}s")
    print(f"  Dashboard: python dashboard.py")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    run_pipeline()
