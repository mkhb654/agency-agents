# AllClear Aerospace & Defense — MK Labs Action Plan

**Date:** 2026-03-15
**Status:** HOT LEAD — CEO + VP met at conference, they want a personalized system
**Location:** Miramar, FL (your backyard)
**Champion:** Raul (VP Repair Station)
**Decision Makers:** Bill Boucek (CEO), GM (unnamed)

---

## What AllClear Actually Wants

From the transcript — Raul's exact words and Bill's reaction:

1. They DO NOT want SalesPatriot or any plug-and-play SaaS
2. They WANT a personalized system built for THEIR business
3. They WANT to own the technology
4. They WANT someone internal/embedded who builds custom solutions
5. Raul said: "SaaS is obliterated. The industry has changed."
6. Bill sat down, listened, and said: "We're gonna be in touch. I'm gonna have people smarter than me talking."
7. Raul said: "I'm not the decision maker but I know this is of interest to them."

**They are buying. The question is the structure and what you show them.**

---

## Competitive Landscape (Corrected)

### SalesPatriot (What They Evaluated)
- **What it is:** YC-backed startup ($6.3M raised, $50M valuation, 13 people)
- **What it ACTUALLY does:** Finds and wins government bids on SAM.gov/DIBBS/NECO. NOT a daily quoting tool.
- **The $800K + $1.1M/year:** Likely inflated by Raul OR includes bundled multi-year deal. SalesPatriot's total revenue is ~$1.9M across ALL customers.
- **Actual SalesPatriot pricing:** Probably $25K-$100K/year based on stage and revenue
- **AllClear is a named SalesPatriot customer** — they may already use it for bid discovery
- **Key: SalesPatriot handles FINDING contracts. Nobody handles EXECUTING them efficiently.**

### SalesEdge by CAMP Systems (The Other Competitor They May Not Know About)
- **What it is:** AI quoting module from the SAME company that makes Quantum Control (their ERP)
- **What it does:** Parses RFQs, searches ILS/PartsBase, syncs with Quantum, AI pricing
- **Pricing:** Enterprise-level, likely $100K-$500K/year for full stack
- **Launched:** October 2024 (new, beta AI pricing tool)
- **Key weakness:** SaaS/cloud. Data leaves their network. Generic for all 1,700 Quantum customers.
- **They may not even know this exists yet**

### What AllClear Said They Want Instead
- **Personalized.** Not plug and play.
- **Their data stays internal.** Government/defense sensitivity.
- **They own it.** No recurring SaaS dependency.
- **Human in the loop.** Raul agreed — models are non-deterministic, need validation.
- **Start small, prove value, then expand.**

---

## What You Build For Them

### The Daily Pain (40 Minutes → 4 Minutes)

```
8:00 AM — Email arrives from military base:
          20 lines of parts needed for F-16 Block 52

TODAY (manual):
├── Rep opens email, reads 20 lines
├── For EACH line (×20):
│   ├── Search Quantum ERP — do we have it?
│   ├── If not → search ILS/PartsBase
│   ├── Check customer history and pricing
│   ├── Calculate margin
│   └── Enter quote in system
├── Format and send quote
└── TOTAL: 40 minutes

WITH YOUR SYSTEM:
├── Rep forwards email to system
├── System parses all 20 lines (2 sec)
├── Checks Quantum inventory via GraphQL (5 sec)
├── Sources out-of-stock items across market (10 sec)
├── Pulls customer history, past pricing, margin targets (3 sec)
├── Generates complete quote with pricing (5 sec)
├── Rep reviews: "Looks good. Send." (60 sec)
└── TOTAL: 4 minutes
```

### On-Prem Architecture (Zero Data Leaves Their Network)

