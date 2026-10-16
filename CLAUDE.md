
# Event study framework

Python 3.13 (uv, pandas, statsmodels) framework measuring market reactions to geopolitical events. Market model: regress a security on a benchmark over a pre-event estimation window, abnormal return = actual minus predicted, sum into CARs over short windows, average across events, t-test. Null results get reported honestly.

First event type: OPEC+ decisions (XLE vs SPY). Later: terrorist attacks, tariffs, OFAC sanctions, Red Sea.

Read DECISIONS.md before changing any methodology.

## Method conventions
- Simple daily returns from adjusted close.
- Event day 0 = first trading day the market could react (after 4pm ET, weekends, holidays roll forward).
- Windows count trading days, never calendar days.
- Estimation window must end before the event window starts. No look-ahead.
- Estimation length, gap, and event windows are parameters, never hardcoded.

## Working rules
- The user is new to pandas. Keep functions small, put assumptions in docstrings, explain anything non-obvious.
- For anything beyond a small fix, show a short plan and wait for approval.
- Never invent events, dates, or sources. The user fills the events CSV from primary sources.
- Flag assumptions instead of silently picking one.
- Do not commit. The user reviews diffs and commits.

## Environment
- Windows, PowerShell. Use pathlib for paths.
- Add packages with uv add. Run tests with uv run pytest.
- Code in src/event_study/, tests in tests/, downloaded data in data/ (gitignored).