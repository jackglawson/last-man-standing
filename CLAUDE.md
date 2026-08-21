# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Instructions from user

Do not edit .ipynb files unless I explicitly ask it

## Git workflow
- When working via agents, always work in a git worktree — don't edit the main checkout directly.
- Do not merge into master automatically. I will merge it manually
- Once I have said "merged", remove the worktree (`git worktree remove <path>`) and delete the branch (`git branch -d <branch>`).

## What this is

A solver for a "Last Man Standing" football pick'em pool: each week you pick one team to win, each team can only be used once across the season, and you're eliminated if your pick loses. The code fetches Premier League + Championship (ELC) fixtures/odds/Elo ratings, models win/draw/loss probabilities for every remaining match, and uses simulated annealing to search for a season-long pick strategy that maximizes expected survival.

## Running

No build step, package manifest, test suite, or linter is configured — this is a small, ungrouped collection of scripts and Jupyter notebooks. Dependencies (requests, pandas, bs4, numpy, tqdm, etc.) are installed in a project-local venv at `venv/`, not the system/conda Python — run scripts with that interpreter:

```
venv/bin/python3 main.py
```

Most exploratory/interactive work happens in the notebooks (`blackboard.ipynb`, `evaluate_elo_model.ipynb`, `dates.ipynb`). `main.py`'s `__main__` block runs the real solver end-to-end but doesn't print or save anything; `report.py` is the CI-facing entry point — it calls `main.main()` and writes a plot + strategy table to `public/` (see "CI / automation" below).

## Architecture

**`settings.py`** — config constants pulled out of `data.py`: `SEASON_YEAR`, `SEASON_START_DATE`, and `ELO_TEAM_MAPPING` (the clubelo → football-data team-name mapping used by `get_elos`). Update these here each season rather than editing `data.py` — the CI workflow does not touch these values, so a new season still needs a manual bump.

**`data.py`** — all external I/O, three data sources:
- `get_matches()` — fixtures/results from football-data.org (`get_matches_for_league`, called for `PL` and `ELC`), enriched with `week_number`, `day_of_week`, `is_midweek`, then run through `add_inferred_match_day` and `add_is_valid_match`.
- `get_upcoming_match_odds()` — h2h odds from the-odds-api.com (Betfair Exchange UK), converted from decimal odds to implied probabilities.
- `get_elos()` — Elo ratings scraped from clubelo.com's HTML ranking page (`_parse_elo_html`). `get_elos_old()` is a retired CSV-API version kept only for reference — don't use it for new code.

  Team names differ across all three sources (e.g. clubelo's "Man City" vs football-data's "Manchester City"), so each source has its own `to_team` name-mapping dict. When adding a new data source, expect to add another mapping.

  All outbound requests go through `get_url()`, wrapped in `mutable_lru_cache` — an in-memory LRU cache layered on top of a per-function, per-args-hash JSON cache on disk under `.cache/<function qualname>/`, with a TTL per call site (`get_url` itself: 10h; odds/matches/elo callers may layer their own). This is why re-running scripts doesn't necessarily hit the network — check `.cache/` and the TTL before assuming a call fetches fresh data.

  The match-day model: football-data.org's own `matchday` numbering is authoritative for PL but not aligned with ELC's, so `add_inferred_match_day` derives a shared `match_day` from `(week_number, is_midweek)`, keyed off PL. `add_is_valid_match` then encodes the pool's actual pick-eligibility rules from `README.md`: PL matches are always valid; midweek ELC matches are never valid (can't be picked); a match's validity also depends on whether its week resolved to a real match_day at all.

**`elo_model.py`** — pure math, no I/O. Converts a pair of Elo ratings into home/away/draw probabilities (`elos_to_modelled_probabilities`), applying a fixed home-advantage adjustment before normalizing. Only used as a fallback in `Tournament.from_apis` when neither a completed result nor bookmaker odds are available for a match.

**`strategy.py`** — the solver:
- `Match` / `Tournament` — `Tournament.from_apis()` is the real entry point: it pulls matches/odds/elos from `data.py`, and for each match picks a probability source in priority order — actual result if the match is finished, else Betfair odds if available, else the Elo model — recording which source was used (`probability_source`) on the `Match`.
- `Strategy` — a candidate season-long assignment of `week -> team`. `Strategy.from_random` seeds a valid strategy by filling *scarcer* weeks (fewest eligible teams — typically ELC-sit-out midweeks) first, so flexible weeks don't exhaust the teams a scarce week needs. `make_swap`/`_can_swap`/`change_to_random_neighbour` mutate a strategy while preserving validity (each team eligible for its assigned week, no team reused); `score()` rewards low loss/draw probability across the season; `get_strategy_df()` renders the final per-week picks as a DataFrame.
- `SimulatedAnnealing` — hill-climbs over `Strategy` neighbours, accepting worse moves early on and tightening (`get_min_improvement`, currently a hard floor of 0 after enough epochs) as `epoch` grows.

**`main.py`** — thin driver: `main()` builds a `Tournament.from_apis()`, runs 100 epochs of `SimulatedAnnealing`, and returns `(strategy, scores)`.

**`report.py`** — CI-facing entry point. Calls `main.main()`, saves a `scores` convergence plot and the `get_strategy_df()` table into `public/index.html` + `public/scores.png`. This is what `.github/workflows/report.yml` runs.

## CI / automation

`.github/workflows/report.yml` runs `report.py` every Friday 08:00 UTC (and on manual `workflow_dispatch`), then publishes `public/` to GitHub Pages via `actions/upload-pages-artifact` + `actions/deploy-pages`. Requires two repo secrets, `ODDS_API_KEY` and `FOOTBALL_DATA_TOKEN` (see below), and Pages source set to "GitHub Actions" in repo settings (one-time, done outside this repo).

## Notes specific to this domain

The pick-eligibility rules (`README.md`) are load-bearing and non-obvious from the data alone: PL midweek matches are pickable, ELC midweek matches never are, and if there's no PL match in a given week, that week isn't picked at all. Any change to `add_inferred_match_day` / `add_is_valid_match` should be checked against these rules, not just against making the code run.

`data.py` reads two API credentials from environment variables — `ODDS_API_KEY` (the-odds-api.com) and `FOOTBALL_DATA_TOKEN` (football-data.org) — via `os.environ`. Locally, populate a gitignored `.env` file (see `.env.example`); `data.py` loads it via `python-dotenv`'s `load_dotenv()`. In CI, the same names come from GitHub Secrets. These are the project's existing credentials, just relocated out of source — not rotated as part of this change.
