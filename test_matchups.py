import unittest
from matchups import prior_team_games, attach_matchups

class MatchupTests(unittest.TestCase):
    def test_filters_future_and_unfinished(self):
        def game(gid, day, state):
            return {"id": gid, "gameDate": day, "gameState": state,
                    "awayTeam": {"abbrev": "ANA"}, "homeTeam": {"abbrev": "BOS"}}
        sched = {"games": [game(1,"2026-10-20","OFF"),
                           game(2,"2026-10-22","OFF"),
                           game(3,"2026-10-19","FUT")]}
        self.assertEqual(prior_team_games(sched, "ANA", "2026-10-22"), [1])
    def test_opponent_mapping(self):
        rows = [{"Player":"X","Team":"ANA"}]
        games = [{"Home":"ANA","Away":"BOS"}]
        data = {"BOS":{"Defense GA/G L5":2.5,"Games verified":5}}
        result = attach_matchups(rows, games, data)[0]
        self.assertEqual(result["Opponent"], "BOS")
        self.assertEqual(result["Opp GA/G L5"], 2.5)
        self.assertEqual(result["Starting goalie"], "Unconfirmed")

if __name__ == "__main__":
    unittest.main()
