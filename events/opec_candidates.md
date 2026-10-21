# OPEC+ event candidates, Dec 2016 to Oct 2026 (first pass, NOT final)

Built from the opec.org press releases. I read the full text of every release in Tables 1A, 1B, 2A and 2B, except the 16 releases in the "listing only" block of Table 2A, which I classified from their listing summary. Event facts come from opec.org. Anything that is not on opec.org (calendar facts, market context) is marked "check".

How to use it
- URL = https://www.opec.org/pr-detail/<slug>.html. Open it and read the decision yourself before the event goes in the CSV.
- "Decision" is a paraphrase, not a quote. When you enter an event, paste the exact sentence from the page into the CSV notes column.
- None of the releases states when it was published. Some notices give a meeting start time (for example 210-17-jul-2021), which is not the same thing. "Timing" says what each row needs:
  - Weekend: date-only is fine, because day 0 is the next trading day whatever the time.
  - Holiday: the same, because the NYSE is closed on the stated date or the Monday after it.
  - TIME ASSUMED: a weekday event with no timed source. Settled 21 Oct 2026: enter it with the announcement date and a time_assumed flag, and report results three ways: all events, without these rows, and with day 0 shifted one trading day later. A timed source (Reuters, Bloomberg, the Saudi Ministry of Energy statement) upgrades the row later.
- "Qualifies" is a first pass against this rule: a formal group-level production decision that sets or changes a production level versus what was last announced. A release that only reaffirms a path already announced is not an event. An open-ended tranche with no preset path (from Sep 2025) counts, because each month's level is a new decision.
- "repeat" in Notes means the same size as the previous step. Repeats stay in the sample and can be dropped later as a robustness run.
- Direction is relative to the previous announced path. cut = lower output, increase = higher, hold = pause, delay or extension of a scheduled increase.
- event_id is proposed as opec_YYYY_MM_DD. The three pilot rows (1B rows 4, 5, 20) would be renamed from their current ids.
- Dating rule used in Table 1A (settled 21 Oct): when an OPEC-only Conference release and the joint ministerial release cover the same decision, the row takes the date of the earliest release that states the decision. The other URL goes in notes. Row A7 follows the same rule: the Conference text says it "decided to support" the extra cut, so it is dated Thu 5 Dec.
- Row labels: 1A rows are A1 to A15 (Dec 2016 to Dec 2021). 1B rows keep the numbers 1 to 28 (Jan 2022 to Oct 2026), so earlier references to row numbers still work.

## Table 1A. Candidates, Dec 2016 to Dec 2021 (15)

