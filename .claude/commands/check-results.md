---
description: Skeptical reading of the latest OPEC+ and supply-route results, by the methodology-reviewer subagent (restricted by its instructions and a hook)
disable-model-invocation: true
---

Use the Agent tool with subagent_type `methodology-reviewer` and pass it the task below word for word. Don't do the review yourself. When it finishes, give me its report unchanged.

Task:

Read the OPEC+ files and the supply-route files, each if present:

- OPEC+: results/opec_results.csv and results/opec_run_info.json (and the `*_official_time` versions if they exist).
- Supply-route attacks: results/supply_route_results.csv (one row per attack and security), results/supply_route_across_event.csv and results/supply_route_run_info.json.

If neither set is present, say so and stop. Report each item below for each run that is present, under an OPEC+ heading and a supply-route heading:

- **Counts**: how many events have status "ok" and how many failed (for attacks, per security), and each failed event's id and error. If a results file has no rows, say so and stop that run after the staleness check.
- **Staleness**: compare `git_commit` and `git_dirty` in each run info with `git log` and `git status`. Each run has its own inputs. OPEC+: src/, scripts/run_opec.py, events/opec_events.csv and events/opec_mask_only.csv, plus events/supply_route_events.csv and events/supply_route_mask_only.csv once results/opec_run_info*.json records hashes for them (the v1.1 rerun that masks attack windows). Supply-route: src/, scripts/run_supply_route.py, events/supply_route_events.csv, events/supply_route_mask_only.csv, events/opec_events.csv and events/opec_mask_only.csv. If any input changed since that run's commit, say the results may be out of date and should be rerun.
- **Settings**: compare each run info with DECISIONS.md. OPEC+: estimation length, gap, event windows and use_leak against the defaults. Supply-route: estimation length, gap, event windows ([0,+1] and [-5,+5]), use_leak, min_spacing (11), securities (XLE, ITA, GLD vs SPY), expected_sign (positive for all three), the primary test (XLE, [0,+1], all attacks, cross-sectional t), group_columns (route, escalation) and pre_war_before (2026-02-28).
- **Overlap diagnostics**: every event with `est_masked_days` above 0 (with its `est_start` and `est_end`, to show how far back its estimation window reaches) or `nearby_events` or `nearby_mask_events` above 0, and what that could do to its CAR or t-stat (see the docstring at the top of src/event_study/runner.py).
- **Sample size**: OPEC+: N of ok events overall, per decision_group and per direction. Note that saudi_unilateral events are a separate subsample (DECISIONS.md). Attacks: N of ok events per security, overall, per route, per escalation and in the pre_war sample. Subgroups are tested only with at least 5 ok events. The across-event tests need at least 5 ok events. No power target is recorded, so don't judge whether N is enough: report the counts and say plainly that power can't be judged without a recorded target. The events-needed figure printed by scripts/across_event_demo.py is an illustration under assumed numbers, not a target.
- **Skeptical reading**: what the numbers do and don't show. Which events drive any large CARs, whether the sign holds without the largest one, whether known confounds (`confound_note`) sit on those days, and which events need a primary-source check of their date, time or outcome before the number can be trusted. For attacks, also:
  - Recompute `p_holm` in results/supply_route_across_event.csv from `cs_p` of the five secondary rows (sample all, group all, role secondary, tested). Holm: sort the five p-values from smallest to largest, multiply the k-th smallest by (6 - k), keep each value at least as large as the one before it, and cap at 1. Flag any row that differs, and any other row with a `p_holm`.
  - For each attack, list OPEC+ day 0s (from results/opec_results.csv) and masked attacks (from events/supply_route_mask_only.csv) that fall inside its [-5,+5], counting trading days from its day0. Flag any its `confound_note` does not list (DECISIONS.md requires it). Say which ones you could not place.
  For OPEC+, list attacks (counted or masked) whose day 0 falls inside an OPEC+ event's [-5,+5], and whether the README discloses them.
  A null result is a valid result; say so if that's what it is.

Tag each numbered finding **Must fix** (wrong or misleading now), **Should fix** (a real risk or gap, not urgent) or **Note** (worth knowing, no action needed).

Extra notes from the user, if any: $ARGUMENTS
