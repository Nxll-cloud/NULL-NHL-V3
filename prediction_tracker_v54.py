"""V5.4 prediction tracking & learning.

Storage: one local SQLite file (stdlib ``sqlite3``). Default path is
``data/prediction_tracker_v54.sqlite`` next to this module (``data/`` is
gitignored); override with the ``PLAYBOOK_TRACKER_DB`` environment variable or
the ``path`` argument. The schema is created on first use and every write is a
single SQLite transaction (atomic: all rows or none).

Streamlit Community Cloud has an EPHEMERAL filesystem: the file is lost on
reboot/redeploy. Use the Track Record tab's JSON export/import to keep history.

Definitions (also in V54_NOTES.md):
* Pick: a player the app predicted to score — the four Home leaders
  (Stats / Numbers / Odds / Overlap sources), the statistical top-N
  (default N=10, source Stats) and the gematria top-5 (source Numbers).
* Watch band: statistical ranks N+1..N+5 are stored with ``is_pick=0``.
* Evaluated game: a game whose results were saved as final. A slate with no
  final game is PENDING and excluded from every rate.
* Hit: a pick who scored >= 1 goal. Miss: a pick who did not score.
* Unpredicted scorer: a scorer in an evaluated game who was not a pick.
* Near-miss: (a) a watch-band player who scored, or (b) a pick who did not
  score but recorded an assist (when assists are known).
* Hit rate = hits / (hits + misses) over unique picks in evaluated games.

Learning (bounded, conservative): for player i with n evaluated picks and k
hits, prior p0 = pooled pick hit rate over all evaluated history (0.25 before
20 evaluated picks), prior strength m = 10:
    shrunk_i = (k + m * p0) / (n + m)
    adj_i    = clamp(0.5 * (shrunk_i - p0) / p0, -CAP, +CAP), CAP = 0.05
             = 0 when n < MIN_SAMPLE (3)
    adjusted score = form score * (1 + adj_i)
Badges: 'Hot when predicted' if n >= 3, k >= 2 and shrunk >= 1.25 * p0;
'Keeps missing' if n >= 3 and (k == 0 or shrunk <= 0.75 * p0).
Rankings change only when the user enables the toggle (default OFF).
"""
from __future__ import annotations

import json
import re
import math
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from odds_intelligence_v46 import normalized_name

DEFAULT_DB = Path(__file__).resolve().parent / 'data' / 'prediction_tracker_v54.sqlite'
SOURCES = ('Stats', 'Numbers', 'Odds', 'Overlap')
PICK_CUTOFF = 10
WATCH_BAND = 5
NUMBERS_PICKS = 5
PRIOR_RATE = 0.25
PRIOR_STRENGTH = 10
MIN_SAMPLE = 3
ADJ_CAP = 0.05
MIN_POOL = 20
# Audit P1.4: a naive shots-share baseline (top N by recent shots per game) is saved with every slate and graded
# next to the picks. It is a comparison line only: never a pick, never in hit rates, near-misses or learning.
BASELINE_SOURCE = 'Shots baseline'
BASELINE_N = 10
BASELINE_COLS = ('Shots/G L10', 'Shots/G L5')

SCHEMA = """
CREATE TABLE IF NOT EXISTS slates(
  day TEXT PRIMARY KEY, locked INTEGER NOT NULL DEFAULT 0, locked_at TEXT, retro INTEGER NOT NULL DEFAULT 0,
  n_games INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS predictions(
  day TEXT NOT NULL, player_key TEXT NOT NULL, source TEXT NOT NULL, player_id TEXT, player TEXT NOT NULL,
  norm_name TEXT NOT NULL, team TEXT, game_id TEXT, rank INTEGER, score REAL, is_pick INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, PRIMARY KEY(day, player_key, source));
CREATE TABLE IF NOT EXISTS actuals(
  day TEXT NOT NULL, game_id TEXT NOT NULL, player_key TEXT NOT NULL, player_id TEXT, player TEXT NOT NULL,
  norm_name TEXT NOT NULL, team TEXT, goals INTEGER NOT NULL DEFAULT 0, assists INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL, PRIMARY KEY(day, game_id, player_key));
CREATE TABLE IF NOT EXISTS game_results(
  day TEXT NOT NULL, game_id TEXT NOT NULL, final INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL,
  updated_at TEXT NOT NULL, PRIMARY KEY(day, game_id));
"""


