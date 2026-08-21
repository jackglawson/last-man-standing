import hashlib
import json
import os
import re
import time
from functools import lru_cache
from io import StringIO
from pathlib import Path
from xml.dom.domreg import well_known_implementations

import numpy as np
import requests
import pandas as pd
import datetime as dt
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from settings import ELO_TEAM_MAPPING, SEASON_START_DATE, SEASON_YEAR

load_dotenv()  # no-op if no .env file present (e.g. in CI)

CACHE_ROOT = Path(__file__).resolve().parent / ".cache"


def iso_time_to_int(time: str):
    return int(time.split("T")[0].replace("-", ""))


def int_to_date(date_id: int):
    return dt.datetime.strptime(str(date_id), "%Y%m%d").date()


class _CachedResponse:
    """Minimal requests.Response look-alike, reconstructed from a cached JSON
    payload. Only exposes what data.py's callers actually use: .status_code,
    .headers, .text and .json(). Extend this if a caller starts needing more.
    """

    def __init__(self, payload: dict):
        self.status_code = payload["status_code"]
        self.headers = requests.structures.CaseInsensitiveDict(payload["headers"])
        self.text = payload["text"]

    def json(self):
        return json.loads(self.text)


def _cache_key(hashable_args: tuple, hashable_kwargs: dict) -> str:
    # hashable_args/hashable_kwargs have already been through make_hashable,
    # so dict-derived values are tuples sorted by key -> repr() below is
    # deterministic across process restarts.
    canonical = repr((hashable_args, tuple(sorted(hashable_kwargs.items()))))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_cache_entry(cache_file: Path, ttl_seconds: float):
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text())
    except (json.JSONDecodeError, OSError):
        # Corrupt/partial file (e.g. an interrupted write) - treat as a miss.
        return None
    if time.time() - payload["timestamp"] > ttl_seconds:
        return None
    return payload


def _write_cache_entry(cache_file: Path, response) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "text": response.text,
    }
    tmp_file = cache_file.with_suffix(".json.tmp")
    tmp_file.write_text(json.dumps(payload))
    tmp_file.replace(cache_file)  # atomic on POSIX - avoids partial-file reads


def mutable_lru_cache(func=None, *, use_disk: bool = True, ttl_seconds: float = 3600):
    """In-memory LRU cache (as before) for functions with unhashable (dict/list/
    set) arguments, optionally backed by a per-key JSON file on disk so results
    survive process/kernel restarts. A disk entry is only used if it's younger
    than `ttl_seconds`.

    Usable bare (`@mutable_lru_cache`) or parameterized
    (`@mutable_lru_cache(use_disk=True, ttl_seconds=3600)`).
    """

    def decorator(f):
        cache_dir = CACHE_ROOT / f.__qualname__

        def disk_dispatch(*hashable_args, **hashable_kwargs):
            if not use_disk:
                return f(*hashable_args, **hashable_kwargs)

            cache_file = cache_dir / f"{_cache_key(hashable_args, hashable_kwargs)}.json"
            cached = _read_cache_entry(cache_file, ttl_seconds)
            if cached is not None:
                return _CachedResponse(cached)

            result = f(*hashable_args, **hashable_kwargs)
            _write_cache_entry(cache_file, result)
            return result

        in_memory_cache = lru_cache(maxsize=128)(disk_dispatch)

        def make_hashable(arg):
            """Helper function to convert mutable arguments to hashable ones."""
            if isinstance(arg, dict):
                return tuple(sorted((k, make_hashable(v)) for k, v in arg.items()))
            elif isinstance(arg, list):
                return tuple(make_hashable(e) for e in arg)
            elif isinstance(arg, set):
                return frozenset(make_hashable(e) for e in arg)
            elif isinstance(arg, tuple):
                return tuple(make_hashable(e) for e in arg)
            else:
                # Return the object itself if it's already hashable
                return arg

        def wrapper(*args, **kwargs):
            # Convert all arguments to hashable types
            hashable_args = tuple(make_hashable(arg) for arg in args)
            hashable_kwargs = {k: make_hashable(v) for k, v in kwargs.items()}
            return in_memory_cache(*hashable_args, **hashable_kwargs)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


