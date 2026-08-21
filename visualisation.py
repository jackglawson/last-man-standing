import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data import get_teams_df


def get_matches_df(matches: list) -> pd.DataFrame:
    return pd.DataFrame(matches)


def match_day_schedule_figure(matches_df: pd.DataFrame) -> go.Figure:
    """Each match's date against its football-data match day (orig) and the
    pool's own inferred match day, split by league, so mismatches between the
    two numberings are visible at a glance."""
    f = go.Figure()
    for league, color in [("PL", "firebrick"), ("ELC", "royalblue")]:
        league_df = matches_df[matches_df["league"] == league]
        f.add_trace(
            go.Scatter(
                x=league_df["date"],
                y=league_df["match_day_orig"],
                mode="markers",
                name=league,
                marker=dict(color=color),
                text=league_df["day_of_week"],
                customdata=league_df["is_valid_match"],
                hovertemplate="%{text}<br>%{x|%Y-%m-%d}<br>Match day: %{y}<br>Valid match: %{customdata}<extra>%{fullData.name}</extra>",
            )
        )

    for league, color in [("PL", "pink"), ("ELC", "lightblue")]:
        league_df = matches_df[matches_df["league"] == league]
        f.add_trace(
            go.Scatter(
                x=league_df["date"],
                y=league_df["match_day"],
                mode="markers",
                name=league,
                marker=dict(color=color),
                text=league_df["day_of_week"],
                customdata=league_df["is_valid_match"],
                hovertemplate="%{text}<br>%{x|%Y-%m-%d}<br>Match day: %{y}<br>Valid match: %{customdata}<extra>%{fullData.name}</extra>",
            )
        )

    return f


def match_count_per_match_day_figure(matches_df: pd.DataFrame) -> go.Figure:
    counts = (
        matches_df[["league", "match_day"]]
        .value_counts()
        .rename("count")
        .sort_index()
        .reset_index()
    )
    return px.bar(counts, x="match_day", y="count", color="league")


def get_team_counts_df(matches: list, strategy_df: pd.DataFrame) -> pd.DataFrame:
    teams = get_teams_df(matches)

    team_picked_count = strategy_df["team"].value_counts().rename("picked_count")
    teams = pd.merge(teams, team_picked_count, on="team", validate="1:1", how="outer")
    teams["picked_count"] = teams["picked_count"].fillna(0).astype(int)

    team_picked_on = strategy_df.set_index("team")["match_day"].rename("team_picked_on")
    teams = pd.merge(teams, team_picked_on, on="team", validate="1:1", how="outer")
    teams["team_picked_on"] = teams["team_picked_on"].fillna(-1).astype(int)

    opponent_team_picked_count = strategy_df["opponent_team"].value_counts().rename(
        "opponent_picked_count"
    )
    teams = pd.merge(
        teams,
        opponent_team_picked_count,
        left_on="team",
        right_on="opponent_team",
        validate="1:1",
        how="outer",
    )
    teams["opponent_picked_count"] = teams["opponent_picked_count"].fillna(0).astype(int)

    return teams.sort_values(["league", "elo"], ascending=False)
