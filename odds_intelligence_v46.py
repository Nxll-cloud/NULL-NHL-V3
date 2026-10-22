"""Mobile odds intelligence: exact-market comparisons and descriptive model overlap."""
import re
import unicodedata
import pandas as pd
from playbook_odds import compare_odds

def normalized_name(value):
    value=unicodedata.normalize("NFKD",str(value or ""))
    value="".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+","",value.casefold())

def price_label(value):
    try:
        n=int(value)
        return f"+{n}" if n>0 else str(n)
    except (TypeError,ValueError): return "—"

def quote_audit(raw, cleaned):
    """Report ingestion, filtering, and duplicate consolidation transparently."""
    raw_count=len(raw)
    # compare_odds retains one quote per event/player/market/selection/line/book.
    return {"received":raw_count,"accepted":len(cleaned),
            "excluded_or_consolidated":max(0,raw_count-len(cleaned))}

def attach_model(discrepancies, ranked):
    """Conservative identity matching: duplicate names must never receive a guessed rank."""
    out=discrepancies.copy()
    out['model_rank']=pd.NA
    out['model_index']=pd.NA
    out['team']=''
    out['player_id']=''
    out['identity_status']='Unverified: no unique provider player ID'
    if ranked is None or ranked.empty or 'Player' not in ranked:
        return out
    model=ranked.copy()
    if 'Statistical rank' not in model and 'V3.2 Adjusted Index' in model:
        model=model.sort_values('V3.2 Adjusted Index',ascending=False)
        model['Statistical rank']=range(1,len(model)+1)
    model['_name']=model['Player'].map(normalized_name)
    groups=model.groupby('_name',dropna=False)
    for i,row in out.iterrows():
        key=normalized_name(row['player'])
        if key not in groups.groups: continue
        matches=groups.get_group(key)
        if len(matches)!=1:
            out.at[i,'identity_status']='Ambiguous: multiple NHL players share this name'
            continue
        match=matches.iloc[0]
        out.at[i,'model_rank']=match.get('Statistical rank',pd.NA)
        out.at[i,'model_index']=match.get('V3.2 Adjusted Index',pd.NA)
        out.at[i,'team']=str(match.get('Team',''))
        pid=match.get('Player ID','')
        try: out.at[i,'player_id']=str(int(float(pid)))
        except (TypeError,ValueError): pass
        # A name-only provider feed cannot establish that two books refer to the same individual.
        out.at[i,'identity_status']='Unverified: name-only sportsbook feed'
    return out


def order_opportunities(frame, mode="Biggest discrepancy", minimum_odds=None, max_rank=None):
    result=frame.copy()
    if minimum_odds is not None:
        result=result[pd.to_numeric(result["best_odds"],errors="coerce")>=minimum_odds]
    if max_rank is not None:
        result=result[pd.to_numeric(result.get("model_rank",pd.Series(pd.NA,index=result.index)),errors="coerce")<=max_rank]
    if mode=="Model-backed":
        result["_rank"]=pd.to_numeric(result.get("model_rank",pd.Series(pd.NA,index=result.index)),errors="coerce")
        result=result.sort_values(["_rank","decimal_price_improvement_pct"],ascending=[True,False],na_position="last")
    elif mode=="Longshots":
        result=result[pd.to_numeric(result["best_odds"],errors="coerce")>=300]
        result["_rank"]=pd.to_numeric(result.get("model_rank",pd.Series(pd.NA,index=result.index)),errors="coerce")
        result=result.sort_values(["_rank","best_odds"],ascending=[True,False],na_position="last")
    else:
        result=result.sort_values(["decimal_price_improvement_pct","sportsbooks_compared"],ascending=[False,False])
    return result.drop(columns=["_rank"],errors="ignore")

def quotes_for_market(cleaned, row):
    mask=pd.Series(True,index=cleaned.index)
    for field in ["event_id","player","market","selection","line"]:
        mask &= cleaned[field].astype(str).eq(str(row[field]))
    return cleaned.loc[mask].sort_values("decimal_odds",ascending=False)


def identity_ambiguities(discrepancies, ranked):
    """Return suspected identity collisions even when model coverage is partial."""
    if ranked is None or ranked.empty or 'Player' not in ranked:
        return set()
    counts=ranked['Player'].map(normalized_name).value_counts()
    return set(counts[counts>1].index)
