# Status

Last updated: 2026-10-27 (review and cleanup of the supply-route work)

## Where we are

- **v1.0.0 released 26 Oct 2026** (tag on 3ad1bed): https://github.com/JohnMitiguy/event-study/releases/tag/v1.0.0. Repo is public, with description, topics, social preview and MIT license. The description, topics and social preview still describe OPEC+ only.
- **Both event types are run** on clean commit c0466d1: every `*_run_info*.json` says `git_dirty: false`. Prices through 2026-10-15 (ITA and GLD cached to 2026-10-26, trimmed to SPY's dates).
- Tests (27 Oct, after the cleanup): ruff clean, 446 passed, 2 skipped (reviewer-hook test: no bash found from pytest's shell).

### OPEC+ decisions (v1.0.0, results fixed)

- 37 events (main, `--shift-assumed`, `--official-time`), all ok.
- Headline (cross-sectional t, [-1,+1]): cuts N 7, +1.51%, t 1.56; increases N 17, -0.51%, t -0.49. Both null. Increases on [-5,+5]: -3.26%, t -2.38 (BMP -2.47, Wilcoxon p 0.045), t -2.03 to -2.79 when any one event is dropped. Most of the cut move is before day 0 (+3.10% by day -1).
- Shifted run: cuts +0.80% (t 0.57), increases -0.82% (t -0.90), increases [-5,+5] -3.33% (t -2.42). Firm-only: cuts 3 (too few), increases N 14 -1.37% (t -1.34), [-5,+5] -4.55% (t -3.19). Official-time run identical to main.
- Outlier run (top 5 residual days, one full-sample beta): 5 events dropped; cuts N 6 +1.61% (t 1.41), increases N 15 -0.88% (t -0.93), [-5,+5] -3.34% (t -2.44).
- opec_2025_04_03 [-1,+1] -12.40% (t -6.09), on the Apr 2025 tariff selloff (confound_note filled). Without it, the other 16 increases average +0.23% (t 0.29).
- OPEC+ runs do not mask attack windows (DECISIONS.md); that waits for a v1.1 rerun.

### Supply-route attacks (first run 27 Oct, pre-registered)

- 22 counted attacks (16 pre-war), 17 masked (12 spacing only, 4 no stated time, 1 off-route, per the `reason` column; earlier STATUS lines said 13/3/1). All 22 ok on XLE, ITA, GLD. 79 mask day 0s.
- **Primary (XLE [0,+1]): N 22, +0.60%, t 1.02, p 0.321. Null.** No secondary test survives Holm (best XLE [-5,+5] +2.27%, p 0.035, Holm 0.177). Pre-war N 16: nothing significant.
- Descriptive, not pre-registered (scratchpad only, quoted in the README as such): without attack_2020_11_23 +0.16%; leave-one-out t on XLE [-5,+5] 1.93 to 2.88; [-5,+5] is +1.83% before day 0 and +0.44% after; without attack_2021_03_07 [-5,+5] +2.10% (t 2.01); without the 2 attacks sharing day 0 with an OPEC+ increase +0.52% (t 0.80, N 20); without the 4 attacks sharing [0,+1] with a masked attack +0.41% (t 0.58, N 18).
- confound_note on attack_2020_11_23 added after the run (allowed by DECISIONS.md, no output reads it).
- Clean rerun of all four runs on c0466d1 (chart axis fix): every results CSV byte-identical to the first run on 37a0ce4.

## Review of 27 Oct work (methodology-reviewer on 5 commits, plus check-results and check-events adapted to the supply-route files)

- No number in any result is wrong or stale. Every README supply-route number matches the results CSVs; Holm recomputes exactly; events hash matches the committed CSV (after CRLF checkout, see below).
- README fixed this session: "surprise OPEC+ hold" (unsourced; opec_2021_03_04 has no surprise_flag) changed to "OPEC+ hold"; new caveats for OPEC+ decisions inside 7 attack windows and masked attacks inside 4 attacks' [0,+1]; pre-war line notes the GLD red_sea subgroup; reviewer-command lines say they are OPEC-only.

## Next

1. **Events CSV edits (John):** confound_note for attack_2025_07_06 and attack_2026_03_01 (same day 0 as an OPEC+ increase); remove "surprise" from attack_2021_03_07's confound_note; decide on mask_2026_03_19 and mask_2026_07_26 (`time_assumed` 0 against DECISIONS.md line 129: flag them, or paste the date-only Decision line). None changes a number.
2. **DECISIONS.md (John):** "Not built yet" still lists the official-time run (done 26 Oct). Draft lines given 27 Oct: escalation reasons, subgroups unadjusted, pre-war ET date, attack confound_note window, date-only mask rows.
3. **Primary-source checks:** attack_2026_07_22 (16:00 ET exactly; any earlier report moves day 0 to Wed 22 Jul), attack_2026_03_18 (15:28 ET, 32 min before close; QNA 15:21 has no URL), attack_2019_07_19 (first public report before 16:00 ET?), attack_2019_05_12 (BIMCO time source not linked), mask_2026_08_04 and mask_2026_08_31 (report time vs incident time), mask_2026_07_26 (25 or 26 Jul).
4. **Line endings:** event CSVs are checked out CRLF here (core.autocrlf true) and LF on Linux/CI, so `events_file_sha256` differs by machine. Fix needs John's OK (a `.gitattributes`, or hashing with normalized newlines).
5. **Reviewer commands:** /check-results, /check-events and /audit-decisions are OPEC-only; extending them needs John's OK.
6. **GitHub (John):** update the repo description, topics and social preview (still OPEC-only, says 414 tests).
7. **v1.1 (not started):** OPEC+ runs mask attack windows; plan given 27 Oct.
8. Source a confound_note check for the other large OPEC rows: opec_2020_12_03 (+9.06%), opec_2021_03_04 (+8.73%), opec_2026_04_05 ([-5,+5] -12.22%).
9. OPEC sourcing: Al Jazeera 5 Dec 2019 time zone (opec_2019_12_05), A5 (6 or 7 Dec 2018), the opec_2022_10_05 11:00 official time, Sep 2016 Algiers releases (slugs 495, 496; inside opec_2016_12_10's estimation window, not masked), A14's table, 1B rows 2, 3, 6. Open call 5 (A2 on 24 or 25 May 2017).
10. Saudi unilateral rows from Saudi Energy Ministry statements (5 Jan 2021 first; then remove mask_2021_01_05).
11. Brent robustness check: confirm the calendar check covers a non-NYSE series first.

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
