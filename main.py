from dataclasses import dataclass
import random
from copy import deepcopy
from typing import Callable

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from data import get_matches, get_upcoming_match_odds, get_elos, int_to_date
from model import elos_to_modelled_probabilities


@dataclass
class Match:
    match_day: int
    league: str
    home_team: str
    away_team: str
    p_home: float
    p_away: float
    probability_source: str
    date_id: int

    def __post_init__(self):
        assert (
            self.p_home >= 0 and self.p_away >= 0 and (self.p_away + self.p_home <= 1)
        )
        self.team_to_p_lose = {self.home_team: self.p_away, self.away_team: self.p_home}

    def get_p_lose(self, team):
        return self.team_to_p_lose[team]

    def get_p_draw(self):
        return 1 - self.p_home - self.p_away


class Tournament:
    def __init__(self, list_of_matches: list):
        self.matches = {}  # {match_day: [match]}
        self.match_weeks = []
        self.teams = []
        self.p_lose_mapping = {}
        self.p_draw_mapping = {}

        for match in list_of_matches:
            self.add_match(match)

    def add_match(self, match: Match):
        if match.match_day not in self.matches:
            self.matches[match.match_day] = []
            self.p_lose_mapping[match.match_day] = {}
            self.p_draw_mapping[match.match_day] = {}

        self.matches[match.match_day].append(match)

        self.match_weeks = sorted(self.matches.keys())

        if match.home_team not in self.teams:
            self.teams.append(match.home_team)
        if match.away_team not in self.teams:
            self.teams.append(match.away_team)

        self.p_lose_mapping[match.match_day][match.home_team] = match.get_p_lose(
            match.home_team
        )
        self.p_lose_mapping[match.match_day][match.away_team] = match.get_p_lose(
            match.away_team
        )
        self.p_draw_mapping[match.match_day][match.home_team] = match.get_p_draw()
        self.p_draw_mapping[match.match_day][match.away_team] = match.get_p_draw()

    @classmethod
    def from_apis(cls):

        matches = get_matches()
        matches = [match for match in matches if match['is_valid_match']]

        upcoming_match_odds = get_upcoming_match_odds()
        upcoming_match_odds_lookup = {
            (m["date_id"], m["home_team"], m["away_team"]): (m["p_home"], m["p_away"])
            for m in upcoming_match_odds
        }

        elos = get_elos()


        def get_elo_for_team(elos: dict, team: str):
            if team in elos:
                return elos[team]
            else:
                print(f"WARNING: Could not find elo for {team}. Using average elo instead")
                return np.mean(list(elos.values()))


        def get_match(match: dict):
            match_day = match["match_day"]
            league = match["league"]
            date_id = match["date_id"]
            home_team = match["home_team"]
            away_team = match["away_team"]

            if match["score_home"] is not None:
                if match["score_home"] > match["score_away"]:
                    p_home, p_away = 1, 0

                elif match["score_home"] < match["score_away"]:
                    p_home, p_away = 0, 1

                else:
                    p_home, p_away = 0, 0

                probability_source = "match completed"

            elif (date_id, home_team, away_team) in upcoming_match_odds_lookup:
                p_home, p_away = upcoming_match_odds_lookup[
                    (date_id, home_team, away_team)
                ]
                probability_source = "betfair"

            else:
                elo_home = get_elo_for_team(elos, home_team)
                elo_away = get_elo_for_team(elos, away_team)
                p_home, p_away = elos_to_modelled_probabilities(elo_home, elo_away)
                probability_source = "elos"

            return Match(
                match_day=match_day,
                league=league,
                home_team=home_team,
                away_team=away_team,
                p_home=p_home,
                p_away=p_away,
                probability_source=probability_source,
                date_id=date_id,
            )

        return cls([get_match(match) for match in matches])

    def as_dataframe(self):
        return pd.concat([pd.DataFrame(x) for x in self.matches.values()])