@mutable_lru_cache(use_disk=True, ttl_seconds=36000)
def get_url(url, params=None, headers=None):
    # mutable_lru_cache's wrapper converts dict args to tuples of sorted
    # pairs to make them hashable for the cache key - requests.get tolerates
    # that for `params` but not `headers`, which needs a real dict/mapping.
    if isinstance(headers, tuple):
        headers = dict(headers)

    print(f"Getting from {url}")
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()

    print(f"Got response 200 from {url}, with headers:")
    print(response.headers)

    return response


def get_upcoming_match_odds_for_league(league: str):
    url = f"https://api.the-odds-api.com/v4/sports/{league}/odds/"

    params = {
        "api_key": os.environ["ODDS_API_KEY"],
        "regions": "uk",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": "betfair_ex_uk",
    }

    response = get_url(url, params)

    raw_odds_data = response.json()

    odds_data = []
    for raw_odds_datum in raw_odds_data:
        if not raw_odds_datum["bookmakers"]:
            print(
                f"No odds available for {raw_odds_datum['home_team']} vs {raw_odds_datum['away_team']} on {raw_odds_datum['commence_time']}"
            )
            continue

        h2h_data = [
            x for x in raw_odds_datum["bookmakers"][0]["markets"] if x["key"] == "h2h"
        ][0]["outcomes"]
        h2h_outcomes = {x["name"]: x["price"] for x in h2h_data}

        odds_home = h2h_outcomes[raw_odds_datum["home_team"]]
        odds_away = h2h_outcomes[raw_odds_datum["away_team"]]
        odds_draw = h2h_outcomes["Draw"]

        p_total = sum([1 / odds_home, 1 / odds_away, 1 / odds_draw])

        p_home = (1 / odds_home) / p_total
        p_away = (1 / odds_away) / p_total

        odds_data.append(
            {
                "date_id": iso_time_to_int(raw_odds_datum["commence_time"]),
                "home_team": raw_odds_datum["home_team"],
                "away_team": raw_odds_datum["away_team"],
                "p_home": p_home,
                "p_away": p_away,
            }
        )

    return odds_data


def get_upcoming_match_odds():
    return sum(
        [
            get_upcoming_match_odds_for_league("soccer_epl"),
            get_upcoming_match_odds_for_league("soccer_efl_champ"),
        ],
        [],
    )


def _parse_elo_html(html: str, country: str) -> dict:
    """clubelo.com's ranking page embeds one <table class="ast"> per country,
    each holding <tr><td class="l">FLAG RANK CLUB</td><td class="r">ELO</td></tr>
    rows (plus non-data "Level N (n teams)" separator rows with no <img>, which
    are skipped since they don't match the row shape below).
    """
    soup = BeautifulSoup(html, "html.parser")

    elos = {}
    for table in soup.find_all("table", class_="ast"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) != 2:
                continue

            left, right = tds
            img = left.find("img")
            if img is None or img.get("alt") != country:
                continue

            club_span = left.find("span", class_="Ast")
            if club_span is None:
                continue

            # Provisional ratings are suffixed with a letter (e.g. "1162p").
            elo_text = re.sub(r"\D", "", right.get_text(strip=True))
            elos[club_span.get_text(strip=True)] = int(elo_text)

    return elos


def get_elos():
    response = get_url("https://clubelo.com/ENG")
    elos = _parse_elo_html(response.text, "ENG")

    def to_team(team: str):
        return ELO_TEAM_MAPPING.get(team, team)

    return {to_team(club): elo for club, elo in elos.items()}


