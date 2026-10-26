# Event study framework

## In 30 seconds

This project tests whether the energy sector (XLE) moves more than the S&P 500 (SPY) would predict around OPEC+ production decisions, using a market-model event study of 37 decisions from Dec 2016 to Oct 2026.

![XLE average cumulative abnormal return around OPEC+ decisions](charts/opec_caar.png)

CAR (cumulative abnormal return) is XLE's return minus what SPY predicts, summed over the window. t is the t-statistic of the average across events.

- **Headline: no significant effect.** Over days -1 to +1, cuts average +1.51% (t 1.56, N 7) and increases -0.51% (t -0.49, N 17). The signs match theory, but neither is statistically different from zero.
- **Increases drift down over a wider window.** Over days -5 to +5, increases average -3.26% (t -2.38), and this holds in every robustness sample (t -2.42 to -3.19). It was not the pre-set headline window, and one of the 17 increases (3 Apr 2025) lands on the US tariff selloff, so treat it as suggestive.
- **Most of the cut move comes before day 0.** By day -1, cuts are already up +3.10% on average (cumulated from day -5), consistent with decisions being anticipated or leaked before the official release.

**Rigor:** no look-ahead (each model is fitted only on days well before its event), headline test fixed before the first run, a frozen price snapshot with hashes recorded for every run, 414 automated tests, robustness checks (shifted dates, official times, outlier exclusion), and the null headline reported as a null.

Full method, results and limitations below. Every methodology decision and its reason is logged in [DECISIONS.md](DECISIONS.md).

## What this is

This project asks a simple question: when a geopolitical event happens, does a stock or sector move more than you would have expected from the market alone? The first case is OPEC+ production decisions and the energy sector, measured with the XLE energy ETF against the S&P 500 (SPY). Later event types are planned: terrorist attacks, tariffs, OFAC sanctions and Red Sea shipping disruptions.

A finding of "no measurable effect" is a valid result here and gets reported as such.

## Method

For each event, a market model is fitted by ordinary least squares: XLE's daily return regressed on SPY's, over an estimation window that ends before the event (by default 120 trading days, ending 10 trading days before day 0). Days inside another event's widest event window (days -5 to +5 of that event, with the default windows) are left out, and the window reaches further back instead. The same goes for real OPEC news that is not tested, such as failed meetings, listed in `events/opec_mask_only.csv` (see [Excluded events](#excluded-events)), so the regression still uses 120 days, none of them inside another event's window. The results show each event's first and last estimation day (`est_start`, `est_end`) and how many days were skipped (`est_masked_days`). The abnormal return on each day around the event is XLE's actual return minus what the model predicted from SPY that day. Abnormal returns are summed into cumulative abnormal returns (CARs) over short windows, by default days -1 to +1 and -5 to +5. Day 0 is the first trading day the market could react to the news (the leak time if there was a credible timed leak, otherwise the official announcement). All windows count trading days, not calendar days. Returns are simple daily returns from adjusted close prices.

CARs are then averaged across events and the average is tested: cross-sectional t-test (primary), standardized-CAR (BMP) test and Wilcoxon signed-rank test (robustness), and a sign test (reported only). Cuts, increases and holds are tested separately, because cuts should push XLE up and increases push it down, so pooling them cancels out. The headline was fixed before the first full run: the cross-sectional t on [-1,+1], for cuts and for increases. Saudi unilateral actions are a separate group and never enter the main averages. Methodology choices and the reasons for them are in [DECISIONS.md](DECISIONS.md).

## Project layout

```
src/event_study/   the library: prices, events loader, trading-day logic, windows, market model, runner
tests/             pytest tests (no network, no price cache needed)
scripts/           run_opec.py (the study), plus demos, the null calibration and a price chart
events/            the hand-filled events CSV, the mask-only list and the candidate list
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
uv run python scripts/run_opec.py --shift-assumed   # robustness check: day 0 of time_assumed rows one trading day later
uv run python scripts/run_opec.py --dates-only      # where each estimation window falls; no returns or CARs
```

`--shift-assumed` writes to `*_day0_shifted` files in the same way.

`--official-time` writes to `results/opec_results_official_time.csv`, `results/opec_run_info_official_time.json` and `charts/opec_events_official_time.png`, so it never overwrites the main outputs.

