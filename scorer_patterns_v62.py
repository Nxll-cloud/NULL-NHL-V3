"""V6.2 Scorer Patterns (Prediction Models page): what recent goal scorers had in common, and who fits it next.

Replaces the retired EXPERIMENTAL Blend column (model chance x gematria layer hits), which never beat the plain model.
Display only: nothing here feeds the model, the NP ranks, the threat score (J=2, D=3, A=2, T=1), the parlay or any log.

Data (all real, nothing guessed):
  * Recent nights: each scored night's saved pre-game slate snapshot (snapshots/YYYY-MM-DD.json: every skater's
    pre-game Shots/G L5 & L10, Goals/G L5 & prior, position, opponent GA/G & SA/G L10, Statistical rank) joined by NHL
    player ID to that night's real scorers (snapshots/accuracy/YYYY-MM-DD.json results). Pre-game features use only
    games before that night (cutoff = slate date), so a trait can never peek at the night it is tested on.
  * Situational: NHL api-web ``score/{day}`` goal lists (scorer, assists, strength ev/pp/sh, empty-net modifier) for the
    7 days before each night -> 'PP goal in last 7 days', '3+ points in last 7 days', '2+ assists in last 7 days'.
  * Tonight (live): the same score feed for the slate date (60 s cache) + the app's already-polled play-by-play
    (goalie in net, shots on goal) -> tonight's scorers so far, their situations, assisters, leaky goalies, shooters.

Method: a trait is KEPT when, across the window's player-nights, players with it scored more often than everyone
(lift = rate with trait / base rate) with at least MIN_N player-nights, MIN_K scorers, lift >= MIN_LIFT and the 95%
Wilson lower bound of its rate above the base rate. Fit score = sum of ln(lift) of the kept traits a player matches,
scaled 0-100 by the maximum possible, plus LIVE_BONUS per live signal tonight (fixed, unvalidated, labelled).
It is a pattern fit, not a calibrated probability. Traits overlap (shooters are often hot), so lifts are not additive
evidence.
"""
from __future__ import annotations

import html
import json
import math
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import resource_guard_v61 as _rg

HERE = Path(__file__).resolve().parent
SNAP_DIR = HERE / 'snapshots'
ACC_DIR = Path(os.environ.get('PLAYBOOK_ACCURACY_DIR') or SNAP_DIR / 'accuracy')
NHL = 'https://api-web.nhle.com/v1/'
WINDOW = 14          # scored nights in the rolling window
PRIOR_DAYS = 7       # situational look-back before each night
MIN_NIGHTS = 5
MIN_SCORERS = 150
MIN_N = 100          # player-nights with the trait
MIN_K = 15           # scorers with the trait
MIN_LIFT = 1.2
MIN_GP = 3           # tonight's candidates need this many prior games
LIVE_BONUS = 8
TOP = 15
TONIGHT_MIN_SCORERS = 5
FORWARDS = ('C', 'L', 'R', 'LW', 'RW', 'F')
_FEED = _rg.BoundedTTL({'final': 6 * 3600, 'live': 60, 'fail': 120}, cap=40)

CAPTION = ('Pattern fit, not a probability. Traits are learned from the last scored nights (real scorers vs every skater '
           'on those slates, pre-game stats only) and re-learned when a new night is scored; tonight’s live signals refresh '
           'with the score feed. Display only: no effect on the model, NP ranks, threat score or logs.')


