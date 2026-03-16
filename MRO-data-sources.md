# Aviation MRO Parts Data Sources — Complete Intelligence Report

**Date:** 2026-03-14
**Verdict: You do NOT need Sophia's data to start. Government data alone gives you pricing + demand signals.**

---

## The Answer: 6 Free Sources That Bootstrap Your System

| # | Source | What It Gives You | Cost | How To Get It |
|---|--------|-------------------|------|---------------|
| 1 | **USAspending.gov** | **ACTUAL TRANSACTION PRICES** the government paid for aviation parts | FREE | REST API, no auth needed, bulk download |
| 2 | **FAA Service Difficulty Reports** | 1.7M failure reports = which parts fail on which aircraft = DEMAND SIGNAL | FREE | Web query at sdrs.faa.gov |
| 3 | **FAA Aircraft Registry** | 370K+ registered aircraft = fleet universe = market sizing | FREE | Daily CSV download (~60MB ZIP) |
| 4 | **FAA Airworthiness Directives** | Mandatory part replacements with deadlines = PREDICTABLE DEMAND | FREE | API with free key at api.faa.gov |
| 5 | **DLA PUB LOG** | Government unit prices + NSN-to-commercial part number cross-references | FREE | Monthly DVD/download |
| 6 | **eBay Browse API** | Actual sold prices for aviation parts (GA-heavy but real transactions) | FREE | Developer program, 5000 calls/month |

### Combined, these give you:
- **Pricing baseline** (USAspending + DLA PUB LOG + eBay sold prices)
- **Demand forecasting** (SDR failure rates + AD mandatory replacements + fleet size)
- **Market sizing** (Aircraft Registry fleet composition + BTS airline maintenance budgets)
- **Part cross-referencing** (CAGE codes + NSN mapping + PMA alternatives)

---

## Tier 1: FREE — Immediate Access, High Value

### 1. USAspending.gov — ACTUAL TRANSACTION PRICES
- **URL:** https://www.usaspending.gov
- **API:** https://api.usaspending.gov/docs/endpoints — NO authentication required
- **What:** Every federal contract award. Search by NAICS codes:
  - 336411 (Aircraft Manufacturing)
  - 336412 (Aircraft Engine Manufacturing)
  - 336413 (Aircraft Parts & Equipment)
- **Also search by PSC (Product Service Code):**
  - 1560 (Airframe Structural Components)
  - 1680 (Aircraft Accessories & Components)
  - 2840 (Gas Turbine Engine Components)
  - 2835 (Engine Electrical System Components)
- **Fields:** Award amount (THE PRICE), contractor name, CAGE code, item description, contract type, period
- **Volume:** Billions of dollars in aviation parts awards
- **Why it matters:** This is the closest to real transaction prices you'll get from public data. Government prices are considered fair market value benchmarks.

