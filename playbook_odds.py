"""Source-labeled, exact-market sportsbook price comparisons; no fabricated odds."""
import pandas as pd

REQUIRED = {'player','team','market','selection','sportsbook','american_odds','updated_at'}

def implied_probability(american):
    a=int(american)
    if a==0: raise ValueError('Zero American odds invalid')
    return 100/(a+100) if a>0 else -a/(-a+100)

def decimal_odds(american):
    a=int(american)
    if a==0: raise ValueError('Zero American odds invalid')
    return 1+a/100 if a>0 else 1+100/(-a)

def compare_odds(frame):
    missing=REQUIRED-set(frame.columns)
    if missing: raise ValueError('Missing required columns: '+', '.join(sorted(missing)))
    df=frame.copy()
    df=df.dropna(subset=list(REQUIRED))
    df['american_odds']=pd.to_numeric(df['american_odds'],errors='coerce')
    df['updated_at']=pd.to_datetime(df['updated_at'],utc=True,errors='coerce')
    df=df.dropna(subset=['american_odds','updated_at'])
    df=df[df['american_odds']!=0].copy()
    if 'event_id' not in df: df['event_id']=''
    if 'line' not in df: df['line']=''
    for col in ['player','team','market','selection','sportsbook','event_id','line']:
        df[col]=df[col].fillna('').astype(str).str.strip()
    df=df[(df['player']!='') & (df['market']!='') & (df['sportsbook']!='') & (df['selection']!='')]
    df['decimal_odds']=df['american_odds'].apply(decimal_odds)
    df['implied_probability']=df['american_odds'].apply(implied_probability)
    # A single market/selection/line/event may be compared; distinct lines never mix.
    keys=['event_id','player','team','market','selection','line']
    df=df.sort_values('updated_at').drop_duplicates(keys+['sportsbook'],keep='last')
    summaries=[]
    for key,group in df.groupby(keys,dropna=False):
        if group['sportsbook'].nunique()<2: continue
        high=group.loc[group['decimal_odds'].idxmax()]
        low=group.loc[group['decimal_odds'].idxmin()]
        summaries.append(dict(zip(keys,key)) | {
            'best_sportsbook':high['sportsbook'], 'best_odds':int(high['american_odds']),
            'worst_sportsbook':low['sportsbook'], 'worst_odds':int(low['american_odds']),
            'american_points_gap':int(high['american_odds']-low['american_odds']),
            'decimal_price_improvement_pct':round((high['decimal_odds']/low['decimal_odds']-1)*100,2),
            'implied_probability_gap_pp':round((low['implied_probability']-high['implied_probability'])*100,2),
            'sportsbooks_compared':group['sportsbook'].nunique(),
            'best_updated_at':high['updated_at'].isoformat(),
        })
    out=pd.DataFrame(summaries)
    if not out.empty: out=out.sort_values(['decimal_price_improvement_pct','sportsbooks_compared'],ascending=[False,False]).reset_index(drop=True)
    return df,out
