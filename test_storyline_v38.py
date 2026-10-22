import unittest
import pandas as pd
from storyline_v38 import opponent_lookup, historical_facts, merge_history

class TestStorylineV38(unittest.TestCase):
    def test_opponent_lookup(self):
        self.assertEqual(opponent_lookup([{'Away':'MIN','Home':'WPG'}]), {'MIN':'WPG','WPG':'MIN'})
    def test_no_future_leak_and_opponent(self):
        log=[{'gameDate':'2026-10-20','gameId':1,'goals':1,'shots':3,'opponentAbbrev':'WPG'},
             {'gameDate':'2026-10-21','gameId':2,'goals':1,'shots':4,'opponentAbbrev':'WPG'},
             {'gameDate':'2026-10-22','gameId':3,'goals':2,'shots':4,'opponentAbbrev':'WPG'}]
        row=historical_facts({'Player ID':123},'2026-10-22','WPG',log)
        self.assertEqual(row['Vs opponent goals'],2)
        self.assertEqual(row['V3.8 flag count'],1)
        self.assertEqual(row['Season goals (log)'],2)
    def test_no_single_game_opponent_flag(self):
        log=[{'gameDate':'2026-10-20','gameId':1,'goals':3,'shots':5,'opponentAbbrev':'WPG'}]
        self.assertEqual(historical_facts({'Player ID':123},'2026-10-22','WPG',log)['V3.8 flag count'],0)
    def test_milestone(self):
        log=[{'gameDate':f'2026-10-{i:02}','gameId':i,'goals':1,'shots':3,'opponentAbbrev':'CAR'} for i in range(1,10)]
        row=historical_facts({'Player ID':123},'2026-10-22','WPG',log)
        self.assertIn('1 goal from 10',row['V3.8 flags'])
    def test_merge(self):
        base=pd.DataFrame([{'Player ID':'123','Storyline count':1,'Verified data flags':'Recent form','Evidence URLs':'source'}])
        hist=pd.DataFrame([{'Player ID':'123','V3.8 flag count':2,'V3.8 flags':'Opponent history','V3.8 source':'nhl','V3.8 status':'Verified'}])
        out=merge_history(base,hist)
        self.assertEqual(out.iloc[0]['Storyline count'],3)
        self.assertIn('Opponent history',out.iloc[0]['Verified data flags'])
    def test_empty_history(self):
        out=merge_history(pd.DataFrame([{'Player ID':'123','Storyline count':0}]),pd.DataFrame())
        self.assertEqual(out.iloc[0]['V3.8 status'],'Not fetched')
if __name__=='__main__': unittest.main()
