"""Multi-season NHL regular-season opponent history, pre-slate only.

These are descriptive observations, not independently predictive probabilities.
Missing seasons are explicitly reported and never interpreted as zero goals.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from functools import lru_cache
import pandas as pd
from nhl_data import get_game_log
from storyline_v38 import normalize_team, opponent_lookup

@lru_cache(maxsize=6000)
def season_log(player_id, season):
    return get_game_log(int(player_id), str(season))

def prior_seasons(day, count=3):
    year = date.fromisoformat(day).year
    current_start = year if date.fromisoformat(day).month >= 7 else year-1
    return [f'{start}{start+1}' for start in range(current_start-1, current_start-count-1, -1)]

def summarize_player(row, day, opponent, logs, seasons):
    cutoff = date.fromisoformat(day)
    pid = str(int(row['Player ID']))
    records = []
    statuses = []
    for season in seasons:
        log = logs.get(season)
        if log is None:
            statuses.append(f'{season}: unavailable')
            continue
        valid = {}; rejected = 0
        for g in log:
            try:
                game_date = date.fromisoformat(g['gameDate'])
                gid = int(g['gameId'])
                goals = int(g['goals']); shots = int(g['shots'])
                opp = normalize_team(g.get('opponentAbbrev'))
                if game_date >= cutoff or gid <= 0 or goals < 0 or shots < goals or not opp:
                    rejected += 1; continue
                valid[gid] = (opp, goals, shots)
            except (KeyError, ValueError, TypeError):
                rejected += 1
        against = [x for x in valid.values() if x[0] == normalize_team(opponent)]
        records.extend((season, goals, shots) for _,goals,shots in against)
        statuses.append(f'{season}: {len(valid)} valid games, {len(against)} meetings, {rejected} excluded')
    gp = len(records); goals = sum(x[1] for x in records); shots = sum(x[2] for x in records)
    complete = len(logs) == len(seasons) and all(logs.get(s) is not None for s in seasons)
    flag = (f'Historical opponent trend: {goals} goals in {gp} meetings vs {opponent} (prior seasons)' if complete and gp >= 3 and goals >= 3 else '')
    return {'Player ID':pid, 'Player':row.get('Player',''), 'Team':row.get('Team',''),
            'Upcoming opponent':opponent, 'Prior seasons requested':', '.join(seasons),
            'Prior seasons available':sum(logs.get(s) is not None for s in seasons),
            'Historical opponent GP':gp, 'Historical opponent goals':goals,
            'Historical opponent shots':shots,
            'Historical goals/game':round(goals/gp,3) if gp else None,
            'Historical shots/game':round(shots/gp,3) if gp else None,
            'Historical data status':'Complete' if complete else 'Partial / unavailable',
            'Historical season diagnostics':' | '.join(statuses),
            'Historical storyline flag':flag,
            'Historical source URLs':' | '.join(f'https://api-web.nhle.com/v1/player/{pid}/game-log/{s}/2' for s in seasons if logs.get(s) is not None)}

def fetch_multi_history(rows, games, day, max_players=50, years=3, workers=8, fetch=None):
    fetch = fetch or season_log
    opponents = opponent_lookup(games)
    seasons = prior_seasons(day, years)
    targets = [r for r in list(rows)[:max_players] if r.get('Team') in opponents and r.get('Player ID')]
    result = []; errors = []
    def task(row):
        logs = {}
        for season in seasons:
            try:
                payload = fetch(int(row['Player ID']), season)
                if not isinstance(payload,list):
                    raise ValueError('Invalid game log')
                logs[season] = payload
            except Exception as exc:
                errors.append(f"{row.get('Player')} / {season}: {type(exc).__name__}: {exc}")
        return summarize_player(row,day,opponents[row['Team']],logs,seasons)
    with ThreadPoolExecutor(max_workers=max(1,min(workers,12))) as pool:
        futures=[pool.submit(task,r) for r in targets]
        for f in as_completed(futures):
            try: result.append(f.result())
            except Exception as exc: errors.append(f'{type(exc).__name__}: {exc}')
    return pd.DataFrame(result), errors

def merge_multi_history(combined, history):
    frame=pd.DataFrame(combined).copy()
    if history is None or pd.DataFrame(history).empty: return frame
    h=pd.DataFrame(history).copy()
    if h['Player ID'].astype(str).duplicated().any(): raise ValueError('Duplicate historical player IDs')
    for f in (frame,h): f['Player ID']=f['Player ID'].astype(str).str.replace(r'\.0$','',regex=True)
    h=h.drop(columns=['Player','Team'],errors='ignore')
    # Prior history layers can already have historical columns. Refresh those
    # from this history dataset without pandas adding _x/_y suffixes.
    history_columns=[c for c in h.columns if c != 'Player ID']
    frame=frame.drop(columns=[c for c in history_columns if c in frame.columns],errors='ignore')
    frame=frame.merge(h,on='Player ID',how='left',validate='one_to_one')
    flags=frame.get('Historical storyline flag',pd.Series('',index=frame.index)).fillna('').astype(str)
    baseline=frame.get('Storyline count',pd.Series(0,index=frame.index))
    frame['Storyline count']=pd.to_numeric(baseline,errors='coerce').fillna(0).astype(int)+flags.ne('').astype(int)
    frame['Verified data flags']=frame.get('Verified data flags',pd.Series('',index=frame.index)).fillna('').astype(str)
    frame['Verified data flags']=[ ' | '.join(x for x in (old,new) if x) for old,new in zip(frame['Verified data flags'],flags)]
    if 'Evidence URLs' in frame:
        frame['Evidence URLs']=[' | '.join(x for x in (str(old) if pd.notna(old) else '',str(new) if pd.notna(new) else '') if x) for old,new in zip(frame['Evidence URLs'],frame.get('Historical source URLs',pd.Series('',index=frame.index)))]
    return frame

def missing_player_ids(ranked, roster_audit):
    if ranked is None or roster_audit is None: return []
    def ids(frame):
        f=pd.DataFrame(frame)
        return set(f['Player ID'].dropna().astype(str).str.replace(r'\.0$','',regex=True)) if 'Player ID' in f else set()
    r=ids(ranked); a=ids(roster_audit)
    lookup={str(x.get('Player ID')):x.get('Player','') for x in pd.DataFrame(ranked).to_dict('records')}
    return [{'Player ID':pid,'Player':lookup.get(pid,'')} for pid in sorted(r-a)]
