"""Distinct, source-backed homepage leaders. Symbolic coincidences are not predictions."""
import pandas as pd
from numerology_v48 import analyze_game
from player_targets_v49 import slate_targets
from odds_intelligence_v46 import normalized_name

TEAM_NAMES={'ANA':'Anaheim Ducks','BOS':'Boston Bruins','BUF':'Buffalo Sabres','CAR':'Carolina Hurricanes','CBJ':'Columbus Blue Jackets','CGY':'Calgary Flames','CHI':'Chicago Blackhawks','COL':'Colorado Avalanche','DAL':'Dallas Stars','DET':'Detroit Red Wings','EDM':'Edmonton Oilers','FLA':'Florida Panthers','LAK':'Los Angeles Kings','MIN':'Minnesota Wild','MTL':'Montreal Canadiens','NJD':'New Jersey Devils','NSH':'Nashville Predators','NYI':'New York Islanders','NYR':'New York Rangers','OTT':'Ottawa Senators','PHI':'Philadelphia Flyers','PIT':'Pittsburgh Penguins','SEA':'Seattle Kraken','SJS':'San Jose Sharks','STL':'St Louis Blues','TBL':'Tampa Bay Lightning','TOR':'Toronto Maple Leafs','UTA':'Utah Mammoth','VAN':'Vancouver Canucks','VGK':'Vegas Golden Knights','WPG':'Winnipeg Jets','WSH':'Washington Capitals'}

def all_targets(games,ranked,day):
    if ranked is None or ranked.empty or not games:return []
    analyses=[analyze_game(g,day,TEAM_NAMES) for g in games]
    return slate_targets(analyses,ranked,day)

def flatten_targets(targets):
    results=[]
    for match in targets:
        for side in ('away','home'):
            for t in match[side+'_targets']:
                results.append({**t,'opponent':match['game']['home' if side=='away' else 'away'], 'arena':match['game']['arena']})
    return results

def choose_leaders(ranked,targets,discrepancies=None):
    """Four DIFFERENT NHL players, or None where the underlying evidence is unavailable.

    Odds names are only included when they match a unique roster name; identity remains
    unverified without provider player IDs, even if the name matches.
    """
    players=flatten_targets(targets)
    by_id={p['player_id'] or (p['team'],p['player'].casefold()):p for p in players}
    unique=list(by_id.values())
    stats=sorted(unique,key=lambda p:(-p['form'],-p['matches'],p['player']))
    gems=sorted(unique,key=lambda p:(-p['matches'],-len(p['day']),-len(p['arena_matches']),-p['form'],p['player']))
    # Overlap rewards strong relative statistical standing AND symbolic coincidences,
    # without calling the result a probability or an expected-value estimate.
    stat_order={p['player_id'] or (p['team'],p['player'].casefold()):i+1 for i,p in enumerate(stats)}
    overlap=sorted([p for p in unique if p['matches']>0 and p['form']>0],key=lambda p:(-p['matches'],stat_order[p['player_id'] or (p['team'],p['player'].casefold())],p['player']))
    used=set(); selected={}
    def take(label,candidates):
        for p in candidates:
            key=p['player_id'] or (p['team'],p['player'].casefold())
            if key not in used:
                used.add(key);selected[label]=p;return
        selected[label]=None
    take('statistical',stats)
    take('gematria',gems)
    odds=[]
    if isinstance(discrepancies,pd.DataFrame) and not discrepancies.empty:
        # Require exact unique name in this slate, to avoid presenting ambiguous
        # Pettersson-like names as resolved; labels still say 'unverified'.
        names={}
        # V5.3: same accent/punctuation-insensitive key used by the Odds tab.
        for p in unique:names.setdefault(normalized_name(p['player']),[]).append(p)
        ordered=discrepancies.copy()
        ordered['_gap']=pd.to_numeric(ordered['decimal_price_improvement_pct'],errors='coerce') if 'decimal_price_improvement_pct' in ordered else float('nan')
        ordered=ordered.sort_values('_gap',ascending=False,na_position='last')
        for _,row in ordered.iterrows():
            if pd.isna(row['_gap']): continue
            key=normalized_name(row.get('player',''))
            matches=names.get(key,[]) if key else []
            if len(matches)==1:
                odds.append({**matches[0], 'best_odds':row.get('best_odds'), 'best_sportsbook':row.get('best_sportsbook'), 'gap_pct':row.get('decimal_price_improvement_pct')})
    take('odds',odds)
    take('overlap',overlap)
    return selected

def gematria_shortlist(targets,limit=8):
    rows=flatten_targets(targets)
    rows.sort(key=lambda p:(-p['matches'],-len(p['day']),-len(p['arena_matches']),-p['form'],p['player']))
    return rows[:limit]
