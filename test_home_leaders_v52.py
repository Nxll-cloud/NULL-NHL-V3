import pandas as pd
from home_leaders_v52 import choose_leaders, all_targets, gematria_shortlist

def fixture():
    games=[{'Away':'NSH','Home':'BOS','Venue':'TD Garden','Start (UTC)':'2026-10-22T23:00:00Z'}]
    ranked=pd.DataFrame([{'Player':name,'Player ID':pid,'Team':team,'V3.2 Adjusted Index':form} for name,pid,team,form in [('Ryan O\'Reilly',1,'NSH',74),('Adam Wilsby',2,'NSH',12),('Mavrik Bourque',3,'NSH',25),('David Pastrnak',4,'BOS',92),('Charlie McAvoy',5,'BOS',50),('Pavel Zacha',6,'BOS',80)]])
    return ranked,all_targets(games,ranked,'2026-10-22')

def test_all_team_targets():
    ranked,targets=fixture()
    assert len(targets)==1
    assert len(targets[0]['away_targets'])==3
    assert len(targets[0]['home_targets'])==3

def test_four_distinct_leaders():
    ranked,targets=fixture()
    odds=pd.DataFrame([{'player':'Adam Wilsby','best_odds':3500,'best_sportsbook':'A','decimal_price_improvement_pct':100.0},{'player':'Pavel Zacha','best_odds':200,'best_sportsbook':'B','decimal_price_improvement_pct':30.0}])
    leaders=choose_leaders(ranked,targets,odds)
    ids=[p['player_id'] for p in leaders.values() if p is not None]
    assert len(ids)==len(set(ids))
    assert set(leaders)=={'statistical','gematria','odds','overlap'}

def test_missing_odds_not_invented():
    ranked,targets=fixture()
    leaders=choose_leaders(ranked,targets)
    assert leaders['odds'] is None

def test_shortlist_is_sorted():
    ranked,targets=fixture()
    shortlist=gematria_shortlist(targets)
    assert all(shortlist[i]['matches']>=shortlist[i+1]['matches'] for i in range(len(shortlist)-1))
