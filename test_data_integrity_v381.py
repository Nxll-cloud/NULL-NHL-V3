import pandas as pd
from data_integrity_v381 import merge_profile_batches, coverage_audit

def test_merge_batches():
    a=pd.DataFrame([{'Player ID':123,'Jersey':'7'},{'Player ID':456,'Jersey':'8'}])
    b=pd.DataFrame([{'Player ID':'123','Jersey':'9'},{'Player ID':'789','Jersey':'10'}])
    result=merge_profile_batches(a,b)
    assert len(result)==3
    assert result.set_index('Player ID').loc['123','Jersey']=='9'

def test_coverage():
    frame=pd.DataFrame([{'Jersey':'9','Life path':2,'Arena':'X','V3.8 flag count':1,'Storyline count':2},{'Jersey':None,'Life path':None,'Arena':'','V3.8 flag count':0,'Storyline count':0}])
    result=coverage_audit(frame,pd.DataFrame([{'Player ID':1}]),pd.DataFrame([{'Player ID':1}]))
    assert result['Eligible players']==2 and result['Total V3.8 flags']==1
    assert result['Players with jersey']==1
