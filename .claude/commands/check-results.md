---
description: Skeptical reading of the latest OPEC+ results, by the methodology-reviewer subagent (restricted by its instructions and a hook)
disable-model-invocation: true
---

Use the Agent tool with subagent_type `methodology-reviewer` and pass it the task below word for word. Don't do the review yourself. When it finishes, give me its report unchanged.

Task:

Read results/opec_results.csv and results/opec_run_info.json (and the `*_official_time` versions if they exist). Report:

- **Counts**: how many events have status "ok" and how many failed, and each failed event's id and error. If the file has no rows, say so and stop after the staleness check.
- **Staleness**: compare `git_commit` and `git_dirty` in the run info with `git log` and `git status`. If src/, scripts/run_opec.py or events/opec_events.csv changed since that commit, say the results may be out of date and should be rerun.
- **Settings**: estimation length, gap, event windows and use_leak from the run info, and whether they match the defaults in DECISIONS.md.
- **Overlap diagnostics**: every event with `est_masked_days` above 0 (with its `est_start` and `est_end`, to show how far back its estimation window reaches) or `nearby_events` above 0, and what that could do to its CAR or t-stat (see the docstring at the top of src/event_study/runner.py).
- **Sample size**: N of ok events overall and per decision_group. Note that saudi_unilateral events are a separate subsample (DECISIONS.md) and the across-event tests need at least 5 ok events. No power target is recorded, so don't judge whether N is enough: report the counts and say plainly that power can't be judged without a recorded target. The events-needed figure printed by scripts/across_event_demo.py is an illustration under assumed numbers, not a target.
- **Skeptical reading**: what the numbers do and don't show. Which events drive any large CARs, whether the sign holds without the largest one, whether known confounds (`confound_note`) sit on those days, and which events need a primary-source check of their date, time or outcome before the number can be trusted. A null result is a valid result; say so if that's what it is.

Extra notes from the user, if any: $ARGUMENTS
