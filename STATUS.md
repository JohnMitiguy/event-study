# Status

Last updated: 2026-10-21 (end of session)

## Where we are

- `events/opec_events.csv` holds 37 events (3 renamed pilots plus 34 new rows from the "Ready to enter" list in `events/opec_candidates.md`). Ids are `opec_YYYY_MM_DD`. New rows have the paraphrase in `notes` with "Quote pending"; no quotes, times or confounds were invented. Rows 13 and 22 of the candidates file say "confound check pending" in `notes`; `confound_note` is blank everywhere new.
- The time_assumed rule is in (DECISIONS.md, README, loader, runner, script). 14 of the 37 rows are `time_assumed` (placeholder 12:00 ET, not a real time). Results are reported three ways: all events, without time_assumed rows (a filter on the full run's results; `sample` column in `opec_across_event.csv`), and day 0 shifted one trading day later (`--shift-assumed`, `*_day0_shifted` outputs). In the without-time_assumed report the cut group has 3 events and shows "too few events (N < 5)".
- The dates table was checked with `--dates-only` (all 37 events have full 120-day estimation windows, no errors, `nearby_events` is 0 for all). Saved untracked as `events/dates_table.csv`. A8 (9 Apr 2020) and A10 (6 Jun 2020) have estimation windows through the Feb to Mar 2020 crash (open call 6).
- **No full run has been done on the 37 events.** `results/` still holds the 3-event pilot output.
- Tests: ruff clean, 397 passed, 2 skipped.

## Built

- Price loader with a frozen cache in `data/prices/` (`prices.load_cached`), simple returns, and a check of every return series against the NYSE trading calendar.
- Events loader for `events/opec_events.csv`, with leak-time handling and validation that reports every bad row at once.
- Event day 0 logic (actual closes, early closes, weekends, holidays) and trading-day windows.
- Market model (OLS with intercept), abnormal returns, CARs and per-event test statistics, calibrated on simulated no-effect events.
- Runner that runs every event, records failed events with reasons, and reports nearby events. `run_events` checks both return series against the NYSE calendar and raises a ValueError for non-session dates or missing sessions (moved from `run_opec.py`, so every caller gets it). It cannot see a series cut short at either end. `simulate.fake_returns` now uses real NYSE sessions (same numbers, new dates).
- Estimation windows skip every day inside another event's widest window (other events in the same run, ok or failed) and reach further back to keep 120 days; if day -10 is skipped the window ends on the latest unskipped day before it. No cap on how far back. The runner reports `est_start`, `est_end` and `est_masked_days`; `est_overlap_days` is gone. A later event can never change an earlier event's row (tested by hand and as a property test, along with a property test that no estimation day lies inside another event's window).
- Across-event tests in `aggregate.py`: cross-sectional t, standardized-CAR (BMP), Wilcoxon and sign test. A simulated power analysis is in `scripts/across_event_demo.py`, which also prints a formula-based count of events needed for 80% power: 26 ok events on [-1,+1], assuming a 1% day-0 abnormal return and 1% daily residual noise (10 on [0,0], 89 on [-5,+5]). That is an illustration, not a recorded target. The three counts are tested in `tests/test_across_event_demo.py`.
- Methodology-reviewer Bash hook in `.claude/hooks/reviewer_bash_guard.py`: an allowlist of commands and, for each, the flags it may take; pytest file arguments must be relative paths under `tests/` with no `..` or backslash. Tested in `tests/test_reviewer_hook.py`, including a test that runs the hook command line from the agent file's frontmatter through bash (it skips with a reason if bash or uv can't be found). It is a backstop and fails open if it can't start.
- `scripts/run_opec.py`: the OPEC+ run (XLE vs SPY), writing results, run info and a per-event chart. `--official-time` uses official announcement times and writes to separate `*_official_time` files. `--dates-only` prints per event the day 0, est_start, est_end, est_masked_days, est_span (trading days, inclusive) and nearby_events, computing no returns, regressions or CARs and saving nothing (`runner.estimation_dates`).
- `run_opec.py` now calls the across-event tests after the per-event summary. For [-1,+1] and [-5,+5] it reports, for all events and separately for cut, increase and hold: N ok, mean CAR, cross-sectional t, BMP t, Wilcoxon p and sign test p. A group with fewer than 5 ok events prints "not tested (N < 5)". Groups are filters on the finished results table. Every event that is not ok is listed with its direction, status and reason. Written to `results/opec_across_event.csv` (`_official_time` suffix with `--official-time`): one row per window and group, with `tested` and `note` columns and empty statistics when not tested. Tested on simulated data (15 ok events plus one failed) and on the pilot; the numbers equal a direct `across_event_tests` call. Nothing in the method or the existing results changed.
- time_assumed support: `time_assumed` column (required, blank/0/1, rejected with a leak time), `load_events(shift_assumed=...)` using `event_days.next_session`, `time_assumed` carried into results, `--shift-assumed` flag, and a `sample` column (`all`, `firm_only`) in the across-event CSV. A group below 5 ok events shows "too few events (N < 5)" (this replaces the older "not tested" wording below).
- Tests (including property-based and fuzz tests), Ruff, and CI.

## Pilot (run 2026-10-21)

Three events entered from the user's values (now renamed opec_2022_10_05, opec_2025_11_02, opec_2023_04_02 and part of the 37-event CSV): opec_2022_10 (leak time used), opec_2025_11, opec_2023_04. The results below are from the 3-event CSV and will change once the full list is run, because other events' days are now skipped. The loader accepted all three, and `run_opec.py` (main run, leak time) gave 3 ok, 0 failed. Outputs are in `results/opec_results.csv`, `results/opec_run_info.json` and `charts/opec_events.png`. Rerun the same day with the skipping rule, on the same price cache (same hashes), with uncommitted changes, so run info records `git_dirty: true`.

| event_id | day 0 | est window | masked | CAR [-1,+1] | t | CAR [-5,+5] | t | nearby |
|---|---|---|---|---|---|---|---|---|
| opec_2022_10 | 2022-10-05 | 2022-03-31 to 2022-09-21 | 0 | +6.36% | 1.76 | +14.37% | 2.08 | 0 |
| opec_2025_11 | 2025-11-03 | 2025-04-30 to 2025-10-20 | 0 | +0.12% | 0.07 | +2.57% | 0.72 | 0 |
| opec_2023_04 | 2023-04-03 | 2022-09-12 to 2023-03-20 | 11 | +2.72% | 0.99 | +8.97% | 1.71 | 0 |

Effect of the skipping rule:
- opec_2022_10 and opec_2025_11 had nothing to skip; every number is bit-for-bit the same as before.
- opec_2023_04 now skips all 11 days of opec_2022_10's [-5,+5] window (2022-09-28 to 2022-10-12) and starts 11 sessions earlier (2022-09-12 instead of 2022-09-27). Alpha fell from +0.000714 to -0.001108 a day, beta rose from 0.818 to 0.827, and resid_std went from 1.58% to 1.59%. CAR [-1,+1] went from +2.18% (t 0.80) to +2.72% (t 0.99), and CAR [-5,+5] from +7.00% (t 1.34) to +8.97% (t 1.71). Nearly all of the CAR change comes from alpha (0.18% a day times 3 or 11 days): the 11 skipped days averaged +1.46% a day of XLE return beyond beta times SPY (opec_2022_10's reaction), and the 11 days that replaced them (2022-09-12 to 2022-09-26) averaged -0.53%. Those replacement days were also more volatile (std 2.09% against 1.43%), which is why resid_std rose slightly instead of falling.
- opec_2025_11 has nothing to skip only because no other 2025 events are in the file yet. The full list will probably add more.
- No event windows overlap each other (nearby_events is 0 for all three).