class Strategy:
    def __init__(self, strategy: list, tournament: Tournament, locked_teams: set = None):
        self.tournament = tournament
        self.validate_input(strategy)
        self.week_to_team = {
            date: team for date, team in zip(self.tournament.match_weeks, strategy)
        }
        self.team_to_week = {
            team: date for date, team in zip(self.tournament.match_weeks, strategy)
        }
        self.unused_teams = set(
            [team for team in self.tournament.teams if team not in strategy]
        )
        # Teams already used in past weeks; change_to_random_neighbour must
        # never reassign these.
        self.locked_teams = set(locked_teams or [])

    def validate_input(self, strategy):
        assert len(strategy) == len(
            self.tournament.match_weeks
        ), "Incorrect strategy length!"

        assert len(set(strategy)) == len(strategy), "Contains duplicates!"

        for team, date in zip(strategy, self.tournament.match_weeks):
            assert (
                team in self.tournament.p_lose_mapping[date]
            ), f"{team} does not play on {date}!"

    @classmethod
    def from_random(cls, tournament: Tournament, locked_teams: list = None):
        locked_teams = locked_teams or []
        assert len(locked_teams) <= len(
            tournament.match_weeks
        ), "More locked teams than weeks in the tournament!"

        # Already-picked teams line up chronologically with the earliest
        # weeks (tournament.match_weeks is stored sorted ascending).
        locked_dates = dict(zip(tournament.match_weeks, locked_teams))

        # Process weeks with the fewest playing teams first (e.g. midweek
        # rounds where the ELC sits out), so a scarce week doesn't get left
        # with no valid team once the more flexible weeks have used them up.
        # Locked weeks are excluded: their team is already decided.
        dates_by_scarcity = sorted(
            (date for date in tournament.match_weeks if date not in locked_dates),
            key=lambda date: len(tournament.p_lose_mapping[date]),
        )

        used_teams = set(locked_teams)
        team_by_date = dict(locked_dates)
        for date in dates_by_scarcity:
            available_teams = [
                team
                for team in tournament.p_lose_mapping[date]
                if team not in used_teams
            ]
            if not available_teams:
                raise ValueError(f"No team available to pick for week {date}")
            team = random.choice(available_teams)
            team_by_date[date] = team
            used_teams.add(team)

        strategy = [team_by_date[date] for date in tournament.match_weeks]
        return cls(strategy, tournament, locked_teams=set(locked_teams))

    def make_swap(self, team_1, team_2):
        # pop (not just read) each team's current date, so a team that ends
        # up unused doesn't leave a stale team_to_week entry behind.
        team_1_date = self.team_to_week.pop(team_1, None)
        team_2_date = self.team_to_week.pop(team_2, None)
        self.unused_teams.discard(team_1)
        self.unused_teams.discard(team_2)

        if team_2_date is not None:
            self.week_to_team[team_2_date] = team_1
            self.team_to_week[team_1] = team_2_date
        else:
            self.unused_teams.add(team_1)

        if team_1_date is not None:
            self.week_to_team[team_1_date] = team_2
            self.team_to_week[team_2] = team_1_date
        else:
            self.unused_teams.add(team_2)

    def _can_swap(self, team_1, team_2):
        if team_1 == team_2:
            return False

        # Locked teams (already picked in past weeks) must never move, and
        # nothing may take over their week.
        if team_1 in self.locked_teams or team_2 in self.locked_teams:
            return False

        team_1_date = self.team_to_week.get(team_1)
        team_2_date = self.team_to_week.get(team_2)

        # A team moving into a date must actually play that week; a team
        # becoming unused has no such constraint.
        if team_2_date is not None and team_1 not in self.tournament.p_lose_mapping[team_2_date]:
            return False
        if team_1_date is not None and team_2 not in self.tournament.p_lose_mapping[team_1_date]:
            return False
        return team_1_date is not None or team_2_date is not None

    def change_to_random_neighbour(self):
        unlocked_teams = [
            team for team in self.tournament.teams if team not in self.locked_teams
        ]
        if not unlocked_teams:
            return
        team_1 = random.choice(unlocked_teams)
        candidates = [
            team_2 for team_2 in self.tournament.teams if self._can_swap(team_1, team_2)
        ]
        if not candidates:
            # No valid swap exists for this team this round; leave the
            # strategy unchanged rather than producing an invalid one.
            return
        team_2 = random.choice(candidates)
        self.make_swap(team_1, team_2)

    def score(self):
        score = 10
        for date in self.tournament.match_weeks:
            team = self.week_to_team[date]
            score -= (
                self.tournament.p_lose_mapping[date][team] * 2
                + self.tournament.p_draw_mapping[date][team]
            )
        return score

    def get_strategy_df(self):
        rows = []
        for date in self.tournament.match_weeks:
            team = self.week_to_team[date]
            match = next(
                m
                for m in self.tournament.matches[date]
                if m.home_team == team or m.away_team == team
            )
            p_win = match.p_home if match.home_team == team else match.p_away
            rows.append(
                {
                    "match_day": date,
                    "date": int_to_date(match.date_id),
                    "league": match.league,
                    "team": team,
                    "opponent_team": match.away_team if team == match.home_team else match.home_team,
                    "is_home": team == match.home_team,
                    "home_team": match.home_team,
                    "away_team": match.away_team,
                    "p_win": p_win,
                    "p_lose": self.tournament.p_lose_mapping[date][team],
                    "p_draw": self.tournament.p_draw_mapping[date][team],
                    "probability_source": match.probability_source,
                }
            )
        return pd.DataFrame(rows)


class SimulatedAnnealing:
    def __init__(self, tournament: Tournament, locked_teams: list = None):
        self.tournament = tournament
        self.strategy = Strategy.from_random(tournament, locked_teams=locked_teams)
        self.score = self.strategy.score()

    @staticmethod
    def get_min_improvement(epoch):
        return min(0, epoch * 0.0002 - 0.5)

    def iterate(self, epoch):
        neighbour = deepcopy(self.strategy)
        neighbour.change_to_random_neighbour()
        neighbour_score = neighbour.score()
        if neighbour_score - self.score > self.get_min_improvement(epoch):
            self.strategy = neighbour
            self.score = neighbour_score
        epoch += 1

    def run(self, n_epochs: int, callback: Callable):
        with tqdm(range(n_epochs)) as pbar:
            for epoch in pbar:
                self.iterate(epoch)
                pbar.set_postfix(score=self.score, min_improvement=self.get_min_improvement(epoch))
                callback(self, epoch)


if __name__ == "__main__":
    tournament = Tournament(
        [
            Match(1, "A", "B", 0.5, 0.3),
            Match(1, "C", "D", 0.1, 0.8),
            Match(2, "A", "C", 0.5, 0.3),
            Match(2, "B", "D", 0.1, 0.8),
        ],
    )