The first run of `run_opec.py` downloads prices from Yahoo Finance into `data/prices/`; after that it reuses them (see [Price data](#price-data)).

## Methodology reviewer (Claude Code)

`.claude/agents/methodology-reviewer.md` is a Claude Code subagent that hunts for look-ahead bias, window errors, overlap, thin samples, silent failures and code that disagrees with DECISIONS.md. It suggests DECISIONS.md lines for you to add rather than editing anything. It has no edit tools and no web access, and two things restrict what it does: its instructions, which tell it never to change files, and a hook (`.claude/hooks/reviewer_bash_guard.py`, tested in `tests/test_reviewer_hook.py`) that lets its shell run only `git log`, `git diff`, `git status`, `uv run pytest` and `uv run ruff check`, each with a short list of allowed flags. The hook is a backstop, not a guarantee: it blocks anything else it sees, but if it can't start (for example, uv is not installed), Claude Code lets the command run anyway. pytest and ruff also still write their own cache folders. `uv run` may sync `.venv` or `uv.lock` before running pytest or ruff. Run it from Claude Code with:

- `/review-last`: the last commit. Did methodology change without a DECISIONS.md entry, and do tests cover it?
- `/audit-decisions`: every DECISIONS.md entry checked against the code.
- `/check-results`: ok and failed counts, overlap diagnostics, sample size and a skeptical reading of `results/`.
- `/check-events`: the events CSV checked against the rules below, plus a list of rows to verify against their primary sources (by hand, since it can't open URLs).

Text after a command is passed along as extra notes, for example `/review-last focus on day 0`.

## Results

First full run, 26 Oct 2026: 37 OPEC+ decisions from Dec 2016 to Oct 2026, all 37 ran (none failed), prices through 15 Oct 2026. Event time is the leak time where there is one (one event), otherwise the announcement. The chart is in [In 30 seconds](#in-30-seconds).

| Group | N | Mean CAR [-1,+1] | t | Mean CAR [-5,+5] | t |
|---|---|---|---|---|---|
| Cuts | 7 | +1.51% | 1.56 | +3.34% | 1.40 |
| Increases | 17 | -0.51% | -0.49 | -3.26% | -2.38 |
| Holds | 13 | +0.46% | 0.48 | +0.29% | 0.25 |

t is the cross-sectional t-test. The headline is the [-1,+1] column for cuts and increases.

**What it says.**

- **The headline is a null result.** XLE moves the way theory says (up after cuts, down after increases), but neither [-1,+1] average is statistically different from zero. With only 7 cuts, a test at 5% would need a much larger average reaction to register.
- **Increases show a slower drift.** Over [-5,+5] the 17 increases average -3.26% (t -2.38; BMP t -2.47; Wilcoxon p 0.045). Dropping any single event keeps t between -2.03 and -2.79. This window was not the headline, so treat it as suggestive, not as the finding.
- **Much of the move comes before day 0.** By day -1, cuts are already up +3.10% on average and increases down -2.02%. That fits decisions being reported or expected days before the official release. The 10-day gap before the estimation window keeps this run-up out of the baseline.

**Robustness.**

- **Day 0 one trading day later for the 13 rows with an assumed announcement time:** cuts [-1,+1] +0.80% (t 0.57), increases -0.82% (t -0.90), increases [-5,+5] -3.33% (t -2.42).
- **Without those 13 rows:** only 3 cuts remain, too few to test. Increases (N 14) are -1.37% on [-1,+1] (t -1.34) and -4.55% on [-5,+5] (t -3.19).
- **Without events fitted on the 5 most extreme days:** the 5 largest XLE-minus-beta-times-SPY days of 2010 to 2026 are 9 Nov 2020 (+13.0%), 9 Mar 2020 (-12.1%), 18 Mar 2020 (-9.1%), 17 Apr 2020 (+7.8%) and 2 Apr 2020 (+6.8%). Five events are fitted on one of them and are dropped (Apr, Jun and Dec 2020, Mar and Jul 2021). Cuts (N 6) are +1.61% on [-1,+1] (t 1.41) and increases (N 15) are -0.88% (t -0.93), with increases at -3.34% on [-5,+5] (t -2.44).
- **Official announcement time instead of the leak:** the numbers are identical, because the one leak (5 Oct 2022) came the same morning as the release.

**Largest single event.** On 3 Apr 2025 (opec_2025_04_03, an increase), the [-1,+1] CAR is -12.40% (t -6.09). Those days were a broad selloff: SPY fell 4.9% and 5.8% on 3 and 4 Apr, and XLE fell 7.9% and 9.2%. The US tariff announcement came on 2 Apr after the US close (Fox Business), so it lands on the same day 0 as the OPEC+ increase, and the two can't be separated. This is recorded in `confound_note`. Per DECISIONS.md, the event stays in the main run. Without it, the other 16 increases average +0.23% on [-1,+1] (t 0.29).

Outputs: `results/opec_results.csv` (per event), `results/opec_across_event.csv` (group tests for all three samples: all events, without assumed times, without outlier-fitted events), `results/opec_abnormal.csv` (daily abnormal returns), `charts/opec_events.png` (one panel per event). The robustness runs write the same files with `_day0_shifted` or `_official_time` added. `results/opec_run_info.json` records the data hashes, settings and git commit of each run.

## Limitations

- **Confounding news.** A CAR picks up everything that moved XLE relative to SPY in the window, not only the OPEC+ decision. Other news on the same days (an oil supply shock, a big energy company's earnings, a market-wide selloff that hits energy harder) can look like an event effect. The `confound_note` column records known cases, but it can't catch everything, and longer windows are more exposed.
- **Thin samples.** OPEC+ decisions are infrequent, and some subgroups (for example Saudi unilateral actions, which are reported separately) will have only a handful of events. With few events the cross-event test has little power, and one unusual event can drive the average.
- **Few events without the assumed times.** 13 of the 37 events have no sourced announcement time (`time_assumed`). In the without-`time_assumed` report only 3 of the 7 cuts remain (below the 5-event minimum), so the cut group shows "too few events" there and is not tested. The all-events cut group and the shifted run do not have this problem, but they rest on assumed announcement times.
- **Long look-back for 2025 and 2026 events.** OPEC+ decided monthly from 2025, so the recent events sit close together. Their estimation windows skip 44 to 77 days and stretch back up to 197 trading days, so their baselines come from an older period. No cap on the look-back was set (DECISIONS.md).
- **2020 baselines.** The April and June 2020 events are fitted on windows that include the March 2020 crash (beta 1.28 and 1.34, residual std 1.7% and 2.0% a day, against a median of 1.2% for all events). Their per-event t statistics are small because of that noise.
- **Overlapping events.** An event's estimation window skips other events' window days and reaches further back, so it can span more than 120 trading days and its beta comes from a slightly older period (`est_start` shows how far back). Only the other events' window days are skipped, not their run-up days before the window. Only events in the events CSV and the mask-only list count. Other news, and other event types, are not skipped. Events whose event windows overlap each other (`nearby_events` above 0) still measure some of the same days, and nothing adjusts for that.
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
| `event_id` | `opec_YYYY_MM_DD` from the event date, like `opec_2023_04_02`. |
| `announcement_datetime_et` | Naive Eastern time, format `YYYY-MM-DD HH:MM`. |
| `leak_datetime_et` | Earliest report from Reuters, Bloomberg or WSJ stating the specific outcome (direction, and size for cuts and increases) from named or multiple sources. Naive Eastern time, format `YYYY-MM-DD HH:MM`. Blank if none. |
| `leak_source_url` | Link to the report behind `leak_datetime_et`. Blank if none. |
| `decision_group` | `ministerial` = a decision from a full OPEC+ ministerial meeting. `voluntary_group` = a decision by the subset of members making voluntary cuts or output adjustments. `saudi_unilateral` = a production action by Saudi Arabia alone, such as an extra voluntary cut. Edge cases get a note in `notes`. |
| `direction` | `cut`, `hold`, or `increase`. |
| `surprise_flag` | `1` if the outcome differed from consensus expectations, else `0`. Blank if unknown. |
| `confound_note` | Specific, dated, sourced news inside [-1,+1] that plausibly hit energy differently from the broad market. Market-wide moves are left out (the market model handles them), and flagged events stay in the main run. |
| `source_url` | Primary source for the announcement date and time (OPEC press release, Reuters). |
| `notes` | Anything else. |
| `time_assumed` | `1` for a weekday event with no timed source: `announcement_datetime_et` is then the announcement date with a placeholder time (12:00), not a real one. `0` or blank otherwise. Not allowed on a row with a leak time. |

Rules:

- **The time must place the event against the close.** A row needs a time precise enough to place the event against the close. If the source gives only a date, enter a representative time and write `date-only` in `notes`, plus the reason every plausible time gives the same day 0 (for example: Sunday meeting, any time gives Monday; weekday Vienna meeting ending in business hours, before the US close). If the date alone cannot settle day 0, the row is entered under the `time_assumed` rule below. Leak times must be exact, from a timestamped source.
- **Weekday events with no timed source are kept.** Enter the announcement date with a placeholder time, set `time_assumed` to `1` and say so in `notes`. Results are reported three ways: all events, without the `time_assumed` rows, and with day 0 of those rows shifted one trading day later (`--shift-assumed`). The without-`time_assumed` report is a filter on the full run's results, so it leaves the events table alone.
- **Untimed leaks are not used.** If a leak is known only by date, without a time, leave `leak_datetime_et` and `leak_source_url` blank so the event falls back to `announcement_datetime_et`. Write in `notes` that an untimed leak existed, and list the leak under [Excluded events](#excluded-events).
- **Leak fields go together.** `leak_datetime_et` and `leak_source_url` are either both filled or both blank.
- **Leak comes first.** `leak_datetime_et` must be earlier than `announcement_datetime_et`.
- **Eastern wall-clock time, no offset.** "Naive" means you write the time an Eastern clock showed (EST or EDT, whichever applied on that date) and leave out any UTC offset. This applies to both announcement and leak times.
- **Converting from Vienna time.** OPEC sources often give Vienna time. Vienna is usually 6 hours ahead of Eastern, but only 5 hours for a few weeks around the clock changes, because the US and EU change their clocks on different dates. Convert with a time zone tool instead of subtracting by hand. Record the original source time in `notes` (for example `source: 14:30 Vienna`).
- **Event time, not event day 0.** The study's event time is `leak_datetime_et` if present, otherwise `announcement_datetime_et`. Day 0 is worked out in code from the event time: times at or after that day's actual close (1pm on early-close days), on weekends, or on holidays roll forward to the next trading day.
- **Quote text with commas.** If `confound_note` or `notes` contains a comma, wrap the value in double quotes, or it will split into extra columns.

### Excluded events

Events, or leak timestamps, left out of the CSV, with the reason. `Excluded` is `event` when the whole event was left out or `leak` when only the leak was left out (for example, an untimed leak) and the event uses its announcement time. `Masked` says whether the date is in `events/opec_mask_only.csv`, so its days are still skipped in other events' estimation windows.

| Event | Date | Excluded | Masked | Reason |
|---|---|---|---|---|
| OPEC-only 171st Conference cut | 30 Nov 2016 | event | yes | Before the OPEC+ sample start (Dec 2016). |
| Joint OPEC+ meeting | 6 Mar 2020 | event | yes (with the 5 Mar Conference) | Ended with no agreement; no outcome release on opec.org. |
| 10th (Extraordinary) ONOMM | 12 Apr 2020 | event | no | Same reaction days as 9 Apr 2020, merged into opec_2020_04_09. |
| 13th ONOMM | 5 Jan 2021 | event | yes | Reaffirmed the plan. The Saudi cut that day will be its own saudi_unilateral row once sourced. |
| 15th ONOMM | 1 Apr 2021 | event | yes | Step sizes are in an attached table not read yet. |
| 18th ONOMM | 1 to 5 Jul 2021 | event | yes | Adjourned twice, then called off with no decision. |
| 31st ONOMM | 3 Aug 2022 | event | yes | Not settled whether a one-month +0.1 mb/d step counts as a new decision. |
| 32nd ONOMM | 5 Sep 2022 | event | yes | Not settled whether reversing that step counts. |
| 35th ONOMM | 4 Jun 2023 | event | yes | Direction unknown until the attached table is read. |
| Same-day ONOMM and JMMC releases with no production change | various | event | no | Not a decision (for example 30 Nov 2023, 7 Jun 2026, 2 Aug 2026, 4 Oct 2026). |

Monitoring-only JMMC meetings and releases that only reaffirm a preset step are not events by definition (DECISIONS.md) and are listed in `events/opec_candidates.md`, not here.