def get_matches_for_league(league):

    url = f"https://api.football-data.org/v4/competitions/{league}/matches"

    headers = {"X-Auth-Token": os.environ["FOOTBALL_DATA_TOKEN"]}

    params = {
        "season": SEASON_YEAR,
    }

    response = get_url(url, params, headers)

    data = response.json()

    def to_team(team: str):
        return team.replace(" FC", "")

    matches = [
        {
            "match_day_orig": match["matchday"],
            "date_id": iso_time_to_int(match["utcDate"]),
            "date": int_to_date(iso_time_to_int(match["utcDate"])),
            "status": match["status"],
            "home_team": to_team(match["homeTeam"]["name"]),
            "away_team": to_team(match["awayTeam"]["name"]),
            "score_home": match["score"]["fullTime"]["home"],
            "score_away": match["score"]["fullTime"]["away"],
            "league": league,
        }
        for match in data["matches"]
    ]

    matches = [match for match in matches if match['date_id'] >= SEASON_START_DATE]

    matches.sort(key=lambda x: x["date_id"])


    for match in matches:

        day_of_week = pd.to_datetime(
            str(match['date_id']),
            format="%Y%m%d"
        ).day_name()

        week_number = (match['date'] - int_to_date(SEASON_START_DATE)).days // 7 + 1

        match['day_of_week'] = day_of_week
        match['week_number'] = week_number
        match['is_midweek'] = match['day_of_week'] in ['Tuesday', 'Wednesday', 'Thursday']



    match_count_by_team = {}

    # for match in matches:
    #     home_team = match["home_team"]
    #     away_team = match["away_team"]
    #
    #     if home_team not in match_count_by_team:
    #         match_count_by_team[home_team] = 0
    #
    #     if away_team not in match_count_by_team:
    #         match_count_by_team[away_team] = 0
    #
    #     match_count_by_team[home_team] += 1
    #     match_count_by_team[away_team] += 1
    #
    #     # Assign the week number to the match
    #     if match_count_by_team[home_team] != match_count_by_team[away_team]:
    #         print("WARNING: home week number does not match away week number!")
    #         print("home week number:", match_count_by_team[home_team])
    #         print("away week number:", match_count_by_team[away_team])
    #         print(match)
    #
    #     # This is actually the exact same thing as matchDay
    #     match["week_number"] = match_count_by_team[home_team]

    # def hack_the_matches(a_matches):
    #     """Sadly the dates make no sense, and I don't know the exact rules of the game."""
    #     a_matches = [m for m in a_matches if m["match_day"] <= 38]
    #     return a_matches
    #
    # matches = hack_the_matches(matches)

    return matches


def get_matches():
    matches = sum(
        [
            get_matches_for_league("PL"),
            get_matches_for_league("ELC"),
        ],
        [],
    )

    matches.sort(key=lambda x: x["date_id"])

    matches = add_inferred_match_day(matches)
    matches = add_is_valid_match(matches)

    return matches


def get_teams_df(matches: list) -> pd.DataFrame:
    team_to_league = {}
    for match in matches:
        team_to_league[match["home_team"]] = match["league"]
        team_to_league[match["away_team"]] = match["league"]

    elos = get_elos()

    def get_elo_for_team(team: str):
        if team in elos:
            return elos[team]
        print(f"WARNING: Could not find elo for {team}. Using average elo instead")
        return np.mean(list(elos.values()))

    return pd.DataFrame(
        [
            {"team": team, "league": league, "elo": get_elo_for_team(team)}
            for team, league in team_to_league.items()
        ]
    )


def add_inferred_match_day(matches: list):
    week_number_to_match_day = {}

    for match in matches:
        if match['league'] != 'PL':
            continue

        key = (match['week_number'], match['is_midweek'])

        if key in week_number_to_match_day:
            assert week_number_to_match_day[key] == match['match_day_orig']
        else:
            week_number_to_match_day[key] = match['match_day_orig']


    for match in matches:
        if match['league'] == 'PL':
            match['match_day'] = match['match_day_orig']
        else:
            key = (match['week_number'], match['is_midweek'])
            match['match_day'] = week_number_to_match_day.get(key, -1)

    return matches


# def add_inferred_match_day(matches: list):
#
#     def week_is_valid(matches_for_week):
#         if len(matches_for_week) == 0:
#             return False
#         if len([match for match in matches_for_week if match['league'] == 'PL']) == 0:
#             return False
#         if len([match for match in matches_for_week if match['league'] == 'ELC']) == 0:
#             return False
#         return True
#
#     match_day = 1
#     week_number_to_match_day = {}
#
#     for week_number in sorted(set([match['week_number'] for match in matches])):
#         matches_for_week = [match for match in matches if match['week_number'] == week_number]
#         if week_is_valid(matches_for_week):
#             week_number_to_match_day[week_number] = match_day
#             match_day += 1
#         else:
#             week_number_to_match_day[week_number] = -1
#
#     for match in matches:
#         match['match_day'] = week_number_to_match_day.get(match['week_number'], -1)
#
#     return matches


def add_is_valid_match(matches: list):
    def is_it(a_match):
        if a_match['league'] == 'PL':
            return True
        if (a_match['league'] == 'ELC') & a_match['is_midweek']:
            return False
        return a_match['match_day'] != -1

    for match in matches:
        match['is_valid_match'] = is_it(match)

    return matches



