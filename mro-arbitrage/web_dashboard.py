"""
web_dashboard.py — MRO Arbitrage Intelligence Command Center

Run this and open http://localhost:5050 in your browser.

USAGE:
    python web_dashboard.py
"""

import json
import subprocess
import sys
from pathlib import Path
from flask import Flask, render_template_string, request

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / "data"


def load_json(filename):
    path = DATA_DIR / filename
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MK Labs — Aerospace Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg-primary: #06080c;
  --bg-secondary: #0c1018;
  --bg-card: #111720;
  --bg-hover: #161d28;
  --border: #1a2332;
  --border-active: #2a3a4e;
  --text-primary: #e8edf3;
  --text-secondary: #7a8a9e;
  --text-muted: #4a5568;
  --accent: #00d4aa;
  --accent-dim: rgba(0,212,170,0.12);
  --profit: #00d4aa;
  --loss: #ff4757;
  --warning: #ffa502;
  --info: #3b82f6;
  --font-display: 'DM Sans', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }
html { font-size: 14px; }

body {
  font-family: var(--font-display);
  background: var(--bg-primary);
  color: var(--text-primary);
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ---- SIDEBAR ---- */
.sidebar {
  width: 220px;
  min-width: 220px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow-y: auto;
}

.sidebar-logo {
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--border);
}

.sidebar-logo h1 {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: -0.5px;
}

.sidebar-logo span {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  letter-spacing: 2px;
  text-transform: uppercase;
  display: block;
  margin-top: 4px;
}

.nav-section {
  padding: 16px 12px 8px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  font-family: var(--font-mono);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 16px;
  margin: 1px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: all 0.15s;
  user-select: none;
}

.nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.nav-item.active { background: var(--accent-dim); color: var(--accent); }
.nav-item .icon { font-size: 16px; width: 20px; text-align: center; }
.nav-item .count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-primary);
  padding: 1px 6px;
  border-radius: 4px;
}

.sidebar-footer {
  margin-top: auto;
  padding: 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.status-dot {
  display: inline-block;
  width: 6px; height: 6px;
  background: var(--accent);
  border-radius: 50%;
  margin-right: 6px;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ---- MAIN CONTENT ---- */
.main {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 28px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  min-height: 54px;
}

.topbar-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.topbar-meta {
  display: flex;
  gap: 20px;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.content {
  flex: 1;
  padding: 24px 28px;
  overflow-y: auto;
}

/* ---- PAGE: OVERVIEW ---- */
.page { display: none; }
.page.active { display: block; }

/* KPI Strip */
.kpi-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 28px;
}

.kpi-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 16px;
  position: relative;
  overflow: hidden;
}

.kpi-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 2px;
}

.kpi-card.green::before { background: var(--profit); }
.kpi-card.yellow::before { background: var(--warning); }
.kpi-card.blue::before { background: var(--info); }
.kpi-card.red::before { background: var(--loss); }

.kpi-value {
  font-family: var(--font-mono);
  font-size: 26px;
  font-weight: 700;
  line-height: 1;
}

.kpi-value.green { color: var(--profit); }
.kpi-value.yellow { color: var(--warning); }
.kpi-value.blue { color: var(--info); }

.kpi-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

/* Grid Layout */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 24px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; margin-bottom: 24px; }

/* Cards */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}

.card-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 1px;
  font-family: var(--font-mono);
}

.card-body { padding: 16px 18px; }

/* Tables */
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left;
  padding: 10px 14px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  font-family: var(--font-mono);
  border-bottom: 1px solid var(--border);
}
td {
  padding: 10px 14px;
  font-size: 13px;
  border-bottom: 1px solid rgba(26,35,50,0.5);
}
tr:hover td { background: var(--bg-hover); }

.text-profit { color: var(--profit); font-weight: 600; }
.text-warning { color: var(--warning); }
.text-loss { color: var(--loss); }
.text-info { color: var(--info); }
.text-muted { color: var(--text-muted); }
.text-mono { font-family: var(--font-mono); }
.text-bold { font-weight: 600; }
.text-sm { font-size: 12px; }

