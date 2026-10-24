"""V5.9 goalie weakness by shooter position on Home goalie rows (display only; the next-goal model is untouched).

Which skater position (C / LW / RW / D) beats a goalie more than the league does. REAL NHL data only:

Data (api-web.nhle.com, cached on disk, never raises, offline -> no chip):
  1. ``player/{goalie}/game-log/{season}/{2|3}`` via goalie_weak_v59.goalie_games (same cache): every game he played.
  2. ``gamecenter/{id}/play-by-play`` for his games in the WINDOW (current + previous season, regular season +
     playoffs, before the slate day): each shot on goal / goal with ``goalieInNetId`` = him, shooter position from the
     game's ``rosterSpots.positionCode``. All strengths (5v5, PP, PK) count; empty-net events (no goalie in net) and
     shootouts are excluded. Per game only the per-goalie {pos: [shots, goals]} counts are cached (tiny files).

Baseline: LEAGUE = every 2025-26 regular-season game (1312 play-by-plays, same rules): goals / shots by position.
Defensemen score far less per shot (5.9%) than forwards (~12%), so each position is judged against its OWN rate.

Marker (shrinkage, so small samples never trigger):
  shrunk rate(pos) = (G + K x p_pos) / (S + K), ratio(pos) = shrunk / p_pos   (K ghost shots at the league rate)
  overall = his goals / the goals a league-average goalie allows on his position mix
  Weak vs X when S(X) >= MIN_SHOTS, ratio(X) >= MIN_RATIO and ratio(X) >= overall x REL_RATIO (so a goalie who is
  simply bad against everyone is not tagged weak vs one position); the largest qualifying ratio wins.
  'Most G' = the position with the biggest share of his goals (needs MIN_GOALS_SHARE goals) - mostly reflects how many
  shots each position takes, so it is shown as a share, never as a weakness.
"""
from __future__ import annotations

import html as _html
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import goalie_weak_v59 as gweak
import h2h_v56 as h2h

API = gweak.API
CACHE_DIR = Path(os.environ.get('PLAYBOOK_GPOS_CACHE', Path(__file__).resolve().parent / 'data' / 'goalie_pos_cache'))
CACHE_CAP_BYTES = 3 * 1024 * 1024
POS = ('C', 'L', 'R', 'D')
LABEL = {'C': 'C', 'L': 'LW', 'R': 'RW', 'D': 'D'}
NAME = {'C': 'centers', 'L': 'left wings', 'R': 'right wings', 'D': 'defensemen'}
# 2025-26 regular season, all 1312 games, shots = SOG + goals, empty net + shootout excluded: (shots, goals)
LEAGUE = {'C': (24911, 2993), 'L': (13637, 1673), 'R': (13852, 1729), 'D': (20144, 1183)}
LEAGUE_SRC = '2025-26 NHL regular season (1312 games)'
K, MIN_SHOTS, MIN_RATIO, REL_RATIO, MIN_GOALS_SHARE = 150, 100, 1.15, 1.05, 20
WINDOW_SEASONS = 2
DONE = ('OFF', 'FINAL')


def _esc(v):
    return _html.escape(str(v if v is not None else ''), quote=True)


def league_rate(pos):
    s, g = LEAGUE[pos]
    return g / s


def window(current_season, n=WINDOW_SEASONS):
    return h2h.seasons_since(current_season, 20002001)[-n:]


def extract(pbp):
    """play-by-play -> {'game_id', 'state', 'g': {goalie_id: {pos: [shots, goals]}}}. Shots = SOG + goals."""
    pbp = pbp or {}
    pos = {}
    for s in pbp.get('rosterSpots') or []:
        try:
            pos[int(s['playerId'])] = s.get('positionCode')
        except (KeyError, TypeError, ValueError):
            continue
    out = {}
    for e in pbp.get('plays') or []:
        kind = e.get('typeDescKey')
        if kind not in ('shot-on-goal', 'goal') or (e.get('periodDescriptor') or {}).get('periodType') == 'SO':
            continue
        d = e.get('details') or {}
        goalie = d.get('goalieInNetId')
        shooter = d.get('scoringPlayerId') if kind == 'goal' else d.get('shootingPlayerId')
        if goalie is None or shooter is None:      # empty net / unknown shooter
            continue
        p = pos.get(int(shooter))
        if p not in POS:
            continue
        c = out.setdefault(str(int(goalie)), {}).setdefault(p, [0, 0])
        c[0] += 1
        c[1] += int(kind == 'goal')
    return {'game_id': int(pbp.get('id') or 0), 'state': pbp.get('gameState'), 'g': out}