class TrackerError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def db_path(path=None):
    return Path(path or os.environ.get('PLAYBOOK_TRACKER_DB') or DEFAULT_DB)


def connect(path=None):
    p = db_path(path)
    if str(p) != ':memory:':
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _clean_id(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ''
    text = str(value).strip()
    if text.endswith('.0'):
        text = text[:-2]
    return text if text.isdigit() else ''


def player_key(player_id, name):
    pid = _clean_id(player_id)
    if pid:
        return 'id:' + pid
    norm = normalized_name(name or '')
    if not norm:
        raise TrackerError('A player needs an NHL id or a name.')
    return 'nm:' + norm


def _num(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


# ---------------------------------------------------------------- predictions

def team_game_map(games):
    out = {}
    for g in games or []:
        if not isinstance(g, dict):
            continue
        gid = _clean_id(g.get('Game ID') or g.get('game_id') or g.get('id'))
        for side in ('Away', 'Home', 'away', 'home'):
            code = str(g.get(side) or '').upper()
            if code and gid:
                out[code] = gid
    return out


def build_prediction_rows(ranked, leaders=None, games=None, gematria=None, cutoff=PICK_CUTOFF, band=WATCH_BAND, baseline_n=BASELINE_N):
    """Collect the slate's predictions. Pure; returns a list of dicts."""
    tg = team_game_map(games)
    rows = []

    def add(pid, name, team, source, rank, score, is_pick=1):
        try:
            key = player_key(pid, name)
        except TrackerError:
            return
        team = str(team or '').upper()
        rows.append({'player_key': key, 'source': source, 'player_id': _clean_id(pid), 'player': str(name),
                     'norm_name': normalized_name(name or ''), 'team': team, 'game_id': tg.get(team, ''),
                     'rank': None if rank is None else int(rank), 'score': _num(score), 'is_pick': int(is_pick)})

    if isinstance(ranked, pd.DataFrame) and not ranked.empty and 'Statistical rank' in ranked:
        r = ranked.copy()
        r['_rank'] = pd.to_numeric(r['Statistical rank'], errors='coerce')
        r = r[r['_rank'].notna()].sort_values('_rank')
        for _, p in r.head(cutoff + band).iterrows():
            add(p.get('Player ID'), p.get('Player'), p.get('Team'), 'Stats', p['_rank'], p.get('V3.2 Adjusted Index'),
                is_pick=1 if p['_rank'] <= cutoff else 0)
        col = next((c for c in BASELINE_COLS if c in ranked), None)
        if col and baseline_n:
            b = r.copy()   # the same ranked (eligible) skaters, re-ordered by shots per game alone
            b['_sog'] = pd.to_numeric(b[col], errors='coerce')
            b = b[b['_sog'].notna()].sort_values(['_sog', '_rank'], ascending=[False, True])
            for i, (_, p) in enumerate(b.head(baseline_n).iterrows(), 1):
                add(p.get('Player ID'), p.get('Player'), p.get('Team'), BASELINE_SOURCE, i, p['_sog'], is_pick=0)
    for i, p in enumerate((gematria or [])[:NUMBERS_PICKS], 1):
        add(p.get('player_id'), p.get('player'), p.get('team'), 'Numbers', i, p.get('matches'))
    source_of = {'statistical': 'Stats', 'gematria': 'Numbers', 'odds': 'Odds', 'overlap': 'Overlap'}
    for key, source in source_of.items():
        p = (leaders or {}).get(key)
        if p:
            score = p.get('gap_pct') if key == 'odds' else (p.get('matches') if key == 'gematria' else p.get('form'))
            add(p.get('player_id'), p.get('player'), p.get('team'), source, 0, score)  # rank 0 = category leader
    # Same player + source twice (e.g. leader and top-N): keep the leader (rank 0) row.
    best = {}
    for row in rows:
        k = (row['player_key'], row['source'])
        if k not in best or (row['rank'] or 0) < (best[k]['rank'] or 0) or row['is_pick'] > best[k]['is_pick']:
            best[k] = row
    return list(best.values())


def slate_info(conn, day):
    r = conn.execute('SELECT * FROM slates WHERE day=?', (day,)).fetchone()
    return dict(r) if r else None


def save_predictions(conn, day, rows, n_games=0, lock=False, retro=False, demo=False):
    """Idempotent per (day, player, source). Locked slates are never modified.

    Returns dict(status='saved'|'locked'|'empty', saved=int, locked=bool)."""
    info = slate_info(conn, day)
    if info and info['locked']:
        return {'status': 'locked', 'saved': 0, 'locked': True}
    rows = list(rows or [])
    if not rows:
        return {'status': 'empty', 'saved': 0, 'locked': bool(info and info['locked'])}
    now = _now()
    with conn:  # one transaction: replace this unlocked slate's predictions atomically
        conn.execute('INSERT INTO slates(day, locked, retro, n_games, created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?) '
                     'ON CONFLICT(day) DO UPDATE SET n_games=excluded.n_games, updated_at=excluded.updated_at, retro=excluded.retro',
                     (day, 0, int(retro), int(n_games), now, now, int(demo)))
        conn.execute('DELETE FROM predictions WHERE day=?', (day,))
        conn.executemany('INSERT INTO predictions(day, player_key, source, player_id, player, norm_name, team, game_id, rank, score, is_pick, created_at) '
                         'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                         [(day, r['player_key'], r['source'], r['player_id'], r['player'], r['norm_name'], r['team'],
                           r['game_id'], r['rank'], r['score'], r['is_pick'], now) for r in rows])
        if lock:
            conn.execute('UPDATE slates SET locked=1, locked_at=? WHERE day=?', (now, day))
    return {'status': 'saved', 'saved': len(rows), 'locked': bool(lock)}