/* Badges */
.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  font-family: var(--font-mono);
  letter-spacing: 0.5px;
}
.badge-profit { background: rgba(0,212,170,0.12); color: var(--profit); }
.badge-warning { background: rgba(255,165,2,0.12); color: var(--warning); }
.badge-danger { background: rgba(255,71,87,0.12); color: var(--loss); }
.badge-info { background: rgba(59,130,246,0.12); color: var(--info); }

/* Progress Bar */
.progress { height: 6px; background: var(--bg-primary); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--accent), var(--info)); transition: width 0.6s ease; }

/* Search */
.search-wrap {
  position: relative;
  margin-bottom: 20px;
}

.search-input {
  width: 100%;
  padding: 14px 18px 14px 44px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-display);
  transition: border-color 0.2s;
}

.search-input:focus { outline: none; border-color: var(--accent); }
.search-input::placeholder { color: var(--text-muted); }

.search-icon {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  font-size: 16px;
}

#lookup-results {
  margin-top: 14px;
  padding: 18px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  max-height: 500px;
  overflow-y: auto;
  display: none;
  color: var(--text-secondary);
}

/* Deal Calculator */
.calc-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.calc-label {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.calc-input {
  width: 130px;
  padding: 10px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 14px;
}

.calc-input:focus { outline: none; border-color: var(--accent); }

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-mono);
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 1px;
  transition: all 0.15s;
}

.btn-accent { background: var(--accent); color: var(--bg-primary); }
.btn-accent:hover { background: #00eabb; }
.btn-blue { background: var(--info); color: white; }
.btn-blue:hover { background: #5a9cf6; }

#deal-result {
  margin-top: 16px;
  padding: 16px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: none;
}

/* Demand Bar */
.demand-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 0;
}

.demand-score {
  width: 36px;
  text-align: right;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 13px;
  color: var(--accent);
}

.demand-bar { flex: 1; }
.demand-name { width: 180px; font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Corridor */
.corridor-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 11px 0;
  border-bottom: 1px solid rgba(26,35,50,0.4);
}
.corridor-row:last-child { border: none; }
.corridor-route { color: var(--text-primary); font-weight: 500; font-size: 13px; }
.corridor-margin { color: var(--profit); font-family: var(--font-mono); font-size: 13px; font-weight: 600; }

/* Pricing Stack */
.stack {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 2;
}

.stack-ceiling { color: var(--loss); font-weight: 600; }
.stack-band {
  border: 1px dashed var(--accent);
  padding: 10px 14px;
  margin: 10px 0;
  border-radius: 6px;
  text-align: center;
  color: var(--accent);
  font-weight: 600;
  background: var(--accent-dim);
}
.stack-floor { color: var(--warning); }
.stack-scrap { color: var(--text-muted); }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-active); }