def _cache_path(game_id, root):
    return Path(root) / f'gpos_{int(game_id)}.json'


def game_counts(game_id, getter, root=None, timeout=15):
    """Cached per-goalie position counts for one finished game. Returns (record or None, error or None)."""
    root = Path(root or CACHE_DIR)
    rec = gweak._read(_cache_path(game_id, root))
    if rec is not None:
        return rec, None
    try:
        r = getter(f'{API}gamecenter/{int(game_id)}/play-by-play', timeout=timeout)
        r.raise_for_status()
        rec = extract(r.json())
    except Exception as exc:
        return None, f'pbp {game_id}: {type(exc).__name__}'
    rec['game_id'] = int(game_id)
    if rec.get('state') in DONE:
        gweak._write(_cache_path(game_id, root), rec)
    return rec, None


def split(records, goalie_id):
    """Sum per-game records -> {pos: {'shots', 'goals'}} for this goalie."""
    out = {p: {'shots': 0, 'goals': 0} for p in POS}
    gid = str(int(goalie_id))
    for rec in records or []:
        for p, (s, g) in ((rec.get('g') or {}).get(gid) or {}).items():
            if p in out:
                out[p]['shots'] += int(s)
                out[p]['goals'] += int(g)
    return out


def load(goalie_id, day, current_season, getter, root=None, gweak_root=None, workers=6, timeout=15):
    """Goalie id -> {'goalie_id', 'split', 'games', 'window', 'errors'}. Never raises."""
    errors = []
    try:
        seasons = window(current_season)
        games, errs = gweak.goalie_games(goalie_id, day, current_season, getter, root=gweak_root, timeout=timeout)
        errors += errs
        keep = {str(s)[:4] for s in seasons}
        ids = sorted({g['game_id'] for g in games if str(g['game_id'])[:4] in keep})
        with ThreadPoolExecutor(max(1, workers)) as ex:
            got = list(ex.map(lambda i: game_counts(i, getter, root, timeout), ids))
        recs = [r for r, _ in got if r]
        errors += [e for _, e in got if e]
        try:
            h2h.prune(root or CACHE_DIR, CACHE_CAP_BYTES)
        except Exception:
            pass
        return {'goalie_id': int(goalie_id), 'split': split(recs, goalie_id), 'games': len(recs), 'games_listed': len(ids),
                'window': f'{h2h.season_label(seasons[0])} to {h2h.season_label(seasons[-1])}', 'day': str(day),
                'errors': errors}
    except Exception as exc:
        return {'goalie_id': goalie_id, 'split': split([], goalie_id or 0), 'games': 0, 'window': '', 'errors':
                errors + [f'goalie pos: {type(exc).__name__}']}


def marker(data):
    """load() output -> chip data or None (no shots at all)."""
    sp = (data or {}).get('split') or {}
    shots = sum(sp.get(p, {}).get('shots', 0) for p in POS)
    goals = sum(sp.get(p, {}).get('goals', 0) for p in POS)
    if shots <= 0:
        return None
    expected = sum(sp.get(p, {}).get('shots', 0) * league_rate(p) for p in POS)
    overall = goals / expected if expected else 1.0
    rows = {}
    for p in POS:
        s, g = sp.get(p, {}).get('shots', 0), sp.get(p, {}).get('goals', 0)
        lg = league_rate(p)
        shrunk = (g + K * lg) / (s + K)
        rows[p] = {'shots': s, 'goals': g, 'sv': (1 - g / s) if s else None, 'league_sv': 1 - lg,
                   'ratio': shrunk / lg, 'share': g / goals if goals else 0.0}
    ok = [p for p in POS if rows[p]['shots'] >= MIN_SHOTS and rows[p]['ratio'] >= MIN_RATIO
          and rows[p]['ratio'] >= overall * REL_RATIO]
    weak = max(ok, key=lambda p: rows[p]['ratio']) if ok else None
    most = max(POS, key=lambda p: (rows[p]['goals'], -rows[p]['shots'])) if goals >= MIN_GOALS_SHARE else None
    return {'weak': weak, 'ratio': rows[weak]['ratio'] if weak else None, 'most': most,
            'most_share': rows[most]['share'] if most else None, 'rows': rows, 'shots': shots, 'goals': goals,
            'overall': overall, 'games': data.get('games', 0), 'window': data.get('window', '')}


