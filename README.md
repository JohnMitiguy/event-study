# Event study framework

## What this is

This project asks a simple question: when a geopolitical event happens, does a stock or sector move more than you would have expected from the market alone? The first case is OPEC+ production decisions and the energy sector, measured with the XLE energy ETF against the S&P 500 (SPY). Later event types are planned: terrorist attacks, tariffs, OFAC sanctions and Red Sea shipping disruptions.

A finding of "no measurable effect" is a valid result here and gets reported as such.

## Method

For each event, a market model is fitted by ordinary least squares: XLE's daily return regressed on SPY's, over an estimation window that ends before the event (by default 120 trading days, ending 10 trading days before day 0). The abnormal return on each day around the event is XLE's actual return minus what the model predicted from SPY that day. Abnormal returns are summed into cumulative abnormal returns (CARs) over short windows, by default days -1 to +1 and -5 to +5. Day 0 is the first trading day the market could react to the news (the leak time if there was a credible timed leak, otherwise the official announcement). All windows count trading days, not calendar days. Returns are simple daily returns from adjusted close prices.

The plan is to average CARs across events and test the average. The across-event tests (cross-sectional t-test, standardized-CAR test, Wilcoxon signed-rank and sign test) exist in `src/event_study/aggregate.py`, but `run_opec.py` does not call them yet, so a run produces only per-event CARs and per-event test statistics. Methodology choices and the reasons for them are in [DECISIONS.md](DECISIONS.md).

## Project layout

```
src/event_study/   the library: prices, events loader, trading-day logic, windows, market model, runner
tests/             pytest tests (no network, no price cache needed)
scripts/           run_opec.py (the study), plus demos, the null calibration and a price chart
events/            the hand-filled events CSV
results/           output CSV and run info from the last run
charts/            saved charts
data/              downloaded price cache (not in git)
DECISIONS.md       methodology decisions and why
```

## How to run

