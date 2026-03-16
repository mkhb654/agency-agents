# MRO Parts Arbitrage Intelligence System

Aviation parts arbitrage intelligence powered by FREE government data.

## Quick Start

```bash
# Run the full pipeline (all data sources + analysis)
python run_all.py

# View the master dashboard
python dashboard.py

# Look up a specific part
python lookup_part.py "CFM56 turbine blade"
python lookup_part.py "APU Honeywell 131"
python lookup_part.py "landing gear actuator"

# Calculate deal P&L
python deal_calculator.py                          # Interactive mode
python deal_calculator.py --quick 10000 15000      # Quick: buy $10K sell $15K
python deal_calculator.py --quick 200000 500000    # Quick: APU deal
```

## What This System Does

Takes FREE government data and turns it into actionable arbitrage alerts:

| Data Source | What It Tells You | Cost |
|------------|-------------------|------|
| USAspending.gov | What the government PAYS for parts (real prices) | Free |
| FAA SDRs | Which parts FAIL most often (demand signal) | Free |
| FAA ADs | Which parts MUST be replaced by deadline (guaranteed demand) | Free |
| FAA Registry | How many aircraft need each part (market size) | Free |
| eBay | What parts trade for on the open market | Free |
| NSN Lookup | Military-to-commercial part cross-references | Free |

## Files

| File | What It Does |
|------|-------------|
| `run_all.py` | Runs entire pipeline in one command |
| `dashboard.py` | Master intelligence dashboard |
| `lookup_part.py` | Part-specific intelligence lookup (all sources) |
| `deal_calculator.py` | Calculate exact P&L for a deal |
| `ingest_usaspending.py` | Pull government contract pricing |
| `ingest_faa_registry.py` | Download 370K aircraft fleet data |
| `ingest_sdr.py` | Analyze component failure demand signals |
| `ingest_ebay.py` | Validate prices against eBay market |
| `monitor_ads.py` | Track AD-driven mandatory parts demand |
| `arbitrage_detector.py` | Identify 6 types of arbitrage opportunities |

## Top 5 Arbitrage Opportunities (Current)

| # | Component | Profit/Unit | Strategy |
|---|-----------|-------------|----------|
| 1 | APU (Auxiliary Power Unit) | $150,000 | Overhaul spread |
| 2 | Combustion Liners | $75,000 | AOG premium |
| 3 | Turbine Blades (HPT/LPT) | $48,750 | AOG premium |
| 4 | FMS Units | $37,500 | Overhaul spread |
| 5 | Hydraulic Pumps | $37,500 | AOG premium |

## 6 Arbitrage Strategies

1. **PMA Spread** — Source FAA-approved aftermarket parts at 30-60% below OEM
2. **AOG Premium** — Stock high-failure parts, sell at 2-5x when aircraft grounded
3. **AD Compliance** — Source parts before mandatory replacement deadlines
4. **Teardown Spread** — Parted-out aircraft worth 2-4x whole value
5. **Geographic Arbitrage** — Same part, different prices in different markets
6. **Condition Arbitrage** — Buy used, overhaul, sell at premium

## Your Workflow

```
1. Paul (Bangor) says "I have turbine blades from a 737 teardown"
   → python lookup_part.py "turbine blade 737"
   → System shows: $48K profit, 95/100 demand, active ADs

2. Sophia (Miami) says "I need a hydraulic pump ASAP — AOG"
   → python lookup_part.py "hydraulic pump"
   → System shows: $37K profit at AOG premium

3. You find the part from Paul for $10K
   → python deal_calculator.py --quick 10000 25000
   → Net profit: $14K, 56% margin, 127% ROI

4. Execute the deal through EasyFlyers logistics
   → Transaction data feeds back into the system
```

## Data in `data/` Directory

| File | Records | Description |
|------|---------|-------------|
| usaspending_aviation_awards.json | 300 | Government contracts with pricing |
| demand_signals.json | 15 | High-demand components ranked |
| arbitrage_scorecard.json | 15 | Components ranked by profit potential |
| ad_demand_analysis.json | 6 | Active ADs creating $604M in demand |
| ebay_price_validation.json | 14 | Market price benchmarks |
| dashboard_report.txt | — | Latest dashboard output |

## Next Steps

1. Register on StockMarket.aero (free) for real-time availability
2. Register on IATA MRO SmartHub (free tier, 5 lookups/day)
3. Set up eBay Browse API (free developer account)
4. Get Sophia's parts purchase history (12 months CSV)
5. Get Paul's teardown inventory list