def _f(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _e(x):
    return html.escape(str(x if x is not None else ''))


# ------------------------------------------------------------------------------------------------ traits
# key, label, group, fn(row) -> True/False/None (None = not measurable for that row; excluded from that trait's test)
def _shots(r):
    return _f(r.get('s5'))


TRAITS = [
    ('shots3', 'Shot volume 3+ SOG/game (last 5)', 'Shots', lambda r: None if _shots(r) is None else _shots(r) >= 3.0),
    ('shots_up', 'Shots trending up (L5 ≥ L10 + 0.5)', 'Shots',
     lambda r: None if _shots(r) is None or _f(r.get('s10')) is None else _shots(r) >= _f(r['s10']) + 0.5),
    ('hot', 'Recent form: 2+ goals in last 5', 'Form', lambda r: None if _f(r.get('g5')) is None else _f(r['g5']) >= 0.4),
    ('scorer', 'Established scorer (0.35+ goals/game prior)', 'Form',
     lambda r: None if _f(r.get('gp')) is None else _f(r['gp']) >= 0.35),
    ('top50', 'Top-50 Form rank on the slate', 'Form', lambda r: None if _f(r.get('rank')) is None else _f(r['rank']) <= 50),
    ('forward', 'Forward (C / LW / RW)', 'Role', lambda r: None if not r.get('pos') else r['pos'] in FORWARDS),
    ('ppg7', 'Power-play goal in last 7 days', 'Situational', lambda r: None if r.get('ppg7') is None else r['ppg7'] >= 1),
    ('pts7', '3+ points in last 7 days', 'Situational', lambda r: None if r.get('pts7') is None else r['pts7'] >= 3),
    ('ast7', '2+ assists in last 7 days (playmaking line)', 'Situational',
     lambda r: None if r.get('ast7') is None else r['ast7'] >= 2),
    ('home', 'Home ice', 'Matchup', lambda r: None if r.get('home') is None else bool(r['home'])),
    ('soft_d', 'Opponent allows 3.4+ goals/game (L10, defense + goalie)', 'Matchup',
     lambda r: None if _f(r.get('oga')) is None else _f(r['oga']) >= 3.4),
    ('shot_d', 'Opponent allows 30+ shots/game (L10)', 'Matchup',
     lambda r: None if _f(r.get('osa')) is None else _f(r['osa']) >= 30),
]
TRAIT = {k: (lab, grp, fn) for k, lab, grp, fn in TRAITS}
SHORT = {'shots3': '3+ SOG/G L5', 'shots_up': 'Shots ↑', 'hot': '2+ G in L5', 'scorer': '0.35+ G/GP', 'top50': 'Top-50 Form',
         'forward': 'Forward', 'ppg7': 'PPG last 7d', 'pts7': '3+ pts last 7d', 'ast7': '2+ A last 7d', 'home': 'Home',
         'soft_d': 'Soft opp D', 'shot_d': 'Opp allows 30+ SOG'}   # compact chips (full labels in the trait table)


def features(row, home=None, prior=None):
    """Snapshot ranking row (+ home flag, + prior-7-day feed totals or None) -> compact feature dict."""
    pid = _pid(row.get('Player ID'))
    d = {'pid': pid, 'name': row.get('Player'), 'team': row.get('Team'), 'pos': str(row.get('Position') or '').upper(),
         's5': row.get('Shots/G L5'), 's10': row.get('Shots/G L10'), 'g5': row.get('Goals/G L5'),
         'gp': row.get('Goals/G Prior'), 'rank': row.get('Statistical rank'), 'oga': row.get('Opp GA/G L10'),
         'osa': row.get('Opp SA/G L10'), 'home': home, 'opp': row.get('Opponent'), 'pgp': row.get('Prior GP')}
    if prior is not None:
        d['ppg7'], d['pts7'], d['ast7'] = prior['pp'].get(pid, 0), prior['g'].get(pid, 0) + prior['a'].get(pid, 0), prior['a'].get(pid, 0)
    return d


def traits_of(feat):
    return {k: fn(feat) for k, (_l, _g, fn) in TRAIT.items()}


def _pid(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ score feed
def parse_score(payload, day):
    """api-web score/{day} -> {'games': {gid: {'state','away','home'}}, 'goals': [(pid, team, strength, modifier,
    (assist ids), gid)]}. Shootout goals are dropped; own goals keep their credited scorer but are flagged."""
    games, goals = {}, []
    for g in (payload or {}).get('games') or []:
        if str(g.get('gameDate') or day) != str(day):
            continue
        gid = str(g.get('id'))
        games[gid] = {'state': str(g.get('gameState') or ''), 'away': (g.get('awayTeam') or {}).get('abbrev', ''),
                      'home': (g.get('homeTeam') or {}).get('abbrev', '')}
        for go in g.get('goals') or []:
            if (go.get('periodDescriptor') or {}).get('periodType') == 'SO' or go.get('playerId') is None:
                continue
            goals.append((int(go['playerId']), go.get('teamAbbrev') or '', str(go.get('strength') or 'ev').lower(),
                          str(go.get('goalModifier') or 'none').lower(),
                          tuple(int(a['playerId']) for a in go.get('assists') or [] if a.get('playerId') is not None), gid))
    return {'games': games, 'goals': goals}


def _final(feed):
    return bool(feed['games']) and all(g['state'] in ('OFF', 'FINAL', 'OVER') for g in feed['games'].values())


def fetch_score(day, getter=None, timeout=8, live_ok=True):
    """Compact score feed for one day, process-cached (final days 6 h, unfinished 60 s, failures 2 min). None on failure."""
    day = str(day)
    for kind in ('final', 'live', 'fail'):
        hit, val = _FEED.get(kind, day)
        if hit:
            return val
    try:
        if getter is None:
            import requests
            getter = requests.get
        r = getter(NHL + f'score/{day}', timeout=timeout, headers={'User-Agent': 'NULL-NHL-V3/0.2'})
        r.raise_for_status()
        feed = parse_score(r.json(), day)
    except Exception:
        return _FEED.put('fail', day, None)
    return _FEED.put('final' if _final(feed) or not feed['games'] else 'live', day, feed)


def fetch_days(days, getter=None, workers=4):
    days = sorted(set(str(d) for d in days))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(days, pool.map(lambda d: fetch_score(d, getter), days)))


def prior_totals(day, feeds, n=PRIOR_DAYS):
    """Goals / PP goals / assists per player over the n days before `day`; None if any of those days is missing."""
    d0 = date.fromisoformat(str(day))
    g, pp, a = defaultdict(int), defaultdict(int), defaultdict(int)
    for i in range(1, n + 1):
        f = feeds.get((d0 - timedelta(days=i)).isoformat())
        if f is None:
            return None
        for pid, _t, strength, mod, assists, _gid in f['goals']:
            if mod == 'own-goal':
                continue
            g[pid] += 1
            pp[pid] += strength == 'pp'
            for x in assists:
                a[x] += 1
    return {'g': g, 'pp': pp, 'a': a}


# ------------------------------------------------------------------------------------------------ recent window
def window_days(day, acc_dir=None, n=WINDOW):
    """Last n days before `day` that have a scored accuracy entry and a saved slate snapshot."""
    acc_dir, out = Path(acc_dir or ACC_DIR), []
    for p in sorted(acc_dir.glob('????-??-??.json'), reverse=True) if acc_dir.is_dir() else []:
        if p.stem >= str(day):
            continue
        out.append(p.stem)
        if len(out) >= n * 2:
            break
    return sorted(out)


def signature(day, acc_dir=None, snap_dir=None):
    """Cache key: the window's accuracy / snapshot file names + mtimes (a newly scored night changes it)."""
    acc_dir, snap_dir = Path(acc_dir or ACC_DIR), Path(snap_dir or SNAP_DIR)
    sig = [str(day)]
    for d in window_days(day, acc_dir):
        for p in (acc_dir / f'{d}.json', snap_dir / f'{d}.json'):
            try:
                sig.append((p.name, p.stat().st_mtime_ns))
            except OSError:
                pass
    return tuple(sig)


def _load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def night_rows(day, acc, snap, prior=None):
    """One scored night -> compact rows [(traits dict, scored bool, position)] for skaters on that night's played games."""
    res = (acc or {}).get('results') or {}
    if not res.get('scorers') or not snap:
        return []
    gids = {str(g) for g in acc.get('games') or []}
    home = {}
    for g in snap.get('games') or []:
        if not gids or str(g.get('Game ID')) in gids:
            home[g.get('Home')], home[g.get('Away')] = True, False
    scorers = {_pid(s[0]) for s in res['scorers']}
    out = []
    for r in snap.get('rankings') or []:
        if r.get('Team') not in home or _pid(r.get('Player ID')) is None:
            continue
        ft = features(r, home[r['Team']], prior)
        out.append((traits_of(ft), ft['pid'] in scorers, ft['pos']))
    return out


def load_window(day, acc_dir=None, snap_dir=None, feeds=None, getter=None, n=WINDOW):
    """-> (rows, nights, feeds). Reads one snapshot at a time (each ~0.1-0.8 MB) and keeps only compact trait rows."""
    acc_dir, snap_dir = Path(acc_dir or ACC_DIR), Path(snap_dir or SNAP_DIR)
    rows, nights = [], []
    cands = window_days(day, acc_dir, n)
    picked = []
    for d in reversed(cands):
        acc = _load_json(acc_dir / f'{d}.json')
        if acc and (acc.get('results') or {}).get('scorers'):
            picked.append((d, acc))
        if len(picked) >= n:
            break
    picked.reverse()
    if feeds is None:
        d_today = date.fromisoformat(str(day))
        need = {(d_today - timedelta(days=i)).isoformat() for i in range(1, PRIOR_DAYS + 1)}   # tonight's own look-back
        for d, _ in picked:
            d0 = date.fromisoformat(d)
            need |= {(d0 - timedelta(days=i)).isoformat() for i in range(0, PRIOR_DAYS + 1)}
        feeds = fetch_days(need, getter) if need else {}
    for d, acc in picked:
        snap = _load_json(snap_dir / f'{d}.json')
        nr = night_rows(d, acc, snap, prior_totals(d, feeds))
        if nr:
            rows.extend(nr)
            nights.append(d)
        del snap
    return rows, nights, feeds


def wilson_lo(k, n, z=1.96):
    if not n:
        return 0.0
    p = k / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def learn(rows):
    """Trait stats over the window rows -> list of dicts (kept first, by lift)."""
    out = []
    for key, (label, grp, _fn) in TRAIT.items():
        meas = [(t[key], s) for t, s, _p in rows if t.get(key) is not None]
        if not meas:
            out.append({'key': key, 'label': label, 'group': grp, 'n': 0, 'k': 0, 'N': 0, 'K': 0, 'lift': None, 'kept': False,
                        'why': 'not measurable (data unavailable)'})
            continue
        N, K = len(meas), sum(1 for _v, s in meas if s)
        n = sum(1 for v, _s in meas if v)
        k = sum(1 for v, s in meas if v and s)
        base = K / N if N else 0
        lift = (k / n) / base if n and base else None
        lo = wilson_lo(k, n)
        if n < MIN_N or k < MIN_K:
            why = f'sample too small (needs {MIN_N}+ player-nights and {MIN_K}+ scorers)'
        elif lift is None or lift < MIN_LIFT:
            why = 'not over-represented among scorers'
        elif lo <= base:
            why = 'lift within noise (95% lower bound ≤ base rate)'
        else:
            why = ''
        out.append({'key': key, 'label': label, 'group': grp, 'n': n, 'k': k, 'N': N, 'K': K, 'lift': lift,
                    'scorer_share': k / K if K else 0, 'all_share': n / N if N else 0, 'kept': not why, 'why': why})
    out.sort(key=lambda s: (not s['kept'], -(s['lift'] or 0)))
    return out


def recent_profile(rows, nights, feeds):
    """Descriptive numbers for the window: player-nights, scorers, base rate, goal situations, forward share of scorers."""
    N, K = len(rows), sum(1 for _t, s, _p in rows if s)
    sit, n_goals = defaultdict(int), 0
    for d in nights:
        f = feeds.get(d) if feeds else None
        for _pid_, _t, strength, mod, _a, _g in (f or {}).get('goals') or []:
            n_goals += 1
            sit['EN' if mod == 'empty-net' else strength.upper()] += 1
    fwd = sum(1 for _t, s, p in rows if s and p in FORWARDS)
    return {'nights': list(nights), 'N': N, 'K': K, 'base': K / N if N else 0, 'goals': n_goals, 'situations': dict(sit),
            'fwd_share': fwd / K if K else None}


def build_patterns(day, acc_dir=None, snap_dir=None, feeds=None, getter=None):
    """Learn the window's patterns -> {'status','stats','profile','feeds'} (feeds returned so tonight can reuse them)."""
    rows, nights, feeds = load_window(day, acc_dir, snap_dir, feeds, getter)
    prof = recent_profile(rows, nights, feeds)
    if len(nights) < MIN_NIGHTS or prof['K'] < MIN_SCORERS:
        return {'status': 'insufficient', 'stats': learn(rows) if rows else [], 'profile': prof, 'feeds': feeds, 'day': str(day)}
    stats = learn(rows)
    return {'status': 'ok' if any(s['kept'] for s in stats) else 'none', 'stats': stats, 'profile': prof, 'feeds': feeds,
            'day': str(day)}


# ------------------------------------------------------------------------------------------------ tonight
def tonight_live(feed, pbp=None):
    """Tonight's score feed (+ optional parsed play-by-play) -> live context.
    {'states': {team: state}, 'goals': n, 'scorers': {pid: goals}, 'assists': {pid: n}, 'situations': {...},
     'team_pp': {team: n}, 'allowed': {team: goals allowed excl. EN}, 'goalie': {team: (goalie name, allowed)},
     'shots': {pid: SOG}}"""
    lv = {'states': {}, 'goals': 0, 'scorers': defaultdict(int), 'assists': defaultdict(int), 'situations': defaultdict(int),
          'team_pp': defaultdict(int), 'allowed': defaultdict(int), 'goalie': {}, 'shots': defaultdict(int), 'scorer_rows': []}
    team_of_game = {}
    for gid, g in ((feed or {}).get('games') or {}).items():
        for side in ('away', 'home'):
            lv['states'][g[side]] = g['state']
        team_of_game[gid] = (g['away'], g['home'])
    for pid, team, strength, mod, assists, gid in (feed or {}).get('goals') or []:
        lv['goals'] += 1
        lv['situations']['EN' if mod == 'empty-net' else strength.upper()] += 1
        if mod != 'own-goal':
            lv['scorers'][pid] += 1
        for a in assists:
            lv['assists'][a] += 1
        if strength == 'pp':
            lv['team_pp'][team] += 1
        teams = team_of_game.get(gid) or ()
        opp = next((t for t in teams if t != team), None)
        if opp and mod != 'empty-net':
            lv['allowed'][opp] += 1
    for game in (pbp or {}).values():
        if not isinstance(game, dict):
            continue
        roster = game.get('roster') or {}
        st_ = str(game.get('state') or '')
        for side in ('away', 'home'):
            if game.get(side) and st_:
                lv['states'].setdefault(game[side], st_)
        g_allowed = defaultdict(int)
        for e in game.get('events') or []:
            if e.get('kind') in ('sog', 'goal') and e.get('shooter') is not None:
                lv['shots'][int(e['shooter'])] += 1
            if e.get('kind') == 'goal' and e.get('goalie') not in (None, ''):
                g_allowed[_pid(e['goalie'])] += 1
        for gk, n in g_allowed.items():
            info = roster.get(gk) or roster.get(str(gk)) or {}
            team = info.get('team')
            opp = next((t for t in (game.get('away'), game.get('home')) if t and t != team), None)
            if opp and n >= (lv['goalie'].get(opp) or ('', 0))[1]:
                lv['goalie'][opp] = (info.get('name') or 'goalie', n)   # keyed by the team SHOOTING at him
    lv['has_pbp'] = bool(pbp)
    return lv


def _state_phase(s):
    s = str(s or '').upper()
    if s in ('OFF', 'FINAL', 'OVER'):
        return 'final'
    if s in ('LIVE', 'CRIT'):
        return 'live'
    return 'pregame'


def live_signals(feat, lv):
    """Live chips for one candidate (only in-progress games)."""
    pid, team, out = feat['pid'], feat['team'], []
    if _state_phase(lv['states'].get(team)) != 'live':
        return out
    if lv['assists'].get(pid):
        out.append(f'Assisted tonight ({lv["assists"][pid]}): on a scoring line')
    if lv['shots'].get(pid, 0) >= 3:
        out.append(f'{lv["shots"][pid]} SOG tonight, no goal yet')
    gk = lv['goalie'].get(team)
    if gk and gk[1] >= 3:
        out.append(f'Facing {gk[0]}, {gk[1]} allowed tonight')
    elif not gk and lv['allowed'].get(feat.get('opp')) is not None and lv['allowed'].get(feat.get('opp'), 0) >= 3:
        out.append(f'Opponent has allowed {lv["allowed"][feat["opp"]]} tonight')
    if lv['team_pp'].get(team) and (feat.get('ppg7') or 0) >= 1:
        out.append('Team PP has scored tonight · recent PP scorer')
    return out


def suggest(rankings, games, patterns, lv, day, top=TOP):
    """Score tonight's skaters in games not yet final -> (rows, info). Tonight's scorers are excluded (counted in info)."""
    kept = [s for s in patterns.get('stats') or [] if s['kept']]
    w = {s['key']: math.log(s['lift']) for s in kept}
    wmax = sum(w.values()) or 1.0
    prior = prior_totals(day, patterns.get('feeds') or {})
    home = {}
    for g in games or []:
        home[g.get('Home')], home[g.get('Away')] = True, False
    rows, excluded, finished = [], 0, 0
    for r in rankings or []:
        pid, team = _pid(r.get('Player ID')), r.get('Team')
        if pid is None or team not in home:
            continue
        if (_f(r.get('Prior GP')) or 0) < MIN_GP:
            continue
        ph = _state_phase(lv['states'].get(team) or next((g.get('Status') for g in games if team in (g.get('Home'), g.get('Away'))), ''))
        if ph == 'final':
            finished += 1
            continue
        if lv['scorers'].get(pid):
            excluded += 1
            continue
        ft = features(r, home[team], prior)
        tr = traits_of(ft)
        matched = [k for k in w if tr.get(k)]
        live = live_signals(ft, lv)
        base = 100 * sum(w[k] for k in matched) / wmax
        score = min(100.0, base + LIVE_BONUS * len(live))
        if not matched and not live:
            continue
        rows.append({'pid': pid, 'name': ft['name'], 'team': team, 'pos': ft['pos'], 'opp': ft['opp'], 'phase': ph,
                     'fit': round(score), 'base_fit': round(base), 'matched': [SHORT[k] for k in matched], 'live': live,
                     '_s5': _f(ft['s5']) or 0})
    rows.sort(key=lambda x: (-x['fit'], -len(x['matched']), -x['_s5'], str(x['name']), x['pid']))
    return rows[:top], {'excluded_scored': excluded, 'final_skipped': finished, 'candidates': len(rows)}


def tonight_check(rankings, games, patterns, lv):
    """Do the kept traits hold among tonight's scorers so far? -> list of (label, scorer share, slate share) or []."""
    sc = set(lv['scorers'])
    if len(sc) < TONIGHT_MIN_SCORERS:
        return []
    home = {}
    for g in games or []:
        home[g.get('Home')], home[g.get('Away')] = True, False
    prior = prior_totals(str(patterns.get('day') or ''), patterns.get('feeds') or {}) if patterns.get('day') else None
    pool = [(traits_of(features(r, home[r['Team']], prior)), _pid(r.get('Player ID')) in sc)
            for r in rankings or [] if r.get('Team') in home and lv['states'].get(r.get('Team')) not in (None, '', 'FUT', 'PRE')]
    out = []
    for s in patterns.get('stats') or []:
        if not s['kept']:
            continue
        m = [(t[s['key']], hit) for t, hit in pool if t.get(s['key']) is not None]
        K = sum(1 for _v, h in m if h)
        if not m or not K:
            continue
        out.append((SHORT[s['key']], sum(1 for v, h in m if v and h) / K, sum(1 for v, _h in m if v) / len(m), K))
    return out


# ------------------------------------------------------------------------------------------------ html
CSS = ('<style>.v55 .spx{margin:10px 0;padding:12px 14px;border-radius:18px;border:1px solid color-mix(in srgb,#3dffa8 34%,transparent);'
       'background:linear-gradient(135deg,rgba(61,255,168,.06),rgba(56,225,255,.06));min-width:0;overflow-wrap:anywhere}'
       '.v55 .spx h4{margin:10px 0 4px;color:var(--ink);font:800 .82rem var(--fd);letter-spacing:.08em;text-transform:uppercase}'
       '.v55 .spx p{margin:4px 0;color:var(--mut);font-size:.8rem;line-height:1.45}.v55 .spx b{color:var(--ink)}'
       '.v55 .spx .spk{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}'
       '.v55 .spx .spk span{padding:3px 9px;border-radius:999px;font-size:.72rem;color:var(--ink);border:1px solid var(--line);background:rgba(255,255,255,.03)}'
       '.v55 .spx .sps{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}'
       '.v55 .spx table{width:100%;border-collapse:collapse;font-size:.8rem;color:var(--ink);font-variant-numeric:tabular-nums}'
       '.v55 .spx th{padding:4px 5px;text-align:left;color:var(--mut);font:700 .7rem var(--fb);letter-spacing:.05em;text-transform:uppercase;border-bottom:1px solid var(--line)}'
       '.v55 .spx td{padding:5px;border-bottom:1px solid var(--line);vertical-align:top}.v55 .spx td.n{text-align:right;white-space:nowrap}'
       '.v55 .spx tr.off td{color:var(--dim)}'
       '.v55 .spr{display:grid;grid-template-columns:2em minmax(0,1fr) auto;gap:4px 8px;padding:7px 0;border-top:1px solid var(--line);align-items:start}'
       '.v55 .spr .rk{color:var(--mut);font-weight:800}.v55 .spr .nm b{font-weight:700}.v55 .spr .nm small{color:var(--dim);margin-left:5px;font-size:.72rem}'
       '.v55 .spr .ft{font-weight:800;color:#3dffa8;white-space:nowrap;text-align:right}.v55 .spr .ch{grid-column:2/4;display:flex;flex-wrap:wrap;gap:4px}'
       '.v55 .spr .ch span{padding:1px 7px;border-radius:999px;font-size:.68rem;color:var(--mut);border:1px solid var(--line)}'
       '.v55 .spr .ch span.lv{color:#1a0710;border-color:transparent;background:linear-gradient(90deg,#38e1ff,#3dffa8)}'
       '.v55 .spr .lvp{font-size:.66rem;font-weight:800;color:#ff3d7f;margin-left:5px}'
       '@media (max-width:420px){.v55 .spx{padding:10px}.v55 .spx th,.v55 .spx td{padding:4px 3px}.v55 .spx .hide-sm{display:none}}</style>')


def _pct(x):
    return '—' if x is None else f'{100 * x:.0f}%'


def section_html(patterns, sugg, info, lv, check, day):
    import accuracy_v58 as acc
    prof = patterns.get('profile') or {}
    nights = prof.get('nights') or []
    span = f'{acc.short_day(nights[0])} – {acc.short_day(nights[-1])}' if nights else 'no nights'
    head = (f'<p>Learned from <b>{len(nights)}</b> scored night{"s" if len(nights) != 1 else ""} ({_e(span)}): '
            f'<b>{prof.get("K", 0)}</b> scorers among <b>{prof.get("N", 0)}</b> skater-games · base rate <b>{_pct(prof.get("base"))}</b>.</p>')
    sit = prof.get('situations') or {}
    if prof.get('goals'):
        head += ('<div class="spk">' + ''.join(f'<span>{k} {_pct(v / prof["goals"])}</span>' for k, v in
                                                 sorted(sit.items(), key=lambda kv: -kv[1]))
                 + (f'<span>Forwards {_pct(prof.get("fwd_share"))} of scorers</span>' if prof.get('fwd_share') is not None else '')
                 + f'<span>{prof["goals"]} goals</span></div>')
    else:
        head += '<p>Goal situations unavailable (NHL score feed not reached); situational traits are not tested.</p>'
    status = patterns.get('status')
    if status == 'insufficient':
        return (f'{CSS}<section class="spx" aria-label="Scorer patterns">{head}<p><b>Not enough scored nights yet</b> '
                f'(needs {MIN_NIGHTS}+ nights and {MIN_SCORERS}+ scorers). No suggestions are shown rather than guessing.</p></section>')
    def _tr(s):
        why = '' if s['kept'] else f'<br><small>{_e(s["why"])}</small>'
        lift = '—' if s['lift'] is None else f'{s["lift"]:.2f}×'
        sh = (_pct(s.get('scorer_share')), _pct(s.get('all_share'))) if s['n'] else ('—', '—')
        return (f'<tr class="{"" if s["kept"] else "off"}"><td>{"✅ " if s["kept"] else ""}{_e(s["label"])}{why}</td>'
                f'<td class="n">{sh[0]}</td><td class="n">{sh[1]}</td><td class="n">{lift}</td>'
                f'<td class="n hide-sm">{s["k"]}/{s["n"]}</td></tr>')
    trs = ''.join(_tr(s) for s in patterns.get('stats') or [])
    table = ('<h4>Recurring traits among recent scorers</h4><div class="sps"><table><thead><tr><th>Trait</th><th>Scorers</th>'
             '<th>Everyone</th><th>Lift</th><th class="hide-sm">Scored / with trait</th></tr></thead>'
             f'<tbody>{trs}</tbody></table></div>')
    # tonight
    sits = lv.get('situations') or {}
    tn = (f'<h4>Tonight so far</h4><p><b>{lv.get("goals", 0)}</b> goal{"s" if lv.get("goals", 0) != 1 else ""} by '
          f'<b>{len(lv.get("scorers") or {})}</b> scorer{"s" if len(lv.get("scorers") or {}) != 1 else ""}'
          + (' · ' + ' · '.join(f'{k} {v}' for k, v in sorted(sits.items(), key=lambda kv: -kv[1])) if sits else '')
          + ('' if lv.get('feed_ok', True) else ' · live score feed unavailable') + '.</p>')
    if check:
        tn += (f'<p>Kept traits among the {check[0][3]} scorers so far who are on tonight’s slate list (vs every skater in started games):</p>'
               '<div class="spk">' + ''.join(f'<span>{_e(lab)} <b>{_pct(a)}</b> vs {_pct(b)}</span>' for lab, a, b, _k in check) + '</div>')
    elif lv.get('goals'):
        tn += f'<p>Trait check on tonight’s scorers appears once {TONIGHT_MIN_SCORERS}+ have scored.</p>'
    if status == 'none':
        body = '<p><b>No trait cleared the bar in this window</b>, so no names are suggested.</p>'
    elif not sugg:
        body = '<p>No upcoming or in-progress skaters to suggest (all games final, or no slate rankings loaded yet).</p>'
    else:
        body = ''.join(
            f'<div class="spr"><span class="rk">{i}</span><span class="nm"><b>{_e(r["name"])}</b><small>{_e(r["pos"])} · {_e(r["team"])}'
            f'{" vs " + _e(r["opp"]) if r.get("opp") else ""}</small>{"<span class=lvp>LIVE</span>" if r["phase"] == "live" else ""}</span>'
            f'<span class="ft">Fit {r["fit"]}</span><span class="ch">'
            + ''.join(f'<span>{_e(m)}</span>' for m in r['matched']) + ''.join(f'<span class="lv">{_e(m)}</span>' for m in r['live'])
            + '</span></div>' for i, r in enumerate(sugg, 1))
    notes = (f'<p>Suggestions: skaters in games not yet final, {MIN_GP}+ prior games. Fit = share of the kept traits’ weight '
             f'(ln lift) a player matches, 0–100; each live signal adds {LIVE_BONUS} (fixed, unvalidated). '
             f'{info.get("excluded_scored", 0)} player{"s" if info.get("excluded_scored", 0) != 1 else ""} who already scored tonight '
             f'{"is" if info.get("excluded_scored", 0) == 1 else "are"} left out'
             + (f'; {info.get("final_skipped", 0)} skaters in final games skipped' if info.get('final_skipped') else '') + '.</p>'
             f'<p>{_e(CAPTION)}</p>')
    return (f'{CSS}<section class="spx" aria-label="Scorer patterns">{head}{table}{tn}<h4>Who fits the pattern · '
            f'{_e(acc.short_day(str(day)))}</h4>{body}{notes}</section>')