| # | event_id (proposed) | Date (day) | Slug | Decision (paraphrase) | decision_group | direction | Qualifies | Timing | Notes |
|---|---|---|---|---|---|---|---|---|---|
| A1 | opec_2016_12_10 | 10 Dec 2016 (Sat) | 457-10-dec-2016 | First joint OPEC/non-OPEC meeting: OPEC's 1.2 mb/d cut is maintained; 11 non-OPEC countries commit 558 kb/d combined; effective 1 Jan 2017 for six months, extendable six | ministerial | cut | yes | Weekend: date-only OK | Sample start per DECISIONS.md. The OPEC-only cut was set on 30 Nov 2016 (458-30-nov-2016, Table 2A), so the new content here is the non-OPEC 558 kb/d. Day 0 is Mon 12 Dec. |
| A2 | opec_2017_05_25 | 25 May 2017 (Thu) | 415-25-may-2017 | 2nd ONOMM: extend the production adjustments nine months from 1 Jul 2017 | ministerial | hold | yes | TIME ASSUMED | Same day: 414-25-may-2017 (172nd Conference, same extension). Put that URL in notes. The JMMC recommended this extension the day before (417-24-may-2017, Table 2A), so some of it may be priced by 25 May. See open call 5. |
| A3 | opec_2017_11_30 | 30 Nov 2017 (Thu) | 385-30-nov-2017 | 3rd ONOMM: the Declaration of Cooperation is amended to run through all of 2018; a review is planned for June 2018 | ministerial | hold | yes | TIME ASSUMED | Same day: 383-01-dec-2017 (173rd Conference, held Thu 30 Nov, listed 1 Dec). Put that URL in notes. |
| A4 | opec_2018_06_22 | 22 Jun 2018 (Fri) | 363-22-jun-2018 | 174th Conference (Fri): OPEC-12 conformity adjusted to 100% from 1 Jul. 4th ONOMM (Sat 23 Jun, 362-23-jun-2018): the same for the whole group | ministerial | increase | yes | TIME ASSUMED | The text gives no size, only "adjust to 100% conformity". Increase is inferred: the JMMC release of 25 May 2018 (366-25-may-2018) reports record conformity above 100% before this. If the Friday outcome was public while the NYSE was open, day 0 is Fri 22 Jun, otherwise Mon 25 Jun. Needs a timed source for Friday. Put 362 in notes. |
| A5 | opec_2018_12_07 | 7 Dec 2018 (Fri) | 339-07-dec-2018 | 5th ONOMM: cut overall production by 1.2 mb/d (OPEC 0.8, non-OPEC 0.4) from Jan 2019 for six months | ministerial | cut | yes | TIME ASSUMED | Also listed 7 Dec: 338-07-dec-2018 (175th Conference, held Thu 6 Dec: OPEC-only cut of 0.8 mb/d against Oct 2018 levels, from Jan 2019 for six months). Put that URL in notes. Whether the 0.8 mb/d leaked on Thu 6 Dec is not on opec.org. |
| A6 | opec_2019_07_01 | 1 Jul 2019 (Mon) | 330-01-jul-2019 | 176th Conference: extend the voluntary production adjustments nine months, 1 Jul 2019 to 31 Mar 2020 | ministerial | hold | yes | TIME ASSUMED | The 6th ONOMM (328-02-jul-2019, Tue 2 Jul) took the same decision. Put that URL in notes. Dated Mon 1 Jul because the Conference release states the decision first. |
| A7 | opec_2019_12_05 | 5 Dec 2019 (Thu) | 320-06-dec-2019 | 177th Conference (Thu 5 Dec): decided to support an extra 500 tb/d from 1 Jan 2020, subject to approval at the 7th ONOMM on 6 Dec; the ONOMM then approved it, total 1.7 mb/d | ministerial | cut | yes | TIME ASSUMED | SETTLED (21 Oct): dated Thu 5 Dec, because Al Jazeera reported the extra 500k on 5 Dec (page time 16:42, timezone not stated), a day before the formal vote. The opec.org page is listed 6 Dec, so the slug date is one day after the event date on purpose. Put 319-06-dec-2019 (7th ONOMM, Fri 6 Dec) in notes. |
| A8 | opec_2020_04_09 | 9 Apr 2020 (Thu) | 313-09-apr-2020 | 9th (Extraordinary) ONOMM: cut 10.0 mb/d in May and June, 8.0 mb/d Jul to Dec, 6.0 mb/d Jan 2021 to Apr 2022, conditional on Mexico | ministerial | cut | yes | TIME ASSUMED | Largest cut in the sample. Cluster with A9. Fri 10 Apr 2020 was Good Friday (check: NYSE closed), so a late Thursday release and the Sunday release can share day 0, Mon 13 Apr. |
| A9 | opec_2020_04_12 | 12 Apr 2020 (Sun) | 310-12-apr-2020 | 10th (Extraordinary) ONOMM: confirms the cut at 9.7 mb/d (May to Jun), 7.7 mb/d (Jul to Dec), 5.8 mb/d (Jan 2021 to Apr 2022) | ministerial | cut | yes | Weekend: date-only OK | Revised sizes versus A8, so it counts as a change. Same reaction day as A8. Day 0 is Mon 13 Apr. SETTLED (call 2): A8 + A9 are one event. |
| A10 | opec_2020_06_06 | 6 Jun 2020 (Sat) | 306-06-jun-2020 | 11th ONOMM: reconfirms the April deal and extends the first phase (the 9.7 mb/d level) one month, to 31 Jul 2020 | ministerial | hold | yes | Weekend: date-only OK | Same day: 307-06-jun-2020 (179th Conference, same extension). Put that URL in notes. The meetings were moved up from 9/10 Jun by a notice on Fri 5 Jun (308-05-jun-2020, Table 2A). Day 0 is Mon 8 Jun. |
| A11 | opec_2020_12_03 | 3 Dec 2020 (Thu) | 281-03-dec-2020 | 12th ONOMM: from Jan 2021 reduce the cut by 0.5 mb/d (7.7 to 7.2 mb/d); monthly ministerial meetings from Jan 2021, each step at most 0.5 mb/d | ministerial | increase | yes | TIME ASSUMED | The 180th Conference adjourned 30 Nov and reconvened 1 Dec (283-30-nov-2020, Table 2A). opec.org has no outcome release for it. |
| A12 | opec_2021_01_05 | 5 Jan 2021 (Tue) | 277-05-jan-2021 | 13th ONOMM (talks 4 Jan, concluded 5 Jan): reconfirms the Jan step; Feb and Mar levels per an attached table (not read); April to be decided monthly | ministerial | unsure | unsure | TIME ASSUMED | Reads as a reaffirmation. Saudi Arabia's additional voluntary cut, "taking effect on 1 February for two months", appears only later (276-03-feb-2021; 270-04-mar-2021 gives 1 mb/d). Its announcement date and time are not on opec.org. Candidate saudi_unilateral row. SETTLED (call 3): skip this ministerial row; enter the Saudi cut as saudi_unilateral once it is sourced from the Saudi Energy Ministry statement. |
| A13 | opec_2021_03_04 | 4 Mar 2021 (Thu) | 270-04-mar-2021 | 14th ONOMM: April levels equal March, except Russia +130 and Kazakhstan +20 kb/d; Saudi extends its 1 mb/d voluntary cut to April | ministerial | hold | yes | TIME ASSUMED | Net group change is +150 kb/d, so hold is a judgment call. No surprise_flag without a dated source for expectations. Same saudi_unilateral question for the extension. |
| A14 | opec_2021_04_01 | 1 Apr 2021 (Thu) | 268-01-apr-2021 | 15th ONOMM: approves production-level adjustments for May, June and July 2021, monthly steps capped at 0.5 mb/d; Saudi keeps its 1 mb/d cut in April | ministerial | increase | yes | TIME ASSUMED | The text gives neither sign nor size; the sizes are in an attached table I did not read. Increase is inferred from the 12th ONOMM mechanism. Read the table before entering. The 27 Apr and 1 Jun releases continue this path (Table 2A). |
| A15 | opec_2021_07_18 | 18 Jul 2021 (Sun) | 209-18-jul-2021 | 19th ONOMM: raise overall output 0.4 mb/d per month from Aug 2021 until the 5.8 mb/d adjustment is phased out; DoC extended to 31 Dec 2022; baselines raised from May 2022 | ministerial | increase | yes | Weekend: date-only OK | Meeting was set for Sun 18 Jul at 12:00 CEST (210-17-jul-2021). Day 0 is Mon 19 Jul. Follows the failed 1 to 5 Jul meeting (212-05-jul-2021, open call 4). The later 0.4 steps (Sep 2021 to Jan 2022) are preset by this decision (Table 2A). |

