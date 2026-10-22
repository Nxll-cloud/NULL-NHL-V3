import pandas as pd
from player_targets_v49 import target_rows,slate_targets
from numerology_v48 import analyze_game

def test_team_scoping_and_deterministic():
    rows=pd.DataFrame([{'Player':'Alpha','Team':'BOS','Player ID':1,'V3.2 Adjusted Index':4}, {'Player':'Beta','Team':'NSH','Player ID':2,'V3.2 Adjusted Index':8}])
    result=target_rows(rows,'BOS','Boston Bruins','TD Garden','2026-10-22')
    assert len(result)==1 and result[0]['player']=='Alpha'
    assert result==target_rows(rows,'BOS','Boston Bruins','TD Garden','2026-10-22')

def test_duplicate_id_not_repeated():
    rows=pd.DataFrame([{'Player':'Same','Team':'BOS','Player ID':1},{'Player':'Same','Team':'BOS','Player ID':1}])
    assert len(target_rows(rows,'BOS','Boston Bruins','TD Garden','2026-10-22'))==1

def test_arena_missing_graceful():
    rows=pd.DataFrame([{'Player':'Alpha','Team':'BOS','Player ID':1}])
    assert target_rows(rows,'BOS','Boston Bruins','', '2026-10-22')[0]['arena_matches']==[]

def test_all_games_and_teams():
    g=analyze_game({'Away':'BOS','Home':'NSH','Venue':'TD Garden'},'2026-10-22',{'BOS':'Boston Bruins','NSH':'Nashville Predators'})
    rows=pd.DataFrame([{'Player':'Alpha','Team':'BOS','Player ID':1},{'Player':'Beta','Team':'NSH','Player ID':2}])
    out=slate_targets([g],rows,'2026-10-22')
    assert len(out)==1 and len(out[0]['away_targets'])==1 and len(out[0]['home_targets'])==1
