import unittest
from datetime import datetime, timezone
from backtesting import make_snapshot, score_snapshot, top_k_metrics

class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.games = [{"Game ID": 123, "Home": "A", "Away": "B",
                       "Start (UTC)": "2026-10-22T23:00:00Z", "Status": "FUT"}]
        self.rows = [{"Player ID": 99, "Player": "Test Player", "Team": "A",
                      "Baseline Form Index": 90, "V3.2 Adjusted Index": 95,
                      "Defense Adjustment": 5.5, "Adjustment status": "Applied"}]
        self.capture = datetime(2026, 10, 22, 18, tzinfo=timezone.utc)

    def test_pregame_snapshot(self):
        df = make_snapshot(self.rows, self.games, "2026-10-22", self.capture)
        self.assertEqual(int(df.iloc[0]["Player ID"]), 99)

    def test_late_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            make_snapshot(self.rows, self.games, "2026-10-22",
                          datetime(2026, 10, 22, 23, tzinfo=timezone.utc))

    def test_final_result(self):
        df = make_snapshot(self.rows, self.games, "2026-10-22", self.capture)
        def fetch(_):
            return {"gameState": "OFF", "gameDate": "2026-10-22",
                    "startTimeUTC": "2026-10-22T23:00:00Z",
                    "playerByGameStats": {
                        "homeTeam": {"forwards": [{"playerId": 99, "goals": 1}], "defense": []},
                        "awayTeam": {"forwards": [], "defense": []}}}
        scored, failures = score_snapshot(df, fetch)
        self.assertFalse(failures)
        self.assertEqual(scored.iloc[0]["Scored"], 1)
        self.assertEqual(top_k_metrics(scored, (1,)).iloc[0]["Hit rate"], 1)

    def test_unverified_player_not_counted_as_zero(self):
        df = make_snapshot(self.rows, self.games, "2026-10-22", self.capture)
        def fetch(_):
            return {"gameState": "OFF", "gameDate": "2026-10-22",
                    "startTimeUTC": "2026-10-22T23:00:00Z",
                    "playerByGameStats": {"homeTeam": {"forwards": [], "defense": []},
                                          "awayTeam": {"forwards": [], "defense": []}}}
        scored, _ = score_snapshot(df, fetch)
        self.assertIsNone(scored.iloc[0]["Scored"])
        self.assertEqual(top_k_metrics(scored, (1,)).iloc[0]["Status"], "Incomplete coverage")

if __name__ == "__main__":
    unittest.main()
