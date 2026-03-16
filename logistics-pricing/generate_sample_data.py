"""
generate_sample_data.py — Create realistic synthetic logistics quoting data.

Use this to test the pipeline before plugging in your real data.
Generates 5 years of freight quotes with:
- Pre-COVID / COVID / post-COVID regime changes
- Seasonal patterns (Q4 peak, produce season)
- Lane-specific pricing
- Win/loss outcomes
- Realistic cost structures

USAGE:
    python generate_sample_data.py
    # Creates data/quotes.csv with ~15,000 synthetic quotes
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

# =============================================================================
# CONFIGURATION
# =============================================================================

OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "quotes.csv")
N_QUOTES = 15000
START_DATE = datetime(2021, 1, 1)
END_DATE = datetime(2026, 1, 1)

# Lanes (origin → destination with base rate per mile)
LANES = [
    ("Los Angeles, CA", "Dallas, TX", 1.80),
    ("Chicago, IL", "Atlanta, GA", 2.10),
    ("Newark, NJ", "Miami, FL", 2.25),
    ("Seattle, WA", "Denver, CO", 1.95),
    ("Houston, TX", "Memphis, TN", 2.00),
    ("Los Angeles, CA", "Chicago, IL", 1.70),
    ("Atlanta, GA", "Newark, NJ", 2.15),
    ("Dallas, TX", "Los Angeles, CA", 1.85),
    ("Miami, FL", "Chicago, IL", 2.30),
    ("Denver, CO", "Houston, TX", 1.90),
    ("Phoenix, AZ", "Kansas City, MO", 2.05),
    ("Portland, OR", "Salt Lake City, UT", 2.20),
    ("Nashville, TN", "Charlotte, NC", 2.40),
    ("Minneapolis, MN", "Detroit, MI", 2.15),
    ("San Francisco, CA", "Las Vegas, NV", 2.50),
]

# Approximate distances (miles)
LANE_DISTANCES = [1400, 720, 1280, 1300, 600, 2000, 870, 1400, 1370, 1050,
                  1100, 770, 400, 690, 570]

EQUIPMENT_TYPES = ["Dry Van", "Reefer", "Flatbed"]
EQUIPMENT_MULTIPLIER = {"Dry Van": 1.0, "Reefer": 1.25, "Flatbed": 1.15}

COMMODITIES = ["General Freight", "Produce", "Electronics", "Building Materials",
               "Automotive Parts", "Food & Beverage", "Chemicals", "Machinery"]

MODES = ["FTL", "LTL"]

CUSTOMERS = [f"CUST-{i:03d}" for i in range(1, 51)]  # 50 customers


# =============================================================================
# REGIME / MARKET FUNCTIONS
# =============================================================================

def get_market_multiplier(date):
    """Simulate COVID and post-COVID market conditions."""
    covid_start = datetime(2020, 3, 15)
    covid_peak = datetime(2021, 6, 1)
    covid_normalize = datetime(2022, 9, 1)

    if date < covid_start:
        # Pre-COVID: stable market
        return 1.0 + np.random.normal(0, 0.03)
    elif date < covid_peak:
        # COVID surge: rates spike 30-80%
        months_in = (date - covid_start).days / 30
        surge = 0.3 + 0.5 * (months_in / 15)  # Ramps up
        return 1.0 + surge + np.random.normal(0, 0.08)
    elif date < covid_normalize:
        # Cooling down from peak
        months_past_peak = (date - covid_peak).days / 30
        remaining_surge = max(0, 0.8 - 0.05 * months_past_peak)
        return 1.0 + remaining_surge + np.random.normal(0, 0.06)
    else:
        # Post-COVID: new normal (10-15% above pre-COVID)
        return 1.12 + np.random.normal(0, 0.04)


def get_seasonal_multiplier(date):
    """Seasonal freight rate patterns."""
    month = date.month
    day_of_year = date.timetuple().tm_yday

    # Base seasonal pattern
    seasonal = 1.0

    # Q4 peak (October-December): holiday shipping surge
    if month in [10, 11, 12]:
        seasonal += 0.08 + 0.04 * (month - 9) / 3

    # Produce season (April-July): reefer demand spike
    if month in [4, 5, 6, 7]:
        seasonal += 0.05

    # January dip: post-holiday slowdown
    if month == 1:
        seasonal -= 0.06

    # Day-of-week effect (slightly higher mid-week)
    dow = date.weekday()
    if dow in [1, 2, 3]:  # Tue-Thu
        seasonal += 0.02

    return seasonal + np.random.normal(0, 0.02)


def get_fuel_surcharge(date):
    """Simulate fuel price trends."""
    base_fuel = 0.35  # base $/mile fuel surcharge

    # Fuel spike during 2022
    if datetime(2022, 2, 1) <= date <= datetime(2022, 10, 1):
        months_in = (date - datetime(2022, 2, 1)).days / 30
        spike = 0.15 * np.sin(np.pi * months_in / 8)  # Peaks mid-2022
        return base_fuel + spike + np.random.normal(0, 0.03)

    # General inflation trend
    years_from_start = (date - START_DATE).days / 365
    trend = 0.02 * years_from_start
    return base_fuel + trend + np.random.normal(0, 0.02)


# =============================================================================
# GENERATE DATA
# =============================================================================

def generate_quotes():
    """Generate synthetic freight quoting data."""
    records = []

    # Random dates across the 5-year span
    date_range = (END_DATE - START_DATE).days
    random_days = np.random.randint(0, date_range, N_QUOTES)
    dates = [START_DATE + timedelta(days=int(d)) for d in sorted(random_days)]

    for i, date in enumerate(dates):
        # Pick random lane
        lane_idx = np.random.randint(0, len(LANES))
        origin, destination, base_rate = LANES[lane_idx]
        distance = LANE_DISTANCES[lane_idx]

        # Equipment and commodity
        equipment = np.random.choice(EQUIPMENT_TYPES, p=[0.6, 0.25, 0.15])
        commodity = np.random.choice(COMMODITIES)
        mode = np.random.choice(MODES, p=[0.7, 0.3])
        customer = np.random.choice(CUSTOMERS)

        # Weight (lbs)
        if mode == "FTL":
            weight = np.random.uniform(20000, 44000)
        else:
            weight = np.random.uniform(2000, 15000)

        # Lead time (days between quote and pickup)
        lead_time = max(0, int(np.random.exponential(3)))

        # Calculate rate
        market_mult = get_market_multiplier(date)
        seasonal_mult = get_seasonal_multiplier(date)
        equip_mult = EQUIPMENT_MULTIPLIER[equipment]
        fuel = get_fuel_surcharge(date)

        # LTL premium
        mode_mult = 1.0 if mode == "FTL" else 1.3 + (44000 - weight) / 44000 * 0.5

        # Base cost per mile
        cost_per_mile = base_rate * market_mult * seasonal_mult * equip_mult * mode_mult

        # Total cost
        actual_cost = (cost_per_mile * distance) + (fuel * distance)

        # Our quoted price (markup + noise)
        markup = np.random.uniform(1.08, 1.18)  # 8-18% margin target
        quoted_price = actual_cost * markup

        # Add some realistic noise
        quoted_price *= (1 + np.random.normal(0, 0.03))

        # Win/loss (higher markup = lower win probability)
        win_prob = max(0.1, min(0.9, 1.0 - (markup - 1.0) * 5))
        # Adjust for lead time (last-minute = more likely to win at higher price)
        if lead_time <= 1:
            win_prob = min(0.95, win_prob + 0.15)
        won = np.random.random() < win_prob

        records.append({
            "quote_date": date.strftime("%Y-%m-%d"),
            "origin": origin,
            "destination": destination,
            "distance_miles": distance,
            "weight": round(weight),
            "equipment_type": equipment,
            "commodity": commodity,
            "mode": mode,
            "customer_id": customer,
            "lead_time_days": lead_time,
            "fuel_surcharge": round(fuel * distance, 2),
            "quoted_price": round(quoted_price, 2),
            "actual_cost": round(actual_cost, 2),
            "won": int(won),
        })

    return pd.DataFrame(records)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Generating synthetic logistics quoting data...")
    df = generate_quotes()

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nGenerated {len(df)} quotes → {OUTPUT_FILE}")
    print(f"Date range: {df['quote_date'].min()} to {df['quote_date'].max()}")
    lane_count = df.apply(lambda r: r["origin"] + " to " + r["destination"], axis=1).nunique()
    print(f"Lanes: {lane_count}")
    print(f"Win rate: {df['won'].mean():.1%}")
    print(f"Avg quoted price: ${df['quoted_price'].mean():,.2f}")
    print(f"Avg actual cost: ${df['actual_cost'].mean():,.2f}")
    print(f"Avg margin: {((df['quoted_price'] - df['actual_cost']) / df['quoted_price']).mean():.1%}")

    # Show regime breakdown
    df["date"] = pd.to_datetime(df["quote_date"])
    pre_covid = df[df["date"] < "2020-03-15"]
    covid = df[(df["date"] >= "2020-03-15") & (df["date"] < "2022-09-01")]
    post_covid = df[df["date"] >= "2022-09-01"]

    print(f"\nRegime breakdown:")
    if len(pre_covid) > 0:
        print(f"  Pre-COVID:  {len(pre_covid)} quotes, avg ${pre_covid['quoted_price'].mean():,.2f}")
    print(f"  COVID era:  {len(covid)} quotes, avg ${covid['quoted_price'].mean():,.2f}")
    print(f"  Post-COVID: {len(post_covid)} quotes, avg ${post_covid['quoted_price'].mean():,.2f}")


if __name__ == "__main__":
    main()
