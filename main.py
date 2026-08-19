from dataclasses import dataclass
import random
from copy import deepcopy
from typing import Callable

import numpy as np
import pandas as pd

from data import get_matches, get_upcoming_match_odds, get_elos
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
    def __init__(self, strategy: list, tournament: Tournament):
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
    def from_random(cls, tournament: Tournament):
        return cls(
            random.sample(tournament.teams, len(tournament.match_weeks)), tournament
        )

    def make_swap(self, team_1, team_2):
        team_1_date = None if team_1 in self.unused_teams else self.team_to_week[team_1]
        team_2_date = None if team_2 in self.unused_teams else self.team_to_week[team_2]

        if team_1_date is None:
            self.unused_teams.remove(team_1)
            self.unused_teams.add(team_2)
        else:
            self.week_to_team[team_1_date] = team_2
            self.team_to_week[team_2] = team_1_date

        if team_2_date is None:
            self.unused_teams.remove(team_2)
            self.unused_teams.add(team_1)
        else:
            self.week_to_team[team_2_date] = team_1
            self.team_to_week[team_1] = team_2_date

    def change_to_random_neighbour(self):
        team_1 = random.choice(self.tournament.teams)
        if team_1 in self.unused_teams:
            team_2 = random.choice(list(self.team_to_week.keys()))
        else:
            team_2 = random.choice(self.tournament.teams)
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

    # def summarize_strategy(self):
    #     for date in self.tournament.match_weeks:



class SimulatedAnnealing:
    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        self.strategy = Strategy.from_random(tournament)
        self.score = self.strategy.score()

    @staticmethod
    def get_min_improvement(epoch):
        return min(0, epoch * 0.001 - 2)

    def iterate(self, epoch):
        neighbour = deepcopy(self.strategy)
        neighbour.change_to_random_neighbour()
        neighbour_score = neighbour.score()
        if neighbour_score - self.score > self.get_min_improvement(epoch):
            self.strategy = neighbour
            self.score = neighbour_score
        epoch += 1

    def run(self, n_epochs: int, callback: Callable):
        for epoch in range(n_epochs):
            self.iterate(epoch)
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