Install [uv](https://docs.astral.sh/uv/), then from the project root:

```
uv sync                              # install Python 3.13 and the packages
uv run pytest                        # run the tests
uv run python scripts/run_opec.py    # run the OPEC+ study
uv run python scripts/run_opec.py --official-time    # robustness check: official announcement times, not leaks
```

`--official-time` writes to `results/opec_results_official_time.csv`, `results/opec_run_info_official_time.json` and `charts/opec_events_official_time.png`, so it never overwrites the main outputs.

The first run of `run_opec.py` downloads prices from Yahoo Finance into `data/prices/`; after that it reuses them (see [Price data](#price-data)).

## Results

There are no real results yet. The events CSV has no events in it, so `results/opec_results.csv` contains only a header row. The charts in `charts/` are either price charts or come from simulated data, not from real events.

## Limitations

- **Confounding news.** A CAR picks up everything that moved XLE relative to SPY in the window, not only the OPEC+ decision. Other news on the same days (an oil supply shock, a big energy company's earnings, a market-wide selloff that hits energy harder) can look like an event effect. The `confound_note` column records known cases, but it can't catch everything, and longer windows are more exposed.
- **Thin samples.** OPEC+ decisions are infrequent, and some subgroups (for example Saudi unilateral actions, which are reported separately) will have only a handful of events. With few events the cross-event test has little power, and one unusual event can drive the average.
- **Overlapping estimation windows.** When events are close together, one event's estimation window can contain an earlier event's reaction, which distorts that event's model. The runner reports the overlap for each event but doesn't exclude or adjust anything yet. How to handle it is still to be decided before the full sample is run.
- **The test statistic ignores estimation error.** The per-event statistic divides the CAR by the residual standard deviation times the square root of the window length. It treats the fitted alpha and beta as exact, which slightly understates the true uncertainty, more so for longer windows.
- **Calibration used simulated normal noise.** The test statistic was checked on simulated events with no planted effect, to confirm it doesn't flag effects too often by chance. That simulation used normally distributed returns. Real daily returns have fatter tails, so on real data the test may produce false positives somewhat more often than the calibration suggests.
- **XLE is part of SPY.** Energy stocks are in the S&P 500, so part of any energy move also shows up in the benchmark. The overlap is small, but it slightly dampens measured abnormal returns.

## Price data

Prices are downloaded from Yahoo Finance once, into `data/prices/`, and then frozen: later runs reuse those files and never download again on their own. To refresh them, run:

```
uv run python scripts/run_opec.py --refresh
```

Refreshing can change results, because Yahoo adds new days and sometimes revises past adjusted prices. Each run writes `results/opec_run_info.json`, which records the data dates and the hashes of the prices used, so two runs can be checked for using the same data.

## Events CSV (`events/opec_events.csv`)

One row per event. Fill it in from primary sources only.

| Column | Meaning |
|---|---|
| `event_id` | Short unique slug, like `opec_2020_04_12`. |
| `announcement_datetime_et` | Naive Eastern time, format `YYYY-MM-DD HH:MM`. |
| `leak_datetime_et` | Earliest report from Reuters, Bloomberg or WSJ stating the specific outcome (direction, and size for cuts and increases) from named or multiple sources. Naive Eastern time, format `YYYY-MM-DD HH:MM`. Blank if none. |
| `leak_source_url` | Link to the report behind `leak_datetime_et`. Blank if none. |
| `decision_group` | `ministerial` = a decision from a full OPEC+ ministerial meeting. `voluntary_group` = a decision by the subset of members making voluntary cuts or output adjustments. `saudi_unilateral` = an action by Saudi Arabia alone, such as an extra voluntary cut or an official selling price change. Edge cases get a note in `notes`. |
| `direction` | `cut`, `hold`, or `increase`. |
| `surprise_flag` | `1` if the outcome differed from consensus expectations, else `0`. Blank if unknown. |
| `confound_note` | Other major news that day, like a market-wide crash. |
| `source_url` | Primary source for the announcement date and time (OPEC press release, Reuters). |
| `notes` | Anything else. |

Rules:

- **The time must place the event against the close.** A row needs a time precise enough to place the event against the close. If the source gives only a date, enter a representative time and write `date-only` in `notes`, plus the reason every plausible time gives the same day 0 (for example: Sunday meeting, any time gives Monday; weekday Vienna meeting ending in business hours, before the US close). If the date alone cannot settle day 0, don't enter the row; list it under [Excluded events](#excluded-events) with the reason. Leak times must be exact, from a timestamped source.
- **Untimed leaks are not used.** If a leak is known only by date, without a time, leave `leak_datetime_et` and `leak_source_url` blank so the event falls back to `announcement_datetime_et`. Write in `notes` that an untimed leak existed, and list the leak under [Excluded events](#excluded-events).
- **Leak fields go together.** `leak_datetime_et` and `leak_source_url` are either both filled or both blank.
- **Leak comes first.** `leak_datetime_et` must be earlier than `announcement_datetime_et`.
- **Eastern wall-clock time, no offset.** "Naive" means you write the time an Eastern clock showed (EST or EDT, whichever applied on that date) and leave out any UTC offset. This applies to both announcement and leak times.
- **Converting from Vienna time.** OPEC sources often give Vienna time. Vienna is usually 6 hours ahead of Eastern, but only 5 hours for a few weeks around the clock changes, because the US and EU change their clocks on different dates. Convert with a time zone tool instead of subtracting by hand. Record the original source time in `notes` (for example `source: 14:30 Vienna`).
- **Event time, not event day 0.** The study's event time is `leak_datetime_et` if present, otherwise `announcement_datetime_et`. Day 0 is worked out in code from the event time: times at or after that day's actual close (1pm on early-close days), on weekends, or on holidays roll forward to the next trading day.
- **Quote text with commas.** If `confound_note` or `notes` contains a comma, wrap the value in double quotes, or it will split into extra columns.

### Excluded events

Events, or leak timestamps, left out of the CSV, with the reason. `Excluded` is `event` when the whole event was left out (for example, the source gives only a date and the date alone cannot settle day 0) or `leak` when only the leak was left out (for example, an untimed leak) and the event uses its announcement time.

| Event | Date | Excluded | Reason |
|---|---|---|---|