Counts (1A)
- Direction: 5 cuts (A1, A5, A7, A8, A9), 5 holds (A2, A3, A6, A10, A13), 4 increases (A4, A11, A14, A15), 1 unsure (A12). Total 15.
- Qualifies: 14 yes, 1 unsure (A12).
- Timing: 4 weekend (A1, A9, A10, A15), 11 TIME ASSUMED (A2 to A8, A11 to A14).

## Table 1B. Candidates, Jan 2022 to Oct 2026 (28)

| # | event_id (proposed) | Date (day) | Slug | Decision (paraphrase) | decision_group | direction | Qualifies | Timing | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 1 | opec_2022_06_02 | 2 Jun 2022 (Thu) | 127-02-jun-2022 | 29th ONOMM: July step +0.648 mb/d, and the planned September adjustment is advanced | ministerial | increase | yes | TIME ASSUMED | Advancing a step changes the schedule. |
| 2 | opec_2022_08_03 | 3 Aug 2022 (Wed) | 80-03-aug-2022 | 31st ONOMM: raise the level by only 0.1 mb/d for September | ministerial | increase | unsure | TIME ASSUMED | Much smaller than the 0.648 step before it. Compare with row 1 before accepting. |
| 3 | opec_2022_09_05 | 5 Sep 2022 (Mon) | 78-05-sep-2022 | 32nd ONOMM: return to the August level for October, saying the +0.1 was for September only | ministerial | cut | unsure | Holiday: date-only OK | NYSE closed on US Labor Day, so day 0 is Tue 6 Sep. The release says the +0.1 was a one-month step, so the reversal may count as already scheduled. |
| 4 | opec_2022_10_05 | 5 Oct 2022 (Wed) | 73-05-oct-2022 | 33rd ONOMM: cut of 2 mb/d from November 2022 | ministerial | cut | yes | Timed (pilot) | Pilot event, current id opec_2022_10. Leak 09:12 ET per Reuters. |
| 5 | opec_2023_04_02 | 2 Apr 2023 (Sun) | 63-03-apr-2023 | Eight countries announce voluntary cuts from May: Saudi 500, Iraq 211, UAE 144, Kuwait 128, Kazakhstan 78, Algeria 48, Oman 40, Gabon 8 kb/d, plus Russia 500, about 1.66 mb/d in total | voluntary_group | cut | yes | Weekend: date-only OK | Pilot event, current id opec_2023_04. The opec.org page is the 3 Apr JMMC release that notes the 2 Apr announcement, so the slug date is one day after the event date on purpose. The announcement itself came from the countries, not opec.org. |
| 6 | opec_2023_06_04 | 4 Jun 2023 (Sun) | 55-04-jun-2023 | 35th ONOMM: set the group's overall 2024 production level at 40.46 mb/d, 1 Jan to 31 Dec 2024 | ministerial | unsure | unsure | Weekend: date-only OK | PARKED. The page text gives the 2024 level "as per the attached table" but not the 2023 level, so I can't tell cut from flat. Open the page and read the production table before entering. |
| 7 | opec_2023_11_30 | 30 Nov 2023 (Thu) | 39-30-nov-2023 | Seven countries plus Russia announce additional voluntary cuts totalling 2.2 mb/d for Q1 2024 | voluntary_group | cut | yes | TIME ASSUMED | The headline overstates the new cut. The 4 Oct 2023 release says Saudi Arabia's 1 mb/d cut and Russia's 300 kb/d export cut already ran to end Dec 2023. The 30 Nov release lists Saudi 1,000 and Russia 500 (300 crude + 200 products) for Jan to Mar. Listed total: 1,000 + 223 + 163 + 135 + 82 + 51 + 42 + 500 = 2,196 kb/d. If Saudi 1,000 and Russia 300 are rollovers, the new cut is about 896 kb/d. That is my reading of two releases; neither says it. Same day as the 36th ONOMM, which made no production change (Table 2B). |
| 8 | opec_2024_03_03 | 3 Mar 2024 (Sun) | 4-03-mar-2024 | Extend the 2.2 mb/d voluntary cuts through Q2 2024 (Russia 471 kb/d) | voluntary_group | hold | yes | Weekend: date-only OK | Extension of cuts that were due to start unwinding after March. |
| 9 | opec_2024_06_02 | 2 Jun 2024 (Sun) | 11-02-jun-2024 | Riyadh: 1.65 mb/d cuts extended to end 2025; 2.2 mb/d extended to end Sep 2024, then unwound monthly to end Sep 2025 | voluntary_group | hold | yes | Weekend: date-only OK | Same day as 12-02-jun-2024 (37th ONOMM, which extends the group level through 2025). Put that URL in notes. Proposed group voluntary_group, because the Riyadh release changes the near-term supply path. Tagged hold under the pause/delay rule even though it sets an unwind path. |
| 10 | opec_2024_09_05 | 5 Sep 2024 (Thu) | 17-05-sep-2024 | Eight countries extend the 2.2 mb/d cuts by two months to end Nov 2024, unwind from 1 Dec | voluntary_group | hold | yes | TIME ASSUMED | Release also covers Iraq and Kazakhstan overproduction. |
| 11 | opec_2024_11_03 | 3 Nov 2024 (Sun) | 23-03-nov-2024 | Extend the 2.2 mb/d cuts one more month to end Dec 2024 | voluntary_group | hold | yes | Weekend: date-only OK | |
| 12 | opec_2024_12_05 | 5 Dec 2024 (Thu) | 29-05-dec-2024 | Eight countries extend 1.65 mb/d to end 2026 and move the 2.2 mb/d unwind to Apr 2025 to Sep 2026 | voluntary_group | hold | yes | TIME ASSUMED | Same day as 28-05-dec-2024 (38th ONOMM: group level extended to end 2026, UAE +0.3 mb/d phased in from Apr 2025). Put that URL in notes. Proposed group voluntary_group, same reason as row 9. The 2 Jun 2024 release gave 1 Dec as the planned meeting date; I don't know why it moved. |
| 13 | opec_2025_04_03 | 3 Apr 2025 (Thu) | 557-03-april-2025 | Eight countries raise output 411 kb/d for May, three monthly steps in one | voluntary_group | increase | yes | TIME ASSUMED | CONFOUND TO SOURCE: I recall the US tariff announcement was 2 Apr 2025 (from memory, not opec.org). Do not put it in confound_note until it has a dated primary source. |
| 14 | opec_2025_05_03 | 3 May 2025 (Sat) | 563-03-may-2025 | Eight countries raise output 411 kb/d for June | voluntary_group | increase | yes | Weekend: date-only OK | repeat (411 again). |
| 15 | opec_2025_05_31 | 31 May 2025 (Sat) | 566-31-may-2025 | Eight countries raise output 411 kb/d for July | voluntary_group | increase | yes | Weekend: date-only OK | repeat (411 again). The 3 May release gave 1 Jun as the next meeting; it was held 31 May. |
| 16 | opec_2025_07_05 | 5 Jul 2025 (Sat) | 569-5-july-2025 | Eight countries raise output 548 kb/d for August | voluntary_group | increase | yes | Weekend: date-only OK | |
| 17 | opec_2025_08_03 | 3 Aug 2025 (Sun) | 572-03-august-2025 | Eight countries raise output 547 kb/d for September | voluntary_group | increase | yes | Weekend: date-only OK | |
| 18 | opec_2025_09_07 | 7 Sep 2025 (Sun) | 573-07-september-2025 | Eight countries start unwinding the 1.65 mb/d tranche: +137 kb/d for October | voluntary_group | increase | yes | Weekend: date-only OK | First step of this tranche. No preset path, so each month is a fresh decision. |
| 19 | opec_2025_10_05 | 5 Oct 2025 (Sun) | 578-05-october-2025 | +137 kb/d for November | voluntary_group | increase | yes | Weekend: date-only OK | repeat (137 again). |
| 20 | opec_2025_11_02 | 2 Nov 2025 (Sun) | 579-02-november-2025 | +137 kb/d for December, then pause Jan to Mar 2026 | voluntary_group | hold | yes | Weekend: date-only OK | Pilot event, current id opec_2025_11. The pause is the news. The CSV source_url ends 1574579-02-november-2025.html, a different form that I could not open (the site showed a security check). The short slug in this table is the one I opened and read. |
| 21 | opec_2026_03_01 | 1 Mar 2026 (Sun) | 593-1-march-2026 | Eight countries resume the unwind: +206 kb/d for April | voluntary_group | increase | yes | Weekend: date-only OK | First step after the pause. |
| 22 | opec_2026_04_05 | 5 Apr 2026 (Sun) | 597-5-april-2026 | +206 kb/d for May. The release also warns about attacks on energy infrastructure and disruption of shipping routes | voluntary_group | increase | yes | Weekend: date-only OK | repeat (206 again). CONFOUND TO SOURCE: the text refers to infrastructure attacks and shipping disruption. I haven't looked up what happened. Keep out of confound_note until sourced. |
| 23 | opec_2026_05_03 | 3 May 2026 (Sun) | 602-3-may-2026 | Seven countries (UAE no longer named) raise output 188 kb/d for June | voluntary_group | increase | yes | Weekend: date-only OK | The releases give no reason for the UAE dropping out. Keep voluntary_group and note the seven-country group in the CSV notes. New step size. |
| 24 | opec_2026_06_07 | 7 Jun 2026 (Sun) | 604-7-june-2026 | +188 kb/d for July; compensation period extended to end Dec 2026 | voluntary_group | increase | yes | Weekend: date-only OK | repeat (188 again). Same day as the 41st ONOMM, which made no production change. |
| 25 | opec_2026_07_05 | 5 Jul 2026 (Sun) | 609-5-july-2026 | +188 kb/d for August | voluntary_group | increase | yes | Weekend: date-only OK | repeat (188 again). |
| 26 | opec_2026_08_02 | 2 Aug 2026 (Sun) | 611-2-august-2026 | +188 kb/d for September | voluntary_group | increase | yes | Weekend: date-only OK | repeat (188 again). |
| 27 | opec_2026_09_06 | 6 Sep 2026 (Sun) | 613-6-september-2026 | Seven countries keep September output unchanged for October | voluntary_group | hold | yes | Weekend and holiday: date-only OK | The next day, Mon 7 Sep 2026, is US Labor Day, so day 0 is Tue 8 Sep. |
| 28 | opec_2026_10_04 | 4 Oct 2026 (Sun) | 616-4-october-2026 | Seven countries keep September output unchanged for November | voluntary_group | hold | yes | Weekend: date-only OK | repeat (unchanged again). Day 0 is Mon 5 Oct, so the [-5,+5] window ends Mon 12 Oct. The 12 Oct 2026 release (619 in Table 2B) lands on day +5, outside [-1,+1]. |

