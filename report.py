import datetime as dt
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — no display server on CI runners
import matplotlib.pyplot as plt

from data import get_matches
from main import main
from visualisation import (
    get_matches_df,
    get_team_counts_df,
    match_count_per_match_day_figure,
    match_day_schedule_figure,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "public"


def generate_report():
    strategy, scores, min_improvements, duration_seconds = main()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with plt.rc_context({"font.size": 6}):
        fig, (ax_score, ax_min_improvement) = plt.subplots(
            2, 1, sharex=True, figsize=(4.5, 4.5)
        )
        ax_score.plot(scores)
        ax_score.set_ylabel("Score")
        ax_score.set_title("Simulated annealing convergence")
        ax_min_improvement.plot(min_improvements)
        ax_min_improvement.set_xlabel("Epoch")
        ax_min_improvement.set_ylabel("Min improvement")
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / "scores.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    df = strategy.get_strategy_df()
    # A "match completed" row means the result is already known, i.e. that
    # week's pick is history and can no longer change.
    is_fixed = df["probability_source"] == "match completed"

    def highlight_fixed(row):
        style = "background-color: #e0e0e0;" if is_fixed.loc[row.name] else ""
        return [style] * len(row)

    strategy_table_html = (
        df.style.hide(axis="index")
        .apply(highlight_fixed, axis=1)
        .to_html(table_attributes='class="report-table"')
    )

    upcoming = df[~is_fixed]
    if not upcoming.empty:
        next_pick = upcoming.iloc[0]
        next_pick_html = (
            f'<p class="next-pick">Pick for match day {next_pick["match_day"]}: '
            f'{next_pick["team"]} ({next_pick["date"]})</p>'
        )
    else:
        next_pick_html = '<p class="next-pick">No upcoming picks.</p>'

    matches = get_matches()
    matches_df = get_matches_df(matches)

    schedule_html = match_day_schedule_figure(matches_df).to_html(
        full_html=False, include_plotlyjs="cdn"
    )
    match_count_html = match_count_per_match_day_figure(matches_df).to_html(
        full_html=False, include_plotlyjs=False
    )
    teams_table_html = get_team_counts_df(matches, df).to_html(
        index=False, classes="report-table", border=0
    )

    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LMS solver</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  .table-scroll {{ overflow-x: auto; }}
  table.report-table {{ border-collapse: collapse; width: 100%; font-size: 0.75rem; }}
  table.report-table th, table.report-table td {{ padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; text-align: left; white-space: nowrap; }}
  table.report-table th {{ background: #f5f5f5; }}
  img {{ max-width: 100%; display: block; margin: 1rem auto; }}
  .next-pick {{ font-size: 1.2rem; font-weight: 600; background: #eef6ff; border: 1px solid #cfe3fb; padding: 0.75rem 1rem; border-radius: 6px; }}
  footer {{ color: #777; font-size: 0.85rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>LMS solver</h1>
{next_pick_html}
<p>Solver convergence:</p>
<img src="scores.png" alt="Simulated annealing score and min improvement per epoch">
<p>Simulated annealing ran in {duration_seconds:.2f}s over {len(scores)} epochs.</p>
<h2>Recommended strategy</h2>
<p>Grey rows are already-played matches — fixed and no longer part of the search.</p>
<div class="table-scroll">{strategy_table_html}</div>
<h2>Schedule overview</h2>
{schedule_html}
<h2>Matches per match day</h2>
{match_count_html}
<h2>Teams</h2>
<div class="table-scroll">{teams_table_html}</div>
<footer>Last updated {generated_at}</footer>
</body>
</html>
"""
    (OUTPUT_DIR / "index.html").write_text(html)
    print("Saving to ", OUTPUT_DIR / "index.html")


if __name__ == "__main__":
    generate_report()
