# Status

Last updated: 2026-10-21

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

## Pilot (run 2026-10-21)

Three events in `events/opec_events.csv`, entered from the user's values: opec_2022_10 (leak time used), opec_2025_11, opec_2023_04. The loader accepted all three, and `run_opec.py` (main run, leak time) gave 3 ok, 0 failed. Outputs are in `results/opec_results.csv`, `results/opec_run_info.json` and `charts/opec_events.png`. The events file and DECISIONS.md were uncommitted at run time, so run info records `git_dirty: true`.

| event_id | day 0 | CAR [-1,+1] | t | CAR [-5,+5] | t | est overlap | nearby |
|---|---|---|---|---|---|---|---|
| opec_2022_10 | 2022-10-05 | +6.36% | 1.76 | +14.37% | 2.08 | 0 | 0 |
| opec_2025_11 | 2025-11-03 | +0.12% | 0.07 | +2.57% | 0.72 | 0 | 0 |
| opec_2023_04 | 2023-04-03 | +2.18% | 0.80 | +7.00% | 1.34 | 11 | 0 |

Overlap diagnostics:
- opec_2023_04's estimation window (2022-09-27 to 2023-03-20) holds all 11 days of opec_2022_10's [-5,+5] window (2022-09-28 to 2022-10-12).
- opec_2025_11 shows 0 overlap only because no other 2025 events are in the file yet. The full list will probably add more.
- No event windows overlap each other (nearby_events is 0 for all three).

Other things seen in the pilot:
- About 9.9% of opec_2022_10's [-5,+5] CAR comes before day 0 (days -5 to -1).
- opec_2022_10's residual std (2.08%) is about twice opec_2025_11's (1.07%).
- The chart caption is cut off at the right edge.

No across-event test has been run: N = 3, below the minimum of 5.

## Not built yet

- Official-time robustness run: the `--official-time` flag exists, but it has not been run on the pilot events (only opec_2022_10 has a leak time, so only it would change).
- Saudi unilateral subsample report.
- Outlier-exclusion robustness run.
- Brent robustness check.
- Calling the across-event tests from `run_opec.py`.

## Next

1. Decide the overlap rule (DECISIONS.md), using the pilot diagnostics above. The open question is an estimation window that contains another event's window (opec_2023_04 holds opec_2022_10's).
2. Review the pilot rows' open items: surprise_flag for opec_2022_10 and opec_2025_11, confound_note for all three, and opec_2025_11's notes, which still call the direction provisional even though DECISIONS.md now records pause = hold.
3. Fill the full OPEC+ list in `events/opec_events.csv`.
4. Call the across-event tests from `run_opec.py` (needs at least 5 events with status "ok").
5. Robustness runs: official-time (the `--official-time` flag exists, but the run hasn't been done), outlier exclusion, Saudi subsample, Brent.
6. Decide whether to record a power target in DECISIONS.md (the user's call). Until then `/check-results` reports ok counts but does not judge power.
