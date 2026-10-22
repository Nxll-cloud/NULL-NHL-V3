"""V3.8 pre-slate opponent history and season milestone facts.

No injuries, trades, former-team or news inference. Facts must be sourced to NHL
regular-season game logs and restricted to dates strictly before the slate.
"""
from datetime import date
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import pandas as pd
from nhl_data import get_game_log, SEASON

@lru_cache(maxsize=1200)
def cached_log(player_id, season):
    return get_game_log(int(player_id), season)


def opponent_lookup(games):
    out = {}
    for g in games:
        a, h = g.get('Away'), g.get('Home')
        if a and h:
            if a in out or h in out:
                raise ValueError('Team appears in more than one game')
            out[a], out[h] = h, a
    return out


def normalize_team(value):
    """Normalize NHL abbreviations; never guess unverified franchise aliases."""
    if isinstance(value, dict):
        value = value.get('default') or value.get('abbrev')
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    # Known historical/alternate NHL codes only; do not remap other teams.
    aliases = {'ARI': 'UTA', 'PHX': 'UTA', 'UTH': 'UTA', 'S.J': 'SJS',
               'N.J': 'NJD', 'L.A': 'LAK', 'T.B': 'TBL'}
    return aliases.get(value, value) if value else None


def historical_facts(row, day, opponent, log, season=SEASON):
    pid = str(int(row['Player ID']))
    cutoff = date.fromisoformat(day)
    unique, seen = [], set()
    raw_opponents = Counter()
    missing_opponents = 0
    for g in log:
        try:
            d = date.fromisoformat(g['gameDate'])
            gid = int(g['gameId'])
            goals = int(g['goals'])
            shots = int(g['shots'])
            raw = g.get('opponentAbbrev')
            opp = normalize_team(raw)
            if raw is None or opp is None:
                missing_opponents += 1
            else:
                raw_opponents[str(raw)] += 1
            if not isinstance(opp, str) or not opp or goals < 0 or shots < goals or gid <= 0:
                continue
            if d >= cutoff or gid in seen:
                continue
            seen.add(gid)
            unique.append((d, opp, goals, shots))
        except (KeyError, ValueError, TypeError):
            continue
    unique.sort(reverse=True)
    normalized_opponent = normalize_team(opponent)
    against = [g for g in unique if g[1] == normalized_opponent]
    flags = []
    if len(against) >= 2:
        gp, total = len(against), sum(g[2] for g in against)
        if total >= 2:
            flags.append(f'Opponent history: {total} goals in {gp} prior games vs {opponent} (current season)')
    else:
        gp, total = len(against), sum(g[2] for g in against)
    season_goals = sum(g[2] for g in unique)
    # Milestones are descriptive round season-goal totals, not career records.
    next_mark = next((m for m in (10, 20, 30, 40, 50, 60) if m > season_goals), None)
    distance = next_mark - season_goals if next_mark else None
    if distance == 1:
        flags.append(f'Season milestone: 1 goal from {next_mark} goals')
    milestone_watch = (f'{distance} goals from {next_mark} season goals'
                       if distance in (2, 3) else '')
    source = f'https://api-web.nhle.com/v1/player/{pid}/game-log/{season}/2'
    return {'Player ID':pid, 'Player':row.get('Player',''), 'Team':row.get('Team',''), 'Opponent':opponent,
            'Vs opponent GP':gp, 'Vs opponent goals':total,
            'Season goals (log)':season_goals, 'Milestone distance':distance,
            'Milestone watch (not a flag)':milestone_watch,
            'Log rows received':len(log), 'Log rows valid pre-slate':len(unique),
            'Log rows excluded':len(log)-len(unique),
            'Opponent match method':'normalized opponentAbbrev team code',
            'Opponent normalized':normalized_opponent,
            'Raw opponent samples':' | '.join(f'{k} ({v})' for k,v in raw_opponents.most_common(12)),
            'Distinct raw opponent values':len(raw_opponents),
            'Rows missing opponent code':missing_opponents,
            'Opponent match diagnostic':('Matched' if gp else 'No match; inspect raw opponent samples'),
            'V3.8 flags':' | '.join(flags), 'V3.8 flag count':len(flags),
            'V3.8 source':source, 'V3.8 status':'Verified pre-slate game-log data'}


def fetch_history(rows, games, day, max_players=50, workers=6, season=SEASON):
    opponents = opponent_lookup(games)
    records, errors = [], []
    targets = [r for r in list(rows)[:max_players] if r.get('Team') in opponents and r.get('Player ID')]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(cached_log, int(r['Player ID']), season):r for r in targets}
        for future in as_completed(futures):
            row = futures[future]
            try:
                records.append(historical_facts(row, day, opponents[row['Team']], future.result(), season))
            except Exception as exc:
                errors.append(f"{row.get('Player')}: {type(exc).__name__}: {exc}")
    return pd.DataFrame(records), errors


def merge_history(combined, history):
    frame = pd.DataFrame(combined).copy()
    if history is None or history.empty:
        frame['V3.8 flag count'] = 0
        frame['V3.8 flags'] = ''
        frame['V3.8 status'] = 'Not fetched'
        return frame
    h = history.copy()
    if h['Player ID'].duplicated().any():
        raise ValueError('Duplicate history player IDs')
    frame['Player ID'] = frame['Player ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    h['Player ID'] = h['Player ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    # Names/teams in history are audit metadata, not replacement ranking columns.
    h = h.drop(columns=[c for c in ('Player', 'Team') if c in h.columns])
    frame = frame.merge(h, on='Player ID', how='left', validate='one_to_one')
    frame['V3.8 flag count'] = pd.to_numeric(frame['V3.8 flag count'], errors='coerce').fillna(0).astype(int)
    frame['V3.8 flags'] = frame['V3.8 flags'].fillna('')
    frame['V3.8 status'] = frame['V3.8 status'].fillna('Not fetched')
    frame['Storyline count'] = pd.to_numeric(frame['Storyline count'], errors='coerce').fillna(0).astype(int) + frame['V3.8 flag count']
    frame['Verified data flags'] = frame.apply(lambda r: ' | '.join(x for x in (str(r.get('Verified data flags','')).replace('None','').strip(), r['V3.8 flags']) if x), axis=1)
    frame['Evidence URLs'] = frame.apply(lambda r: ' | '.join(x for x in (str(r.get('Evidence URLs','')).strip(), str(r.get('V3.8 source','')).strip()) if x and x != 'nan'), axis=1)
    return frame
