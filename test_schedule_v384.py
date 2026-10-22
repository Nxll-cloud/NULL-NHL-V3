from schedule_validation_v384 import prior_team_meetings, validate_slate_games, audit_schedule
from storyline_v38 import historical_facts, merge_history
import pandas as pd

def test_name_team_export():
    x=historical_facts({'Player ID':123,'Player':'Sample Player','Team':'MIN'},'2026-10-22','BOS',[])
    assert x['Player']=='Sample Player' and x['Team']=='MIN'

def test_merge_keeps_ranking_names():
    original=pd.DataFrame([{'Player ID':123,'Player':'Sample Player','Team':'MIN','Storyline count':0,'Verified data flags':'','Evidence URLs':''}])
    history=pd.DataFrame([historical_facts({'Player ID':123,'Player':'Sample Player','Team':'MIN'},'2026-10-22','BOS',[])])
    merged=merge_history(original,history)
    assert merged.loc[0,'Player']=='Sample Player' and merged.loc[0,'Team']=='MIN'
    assert 'Player_x' not in merged

def test_official_schedule_match():
    games=[{'Away':'MIN','Home':'BOS','Game ID':111}]
    assert validate_slate_games(games,games).iloc[0]['Schedule status']=='Verified official slate matchup'
    assert 'Mismatch' in validate_slate_games(games,[{'Away':'MIN','Home':'BOS','Game ID':112}]).iloc[0]['Schedule status']

def test_prior_meetings_and_unavailable():
    sched={'games':[{'gameDate':'2026-10-20','id':1,'gameState':'OFF','awayTeam':{'abbrev':'MIN'},'homeTeam':{'abbrev':'BOS'}},
                    {'gameDate':'2026-10-22','id':2,'gameState':'FUT','awayTeam':{'abbrev':'BOS'},'homeTeam':{'abbrev':'MIN'}}]}
    assert prior_team_meetings('MIN','BOS','2026-10-22',sched)==1
    assert prior_team_meetings('MIN','BOS','2026-10-22',{}) is None

def test_audit_no_network():
    games=[{'Away':'MIN','Home':'BOS','Game ID':111}]
    rows=[{'Player ID':123,'Player':'Sample Player','Team':'MIN'}]
    sg,sp,errors=audit_schedule(rows,games,'2026-10-22',schedule_fetch=lambda day:games,team_fetch=lambda team:{'games':[]})
    assert not errors and bool(sp.iloc[0]['Official slate match verified'])
    assert sp.iloc[0]['Prior team meetings (official schedule)']==0
