"""Draw the summary charts in the README from the saved results.

Run from the project root, after run_opec.py and run_supply_route.py:

    uv run python scripts/readme_charts.py

Reads only results/*.csv and results/*_run_info.json (no prices, no
regressions), so it can never change a result. Saves:

- charts/where_the_move_happens.png: mean XLE CAR before day 0 and from
  day 0 on, for OPEC+ cuts, OPEC+ increases and supply-route attacks.
- charts/opec_event_cars.png: each OPEC+ decision's [-1,+1] CAR with a 95%
  interval, by direction.
- charts/supply_route_event_cars.png: each attack's XLE [0,+1] CAR with a
  95% interval, by route.
- charts/social_preview.png: the image GitHub shows when the repository
  link is shared (uploaded by hand under Settings > General > Social preview).

Assumptions:
- The main runs' files are used (not _day0_shifted or _official_time).
- OPEC+ groups leave out saudi_unilateral rows, as the headline tests do
  (run_opec.opec_groups).
- Every average counts "ok" events only, and every other event is printed
  with its reason before any chart is drawn.
"""

import json
from pathlib import Path

import pandas as pd

from event_study import reporting
from event_study.aggregate import excluded_events

RESULTS = Path("results")
CHARTS = Path("charts")
OPEC_WINDOW = (-1, 1)
ATTACK_WINDOW = (0, 1)
ATTACK_SECURITY = "XLE"

# Categorical slots 1 to 3 of the palette in plot_prices.py, in the order
# run_opec.py already uses for cuts (1) and increases (2).
OPEC_COLORS = {"cut": "#2a78d6", "increase": "#eb6834", "hold": "#1baf7a"}
ROUTE_COLORS = {"gulf_facility": "#2a78d6", "red_sea": "#eb6834", "hormuz": "#1baf7a"}
OPEC_NAMES = {"cut": "Cuts", "increase": "Increases", "hold": "Holds"}
ROUTE_NAMES = {
    "gulf_facility": "Gulf energy facilities",
    "red_sea": "Red Sea shipping",
    "hormuz": "Hormuz and Gulf shipping",
}


def data_end(run_info_path: Path, ticker: str | None = None) -> str:
    """Last return date recorded in a run info file, as "YYYY-MM-DD".

    The OPEC+ file has one returns_used entry; the supply-route file has
    one per ticker, so pass ticker for it.
    """
    used = json.loads(run_info_path.read_text(encoding="utf-8"))["returns_used"]
    return (used[ticker] if ticker else used)["last_date"]


def report_excluded(name: str, results: pd.DataFrame) -> None:
    """Print every event that is not "ok", with its reason, or "none"."""
    excluded = excluded_events(results)
    print(f"{name}: {len(results)} events, {len(excluded)} excluded from the averages")
    for _, row in excluded.iterrows():
        print(f"  {row['event_id']} ({row['status']}): {row['reason']}")


def ok_abnormal(results: pd.DataFrame, abnormal: pd.DataFrame) -> pd.DataFrame:
    """The abnormal-return rows (indexed by event_id) of results' "ok" events."""
    ids = results.loc[results["status"] == "ok", "event_id"]
    return abnormal.loc[ids]


def group_heading(name: str, row: pd.Series) -> str:
    """'Cuts (N = 7): mean +1.51%, t 1.64' from a row of an across-event CSV."""
    t = f"{row['cross_sectional_t']:.2f}".replace("-", "−")
    return f"{name} (N = {row['n_ok']}): mean {reporting.signed(row['mean_car'])}, t {t}"


def headings(across: pd.DataFrame, names: dict[str, str]) -> dict[str, str]:
    """{group: heading} for the groups in names, from across-event rows of one window."""
    rows = across.set_index("group")
    return {group: group_heading(name, rows.loc[group]) for group, name in names.items()}


