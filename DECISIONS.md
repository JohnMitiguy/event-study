# Decisions

Decision: OPEC+ first pass uses XLE as the security and SPY as the benchmark, with Brent as a later robustness check. Reason: ETF prices avoid futures roll artifacts, and SPY is simple, with the small XLE-in-SPY overlap noted in the README.

Decision: The project targets Python 3.13, set by .python-version and CI. Reason: core data libraries can lag on a brand-new Python version, and compatibility bugs are a distraction on a first project.

Decision: Standing project rules live in CLAUDE.md and each session gets a short task brief. Reason: the agent reads it every session, so rules are not forgotten or retyped.

Decision: Prices come from yfinance with auto_adjust=False using the Adj Close column, and returns are simple daily returns computed from it. Reason: raw Close stays available and nothing depends on a library default that could change.

Decision: The price cache is one CSV per ticker holding full history from 2010-01-01, replaced whole on refresh. Events that need earlier data fail until CACHE_START is moved earlier and the cache is refreshed. Reason: whole-file replacement avoids fake returns at the seam between old and new adjusted prices, and the 2010 start is a known limit on older event types.

Decision: Results come from a frozen price snapshot refreshed only with --refresh, results code reads prices only through load_cached, and each run records data dates, hashes of dates and values, settings and a hash of the events file. Reason: Yahoo revises adjusted prices, so an automatic refresh could change a CAR between runs with no record of why.

Decision: Estimation length, gap and event windows are configurable parameters, not hardcoded. Reason: the 120-day and 10-day choices are defaults we may revisit, and robustness checks need to vary them without rewriting code.

