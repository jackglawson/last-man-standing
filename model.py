def elos_to_win_lose_probabilites(elo_home, elo_away):
    p_home = 1 / (1 + 10 ** ((elo_away - elo_home) / 400))
    p_away = 1 - p_home
    return p_home, p_away


def elos_to_modelled_probabilities(elo_home, elo_away):
    home_advantage = 65
    p_unnorm_home, p_unnorm_away = elos_to_win_lose_probabilites(
        elo_home + home_advantage, elo_away
    )
    p_unnorm_draw = 0.7 * (p_unnorm_home * p_unnorm_away) ** 0.5

    total_p = p_unnorm_home + p_unnorm_away + p_unnorm_draw
    p_home = p_unnorm_home / total_p
    p_away = p_unnorm_away / total_p

    return p_home, p_away