def main() -> None:
    opec = pd.read_csv(RESULTS / "opec_results.csv")
    opec = opec[opec["decision_group"] != "saudi_unilateral"]
    opec_abnormal = pd.read_csv(RESULTS / "opec_abnormal.csv", index_col="event_id")
    opec_across = pd.read_csv(RESULTS / "opec_across_event.csv")
    opec_end = data_end(RESULTS / "opec_run_info.json")

    attacks = pd.read_csv(RESULTS / "supply_route_results.csv")
    attacks = attacks[attacks["security"] == ATTACK_SECURITY]
    attack_abnormal = pd.read_csv(RESULTS / "supply_route_abnormal.csv")
    attack_abnormal = (
        attack_abnormal[attack_abnormal["security"] == ATTACK_SECURITY]
        .drop(columns="security")
        .set_index("event_id")
    )
    attack_across = pd.read_csv(RESULTS / "supply_route_across_event.csv")
    attack_end = data_end(RESULTS / "supply_route_run_info.json", ATTACK_SECURITY)

    report_excluded("OPEC+ (without saudi_unilateral)", opec)
    report_excluded(f"Supply-route attacks, {ATTACK_SECURITY}", attacks)

    timing_groups = {
        "OPEC+ cuts": ok_abnormal(opec[opec["direction"] == "cut"], opec_abnormal),
        "OPEC+ increases": ok_abnormal(opec[opec["direction"] == "increase"], opec_abnormal),
        "Supply-route attacks": ok_abnormal(attacks, attack_abnormal),
    }
    # Both studies use the same price snapshot today; name both dates if not.
    through = opec_end if opec_end == attack_end else f"{opec_end} (OPEC+) and {attack_end} (attacks)"
    reporting.draw_move_timing_chart(
        timing_groups,
        CHARTS / "where_the_move_happens.png",
        title="Most of XLE's average move comes before day 0",
        caption=(
            "Mean XLE abnormal return (return minus a market model on SPY), summed over days "
            "−5 to −1 and over days 0 to +5. The two columns of a pair add up to the mean CAR "
            "over days −5 to +5. Descriptive split, not a pre-registered test. N counts events "
            "that ran. Source: results/opec_abnormal.csv and supply_route_abnormal.csv, data "
            f"through {through}."
        ),
    )

    opec_label = reporting.window_label(OPEC_WINDOW)
    in_window = (opec_across["sample"] == "all") & (opec_across["window"] == opec_label)
    reporting.draw_event_car_dots(
        opec,
        CHARTS / "opec_event_cars.png",
        window=OPEC_WINDOW,
        group_column="direction",
        group_labels=headings(opec_across[in_window], OPEC_NAMES),
        colors=OPEC_COLORS,
        title="XLE abnormal return on each OPEC+ decision, days −1 to +1",
        xlabel="Cumulative abnormal return, days −1 to +1 (dot), with 95% interval (bar)",
        caption=(
            "Abnormal return = XLE return minus a market model on SPY. Interval: 1.96 standard "
            "errors from the event's own estimation window, treating alpha and beta as exact. "
            "Rows are named by decision date (day 0 can be the next session). "
            "Thin vertical line: the group mean. t: cross-sectional t across the group's events; "
            "the headline tests are cuts and increases. Saudi unilateral actions are not in these "
            f"groups. Source: results/opec_results.csv, data through {opec_end}."
        ),
    )

    attack_label = reporting.window_label(ATTACK_WINDOW)
    attack_rows = attack_across[
        (attack_across["sample"] == "all")
        & (attack_across["security"] == ATTACK_SECURITY)
        & (attack_across["window"] == attack_label)
    ]
    pooled = attack_rows.set_index("group").loc["all"]
    reporting.draw_event_car_dots(
        attacks,
        CHARTS / "supply_route_event_cars.png",
        window=ATTACK_WINDOW,
        group_column="route",
        group_labels=headings(attack_rows, ROUTE_NAMES),
        colors=ROUTE_COLORS,
        title=(
            "XLE abnormal return on each supply-route attack, days 0 to +1\n"
            f"All {pooled['n_ok']} attacks: mean {reporting.signed(pooled['mean_car'])}, "
            f"t {pooled['cross_sectional_t']:.2f}, p {pooled['cs_p']:.2f} (primary test)"
        ),
        xlabel="Cumulative abnormal return, days 0 to +1 (dot), with 95% interval (bar)",
        caption=(
            "Abnormal return = XLE return minus a market model on SPY. Interval: 1.96 standard "
            "errors from the event's own estimation window, treating alpha and beta as exact. "
            "Rows are named by local attack date (day 0 can be the next session). "
            "Thin vertical line: the route mean. t: cross-sectional t across the route's events, "
            "unadjusted (route subgroups are descriptive breakdowns). Source: "
            f"results/supply_route_results.csv, data through {attack_end}."
        ),
    )

    n_opec = int((opec["status"] == "ok").sum())
    n_attacks = int((attacks["status"] == "ok").sum())
    reporting.draw_social_preview(
        timing_groups,
        CHARTS / "social_preview.png",
        title="Geopolitical Events\nand Markets",
        subtitle=(
            f"Event studies of {n_opec} OPEC+ decisions and\n"
            f"{n_attacks} attacks on Gulf oil supply routes.\n"
            "XLE, ITA and GLD vs a market model on SPY."
        ),
        footer="Python  ·  pandas  ·  statsmodels  ·  pre-registered tests",
        url="github.com/JohnMitiguy/event-study",
        chart_title="Average XLE abnormal return",
    )


if __name__ == "__main__":
    main()