```
AllClear's Server (on-prem, their building):
┌─────────────────────────────────────────────────────┐
│                                                      │
│  LOCAL LLM (no cloud, no frontier models)            │
│  ├── Llama 3.1 70B (open source, Meta, free)         │
│  ├── Fine-tuned with LoRA on AllClear's 30yr data    │
│  ├── Runs on Mac Studio M4 Ultra ($7K) or Dell GPU   │
│  └── ITAR compliant — nothing leaves the building    │
│                                                      │
│  YOUR AI ENGINE                                      │
│  ├── RFQ Parser (email/Excel/PDF → structured data)  │
│  ├── Quantum ERP Connector (GraphQL API)             │
│  ├── Multi-Source Sourcing Engine                     │
│  ├── Pricing Recommender (cost + margin + customer)  │
│  ├── Quote Generator (their format)                  │
│  └── Human-in-the-Loop Review Interface              │
│                                                      │
│  DATA (all local)                                    │
│  ├── Quantum ERP data (already there)                │
│  ├── Government pricing benchmarks (USAspending)     │
│  ├── Demand signals (FAA SDR/AD data)                │
│  ├── Supplier directory (69+ verified companies)     │
│  └── Transaction history (learns from every quote)   │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## The Deal Structure (One Clean Offer)

### Phase 1: Free POC (Get In The Door)
- Visit Miramar. Sit with the quoting team for a day.
- Watch them process RFQs. Understand the exact workflow.
- Build a working prototype in 1-2 weeks.
- Show them: "40 minutes became 4 minutes on YOUR real RFQs."
- **Cost to AllClear: $0.** You eat this. It's the investment that opens the door.

### Phase 2: Custom Build — $150,000 - $175,000
- Full system: RFQ parser + Quantum GraphQL integration + sourcing engine + pricing recommender + quote generator + on-prem deployment
- Local LLM (Llama 3.1 70B), fine-tuned on their data with LoRA
- Human-in-the-loop review interface
- 6-8 weeks to production
- **They own this instance completely. Their data. Their server. Their system.**

### Phase 3: Monthly Retainer — $8,000 - $12,000/month
- 24-month minimum commitment
- Support, updates, model retraining as data grows
- New features as they request them
- You stay embedded in their operation — continuous improvement
- **Guaranteed: $192,000 - $288,000 over 2 years**

### IP Framing (Simple, No Contradictions)
- **To AllClear:** "You own your instance. Everything on your server is yours."
- **To yourself:** You retain the right to build similar systems for non-competing companies (commercial MRO, metals distributors, marine, industrial).
- **Do NOT say:** "I own the IP" or "50/50 on the algorithms." Just don't discuss it unless they ask. If they ask, say: "You own everything I deploy on your servers. I'm free to build for companies outside your space."
- **No equity conversation.** Not at this stage. Deliver first. If they love it and want you deeper in 12 months, THEN it's a conversation — from a position of strength.

### The Math

| Item | Amount |
|------|--------|
| Build fee | $150,000 - $175,000 |
| Retainer (24 months × $10K) | $240,000 |
| **AllClear total (2 years)** | **$390,000 - $415,000** |
| Hardware (Mac Studio, their cost) | ~$7,000 |

### Why This Beats Everything Else

| Option | Year 1 Cost | They Own It? | On-Prem? | Custom? |
|--------|-------------|-------------|----------|---------|
| SalesPatriot | $25-100K/yr | No | No | No |
| SalesEdge (CAMP) | $200-500K+/yr | No | No (cloud) | No (1,700 customers) |
| Internal hire (AI engineer) | $180-250K salary + benefits | Yes but slow | Yes | Yes but 1 person |
| **MK Labs (You)** | **$150-175K + $10K/mo** | **Yes** | **Yes** | **Yes** |

### What NOT To Do
- Do NOT offer $75K. That's negotiating against yourself.
- Do NOT mention equity or revenue share on the discovery call.
- Do NOT say "I own the underlying IP." Say "you own your instance."
- Do NOT present 4 options. Present ONE clear offer.
- Do NOT discuss pricing until after the free POC proves value.

---

## What You Already Have For The Demo / Loom Video

### What's Built and Working RIGHT NOW

| Component | What It Shows | Demo-Ready? |
|-----------|--------------|-------------|
| **Web Dashboard** (localhost:5050) | Full intelligence view — KPIs, top 15 opportunities, demand heatmap, pricing stack, AD demand, suppliers, PMA map, trade corridors | YES |
| **Part Lookup** (lookup_part.py) | Type any part → 8 sources searched → pricing, demand, suppliers, ADs, NSN cross-ref | YES |
| **Deal Calculator** (deal_calculator.py) | Buy $X, sell $Y → instant profit, margin, ROI, GO/NO-GO | YES |
| **Supplier Directory** (supplier_directory.py) | 69 real companies from government contracts, filterable | YES |
| **Government Pricing** ($716M in contracts) | Real transaction prices the DoD paid for parts | YES |
| **AD Demand Monitor** ($604M mandatory demand) | 6 active ADs with fleet counts, deadlines, part requirements | YES |
| **Competitive Intel** (TransDigm/HEICO/FTAI) | Pricing stack showing where margins live | YES |

### Is This Good Enough For A Loom Video?

**YES — but reframe it.** Don't show it as "here's my aviation data tool." Show it as "here's what I built in ONE DAY for the military aftermarket. Imagine what I build in 30 days with YOUR Quantum data."

### Loom Video Script (3-4 Minutes)

```
SLIDE 1 (10 sec): "MK Labs — What We Build For Aerospace & Defense"

