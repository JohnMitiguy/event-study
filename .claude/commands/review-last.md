---
description: Methodology review of the last commit, by the read-only methodology-reviewer subagent
disable-model-invocation: true
---

Use the Agent tool with subagent_type `methodology-reviewer` and pass it the task below word for word. Don't do the review yourself. When it finishes, give me its report unchanged.

Task:

Review the most recent commit. Run `git log -5 --stat` and `git diff HEAD~1`. Also run `git status` and mention any uncommitted changes, but don't review them unless they touch methodology. Report:

- What changed, in a few lines.
- Whether methodology changed (windows, day 0 rules, event time, the market model, test statistics, aggregation, exclusions, data handling) without a matching DECISIONS.md entry in the same commit.
- Whether tests cover each behavior change: name the test file and test, or say none does.
- Anything that could silently change a result: a CAR, a t-stat, N, or which events count as ok.

Extra notes from the user, if any: $ARGUMENTS
