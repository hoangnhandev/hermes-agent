# Calibration Reference

> Stub — filled in Phase 04/05 with Brier score, calibration curve, and gating rules.

## Key Definitions

- **Brier Score**: Mean squared error of probabilistic predictions. Lower is better.
  Perfect = 0, always-0.5 = 0.25. Formula: `(1/N) * Σ(p_i - o_i)²`

- **Calibration Curve**: Groups predictions into decile buckets by predicted_p,
  compares mean prediction vs empirical frequency. Perfect calibration = diagonal.

- **Realized Edge**: Paper-trade PnL per prediction. Bet at market_p, payout based
  on outcome, minus fee/spread proxy (default 0.02).

- **Gating Rule**: Alerts only fire when a category has enough resolved history
  (≥30), calibration gap < tolerance, and realized edge > 0.

## Phase 02 Note

All Phase 02 alerts are explicitly **"uncalibrated — paper trade"**. No gating
applies until enough resolved history accumulates (4-6 weeks minimum).
