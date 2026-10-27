---
description: Validate the OPEC+ and supply-route events CSVs against the README rules, by the methodology-reviewer subagent (restricted by its instructions and a hook)
disable-model-invocation: true
---

Use the Agent tool with subagent_type `methodology-reviewer` and pass it the task below word for word. Don't do the check yourself. When it finishes, give me its report unchanged.

Task:

Validate events/opec_events.csv against the rules in README.md (section "Events CSVs", OPEC+ part) and DECISIONS.md. Then validate events/supply_route_events.csv and events/supply_route_mask_only.csv against README.md (section "Supply-route attacks" under "Events CSVs", and "What counts as an attack") and the attack entries in DECISIONS.md (from "A supply-route attack event is..." on). If a file has no rows, say so and skip its checks.

In events/opec_events.csv, for every row check:

- `source_url` is present.
- Rows with a date-only source have `date-only` in `notes` plus the reason every plausible time gives the same day 0. Flag representative times near the close (roughly 3pm to 5pm ET), or on an early-close day, where the reason doesn't settle day 0.
- Leak fields: `leak_datetime_et` and `leak_source_url` are both filled or both blank, and the leak is earlier than `announcement_datetime_et`.
- `decision_group` is one of ministerial, voluntary_group, saudi_unilateral, and `direction` is one of cut, hold, increase. `surprise_flag` is 0, 1 or blank.
- Times are `YYYY-MM-DD HH:MM` with no UTC offset, and `notes` records the source's original time zone where the source wasn't Eastern.
- Duplicate `event_id`s or duplicate dates, and events close enough together that their windows overlap.
- The README "Excluded events" table: every untimed leak mentioned in `notes` is listed there.

In events/supply_route_events.csv (counted attacks) and events/supply_route_mask_only.csv (masked attacks), check:

- `source_url` is present on every row in both files.
- Counted rows: `event_id` is `attack_YYYY_MM_DD` from the local date of the attack, `event_type` is supply_route, `route` is one of gulf_facility, red_sea, hormuz, and `escalation` is one of first_attack, named_escalation. The leak columns and `surprise_flag` are blank. `notes` gives a basis for the escalation label that fits the DECISIONS.md list (deaths, a sinking or seizure, a new country or facility hit, a return after a lull of 30 days or more, or a source calling it an escalation).
- Spacing: counted attacks are at least 11 trading days apart, day 0 to day 0. Every masked row's `reason` says why it is masked (inside that gap, outside the three routes, or no stated time).
- Timestamps: times are `YYYY-MM-DD HH:MM` Eastern with no UTC offset. `notes` gives the source time exactly as stated and the conversion to Eastern. Check the arithmetic: Gulf states and Yemen don't change their clocks, so their gap to Eastern is one hour smaller while the US is on daylight saving (Saudi time is 8 hours ahead of EST and 7 ahead of EDT). A time with no zone is read as local time at the attack site. When a source gives several times, the earliest is used.
- `time_assumed`: blank or 0 on every counted row, since a counted attack needs a stated time. A counted row with no stated time in `notes` is a finding, even if its date alone pins day 0. On mask rows, 1 when there is no stated time or the times conflict; a date-only mask row with 0 is allowed only when its date alone pins day 0 (weekend or overnight local time), and `notes` or `reason` should say so.
- `confound_note` on counted rows lists specific, dated, sourced items inside the attack's [-5,+5], including any OPEC+ decision (events/opec_events.csv) or masked attack whose day 0 falls there. Flag ones that appear to be missing. A note added after a run should say when it was added.
- Duplicate `event_id`s across both files, and a masked attack that is also a counted row.
- The README "Masked attacks" table lists every row of the mask-only file, and nothing else.

You have no web access, so you cannot open source_url. End with a table of every row whose date, time or outcome still needs checking against its primary source: file, event_id, what to check (date, time, time zone conversion, outcome, leak time, route, escalation), and the URL to open. Don't judge whether a date or outcome is correct from memory.

Tag each numbered finding **Must fix** (wrong or misleading now), **Should fix** (a real risk or gap, not urgent) or **Note** (worth knowing, no action needed).

Extra notes from the user, if any: $ARGUMENTS
