import unittest
import pandas as pd
from signals import universal_day, pythagorean, ordinal, build_signals

class SignalTests(unittest.TestCase):
    def test_day(self):
        self.assertEqual(universal_day('2026-10-22'), 6)
    def test_name(self):
        self.assertEqual(pythagorean('ABC'), 6)
        self.assertEqual(ordinal('ABC'), 6)
    def test_missing_metadata_is_not_invented(self):
        data = build_signals(pd.DataFrame([{'Player': 'ABC', 'Player ID': 123, 'Team': 'MIN'}]), '2026-10-22')
        self.assertIsNone(data.iloc[0]['Life path'])
        self.assertIsNone(data.iloc[0]['Verified storyline'])
    def test_unsourced_storyline_excluded(self):
        players = pd.DataFrame([{'Player': 'ABC', 'Player ID': 123, 'Team': 'MIN'}])
        meta = pd.DataFrame([{'Player ID': '123', 'Verified storyline': 'Claim'}])
        data = build_signals(players, '2026-10-22', meta)
        self.assertIsNone(data.iloc[0]['Verified storyline'])
