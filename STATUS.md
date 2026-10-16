# Status

Last updated: 2026-10-16

## Built

- Price loader with a frozen cache in `data/prices/` (`prices.load_cached`), simple returns, and a check of every return series against the NYSE trading calendar.
- Events loader for `events/opec_events.csv`, with leak-time handling and validation that reports every bad row at once.
- Event day 0 logic (actual closes, early closes, weekends, holidays) and trading-day windows.
- Market model (OLS with intercept), abnormal returns, CARs and per-event test statistics, calibrated on simulated no-effect events.
- Runner that runs every event, records failed events with reasons, and reports estimation-window overlap and nearby events.
- Across-event tests in `aggregate.py`: cross-sectional t, standardized-CAR (BMP), Wilcoxon and sign test. A simulated power analysis is in `scripts/across_event_demo.py`, which also prints a formula-based count of events needed for 80% power: 26 ok events on [-1,+1], assuming a 1% day-0 abnormal return and 1% daily residual noise (10 on [0,0], 89 on [-5,+5]). That is an illustration, not a recorded target. The three counts are tested in `tests/test_across_event_demo.py`.
- Methodology-reviewer Bash hook in `.claude/hooks/reviewer_bash_guard.py`: an allowlist of commands and, for each, the flags it may take; pytest file arguments must be relative paths under `tests/` with no `..` or backslash. Tested in `tests/test_reviewer_hook.py`, including a test that runs the hook command line from the agent file's frontmatter through bash (it skips with a reason if bash or uv can't be found). It is a backstop and fails open if it can't start.
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
6. Decide whether to record a power target in DECISIONS.md (the user's call). Until then `/check-results` reports ok counts but does not judge power.
