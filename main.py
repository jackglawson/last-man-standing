import random
import time

from settings import N_EPOCHS, LOCKED_TEAMS, RANDOM_SEED
from strategy import Tournament, SimulatedAnnealing


def main():
    random.seed(RANDOM_SEED)

    tournament = Tournament.from_apis()

    scores = []
    min_improvements = []

    def callback(simulated_annealing: SimulatedAnnealing):
        epoch = len(scores)
        scores.append(simulated_annealing.score)
        min_improvements.append(simulated_annealing.get_min_improvement(epoch))

    s = SimulatedAnnealing(tournament, locked_teams=LOCKED_TEAMS)

    start = time.perf_counter()
    s.run(N_EPOCHS, callback)
    duration_seconds = time.perf_counter() - start

    return s.strategy, scores, min_improvements, duration_seconds


if __name__ == '__main__':
    main()
