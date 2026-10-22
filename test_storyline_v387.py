import pandas as pd
from storyline_v387 import separate_leaders

def test_separate_leaders_and_longshot():
    f=pd.DataFrame([
        {'Player ID':'1','Player':'Form Leader','Team':'AAA','Statistical rank':1,'V3.2 Adjusted Index':150,'Storyline count':2,'Shots/G L5':4,'Historical data status':'Complete','Historical opponent GP':5,'Historical opponent goals':2,'Historical opponent shots':20,'Historical goals/game':.4},
        {'Player ID':'2','Player':'History Leader','Team':'BBB','Statistical rank':5,'V3.2 Adjusted Index':120,'Storyline count':1,'Shots/G L5':3,'Historical data status':'Complete','Historical opponent GP':10,'Historical opponent goals':8,'Historical opponent shots':40,'Historical goals/game':.8},
        {'Player ID':'3','Player':'Sleeper','Team':'CCC','Statistical rank':30,'V3.2 Adjusted Index':80,'Storyline count':1,'Shots/G L5':2.5,'Historical data status':'Complete','Historical opponent GP':4,'Historical opponent goals':5,'Historical opponent shots':17,'Historical goals/game':1.25},
    ])
    d=separate_leaders(f)
    assert d['leaders']['statistical']['Player']=='Form Leader'
    assert d['leaders']['storyline']['Player']=='History Leader'
    assert d['leaders']['longshots']['Player']=='Sleeper'
    assert len(d['overlap'])==2

def test_missing_history_is_not_fabricated():
    f=pd.DataFrame([{'Player ID':'4','Player':'No history','Statistical rank':1,'Storyline count':0}])
    d=separate_leaders(f)
    assert d['leaders']['storyline'] is None
    assert d['statistical'].iloc[0]['Historical evidence points']==0