def lock_slate(conn, day):
    info = slate_info(conn, day)
    if not info:
        raise TrackerError('Save predictions for this slate before locking.')
    if info['locked']:
        return False
    with conn:
        conn.execute('UPDATE slates SET locked=1, locked_at=? WHERE day=?', (_now(), day))
    return True


def predictions(conn, day=None):
    q = 'SELECT * FROM predictions' + (' WHERE day=?' if day else '') + ' ORDER BY day, source, rank'
    return pd.DataFrame([dict(r) for r in conn.execute(q, (day,) if day else ())])


# ---------------------------------------------------------------- actuals

def resolve_names(names, roster):
    """Free-text names -> (matched roster dicts, unmatched names). Normalized, unique matches only."""
    index = {}
    for p in roster or []:
        index.setdefault(normalized_name(p.get('player', '')), []).append(p)
    matched, unmatched = [], []
    for raw in names or []:
        raw = str(raw).strip()
        if not raw:
            continue
        hits = index.get(normalized_name(raw), [])
        if len(hits) == 1:
            matched.append(hits[0])
        else:
            unmatched.append(raw)
    return matched, unmatched


def record_game_results(conn, day, game_id, scorers, source='manual', final=True):
    """Replace one game's actuals. ``scorers``: dicts with player, player_id, team, goals, assists.

    Duplicate entries for one player are merged (goals/assists summed)."""
    gid = _clean_id(game_id) or str(game_id or '').strip()
    if not gid:
        raise TrackerError('game_id is required')
    merged = {}
    for s in scorers or []:
        try:
            key = player_key(s.get('player_id'), s.get('player'))
        except TrackerError:
            continue
        cur = merged.setdefault(key, {'player_id': _clean_id(s.get('player_id')), 'player': str(s.get('player') or ''),
                                      'team': str(s.get('team') or '').upper(), 'goals': 0, 'assists': 0})
        cur['goals'] += max(int(_num(s.get('goals', 1)) or 0), 0)
        cur['assists'] += max(int(_num(s.get('assists', 0)) or 0), 0)
    now = _now()
    with conn:
        conn.execute('DELETE FROM actuals WHERE day=? AND game_id=?', (day, gid))
        conn.executemany('INSERT INTO actuals(day, game_id, player_key, player_id, player, norm_name, team, goals, assists, source) VALUES(?,?,?,?,?,?,?,?,?,?)',
                         [(day, gid, k, v['player_id'], v['player'], normalized_name(v['player']), v['team'], v['goals'], v['assists'], source)
                          for k, v in merged.items()])
        conn.execute('INSERT INTO game_results(day, game_id, final, source, updated_at) VALUES(?,?,?,?,?) '
                     'ON CONFLICT(day, game_id) DO UPDATE SET final=excluded.final, source=excluded.source, updated_at=excluded.updated_at',
                     (day, gid, int(bool(final)), source, now))
    return len(merged)


