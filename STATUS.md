# Status

Last updated: 2026-10-27 (supply-route rows entered, pre-war sample built)

## Where we are

- **v1.0.0 released 26 Oct 2026** (tag on 3ad1bed): https://github.com/JohnMitiguy/event-study/releases/tag/v1.0.0. Repo is public, with description, topics, social preview and MIT license.

- **First full run done** on the 37 events (main, `--shift-assumed`, `--official-time`), all 37 ok, 0 failed, prices through 2026-10-15. Rerun on the clean commit fcd40e8: every `opec_run_info*.json` says `git_dirty: false`, and all results CSVs and charts came out byte-for-byte identical to the first run.
- Headline (cross-sectional t, [-1,+1]): cuts N 7, +1.51%, t 1.56; increases N 17, -0.51%, t -0.49. Both null. Increases on [-5,+5]: -3.26%, t -2.38 (BMP -2.47, Wilcoxon p 0.045), t stays between -2.03 and -2.79 when any one event is dropped. Most of the cut move is before day 0 (+3.10% by day -1).
- Shifted run (13 time_assumed rows): cuts [-1,+1] +0.80% (t 0.57), increases -0.82% (t -0.90), increases [-5,+5] -3.33% (t -2.42). Firm-only: cuts 3 (too few), increases N 14: -1.37% (t -1.34), [-5,+5] -4.55% (t -3.19). Official-time run identical to main (the one leak is the same day as its release). opec_2025_04_03 upgraded 26 Oct from time_assumed to 09:15 ET (Dow Jones, date-only rule) with surprise_flag 1 (Reuters "unexpectedly").
- Outlier-exclusion run built (`no_outliers` sample in `opec_across_event*.csv`): top 5 residual days, using one full-sample beta (an assumption, DECISIONS.md does not say which beta), are 2020-11-09, 2020-03-09, 2020-03-18, 2020-04-17, 2020-04-02. 9 Mar 2020 is masked, so it hits no fit. 5 events are dropped (opec_2020_04_09, opec_2020_06_06, opec_2020_12_03, opec_2021_03_04, opec_2021_07_18). Cuts N 6: +1.61% (t 1.41); increases N 15: -0.88% (t -0.93); increases [-5,+5] -3.34% (t -2.44). `runner.estimation_days` gives the fitted days per event.
- opec_2025_04_03 is the biggest single event: [-1,+1] -12.40% (t -6.09) during the 3-4 Apr 2025 selloff (SPY -4.9%, -5.8%). confound_note now filled (2 Apr tariffs after the close, Fox Business); the other 16 increases average +0.23% (t 0.29) on [-1,+1].
- README now has a Results section, the average-CAR chart (`charts/opec_caar.png`), a filled Excluded events table, and fixes for the stale lines found in the 21 Oct audit.
- Tests (27 Oct): ruff clean, 445 passed.

## Supply-route attacks (second event type, built 26 Oct 2026, no events yet)

