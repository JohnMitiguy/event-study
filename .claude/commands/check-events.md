---
description: Validate events/opec_events.csv against the README rules, by the methodology-reviewer subagent (restricted by its instructions and a hook)
disable-model-invocation: true
---

Use the Agent tool with subagent_type `methodology-reviewer` and pass it the task below word for word. Don't do the check yourself. When it finishes, give me its report unchanged.

Task:

Validate events/opec_events.csv against the rules in README.md (section "Events CSV") and DECISIONS.md. If the file has no rows, say so and stop. For every row check:

- `source_url` is present.
- Rows with a date-only source have `date-only` in `notes` plus the reason every plausible time gives the same day 0. Flag representative times near the close (roughly 3pm to 5pm ET), or on an early-close day, where the reason doesn't settle day 0.
- Leak fields: `leak_datetime_et` and `leak_source_url` are both filled or both blank, and the leak is earlier than `announcement_datetime_et`.
- `decision_group` is one of ministerial, voluntary_group, saudi_unilateral, and `direction` is one of cut, hold, increase. `surprise_flag` is 0, 1 or blank.
- Times are `YYYY-MM-DD HH:MM` with no UTC offset, and `notes` records the source's original time zone where the source wasn't Eastern.
- Duplicate `event_id`s or duplicate dates, and events close enough together that their windows overlap.
- The README "Excluded events" table: every untimed leak mentioned in `notes` is listed there.

You have no web access, so you cannot open source_url. End with a table of every row whose date, time or outcome still needs checking against its primary source: event_id, what to check (date, time, time zone conversion, outcome, leak time), and the URL to open. Don't judge whether a date or outcome is correct from memory.

Extra notes from the user, if any: $ARGUMENTS
