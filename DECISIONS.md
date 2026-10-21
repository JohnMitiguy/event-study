# Decisions

Decision: OPEC+ first pass uses XLE as the security and SPY as the benchmark, with Brent as a later robustness check. Reason: ETF prices avoid futures roll artifacts, and SPY is simple, with the small XLE-in-SPY overlap noted in the README.

Decision: The project targets Python 3.13, set by .python-version and CI. Reason: core data libraries can lag on a brand-new Python version, and compatibility bugs are a distraction on a first project.

Decision: Standing project rules live in CLAUDE.md and each session gets a short task brief. Reason: the agent reads it every session, so rules are not forgotten or retyped.

Decision: Prices come from yfinance with auto_adjust=False using the Adj Close column, and returns are simple daily returns computed from it. Reason: raw Close stays available and nothing depends on a library default that could change.

Decision: The price cache is one CSV per ticker holding full history from 2010-01-01, replaced whole on refresh. Events that need earlier data fail until CACHE_START is moved earlier and the cache is refreshed. Reason: whole-file replacement avoids fake returns at the seam between old and new adjusted prices, and the 2010 start is a known limit on older event types.

Decision: Results come from a frozen price snapshot refreshed only with --refresh, results code reads prices only through load_cached, and each run records data dates, hashes of dates and values, settings and a hash of the events file. Reason: Yahoo revises adjusted prices, so an automatic refresh could change a CAR between runs with no record of why.

Decision: Estimation length, gap and event windows are configurable parameters, not hardcoded. Reason: the 120-day and 10-day choices are defaults we may revisit, and robustness checks need to vary them without rewriting code.

Decision: The estimation window is 120 trading days ending at day -10 (days -129 through -10), and the event windows are [-1,+1] and [-5,+5], all counted by trading-day position. Reason: the gap keeps pre-event run-up and leaked news out of the model, and counting positions avoids calendar-day errors around weekends and holidays.

Decision: The estimation window must end before day 0 and before the start of every event window, so the gap is at least 1. Reason: otherwise a post-event window with a small gap would fit the model on the event's own reaction.

Decision: Window slicing raises when day 0 is missing or a window runs off the data, the parameter checks raise when windows collide, and NaN or infinite returns raise in the market model; windows are never shrunk or shifted. Missing trading days are caught by the calendar check in run_opec.py before slicing, because slicing counts rows. Reason: a silently truncated 60-day estimation window would look like a 120-day regression and quietly weaken every result.

Decision: The returns series is validated against the NYSE calendar before any event is run through the windows. Reason: a single dropped trading day silently shifts every window after it by one row.

Decision: Event time is the earliest credible timed leak (Reuters, Bloomberg or WSJ stating the specific outcome, direction and size for cuts and increases, from named or multiple sources) when one exists, otherwise the official announcement; the official time is run as a robustness check. Day 0 is the event date if that date is a trading session and the event time is before that day's actual close (1pm on early-close days, and a time exactly at the close rolls forward), otherwise the next session. Reason: markets react when information arrives, and early closes, weekends, holidays and unscheduled closures change when the market can first react. The rule is fixed before seeing returns so the leak time cannot be tuned to the result.

Decision: Event day logic only accepts timezone-aware datetimes in America/New_York. Reason: naive or fixed-offset timestamps cause silent off-by-one-day errors around daylight saving.

Decision: An event is a formal group-level OPEC+ production decision, including emergency meetings; monitoring-only meetings that decide nothing are excluded, and unilateral moves are tagged instead of mixed in. Reason: the study measures reactions to production decisions, and mixing other kinds of news would blur the average.

Decision: Each event carries a decision_group of ministerial (a full OPEC+ ministerial meeting), voluntary_group (the subset making voluntary adjustments) or saudi_unilateral (an action by Saudi Arabia alone); Saudi unilateral events are reported as a separate subsample, not averaged into the main result. Reason: they are a different kind of shock from group decisions, and a blended average would describe neither.

Decision: A row needs an announcement time precise enough to place the event against the close. When the source gives only a date, the row is kept with a representative time and a note explaining why every plausible time gives the same day 0; events where the date alone cannot settle day 0 are excluded and listed with reasons in the README. Leak times must be exact and come from a timestamped source. Reason: requiring exact times would drop most events and bias the sample, while day 0 only depends on the time when the announcement falls near the close.

Decision: An event with a leak known only by date uses the official announcement time and is logged in the README with a note, not dropped. Reason: dropping it would silently shrink the sample, and the official time is the conservative fallback.

