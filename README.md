# Event study framework

Measures stock market reactions to geopolitical events using a market-model event study, starting with OPEC+ decisions (XLE vs SPY).

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

- **Time of day is required.** A row needs an announcement time of day from a primary source. If you can only find the date, do not enter the event. List it under [Excluded events](#excluded-events) with the reason.
- **Untimed leaks are not used.** If a leak is known only by date, without a time, leave `leak_datetime_et` and `leak_source_url` blank so the event falls back to `announcement_datetime_et`. Write in `notes` that an untimed leak existed, and list the leak under [Excluded events](#excluded-events).
- **Leak fields go together.** `leak_datetime_et` and `leak_source_url` are either both filled or both blank.
- **Leak comes first.** `leak_datetime_et` must be earlier than `announcement_datetime_et`.
- **Eastern wall-clock time, no offset.** "Naive" means you write the time an Eastern clock showed (EST or EDT, whichever applied on that date) and leave out any UTC offset. This applies to both announcement and leak times.
- **Converting from Vienna time.** OPEC sources often give Vienna time. Vienna is usually 6 hours ahead of Eastern, but only 5 hours for a few weeks around the clock changes, because the US and EU change their clocks on different dates. Convert with a time zone tool instead of subtracting by hand. Record the original source time in `notes` (for example `source: 14:30 Vienna`).
- **Event time, not event day 0.** The study's event time is `leak_datetime_et` if present, otherwise `announcement_datetime_et`. Day 0 is worked out in code from the event time (times after 4pm ET, on weekends, or on holidays roll forward to the next trading day).
- **Quote text with commas.** If `confound_note` or `notes` contains a comma, wrap the value in double quotes, or it will split into extra columns.

### Excluded events

Events, or leak timestamps, left out of the CSV, with the reason. `Excluded` is `event` when the whole event was left out (for example, no primary-source announcement time) or `leak` when only the leak was left out (for example, an untimed leak) and the event uses its announcement time.

| Event | Date | Excluded | Reason |
|---|---|---|---|
