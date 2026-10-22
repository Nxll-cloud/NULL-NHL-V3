from odds_api_v45 import fetch_odds, OddsFeedError
from playbook_odds import compare_odds

class FakeResponse:
    status_code=200
    def __init__(self, body): self.body=body
    def json(self): return self.body

class FakeSession:
    def get(self,url,params,timeout):
        if url.endswith('/events'):
            return FakeResponse([{'id':'event123'}])
        return FakeResponse({'home_team':'A','away_team':'B','bookmakers':[
            {'title':'Book One','markets':[{'key':'player_goal_scorer_anytime','last_update':'2026-10-22T18:00:00Z','outcomes':[{'description':'Player X','name':'Yes','price':220}]}]},
            {'title':'Book Two','markets':[{'key':'player_goal_scorer_anytime','last_update':'2026-10-22T18:00:00Z','outcomes':[{'description':'Player X','name':'Yes','price':280}]}]}
        ]})

def test_api_and_discrepancy():
    frame,warnings=fetch_odds('fake',session=FakeSession())
    assert not warnings and len(frame)==2
    _,differences=compare_odds(frame)
    assert len(differences)==1 and differences.iloc[0]['best_sportsbook']=='Book Two'

def test_missing_api_key():
    try: fetch_odds('')
    except OddsFeedError: pass
    else: assert False