/* Responsive */
@media (max-width: 1200px) {
  .kpi-strip { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div class="sidebar">
  <div class="sidebar-logo">
    <h1>MK LABS</h1>
    <span>Aerospace Intel</span>
  </div>

  <div class="nav-section">Intelligence</div>
  <div class="nav-item active" onclick="showPage('overview')">
    <span class="icon">&#9632;</span> Overview
  </div>
  <div class="nav-item" onclick="showPage('opportunities')">
    <span class="icon">&#9650;</span> Opportunities <span class="count">{{ scorecard|length }}</span>
  </div>
  <div class="nav-item" onclick="showPage('demand')">
    <span class="icon">&#9608;</span> Demand Signals
  </div>
  <div class="nav-item" onclick="showPage('ads')">
    <span class="icon">&#9888;</span> AD Alerts <span class="count">{{ ads|length }}</span>
  </div>

  <div class="nav-section">Tools</div>
  <div class="nav-item" onclick="showPage('lookup')">
    <span class="icon">&#8981;</span> Part Lookup
  </div>
  <div class="nav-item" onclick="showPage('calculator')">
    <span class="icon">&#36;</span> Deal Calculator
  </div>
  <div class="nav-item" onclick="showPage('suppliers')">
    <span class="icon">&#9733;</span> Suppliers <span class="count">{{ supplier_count }}</span>
  </div>

  <div class="nav-section">Market</div>
  <div class="nav-item" onclick="showPage('corridors')">
    <span class="icon">&#8644;</span> Trade Corridors
  </div>
  <div class="nav-item" onclick="showPage('pma')">
    <span class="icon">&#9881;</span> PMA Intel
  </div>
  <div class="nav-item" onclick="showPage('pricing')">
    <span class="icon">&#8942;</span> Pricing Stack
  </div>

  <div class="sidebar-footer">
    <span class="status-dot"></span>{{ data_sources }} sources live
  </div>
</div>

<!-- MAIN -->
<div class="main">
  <div class="topbar">
    <div class="topbar-title" id="page-title">Overview</div>
    <div class="topbar-meta">
      <span>{{ total_records }} records</span>
      <span>Last refresh: now</span>
    </div>
  </div>

  <div class="content">

    <!-- PAGE: OVERVIEW -->
    <div class="page active" id="page-overview">
      <div class="kpi-strip">
        <div class="kpi-card green">
          <div class="kpi-value green">${{ "{:,.0f}".format(total_contract_value / 1e6) }}M</div>
          <div class="kpi-label">Gov Contracts Tracked</div>
        </div>
        <div class="kpi-card yellow">
          <div class="kpi-value yellow">${{ "{:,.0f}".format(ad_demand / 1e6) }}M</div>
          <div class="kpi-label">AD Mandatory Demand</div>
        </div>
        <div class="kpi-card blue">
          <div class="kpi-value blue">{{ supplier_count }}</div>
          <div class="kpi-label">Suppliers Cataloged</div>
        </div>
        <div class="kpi-card green">
          <div class="kpi-value green">{{ component_count }}</div>
          <div class="kpi-label">Components Scored</div>
        </div>
        <div class="kpi-card blue">
          <div class="kpi-value blue">6</div>
          <div class="kpi-label">Arbitrage Strategies</div>
        </div>
      </div>

      <div class="grid-2">
        <!-- Top 5 Opportunities -->
        <div class="card">
          <div class="card-header"><div class="card-title">Top Opportunities</div></div>
          <table>
            <thead><tr><th>#</th><th>Component</th><th>Price</th><th>Profit</th><th>Strategy</th></tr></thead>
            <tbody>
            {% for s in scorecard[:7] %}
            <tr>
              <td class="text-mono text-muted">{{ loop.index }}</td>
              <td class="text-bold">{{ s.component[:28] }}</td>
              <td class="text-mono">${{ "{:,.0f}".format(s.mid_price) }}</td>
              <td class="text-mono text-profit">${{ "{:,.0f}".format(s.estimated_profit_per_unit) }}</td>
              <td><span class="badge badge-info">{{ s.best_arbitrage_type.replace('_',' ').title()[:16] }}</span></td>
            </tr>
            {% endfor %}
            </tbody>
          </table>
        </div>

        <!-- Demand Heatmap -->
        <div class="card">
          <div class="card-header"><div class="card-title">Demand Heatmap</div></div>
          <div class="card-body">
            {% for s in demand_signals[:8] %}
            <div class="demand-row">
              <div class="demand-score">{{ s.demand_score }}</div>
              <div class="demand-bar"><div class="progress"><div class="progress-fill" style="width:{{ s.demand_score }}%"></div></div></div>
              <div class="demand-name">{{ s.component }}</div>
            </div>
            {% endfor %}
          </div>
        </div>
      </div>

      <div class="grid-2">
        <!-- AD Alerts -->
        <div class="card">
          <div class="card-header"><div class="card-title">Active AD Alerts</div><div class="badge badge-warning">{{ ads|length }} Active</div></div>
          <table>
            <thead><tr><th>AD</th><th>Fleet</th><th>$/Unit</th><th>Market Impact</th></tr></thead>
            <tbody>
            {% for ad in ads[:5] %}
            <tr>
              <td class="text-mono text-sm">{{ ad.ad_number }}</td>
              <td class="text-mono">{{ "{:,}".format(ad.fleet_affected) }}</td>
              <td class="text-mono">${{ "{:,.0f}".format(ad.estimated_part_cost_per_unit) }}</td>
              <td class="text-mono text-warning">${{ "{:,.0f}".format(ad.total_market_impact) }}</td>
            </tr>
            {% endfor %}
            </tbody>
          </table>
        </div>

        <!-- Trade Corridors -->
        <div class="card">
          <div class="card-header"><div class="card-title">Trade Corridors</div></div>
          <div class="card-body">
            {% for c in corridors[:5] %}
            <div class="corridor-row">
              <span class="corridor-route">{{ c.corridor }}</span>
              <span class="corridor-margin">{{ c.margin }}</span>
            </div>
            {% endfor %}
          </div>
        </div>
      </div>
    </div>

    <!-- PAGE: OPPORTUNITIES -->
    <div class="page" id="page-opportunities">
      <div class="card">
        <div class="card-header"><div class="card-title">All Arbitrage Opportunities — Ranked by Composite Score</div></div>
        <table>
          <thead><tr><th>#</th><th>Component</th><th>Score</th><th>Market Price</th><th>Est. Profit</th><th>Strategy</th><th>Failure Rate</th><th>Aircraft</th></tr></thead>
          <tbody>
          {% for s in scorecard %}
          <tr>
            <td class="text-mono text-muted">{{ loop.index }}</td>
            <td class="text-bold">{{ s.component }}</td>
            <td><div style="display:flex;align-items:center;gap:8px;"><div class="progress" style="width:80px;"><div class="progress-fill" style="width:{{ s.composite_score }}%"></div></div><span class="text-mono text-sm">{{ s.composite_score }}</span></div></td>
            <td class="text-mono">${{ "{:,.0f}".format(s.mid_price) }}</td>
            <td class="text-mono text-profit">${{ "{:,.0f}".format(s.estimated_profit_per_unit) }}</td>
            <td><span class="badge badge-info">{{ s.best_arbitrage_type.replace('_',' ').title() }}</span></td>
            <td><span class="badge {% if s.failure_rate in ['HIGH','VERY HIGH'] %}badge-danger{% else %}badge-warning{% endif %}">{{ s.failure_rate }}</span></td>
            <td class="text-sm text-muted">{{ s.aircraft_types[:3]|join(', ') if s.aircraft_types else '' }}</td>
          </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <!-- PAGE: DEMAND -->
    <div class="page" id="page-demand">
      <div class="card">
        <div class="card-header"><div class="card-title">Component Demand Signals — Failure Rate Analysis</div></div>
        <div class="card-body">
          {% for s in demand_signals %}
          <div class="demand-row" style="padding:10px 0;">
            <div class="demand-score" style="width:44px;font-size:16px;">{{ s.demand_score }}</div>
            <div class="demand-bar"><div class="progress" style="height:8px;"><div class="progress-fill" style="width:{{ s.demand_score }}%"></div></div></div>
            <div style="width:260px;">
              <div style="font-weight:600;font-size:13px;">{{ s.component }}</div>
              <div class="text-sm text-muted">{{ s.failure_rate }} failure | {{ s.replacement_frequency }}</div>
            </div>
            <div class="text-mono text-sm" style="width:160px;">{{ s.estimated_unit_price }}</div>
          </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- PAGE: ADS -->
    <div class="page" id="page-ads">
      <div style="margin-bottom:20px;">
        <span class="kpi-value yellow" style="font-size:22px;">${{ "{:,.0f}".format(ad_demand) }}</span>
        <span class="text-muted" style="margin-left:8px;">total AD-driven mandatory demand</span>
      </div>
      <div class="card">
        <table>
          <thead><tr><th>AD Number</th><th>Title</th><th>Aircraft</th><th>Fleet</th><th>$/Unit</th><th>Total Impact</th><th>Deadline</th></tr></thead>
          <tbody>
          {% for ad in ads %}
          <tr>
            <td class="text-mono text-bold">{{ ad.ad_number }}</td>
            <td class="text-sm">{{ ad.title[:50] }}</td>
            <td class="text-sm text-muted">{{ ad.affected_aircraft[:30] }}</td>
            <td class="text-mono">{{ "{:,}".format(ad.fleet_affected) }}</td>
            <td class="text-mono">${{ "{:,.0f}".format(ad.estimated_part_cost_per_unit) }}</td>
            <td class="text-mono text-warning">${{ "{:,.0f}".format(ad.total_market_impact) }}</td>
            <td class="text-sm text-muted">{{ ad.compliance_deadline[:30] }}</td>
          </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <!-- PAGE: LOOKUP -->
    <div class="page" id="page-lookup">
      <div class="search-wrap">
        <span class="search-icon">&#8981;</span>
        <form onsubmit="lookupPart(event)">
          <input type="text" class="search-input" id="part-query" placeholder="Search any part — turbine blade, hydraulic pump, APU, landing gear...">
        </form>
      </div>
      <div id="lookup-results"></div>
    </div>

    <!-- PAGE: CALCULATOR -->
    <div class="page" id="page-calculator">
      <div class="card">
        <div class="card-header"><div class="card-title">Deal P&L Calculator</div></div>
        <div class="card-body">
          <div class="calc-row">
            <span class="calc-label">Buy $</span>
            <input type="number" id="buy-price" class="calc-input" placeholder="10,000">
            <span class="calc-label">Sell $</span>
            <input type="number" id="sell-price" class="calc-input" placeholder="25,000">
            <span class="calc-label">Qty</span>
            <input type="number" id="qty" class="calc-input" style="width:80px;" value="1">
            <button class="btn btn-accent" onclick="calcDeal()">Calculate</button>
          </div>
          <div id="deal-result"></div>
        </div>
      </div>
    </div>

    <!-- PAGE: SUPPLIERS -->
    <div class="page" id="page-suppliers">
      <div class="card">
        <div class="card-header"><div class="card-title">Government Contract Suppliers — Sourcing Partners</div></div>
        <table>
          <thead><tr><th>Company</th><th>Contract Value</th><th>Contracts</th><th>Parts</th></tr></thead>
          <tbody>
          {% for name, data in suppliers[:20] %}
          <tr>
            <td class="text-bold">{{ name[:45] }}</td>
            <td class="text-mono text-profit">${{ "{:,.0f}".format(data.total_value) }}</td>
            <td class="text-mono">{{ data.contract_count }}</td>
            <td class="text-sm text-muted">{{ data.parts[:55] }}</td>
          </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <!-- PAGE: CORRIDORS -->
    <div class="page" id="page-corridors">
      <div class="card">
        <div class="card-header"><div class="card-title">Geographic Arbitrage Corridors</div></div>
        <div class="card-body">
          {% for c in corridors %}
          <div style="padding:16px 0;border-bottom:1px solid var(--border);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-weight:600;font-size:15px;">{{ c.corridor }}</span>
              <span class="badge badge-profit" style="font-size:12px;">{{ c.margin }}</span>
            </div>
            <div class="text-sm text-muted" style="margin-top:6px;">{{ c.opportunity[:120] }}</div>
            <div style="margin-top:6px;"><span class="text-sm">Volume:</span> <span class="text-sm text-info">{{ c.volume }}</span> &nbsp; <span class="text-sm">Parts:</span> <span class="text-sm text-muted">{{ c.parts }}</span></div>
          </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- PAGE: PMA -->
    <div class="page" id="page-pma">
      {% if pma %}
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><div class="card-title">PMA Market Overview</div></div>
          <div class="card-body">
            {% if pma.market_overview is mapping %}
            <div class="kpi-value green" style="font-size:28px;">${{ pma.market_overview.get('global_pma_market_size_2024', '?') }}</div>
            <div class="kpi-label">Global PMA Market (2024)</div>
            <div style="margin-top:16px;font-size:13px;line-height:2;color:var(--text-secondary);">
              <div>US Approvals (2023): <span class="text-bold">{{ pma.market_overview.get('us_pma_approvals_2023', '?') }}</span></div>
              <div>Fleet using PMA: <span class="text-bold">{{ pma.market_overview.get('aircraft_using_pma_parts_2023', '?') }}</span></div>
              <div>Active PMA parts globally: <span class="text-bold">{{ pma.market_overview.get('active_pma_part_numbers_globally', '?') }}</span></div>
            </div>
            {% endif %}
          </div>
        </div>
        <div class="card">
          <div class="card-header"><div class="card-title">Actionable PMA Opportunities</div></div>
          <div class="card-body">
            {% if pma.actionable_arbitrage_opportunities is mapping %}
              {% for key, opp in pma.actionable_arbitrage_opportunities.items() %}
                {% if opp is mapping %}
                <div style="padding:10px 0;border-bottom:1px solid var(--border);">
                  <div class="text-bold" style="font-size:13px;">{{ opp.get('description', key)[:65] }}</div>
                  {% if opp.get('savings') %}<div class="text-profit text-sm" style="margin-top:4px;">{{ opp.savings }}</div>{% endif %}
                  {% if opp.get('action') %}<div class="text-muted text-sm" style="margin-top:4px;">{{ opp.action[:80] }}</div>{% endif %}
                </div>
                {% endif %}
              {% endfor %}
            {% endif %}
          </div>
        </div>
      </div>
      {% endif %}
    </div>

    <!-- PAGE: PRICING STACK -->
    <div class="page" id="page-pricing">
      <div class="card" style="max-width:600px;">
        <div class="card-header"><div class="card-title">Market Pricing Stack — Your Arbitrage Band</div></div>
        <div class="card-body">
          <div class="stack">
            <div class="stack-ceiling">CEILING: TransDigm sole-source (50-60% EBITDA)</div>
            <div class="text-muted text-sm">Overpriced — target these parts with PMA/USM alternatives</div>
            <div class="stack-band">YOUR BAND: Buy PMA/USM, sell below OEM — 20-40% margin</div>
            <div class="stack-floor">FLOOR: HEICO PMA pricing (26% EBITDA, 30-60% below OEM)</div>
            <div class="stack-scrap" style="margin-top:8px;">SCRAP: Uncertified parts (eBay $15 turbine blades)</div>
          </div>
        </div>
      </div>
    </div>

  </div>
</div>

<script>
function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  event.currentTarget.classList.add('active');
  const titles = {
    overview:'Overview', opportunities:'Arbitrage Opportunities', demand:'Demand Signals',
    ads:'Airworthiness Directive Alerts', lookup:'Part Intelligence Lookup',
    calculator:'Deal P&L Calculator', suppliers:'Supplier Directory',
    corridors:'Geographic Trade Corridors', pma:'PMA Disruption Intelligence',
    pricing:'Market Pricing Stack'
  };
  document.getElementById('page-title').textContent = titles[id] || id;
}

function lookupPart(e) {
  e.preventDefault();
  const q = document.getElementById('part-query').value;
  if (!q) return;
  const el = document.getElementById('lookup-results');
  el.style.display = 'block';
  el.textContent = 'Searching all sources for "' + q + '"...';
  fetch('/api/lookup?q=' + encodeURIComponent(q))
    .then(r => r.text())
    .then(t => { el.textContent = t; })
    .catch(err => { el.textContent = 'Error: ' + err; });
}

function calcDeal() {
  const buy = parseFloat(document.getElementById('buy-price').value) || 0;
  const sell = parseFloat(document.getElementById('sell-price').value) || 0;
  const qty = parseInt(document.getElementById('qty').value) || 1;
  const costs = 500 + (sell * qty * 0.02) + 200;
  const net = (sell * qty) - (buy * qty) - costs;
  const margin = sell > 0 ? (net / (sell * qty) * 100) : 0;
  const roi = (buy * qty + costs) > 0 ? (net / (buy * qty + costs) * 100) : 0;
  const verdict = margin >= 20 ? 'STRONG GO' : margin >= 10 ? 'GO' : margin >= 5 ? 'MARGINAL' : net > 0 ? 'THIN' : 'NO GO';
  const cls = net > 0 ? 'profit' : 'loss';
  const el = document.getElementById('deal-result');
  el.style.display = 'block';
  el.innerHTML = `
    <div style="display:flex;gap:32px;align-items:center;flex-wrap:wrap;">
      <div>
        <div class="kpi-label">Net Profit</div>
        <div class="kpi-value ${cls}" style="font-size:28px;">$${net.toLocaleString(undefined,{maximumFractionDigits:0})}</div>
      </div>
      <div>
        <div class="kpi-label">Margin</div>
        <div class="text-mono" style="font-size:20px;color:var(--text-primary);">${margin.toFixed(1)}%</div>
      </div>
      <div>
        <div class="kpi-label">ROI</div>
        <div class="text-mono" style="font-size:20px;color:var(--text-primary);">${roi.toFixed(0)}%</div>
      </div>
      <div>
        <span class="badge badge-${cls}" style="font-size:13px;padding:6px 14px;">${verdict}</span>
      </div>
    </div>
    <div class="text-muted text-sm" style="margin-top:12px;">
      Revenue: $${(sell*qty).toLocaleString()} | Cost: $${(buy*qty).toLocaleString()} | Fees: $${costs.toLocaleString(undefined,{maximumFractionDigits:0})} (ship + ins + overhead)
    </div>
  `;
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    scorecard = load_json("arbitrage_scorecard.json") or []
    demand_signals = load_json("demand_signals.json") or []
    ad_data = load_json("ad_demand_analysis.json") or {}
    awards = load_json("usaspending_aviation_awards.json") or []
    supplier_dir = load_json("supplier_directory.json") or {}
    trade_flows = load_json("trade_flow_analysis.json") or {}
    pma = load_json("pma_landscape_research.json")

    data_files = list(DATA_DIR.glob("*.json"))
    data_sources = len(data_files)
    total_records = sum(
        len(load_json(f.name) or []) if isinstance(load_json(f.name), list) else 1
        for f in data_files
    )

    total_contract_value = sum(a.get("Award Amount", 0) or 0 for a in awards)
    ad_demand = ad_data.get("total_market_impact", 0)
    ads = ad_data.get("ads", [])
    ads.sort(key=lambda x: x.get("total_market_impact", 0), reverse=True)

    suppliers_list = []
    for name, data in supplier_dir.items():
        if isinstance(data, dict):
            suppliers_list.append((name, type('', (), {
                'total_value': data.get('total_value', 0),
                'contract_count': data.get('contract_count', 0),
                'parts': ', '.join(data.get('parts', [])[:3]),
            })))
    suppliers_list.sort(key=lambda x: x[1].total_value, reverse=True)

    corridors = trade_flows.get("arbitrage_corridors", [])

    return render_template_string(
        HTML_TEMPLATE,
        scorecard=scorecard,
        demand_signals=demand_signals,
        ads=ads,
        ad_demand=ad_demand,
        total_contract_value=total_contract_value,
        supplier_count=len(supplier_dir),
        component_count=len(scorecard),
        data_sources=data_sources,
        total_records=total_records,
        suppliers=suppliers_list,
        corridors=corridors,
        pma=pma,
    )


@app.route("/api/lookup")
def api_lookup():
    query = request.args.get("q", "")
    if not query:
        return "Enter a part name or number", 400
    try:
        script_dir = Path(__file__).parent
        result = subprocess.run(
            [sys.executable, str(script_dir / "lookup_part.py"), query],
            capture_output=True, text=True, timeout=60,
            cwd=str(script_dir),
        )
        return result.stdout or result.stderr or "No results"
    except subprocess.TimeoutExpired:
        return "Search timed out. Try a simpler query."
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  MK LABS — AEROSPACE INTELLIGENCE")
    print("  Open http://localhost:5050 in your browser")
    print("=" * 50 + "\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