def _event_get(ev, name, default=None):
    return getattr(ev, name, None) if not isinstance(ev, dict) else ev.get(name, default)


def events_to_scorers(events):
    """GoalEvent list (live_scoring_future) -> {game_id: [scorer dicts]}, deduped by event key."""
    from live_scoring_future import GoalEvent, dedupe_events
    norm = []
    for ev in events or []:
        if isinstance(ev, dict):
            try:
                ev = GoalEvent(**{k: ev[k] for k in ev if k in GoalEvent.__dataclass_fields__})
            except TypeError:
                continue
        if isinstance(ev, GoalEvent):
            norm.append(ev)
    per_game = {}
    for ev in dedupe_events(norm):
        game = per_game.setdefault(str(ev.game_id), {})
        k = (ev.scorer_id or '', ev.scorer)
        game.setdefault(k, {'player': ev.scorer, 'player_id': ev.scorer_id, 'team': ev.team, 'goals': 0, 'assists': 0})['goals'] += 1
        for name, pid in ev.assists or ():
            a = game.setdefault((pid or '', name), {'player': name, 'player_id': pid, 'team': ev.team, 'goals': 0, 'assists': 0})
            a['assists'] += 1
    return {g: list(v.values()) for g, v in per_game.items()}


def ingest_goal_events(conn, day, events, final=False, source='live'):
    """Entry point for the future live scoring module: GoalEvent list -> actuals per game."""
    total = 0
    for gid, scorers in events_to_scorers(events).items():
        total += record_game_results(conn, day, gid, scorers, source=source, final=final)
    return total


def parse_landing_goals(payload, game_id=None):
    """NHL api-web ``gamecenter/{id}/landing`` -> (list[GoalEvent], is_final)."""
    from live_scoring_future import GoalEvent
    if not isinstance(payload, dict):
        raise TrackerError('Unexpected NHL response')
    gid = str(game_id or payload.get('id') or '')
    out = []
    scoring = ((payload.get('summary') or {}).get('scoring')) or []
    for period in scoring if isinstance(scoring, list) else []:
        pnum = int(_num(((period or {}).get('periodDescriptor') or {}).get('number')) or 0)
        for g in (period or {}).get('goals') or []:
            if not isinstance(g, dict):
                continue
            first = (g.get('firstName') or {}).get('default', '') if isinstance(g.get('firstName'), dict) else ''
            last = (g.get('lastName') or {}).get('default', '') if isinstance(g.get('lastName'), dict) else ''
            assists = tuple(((((a.get('firstName') or {}).get('default', '') + ' ' + (a.get('lastName') or {}).get('default', '')).strip(),
                              _clean_id(a.get('playerId')) or None) for a in g.get('assists') or [] if isinstance(a, dict)))
            out.append(GoalEvent(game_id=gid, period=pnum, time=str(g.get('timeInPeriod') or ''),
                                 team=str((g.get('teamAbbrev') or {}).get('default', '') if isinstance(g.get('teamAbbrev'), dict) else ''),
                                 scorer=(first + ' ' + last).strip() or 'Unknown', scorer_id=_clean_id(g.get('playerId')) or None,
                                 assists=assists, strength=str(g.get('strength') or 'ev'),
                                 event_id=str(g.get('eventId')) if g.get('eventId') is not None else None))
    return out, str(payload.get('gameState') or '') in ('OFF', 'FINAL')


def fetch_final_goals(game_id, fetch=None):
    """Network helper (button-driven in the app): official NHL final boxscore goals."""
    if fetch is None:
        from nhl_data import fetch_json as fetch
    try:
        payload = fetch(f'gamecenter/{_clean_id(game_id)}/landing')
    except Exception as exc:  # network/HTTP/JSON errors surface as one clean message
        raise TrackerError(f'NHL results unavailable for game {game_id}: {type(exc).__name__}') from exc
    return parse_landing_goals(payload, game_id)


def actuals(conn, day=None):
    q = 'SELECT * FROM actuals' + (' WHERE day=?' if day else '')
    return pd.DataFrame([dict(r) for r in conn.execute(q, (day,) if day else ())])


