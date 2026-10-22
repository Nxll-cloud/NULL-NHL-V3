import unittest
import pandas as pd
from history_v386 import prior_seasons, summarize_player, missing_player_ids, merge_multi_history

class Tests(unittest.TestCase):
 def test_seasons(self):
  self.assertEqual(prior_seasons('2026-10-22'),['20252026','20242025','20232024'])
  self.assertEqual(prior_seasons('2026-02-01',2),['20242025','20232024'])
 def test_goals(self):
  row={'Player ID':123,'Player':'Test','Team':'BOS'}
  logs={'20252026':[{'gameDate':'2026-01-01','gameId':1,'goals':2,'shots':4,'opponentAbbrev':'NYR'}, {'gameDate':'2026-02-01','gameId':2,'goals':1,'shots':3,'opponentAbbrev':{'default':'NYR'}}]}
  x=summarize_player(row,'2026-10-22','NYR',logs,['20252026'])
  self.assertEqual(x['Historical opponent goals'],3)
  self.assertEqual(x['Historical opponent GP'],2)
  self.assertEqual(x['Historical storyline flag'],'')
 def test_missing(self):
  self.assertEqual(missing_player_ids([{'Player ID':1,'Player':'One'},{'Player ID':2,'Player':'Two'}],[{'Player ID':1}]),[{'Player ID':'2','Player':'Two'}])
 def test_partial(self):
  x=summarize_player({'Player ID':1},'2026-10-22','NYR',{},['20252026'])
  self.assertEqual(x['Historical data status'],'Partial / unavailable')
 def test_merge(self):
  base=pd.DataFrame([{'Player ID':1,'Storyline count':1,'Verified data flags':'Form','Evidence URLs':''}])
  h=pd.DataFrame([{'Player ID':'1','Historical storyline flag':'Opponent trend','Historical source URLs':'https://example.com'}])
  x=merge_multi_history(base,h)
  self.assertEqual(x.iloc[0]['Storyline count'],2)

if __name__=='__main__': unittest.main()