Other things seen in the pilot:
- About 9.9% of opec_2022_10's [-5,+5] CAR comes before day 0 (days -5 to -1).
- opec_2022_10's residual std (2.08%) is about twice opec_2025_11's (1.07%).
- The chart caption is now wrapped to the figure width. With a single panel the chart title is still cut off (not an issue with three panels).

Across-event tests on the pilot: every group prints "not tested (N < 5)" (all 3 ok, cut 2, hold 1, increase 0), so `results/opec_across_event.csv` holds no statistics yet. `results/opec_results.csv` and the chart came out identical on rerun; `results/opec_run_info.json` was left as committed (a rerun now would record a dirty tree).

## Not built yet

- Official-time robustness run: the `--official-time` flag exists, but it has not been run on the pilot events (only opec_2022_10 has a leak time, so only it would change).
- Saudi unilateral subsample report.
- Outlier-exclusion robustness run.
- Brent robustness check.

## Next

1. Add a `mask_only` flag for real OPEC events left out of the CSV (for example the 30 Nov 2016 OPEC-only decision, open call 7, and the Saudi cuts), so their days are skipped in other events' estimation windows but they are never tested or averaged. Needs a DECISIONS.md entry first (the user edits that file).
2. First full run on the 37 events (main, then `--shift-assumed`, then `--official-time`), reading the look-back limit and routine-decision rule from `--dates-only` output first.
3. Saudi unilateral rows from the Saudi Energy Ministry statements (5 Jan 2021 and the others in opec_candidates.md Gaps), and read the 1 Apr 2021 production table (A14, then enter it); also settle rows 2 and 3 of 1B and parked row 6.
4. Set the look-back limit and the rule for routine monthly decisions from `--dates-only` output before reading any CARs.
5. Before any non-NYSE security such as Brent, confirm the calendar check covers it.
6. Review the pilot rows' open items: surprise_flag for opec_2022_10 and opec_2025_11, and confound_note for all three. (opec_2025_11's notes now say it is tagged hold per the pause rule.)
7. Finish the OPEC+ list: the caveat rows (A14, 1B rows 2 and 3), row 6, and the Saudi rows. Open calls 5 to 7 in `opec_candidates.md` are still open.
8. Robustness runs: official-time (the `--official-time` flag exists, but the run hasn't been done), outlier exclusion, Saudi subsample, Brent.
   - The outlier-exclusion run must test the estimation days actually used, not the span from est_start to est_end: the span includes the skipped days of other events' windows.
   - Subsamples and exclusions should filter the results of the full run, not the events table before it: dropping an event from the table changes the estimation windows of the events after it.
9. Decide whether to record a power target in DECISIONS.md (the user's call). Until then `/check-results` reports ok counts but does not judge power.
