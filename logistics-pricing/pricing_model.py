"""
pricing_model.py — THE MODEL (Agent Modifies This File)

AutoResearch-style pricing model for logistics freight quoting.
This is the ONLY file the agent should modify during experiments.

The agent can change:
- Algorithm (XGBoost, LightGBM, linear, neural net)
- Hyperparameters (learning rate, depth, regularization)
- Feature selection (which columns to use)
- Time weighting strategy (how much to weight recent vs old data)
- Regime handling (how to handle COVID-era data)
- Ensemble methods (combine multiple models)

USAGE:
    python pricing_model.py
"""

import time
import numpy as np
from prepare import load_processed_data, evaluate_pricing, log_result

# =============================================================================
# EXPERIMENT CONFIGURATION — Agent modifies these
# =============================================================================

EXPERIMENT_NAME = "gradient_boost_v1"
NOTES = "GradientBoosting with recency weighting - best baseline"

# Algorithm choice: "xgboost", "lightgbm", "linear", "ridge", "ensemble", "gradient_boosting"
ALGORITHM = "gradient_boosting"

# Whether to use recency weights during training
USE_RECENCY_WEIGHTS = True

# Feature indices to use (None = use all)
# Agent can experiment with feature subsets
FEATURE_INDICES = None

# =============================================================================
# MODEL HYPERPARAMETERS — Agent tunes these
# =============================================================================

XGBOOST_PARAMS = {
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_alpha": 0.1,       # L1 regularization
    "reg_lambda": 1.0,      # L2 regularization
    "objective": "reg:squarederror",
    "random_state": 42,
    "verbosity": 0,
}

LIGHTGBM_PARAMS = {
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 10,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "objective": "regression",
    "random_state": 42,
    "verbosity": -1,
}


# =============================================================================
# MODEL TRAINING & PREDICTION
# =============================================================================

def train_and_predict(X_train, X_test, y_train, w_train, feature_cols):
    """Train model and return predictions on test set."""

    # Feature selection
    if FEATURE_INDICES is not None:
        X_train = X_train[:, FEATURE_INDICES]
        X_test = X_test[:, FEATURE_INDICES]

    # Sample weights
    weights = w_train if USE_RECENCY_WEIGHTS else None

    if ALGORITHM == "xgboost":
        import xgboost as xgb
        model = xgb.XGBRegressor(**XGBOOST_PARAMS)
        model.fit(X_train, y_train, sample_weight=weights)
        predictions = model.predict(X_test)

        # Feature importance (for logging)
        if FEATURE_INDICES is None:
            importances = model.feature_importances_
            top_features = sorted(
                zip(feature_cols, importances),
                key=lambda x: x[1], reverse=True
            )[:10]
            print("\nTop 10 features:")
            for name, imp in top_features:
                print(f"  {name}: {imp:.4f}")

    elif ALGORITHM == "lightgbm":
        import lightgbm as lgb
        model = lgb.LGBMRegressor(**LIGHTGBM_PARAMS)
        model.fit(X_train, y_train, sample_weight=weights)
        predictions = model.predict(X_test)

    elif ALGORITHM == "linear":
        from sklearn.linear_model import LinearRegression
        model = LinearRegression()
        # For weighted linear regression, use sample_weight in fit
        model.fit(X_train, y_train, sample_weight=weights)
        predictions = model.predict(X_test)

    elif ALGORITHM == "ridge":
        from sklearn.linear_model import Ridge
        model = Ridge(alpha=1.0)
        model.fit(X_train, y_train, sample_weight=weights)
        predictions = model.predict(X_test)

    elif ALGORITHM == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_leaf=10,
            random_state=42,
        )
        model.fit(X_train, y_train, sample_weight=weights)
        predictions = model.predict(X_test)

        # Feature importance
        if FEATURE_INDICES is None:
            importances = model.feature_importances_
            top_features = sorted(
                zip(feature_cols, importances),
                key=lambda x: x[1], reverse=True
            )[:10]
            print("\nTop 10 features:")
            for name, imp in top_features:
                print(f"  {name}: {imp:.4f}")

    elif ALGORITHM == "ensemble":
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.linear_model import Ridge

        # Model 1: GradientBoosting
        gb_model = GradientBoostingRegressor(
            n_estimators=500, max_depth=6, learning_rate=0.05, random_state=42
        )
        gb_model.fit(X_train, y_train, sample_weight=weights)
        pred_xgb = gb_model.predict(X_test)

        # Model 2: Ridge
        ridge_model = Ridge(alpha=1.0)
        ridge_model.fit(X_train, y_train, sample_weight=weights)
        pred_ridge = ridge_model.predict(X_test)

        # Blend (agent can tune these weights)
        predictions = 0.7 * pred_xgb + 0.3 * pred_ridge  # Agent can tune blend weights

    else:
        raise ValueError(f"Unknown algorithm: {ALGORITHM}")

    return predictions


# =============================================================================
# MAIN — Run experiment
# =============================================================================

def main():
    start_time = time.time()

    print(f"Experiment: {EXPERIMENT_NAME}")
    print(f"Algorithm: {ALGORITHM}")
    print(f"Recency weights: {USE_RECENCY_WEIGHTS}")
    print()

    # Load data
    X_train, X_test, y_train, y_test, w_train, test_data, feature_cols = \
        load_processed_data()

    # Train and predict
    predictions = train_and_predict(X_train, X_test, y_train, w_train, feature_cols)

    # Evaluate (THE VERIFIABLE REWARD)
    metrics = evaluate_pricing(predictions, y_test, test_data)

    # Log result
    elapsed = time.time() - start_time
    log_result(EXPERIMENT_NAME, metrics, notes=f"{NOTES} | {elapsed:.1f}s")

    print(f"Experiment completed in {elapsed:.1f}s")
    print(f"Results logged to results.tsv")

    return metrics


if __name__ == "__main__":
    main()
