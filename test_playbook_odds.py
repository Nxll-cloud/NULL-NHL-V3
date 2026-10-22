import pandas as pd
import pytest
from playbook_odds import compare_odds, implied_probability

def test_gap():
    x=pd.DataFrame([dict(player='A',team='MIN',market='anytime_goal',selection='yes',sportsbook=b,american_odds=o,updated_at='2026-10-22T14:00:00Z',event_id='123',line='') for b,o in [('Book1',180),('Book2',250)]])
    raw,summary=compare_odds(x)
    assert summary.iloc[0]['best_sportsbook']=='Book2'
    assert summary.iloc[0]['american_points_gap']==70
    assert round(summary.iloc[0]['decimal_price_improvement_pct'],2)==25.0
    assert len(raw)==2

def test_no_cross_market_or_line():
    x=pd.DataFrame([dict(player='A',team='MIN',market='shots',selection='over',sportsbook=b,american_odds=o,updated_at='2026-10-22T14:00:00Z',event_id='123',line=line) for b,o,line in [('Book1',180,'2.5'),('Book2',250,'3.5')]])
    assert compare_odds(x)[1].empty

def test_invalid():
    with pytest.raises(ValueError): compare_odds(pd.DataFrame({'player':['A']}))
    assert implied_probability(100)==0.5
