import pandas as pd
import pytest
from ranking_integrity_v3871 import assign_statistical_ranks,validate_statistical_ranks
from storyline_v387 import separate_leaders


def players():
    return [{'Player ID':1,'Player':'A','Team':'MIN','V3.2 Adjusted Index':156.2,'Shots/G L5':4.2,'Storyline count':1},
            {'Player ID':2,'Player':'B','Team':'SJS','V3.2 Adjusted Index':100,'Shots/G L5':3,'Storyline count':1},
            {'Player ID':3,'Player':'C','Team':'NSH','V3.2 Adjusted Index':62.8,'Shots/G L5':1.4,'Storyline count':1}]


def test_top_is_rank_one_not_482():
    f=assign_statistical_ranks(players())
    assert f['Statistical rank'].tolist()==[1,2,3]
    assert separate_leaders(f)['leaders']['statistical']['Statistical rank']==1


def test_rank_survives_merge_and_reordering():
    f=assign_statistical_ranks(players())
    f=f.merge(pd.DataFrame([{'Player ID':3,'Historical opponent GP':4,'Historical opponent goals':4,'Historical opponent shots':18,'Historical goals/game':1.,'Historical data status':'Complete'}]),on='Player ID',how='left')
    f=f.iloc[::-1].reset_index(drop=True)
    assert validate_statistical_ranks(f)
    leaders=separate_leaders(f)['leaders']
    assert leaders['statistical']['Player']=='A'
    assert leaders['storyline']['Player']=='C'
    assert leaders['statistical']['Statistical rank']==1


def test_missing_rank_rejected():
    with pytest.raises(ValueError): separate_leaders(pd.DataFrame(players()))


def test_duplicate_rank_rejected():
    f=assign_statistical_ranks(players()); f.loc[1,'Statistical rank']=1
    with pytest.raises(ValueError): validate_statistical_ranks(f)


def test_duplicate_id_rejected():
    rows=players(); rows[1]['Player ID']=1
    with pytest.raises(ValueError): assign_statistical_ranks(rows)
