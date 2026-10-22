"""Recreational player/team/arena numerical matching, never scoring probabilities."""
import pandas as pd
from numerology_v48 import gematria, universal_day

METHODS=(('ordinal_root','English'),('reduction_root','Reduction'),('reverse_root','Reverse'))

def target_rows(ranked, team, team_name, arena, day):
    """Rank named, ID-distinct roster members using reproducible numerical coincidences."""
    if ranked is None or ranked.empty or not {'Player','Team'}.issubset(ranked.columns):
        return []
    subset=ranked[ranked['Team'].astype(str).str.upper().eq(str(team).upper())]
    day_root=universal_day(day)
    team_values=gematria(team_name)
    arena_values=gematria(arena) if arena else None
    out=[]; seen=set()
    for _,row in subset.iterrows():
        name=str(row.get('Player','')).strip()
        if not name or name.lower()=='nan': continue
        raw_id=row.get('Player ID','')
        try: player_id=str(int(float(raw_id))) if pd.notna(raw_id) else ''
        except (ValueError,TypeError,OverflowError): player_id=''
        key=player_id or (str(team).upper(),name.casefold())
        if key in seen: continue
        seen.add(key)
        values=gematria(name)
        day_matches=[label for field,label in METHODS if values[field]==day_root]
        team_matches=[label for field,label in METHODS if values[field]==team_values[field]]
        arena_matches=[label for field,label in METHODS if arena_values and values[field]==arena_values[field]]
        # Match counts are descriptive only, not estimated probabilities.
        total=len(day_matches)+len(team_matches)+len(arena_matches)
        try: form=float(row.get('V3.2 Adjusted Index',0))
        except (ValueError,TypeError): form=0.0
        out.append({'player':name,'player_id':player_id,'team':team,'number':values['ordinal_root'],
                    'day':day_matches,'team_matches':team_matches,'arena_matches':arena_matches,
                    'matches':total,'form':form,'values':values})
    out.sort(key=lambda x:(-x['matches'],-len(x['day']),-len(x['arena_matches']),-x['form'],x['player']))
    return out

def slate_targets(analyses, ranked, day):
    return [{'game':g,'away_targets':target_rows(ranked,g['away'],g['away_name'],g['arena'],day),
             'home_targets':target_rows(ranked,g['home'],g['home_name'],g['arena'],day)} for g in analyses]
