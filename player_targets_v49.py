"""Recreational player/team/arena numerical matching, never scoring probabilities."""
import math
import pandas as pd
from numerology_v48 import gematria, universal_day

METHODS=(('ordinal_root','English'),('reduction_root','Reduction'),('reverse_root','Reverse'))  # display order (all three digits)
# The three digits are not independent: Reduction always equals English (both are the name total reduced mod 9), and
# Reverse mirrors English (English + Reverse always reduces to 9, e.g. 7 <-> 2, 3 <-> 6). So a name carries ONE digit.
# Scoring counts that digit once per target: vs the day number, the English or the Reverse digit may hit (at most one
# label); vs a team or arena name, Reverse agrees whenever English does, so only English is compared.
DAY_METHODS=(('ordinal_root','English'),('reverse_root','Reverse'))
NAME_METHODS=(('ordinal_root','English'),)

def _first_hit(values, target, methods):
    """[label] of the first cipher whose digit equals the target (each name digit counts once), else []."""
    if not target:
        return []
    return next(([label] for field,label in methods if values[field]==target[field]), [])

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
        day_matches=_first_hit(values,{f:day_root for f,_ in DAY_METHODS},DAY_METHODS)
        team_matches=_first_hit(values,team_values if team_values['letters'] else None,NAME_METHODS)
        arena_matches=_first_hit(values,arena_values if arena_values and arena_values['letters'] else None,NAME_METHODS)
        # Match counts are descriptive only, not estimated probabilities.
        total=len(day_matches)+len(team_matches)+len(arena_matches)
        try: form=float(row.get('V3.2 Adjusted Index',0))
        except (ValueError,TypeError): form=0.0
        if not math.isfinite(form): form=0.0  # V5.3: NaN would break sorting and display
        out.append({'player':name,'player_id':player_id,'team':team,'number':values['ordinal_root'],
                    'day':day_matches,'team_matches':team_matches,'arena_matches':arena_matches,
                    'matches':total,'form':form,'values':values,
                    # raw cipher totals before the one-digit reduction: unique-ish per name, shown and used for ties
                    'eng_total':values['ordinal'],'rev_total':values['reverse'],'letters':values['letters']})
    out.sort(key=lambda x:(-x['matches'],-len(x['day']),-len(x['arena_matches']),-x['form'],x['player']))
    return out

def slate_targets(analyses, ranked, day):
    return [{'game':g,'away_targets':target_rows(ranked,g['away'],g['away_name'],g['arena'],day),
             'home_targets':target_rows(ranked,g['home'],g['home_name'],g['arena'],day)} for g in analyses]