def final_games(conn, day):
    return {r['game_id'] for r in conn.execute('SELECT game_id FROM game_results WHERE day=? AND final=1', (day,))}


# ---------------------------------------------------------------- evaluation

def _match_actual(pred, by_id, by_name):
    if pred.get('player_id') and pred['player_id'] in by_id:
        return by_id[pred['player_id']]
    cands = by_name.get(pred.get('norm_name'), [])
    return cands[0] if len(cands) == 1 else None


def evaluate_slate(conn, day):
    """Hits / misses / unpredicted / near-misses for one slate (see module docstring)."""
    info = slate_info(conn, day)
    finals = final_games(conn, day)
    preds = [dict(r) for r in conn.execute('SELECT * FROM predictions WHERE day=?', (day,))]
    acts = [dict(r) for r in conn.execute('SELECT * FROM actuals WHERE day=?', (day,))]
    base = {'day': day, 'locked': bool(info and info['locked']), 'retro': bool(info and info['retro']),
            'demo': bool(info and info['demo']), 'final_games': len(finals), 'n_games': int(info['n_games']) if info else 0}
    if not finals:
        return {**base, 'status': 'pending', 'hits': [], 'misses': [], 'unpredicted': [], 'near_misses': [],
                'picks': 0, 'hit_rate': None, 'by_source': {}}
    slate_final = base['n_games'] > 0 and len(finals) >= base['n_games']
    acts = [a for a in acts if a['game_id'] in finals]
    by_id = {a['player_id']: a for a in acts if a['player_id']}
    by_name = {}
    for a in acts:
        by_name.setdefault(a['norm_name'], []).append(a)

    def in_scope(p):
        return p['game_id'] in finals if p['game_id'] else slate_final

    picks, watch, base_rows = {}, {}, {}
    for p in preds:
        if not in_scope(p):
            continue
        if p['source'] == BASELINE_SOURCE:   # comparison line only (audit P1.4)
            base_rows[p['player_key']] = p
            continue
        target = picks if p['is_pick'] else watch
        entry = target.setdefault(p['player_key'], {**p, 'sources': set()})
        entry['sources'].add(p['source'])
    for k in list(watch):
        if k in picks:
            watch.pop(k)
    hits, misses, near, matched_keys = [], [], [], set()
    by_source = {s: {'picks': 0, 'hits': 0} for s in SOURCES}
    for k, p in picks.items():
        a = _match_actual(p, by_id, by_name)
        scored = bool(a and a['goals'] > 0)
        if a:
            matched_keys.add(a['player_key'])  # this scorer was predicted
        rec = {'player': p['player'], 'player_key': k, 'team': p['team'], 'sources': sorted(p['sources']),
               'goals': a['goals'] if a else 0, 'assists': a['assists'] if a else 0}
        (hits if scored else misses).append(rec)
        if not scored and a and a['assists'] > 0:
            near.append({**rec, 'reason': 'Predicted · assist, no goal'})
        for s in p['sources']:
            if s in by_source:
                by_source[s]['picks'] += 1
                by_source[s]['hits'] += int(scored)
    for k, p in watch.items():
        a = _match_actual(p, by_id, by_name)
        if a and a['goals'] > 0:
            near.append({'player': p['player'], 'player_key': k, 'team': p['team'], 'sources': ['Stats'],
                         'goals': a['goals'], 'assists': a['assists'], 'reason': f'Ranked #{p["rank"]}, just outside the top {PICK_CUTOFF}'})
    bh = sum(1 for p in base_rows.values() if (lambda a: bool(a and a['goals'] > 0))(_match_actual(p, by_id, by_name)))
    baseline = {'picks': len(base_rows), 'hits': bh, 'rate': (bh / len(base_rows)) if base_rows else None}
    unpredicted = [{'player': a['player'], 'player_key': a['player_key'], 'team': a['team'], 'goals': a['goals']}
                   for a in acts if a['goals'] > 0 and a['player_key'] not in matched_keys]
    n = len(hits) + len(misses)
    return {**base, 'status': 'evaluated' if n else 'no_picks', 'hits': hits, 'misses': misses, 'unpredicted': unpredicted,
            'near_misses': near, 'picks': n, 'hit_rate': (len(hits) / n) if n else None, 'baseline': baseline,
            'by_source': {s: {**v, 'rate': (v['hits'] / v['picks']) if v['picks'] else None} for s, v in by_source.items()}}