SCREEN SHARE — WEB DASHBOARD (30 sec):
"This is a parts intelligence dashboard I built using free government
data. It tracks $601 billion in aviation contracts, monitors $604 million
in mandatory Airworthiness Directive demand, and ranks 15 high-value
components by arbitrage potential. This took me one day to build."

PART LOOKUP DEMO (60 sec):
"Let's say a customer sends you an RFQ for a hydraulic pump."
[Type: hydraulic pump]
"In 4 seconds, the system pulls government transaction prices —
Eaton Aerospace sells these to the DoD at $543K per contract.
It shows demand score — 82 out of 100, high failure rate.
It finds suppliers — Moog, Parker, Eaton are all in the database.
It checks eBay market pricing — $6 to $19,000 range.
And it cross-references NSN numbers for military equivalents.
One query. Eight sources. Four seconds."

DEAL CALCULATOR (30 sec):
"If I source this pump at $8,000 and sell at $25,000..."
[Type: --quick 8000 25000]
"$15,800 profit. 63% margin. 171% ROI. Go."

THE PITCH (60 sec):
"Now imagine this connected to YOUR Quantum ERP via GraphQL.
An email comes in with 20 lines. My system parses it automatically.
Checks YOUR inventory. Sources what you don't have. Prices every line
based on YOUR margin targets and customer history. Your rep reviews
it in 60 seconds and sends.

40 minutes becomes 4 minutes. On your server. Your data never leaves
the building. You own everything I build. No SaaS. No subscription.

I'd love to come to Miramar this week and show you this in person.
Let me know when works."
```

### What To Record

1. Open browser to `http://localhost:5050` — show the dashboard
2. Scroll through each section slowly (15 sec)
3. Use the Part Lookup search box — type "hydraulic pump" — show results
4. Use the Deal Calculator — type buy/sell prices — show result
5. Switch to terminal — run `python lookup_part.py "turbine blade"` — show the full 8-source output
6. End with your face on camera for the pitch (60 sec)

### What To Improve Before Recording

The dashboard and tools work great for the demo. But to make it FEEL like AllClear's system:

**Quick wins (30 min of work):**

1. Change the dashboard title from "MRO Parts Arbitrage Intelligence" to something like "Defense Aftermarket Intelligence Platform — Demo"
2. Add a fake RFQ input that shows: "Paste an RFQ email here" → parses it
3. Show military part numbers (NSN format: 1650-01-234-5678) in the examples

These are cosmetic changes. The underlying system is the same.

---

## Key Contacts

| Name | Role | Relationship | Next Step |
|------|------|-------------|-----------|
| **Raul** | VP Repair Station | Champion — deep AI conversation, briefed his boss, wants to set up meeting | Text Monday AM |
| **Bill Boucek** | CEO | Met at conference, sat down with you, said "we're gonna be in touch" | Present at discovery call |
| **GM** | General Manager | Reports to Bill, above Raul, been briefed | Meet at discovery call |

---

## Competitive Intelligence (Corrected)