### 2. FAA Service Difficulty Reports (SDRs) — DEMAND SIGNAL
- **URL:** https://sdrs.faa.gov/Query.aspx
- **Volume:** ~1,700,000 reports from 1975-present
- **Fields:** Aircraft make/model, ATA code, part name, part number, part manufacturer, failure mode, narrative
- **Why it matters:** SDRs tell you which parts FAIL, how often, on which aircraft. Failure rate = replacement demand. A part that fails 500 times/year on 737s has guaranteed demand.
- **How to use:** Rank components by failure frequency per aircraft type. Cross-reference with fleet size (Registry) to predict annual demand.
- **GitHub tools:** [Boeing/sdr-hazards-classification](https://github.com/Boeing/sdr-hazards-classification) — Boeing+FAA ML models on SDR data

### 3. FAA Aircraft Registry — FLEET UNIVERSE
- **URL:** https://registry.faa.gov/database/ReleasableAircraft.zip (~60MB)
- **Format:** CSV, refreshed daily at 11:30 PM CT
- **Fields:** N-number, serial number, make/model, engine type, year manufactured, owner, status, airworthiness date
- **Volume:** 370,000+ registered aircraft
- **Why it matters:** Total addressable market. "There are X active 737-800s with CFM56-7B engines. Each needs Y components replaced per year. That's the market for CFM56 parts."
- **GitHub tools:** [simonw/scrape-faa-releasable-aircraft](https://github.com/simonw/scrape-faa-releasable-aircraft), [ClearAerospace/faa-aircraft-registry](https://github.com/ClearAerospace/faa-aircraft-registry)

### 4. FAA Airworthiness Directives — PREDICTABLE DEMAND
- **URL:** https://drs.faa.gov/browse/ADFRAWD/doctypeDetails
- **API:** https://api.faa.gov/s/ (free API key)
- **Why it matters:** ADs are MANDATORY. When the FAA issues an AD requiring part replacement on all 737-800s by a specific deadline, that creates guaranteed, time-bounded demand for specific parts. You can predict demand spikes.

### 5. DLA PUB LOG — GOVERNMENT PRICES + CROSS-REFERENCES
- **URL:** https://www.dla.mil/Information-Operations/Services/Applications/PUB-LOG/
- **Download:** https://www.dla.mil/HQ/InformationOperations/LogisticsInformationServices/FOIAReading.aspx
- **Format:** Monthly DVD/download (IMD format)
- **Fields:** NSN, CAGE code, part number, UNIT PRICE, item description, cross-reference data
- **Why it matters:** Contains actual government unit prices AND maps NSN → commercial part numbers. This is the bridge between military and commercial parts. UNDERUTILIZED GOLD MINE.

### 6. eBay Browse API — ACTUAL TRANSACTION PRICES
- **URL:** https://developer.ebay.com (free developer program)
- **Category:** Aviation Parts & Accessories (ID: 26435), Engine Parts (ID: 26439)
- **Volume:** 50,000-100,000+ active listings at any time
- **Key feature:** COMPLETED/SOLD listings show actual prices parts traded at
- **Limitation:** Skews toward General Aviation (Cessna, Piper, Beechcraft). Less commercial airline parts.
- **Why it matters:** Only public source with real market transaction prices (not list prices).

---

## Tier 2: FREE — Limited Access, Still Valuable

### 7. IATA MRO SmartHub — Fair Market Values
- **URL:** https://mrosmarthub.iata.org
- **Free tier:** 5 part searches per day, can view listings, participate in auctions
- **Paid tier:** Full access to FMV data on 1.5M+ part numbers
- **Why it matters:** IATA-backed, neutral platform. Best source for commercial aviation parts FMV. Free tier is limited but useful for validation.

### 8. StockMarket.aero — Free Parts Marketplace
- **URL:** https://stockmarket.aero
- **Cost:** COMPLETELY FREE for all users
- **Data:** Real-time inventory listings, MRO capabilities, part alternatives
- **Limitation:** RFQ-based (no prices shown), but availability and vendor data is valuable
- **Why it matters:** World's largest FREE open marketplace for aircraft parts since 2006

### 9. BTS Form 41 Data — Airline Maintenance Spending
- **URL:** https://www.transtats.bts.gov
- **Key schedules:** P-5.2 (maintenance costs by aircraft type), P-6 (labor vs materials breakdown)
- **Why it matters:** Only public source quantifying how much airlines spend on parts by aircraft type. Market sizing.

### 10. NTSB Aviation Accident Database
- **URL:** https://data.ntsb.gov/avdata
- **Download:** avall.zip (1982-present) — bulk CSV
- **API:** https://developer.ntsb.gov (free registration)
- **Volume:** 90,000+ records
- **Why it matters:** Component failure data from actual accidents. Supplements SDR data.

### 11. FAA PMA Database — Aftermarket Alternatives
- **URL:** https://drs.faa.gov/browse/PMA/doctypeDetails
- **Cross-reference tool:** [FlyPMA.com](https://www.flypma.com/search.php) — search by OEM part number, batch up to 5,000 parts
- **Why it matters:** PMA parts are 30-60% cheaper than OEM. This database tells you which parts have aftermarket alternatives = competitive pricing pressure.

### 12. NASA ASRS — Safety Reports from Mechanics
- **URL:** https://asrs.arc.nasa.gov/search/database.html
- **Why it matters:** Mechanics describe parts problems, failures, sourcing difficulties. Qualitative demand intelligence.

### 13. FlightAware AeroAPI — Grounded Aircraft Detection
- **URL:** https://www.flightaware.com/aeroapi/portal
- **Free tier:** 500 calls/month
- **Why it matters:** Aircraft not flying = potentially being parted out = parts supply entering market. Aircraft returning to service = parts demand.

---

## Tier 3: PAID — Requires Partnership or Subscription

### 14. ILS (Inventory Locator Service) — THE Industry Standard
- **URL:** https://www.ilsmart.com
- **Cost:** Custom annual subscription (typically $$$)
- **Data:** 6+ billion parts listings, 28,000+ users, 165+ countries
- **Assessment:** No free data. Requires subscription. Industry gold standard.

### 15. PartsBase — Second Largest Marketplace
- **URL:** https://www.partsbase.com
- **Cost:** Paid subscription (14-day free trial)
- **API:** https://apiservices.partsbase.com/docs/index (requires credentials)
- **Free workaround:** PartStore (https://partstore.partsbase.com) is publicly browsable e-commerce
- **Assessment:** API requires paid access. PartStore pages may be scrapable for some pricing.

### 16. ePlane AI Parts Analyzer — AI Pricing Intelligence
- **URL:** https://www.eplaneai.com/parts-analyzer
- **Cost:** Paid subscription (tiered)
- **Data:** ML-driven pricing, forecasts, stock predictions across 1,000+ locations
- **Assessment:** Most directly relevant commercial product. Competitor to what you're building.

### 17. AVITAS BlueBooks — Aircraft/Engine Valuations
- **URL:** https://www.avitas.com
- **Cost:** $1,600-$2,300/year per publication
- **Assessment:** Whole-aircraft/engine valuations, not individual parts.

---

## Tier 4: SCRAPABLE — Public Pricing Visible

### 18. Aircraft Spruce — GA Parts Retailer
- **URL:** https://www.aircraftspruce.com
- **Robots.txt:** Product pages ALLOWED for scraping
- **Volume:** 60,000+ products with PUBLIC PRICES
- **Limitation:** General Aviation only, retail pricing
- **Assessment:** Best scrapable source for GA parts pricing

### 19. AeroBase Group — Aerospace Hardware
- **URL:** https://aerobase.us
- **Robots.txt:** Very permissive (only disallows /lumber)
- **Data:** NSN numbers, part numbers, CAGE codes, SOME PRICING visible
- **Assessment:** Good for aerospace fasteners/hardware pricing

### 20. AviationPartsSupply.com — AI-Friendly Parts Broker
- **URL:** https://aviationpartssupply.com
- **Robots.txt:** Explicitly ALLOWS AI crawlers (ClaudeBot, GPTBot, PerplexityBot)
- **Has:** llms.txt files with structured data
- **Assessment:** No pricing shown (RFQ-based) but most AI-friendly aviation parts site

### 21. BAS Part Sales — Salvage/Used Parts
- **URL:** https://baspartsales.com
- **Data:** Largest online supplier of aircraft salvage parts, searchable catalog
- **Assessment:** Used/salvage parts pricing data

### 22. Trade-A-Plane — GA Marketplace
- **URL:** https://www.trade-a-plane.com/parts
- **API:** Piloterr offers scraper API (50 free trial requests)
- **Assessment:** GA parts with some pricing

---

## Data Pipeline Architecture (All Free Sources)

```
Layer 1: WHAT'S FLYING (Market Sizing)
├── FAA Aircraft Registry → 370K aircraft, daily refresh
├── BTS Form 41 → airline maintenance spending by type
└── FlightAware API → which aircraft are grounded/active

Layer 2: WHAT BREAKS (Demand Signals)
├── FAA SDRs → 1.7M failure reports by part/aircraft
├── FAA ADs → mandatory replacements with deadlines
├── NTSB data → component failures from accidents
└── NASA ASRS → mechanic-reported parts problems

Layer 3: WHAT IT COSTS (Pricing)
├── USAspending.gov → government transaction prices
├── DLA PUB LOG → government unit prices + NSN cross-refs
├── eBay sold listings → market transaction prices (GA)
├── Aircraft Spruce → retail GA pricing (scrapable)
└── IATA SmartHub → 5 FMV lookups/day (validation)

Layer 4: WHAT'S AVAILABLE (Supply)
├── StockMarket.aero → free open marketplace
├── FAA PMA database → aftermarket alternatives
├── CAGE codes → manufacturer-to-part mapping
└── PartsBase PartStore → browsable e-commerce

Layer 5: INTELLIGENCE (Your Value-Add)
├── Demand forecast: SDR failure rate × fleet size × AD deadlines
├── Price prediction: USAspending trends + eBay actuals + DLA benchmarks
├── Arbitrage detection: PMA price vs OEM price vs USM price
├── Supply risk: Grounded aircraft (parts entering market) vs AD compliance (parts leaving market)
└── Your transaction data: Every deal you broker feeds back in
```

---

## Bottom Line: What You Can Build WITHOUT Any Partnerships

Using only free public data, you can build a system that:

1. **Knows every aircraft in the US** (Registry: make, model, engine, age, owner)
2. **Predicts which parts will be needed** (SDRs: failure rates + ADs: mandatory replacements)
3. **Has pricing benchmarks** (USAspending: government prices + eBay: market prices + DLA: unit prices)
4. **Maps the parts ecosystem** (PMA: alternatives, CAGE: manufacturers, NSN: cross-references)
5. **Detects supply changes** (FlightAware: grounded aircraft = parts supply entering market)

**Sophia's data is a BONUS, not a requirement.** Her 12 months of purchase orders would add real commercial transaction prices (the hardest data to get), but you can launch without it.

**The time-critical operator's data** is also a bonus — his 3,400 data points per shipment add logistics intelligence.

**Paul's tribal knowledge** is a bonus — his teardown economics calibrate the model.

But the FOUNDATION is all free government data. Start there. Add partnership data as relationships develop.
