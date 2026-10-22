import pandas as pd
from odds_intelligence_v46 import attach_model

def test_duplicate_name_never_assigned_arbitrary_model_rank():
    odds=pd.DataFrame([{'player':'Elias Pettersson','event_id':'one','best_odds':1400}])
    ranked=pd.DataFrame([{'Player':'Elias Pettersson','Team':'VAN','Player ID':101,'Statistical rank':1},
                         {'Player':'Elias Pettersson','Team':'VAN','Player ID':202,'Statistical rank':170}])
    result=attach_model(odds,ranked)
    assert pd.isna(result.iloc[0]['model_rank'])
    assert result.iloc[0]['player_id']==''
    assert result.iloc[0]['identity_status'].startswith('Ambiguous')

def test_unique_name_still_unverified_without_provider_player_id():
    odds=pd.DataFrame([{'player':'Kirill Kaprizov','event_id':'one'}])
    ranked=pd.DataFrame([{'Player':'Kirill Kaprizov','Team':'MIN','Player ID':101,'Statistical rank':1}])
    result=attach_model(odds,ranked)
    assert result.iloc[0]['model_rank']==1
    assert 'Unverified' in result.iloc[0]['identity_status']
