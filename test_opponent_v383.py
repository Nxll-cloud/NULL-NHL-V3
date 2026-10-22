from storyline_v38 import normalize_team, historical_facts

def test_normalize():
    assert normalize_team({'default':' min '}) == 'MIN'
    assert normalize_team(' sjS ') == 'SJS'
    assert normalize_team('ARI') == 'UTA'
    assert normalize_team(None) is None

def test_matching_nested_and_case():
    log=[{'gameDate':'2026-10-18','gameId':1,'goals':1,'shots':3,'opponentAbbrev':{'default':' min '}},
         {'gameDate':'2026-10-19','gameId':2,'goals':1,'shots':2,'opponentAbbrev':'MIN'},
         {'gameDate':'2026-10-22','gameId':3,'goals':1,'shots':2,'opponentAbbrev':'MIN'}]
    x=historical_facts({'Player ID':8478864},'2026-10-22','min',log)
    assert x['Vs opponent GP']==2 and x['Vs opponent goals']==2
    assert x['V3.8 flag count']==1
    assert x['Log rows excluded']==1

def test_zero_matches_has_diagnostic():
    x=historical_facts({'Player ID':8478864},'2026-10-22','BOS',
      [{'gameDate':'2026-10-20','gameId':5,'goals':0,'shots':1,'opponentAbbrev':'MTL'}])
    assert x['Vs opponent GP']==0
    assert 'MTL' in x['Raw opponent samples']
