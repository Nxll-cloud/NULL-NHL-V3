import unittest
from matchups import attach_matchups, league_defense_baseline, prior_team_games

def defense(team, ga, sa, gp=10, errors=0):
    return {"Opponent": team, "Defense GA/G L5": ga, "Defense GA/G L10": ga,
            "Defense SA/G L5": sa, "Defense SA/G L10": sa,
            "Games verified": gp, "Boxscore errors": errors}

class MatchupTests(unittest.TestCase):
    def setUp(self):
        self.d = {"B": defense("B", 5, 40), "C": defense("C", 2, 20),
                  "D": defense("D", 3, 30), "E": defense("E", 3, 30)}
        self.games = [{"Home":"A", "Away":"B"}]
        self.ranked = [{"Player":"One","Team":"A","Form Index":100,"Shots/G L5":3}]

    def test_adjustment_is_capped(self):
        row = attach_matchups(self.ranked, self.games, self.d)[0]
        self.assertLessEqual(row["Defense Adjustment"], 15)
        self.assertGreaterEqual(row["Defense Adjustment"], -15)
        self.assertGreater(row["V3.2 Adjusted Index"], row["Baseline Form Index"])

    def test_missing_opponent_neutral(self):
        row = attach_matchups(self.ranked, [], self.d)[0]
        self.assertEqual(row["Defense Adjustment"], 0)
        self.assertEqual(row["Adjustment status"], "Insufficient opponent coverage")

    def test_partial_boxscores_neutral(self):
        self.d["B"]["Boxscore errors"] = 1
        row = attach_matchups(self.ranked, self.games, self.d)[0]
        self.assertEqual(row["Defense Adjustment"], 0)

    def test_disabled_neutral(self):
        row = attach_matchups(self.ranked, self.games, self.d, adjust=False)[0]
        self.assertEqual(row["V3.2 Adjusted Index"], 100)

    def test_no_future_games(self):
        schedule = {"games":[
            {"gameDate":"2026-10-21","id":1,"gameState":"OFF",
             "awayTeam":{"abbrev":"A"},"homeTeam":{"abbrev":"B"}},
            {"gameDate":"2026-10-22","id":2,"gameState":"OFF",
             "awayTeam":{"abbrev":"A"},"homeTeam":{"abbrev":"C"}}]}
        self.assertEqual(prior_team_games(schedule,"A","2026-10-22"),[1])

if __name__ == "__main__":
    unittest.main()