Counts (1B)
- Direction: 4 cuts (rows 3, 4, 5, 7), 8 holds (rows 8 to 12, 20, 27, 28), 15 increases (rows 1, 2, 13 to 19, 21 to 26), 1 unsure (row 6). Total 28.
- Qualifies: 25 yes, 3 unsure (rows 2, 3, 6). Row 6 is parked.
- Timing: 20 weekend, 1 holiday, 1 timed pilot row, 6 TIME ASSUMED (rows 1, 2, 7, 10, 12, 13).
- Tagged repeat: 8 rows (14, 15, 19, 22, 24, 25, 26, 28).

## Counts, both tables (43 rows)
- Direction: 9 cuts, 13 holds, 19 increases, 2 unsure (A12 and row 6).
- Timing: 24 weekend, 1 holiday, 1 timed pilot, 17 time assumed.
- After the settled calls (21 Oct): A9 merges into A8 and A12 is skipped until the Saudi cut is sourced, so 41 rows and 8 independent cuts.
- Cuts: 9 on paper, 8 independent after the merge. Four have a firm day 0 (A1, rows 3, 4, 5) and four are time assumed (A5, A7, A8, row 7). Row 3 is "unsure". The 5-event minimum is met, but report the cut group both ways, with and without the time-assumed cuts.

