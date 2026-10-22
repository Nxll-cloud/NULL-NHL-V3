import unittest
import pandas as pd
from storylines_v36 import build_storylines, combined_table

class TestV36(unittest.TestCase):
    def setUp(self):
        self.ranked=pd.DataFrame([{'Player ID':123,'Player':'Test Skater','Team':'BOS','Goals/G L5':0.8,'Prior GP':6,'Shots/G L5':3,'Baseline Form Index':80}])
        self.meta=pd.DataFrame([{'Player ID':'123','Birth date':'1990-10-22','Source URL':'https://api-web.nhle.com/v1/player/123/landing'}])
    def test_birthday_and_form(self):
        out=build_storylines(self.ranked,self.meta,'2026-10-22')
        self.assertEqual(out.iloc[0]['Storyline count'],2)
    def test_no_future_birthday(self):
        out=build_storylines(self.ranked,self.meta,'2026-10-21')
        self.assertEqual(out.iloc[0]['Storyline count'],1)
    def test_combined_keeps_statistical_index(self):
        s=pd.DataFrame([{'Player ID':'123','Pattern overlaps':2,'Matching patterns':'Test','Name Pythagorean':12,'Name ordinal':24}])
        c=combined_table(self.ranked,s,build_storylines(self.ranked,self.meta,'2026-10-22'))
        self.assertEqual(c.iloc[0]['Baseline Form Index'],80)
        self.assertEqual(c.iloc[0]['Exploratory overlap count'],4)
        self.assertEqual(c.iloc[0]['Name ordinal reduced'],6)
if __name__=='__main__': unittest.main()
