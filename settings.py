LOCKED_TEAMS = ["Queens Park Rangers"]

RANDOM_SEED = 0

SEASON_YEAR = "2026"

SEASON_START_DATE = 20260821  # Must be a Friday

ELO_TEAM_MAPPING = {
    "Birmingham": "Birmingham City",
    "Blackburn": "Blackburn Rovers",
    "Bolton": "Bolton Wanderers",
    "Bournemouth": "AFC Bournemouth",
    "Brighton": "Brighton & Hove Albion",
    "Cardiff": "Cardiff City",
    "Charlton": "Charlton Athletic",
    "Coventry": "Coventry City",
    "Derby": "Derby County",
    "Forest": "Nottingham Forest",
    "Hull": "Hull City AFC",
    "Ipswich": "Ipswich Town",
    "Leeds": "Leeds United",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Newcastle": "Newcastle United",
    "Norwich": "Norwich City",
    "Preston": "Preston North End",
    "QPR": "Queens Park Rangers",
    "Stoke": "Stoke City",
    "Sunderland": "Sunderland AFC",
    "Swansea": "Swansea City AFC",
    "Tottenham": "Tottenham Hotspur",
    "West Brom": "West Bromwich Albion",
    "West Ham": "West Ham United",
    "Wolves": "Wolverhampton Wanderers",
    "Wrexham": "Wrexham AFC",
}

N_EPOCHS = 10000

MIN_IMPROVEMENT_SCHEDULE = {500: -0.5, 2000: -0.1, 4000: -0.05, 6000: -0.02, 10000: 0}

# Per-week decay applied to score() so weeks further in the future count for
# less: the pool may already be decided by then, and the probability
# estimates for far-out matches (Elo fallback rather than market odds) are
# less trustworthy anyway. weight(t) = SCORE_DECAY_GAMMA ** t, t = rank among
# not-yet-locked weeks.
SCORE_DECAY_GAMMA = 0.95
