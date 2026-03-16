"""
prepare.py — IMMUTABLE DATA & EVALUATION (Do Not Modify)

AutoResearch-style scaffold for logistics freight pricing.
This file handles data loading, feature engineering, train/test splitting,
and the verifiable evaluation function.

Adapted from Karpathy's autoresearch pattern:
- prepare.py = fixed data + eval (nobody edits)
- pricing_model.py = the model (agent edits)
- program.md = research objectives (human edits)

USAGE:
    1. Place your quoting data CSV at: data/quotes.csv
    2. Run: python prepare.py  (one-time setup, creates processed data)
    3. Then run: python pricing_model.py  (training + eval)
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# =============================================================================
# CONSTANTS — Adjust these to match YOUR data
# =============================================================================

DATA_DIR = Path("data")
PROCESSED_DIR = Path("processed")
RESULTS_FILE = Path("results.tsv")

# COVID regime boundary (adjust if needed)
COVID_START = pd.Timestamp("2020-03-15")
COVID_PEAK = pd.Timestamp("2021-06-01")
COVID_NORMALIZE = pd.Timestamp("2022-09-01")

# Train/test split: last N months = test set
TEST_MONTHS = 6

# Column mapping — map YOUR column names to standard names
# Edit this dict to match your CSV headers
COLUMN_MAP = {
    # Required columns (map your names on the left)
    "quote_date": "quote_date",       # Date the quote was created
    "origin": "origin",               # Origin city/zip/region
    "destination": "destination",     # Destination city/zip/region
    "quoted_price": "quoted_price",   # Price we quoted
    "actual_cost": "actual_cost",     # What it actually cost us (if known)
    "won": "won",                     # Did we win? (1/0 or True/False)
    # Optional columns (comment out if you don't have them)
    "weight": "weight",               # Shipment weight
    "equipment_type": "equipment_type", # Flatbed, van, reefer, etc.
    "commodity": "commodity",         # What's being shipped
    "distance_miles": "distance_miles", # Lane distance
    "fuel_surcharge": "fuel_surcharge", # Fuel cost component
    "lead_time_days": "lead_time_days", # Days between quote and pickup
    "customer_id": "customer_id",     # Customer identifier
    "mode": "mode",                   # FTL, LTL, intermodal, etc.
}


# =============================================================================
# DATA LOADING & FEATURE ENGINEERING
# =============================================================================

def load_raw_data(filepath=None):
    """Load raw quoting data from CSV."""
    if filepath is None:
        filepath = DATA_DIR / "quotes.csv"

    if not os.path.exists(filepath):
        print(f"ERROR: No data file found at {filepath}")
        print("Please place your quoting data CSV there.")
        print("Expected columns (at minimum):")
        print("  quote_date, origin, destination, quoted_price, won")
        raise FileNotFoundError(filepath)

    df = pd.read_csv(filepath)

    # Rename columns to standard names
    rename_map = {}
    for user_col, std_col in COLUMN_MAP.items():
        if user_col in df.columns and user_col != std_col:
            rename_map[user_col] = std_col
    if rename_map:
        df = df.rename(columns=rename_map)

    # Parse dates
    df["quote_date"] = pd.to_datetime(df["quote_date"])
    df = df.sort_values("quote_date").reset_index(drop=True)

    print(f"Loaded {len(df)} quotes from {df['quote_date'].min()} to {df['quote_date'].max()}")
    return df


def engineer_features(df):
    """Create features from raw data. Returns DataFrame with feature columns."""
    features = pd.DataFrame(index=df.index)

    # ---- Time features ----
    features["year"] = df["quote_date"].dt.year
    features["month"] = df["quote_date"].dt.month
    features["day_of_week"] = df["quote_date"].dt.dayofweek
    features["week_of_year"] = df["quote_date"].dt.isocalendar().week.astype(int)
    features["quarter"] = df["quote_date"].dt.quarter

    # Seasonal encoding (cyclical)
    features["month_sin"] = np.sin(2 * np.pi * features["month"] / 12)
    features["month_cos"] = np.cos(2 * np.pi * features["month"] / 12)
    features["dow_sin"] = np.sin(2 * np.pi * features["day_of_week"] / 7)
    features["dow_cos"] = np.cos(2 * np.pi * features["day_of_week"] / 7)

    # ---- COVID regime features ----
    features["is_pre_covid"] = (df["quote_date"] < COVID_START).astype(int)
    features["is_covid_peak"] = (
        (df["quote_date"] >= COVID_START) & (df["quote_date"] < COVID_NORMALIZE)
    ).astype(int)
    features["is_post_covid"] = (df["quote_date"] >= COVID_NORMALIZE).astype(int)
    features["days_since_covid"] = (df["quote_date"] - COVID_START).dt.days.clip(lower=0)

    # ---- Recency weight (for time-weighted training) ----
    max_date = df["quote_date"].max()
    days_ago = (max_date - df["quote_date"]).dt.days
    # Exponential decay: half-life of 180 days (6 months)
    half_life_days = 180
    features["recency_weight"] = np.exp(-np.log(2) * days_ago / half_life_days)

    # ---- Lane features (if origin/destination exist) ----
    if "origin" in df.columns and "destination" in df.columns:
        # Create lane identifier
        features["lane"] = df["origin"].astype(str) + "_to_" + df["destination"].astype(str)
        # Encode as category codes
        lane_codes = features["lane"].astype("category").cat.codes
        features["lane_code"] = lane_codes

    # ---- Distance ----
    if "distance_miles" in df.columns:
        features["distance_miles"] = df["distance_miles"].fillna(df["distance_miles"].median())
        features["log_distance"] = np.log1p(features["distance_miles"])

    # ---- Weight ----
    if "weight" in df.columns:
        features["weight"] = df["weight"].fillna(df["weight"].median())
        features["log_weight"] = np.log1p(features["weight"])

    # ---- Equipment type ----
    if "equipment_type" in df.columns:
        features["equipment_code"] = df["equipment_type"].astype("category").cat.codes

    # ---- Mode ----
    if "mode" in df.columns:
        features["mode_code"] = df["mode"].astype("category").cat.codes

    # ---- Lead time ----
    if "lead_time_days" in df.columns:
        features["lead_time_days"] = df["lead_time_days"].fillna(0)

    # ---- Lane historical stats (rolling averages) ----
    if "lane" in features.columns and "quoted_price" in df.columns:
        df_with_lane = df.copy()
        df_with_lane["lane"] = features["lane"]
        for window in [30, 60, 90]:
            col_name = f"lane_avg_price_{window}d"
            # Rolling mean by lane (approximation using all data up to that point)
            features[col_name] = (
                df_with_lane.groupby("lane")["quoted_price"]
                .transform(lambda x: x.rolling(window, min_periods=1).mean())
            )

    # ---- Fuel ----
    if "fuel_surcharge" in df.columns:
        features["fuel_surcharge"] = df["fuel_surcharge"].fillna(0)

    # ---- Customer ----
    if "customer_id" in df.columns:
        features["customer_code"] = df["customer_id"].astype("category").cat.codes

    return features


def create_train_test_split(df, features):
    """Time-based split: last TEST_MONTHS months = test, rest = train."""
    max_date = df["quote_date"].max()
    split_date = max_date - pd.DateOffset(months=TEST_MONTHS)

    train_mask = df["quote_date"] < split_date
    test_mask = df["quote_date"] >= split_date

    # Feature columns (exclude recency_weight and lane string)
    feature_cols = [c for c in features.columns if c not in ["recency_weight", "lane"]]

    X_train = features.loc[train_mask, feature_cols].values.astype(np.float32)
    X_test = features.loc[test_mask, feature_cols].values.astype(np.float32)

    y_train = df.loc[train_mask, "quoted_price"].values.astype(np.float32)
    y_test = df.loc[test_mask, "quoted_price"].values.astype(np.float32)

    w_train = features.loc[train_mask, "recency_weight"].values.astype(np.float32)

    # Additional test data for evaluation
    test_data = {
        "actual_cost": df.loc[test_mask, "actual_cost"].values if "actual_cost" in df.columns else None,
        "won": df.loc[test_mask, "won"].values if "won" in df.columns else None,
    }

    print(f"Train: {len(X_train)} quotes (before {split_date.date()})")
    print(f"Test:  {len(X_test)} quotes (after {split_date.date()})")
    print(f"Features: {len(feature_cols)} columns")

    return X_train, X_test, y_train, y_test, w_train, test_data, feature_cols


# =============================================================================
# EVALUATION — THE VERIFIABLE REWARD FUNCTION
# =============================================================================

def evaluate_pricing(predictions, y_true, test_data, verbose=True):
    """
    THE VERIFIABLE REWARD FUNCTION.

    This is the equivalent of val_bpb in autoresearch.
    Lower score = better model. Agent optimizes to minimize this.

    Components:
    1. MAPE (Mean Absolute Percentage Error) — how close are our quotes?
    2. Win rate bonus — would our quotes have won business?
    3. Margin bonus — would we have been profitable?

    Returns: composite score (lower = better)
    """
    # Clip predictions to be positive
    predictions = np.clip(predictions, 1.0, None)

    # ---- Metric 1: MAPE ----
    mape = np.mean(np.abs(y_true - predictions) / np.clip(y_true, 1.0, None)) * 100
    mae = np.mean(np.abs(y_true - predictions))

    # ---- Metric 2: Win rate (if we have won/lost data) ----
    win_rate = None
    if test_data.get("won") is not None:
        # Simple proxy: our prediction is within 5% of what won
        competitive = np.abs(predictions - y_true) / np.clip(y_true, 1.0, None) < 0.05
        win_rate = competitive.mean() * 100

    # ---- Metric 3: Margin (if we have actual cost data) ----
    margin = None
    if test_data.get("actual_cost") is not None:
        actual_cost = test_data["actual_cost"]
        valid = ~np.isnan(actual_cost) & (actual_cost > 0)
        if valid.any():
            margin = np.mean(
                (predictions[valid] - actual_cost[valid]) / np.clip(predictions[valid], 1.0, None)
            ) * 100

    # ---- Composite Score (lower = better) ----
    # Primary: MAPE (want low)
    # Bonus: subtract win_rate and margin contributions
    score = mape
    if win_rate is not None:
        score -= win_rate * 0.3  # Reward competitive quotes
    if margin is not None:
        score -= max(margin, 0) * 0.2  # Reward profitable quotes (but don't penalize)

    if verbose:
        print(f"\n{'='*50}")
        print(f"  PRICING MODEL EVALUATION")
        print(f"{'='*50}")
        print(f"  MAPE:          {mape:.2f}%")
        print(f"  MAE:           ${mae:.2f}")
        if win_rate is not None:
            print(f"  Win Rate:      {win_rate:.1f}%")
        if margin is not None:
            print(f"  Avg Margin:    {margin:.1f}%")
        print(f"  ────────────────────────────")
        print(f"  COMPOSITE SCORE: {score:.4f}  (lower = better)")
        print(f"{'='*50}\n")

    return {
        "score": score,
        "mape": mape,
        "mae": mae,
        "win_rate": win_rate,
        "margin": margin,
    }


def log_result(experiment_name, metrics, notes=""):
    """Append experiment result to results.tsv (autoresearch-style tracking)."""
    header_needed = not RESULTS_FILE.exists()

    with open(RESULTS_FILE, "a") as f:
        if header_needed:
            f.write("timestamp\texperiment\tscore\tmape\tmae\twin_rate\tmargin\tnotes\n")
        f.write(
            f"{datetime.now().isoformat()}\t"
            f"{experiment_name}\t"
            f"{metrics['score']:.4f}\t"
            f"{metrics['mape']:.2f}\t"
            f"{metrics['mae']:.2f}\t"
            f"{metrics.get('win_rate', 'N/A')}\t"
            f"{metrics.get('margin', 'N/A')}\t"
            f"{notes}\n"
        )


# =============================================================================
# CHANGEPOINT DETECTION — Find regime boundaries in your data
# =============================================================================

def detect_regime_changes(df, column="quoted_price", min_segment_length=60):
    """
    Detect structural breaks in pricing data.
    Uses simple rolling statistics to find regime boundaries.

    Returns list of (date, direction) tuples.
    """
    if column not in df.columns:
        return []

    # Monthly average price
    monthly = df.set_index("quote_date")[column].resample("ME").mean().dropna()

    if len(monthly) < 6:
        return []

    # Rolling mean with different windows
    short_ma = monthly.rolling(3).mean()
    long_ma = monthly.rolling(12).mean()

    # Detect crossovers (regime changes)
    changes = []
    prev_diff = None
    for date, (short, long_val) in zip(monthly.index[12:], zip(short_ma[12:], long_ma[12:])):
        if pd.isna(short) or pd.isna(long_val):
            continue
        diff = short - long_val
        if prev_diff is not None:
            if prev_diff <= 0 and diff > 0:
                changes.append((date, "UP"))
            elif prev_diff >= 0 and diff < 0:
                changes.append((date, "DOWN"))
        prev_diff = diff

    if changes:
        print(f"\nDetected {len(changes)} regime changes:")
        for date, direction in changes:
            print(f"  {date.date()}: Market shift {direction}")

    return changes


# =============================================================================
# ONE-TIME SETUP
# =============================================================================

def prepare_data(filepath=None):
    """Run once to process data and save to disk."""
    PROCESSED_DIR.mkdir(exist_ok=True)

    # Load
    df = load_raw_data(filepath)

    # Detect regime changes
    changes = detect_regime_changes(df)

    # Engineer features
    features = engineer_features(df)

    # Split
    X_train, X_test, y_train, y_test, w_train, test_data, feature_cols = \
        create_train_test_split(df, features)

    # Save processed data
    np.save(PROCESSED_DIR / "X_train.npy", X_train)
    np.save(PROCESSED_DIR / "X_test.npy", X_test)
    np.save(PROCESSED_DIR / "y_train.npy", y_train)
    np.save(PROCESSED_DIR / "y_test.npy", y_test)
    np.save(PROCESSED_DIR / "w_train.npy", w_train)

    # Save test metadata
    test_meta = {}
    for k, v in test_data.items():
        if v is not None:
            np.save(PROCESSED_DIR / f"test_{k}.npy", v)
            test_meta[k] = True
        else:
            test_meta[k] = False

    with open(PROCESSED_DIR / "meta.json", "w") as f:
        json.dump({
            "feature_cols": feature_cols,
            "n_train": len(X_train),
            "n_test": len(X_test),
            "n_features": len(feature_cols),
            "test_meta": test_meta,
            "regime_changes": [(str(d), dir) for d, dir in changes],
        }, f, indent=2)

    print(f"\nProcessed data saved to {PROCESSED_DIR}/")
    return X_train, X_test, y_train, y_test, w_train, test_data, feature_cols


def load_processed_data():
    """Load preprocessed data from disk."""
    X_train = np.load(PROCESSED_DIR / "X_train.npy")
    X_test = np.load(PROCESSED_DIR / "X_test.npy")
    y_train = np.load(PROCESSED_DIR / "y_train.npy")
    y_test = np.load(PROCESSED_DIR / "y_test.npy")
    w_train = np.load(PROCESSED_DIR / "w_train.npy")

    with open(PROCESSED_DIR / "meta.json") as f:
        meta = json.load(f)

    test_data = {}
    for k, exists in meta["test_meta"].items():
        if exists:
            test_data[k] = np.load(PROCESSED_DIR / f"test_{k}.npy")
        else:
            test_data[k] = None

    return X_train, X_test, y_train, y_test, w_train, test_data, meta["feature_cols"]


if __name__ == "__main__":
    prepare_data()
