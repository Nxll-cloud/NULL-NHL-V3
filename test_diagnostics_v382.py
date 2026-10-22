import unittest
import pandas as pd
from diagnostics_v382 import diagnostic_summary
from storyline_v38 import historical_facts

class Tests(unittest.TestCase):
    def test_near_milestone_not_flag(self):
        log=[{'gameDate':f'2026-10-{i:02}','gameId':i,'goals':1,'shots':2,'opponentAbbrev':'CAR'} for i in range(1,9)]
        result=historical_facts({'Player ID':123},'2026-10-22','WPG',log)
        self.assertEqual(result['V3.8 flag count'],0)
        self.assertEqual(result['Milestone distance'],2)
        self.assertIn('2 goals',result['Milestone watch (not a flag)'])
    def test_dict_opponent(self):
        log=[{'gameDate':'2026-10-20','gameId':1,'goals':1,'shots':2,'opponentAbbrev':{'default':'WPG'}}]
        self.assertEqual(historical_facts({'Player ID':123},'2026-10-22','WPG',log)['Vs opponent GP'],1)
    def test_birthday(self):
        result=diagnostic_summary(pd.DataFrame([{'Player ID':'1'}]),pd.DataFrame([{'Birth date':'1998-10-22'},{'Birth date':'not-date'}]),None,'2026-10-22')
        self.assertEqual(result['Birthdays on slate date'],1)
        self.assertEqual(result['Profiles with invalid birthdays'],1)
if __name__=='__main__': unittest.main()