def all_days(conn):
    return [r['day'] for r in conn.execute('SELECT day FROM slates UNION SELECT day FROM game_results ORDER BY day')]


def history(conn):
    return [evaluate_slate(conn, d) for d in all_days(conn)]


def rolling(evals, last_n=None):
    done = [e for e in evals if e['status'] == 'evaluated']
    done = sorted(done, key=lambda e: e['day'])
    if last_n:
        done = done[-last_n:]
    hits = sum(len(e['hits']) for e in done)
    picks = sum(e['picks'] for e in done)
    return {'slates': len(done), 'hits': hits, 'picks': picks, 'rate': (hits / picks) if picks else None}


def baseline_rollup(evals, last_n=None):
    """Shots-share baseline graded over the same evaluated slates (slates saved before it existed are skipped)."""
    done = sorted([e for e in evals if e['status'] == 'evaluated' and (e.get('baseline') or {}).get('picks')], key=lambda e: e['day'])
    if last_n:
        done = done[-last_n:]
    h, p = sum(e['baseline']['hits'] for e in done), sum(e['baseline']['picks'] for e in done)
    stats = [e for e in done if (e.get('by_source') or {}).get('Stats', {}).get('picks')]
    sh, sp = sum(e['by_source']['Stats']['hits'] for e in stats), sum(e['by_source']['Stats']['picks'] for e in stats)
    return {'slates': len(done), 'hits': h, 'picks': p, 'rate': (h / p) if p else None,
            'stats_rate_same_slates': (sh / sp) if sp else None}


def source_breakdown(evals, last_n=None):
    done = sorted([e for e in evals if e['status'] == 'evaluated'], key=lambda e: e['day'])
    if last_n:
        done = done[-last_n:]
    out = []
    for s in SOURCES:
        p = sum(e['by_source'].get(s, {}).get('picks', 0) for e in done)
        h = sum(e['by_source'].get(s, {}).get('hits', 0) for e in done)
        out.append({'Source': s, 'Picks': p, 'Hits': h, 'Hit rate': (h / p) if p else None})
    return pd.DataFrame(out)


def trend(evals):
    done = sorted([e for e in evals if e['status'] == 'evaluated'], key=lambda e: e['day'])
    rows, hits, picks = [], [], []
    for e in done:
        hits.append(len(e['hits'])); picks.append(e['picks'])
        h7, p7 = sum(hits[-7:]), sum(picks[-7:])
        rows.append({'Slate': e['day'], 'Hit rate': e['hit_rate'], 'Rolling 7': (h7 / p7) if p7 else None})
    return pd.DataFrame(rows, columns=['Slate', 'Hit rate', 'Rolling 7'])


# ---------------------------------------------------------------- learning

def pooled_rate(evals):
    r = rolling(evals)
    return r['rate'] if r['picks'] >= MIN_POOL and r['rate'] else PRIOR_RATE


def shrunk_rate(k, n, p0, m=PRIOR_STRENGTH):
    return (k + m * p0) / (n + m)


def adjustment(k, n, p0, cap=ADJ_CAP, min_n=MIN_SAMPLE, m=PRIOR_STRENGTH):
    if n < min_n or p0 <= 0:
        return 0.0
    return max(-cap, min(cap, 0.5 * (shrunk_rate(k, n, p0, m) - p0) / p0))


def badge_for(k, n, p0):
    if n < MIN_SAMPLE:
        return None
    s = shrunk_rate(k, n, p0)
    if k >= 2 and s >= 1.25 * p0:
        return 'Hot when predicted'
    if k == 0 or s <= 0.75 * p0:
        return 'Keeps missing'
    return None


