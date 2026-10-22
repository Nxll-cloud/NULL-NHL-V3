import unittest
import pandas as pd
from storyline_v37 import select_storyline_watch

class TestStorylineV37(unittest.TestCase):
    def test_verified_flags_outrank_form(self):
        rows = pd.DataFrame([
            {'Player':'A','Team':'AAA','Storyline count':0,'V3.2 Adjusted Index':150,'Baseline Form Index':150,'Shots/G L5':3},
            {'Player':'B','Team':'BBB','Storyline count':2,'V3.2 Adjusted Index':60,'Baseline Form Index':60,'Shots/G L5':2.5},
            {'Player':'C','Team':'CCC','Storyline count':1,'V3.2 Adjusted Index':90,'Baseline Form Index':90,'Shots/G L5':3},
        ])
        top, sleepers, featured = select_storyline_watch(rows)
        self.assertEqual(featured['Player'],'B')
        self.assertEqual(list(top['Player']), ['B','C'])
        self.assertEqual(len(sleepers),0)
    def test_sleeper_filter(self):
        rows = pd.DataFrame([{'Player':'B','Team':'BBB','Storyline count':1,'V3.2 Adjusted Index':60,'Baseline Form Index':60,'Shots/G L5':2.5,'Statistical rank':25}])
        _, sleepers, _ = select_storyline_watch(rows)
        self.assertEqual(len(sleepers),1)
    def test_empty(self):
        top, sleepers, featured = select_storyline_watch(pd.DataFrame())
        self.assertIsNone(featured)
        self.assertTrue(top.empty)
    def test_no_supported_storyline(self):
        top, _, featured = select_storyline_watch(pd.DataFrame([{'Player':'A','Storyline count':0}]))
        self.assertTrue(top.empty)
        self.assertIsNone(featured)
if __name__ == '__main__': unittest.main()
