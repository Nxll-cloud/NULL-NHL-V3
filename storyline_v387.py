"""V3.8.7: distinct, explainable descriptive rankings; no predictive probabilities."""
import pandas as pd


def _num(frame, col):
    return pd.to_numeric(frame[col], errors='coerce').fillna(0) if col in frame else pd.Series(0.0, index=frame.index)


def separate_leaders(combined, top_n=10):
    f = pd.DataFrame(combined).copy()
    if f.empty:
        return {'statistical': f, 'storyline': f, 'overlap': f, 'longshots': f, 'leaders': {}}
    f['Statistical rank'] = _num(f, 'Statistical rank').replace(0, len(f)+1)
    f['Storyline count'] = _num(f, 'Storyline count')
    f['Historical opponent GP'] = _num(f, 'Historical opponent GP')
    f['Historical opponent goals'] = _num(f, 'Historical opponent goals')
    f['Historical opponent shots'] = _num(f, 'Historical opponent shots')
    f['Historical goals/game'] = _num(f, 'Historical goals/game')
    f['Shots/G L5'] = _num(f, 'Shots/G L5')
    f['V3.2 Adjusted Index'] = _num(f, 'V3.2 Adjusted Index')
    # Historical scoring is evidence of a past matchup, not an expected-goals estimate.
    # Only score histories with 3+ meetings and complete seasons. No-data stays ineligible.
    complete = f['Historical data status'].eq('Complete') if 'Historical data status' in f else pd.Series(False,index=f.index)
    eligible_hist = complete & f['Historical opponent GP'].ge(3)
    f['Historical evidence points'] = 0.0
    f.loc[eligible_hist, 'Historical evidence points'] = (
        f.loc[eligible_hist, 'Historical opponent goals'].clip(upper=10) * 2
        + f.loc[eligible_hist, 'Historical goals/game'].clip(upper=1.5) * 6
        + f.loc[eligible_hist, 'Historical opponent shots'].clip(upper=50) / 10
    ).round(2)
    # Flag count is a secondary signal, not the primary driver of the storyline leader.
    f['Storyline evidence score'] = (f['Historical evidence points'] + f['Storyline count'].clip(upper=5) * 1.5).round(2)
    f['Historical coverage'] = ['Complete, >=3 meetings' if ok else 'Insufficient / unavailable' for ok in eligible_hist]
    statistical = f.sort_values(['Statistical rank','V3.2 Adjusted Index','Player'], ascending=[True,False,True],kind='stable')
    # Storyline ranking requires actual flags and/or qualifying opponent history.
    story = f[(f['Storyline count']>0) | eligible_hist].sort_values(
        ['Storyline evidence score','Historical opponent goals','Historical opponent GP','Statistical rank','Player'],
        ascending=[False,False,False,True,True],kind='stable').copy()
    story['Storyline rank'] = range(1,len(story)+1)
    f = f.merge(story[['Player ID','Storyline rank']],on='Player ID',how='left',validate='one_to_one') if 'Player ID' in f else f
    overlap = f[(f['Statistical rank']<=20)&(f.get('Storyline rank',pd.Series(float('nan'),index=f.index))<=20)].sort_values(['Statistical rank','Storyline rank'],kind='stable')
    longshots = f[(f['Statistical rank']>20)&(f['Shots/G L5']>=2)&(f['Storyline evidence score']>0)].sort_values(
        ['Storyline evidence score','Shots/G L5','Statistical rank'],ascending=[False,False,True],kind='stable')
    return {'statistical':statistical.head(top_n), 'storyline':story.head(top_n), 'overlap':overlap.head(top_n), 'longshots':longshots.head(top_n),
            'leaders':{'statistical':statistical.iloc[0] if len(statistical) else None,
                       'storyline':story.iloc[0] if len(story) else None,
                       'overlap':overlap.iloc[0] if len(overlap) else None,
                       'longshots':longshots.iloc[0] if len(longshots) else None}}