def player_records(evals):
    p0 = pooled_rate(evals)
    agg = {}
    for e in evals:
        if e['status'] != 'evaluated':
            continue
        for rec, hit in [(r, 1) for r in e['hits']] + [(r, 0) for r in e['misses']]:
            a = agg.setdefault(rec['player_key'], {'Player': rec['player'], 'Team': rec['team'], 'Picks': 0, 'Hits': 0})
            a['Picks'] += 1; a['Hits'] += hit
            a['Player'], a['Team'] = rec['player'], rec['team'] or a['Team']   # latest team (trades)
    rows = []
    for key, a in agg.items():
        n, k = a['Picks'], a['Hits']
        rows.append({'player_key': key, **a, 'Hit rate': k / n if n else None, 'Shrunk rate': shrunk_rate(k, n, p0),
                     'Adjustment': adjustment(k, n, p0), 'Badge': badge_for(k, n, p0)})
    cols = ['player_key', 'Player', 'Team', 'Picks', 'Hits', 'Hit rate', 'Shrunk rate', 'Adjustment', 'Badge']
    return pd.DataFrame(rows, columns=cols).sort_values(['Shrunk rate', 'Picks'], ascending=[False, False]).reset_index(drop=True)


def badge_lookup(records):
    if not isinstance(records, pd.DataFrame) or records.empty:
        return {}
    return {r['player_key']: r['Badge'] for _, r in records.iterrows() if r['Badge']}


def apply_track_record(ranked, records, enabled=False, score_col='V3.2 Adjusted Index'):
    """Toggle OFF -> the exact same DataFrame object is returned (rankings unchanged).
    Toggle ON -> copy with 'Track adj' and 'Track-adjusted index' columns, sorted by the adjusted index."""
    if not enabled or not isinstance(ranked, pd.DataFrame) or ranked.empty or score_col not in ranked:
        return ranked
    adj = {}
    if isinstance(records, pd.DataFrame) and not records.empty:
        adj = dict(zip(records['player_key'], records['Adjustment']))
    out = ranked.copy()

    def key(r):
        try:
            return player_key(r.get('Player ID'), r.get('Player'))
        except TrackerError:
            return ''
    out['Track adj'] = [float(adj.get(key(r), 0.0)) for _, r in out.iterrows()]
    out['Track-adjusted index'] = pd.to_numeric(out[score_col], errors='coerce') * (1 + out['Track adj'])
    return out.sort_values('Track-adjusted index', ascending=False, na_position='last').reset_index(drop=True)


# ---------------------------------------------------------------- export / import

def export_json(conn):
    data = {t: [dict(r) for r in conn.execute(f'SELECT * FROM {t}')] for t in ('slates', 'predictions', 'actuals', 'game_results')}
    return json.dumps({'schema': 'prediction_tracker_v54', 'exported_at': _now(), **data}, indent=1)


def months(conn):
    """'YYYY-MM' months that have slates or predictions (newest first)."""
    rows = conn.execute("SELECT DISTINCT substr(day,1,7) m FROM slates UNION SELECT DISTINCT substr(day,1,7) FROM predictions ORDER BY 1 DESC")
    return [r[0] for r in rows if r[0]]


def export_month_json(conn, month):
    """V5.5: one month's slice of the store (same schema as export_json, so import_json accepts it).
    Small per-month files keep exports far under GitHub's limits; nothing is deleted."""
    if not re.fullmatch(r'\d{4}-\d{2}', str(month or '')):
        raise TrackerError('month must be YYYY-MM')
    like = f'{month}-%'
    data = {t: [dict(r) for r in conn.execute(f'SELECT * FROM {t} WHERE day LIKE ?', (like,))]
            for t in ('slates', 'predictions', 'actuals', 'game_results')}
    return json.dumps({'schema': 'prediction_tracker_v54', 'exported_at': _now(), 'month': month, **data}, indent=1)


def import_json(conn, text):
    """Merge an export into the store. Existing locked slates are kept as they are."""
    data = json.loads(text)
    if not isinstance(data, dict) or data.get('schema') != 'prediction_tracker_v54':
        raise TrackerError('Not a prediction tracker export')
    locked = {r['day'] for r in conn.execute('SELECT day FROM slates WHERE locked=1')}
    with conn:
        for t in ('slates', 'predictions', 'actuals', 'game_results'):
            allowed = [r['name'] for r in conn.execute(f'PRAGMA table_info({t})')]  # fixed table names; columns whitelisted
            for row in data.get(t) or []:
                if not isinstance(row, dict) or (t in ('slates', 'predictions') and row.get('day') in locked):
                    continue
                cols = [c for c in allowed if c in row]
                if not cols:
                    continue
                conn.execute(f'INSERT OR REPLACE INTO {t}({",".join(cols)}) VALUES({",".join("?" * len(cols))})',
                             tuple(row[c] for c in cols))
    return True
