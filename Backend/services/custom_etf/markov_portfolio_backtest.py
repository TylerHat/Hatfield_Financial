"""Compatibility shim — the Markov backtest now runs on the generic engine.

HFA-069 replaced the hand-rolled walk-forward in this module with
services.custom_etf.walk_forward, which replays the LIVE strategy semantics
(composite score, hold-until-sell hysteresis, eligibility gates, conviction
weights) via the shared rebalance core. The old engine ranked candidates by
raw 5-day bull probability and force-sold anything outside the day's top 10
— a materially different (higher-turnover) strategy than the deployed
MarkovRegimeStrategy, so its results couldn't validate the product. Numbers
produced after this change are NOT comparable to results from the old
engine; that is the fix, not a regression.

Kept importable for:
  - scripts/backfill_markov_history (one-shot, idempotency-guarded)
  - any caller of run_markov_portfolio_backtest (job entrypoint)
"""

from __future__ import annotations

import pandas as pd

from .walk_forward import run_walk_forward, run_generic_backtest, _BACKTEST_FETCH_PERIOD


def _walk_forward_markov(
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    cadence: str,
    period: str = _BACKTEST_FETCH_PERIOD,
    progress_cb=None,
) -> dict:
    """Walk-forward Markov portfolio simulation between two explicit dates.
    Thin delegation to the generic engine with the registered
    markov-regime strategy."""
    from .strategies import get_strategy
    strategy = get_strategy('markov-regime')
    if strategy is None:
        raise RuntimeError('markov-regime strategy is not registered')
    return run_walk_forward(strategy, start_date, end_date, cadence,
                            period=period, progress_cb=progress_cb)


def run_markov_portfolio_backtest(job_id: str, years: int, cadence: str) -> None:
    """Job entrypoint kept for backwards compatibility — delegates to the
    generic engine's job wrapper."""
    run_generic_backtest(job_id, 'markov-regime', years, cadence)
