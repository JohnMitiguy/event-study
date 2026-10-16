# Event study framework

Measures stock market reactions to geopolitical events using a market-model event study, starting with OPEC+ decisions (XLE vs SPY).

## Events CSV (`events/opec_events.csv`)

One row per event. Fill it in from primary sources only.

| Column | Meaning |
|---|---|
| `event_id` | Short unique slug, like `opec_2020_04_12`. |
| `announcement_datetime_et` | Naive Eastern time, format `YYYY-MM-DD HH:MM`. |
| `direction` | `cut`, `hold`, or `increase`. |
| `surprise_flag` | `1` if the outcome differed from consensus expectations, else `0`. Blank if unknown. |
| `confound_note` | Other major news that day, like a market-wide crash. |
| `source_url` | Primary source for the date and time (OPEC press release, Reuters). |
| `notes` | Anything else. |

Rules:

- **Time of day is required.** A row needs a time of day from a primary source. If you can only find the date, do not enter the event. List it under [Excluded events](#excluded-events) with the reason.
- **Eastern wall-clock time, no offset.** "Naive" means you write the time an Eastern clock showed (EST or EDT, whichever applied on that date) and leave out any UTC offset.
- **Converting from Vienna time.** OPEC sources often give Vienna time. Vienna is usually 6 hours ahead of Eastern, but only 5 hours for a few weeks around the clock changes, because the US and EU change their clocks on different dates. Convert with a time zone tool instead of subtracting by hand. Record the original source time in `notes` (for example `source: 14:30 Vienna`).
- **This is the announcement time, not event day 0.** Day 0 is worked out in code (announcements after 4pm ET, on weekends, or on holidays roll forward to the next trading day).
- **Quote text with commas.** If `confound_note` or `notes` contains a comma, wrap the value in double quotes, or it will split into extra columns.

### Excluded events

Events left out of the CSV, with the reason (for example, no primary-source time of day).

| Event | Date | Reason |
|---|---|---|
