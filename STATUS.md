# Status

Last updated: 2026-10-27 (v1.1: OPEC+ runs mask attack windows)

## Where we are

- **v1.0.0 released 26 Oct 2026** (tag on 3ad1bed): https://github.com/JohnMitiguy/event-study/releases/tag/v1.0.0. Repo is public. The GitHub description, topics and social preview still describe OPEC+ only (preview also says 414 tests and shows v1.0 numbers).
- **v1.1 committed 27 Oct** (85e2cdc) and rerun clean (4228dba): every run info says `git_dirty: false` at 85e2cdc, every events and mask hash matches the committed file, and every results CSV and chart was byte-identical to the pre-commit run. CI passed on 4228dba. Tag v1.1.0 on 4228dba, pushed.
- Tests (27 Oct, v1.1): ruff clean, 461 passed, 2 skipped (reviewer-hook test: no bash found from pytest's shell).

### v1.1 changes

- `scripts/run_opec.py`: every OPEC+ run (main, `--official-time`, `--shift-assumed`, `--dates-only`) skips the [-5,+5] days of every counted attack and attack mask row (both days for time_assumed rows) in its estimation windows. One combined set goes to `run_events`, `estimation_days` (no_outliers) and `estimation_dates`. Attack day 0s ignore the OPEC+ flags. Run info records the supply-route file hashes and `attack_mask_day0_count` (40).
- `events.main_and_shifted_day0s` (moved from run_supply_route.py, behavior unchanged: still 79 mask day 0s).
- `reporting.file_sha256` hashes with CRLF turned into LF, so the hash equals the committed file's git blob hash on any machine. Run info hashes from before v1.1 used raw CRLF bytes, so they differ from v1.1 hashes although no events file changed (`git log c0466d1..HEAD -- events` is empty).
- Tests: 15 new (combined masks, flags, one mask set reaching both calls, CRLF hashing, confound_note never reaching an output for both studies, build_mask_day0s unchanged).
- `.claude/`: reviewer commands now cover both event types; /review-last accepts a DECISIONS.md entry from any earlier commit.
- README: v1.1 numbers throughout, a "What changed in v1.1" subsection, attacks inside OPEC+ windows, two pairs of events sharing one estimation window.

### OPEC+ decisions (v1.1)

- 37 events, all ok in all three runs. Day 0s unchanged. 22 of 37 estimation windows changed (biggest in 2026); longest look-back 197 -> 296 sessions (opec_2026_10_04, 176 skipped days). opec_2026_04_05 and opec_2026_05_03 now share one estimation window (2025-05-13 to 2026-02-20). 2026 betas moved from -0.29 to 0.23 (v1.0) to 0.02 to 0.29.
- Headline (cross-sectional t, [-1,+1]): cuts N 7, +1.51%, t 1.64 (p 0.15); increases N 17, -0.40%, t -0.38. Both null.
- Increases [-5,+5]: -2.82%, t -2.08, p 0.054 (v1.0: -3.26%, t -2.38, p 0.030); BMP -2.19, Wilcoxon p 0.080; leave-one-out t -1.72 to -2.51. Now borderline, not significant at 5%.
- Shifted: cuts +0.80% (t 0.59), increases -0.70% (t -0.77), increases [-5,+5] -2.82% (t -2.06). Firm-only increases N 14: -1.26% (t -1.22), [-5,+5] -4.10% (t -2.90). Outlier run: same 5 days, same 5 events dropped; cuts N 6 +1.59% (t 1.46), increases N 15 -0.76% (t -0.80), [-5,+5] -2.93% (t -2.16). Official-time identical to main.
- Cuts by day -1 +3.10%, increases -1.81%. opec_2025_04_03 unchanged at -12.40% (t -6.09); other 16 increases +0.35% (t 0.44).
- Descriptive, not pre-registered (scratchpad `opec_v11_descriptive.py`, quoted in README as such): 12 OPEC+ events have an attack day 0 in their [-5,+5], 8 increases (5 in [-1,+1]). Without those 8, the other 9 increases are -4.85% on [-5,+5] (t -2.35).
- Small-sample cells not to promote: firm-only holds [-5,+5] t 3.08 (N 7); shifted no_outliers cuts [-1,+1] t 2.00 (N 6). About 70 unadjusted cells across three runs.

### Supply-route attacks (first run 27 Oct, pre-registered; unchanged by v1.1)

- 22 counted attacks (16 pre-war), 17 masked (12 spacing only, 4 no stated time, 1 off-route). All 22 ok on XLE, ITA, GLD. 79 mask day 0s. v1.1 rerun: every results CSV and chart byte-identical; only run info changed (hashes, commit).
- **Primary (XLE [0,+1]): N 22, +0.60%, t 1.02, p 0.321. Null.** No secondary test survives Holm (best XLE [-5,+5] +2.27%, p 0.035, Holm 0.177). Pre-war N 16: nothing significant.
- Descriptive, not pre-registered (quoted in README as such): without attack_2020_11_23 +0.16%; leave-one-out t on XLE [-5,+5] 1.93 to 2.88; [-5,+5] is +1.83% before day 0 and +0.44% after; without attack_2021_03_07 [-5,+5] +2.10% (t 2.01); without the 2 attacks sharing day 0 with an OPEC+ increase +0.52% (t 0.80, N 20); without the 4 attacks sharing [0,+1] with a masked attack +0.41% (t 0.58, N 18).

## Next

1. **README rewrite (new session):** more detail and charts up top; brief given to John 27 Oct, pasted into the new session.
2. **Commit the confound notes, then rerun clean (John):** notes pasted 27 Oct (13 attacks, 5 OPEC+ increases, attack_2021_03_07 'surprise' removed and +8.80%); only confound_note changed. The events hashes in all 4 run info files are now stale: commit, rerun the four studies, check only the run info files change, commit.
3. **events/dates_table.csv** is the v1.0 table (max span 197). A v1.1 version is in the 27 Oct scratchpad (`dates_table_v1.1.csv`, drop its `index` column); copy it over if you want it current.
4. **Primary-source checks:** attack_2026_07_22 (16:00 ET exactly; any earlier report moves day 0 to Wed 22 Jul), attack_2026_03_18 (15:28 ET, 32 min before close; QNA 15:21 has no URL), attack_2019_07_19 (first public report before 16:00 ET?), attack_2019_05_12 (BIMCO time source not linked), mask_2026_08_04 and mask_2026_08_31 (report time vs incident time), mask_2026_07_26 (25 or 26 Jul).
5. **GitHub (John):** description, topics, and a new social preview (needs a script or a hand-made image; current one is OPEC-only, v1.0 numbers, 414 tests).
6. Source a confound_note check for the other large OPEC rows: opec_2020_12_03 (+9.25%), opec_2021_03_04 (+8.80%), opec_2026_04_05 ([-5,+5] -10.86%).
7. OPEC sourcing: Al Jazeera 5 Dec 2019 time zone (opec_2019_12_05), A5 (6 or 7 Dec 2018), the opec_2022_10_05 11:00 official time, Sep 2016 Algiers releases (slugs 495, 496; inside opec_2016_12_10's estimation window, not masked), A14's table, 1B rows 2, 3, 6. Open call 5 (A2 on 24 or 25 May 2017).
8. Saudi unilateral rows from Saudi Energy Ministry statements (5 Jan 2021 first; then remove mask_2021_01_05).
9. Brent robustness check: confirm the calendar check covers a non-NYSE series first.

## Not built yet

- Saudi unilateral subsample report.
- Brent robustness check.

## Built

- Price loader with a frozen cache in `data/prices/` (`prices.load_cached`), simple returns, NYSE calendar check in `run_events`.
- Events loaders: `events/opec_events.csv` (leak times, time_assumed, `--shift-assumed`), mask-only files, `load_supply_route_events` (11-session spacing check).
- Day 0 logic (actual closes, early closes, weekends, holidays) and trading-day windows.
- Market model (OLS with intercept), abnormal returns, CARs, per-event t, calibrated on simulated no-effect events.
- Runner: failed events recorded with reasons, `nearby_events` and `nearby_mask_events`, estimation windows that skip every other event's and mask row's widest window (no cap on look-back), `est_start`, `est_end`, `est_masked_days`; `runner.estimation_dates` for `--dates-only`.
- Across-event tests in `aggregate.py`: cross-sectional t, BMP, Wilcoxon, sign test. Power illustration in `scripts/across_event_demo.py`.
- `scripts/run_opec.py` (main, `--shift-assumed`, `--official-time`, `--dates-only`, `--refresh`; samples all, firm_only, no_outliers) and `scripts/run_supply_route.py` (XLE, ITA, GLD; primary, Holm over five secondary tests, route and escalation subgroups, pre-war sample; no `--refresh`). Shared output code in `src/event_study/reporting.py` (incl. `percent_label` for chart ticks).
- Methodology-reviewer subagent with a Bash allowlist hook (`.claude/hooks/reviewer_bash_guard.py`, tested in `tests/test_reviewer_hook.py`).
- Tests (property-based and fuzz included), Ruff, CI.
