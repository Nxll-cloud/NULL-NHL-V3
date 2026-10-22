import unittest
from nhl_data import summarize_games

class ValidationTests(unittest.TestCase):
    def test_cutoff_and_duplicates(self):
        games = [
            {"gameId": 1, "gameDate": "2026-10-20", "goals": 2, "shots": 5},
            {"gameId": 1, "gameDate": "2026-10-20", "goals": 2, "shots": 5},
            {"gameId": 2, "gameDate": "2026-10-22", "goals": 1, "shots": 3},
            {"gameId": 3, "gameDate": "2026-10-19", "goals": 3, "shots": 1},
            {"gameId": 4, "gameDate": "2026-10-18", "goals": 0, "shots": 2},
        ]
        result = summarize_games(games, "2026-10-22")
        self.assertEqual(result["Season"], {"GP": 2, "G": 2, "SOG": 7})
        self.assertEqual(result["Quality"]["duplicate_rows"], 1)
        self.assertEqual(result["Quality"]["invalid_rows"], 1)
        self.assertEqual(result["Quality"]["excluded_on_or_after_date"], 1)

if __name__ == "__main__":
    unittest.main()