Decision: The estimation window is 120 trading days up to day -10 (days -129 through -10 when no other event's window falls in it; see the skipping rule), and the event windows are [-1,+1] and [-5,+5], all counted by trading-day position. Reason: the gap keeps pre-event run-up and leaked news out of the model, and counting positions avoids calendar-day errors around weekends and holidays.

Decision: The estimation window must end before day 0 and before the start of every event window, so the gap is at least 1. Reason: otherwise a post-event window with a small gap would fit the model on the event's own reaction.

Decision: Window slicing raises when day 0 is missing or a window runs off the data (including an estimation window that reaches back past the first row after skipping other events' days), the parameter checks raise when windows collide, and NaN or infinite returns raise in the market model; windows are never shrunk, and the estimation window moves back only to replace skipped days, with est_start, est_end and est_masked_days reported. Missing or non-session dates in a return series are caught by run_events, which checks both series against the NYSE calendar before any event is sliced, because slicing counts rows. Reason: a silently truncated 60-day estimation window would look like a 120-day regression and quietly weaken every result.

Decision: The returns series is validated against the NYSE calendar before any event is run through the windows. Reason: a single dropped trading day silently shifts every window after it by one row.

Decision: Event time is the earliest credible timed leak (Reuters, Bloomberg or WSJ stating the specific outcome, direction and size for cuts and increases, from named or multiple sources) when one exists, otherwise the official announcement; the official time is run as a robustness check. Day 0 is the event date if that date is a trading session and the event time is before that day's actual close (1pm on early-close days, and a time exactly at the close rolls forward), otherwise the next session. Reason: markets react when information arrives, and early closes, weekends, holidays and unscheduled closures change when the market can first react. The rule is fixed before seeing returns so the leak time cannot be tuned to the result.

Decision: Event day logic only accepts timezone-aware datetimes in America/New_York. Reason: naive or fixed-offset timestamps cause silent off-by-one-day errors around daylight saving.

Decision: An event is a formal group-level OPEC+ production decision, including emergency meetings; monitoring-only meetings that decide nothing are excluded, and unilateral moves are tagged instead of mixed in. Reason: the study measures reactions to production decisions, and mixing other kinds of news would blur the average.

Decision: Each event carries a decision_group of ministerial (a full OPEC+ ministerial meeting), voluntary_group (the subset making voluntary adjustments) or saudi_unilateral (an action by Saudi Arabia alone); Saudi unilateral events are reported as a separate subsample, not averaged into the main result. Reason: they are a different kind of shock from group decisions, and a blended average would describe neither.

Decision: A row needs one of three things: an announcement time, a date where every plausible time gives the same day 0, or the time_assumed flag. A date-only row of the second kind (weekends, holidays, or a meeting that a timed source shows ended well inside the session) is kept with a representative time and a note saying why. A weekday event with no timed source is handled by the time_assumed rule below, not excluded. Leak times must be exact and come from a timestamped source. Reason: requiring exact times would drop about 40% of the candidate events and bias the sample, while day 0 only depends on the time when the announcement falls near the close.

Decision: An event with a leak known only by date uses the official announcement time and is logged in the README with a note, not dropped. Reason: dropping it would silently shrink the sample, and the official time is the conservative fallback.

Decision: The events CSV has a confound_note column, and the file lives in a tracked events/ folder, not the gitignored data/ folder. Reason: market-wide confounds need to be recorded when each event is entered, and the hand-built event list is part of the project, not downloaded data.

Decision: Main results drop no events for outliers; a robustness run drops events whose estimation days (the days actually fitted, not the span from est_start to est_end) contain any of the five largest absolute market-model residual days (XLE return minus beta times SPY return), filtering the results of the full run rather than the events table. Reason: extreme residual days inflate residual variance and distort beta, ranking by residual removes market-wide days that beta already handles, and fixing the rule before seeing results avoids data snooping.

Decision: The market model is an OLS regression of security returns on benchmark returns with an intercept, using the estimation window only, with residual variance computed on n-2 degrees of freedom. Reason: it is the standard specification, and the n-2 divisor reflects the two estimated parameters.

Decision: The per-event test statistic is CAR divided by residual std times the square root of window length, ignoring estimation error in alpha and beta. Reason: with 120 observations the omitted error is small; simulated rejection rates at the 5% level were 5.1% for [-1,+1] and 6.6% for [-5,+5], and the across-event test is the headline inference.

Decision: A test statistic is accepted only if a 1000-event simulation with no planted effect gives an absolute mean of at most 0.1, a standard deviation between 0.9 and 1.15, and 3 to 8 percent of statistics beyond +/-1.96, for both windows, enforced in tests/test_market_model.py. Reason: a statistic that fires too often on pure noise would flatter every real result, and the check uses simulated normal noise, so real returns with fatter tails may behave somewhat worse.

Decision: The primary across-event test is the cross-sectional t-test on [-1,+1] CARs, with the standardized-CAR (BMP) test and Wilcoxon as robustness checks; the sign test is reported but not relied on. Reason: all four calibrated correctly in simulation, but the sign test needs 40 to 50 percent more events for the same power, and fixing the choice in advance avoids picking whichever test comes out significant.

Decision: Across-event tests need at least 5 ok events, compare BMP to a t distribution with N-1 degrees of freedom, drop zero CARs in the sign test, and do not adjust for overlapping events. Reason: these are the simplest defensible choices, and overlapping windows make the tests reject too often, which is why overlap diagnostics are reported and listed as a limitation.

Decision: Bad-input errors raise ValueError (Ruff's TRY004 is ignored for this). Data problems tied to one event raise EventDataError, a ValueError subclass, and run_events is the only code that catches it. Reason: a single base type keeps error handling consistent, and catching only the subclass means a bug elsewhere that raises ValueError stops the run instead of showing up as one more failed event.

Decision: File-level problems in the events CSV (unreadable, not UTF-8, NUL byte, extra fields, missing column) reject the file at the first one found; otherwise every bad row is listed in one error and nothing is loaded. The runner records an EventDataError as a failed event and continues. Reason: a bad CSV is a data-entry mistake you should fix, but an event with too little price history is a legitimate result to report.

Decision: The events loader rejects NUL bytes and event years outside the calendar range, and turns any read failure into a ValueError that names the file. Reason: a hand-edited data file should fail with a message you can act on, and text must never load truncated without a warning.

Decision: A benchmark with no variance in an estimation window stops the run, while a near-perfect security fit is recorded as a failed event. Reason: a flat benchmark signals a broken series that would affect many events, but one security can legitimately misbehave on its own.

Decision: run_events stops, instead of logging a failed event, if the trading-day check fails, and run_opec.py stops if an event needs prices after the cached data ends (rerun with --refresh). Reason: misaligned or missing data would give wrong numbers without any error.

Decision: The runner drops no events for overlap: estimation-window overlap is handled by the skipping rule, and nearby_events (events whose widest windows share a day) is reported. Reason: dropping overlapping events would shrink a small sample, and the diagnostic shows where CARs measure the same days.

Decision: confound_note records only specific, dated, sourced items inside [-1,+1] that plausibly hit energy differently from the broad market; market backdrop is left out and flagged events stay in the main run. Reason: the market model already removes market-wide moves, and excluding on judgment calls invites cherry-picking.

Decision: A pause or delay of scheduled increases is tagged hold, even when the same release includes a small pre-announced increase. Reason: tagging it increase would pool a supply-tightening surprise with real loosening events and wash out the cut and increase tests.

Decision: Failed events still mask other events' estimation windows; if day -10 is masked the window ends on the latest unmasked day before it; there is no cap on how far back the window reaches yet; only earlier events mask later ones. Reason: the market reacted whether or not an event's own regression ran, a cap will be chosen from event dates before any CARs are read, and a later event cannot be known when an earlier one is estimated.

Decision: Each event's estimation window leaves out every trading day inside another event's widest configured event window (all other rows of the same events table, ok or failed; not their run-up days, not events outside the table) and reaches further back to keep est_length days. Reason: those days carry another event's reaction, which would inflate resid_std and bend alpha and beta, and a fixed est_length keeps every regression the same size.

Decision: Subsamples and robustness exclusions (Saudi unilateral, outlier) filter the results of the full run; the events table is never cut before run_events. Reason: removing an event from the table changes later events' estimation windows.

Decision: The official-time run takes its skipped days from its own day 0s, so each run is a complete specification on its own. Reason: a leak-versus-official difference moves a neighbour's skipped days by about a day, and holding the main run's skips fixed would make it an inconsistent hybrid.

Decision: An event is a formal group-level OPEC+ production decision that changes the schedule of production levels versus the last announced one (a new cut, increase, extension, pause, delay or reversal); releases that only implement or reaffirm an already-announced step are not events. Reason: the market reacts to new information, and counting routine confirmations adds events with nothing to measure and packs overlapping windows into the sample.

Decision: The OPEC+ sample starts at the first joint OPEC and non-OPEC meeting in December 2016. Reason: the framework studies OPEC+ decisions, and earlier OPEC-only decisions came from a different institution.

Decision: New OPEC+ event ids use the pattern opec_YYYY_MM_DD, and the three pilot ids are renamed to match. Reason: two events share May 2025 (3 May and 31 May), so opec_YYYY_MM collides.

Decision: When a ministerial release and a voluntary-group release come out on the same day, they are one event row with decision_group voluntary_group, and the ministerial URL goes in notes. Reason: the voluntary release is the one that changes the near-term supply path; the ministerial one mostly extends levels already in place.

Decision: A release qualifies when it sets or changes a monthly production level that no earlier announcement had already set; reaffirming a preset path does not qualify. Same-size steps are tagged repeat and can be dropped in a robustness run. Reason: from Sep 2025 there is no preset path, so every monthly step is a new decision, and the repeat tag lets us test whether predictable steps move prices.

Decision: When an OPEC-only Conference release and the joint ministerial release cover the same decision, the event takes the date of the earliest release that states the decision. Reason: that is the first public information.

Decision: Events whose reaction days coincide (9 and 12 Apr 2020) are treated as one event. Reason: overlapping windows would count one reaction twice and break independence in the across-event tests.

Decision: The 5 Jan 2021 ministerial release is skipped; the Saudi cut that day is entered as a saudi_unilateral event once sourced from the Saudi Energy Ministry statement. Reason: the group release only reaffirmed the plan; the market news was the Saudi cut.

Decision: Meetings that ended with no decision (6 Mar 2020, 1 to 5 Jul 2021) stay out of the main run and are listed in the README. Reason: there is no decision to test, and opec.org has no outcome release for 6 Mar 2020.

Decision: Weekday events with no timed source are entered with the announcement date and flagged time_assumed; results are reported with all events, without those rows, and with day 0 shifted one trading day later. Reason: the [-1,+1] and [-5,+5] windows absorb a one-day dating error, so a missing time adds a little noise instead of invalidating the event. This replaces the old rule that weekday events need a timed source.

Decision: Real OPEC news that is not a tested event (failed meetings, the pre-sample 30 Nov 2016 cut, releases not yet entered) goes in events/opec_mask_only.csv; its [-5,+5] days are skipped in every event's estimation window, but it is never run or averaged. Reason: those days carry an oil reaction that would bend alpha and beta, and a failed meeting has no direction to test.

Decision: The headline test is the cross-sectional t on [-1,+1], run separately for cuts and increases; the pooled row is descriptive only. Reason: they predict opposite signs and cancel when pooled.

Decision: No cap on estimation look-back; the longest span is 197 sessions. Reason: chosen from the dates table before any CAR was read.

Decision: saudi_unilateral rows are kept out of the all/cut/hold/increase groups and tested as their own group. Reason: implements the separate-subsample rule.

Decision: The outlier run ranks days by XLE return minus one full-sample beta (2010 to 2026) times SPY return. Reason: a single beta gives one fixed list of extreme days for every event, picked before any CAR was read.

Decision: An event whose day 0 is pinned by a timed news report before the open on the decision day is entered as date-only with that report's time, not time_assumed. Reason: every plausible announcement time then gives the same day 0, which is the existing date-only rule.

## Not built yet
- Official-time robustness run (the --official-time flag exists, but the run has not been done)
- Saudi unilateral subsample report
- Brent robustness check
