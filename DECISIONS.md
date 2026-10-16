Decision: OPEC+ first pass uses XLE as the security and SPY as the benchmark, with Brent as a later robustness check. Reason: ETF prices avoid futures roll artifacts, and SPY is simple, with the small XLE-in-SPY overlap noted in the README.

Decision: Day 0 is the announcement date if it is a trading session and the announcement comes before that day’s actual close, otherwise the next session. Reason: early closes, weekends, holidays and unscheduled closures all change when the market can first react.

Decision: Event day logic only accepts timezone-aware datetimes in America/New_York. Reason: naive or fixed-offset timestamps cause silent off-by-one-day errors around daylight saving.

Decision: Estimation window is 120 trading days ending at day -10 (days -129 through -10), and event windows are [-1,+1] and [-5,+5], all by trading-day position. Reason: the gap keeps pre-event run-up and leaked news out of the model, and counting positions avoids calendar-day errors around weekends and holidays.