## Ready to enter (after the 21 Oct calls)
- Ready (37): A1 to A8, A10, A11, A13, A15 (12 rows; A8 stands in for the merged April 2020 pair) and 1B rows 1, 4, 5 and 7 to 28 (25 rows). Rows 4, 5 and 20 are already in the CSV as pilots, so 34 are new.
- Enter with a caveat (3): A14 (sizes are in an attached table, not read), and 1B rows 2 and 3 (unsure whether they qualify).
- Not yet (1): 1B row 6 (parked, direction unknown).
- Skipped by decision (2): A9 (merged into A8) and A12 (waiting for the Saudi statement).
- Check: 37 + 3 + 1 + 2 = 43.

## Table 2A. Read, not an event, Dec 2016 to 2021 (first pass, 35 read plus 16 listing only)

| Date | Slug | Why not |
|---|---|---|
| 30 Nov 2016 | 458-30-nov-2016 | 171st Conference: OPEC-only cut (OPEC-14 target 32.5 mb/d from 1 Jan 2017). Before the Dec 2016 sample start; A1 maintains it |
| 24 May 2017 | 417-24-may-2017 | 3rd JMMC recommends the nine-month extension decided the next day (A2). Recommendation only, but see open call 5 |
| 8 Aug 2017 | 400-08-aug-2017 | JTC consultations on conformity |
| 25 May 2018 | 366-25-may-2018 | JMMC conformity report |
| 18 Jul 2018 | 361-18-jul-2018 | JMMC teleconference; sets monthly JMMC meetings |
| 23 Sep 2018 | 357-23-sep-2018 | 10th JMMC in Algiers; asks the JTC to study 2019 options |
| 25 Oct 2018 | 344-25-oct-2018 | JMMC; same instruction |
| 11 Nov 2018 | 343-11-nov-2018 | 11th JMMC; directs the JTC to refine 2019 options |
| 18 Jan 2019 | 337-18-jan-2019 | JMMC monitoring |
| 18 Mar 2019 | 334-18-mar-2019 | 13th JMMC monitoring |
| 19 May 2019 | 332-19-may-2019 | 14th JMMC; says the recommendation for H2 2019 comes at the June meetings |
| 27 Aug 2019 | 327-27-aug-2019 | JMMC monitoring |
| 12 Sep 2019 | 326-12-sep-2019 | 16th JMMC monitoring |
| 8 Feb 2020 | 318-08-feb-2020 | JTC recommendation to extend adjustments to end 2020; recommendation only |
| 5 Mar 2020 | 317-05-mar-2020 | OPEC Heads of Delegation recommend extending the proposed extra 1.5 mb/d adjustment to end 2020; recommendation only |
| 5 Mar 2020 | 316-05-mar-2020 | 178th (Extraordinary) Conference; recommendation only. The joint meeting on 6 Mar 2020 has no release on opec.org (Gaps) |
| 5 Jun 2020 | 308-05-jun-2020 | Notice: 179th Conference and 11th ONOMM moved from 9/10 Jun to Sat 6 Jun |
| 18 Jun 2020 | 304-18-jun-2020 | 19th JMMC; notes extra voluntary contributions of 1.2 mb/d in June by Saudi Arabia, UAE, Kuwait and Oman |
| 15 Jul 2020 | 301-15-jul-2020 | 20th JMMC monitoring |
| 19 Aug 2020 | 300-19-aug-2020 | 21st JMMC monitoring |
| 17 Sep 2020 | 297-17-sep-2020 | 22nd JMMC; recommends extending the compensation period |
| 19 Oct 2020 | 292-19-oct-2020 | 23rd JMMC monitoring |
| 17 Nov 2020 | 285-17-nov-2020 | 24th JMMC monitoring |
| 30 Nov 2020 | 283-30-nov-2020 | Notice: 180th Conference adjourned, reconvenes 1 Dec. No outcome release exists on the 2020 page |
| 3 Feb 2021 | 276-03-feb-2021 | 26th JMMC; notes Saudi Arabia's extra voluntary cut "taking effect on 1 February for two months" |
| 27 Apr 2021 | 267-27-apr-2021 | 16th ONOMM: continues the 15th ONOMM adjustments for June and July |
| 1 Jun 2021 | 266-01-jun-2021 | 17th ONOMM: reconfirms the July adjustment |
| 1 Jul 2021 | 214-01-jul-2021 | Notice: 31st JMMC and 18th ONOMM adjourn to Fri 2 Jul |
| 2 Jul 2021 | 213-02-jul-2021 | Notice: 18th ONOMM adjourns to Mon 5 Jul |
| 5 Jul 2021 | 212-05-jul-2021 | Reconvened 18th ONOMM called off. No decision, no production change stated. Mon 5 Jul 2021 was likely a US market holiday (check). See open call 4 |
| 17 Jul 2021 | 210-17-jul-2021 | Notice: 19th ONOMM convenes Sun 18 Jul at 12:00 CEST |
| 1 Sep 2021 | 207-01-sep-2021 | 20th ONOMM: reconfirms the 0.4 mb/d step for October, already set by A15 |
| 4 Oct 2021 | 179-04-oct-2021 | 21st ONOMM: reconfirms 0.4 mb/d for November |
| 4 Nov 2021 | 168-04-nov-2021 | 22nd ONOMM: reconfirms 0.4 mb/d for December |
| 2 Dec 2021 | 165-02-dec-2021 | 23rd ONOMM: reconfirms 0.4 mb/d for January 2022; the meeting stays in session |

