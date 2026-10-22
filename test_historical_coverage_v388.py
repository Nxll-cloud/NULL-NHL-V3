import pandas as pd
from historical_coverage_v388 import historical_coverage

def test_coverage_mixed():
    result=historical_coverage(pd.DataFrame({'Historical data status':['Complete','Partial / unavailable','Not fetched',None,'Complete']}))
    assert (result['complete'],result['partial'],result['not_fetched'])==(2,1,2)
    assert result['percent']==40

def test_coverage_missing_column():
    assert historical_coverage(pd.DataFrame({'Player':[1,2]}))['not_fetched']==2

def test_empty():
    assert historical_coverage(pd.DataFrame())['fraction']==0
