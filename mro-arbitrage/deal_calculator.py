"""
deal_calculator.py — Calculate exact P&L for a specific parts deal

When you find an opportunity (Paul has a part, Sophia needs it),
this tool calculates your exact profit after ALL costs.

Inputs:
- Buy price (what you pay the supplier)
- Sell price (what you charge the MRO)
- Part weight/dimensions (for shipping cost)
- Condition (as-is, serviceable, overhauled, new)
- Whether overhaul is needed
- Urgency (routine vs AOG)

Outputs:
- Gross margin
- Net profit after logistics, certification, overhead
- ROI percentage
- Break-even analysis
- Deal score (go/no-go recommendation)

USAGE:
    python deal_calculator.py
    # Interactive mode — walks you through each field
"""

import sys
from datetime import datetime


def get_input(prompt, default=None, type_fn=str):
    """Get user input with default value."""
    default_str = f" [{default}]" if default is not None else ""
    raw = input(f"  {prompt}{default_str}: ").strip()
    if not raw and default is not None:
        return type_fn(default) if type_fn != str else default
    try:
        return type_fn(raw)
    except (ValueError, TypeError):
        return default


def calculate_deal():
    """Interactive deal P&L calculator."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + "  MRO PARTS DEAL CALCULATOR".center(68) + "║")
    print("║" + "  Calculate exact profit before committing".center(68) + "║")
    print("╚" + "═" * 68 + "╝")

    # ---- Part Info ----
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  PART INFORMATION':^68}│")
    print(f"└{'─' * 68}┘")

    part_name = get_input("Part name/description", "CFM56-7B Turbine Blade")
    part_number = get_input("Part number (if known)", "N/A")
    quantity = get_input("Quantity", 1, int)

    condition_options = {
        "1": ("As-Removed (AR)", 0.4),     # 40% of new price
        "2": ("Serviceable (SV)", 0.6),     # 60% of new price
        "3": ("Overhauled (OH)", 0.8),      # 80% of new price
        "4": ("New (NE)", 1.0),             # Full price
        "5": ("Repairable (RE)", 0.2),      # 20% — needs work
    }

    print("\n  Part condition:")
    for k, (name, _) in condition_options.items():
        print(f"    {k}. {name}")
    cond_choice = get_input("Select condition", "2")
    condition_name, condition_factor = condition_options.get(cond_choice, ("Serviceable", 0.6))

    # ---- Pricing ----
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  PRICING':^68}│")
    print(f"└{'─' * 68}┘")

    buy_price = get_input("Buy price (per unit, $)", 10000, float)
    sell_price = get_input("Sell price (per unit, $)", 15000, float)

    urgency_options = {
        "1": ("Routine (2-4 weeks)", 1.0),
        "2": ("Urgent (1 week)", 1.15),
        "3": ("AOG Critical (24-48 hours)", 1.5),
    }

    print("\n  Urgency level (affects logistics cost and sell price):")
    for k, (name, _) in urgency_options.items():
        print(f"    {k}. {name}")
    urg_choice = get_input("Select urgency", "1")
    urgency_name, urgency_mult = urgency_options.get(urg_choice, ("Routine", 1.0))

    # ---- Costs ----
    print(f"\n┌{'─' * 68}┐")
    print(f"│{'  COSTS':^68}│")
    print(f"└{'─' * 68}┘")

    # Logistics cost
    weight_lbs = get_input("Part weight (lbs)", 50, float)

    # Estimate shipping based on weight and urgency
    if weight_lbs <= 50:
        base_shipping = 150
    elif weight_lbs <= 150:
        base_shipping = 400
    elif weight_lbs <= 500:
        base_shipping = 1200
    elif weight_lbs <= 2000:
        base_shipping = 3500
    else:
        base_shipping = 8000

    shipping_cost = base_shipping * urgency_mult
    shipping_override = get_input(f"Shipping cost (estimated ${shipping_cost:.0f})", shipping_cost, float)
    shipping_cost = shipping_override

    # Certification / documentation
    needs_overhaul = get_input("Needs overhaul before sale? (y/n)", "n")
    overhaul_cost = 0
    if needs_overhaul.lower() == "y":
        overhaul_cost = get_input("Overhaul cost ($)", buy_price * 0.3, float)

    # 8130-3 tag / documentation
    needs_cert = get_input("Needs certification/8130-3 tag? (y/n)", "n")
    cert_cost = 0
    if needs_cert.lower() == "y":
        cert_cost = get_input("Certification cost ($)", 500, float)

    # Insurance
    insurance_rate = 0.02  # 2% of transaction value
    insurance_cost = sell_price * quantity * insurance_rate

    # Commission / finder's fee
    commission_pct = get_input("Commission/finder's fee (%)", 0, float) / 100
    commission_cost = sell_price * quantity * commission_pct

    # Overhead (your time, phone, travel)
    overhead = get_input("Overhead/admin cost ($)", 200, float)

    # ---- CALCULATIONS ----
    total_buy = buy_price * quantity
    total_sell = sell_price * quantity
    total_costs = (
        shipping_cost +
        overhaul_cost * quantity +
        cert_cost * quantity +
        insurance_cost +
        commission_cost +
        overhead
    )

    gross_profit = total_sell - total_buy
    net_profit = gross_profit - total_costs
    gross_margin_pct = (gross_profit / total_sell * 100) if total_sell > 0 else 0
    net_margin_pct = (net_profit / total_sell * 100) if total_sell > 0 else 0
    roi = (net_profit / (total_buy + total_costs) * 100) if (total_buy + total_costs) > 0 else 0

    # Break-even sell price
    breakeven = total_buy + total_costs
    breakeven_per_unit = breakeven / quantity if quantity > 0 else 0

    # Deal score
    if net_margin_pct >= 20 and net_profit >= 5000:
        deal_score = "STRONG GO"
        score_bar = "██████████"
    elif net_margin_pct >= 15 and net_profit >= 2000:
        deal_score = "GO"
        score_bar = "████████░░"
    elif net_margin_pct >= 10 and net_profit >= 1000:
        deal_score = "MARGINAL"
        score_bar = "██████░░░░"
    elif net_margin_pct >= 5:
        deal_score = "THIN — consider volume"
        score_bar = "████░░░░░░"
    elif net_profit > 0:
        deal_score = "BARELY PROFITABLE"
        score_bar = "██░░░░░░░░"
    else:
        deal_score = "NO GO — LOSING MONEY"
        score_bar = "░░░░░░░░░░"

    # ---- RESULTS ----
    print(f"\n{'═' * 70}")
    print(f"  DEAL ANALYSIS: {part_name}")
    print(f"{'═' * 70}")

    print(f"\n  Part: {part_name} (P/N: {part_number})")
    print(f"  Condition: {condition_name}")
    print(f"  Quantity: {quantity}")
    print(f"  Urgency: {urgency_name}")

    print(f"\n  ┌{'─' * 40}┐")
    print(f"  │ REVENUE                               │")
    print(f"  ├{'─' * 40}┤")
    print(f"  │  Sell price:     ${sell_price:>12,.2f}/unit  │")
    print(f"  │  Quantity:              {quantity:>8}       │")
    print(f"  │  Total revenue:  ${total_sell:>12,.2f}       │")
    print(f"  └{'─' * 40}┘")

    print(f"\n  ┌{'─' * 40}┐")
    print(f"  │ COSTS                                  │")
    print(f"  ├{'─' * 40}┤")
    print(f"  │  Buy price:      ${total_buy:>12,.2f}       │")
    print(f"  │  Shipping:       ${shipping_cost:>12,.2f}       │")
    if overhaul_cost > 0:
        print(f"  │  Overhaul:       ${overhaul_cost * quantity:>12,.2f}       │")
    if cert_cost > 0:
        print(f"  │  Certification:  ${cert_cost * quantity:>12,.2f}       │")
    print(f"  │  Insurance (2%): ${insurance_cost:>12,.2f}       │")
    if commission_cost > 0:
        print(f"  │  Commission:     ${commission_cost:>12,.2f}       │")
    print(f"  │  Overhead:       ${overhead:>12,.2f}       │")
    print(f"  │  ──────────────────────────────        │")
    print(f"  │  Total costs:    ${total_buy + total_costs:>12,.2f}       │")
    print(f"  └{'─' * 40}┘")

    print(f"\n  ┌{'─' * 40}┐")
    print(f"  │ PROFIT & LOSS                          │")
    print(f"  ├{'─' * 40}┤")
    print(f"  │  Gross profit:   ${gross_profit:>12,.2f}       │")
    print(f"  │  Total costs:    ${total_costs:>12,.2f}       │")
    print(f"  │  ──────────────────────────────        │")
    pnl_color = "" if net_profit >= 0 else "LOSS "
    print(f"  │  NET PROFIT:     ${net_profit:>12,.2f}       │")
    print(f"  │                                        │")
    print(f"  │  Gross margin:          {gross_margin_pct:>6.1f}%       │")
    print(f"  │  Net margin:            {net_margin_pct:>6.1f}%       │")
    print(f"  │  ROI:                   {roi:>6.1f}%       │")
    print(f"  │  Break-even sell:  ${breakeven_per_unit:>10,.2f}/unit  │")
    print(f"  └{'─' * 40}┘")

    print(f"\n  ┌{'─' * 40}┐")
    print(f"  │ DEAL SCORE                             │")
    print(f"  ├{'─' * 40}┤")
    print(f"  │  {score_bar}  {deal_score:<20}  │")
    print(f"  └{'─' * 40}┘")

    if net_profit > 0:
        print(f"\n  You invest ${total_buy + total_costs:,.0f}, you get back ${total_sell:,.0f}.")
        print(f"  Net ${net_profit:,.0f} in your pocket. {roi:.0f}% return.")
        if urgency_name.startswith("AOG"):
            print(f"\n  AOG PREMIUM TIP: At AOG urgency, consider charging")
            print(f"  ${sell_price * 1.5:,.0f}-${sell_price * 2:,.0f}/unit. MROs pay anything for speed.")
    else:
        print(f"\n  This deal LOSES ${abs(net_profit):,.0f}. Don't do it.")
        print(f"  Minimum sell price to break even: ${breakeven_per_unit:,.2f}/unit")

    print(f"\n{'═' * 70}")

    return {
        "part": part_name,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "quantity": quantity,
        "net_profit": net_profit,
        "net_margin_pct": net_margin_pct,
        "roi": roi,
        "deal_score": deal_score,
    }


def quick_calc(buy, sell, qty=1, shipping=500, overhaul=0):
    """Quick non-interactive calculation for scripting."""
    total_buy = buy * qty
    total_sell = sell * qty
    insurance = total_sell * 0.02
    overhead = 200
    total_costs = shipping + overhaul * qty + insurance + overhead
    net = total_sell - total_buy - total_costs
    margin = (net / total_sell * 100) if total_sell > 0 else 0
    roi = (net / (total_buy + total_costs) * 100) if (total_buy + total_costs) > 0 else 0

    print(f"  Buy ${buy:,.0f} → Sell ${sell:,.0f} × {qty}")
    print(f"  Costs: ${total_costs:,.0f} (ship ${shipping}, ins ${insurance:.0f}, OH ${overhaul})")
    print(f"  Net profit: ${net:,.0f} | Margin: {margin:.1f}% | ROI: {roi:.1f}%")
    return net


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        # Quick mode: python deal_calculator.py --quick 10000 15000
        if len(sys.argv) >= 4:
            buy = float(sys.argv[2])
            sell = float(sys.argv[3])
            qty = int(sys.argv[4]) if len(sys.argv) > 4 else 1
            quick_calc(buy, sell, qty)
        else:
            print("Usage: python deal_calculator.py --quick <buy> <sell> [qty]")
    else:
        calculate_deal()