Listing only (body not read, classified from the listing summary as routine JMMC conformity reports, 16 releases): 378-21-jan-2018, 376-22-feb-2018 (duplicate 375-22-feb-2018), 371-21-mar-2018, 369-20-apr-2018, 360-30-aug-2018, and 11 routine 2017 JMMC releases with slugs 436, 429, 424, 419, 408, 404, 403, 398, 392, 388 and 380 (full slugs are on the 2017 year page). If you want the claim "every release was read", these 16 still need opening.

## Table 2B. Read, not an event, Jan 2022 to Oct 2026 (first pass, 35)

| Date | Slug | Why not |
|---|---|---|
| 4 Jan 2022 | 151-04-jan-2022 | Reconfirms the step already set |
| 2 Feb 2022 | 150-02-feb-2022 | Reconfirms |
| 2 Mar 2022 | 136-02-mar-2022 | Reconfirms |
| 31 Mar 2022 | 132-31-mar-2022 | OPEC Conference on production estimate sources, not output |
| 31 Mar 2022 | 130-31-mar-2022 | 27th ONOMM: the text says it reconfirms the plan and the 0.432 mb/d step for May |
| 5 May 2022 | 129-05-may-2022 | Reconfirms |
| 30 Jun 2022 | 103-30-jun-2022 | Reconfirms |
| 4 Dec 2022 | 69-04-dec-2022 | Reaffirms; changes the JMMC meeting frequency |
| 1 Feb 2023 | 65-01-feb-2023 | JMMC monitoring |
| 5 Jul 2023 | 51-05-jul-2023 | Ministers thank Saudi Arabia for extending its 1 mb/d cut for August, plus Russia and Algeria cuts. The extension itself is a saudi_unilateral candidate; its announcement date needs a Saudi source |
| 4 Aug 2023 | 49-04-aug-2023 | JMMC monitoring; notes the Saudi 1 mb/d cut extended to September and a Russian export cut. Same saudi_unilateral question |
| 4 Oct 2023 | 44-04-oct-2023 | JMMC monitoring; notes the Saudi 1 mb/d cut and a Russian 300 kb/d export cut extended to end Dec 2023. Same question |
| 30 Nov 2023 | 38-30-nov-2023 | 36th ONOMM: no production change |
| 3 Jan 2024 | 1-03-jan-2024 | Statement of commitment |
| 1 Feb 2024 | 2-01-feb-2024 | JMMC monitoring |
| 3 Apr 2024 | 7-03-apr-2024 | JMMC monitoring |
| 1 Aug 2024 | 14-01-aug-2024 | JMMC; repeats the June plan |
| 2 Oct 2024 | 21-02-oct-2024 | JMMC monitoring |
| 10 Dec 2024 | 32-10-dec-2024 | OPEC Conference: elections and administration |
| 3 Feb 2025 | 33-03-feb-2025 | JMMC monitoring |
| 3 Mar 2025 | 518-03-march-2025 | Eight countries reaffirm the 5 Dec 2024 path; the April start was already set |
| 5 Apr 2025 | 558-05-april-2025 | JMMC monitoring |
| 28 May 2025 | 564-28-may-2025 | 39th ONOMM: reaffirms the group level to end 2026 and mandates a capacity mechanism |
| 28 Jul 2025 | 571-28-july-2025 | JMMC monitoring |
| 1 Oct 2025 | 576-01-october-2025 | JMMC monitoring |
| 30 Nov 2025 | 582-30-november-2025 | 40th ONOMM: reaffirms the level and approves the capacity mechanism |
| 30 Nov 2025 | 583-30-november-2025 | Eight countries reaffirm the 2 Nov decision |
| 4 Jan 2026 | 587-4-january-2026 | Reaffirms the 2 Nov 2025 pause, already set |
| 1 Feb 2026 | 589-1-february-2026 | Reaffirms the pause for March, already set |
| 1 Feb 2026 | 590-1-february-2026 | JMMC monitoring |
| 5 Apr 2026 | 596-5-april-2026 | JMMC statement on shipping routes and infrastructure |
| 7 Jun 2026 | 605-7-june-2026 | 41st ONOMM: reaffirms the group level to end 2026 |
| 2 Aug 2026 | 612-2-august-2026 | JMMC; same shipping and infrastructure language |
| 4 Oct 2026 | 617-4-october-2026 | JMMC; same language |
| 12 Oct 2026 | 619-12-october-2026 | Riyadh ministers' sidelines meeting: reaffirm the 7 Jun decisions; says shipping and insurance costs have reached unprecedented levels |

