from strategy import Tournament, SimulatedAnnealing


def main():
    tournament = Tournament.from_apis()

    scores = []

    def callback(simulated_annealing: SimulatedAnnealing):
        scores.append(simulated_annealing.score)

    s = SimulatedAnnealing(tournament, locked_teams=[])

    s.run(100, callback)

    return s.strategy, scores


if __name__ == '__main__':
    main()
