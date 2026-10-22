import pandas as pd
from roster_schedule_v385 import roster_ids,schedule_coverage,audit_roster_and_history

def test_roster_ids():
    assert roster_ids({'forwards':[{'id':123}],'defensemen':[]})=={'123'}

def test_roster_missing_is_not_empty():
    try: roster_ids({}); assert False
    except ValueError: pass

def test_schedule_counts_and_excludes_future():
    data={'games':[{'id':1,'gameDate':'2026-10-20','gameType':2,'gameState':'OFF','awayTeam':{'abbrev':'MIN'},'homeTeam':{'abbrev':'BOS'}},
                   {'id':2,'gameDate':'2026-10-22','gameType':2,'gameState':'FUT','awayTeam':{'abbrev':'MIN'},'homeTeam':{'abbrev':'BOS'}}]}
    result=schedule_coverage(data,'MIN','BOS','2026-10-22')
    assert result['Completed games inspected']==1 and result['Prior opponent meetings']==1

def test_missing_schedule_is_unknown():
    assert schedule_coverage({},'MIN','BOS','2026-10-22')['Prior opponent meetings'] is None

def test_roster_mismatch_visible():
    rows=[{'Player ID':123,'Player':'Example','Team':'MIN'},{'Player ID':124,'Player':'Another','Team':'MIN'}]
    games=[{'Away':'MIN','Home':'BOS'}]
    players,teams,errors=audit_roster_and_history(rows,games,'2026-10-22',
        roster_fetch=lambda team:{'forwards':[{'id':123}]},schedule_fetch=lambda team:{'games':[]})
    assert not errors and len(players)==2
    assert players.iloc[0]['Roster membership']=='Found on season roster'
    assert players.iloc[1]['Roster membership']=='NOT FOUND on assigned team roster'

def test_fetch_failure_not_zero():
    def fail(team): raise RuntimeError('offline')
    players,teams,errors=audit_roster_and_history([{'Player ID':1,'Player':'X','Team':'MIN'}],
        [{'Away':'MIN','Home':'BOS'}],'2026-10-22',roster_fetch=fail,schedule_fetch=fail)
    assert errors and pd.isna(teams.iloc[0]['Prior opponent meetings'])