Same-day ONOMM and JMMC releases (30 Nov 2023, 7 Jun 2026, 2 Aug 2026, 4 Oct 2026 and others) are left out on purpose because they made no production change. The README should say so.

## Open calls (1 to 4 settled by John on 21 Oct 2026; 5 to 7 still open, my lean stated)
1. SETTLED (yes). Dating when a Conference release comes first (A4, A5, A6, A7). Use the earliest release that states the decision, as in the dating rule above. A7 follows the rule too: settled as Thu 5 Dec on 21 Oct, because Al Jazeera reported the extra 500k on 5 Dec.
2. SETTLED (yes). A8 and A9 are one reaction. They are 3 days apart and may share day 0 (Mon 13 Apr 2020, if Good Friday closed the NYSE, check). One event: enter A8 (time assumed) and put A9 in notes.
3. SETTLED (yes). A12, 5 Jan 2021. The group release is a reaffirmation, and the Saudi cut is the market news. Lean: skip the ministerial row and enter one saudi_unilateral row once the Saudi statement gives the date and time.
4. SETTLED (yes). Failed meetings: 1 to 5 Jul 2021 (212-05-jul-2021) and 6 Mar 2020 (no release on opec.org). Neither is a decision, so neither is in Table 1. Lean: leave them out of the main run and mention them in the README as no-agreement cases that are not tested. They would need their own category and outside sources.
5. The 24 May 2017 JMMC recommendation (417-24-may-2017) came the day before A2. Lean: date A2 on 25 May (the formal decision) and note 24 May. If you want the earliest credible signal instead, the row moves to 24 May and the JMMC release becomes the source.
6. Regime: A8, A9 and A10 (Apr to Jun 2020) have estimation windows that run through the Feb to Mar 2020 crash (check with --dates-only). Betas from that window are unreliable. Lean: keep them in, and run the main result with and without them.
7. Pre-sample events in A1's windows. The OPEC-only decision of 30 Nov 2016 sits about 8 trading days before A1's day 0, just after its estimation window ends. The Sep 2016 Algiers releases (slugs 495 and 496 on the 2016 page, not read) fall inside the estimation window. The skip rule only masks events that are in the CSV. Ask the build session whether a mask-only row is possible, or accept the contamination and say so in the README.

