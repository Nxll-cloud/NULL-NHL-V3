"""V5.6 next-goal backtest: replay a past slate's official play-by-play through the live model, goal by goal.

No lookahead: for every goal the model sees only the shot events strictly before it (``ng.truncate``), the clock at
the goal, and the manpower/goalie state the goal was scored in (situationCode, known before the shot). Priors come
from each dressed skater's game log filtered to games dated BEFORE the slate (season stats as of the prior day).

  python backtest_next_goal.py --date 2026-04-04            # first run writes backtests/baseline_v56.json
  python backtest_next_goal.py --date 2026-04-04            # later runs print deltas; the baseline is never touched
  python backtest_next_goal.py --date 2026-04-04 --reset-baseline   # the ONLY way to replace the baseline
  python backtest_next_goal.py --baseline-only              # print the stored baseline headline
  python backtest_next_goal.py --lines my_openers.csv ...   # opening anytime lines (template: backtests/opening_lines_template.csv)

Network is used only by the default fetcher (api-web.nhle.com); every function takes an injectable ``getter`` and tests
run fully offline. Raw downloads are cached under data/backtest_cache/ (gitignored).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import live_nextgoal_v56 as ng

BACKTEST_VERSION = 'bt-1'
MODEL_VERSION = 'V5.6 next-goal (live_nextgoal_v56)'
ROOT = Path(__file__).resolve().parent
BASELINE_PATH = ROOT / 'backtests' / 'baseline_v56.json'
CACHE_DIR = ROOT / 'data' / 'backtest_cache'
API = 'https://api-web.nhle.com/v1'
KS = (1, 3, 5)
BUCKETS = (0.0, 0.02, 0.05, 0.10, 0.15, 0.25, 1.0001)
ANY_BUCKETS = (0.0, 0.10, 0.20, 0.30, 0.40, 1.0001)
REBOUND_SECS = 3
EARLY_SOG = 10          # "early game / few shots": fewer than this many combined SOG before the goal
LINE_COLUMNS = ['date', 'game_id', 'player', 'player_id', 'team', 'book', 'side', 'american_odds', 'timestamp']


class BaselineExists(RuntimeError):
    pass


# ---------------------------------------------------------------- fetching (network only here)
def http_getter(url, timeout=20):
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'NullsPlaybook-backtest/5.6'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def cached(getter, cache_dir=None):
    """Wrap a getter with a JSON file cache keyed by URL."""
    if cache_dir is None:
        return getter
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    def get(url):
        f = cache_dir / (hashlib.sha1(url.encode()).hexdigest()[:16] + '.json')
        if f.exists():
            return json.loads(f.read_text())
        data = getter(url)
        f.write_text(json.dumps(data))
        return data
    return get


def season_for(date):
    y, m = int(date[:4]), int(date[5:7])
    start = y if m >= 7 else y - 1
    return f'{start}{start + 1}'


def slate_game_ids(date, getter):
    sched = getter(f'{API}/schedule/{date}')
    for day in sched.get('gameWeek') or []:
        if day.get('date') == date:
            return [g['id'] for g in day.get('games') or [] if g.get('gameType') == 2]
    return []


def fetch_slate(date, getter, workers=8):
    """-> (pbp payloads, {pid: game log rows}) for every regular-season game on ``date``."""
    ids = slate_game_ids(date, getter)
    with ThreadPoolExecutor(workers) as ex:
        payloads = list(ex.map(lambda gid: getter(f'{API}/gamecenter/{gid}/play-by-play'), ids))
    season = season_for(date)
    pids = sorted({int(s['playerId']) for p in payloads for s in p.get('rosterSpots') or [] if s.get('positionCode') != 'G'})

    def log(pid):
        try:
            return pid, (getter(f'{API}/player/{pid}/game-log/{season}/2') or {}).get('gameLog') or []
        except Exception:  # noqa: BLE001 - a missing log just means a league-mean prior
            return pid, []
    with ThreadPoolExecutor(workers) as ex:
        logs = dict(ex.map(log, pids))
    return payloads, logs


# ---------------------------------------------------------------- priors (strictly before the slate date)
def priors_as_of(logs, roster, date, mode='season'):
    """Priors from game logs, using only games with gameDate < date.

    mode='season': season-to-date SOG/GP (the backtest headline).  mode='app_l10': what the app's
    ``ng.priors_from_rankings`` builds from rankings rows -- SOG = (Shots/G over the last 10 games) x GP."""
    out = {}
    for pid, rows in (logs or {}).items():
        pid = int(pid)
        prev = sorted((r for r in rows or [] if str(r.get('gameDate', '')) < date), key=lambda r: str(r.get('gameDate', '')))
        ro = roster.get(pid) or {}
        sog = float(sum(int(r.get('shots') or 0) for r in prev))
        if mode == 'app_l10' and prev:
            last = prev[-10:]
            sog = sum(int(r.get('shots') or 0) for r in last) / len(last) * len(prev)
        out[pid] = {'name': ro.get('name', str(pid)), 'team': ro.get('team', ''), 'pos': ro.get('pos', ''),
                    'gp': float(len(prev)), 'goals': sum(int(r.get('goals') or 0) for r in prev),
                    'sog': sog, 'form': None, 'source': 'season-to-date' if mode == 'season' else 'app-L10'}
    return out


# ---------------------------------------------------------------- replay
def _situations(payload):
    return {p.get('eventId'): p.get('situationCode') for p in payload.get('plays') or []}


def goal_moments(payload):
    """Yield (goal event, game state just before it) for every non-shootout goal, in order."""
    game = ng.parse_pbp(payload)
    sits = _situations(payload)
    for i, e in enumerate(game['events']):
        if e['kind'] != 'goal':
            continue
        g = ng.truncate(game, i)
        g.update(state='LIVE', period=e['period'], ptype=e['ptype'], intermission=False,
                 secs_remaining=max(0, (ng.OT_MINUTES * 60 if e['ptype'] == 'OT' else 1200) - e['secs']),
                 situation=sits.get(e['eid']) or '1551')
        yield i, e, g, game


def _rank_of(players, pid):
    for i, p in enumerate(players, 1):
        if p['pid'] == pid:
            return i
    return None


def _sog_leader_order(players):
    def spg(p):
        return (p.get('season_sog') or 0.0) / p['gp'] if p.get('gp') else 0.0
    return sorted(players, key=lambda p: (-spg(p), p['name']))


def _rebound(game, i, e):
    for prev in reversed(game['events'][:i]):
        if prev['period'] != e['period'] or e['secs'] - prev['secs'] > REBOUND_SECS:
            return False
        if prev['team'] == e['team'] and prev['kind'] in ('sog', 'miss', 'goal'):
            return True
    return False


def replay_game(payload, priors):
    """Per-goal records plus a pregame record for one game."""
    game0 = ng.parse_pbp(payload)
    pre = ng.model(ng.pregame_game(game0['game_id'], game0['away'], game0['home']) | {'roster': game0['roster']}, priors)
    scorers = {}
    for e in game0['events']:
        if e['kind'] == 'goal':
            scorers[e['shooter']] = scorers.get(e['shooter'], 0) + 1
    pre_rows = [{'pid': p['pid'], 'name': p['name'], 'team': p['team'], 'lam': round(p['lam_game'], 4),
                 'p_any': round(ng.p_anytime(p['lam_game']), 4), 'scored': p['pid'] in scorers} for p in pre['players']]
    pre_rows.sort(key=lambda r: (-r['lam'], r['name']))
    sog_lead = _sog_leader_order(pre['players'])[0] if pre['players'] else None
    records = []
    for i, e, g, full in goal_moments(payload):
        res = ng.model(g, priors)
        ps = res['players']
        if not ps:
            continue
        p_any = res['p_any'] or 1e-12
        team_ps = [p for p in ps if p['team'] == e['team']]
        sog_order = _sog_leader_order(ps)
        sog_team = [p for p in sog_order if p['team'] == e['team']]
        rank = _rank_of(ps, e['shooter'])
        scorer = next((p for p in ps if p['pid'] == e['shooter']), None)
        lead_before = (g['home_score'] or 0) - (g['away_score'] or 0)
        diff_for = lead_before if e['team'] == g['home'] else -lead_before
        records.append({
            'game_id': g['game_id'], 'matchup': f"{g['away']}@{g['home']}", 'period': e['period'], 'ptype': e['ptype'],
            'time': f"{e['secs'] // 60:02d}:{e['secs'] % 60:02d}", 'score_before': f"{g['away_score']}-{g['home_score']}",
            'scoring_team_diff': diff_for, 'strength': e['strength'], 'situation': g['situation'],
            'game_sog_before': (g['away_sog'] or 0) + (g['home_sog'] or 0),
            'top': ps[0]['name'], 'top_team': ps[0]['team'], 'top_q': round(ps[0]['p_next'] / p_any, 4),
            'team_top': team_ps[0]['name'] if team_ps else None,
            'team_top_q': round(team_ps[0]['p_next'] / p_any, 4) if team_ps else None,
            'scorer': scorer['name'] if scorer else str(e['shooter']), 'scorer_id': e['shooter'],
            'scorer_pos': ng.pos_group(scorer['pos']) if scorer else '?',
            'rank': rank, 'team_rank': _rank_of(team_ps, e['shooter']),
            'q': round(scorer['p_next'] / p_any, 5) if scorer else 0.0,
            'brier': round(sum((p['p_next'] / p_any - (p['pid'] == e['shooter'])) ** 2 for p in ps)
                           + (0 if scorer else 1), 5),
            'n': len(ps), 'n_team': len(team_ps),
            'sog_rank': _rank_of(sog_order, e['shooter']), 'sog_team_rank': _rank_of(sog_team, e['shooter']),
            'sog_q': round(_sog_share(ps, e['shooter']), 5),
            'rebound': _rebound(full, i, e),
            '_qs': [round(p['p_next'] / p_any, 5) for p in ps], '_ys': [p['pid'] == e['shooter'] for p in ps]})
    return {'game_id': game0['game_id'], 'matchup': f"{game0['away']}@{game0['home']}",
            'final': f"{game0['away_score']}-{game0['home_score']}", 'n_goals': len(records),
            'pre_top': pre_rows[0] if pre_rows else None,
            'pre_top_by_team': {t: next((r for r in pre_rows if r['team'] == t), None) for t in (game0['away'], game0['home'])},
            'sog_leader': ({'name': sog_lead['name'], 'scored': sog_lead['pid'] in scorers} if sog_lead else None),
            '_pre_rows': pre_rows}, records


def _sog_share(ps, pid):
    w = [((p.get('season_sog') or 0.0) + 1.0) / ((p.get('gp') or 0.0) + 1.0) for p in ps]
    tot = sum(w) or 1.0
    for p, x in zip(ps, w):
        if p['pid'] == pid:
            return x / tot
    return 0.0


# ---------------------------------------------------------------- metrics
def _rate(xs):
    xs = list(xs)
    return round(sum(xs) / len(xs), 4) if xs else None


def calibration(pairs, edges=BUCKETS):
    out = []
    for lo, hi in zip(edges, edges[1:]):
        sel = [(q, y) for q, y in pairs if lo <= q < hi]
        if sel:
            out.append({'bucket': f'{lo:.0%}-{min(hi, 1):.0%}', 'n': len(sel), 'mean_pred': round(sum(q for q, _ in sel) / len(sel), 4),
                        'observed': round(sum(y for _, y in sel) / len(sel), 4)})
    return out


def flags(r):
    late = (r['ptype'] == 'REG' and r['period'] == 3 and r['time'] >= '15:00') or r['ptype'] == 'OT'
    return {'blowout (lead>=3 before goal)': abs(r['scoring_team_diff']) >= 3, 'late (P3 last 5 min / OT)': late,
            'empty net': r['strength'] == 'EN', 'power play': r['strength'] == 'PP', 'shorthanded': r['strength'] == 'SH',
            f'early (<{EARLY_SOG} game SOG)': r['game_sog_before'] < EARLY_SOG, 'defenceman scorer': r['scorer_pos'] == 'D',
            'rebound (<=3 s)': bool(r['rebound']), 'even strength': r['strength'] == 'EV'}


def summarize(games, records):
    n = len(records)
    head = {'goals': n, 'games': len(games)}
    for k in KS:
        head[f'game_top{k}'] = _rate(r['rank'] is not None and r['rank'] <= k for r in records)
        head[f'team_top{k}'] = _rate(r['team_rank'] is not None and r['team_rank'] <= k for r in records)
        head[f'sog_game_top{k}'] = _rate(r['sog_rank'] is not None and r['sog_rank'] <= k for r in records)
        head[f'sog_team_top{k}'] = _rate(r['sog_team_rank'] is not None and r['sog_team_rank'] <= k for r in records)
        head[f'rand_game_top{k}'] = _rate(min(1.0, k / r['n']) for r in records)
        head[f'rand_team_top{k}'] = _rate(min(1.0, k / max(1, r['n_team'])) for r in records)
    head['brier'] = _rate(r['brier'] for r in records)
    head['log_loss'] = _rate(-math.log(max(r['q'], 1e-6)) for r in records)
    head['log_loss_uniform'] = _rate(math.log(r['n']) for r in records)
    head['log_loss_sog_share'] = _rate(-math.log(max(r['sog_q'], 1e-6)) for r in records)
    head['brier_uniform'] = _rate((1 - 1 / r['n']) for r in records)
    pre_top = [g['pre_top']['scored'] for g in games if g.get('pre_top')]
    head['games_pregame_top1_scored'] = _rate(pre_top)
    head['games_sog_leader_scored'] = _rate(g['sog_leader']['scored'] for g in games if g.get('sog_leader'))
    team_tops = [r['scored'] for g in games for r in (g['pre_top_by_team'] or {}).values() if r]
    head['teams_pregame_top1_scored'] = _rate(team_tops)
    pairs = [(q, y) for r in records for q, y in zip(r['_qs'], r['_ys'])]
    any_pairs = [(row['p_any'], row['scored']) for g in games for row in g['_pre_rows']]
    head['anytime_brier'] = _rate((p - y) ** 2 for p, y in any_pairs)
    misses = [r for r in records if r['rank'] != 1]
    patterns = []
    for name in flags(records[0]) if records else []:
        sel = [r for r in records if flags(r)[name]]
        if sel:
            patterns.append({'pattern': name, 'goals': len(sel), 'top1': _rate(r['rank'] == 1 for r in sel),
                             'top3': _rate((r['rank'] or 99) <= 3 for r in sel), 'team_top1': _rate(r['team_rank'] == 1 for r in sel),
                             'median_rank': sorted(r['rank'] or 99 for r in sel)[len(sel) // 2],
                             'share_of_misses': round(sum(flags(r)[name] for r in misses) / max(1, len(misses)), 4)})
    return {'headline': head, 'calibration_next_goal': calibration(pairs), 'calibration_anytime': calibration(any_pairs, ANY_BUCKETS),
            'patterns': patterns}


def public_record(r):
    return {k: v for k, v in r.items() if not k.startswith('_')}


def code_hash():
    h = hashlib.sha256()
    for name in ('live_nextgoal_v56.py', 'backtest_next_goal.py'):
        h.update((ROOT / name).read_bytes())
    return h.hexdigest()[:16]


LINES_BLOCKED = ('blocked: no historical opening anytime-goal lines available (Odds API historical endpoint needs a paid key; '
                 'no CSV supplied). Supply one with --lines; template backtests/opening_lines_template.csv')


def run_backtest(date, getter=None, payloads=None, logs=None, cache_dir=CACHE_DIR, lines_path=None):
    """Run the backtest for ``date``. Pass ``payloads``/``logs`` (offline) or a ``getter``; default = cached HTTP."""
    if payloads is None or logs is None:
        getter = getter or cached(http_getter, cache_dir)
        payloads, logs = fetch_slate(date, getter)
    games, records, l10_games, l10_records = [], [], [], []
    for p in payloads:
        roster = ng.parse_pbp(p)['roster']
        plogs = {pid: logs.get(pid) or logs.get(str(pid)) or [] for pid in roster}
        g, recs = replay_game(p, priors_as_of(plogs, roster, date))
        games.append(g)
        records.extend(recs)
        g2, recs2 = replay_game(p, priors_as_of(plogs, roster, date, mode='app_l10'))
        l10_games.append(g2)
        l10_records.extend(recs2)
    s = summarize(games, records)
    s['headline_app_l10_priors'] = summarize(l10_games, l10_records)['headline']
    if lines_path:
        market = {(str(k[0]), k[1]): v for k, v in devig(load_opening_lines(lines_path)).items()}
        lines = compare_lines(games, {g['game_id']: g['_pre_rows'] for g in games}, market)
    else:
        lines = {'status': LINES_BLOCKED, 'n': 0, 'rows': []}
    return {'lines': lines, 'backtest_version': BACKTEST_VERSION, 'model_version': MODEL_VERSION, 'code_hash': code_hash(), 'slate_date': date,
            'season': season_for(date), 'priors': 'season-to-date game logs, games dated before slate_date; Form off',
            **s, 'games': [{k: v for k, v in g.items() if not k.startswith('_')} for g in games],
            'records': [public_record(r) for r in records]}


# ---------------------------------------------------------------- baseline store (write-once)
def load_baseline(path=BASELINE_PATH):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else None


def save_baseline(result, path=BASELINE_PATH, reset=False):
    """Write ``result`` as the baseline. Refuses if one exists unless reset=True. Returns True when written."""
    path = Path(path)
    if path.exists() and not reset:
        raise BaselineExists(f'{path} exists; pass --reset-baseline to replace it')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, separators=(',', ':'), sort_keys=True))
    os.replace(tmp, path)
    return True


def compare(result, baseline):
    """Numeric headline deltas (result - baseline) for every shared metric."""
    if not baseline:
        return {}
    a, b = result.get('headline') or {}, baseline.get('headline') or {}
    out = {}
    for k in sorted(set(a) & set(b)):
        if isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)):
            out[k] = {'now': a[k], 'baseline': b[k], 'delta': round(a[k] - b[k], 4)}
    out['_meta'] = {'same_slate': result.get('slate_date') == baseline.get('slate_date'),
                    'same_code': result.get('code_hash') == baseline.get('code_hash')}
    return out


def run_and_compare(result, path=BASELINE_PATH, reset=False):
    """First run (no baseline) or reset -> write. Otherwise leave the file untouched and return deltas."""
    base = load_baseline(path)
    if base is None or reset:
        save_baseline(result, path, reset=reset)
        return {'written': True, 'deltas': {}}
    return {'written': False, 'deltas': compare(result, base)}


# ---------------------------------------------------------------- opening lines (CSV import, vig removal, comparison)
def implied(odds):
    o = float(odds)
    if o == 0 or -100 < o < 100:
        raise ValueError(f'invalid American odds {odds!r}')
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def load_opening_lines(path):
    """CSV with LINE_COLUMNS (side = yes/no). Keeps the EARLIEST timestamp per (game, player, book, side)."""
    rows = {}
    with open(path, newline='', encoding='utf-8') as fh:
        rd = csv.DictReader(fh)
        missing = [c for c in ('date', 'player', 'book', 'side', 'american_odds') if c not in (rd.fieldnames or [])]
        if missing:
            raise ValueError(f'opening-lines CSV missing columns: {missing}')
        for r in rd:
            if str(r.get('date', '')).startswith('#'):
                continue
            key = (r.get('game_id') or r['date'], (r.get('player_id') or r['player']).strip().lower(), r['book'].strip(), r['side'].strip().lower())
            if key not in rows or str(r.get('timestamp') or '') < str(rows[key].get('timestamp') or ''):
                rows[key] = r
    return list(rows.values())


def devig(lines):
    """-> {(game, player key): {'p': implied yes prob averaged over books, 'two_sided': bool, 'books': n, 'player': name}}."""
    by = {}
    for r in lines:
        k = (r.get('game_id') or r['date'], (r.get('player_id') or r['player']).strip().lower())
        by.setdefault(k, {}).setdefault(r['book'].strip(), {})[r['side'].strip().lower()] = r
    out = {}
    for k, books in by.items():
        ps, two = [], True
        name = ''
        for sides in books.values():
            y, n = sides.get('yes'), sides.get('no')
            if not y:
                continue
            name = y['player']
            py = implied(y['american_odds'])
            if n:
                pn = implied(n['american_odds'])
                ps.append(py / (py + pn))
            else:
                ps.append(py)
                two = False
        if ps:
            out[k] = {'p': sum(ps) / len(ps), 'two_sided': two, 'books': len(ps), 'player': name}
    return out


def compare_lines(result_games, pre_rows_by_game, market):
    """Model pregame P(anytime) vs vig-removed opening implied probability for every player with a line."""
    rows = []
    for g in result_games:
        for r in pre_rows_by_game.get(g['game_id'], []):
            m = market.get((str(g['game_id']), str(r['pid']))) or market.get((str(g['game_id']), r['name'].lower()))
            if m:
                rows.append({'game_id': g['game_id'], 'player': r['name'], 'model_p': r['p_any'], 'market_p': round(m['p'], 4),
                             'edge': round(r['p_any'] - m['p'], 4), 'two_sided': m['two_sided'], 'scored': r['scored']})
    if not rows:
        return {'status': 'no matching lines', 'n': 0, 'rows': []}
    bm = _rate((x['model_p'] - x['scored']) ** 2 for x in rows)
    bk = _rate((x['market_p'] - x['scored']) ** 2 for x in rows)
    pos = [x for x in rows if x['edge'] > 0]
    return {'status': 'ok', 'n': len(rows), 'brier_model': bm, 'brier_market': bk,
            'positive_edge_n': len(pos), 'positive_edge_hit': _rate(x['scored'] for x in pos),
            'positive_edge_market_p': _rate(x['market_p'] for x in pos), 'rows': rows}


# ---------------------------------------------------------------- CLI
def _fmt(h):
    lines = [f"goals {h['goals']} in {h['games']} games"]
    for k in KS:
        lines.append(f"top-{k}: game {h[f'game_top{k}']:.1%} (SOG/G leader {h[f'sog_game_top{k}']:.1%}, random {h[f'rand_game_top{k}']:.1%})"
                     f" | team {h[f'team_top{k}']:.1%} (SOG/G {h[f'sog_team_top{k}']:.1%}, random {h[f'rand_team_top{k}']:.1%})")
    lines.append(f"brier {h['brier']} (uniform {h['brier_uniform']}) | log loss {h['log_loss']} (uniform {h['log_loss_uniform']}, SOG-share {h['log_loss_sog_share']})")
    lines.append(f"pregame top-1 scored in {h['games_pregame_top1_scored']:.1%} of games (SOG/G leader {h['games_sog_leader_scored']:.1%}); per team {h['teams_pregame_top1_scored']:.1%}")
    return '\n'.join(lines)


def main(argv=None, getter=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--date', default=None)
    ap.add_argument('--baseline', default=str(BASELINE_PATH))
    ap.add_argument('--reset-baseline', action='store_true', help='replace the stored baseline (otherwise it is never overwritten)')
    ap.add_argument('--baseline-only', action='store_true')
    ap.add_argument('--lines', default=None, help='opening-lines CSV (see backtests/opening_lines_template.csv)')
    ap.add_argument('--json', default=None, help='also write this run to a file (never the baseline path)')
    a = ap.parse_args(argv)
    base = load_baseline(a.baseline)
    if a.baseline_only:
        print(_fmt(base['headline']) if base else 'no baseline stored')
        return 0
    date = a.date or (base or {}).get('slate_date')
    if not date:
        ap.error('--date is required when no baseline exists')
    result = run_backtest(date, getter=getter, lines_path=a.lines)
    print(f'slate {date} | code {result["code_hash"]}')
    print(_fmt(result['headline']))
    print('opening-line comparison:', json.dumps({k: v for k, v in result['lines'].items() if k != 'rows'}))
    if a.json and Path(a.json).resolve() != Path(a.baseline).resolve():
        Path(a.json).write_text(json.dumps(result, separators=(',', ':')))
    out = run_and_compare(result, a.baseline, reset=a.reset_baseline)
    if out['written']:
        print(f'baseline written: {a.baseline}')
    else:
        print('baseline unchanged; deltas vs baseline:')
        for k, v in out['deltas'].items():
            if k != '_meta' and v['delta']:
                print(f"  {k}: {v['baseline']} -> {v['now']} ({v['delta']:+})")
        print('  meta:', out['deltas'].get('_meta'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
