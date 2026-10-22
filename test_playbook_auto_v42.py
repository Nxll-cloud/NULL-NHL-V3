from datetime import datetime, timezone, timedelta
import pandas as pd
from playbook_auto_v42 import needs_refresh, coverage_summary, auto_full_slate

def test_refresh_first_and_interval():
    now=datetime(2026,10,22,14,tzinfo=timezone.utc)
    assert needs_refresh({}, '2026-10-22', now)
    state={'np_v42_day':'2026-10-22','np_v42_last_run':now-timedelta(minutes=14)}
    assert not needs_refresh(state,'2026-10-22',now)
    assert needs_refresh(state,'2026-10-22',now+timedelta(minutes=1))
    assert needs_refresh(state,'2026-10-23',now)

def test_coverage_partial_and_missing():
    ranked=pd.DataFrame({'Player ID':[1,2,3]})
    hist=pd.DataFrame({'Player ID':['1','2'], 'Historical data status':['Complete','Partial / unavailable']})
    assert coverage_summary(ranked,hist)==(1,1,1)

def test_auto_full_slate_calls_three_years():
    captured={}
    def history(rows,games,day,max_players,years):
        captured.update({'count':max_players,'years':years,'day':day})
        return pd.DataFrame({'Player ID':[1], 'Historical data status':['Complete']}),[]
    result=auto_full_slate('2026-10-22',lambda d:[{'Home':'AAA','Away':'BBB'}],
        lambda t,d:([{'Player ID':1,'Team':t}],[]),lambda t,d:{'Opponent':t},history,
        lambda rows,min_games:rows,lambda rows,games,defense,adjust:rows,
        lambda rows:rows)
    assert len(result['ranked'])==2
    assert captured=={'count':500,'years':3,'day':'2026-10-22'}