## Gaps
- Scope: this file now covers Dec 2016 to Oct 2026, so the README can claim the sample start from DECISIONS.md. 17 weekday rows carry an assumed announcement time (the time_assumed rule).
- Saudi unilateral cuts: DECISIONS.md already tags them saudi_unilateral and reports them as a separate subsample. None is collected, because the source has to be the Saudi statement, not opec.org. Known candidates from opec.org references: the June 2020 extra voluntary cuts (Saudi, UAE, Kuwait, Oman, 1.2 mb/d per 304-18-jun-2020), the Feb to Apr 2021 Saudi cut (A12, A13) and the 2023 extensions (Table 2B).
- Missing outcome releases on opec.org: the 8th ONOMM (6 Mar 2020), the 180th Conference (1 Dec 2020) and the 181st Conference (1 Jul 2021).
- Attached production tables I did not read: A12 (Feb and Mar levels), A14 (May to Jul steps), A15 (baselines from May 2022) and 1B row 6.
- Surprise flags: none are set in this file. The CSV already has surprise_flag=1 on the 2 Apr 2023 event (same-day Reuters "surprise" headline, per DECISIONS.md).
- The 2025 year page listed nothing for January 2025 and nothing between 3 Feb and 3 Mar 2025. I don't know if any releases exist there.
- Nothing here has been checked outside opec.org. Spot-check rows in your own Chrome.
