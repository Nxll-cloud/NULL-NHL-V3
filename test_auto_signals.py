import unittest
from unittest.mock import patch
from auto_signals import arena_lookup, profile_metadata
class TestAutoSignals(unittest.TestCase):
    def test_arena(self):
        self.assertEqual(arena_lookup([{'Home':'NYR','Away':'BOS','Venue':'Madison Square Garden'}])['BOS'],'Madison Square Garden')
    @patch('auto_signals.fetch_json')
    def test_profile(self, mock):
        mock.return_value={'playerId':123,'birthDate':'1995-01-01','sweaterNumber':9}
        item=profile_metadata({'Player ID':123,'Team':'BOS'},'2026-10-22',{'BOS':'TD Garden'})
        self.assertEqual(item['Jersey'],'9')
        self.assertEqual(item['Arena'],'TD Garden')
    @patch('auto_signals.fetch_json')
    def test_wrong_id(self,mock):
        mock.return_value={'playerId':456}
        with self.assertRaises(ValueError): profile_metadata({'Player ID':123},'2026-10-22')
