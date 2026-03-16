# Logistics Freight Pricing — Autonomous Research Program

## Objective

Optimize a freight quoting model using 5 years of logistics data spanning
pre-COVID through post-COVID market conditions with seasonal patterns.

The primary metric is the **composite score** from `evaluate_pricing()` in
`prepare.py`. **Lower score = better model.** The score combines:
- MAPE (mean absolute percentage error) — want low
- Win rate bonus — want high (competitive quotes)
- Margin bonus — want high (profitable quotes)

## Constraints

- **Only modify `pricing_model.py`** — never touch `prepare.py`
- No new dependencies beyond: xgboost, lightgbm, scikit-learn, numpy, pandas
- Each experiment should complete in under 5 minutes
- Keep changes reviewable (one idea per experiment)

## Key Challenges

1. **COVID regime change**: Pre-COVID (before March 2020) pricing patterns are
   fundamentally different from post-COVID. The model must handle this —
   either by weighting recent data more heavily, using regime features, or
   training separate models for different eras.

2. **Seasonality**: Freight rates have strong seasonal patterns (Q4 peak,
   produce season, holiday surges). The model needs to capture weekly and
   monthly cyclical patterns.

3. **Lane specificity**: Pricing is highly lane-dependent. The same weight
   on different origin→destination pairs can have 3-10x price differences.

4. **Market volatility**: Spot rates can change weekly. Historical averages
   are a floor, not a ceiling.

## Experiment Ideas (Agent Should Try)

### Phase 1: Baseline & Algorithm Comparison
- [ ] XGBoost baseline with default hyperparameters
- [ ] LightGBM comparison
- [ ] Ridge regression baseline (simple benchmark)
- [ ] Ensemble (XGBoost + Ridge blend)

### Phase 2: Time Weighting
- [ ] Exponential decay with different half-lives (90d, 180d, 365d)
- [ ] Hard COVID cutoff (discard pre-COVID data entirely)
- [ ] Soft COVID cutoff (10x weight for post-COVID data)
- [ ] Rolling window (only last 12/18/24 months)

### Phase 3: Feature Engineering
- [ ] Test with/without COVID regime features
- [ ] Add interaction features (lane × season)
- [ ] Try different seasonal encodings (cyclical vs one-hot)
- [ ] Lane-level historical averages with different windows

### Phase 4: Hyperparameter Tuning
- [ ] XGBoost depth: 4 vs 6 vs 8 vs 10
- [ ] Learning rate: 0.01 vs 0.05 vs 0.1
- [ ] Regularization strength sweep
- [ ] Number of estimators: 200 vs 500 vs 1000

### Phase 5: Advanced
- [ ] Separate models per regime (pre-COVID, COVID, post-COVID)
- [ ] Quantile regression (predict price range, not point estimate)
- [ ] Lane clustering (group similar lanes)
- [ ] Customer-specific adjustments

## Workflow

```
1. Modify pricing_model.py (change ONE thing)
2. Commit with descriptive message
3. Run: python pricing_model.py
4. Check composite score in output
5. If score improved → keep changes
   If score equal/worse → git reset --hard HEAD~1
6. Log observations
7. NEVER STOP — continue to next experiment
```

## Success Criteria

- MAPE below 10% is good, below 7% is excellent
- Win rate above 60% means quotes are competitive
- Margin above 8% means quotes are profitable
- Composite score trending downward across experiments