Decision: The events CSV has a confound_note column, and the file lives in a tracked events/ folder, not the gitignored data/ folder. Reason: market-wide confounds need to be recorded when each event is entered, and the hand-built event list is part of the project, not downloaded data.

Decision: Main results keep all data; a robustness run drops events whose estimation window contains any of the five largest absolute market-model residual days (XLE return minus beta times SPY return). Reason: extreme residual days inflate residual variance and distort beta, ranking by residual removes market-wide days that beta already handles, and fixing the rule before seeing results avoids data snooping.

Decision: The market model is an OLS regression of security returns on benchmark returns with an intercept, using the estimation window only, with residual variance computed on n-2 degrees of freedom. Reason: it is the standard specification, and the n-2 divisor reflects the two estimated parameters.

Decision: The per-event test statistic is CAR divided by residual std times the square root of window length, ignoring estimation error in alpha and beta. Reason: with 120 observations the omitted error is small; simulated rejection rates at the 5% level were 5.1% for [-1,+1] and 6.6% for [-5,+5], and the across-event test is the headline inference.

Decision: A test statistic is accepted only if a 1000-event simulation with no planted effect gives an absolute mean of at most 0.1, a standard deviation between 0.9 and 1.15, and 3 to 8 percent of statistics beyond +/-1.96, for both windows, enforced in tests/test_market_model.py. Reason: a statistic that fires too often on pure noise would flatter every real result, and the check uses simulated normal noise, so real returns with fatter tails may behave somewhat worse.

Decision: The primary across-event test is the cross-sectional t-test on [-1,+1] CARs, with the standardized-CAR (BMP) test and Wilcoxon as robustness checks; the sign test is reported but not relied on. Reason: all four calibrated correctly in simulation, but the sign test needs 40 to 50 percent more events for the same power, and fixing the choice in advance avoids picking whichever test comes out significant.

Decision: Across-event tests need at least 5 ok events, compare BMP to a t distribution with N-1 degrees of freedom, drop zero CARs in the sign test, and do not adjust for overlapping events. Reason: these are the simplest defensible choices, and overlapping windows make the tests reject too often, which is why overlap diagnostics are reported and listed as a limitation.

Decision: Bad-input errors raise ValueError (Ruff's TRY004 is ignored for this). Data problems tied to one event raise EventDataError, a ValueError subclass, and run_events is the only code that catches it. Reason: a single base type keeps error handling consistent, and catching only the subclass means a bug elsewhere that raises ValueError stops the run instead of showing up as one more failed event.

Decision: File-level problems in the events CSV (unreadable, not UTF-8, NUL byte, extra fields, missing column) reject the file at the first one found; otherwise every bad row is listed in one error and nothing is loaded. The runner records an EventDataError as a failed event and continues. Reason: a bad CSV is a data-entry mistake you should fix, but an event with too little price history is a legitimate result to report.

Decision: The events loader rejects NUL bytes and event years outside the calendar range, and turns any read failure into a ValueError that names the file. Reason: a hand-edited data file should fail with a message you can act on, and text must never load truncated without a warning.

Decision: A benchmark with no variance in an estimation window stops the run, while a near-perfect security fit is recorded as a failed event. Reason: a flat benchmark signals a broken series that would affect many events, but one security can legitimately misbehave on its own.

Decision: run_opec.py stops, instead of logging failed events, if the trading-day check fails or an event needs prices after the cached data ends (rerun with --refresh). Reason: misaligned or missing data would give wrong numbers without any error.

Decision: The runner reports overlap diagnostics per event and applies no exclusions, and the treatment of overlapping estimation windows is decided after the pilot, before the full sample is run. Reason: with a handful of events overlap is rare, and seeing the diagnostics on the real list is better than guessing a rule.

Decision: confound_note records only specific, dated, sourced items inside [-1,+1] that plausibly hit energy differently from the broad market; market backdrop is left out and flagged events stay in the main run. Reason: the market model already removes market-wide moves, and excluding on judgment calls invites cherry-picking.

Decision: A pause or delay of scheduled increases is tagged hold, even when the same release includes a small pre-announced increase. Reason: tagging it increase would pool a supply-tightening surprise with real loosening events and wash out the cut and increase tests.

## Not built yet
- Official-time robustness run (the --official-time flag exists, but the run has not been done)
- Saudi unilateral subsample report
- Outlier-exclusion robustness run
- Brent robustness check
- Calling the across-event tests from run_opec.py