### SalesPatriot — What It Actually Is
- **YC W25 startup**, $6.3M raised, $50M valuation, ~13 employees
- **Does:** Finds government solicitations on SAM.gov/DIBBS/NECO. AI matches to company capabilities. Automates vendor outreach for bidding. One-click bid submission to DLA.
- **Does NOT do:** Daily RFQ quoting, Quantum ERP integration, ILS/PartsBase searching
- **Actual price:** Likely $25K-$100K/year (not $800K+$1.1M Raul quoted)
- **AllClear is a named customer** — they may already use it for bid discovery
- **Founders:** Nelson Ray (CEO, ex-Aurora Defense), Benjamin Rhodes-Kropf (CTO, MIT), Maciej Szymczyk (CAI, Human Brain Project)
- **Named customers:** Jamaica Bearings Group, AllClear, STATZ, S3 AeroDefense, Air Industries Group

### SalesEdge by CAMP Systems — The Hidden Competitor
- **Owned by CAMP Systems** — same company that owns Quantum Control
- **Launched:** October 2024
- **Does:** RFQ consolidation from ILS/PartsBase/email, real-time Quantum sync, AI pricing (beta)
- **AllClear may not know this exists** — it's new
- **Weakness:** SaaS/cloud, generic (same for 1,700 customers), expensive
- **Threat:** CAMP could pitch AllClear to just "upgrade" their Quantum system

### Your Positioning vs Both
- **vs SalesPatriot:** Not competing. Different problem. SalesPatriot finds bids. You execute them.
- **vs SalesEdge:** Competing directly. You win on: on-prem (ITAR), customization, ownership, price, market intelligence they don't have.
- **Key message:** "They don't want plug and play. They want THEIR system. That's what we build."

### What You Have That Neither Competitor Offers
- $716M in government transaction pricing data
- 15 components ranked by demand with failure rate analysis
- $604M in AD-driven mandatory demand tracking
- 69 suppliers from real government contracts
- TransDigm/HEICO/FTAI competitive pricing intelligence
- 6 geographic arbitrage corridors
- PMA disruption mapping ($11.4B market)
- Engine shop visit economics (CFM56 teardown yields $2-5M in USM)
- Aircraft boneyard/storage tracking
- On-prem local LLM architecture (ITAR compliant)

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| They discover SalesEdge from CAMP/Quantum and just "upgrade" | Get in BEFORE they learn about it. Your free POC proves value while SalesEdge is still beta. |
| They already use SalesPatriot and are happy | Position as complementary. "SalesPatriot finds contracts. I execute them." |
| CEO wants proven vendor, not startup | Show the running system. Reference EasyFlyers (5 years), Wells Fargo orchestrator work, Harvard iLabs. |
| They push back on pricing | Offer Approach A (reduced build + revenue share). Zero risk to them. |
| Quantum GraphQL integration is harder than expected | Phase it. Start with standalone (upload CSV/email). Add Quantum integration in Phase 2. |
| PE firm (Odyssey) blocks equity deal | Fall back to Approach C (IP licensing) or Approach D (pure build). |

---

## Monday Sequence

**7:00 AM** — Record Loom video (3-4 min, script above)

**8:00 AM** — Text Raul:
```
Hey Raul, it's Roger from MK Labs. Great conversation at the
conference. I recorded a quick video showing what I built for
military aftermarket intelligence — 8 data sources, government
pricing, demand forecasting, all running locally. Would love
to show you and the team in person. Can I come to Miramar
this week?

[Loom link]
```

**8:30 AM** — If Raul responds, schedule the visit.

**9:00 AM** — Move to next contacts (Ryan, Sophia, etc.)

---

## Revenue Projection (Realistic)

| Source | Year 1 | Year 2 |
|--------|--------|--------|
| AllClear build | $150-175K | — |
| AllClear retainer ($10K/mo) | $120K (12 months) | $120K |
| AMI Metals / Ryan (same engine) | $100-150K build | $60-120K retainer |
| 2-3 more MRO clients from pipeline | $200-400K | $200-400K |
| **Total** | **$570K - $845K** | **$380K - $640K** |

**18-24 month total: $950K - $1.5M from one product line.**

AllClear is the anchor client. They fund the build. They become the reference. Every client after that is faster and cheaper because the core engine already exists.
