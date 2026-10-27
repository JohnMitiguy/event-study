---
description: Check every DECISIONS.md entry against the code, by the methodology-reviewer subagent (restricted by its instructions and a hook)
disable-model-invocation: true
---

Use the Agent tool with subagent_type `methodology-reviewer` and pass it the task below word for word. Don't do the audit yourself. When it finishes, give me its report unchanged.

Task:

Audit DECISIONS.md against the code. For each entry, in order, give a one-line verdict: **matches**, **wrong** (the code does something else) or **stale** (it describes something that no longer exists or has moved). Cite the file:line that implements it, or that contradicts it. Check the "Not built yet" list against the code too.

Then list:

1. Entries that are wrong or stale, with what the code actually does.
2. Behavior in src/event_study/, scripts/run_opec.py and scripts/run_supply_route.py that has no entry but is a real methodology choice (it could change a number in a result). For each, suggest a one-line entry in the form `Decision: X. Reason: Y.` Leave the reason as "Reason: (needs your input)" if the code doesn't make it clear.

Don't edit DECISIONS.md.

Tag each numbered finding **Must fix** (wrong or misleading now), **Should fix** (a real risk or gap, not urgent) or **Note** (worth knowing, no action needed).

Extra notes from the user, if any: $ARGUMENTS