def tooltip(m, name=''):
    lines = [f'{name + ": " if name else ""}goals / shots on goal by shooter position, {m["window"]} '
             f'({m["games"]} GP, reg. season + playoffs, all strengths, empty net + shootout excluded)']
    for p in POS:
        r = m['rows'][p]
        sv = f'{r["sv"]:.3f}' if r['sv'] is not None else '-'
        lines.append(f'{LABEL[p]}: {r["goals"]} G / {r["shots"]} SOG, SV% {sv} vs league {r["league_sv"]:.3f}, '
                     f'shrunk {r["ratio"]:.2f}x league, {r["share"] * 100:.0f}% of his goals')
    lines.append(f'Overall {m["overall"]:.2f}x league goals for his shot mix. League baseline: {LEAGUE_SRC}.')
    lines.append(f'Weak = shrunk ({K} league-rate ghost shots) >= {MIN_RATIO:.2f}x league, >= {MIN_SHOTS} shots and '
                 f'{REL_RATIO:.2f}x his overall. Most G share needs {MIN_GOALS_SHARE}+ goals.')
    return '\n'.join(lines)


def chip(m, name=''):
    """Compact HTML chip for a Home goalie row ('' when there is nothing to say)."""
    if not m:
        return ''
    parts = []
    if m.get('weak'):
        parts.append(f'<b><i>WEAK</i> vs {LABEL[m["weak"]]} · {m["ratio"]:.2f}×</b>')
    elif any(r['shots'] >= MIN_SHOTS for r in m['rows'].values()):   # tested, nothing above threshold
        parts.append('<em>no clear split</em>')
    if m.get('most'):
        parts.append(f'<em>{"· " if parts else ""}most G: {LABEL[m["most"]]} {m["most_share"] * 100:.0f}%</em>')
    if not parts:
        return ''
    cls = 'gpos weak' if m.get('weak') else 'gpos'
    return f'<span class="{cls}" title="{_esc(tooltip(m, name))}">{" ".join(parts)}</span>'


def home_marks(state, loader):
    """Featured-game goalies (listed starters + team leakiest) -> state['goalies'][team]['pos_marks'][id] = marker.
    Returns {'shown', 'errors'}. ``loader(goalie_id)`` -> load() output. Never raises."""
    stat = {'shown': 0, 'errors': []}
    cache = {}
    for team, g in ((state or {}).get('goalies') or {}).items():
        marks = {}
        for row in (g.get('starter_stats'), g.get('leakiest')):
            gid = str((row or {}).get('Player ID') or '')
            if not gid.isdigit():
                continue
            try:
                if gid not in cache:
                    data = loader(int(gid))
                    stat['errors'] += (data or {}).get('errors') or []
                    cache[gid] = marker(data)
                if cache[gid]:
                    marks[gid] = cache[gid]
                    stat['shown'] += 1
            except Exception as exc:
                stat['errors'].append(f'goalie pos {gid}: {type(exc).__name__}')
        g['pos_marks'] = marks
    return stat


def row_chip(g, stats_row):
    """v55_ui hook: chip for the goalie in ``stats_row`` using g['pos_marks'] (set by home_marks)."""
    try:
        gid = str((stats_row or {}).get('Player ID') or '')
        return chip(((g or {}).get('pos_marks') or {}).get(gid), (stats_row or {}).get('Goalie') or '')
    except Exception:
        return ''