- Plan approved and decisions committed (560b69d): XLE primary, ITA and GLD secondary, all vs SPY, expected sign positive; primary test XLE [0,+1] cross-sectional t, all attacks pooled; windows [0,+1] and [-5,+5]; Holm p over the other five; two-sided; subgroups route and escalation; counted attacks at least 11 trading days apart; no time_assumed rows; attack runs mask all OPEC events and OPEC masks (main and shifted day 0); OPEC runs do not mask attacks until a v1.1.
- Built: `src/event_study/reporting.py` (shared helpers moved out of run_opec.py), `group_columns` in the runner, `events.load_supply_route_events` (spacing check), `scripts/run_supply_route.py` (`--dates-only`; no `--refresh`, so the shared XLE/SPY cache is never replaced), header-only `events/supply_route_events.csv` and `events/supply_route_mask_only.csv`, tests in `tests/test_supply_route.py`. OPEC outputs byte-identical after the refactor.
- The run refuses to start below 5 events. The first `--dates-only` run downloads ITA and GLD once.
- Candidates saved in `events/supply_route_candidates.md` (39 rows; Q-A/Q-B/Q-C settled at its top).
- 27 Oct: pre-war sample built (`sample` column `all`/`pre_war` in `supply_route_across_event.csv`; pre_war rows have role `robustness`, no primary, no Holm; left-out attacks listed). `WAR_START` = 2026-02-28, compared with the ET date of event_time.
- 27 Oct: all 39 candidates entered (counts updated below). 20 counted in `supply_route_events.csv` (15 pre-war), 19 in `supply_route_mask_only.csv` (12 spacing, 6 no time, 1 off-route). `--dates-only` runs clean: no attack has a nearby attack, est_span 131 to 267 sessions (2026 attacks reach back to mid-2025 because the war months are mostly masked). Each row's notes give the source time as stated, the ET conversion, and a fetch-check line.
- Fetch check: only attack_2019_07_19, attack_2019_09_14, attack_2020_11_23, attack_2022_01_17 and the dates of 7 mask rows were confirmed by fetch. CENTCOM, ONI, UKMTO, S&P, Seatrade and GlobalSecurity block the fetch tool (403/402). John checked the other 16 by hand on 27 Oct ("all good or good enough"); their notes say so.
- 27 Oct, later: attack_2026_03_18 (Ras Laffan) moved to the events file at 15:28 ET (Libnanews live item, 19:28:14 GMT, confirmed by fetch; John's QNA time 15:21 ET, no URL), day 0 Wed 18 Mar. mask_2026_03_19 is now masked for spacing. Now 21 counted (15 pre-war), 18 masked (13 spacing, 4 no time, 1 off-route).
- Waiting on a URL: mask_2021_03_07 (Ras Tanura). John reports MoD 23:35 AST, but Argaam and Ajel give only "morning"/"this evening". If it counts, day 0 is Mon 8 Mar 2021, 2 sessions after opec_2021_03_04, so it needs a confound_note ([-5,+5] holds that OPEC surprise).
- Defaults taken, need Decision lines from John: untimed attacks are masked even when the date alone pins day 0 (attack 2021-03-07 Sun and 2026-03-19 "early Thursday" would otherwise count, +2 events); earliest time used when a source gives several; zone not stated = local time of the site (every such row gives the same day 0 read as UTC); untimed or conflicting-time mask rows are time_assumed (both days masked). attack_2026_07_22 is a UKMTO report at exactly 16:00 ET, so day 0 rolls to Thu 23 Jul.
- Next: John confirms the 16 blocked sources by hand, pastes the Decision lines, commits; then the first run (do not run before, so no row is changed after seeing results); then a README section (GLD beta near zero, ITA overlap with SPY, long 2026 estimation windows).

## Changed this session (needs DECISIONS.md lines from the user)

- `events/opec_mask_only.csv` (8 rows, all opec.org slugs already in `opec_candidates.md`): 30 Nov 2016 OPEC-only cut, 5 Mar 2020 (covers the failed 6 Mar meeting), 5 Jan 2021, 1 Apr 2021 (A14), 5 Jul 2021 failed meeting, 3 Aug 2022, 5 Sep 2022, 4 Jun 2023. `events.load_mask_events` loads it; `run_events`/`estimation_dates` take `mask_day0s`; masks are skipped like other events' windows but get no results row. New diagnostic `nearby_mask_events` (1 for opec_2016_12_10 and opec_2021_07_18: mask news inside their own [-5,+5]). Run info records the mask file hash.
- `events/dates_table.csv` regenerated with masks: longest span still 197 sessions, no errors.
- Across-event groups: saudi_unilateral rows are kept out of all/cut/hold/increase and tested as their own group. `headline` column (True for [-1,+1] cut and increase), marked `*` in the printout.
- New outputs: `results/opec_abnormal*.csv` and `charts/opec_caar*.png`. Fixed the per-event chart title running into the first row.

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

## Not built yet

- Saudi unilateral subsample report.
- Brent robustness check.

## Next

1. Done 26 Oct: DECISIONS.md lines pasted, committed (fcd40e8), clean rerun.
2. Source a confound_note for opec_2025_04_03 (3 Apr 2025 selloff), and check the other large rows: opec_2020_12_03 (+9.06%), opec_2021_03_04 (+8.73%), opec_2026_04_05 ([-5,+5] -12.22%).
3. Sourcing: the Al Jazeera 5 Dec 2019 time zone (opec_2019_12_05), A5 (6 or 7 Dec 2018), the opec_2022_10_05 11:00 official time, the Sep 2016 Algiers releases (slugs 495, 496; inside opec_2016_12_10's estimation window, not masked), A14's table, 1B rows 2, 3, 6. Each one settled moves a row out of the mask file or into the CSV.
4. Saudi unilateral rows from Saudi Energy Ministry statements (5 Jan 2021 first; then remove mask_2021_01_05).
5. Done 26 Oct: outlier-exclusion run. User to remove it from DECISIONS.md "Not built yet" and add the beta line.
6. Brent robustness check: confirm the calendar check covers a non-NYSE series first.
7. Open call 5 (A2 on 24 or 25 May 2017) is still open.
