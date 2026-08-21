import time

from strategy import Tournament, SimulatedAnnealing


def main():
    tournament = Tournament.from_apis()

    scores = []
    min_improvements = []

    def callback(simulated_annealing: SimulatedAnnealing):
        epoch = len(scores)
        scores.append(simulated_annealing.score)
        min_improvements.append(simulated_annealing.get_min_improvement(epoch))

    s = SimulatedAnnealing(tournament, locked_teams=[])

    start = time.perf_counter()
    s.run(100, callback)
    duration_seconds = time.perf_counter() - start

    return s.strategy, scores, min_improvements, duration_seconds


if __name__ == '__main__':
    main()
