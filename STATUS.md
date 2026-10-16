# Status

Last updated: 2026-10-16

## Built

- Price loader with a frozen cache in `data/prices/` (`prices.load_cached`), simple returns, and a check of every return series against the NYSE trading calendar.
- Events loader for `events/opec_events.csv`, with leak-time handling and validation that reports every bad row at once.
- Event day 0 logic (actual closes, early closes, weekends, holidays) and trading-day windows.
- Market model (OLS with intercept), abnormal returns, CARs and per-event test statistics, calibrated on simulated no-effect events.
- Runner that runs every event, records failed events with reasons, and reports estimation-window overlap and nearby events.
- Across-event tests in `aggregate.py`: cross-sectional t, standardized-CAR (BMP), Wilcoxon and sign test. A power analysis is in `scripts/across_event_demo.py`.
- `scripts/run_opec.py`: the OPEC+ run (XLE vs SPY), writing results, run info and a per-event chart. `--official-time` uses official announcement times and writes to separate `*_official_time` files.
- Tests (including property-based and fuzz tests), Ruff, and CI.

## Not built yet

- Official-time robustness run: the `--official-time` flag exists, but the run has not been done or reported, because the events CSV has no events yet.
- Saudi unilateral subsample report.
- Outlier-exclusion robustness run.
- Brent robustness check.
- Calling the across-event tests from `run_opec.py`.

## Next

1. Pick and source three pilot OPEC+ events (the user does this, from primary sources).
2. Run the pilot and review the overlap diagnostics, then decide the overlap rule (DECISIONS.md).
3. Fill the full OPEC+ list in `events/opec_events.csv`.
4. Call the across-event tests from `run_opec.py` (needs at least 5 events with status "ok").
5. Robustness runs: official-time (the `--official-time` flag exists, but the run hasn't been done), outlier exclusion, Saudi subsample, Brent.
