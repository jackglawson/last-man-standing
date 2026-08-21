import datetime as dt
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — no display server on CI runners
import matplotlib.pyplot as plt

from main import main

OUTPUT_DIR = Path(__file__).resolve().parent / "public"


def generate_report():
    strategy, scores = main()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots()
    ax.plot(scores)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Score")
    ax.set_title("Simulated annealing convergence")
    fig.savefig(OUTPUT_DIR / "scores.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    df = strategy.get_strategy_df()
    table_html = df.to_html(index=False, classes="strategy-table", border=0)

    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Last Man Standing — weekly picks</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  table.strategy-table {{ border-collapse: collapse; width: 100%; }}
  table.strategy-table th, table.strategy-table td {{ padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; text-align: left; }}
  table.strategy-table th {{ background: #f5f5f5; }}
  img {{ max-width: 100%; }}
  footer {{ color: #777; font-size: 0.85rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>Last Man Standing — weekly picks</h1>
<p>Solver convergence:</p>
<img src="scores.png" alt="Simulated annealing score over epochs">
<h2>Recommended strategy</h2>
{table_html}
<footer>Last updated {generated_at}</footer>
</body>
</html>
"""
    (OUTPUT_DIR / "index.html").write_text(html)


if __name__ == "__main__":
    generate_report()
