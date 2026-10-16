
# Event study framework

Python 3.13 (uv, pandas, statsmodels) framework measuring market reactions to geopolitical events. Market model: regress a security on a benchmark over a pre-event estimation window, abnormal return = actual minus predicted, sum into CARs over short windows, average across events, t-test. Null results get reported honestly.

First event type: OPEC+ decisions (XLE vs SPY). Later: terrorist attacks, tariffs, OFAC sanctions, Red Sea.

Read DECISIONS.md before changing any methodology.

## Method conventions
- Simple daily returns from adjusted close.
- Event day 0 = first trading day the market could react. Times at or after that day's actual close (4pm ET, or 1pm on early-close days), weekends and holidays roll forward.
- Event time = leak_datetime_et if present, else announcement_datetime_et. Day 0 is computed from event time. Untimed leaks are not used.
- Windows count trading days, never calendar days.
- Estimation window must end before day 0 and before every event window starts. No look-ahead.
- Results code reads prices only through prices.load_cached.
- Estimation length, gap, and event windows are parameters, never hardcoded.
- Any averaging across events must count N from status "ok" only and report every excluded event with its reason.

## Working rules
- The user is new to pandas. Keep functions small, put assumptions in docstrings, explain anything non-obvious.
- For anything beyond a small fix, show a short plan and wait for approval.
- Never invent events, dates, or sources. The user fills the events CSV from primary sources.
- Flag assumptions instead of silently picking one.
- Do not commit. The user reviews diffs and commits.
- At the end of each session, update STATUS.md.

- Before saying a task is done, run `uv run ruff check` and `uv run pytest`, and report both results.
- Prefer the simplest approach. Don't add files, dependencies, or features beyond what the brief names without asking.
- For choices that don't change results (file formats, names, paths), pick the simplest option and note it in one line instead of asking.

## Environment
- Windows, PowerShell. Use pathlib for paths.
- Add packages with uv add. Run tests with uv run pytest.
- Code in src/event_study/, tests in tests/, downloaded data in data/ (gitignored).