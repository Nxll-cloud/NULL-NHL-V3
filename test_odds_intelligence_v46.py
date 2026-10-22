import pandas as pd
from odds_intelligence_v46 import attach_model, order_opportunities, quote_audit, quotes_for_market, normalized_name

def sample():
    return pd.DataFrame([{"event_id":"e1","player":"Kirill Kaprizov","market":"player_goal_scorer_anytime","selection":"Yes","line":"","best_odds":300,"worst_odds":200,"decimal_price_improvement_pct":25.0,"sportsbooks_compared":3,"best_sportsbook":"A","worst_sportsbook":"B"}])

def test_name_normalization():
    assert normalized_name("José O’Neill")==normalized_name("Jose O Neill")

def test_model_join():
    ranked=pd.DataFrame([{"Player":"Kirill Kaprizov","Team":"MIN","Player ID":123,"Statistical rank":1,"V3.2 Adjusted Index":156.2}])
    out=attach_model(sample(),ranked)
    assert out.iloc[0]["model_rank"]==1
    assert out.iloc[0]["team"]=="MIN"

def test_longshot_filter():
    assert len(order_opportunities(sample(),"Longshots"))==1
    assert len(order_opportunities(sample().assign(best_odds=250),"Longshots"))==0

def test_audit_does_not_invent_reason():
    assert quote_audit(pd.DataFrame(index=range(5)),pd.DataFrame(index=range(4)))["excluded_or_consolidated"]==1

def test_exact_event_matching():
    from playbook_odds import compare_odds
    rows=[]
    for event in ["e1","e2"]:
        for book,odds in [("A",200),("B",300)]:
            rows.append({"event_id":event,"player":"Kirill Kaprizov","team":"MIN","market":"player_goal_scorer_anytime","selection":"Yes","line":"","sportsbook":book,"american_odds":odds,"updated_at":"2026-10-22T15:00:00Z"})
    clean,disc=compare_odds(pd.DataFrame(rows))
    assert len(quotes_for_market(clean,disc.iloc[0]))==2
