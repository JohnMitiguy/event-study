Decision: OPEC+ first pass uses XLE as the security and SPY as the benchmark, with Brent as a later robustness check. Reason: ETF prices avoid futures roll artifacts, and SPY is simple, with the small XLE-in-SPY overlap noted in the README.

Decision: Day 0 is based on the earliest credible leak (Reuters, Bloomberg or WSJ stating the specific outcome from multiple or named sources) when one exists, otherwise the official announcement; the official time is run as a robustness check. Reason: markets react when information arrives, and the rule is fixed before seeing returns so the choice of leak time can’t be tuned to the result.

Decision: Event day logic only accepts timezone-aware datetimes in America/New_York. Reason: naive or fixed-offset timestamps cause silent off-by-one-day errors around daylight saving.

Decision: Estimation window is 120 trading days ending at day -10 (days -129 through -10), and event windows are [-1,+1] and [-5,+5], all by trading-day position. Reason: the gap keeps pre-event run-up and leaked news out of the model, and counting positions avoids calendar-day errors around weekends and holidays.

Decision: Window functions raise an error when data is missing or windows collide, and never shrink or shift a window. Reason: a silently truncated 60-day estimation window would look like a 120-day regression and quietly weaken every result.


Decision: Main results keep all data; a robustness run drops events whose estimation window contains the five largest absolute XLE return days (all 2020). Reason: those days are XLE-specific outliers that inflate residual variance and distort beta, and fixing the rule before seeing results avoids data snooping.

Next: session 5, the events CSV schema, with confound_note added. After that, the CSV loader (which attaches the Eastern timezone to naive strings), then the engine. The overlapping estimation window question is still open, and it needs an answer before the engine.

Decision: A row needs a primary-source announcement time, and events without one are left out and listed with reasons in the README. Reason: guessing the time can shift day 0 by a day, and silently dropping events would be an undisclosed selection effect.

Decision: Saudi unilateral decisions are logged with a decision_group tag and reported as a separate subsample, not averaged into the main result. Reason: they are a different kind of shock from group decisions, and a blended average would describe neither.

Decision: An event with a leak known only by date uses the official announcement time and is logged in the README with a note, not dropped. Reason: dropping it would silently shrink the sample, and the official time is the conservative fallback.

Decision: The market model is an OLS regression of security returns on benchmark returns with an intercept, using the estimation window only, with residual variance computed on n-2 degrees of freedom. Reason: it is the standard specification, and the n-2 divisor reflects the two estimated parameters.

Decision: The per-event test statistic is CAR divided by residual std times the square root of window length, ignoring estimation error in alpha and beta; headline inference comes from the across-event test. Reason: with 120 observations the omitted error is small (about 3% of variance for a 3-day window, 10% for an 11-day one), and the cross-event test handles event-induced volatility better.

Decision: The test statistic is accepted only if a 1000-event simulation with no planted effect gives a mean near 0, a standard deviation between 0.9 and 1.15, and 3 to 8 percent of statistics beyond ±1.96, for both windows. Reason: a statistic that fires too often on pure noise would flatter every real result, and the check uses simulated normal noise, so real returns with fatter tails may behave somewhat worse.

Decision: All bad-input errors raise ValueError, including a wrong index type, and Ruff’s TRY004 rule is ignored. Reason: one exception type lets the runner catch and log any bad event without stopping the run.

Decision: The events loader is strict and rejects the whole file with every bad row listed, while the runner records a per-event error and continues. Reason: a bad CSV is a data-entry mistake you should fix, but an event with too little price history is a legitimate result to report.

Decision: The first version of the runner reports overlap diagnostics per event and applies no exclusions, and the treatment of overlapping estimation windows is decided after the pilot, before the full sample is run. Reason: with a handful of events overlap is rare, and seeing the diagnostics on the real list is better than guessing a rule.

Decision: Results come from a frozen price snapshot that is refreshed only on request, and each run records the data dates and a hash of the prices used. Reason: Yahoo revises adjusted prices, so an automatic refresh could change a CAR between runs with no record of why.

Decision: The estimation window must end before day 0 and before the start of every event window, so the gap is at least 1. Reason: otherwise a post-event window with a small gap would fit the model on the event’s own reaction.

Decision: Data problems tied to one event raise EventDataError, a subclass of ValueError, and the runner catches only that. Reason: a bug inside a library that happens to raise ValueError should stop the run instead of showing up as one more failed event.