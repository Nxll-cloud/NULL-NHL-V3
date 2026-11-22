"""V6.2 Anytime goal · tonight's patterns (EdgeLab page): P(scores 1+ goal tonight) for every skater still in play.

Replaces the experimental gematria Blend (retired from Prediction Models) and, since t233, is the ONLY content of the
EdgeLab tab. Display only: nothing here feeds the model, the NP ranks, the threat score (J=2, D=3, A=2, T=1), the
parlay, Edge Flags, the Home price-gap leader or any log.

How a probability is made (all inputs real; nothing guessed):
 1. Recent-games prior. Over the last WINDOW scored nights, each skater's PRE-GAME traits (saved slate snapshot: shot
    volume, shot trend, recent goals, prior goals/game, Form rank, position, home, opponent GA/G and SA/G; NHL score feed:
    PP goals, points and assists in the 7 days before) plus the app Model's own pre-game anytime-goal chance (as a logit)
    are fitted JOINTLY by an L2-regularised logistic regression against who really scored. A joint fit counts overlapping
    traits once (a star matching shots + hot + top-50 does not get three separate boosts) and lets a rarer, more specific
    trait carry its own weight. Weights are re-fitted whenever a new night is scored.
 2. Tonight's scorers (primary live input). Skaters in games already underway or final are tonight's training signal:
    scorers (y = 1) vs non-scorers weighted by the share of the game played so far. Their shared traits update every
    weight through a Gaussian prior centred on the recent-games fit (MAP, strength TAU), so 2-3 early goals barely move
    it and a full early window moves it more. The effective share of tonight's data is shown.
 3. Remaining chance. Unstarted games: the full-game probability. In-progress games: 1 - (1 - p)^(minutes left / 60).
    Live context (assists, shots tonight, a goalie who has allowed 3+) is shown as chips but NOT added to the
    probability (not validated). Players who already scored tonight are listed separately.
Walk-forward check (train on prior nights, test on later games of each night using earlier games as 'tonight so far'):
see CHANGELOG (V6.2 anytime-goal engine). It is an estimate, not a guarantee; calibration is checked in buckets there.
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
MIN_N = 100          # descriptive trait table: player-nights with the trait
MIN_K = 15           # descriptive trait table: scorers with the trait
MIN_LIFT = 1.2
MIN_GP = 3           # skaters need this many prior games (training and tonight)
LAM = 50.0           # L2 strength of the recent-games fit (walk-forward pick)
TAU = 100.0          # prior strength for tonight's update (walk-forward pick; see CHANGELOG / BACKTEST_NOTE)
TOP = 20
TONIGHT_MIN_SCORERS = 3
P_FALLBACK = 0.12
FORWARDS = ('C', 'L', 'R', 'LW', 'RW', 'F')
_FEED = _rg.BoundedTTL({'final': 6 * 3600, 'live': 60, 'fail': 120}, cap=40)

CAPTION = ('Estimated chance each skater still in play scores at least one goal tonight. Built from a joint fit on the last '
           'scored nights (pre-game traits + the app Model’s chance, overlapping traits counted once), updated by the traits '
           'shared by tonight’s scorers so far, then scaled to the minutes left. An estimate, not a guarantee; display only.')


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
        per = (g.get('periodDescriptor') or {}).get('number') or g.get('period') or 0
        left = (g.get('clock') or {}).get('secondsRemaining')
        el = None
        if per:
            el = min(60.0, (min(int(per), 3) - 1) * 20 + (20 - (left or 0) / 60 if int(per) <= 3 else 20))
        games[gid] = {'state': str(g.get('gameState') or ''), 'away': (g.get('awayTeam') or {}).get('abbrev', ''),
                      'home': (g.get('homeTeam') or {}).get('abbrev', ''), 'elapsed': el}
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



def tonight_live(feed, pbp=None):
    """Tonight's score feed (+ optional parsed play-by-play) -> live context.
    {'states': {team: state}, 'goals': n, 'scorers': {pid: goals}, 'assists': {pid: n}, 'situations': {...},
     'team_pp': {team: n}, 'allowed': {team: goals allowed excl. EN}, 'goalie': {team: (goalie name, allowed)},
     'shots': {pid: SOG}}"""
    lv = {'states': {}, 'goals': 0, 'scorers': defaultdict(int), 'assists': defaultdict(int), 'situations': defaultdict(int),
          'team_pp': defaultdict(int), 'allowed': defaultdict(int), 'goalie': {}, 'shots': defaultdict(int), 'elapsed': {}}
    team_of_game = {}
    for gid, g in ((feed or {}).get('games') or {}).items():
        for side in ('away', 'home'):
            lv['states'][g[side]] = g['state']
            lv['elapsed'][g[side]] = g.get('elapsed')
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



# ------------------------------------------------------------------------------------------------ recent window
KEYS = [k for k, *_ in TRAITS]


def _logit(p):
    p = min(max(float(p), 1e-3), 0.999)
    return math.log(p / (1 - p))


def _vec(t, mp=None, use_model=True):
    v = [1.0] + [1.0 if t.get(k) else 0.0 for k in KEYS]
    if use_model:
        v.append(_logit(P_FALLBACK if mp is None else mp))
    return v


def night_rows(day, acc, snap, prior=None):
    """One scored night -> [{'t','y','pos','mp'}] for skaters (MIN_GP+ prior games) on that night's played games."""
    res = (acc or {}).get('results') or {}
    if not res.get('scorers') or not snap:
        return []
    gids = {str(g) for g in acc.get('games') or []}
    home = {}
    for g in snap.get('games') or []:
        if not gids or str(g.get('Game ID')) in gids:
            home[g.get('Home')], home[g.get('Away')] = True, False
    scorers = {_pid(s[0]) for s in res['scorers']}
    mp = {}
    for p in acc.get('players') or []:
        try:
            mp[int(p[0])] = float(p[3])
        except (TypeError, ValueError, IndexError):
            continue
    out = []
    for r in snap.get('rankings') or []:
        if r.get('Team') not in home or _pid(r.get('Player ID')) is None or (_f(r.get('Prior GP')) or 0) < MIN_GP:
            continue
        ft = features(r, home[r['Team']], prior)
        out.append({'t': traits_of(ft), 'y': ft['pid'] in scorers, 'pos': ft['pos'], 'mp': mp.get(ft['pid'])})
    return out


def load_window(day, acc_dir=None, snap_dir=None, feeds=None, getter=None, n=WINDOW):
    """-> (rows, nights, feeds). Reads one snapshot at a time and keeps only compact rows."""
    acc_dir, snap_dir = Path(acc_dir or ACC_DIR), Path(snap_dir or SNAP_DIR)
    rows, nights, picked = [], [], []
    for d in reversed(window_days(day, acc_dir, n)):
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


def fit(X, y, lam=LAM, w0=None, tau=None, wts=None):
    """Logistic regression by Newton steps. Ridge (lam, intercept free) when w0 is None, else MAP with a Gaussian
    prior N(w0, 1/tau) on every weight. Returns (weights, effective share of this data vs the prior)."""
    import numpy as np
    X, y = np.asarray(X, float), np.asarray(y, float)
    n, p = X.shape
    wts = np.ones(n) if wts is None else np.asarray(wts, float)
    if w0 is None:
        R = lam * np.eye(p)
        R[0, 0] = 0.0
        c = np.zeros(p)
        base = min(max((wts * y).sum() / max(wts.sum(), 1e-9), 1e-3), 0.999)
        w = np.zeros(p)
        w[0] = math.log(base / (1 - base))
    else:
        R, c = tau * np.eye(p), np.asarray(w0, float)
        w = c.copy()
    for _ in range(40):
        pr = 1 / (1 + np.exp(-(X @ w)))
        g = X.T @ (wts * (pr - y)) + R @ (w - c)
        H = (X * (wts * pr * (1 - pr))[:, None]).T @ X + R
        step = np.linalg.solve(H, g)
        w = w - step
        if np.abs(step).max() < 1e-9:
            break
    pr = 1 / (1 + np.exp(-(X @ w)))
    Hd = float(np.trace((X * (wts * pr * (1 - pr))[:, None]).T @ X))
    return w, (Hd / (Hd + float(np.trace(R))) if np.trace(R) else 1.0)


def build_patterns(day, acc_dir=None, snap_dir=None, feeds=None, getter=None):
    """Recent-games prior -> {'status','stats','profile','feeds','day','w_model','w_traits'} (weights as lists)."""
    rows, nights, feeds = load_window(day, acc_dir, snap_dir, feeds, getter)
    prof = recent_profile([(r['t'], r['y'], r['pos']) for r in rows], nights, feeds)
    out = {'stats': learn([(r['t'], r['y'], r['pos']) for r in rows]) if rows else [], 'profile': prof, 'feeds': feeds,
           'day': str(day), 'w_model': None, 'w_traits': None}
    if len(nights) < MIN_NIGHTS or prof['K'] < MIN_SCORERS:
        return dict(out, status='insufficient')
    y = [1.0 if r['y'] else 0.0 for r in rows]
    have = [r for r in rows if r['mp'] is not None]
    out['w_traits'] = [float(x) for x in fit([_vec(r['t'], use_model=False) for r in rows], y)[0]]
    if len(have) >= 0.8 * len(rows):
        out['w_model'] = [float(x) for x in fit([_vec(r['t'], r['mp']) for r in have], [1.0 if r['y'] else 0.0 for r in have])[0]]
    return dict(out, status='ok')


# ------------------------------------------------------------------------------------------------ tonight
def _game_clock(results):
    """_v56_results -> {team: (phase, elapsed min, remaining min)} and {pid: pre-game model p}."""
    from live_nextgoal_v56 import p_anytime
    clock, mp = {}, {}
    for r in results or []:
        s, res = r.get('slate') or {}, r.get('result') or {}
        ph = res.get('phase') or 'pregame'
        el, rem = _f(res.get('elapsed')), _f(res.get('remaining'))
        for t in (s.get('away'), s.get('home')):
            if t:
                clock[t] = (ph, el, rem)
        for rec in res.get('players') or []:
            p = _pid(rec.get('pid'))
            if p is not None and rec.get('lam_game') is not None:
                mp[p] = p_anytime(rec.get('lam_game'))
    return clock, mp


def _phase(team, clock, lv, games):
    if team in clock:
        ph = clock[team][0]
        return 'final' if ph in ('final', 'shootout') else ('live' if ph == 'live' else 'pregame')
    st_ = lv['states'].get(team) or next((g.get('Status') for g in games or [] if team in (g.get('Home'), g.get('Away'))), '')
    return _state_phase(st_)


def tonight_rows(rankings, games, patterns, lv, results=None, frozen=None):
    """Every slate skater (MIN_GP+) -> dict with traits, phase, minutes, pre-game model p and tonight goals."""
    clock, mp = _game_clock(results)
    for p in (frozen or {}).get('players') or []:
        try:
            mp.setdefault(int(p[0]), float(p[3]))
        except (TypeError, ValueError, IndexError):
            continue
    prior = prior_totals(patterns.get('day') or '', patterns.get('feeds') or {}) if patterns.get('day') else None
    home = {}
    for g in games or []:
        home[g.get('Home')], home[g.get('Away')] = True, False
    out = []
    for r in rankings or []:
        pid, team = _pid(r.get('Player ID')), r.get('Team')
        if pid is None or team not in home or (_f(r.get('Prior GP')) or 0) < MIN_GP:
            continue
        ft = features(r, home[team], prior)
        ph = _phase(team, clock, lv, games)
        el, rem = (clock.get(team) or (None, lv.get('elapsed', {}).get(team), None))[1:]
        if ph == 'final':
            el, rem = 60.0, 0.0
        elif ph == 'pregame':
            el, rem = 0.0, 60.0
        else:
            el = 30.0 if el is None else min(max(el, 0.0), 60.0)
            rem = max(0.0, 60.0 - el) if rem is None else max(0.0, rem)
        out.append({'pid': pid, 'name': ft['name'], 'team': team, 'opp': ft['opp'], 'pos': ft['pos'], 'phase': ph,
                    'elapsed': el, 'remaining': rem, 'mp': mp.get(pid), 't': traits_of(ft), 'feat': ft,
                    'goals': int(lv['scorers'].get(pid, 0))})
    return out


def update_tonight(patterns, rows, tau=TAU):
    """Tonight's started games as training signal -> {'w_model','w_traits','eff','n_sig','k_sig'}: scorers y=1 (weight 1),
    non-scorers y=0 weighted by the share of their game played. Few scorers -> weights stay near the prior."""
    sig = [r for r in rows if r['phase'] in ('live', 'final') and (r['elapsed'] or 0) > 0]
    k = sum(1 for r in sig if r['goals'])
    out = {'w_model': patterns.get('w_model'), 'w_traits': patterns.get('w_traits'), 'eff': 0.0, 'n_sig': len(sig), 'k_sig': k}
    if k < TONIGHT_MIN_SCORERS or not patterns.get('w_traits'):
        return out
    y = [1.0 if r['goals'] else 0.0 for r in sig]
    wts = [1.0 if r['goals'] else min(1.0, (r['elapsed'] or 0) / 60.0) for r in sig]
    w, eff = fit([_vec(r['t'], use_model=False) for r in sig], y, w0=patterns['w_traits'], tau=tau, wts=wts)
    out['w_traits'], out['eff'] = [float(x) for x in w], eff
    if patterns.get('w_model'):
        w, eff = fit([_vec(r['t'], r['mp']) for r in sig], y, w0=patterns['w_model'], tau=tau, wts=wts)
        out['w_model'], out['eff'] = [float(x) for x in w], eff
    return out


def prob_full(row, weights):
    """Full-game P(1+ goal) for one tonight row with the (updated) weights; uses the model-p fit when p is known."""
    if weights.get('w_model') and row.get('mp') is not None:
        w, v = weights['w_model'], _vec(row['t'], row['mp'])
    else:
        w, v = weights['w_traits'], _vec(row['t'], use_model=False)
    z = sum(a * b for a, b in zip(w, v))
    return 1 / (1 + math.exp(-z))


def predict(rows, weights, lv=None, top=TOP):
    """Remaining skaters (unstarted / in progress, not yet scored) -> (rows sorted by P remaining, info)."""
    out, final, scored = [], 0, 0
    for r in rows:
        if r['phase'] == 'final':
            final += 1
            continue
        if r['goals']:
            scored += 1
            continue
        p = prob_full(r, weights)
        frac = 1.0 if r['phase'] == 'pregame' else max(0.0, min(1.0, (r['remaining'] or 0) / 60.0))
        pr = 1 - (1 - p) ** frac
        out.append(dict(r, p_full=p, p=pr, chips=[SHORT[k] for k in KEYS if r['t'].get(k)],
                        live=live_signals(r['feat'], lv) if lv else []))
    out.sort(key=lambda x: (-x['p'], str(x['name']), x['pid']))
    return out[:top], {'final_skipped': final, 'scored': scored, 'candidates': len(out)}


def live_signals(feat, lv):
    """Live context chips for one in-progress skater (shown, NOT part of the probability)."""
    pid, team, out = feat['pid'], feat['team'], []
    if _state_phase(lv['states'].get(team)) != 'live':
        return out
    if lv['assists'].get(pid):
        out.append(f'Assisted tonight ({lv["assists"][pid]})')
    if lv['shots'].get(pid, 0) >= 3:
        out.append(f'{lv["shots"][pid]} SOG tonight')
    gk = lv['goalie'].get(team)
    if gk and gk[1] >= 3:
        out.append(f'Facing {gk[0]} ({gk[1]} allowed)')
    return out


def scorer_profile(rows):
    """Tonight's scorers so far (in the slate list) + their shared traits vs exposure-weighted non-scorers in started games.
    -> (scorers [{'name','team','goals','chips'}], [(short label, scorer share, others share)])."""
    sig = [r for r in rows if r['phase'] in ('live', 'final') and (r['elapsed'] or 0) > 0]
    sc = [r for r in sig if r['goals']]
    oth = [(r, min(1.0, (r['elapsed'] or 0) / 60.0)) for r in sig if not r['goals']]
    tw = sum(w for _r, w in oth) or 1.0
    shared = []
    for k in KEYS:
        if not sc:
            break
        a = sum(1 for r in sc if r['t'].get(k)) / len(sc)
        b = sum(w for r, w in oth if r['t'].get(k)) / tw
        shared.append((SHORT[k], a, b))
    shared.sort(key=lambda x: -(x[1] - x[2]))
    scorers = sorted(({'name': r['name'], 'team': r['team'], 'goals': r['goals'], 'pos': r['pos'],
                       'chips': [SHORT[k] for k in KEYS if r['t'].get(k)]} for r in sc), key=lambda x: (-x['goals'], str(x['name'])))
    return scorers, shared


# ------------------------------------------------------------------------------------------------ html
BACKTEST_NOTE = ('Walk-forward check, 19 saved nights (later games of each night, earlier games as "tonight so far"): '
                 'log loss 0.3530 vs 0.3552 for the app Model alone, AUC 0.712 vs 0.706, top-10 hits 59/190 vs 55/190 '
                 '(old pattern-fit list 48/190). Giving tonight’s scorers a much larger say made it worse (log loss 0.3623), '
                 'so their update is kept modest.')

CSS = ('<style>.v55 .spx{margin:10px 0;padding:12px 14px;border-radius:18px;border:1px solid color-mix(in srgb,#3dffa8 34%,transparent);'
       'background:linear-gradient(135deg,rgba(61,255,168,.06),rgba(56,225,255,.06));min-width:0;overflow-wrap:anywhere}'
       '.v55 .spx h4{margin:12px 0 4px;color:var(--ink);font:800 .82rem var(--fd);letter-spacing:.08em;text-transform:uppercase}'
       '.v55 .spx p{margin:4px 0;color:var(--mut);font-size:.8rem;line-height:1.45}.v55 .spx b{color:var(--ink)}'
       '.v55 .spx .spk{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}'
       '.v55 .spx .spk span{padding:3px 9px;border-radius:999px;font-size:.72rem;color:var(--ink);border:1px solid var(--line);background:rgba(255,255,255,.03)}'
       '.v55 .spx .sps{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}'
       '.v55 .spx table{width:100%;border-collapse:collapse;font-size:.8rem;color:var(--ink);font-variant-numeric:tabular-nums}'
       '.v55 .spx th{padding:4px 5px;text-align:left;color:var(--mut);font:700 .7rem var(--fb);letter-spacing:.05em;text-transform:uppercase;border-bottom:1px solid var(--line)}'
       '.v55 .spx td{padding:5px;border-bottom:1px solid var(--line);vertical-align:top}.v55 .spx td.n{text-align:right;white-space:nowrap}'
       '.v55 .spr{display:grid;grid-template-columns:2em minmax(0,1fr) auto;gap:4px 8px;padding:7px 0;border-top:1px solid var(--line);align-items:start}'
       '.v55 .spr .rk{color:var(--mut);font-weight:800}.v55 .spr .nm b{font-weight:700}.v55 .spr .nm small{color:var(--dim);margin-left:5px;font-size:.72rem}'
       '.v55 .spr .ft{font-weight:800;color:#3dffa8;white-space:nowrap;text-align:right;font-size:1rem}'
       '.v55 .spr .ft small{display:block;color:var(--dim);font-weight:600;font-size:.66rem}'
       '.v55 .spr .ch{grid-column:2/4;display:flex;flex-wrap:wrap;gap:4px}'
       '.v55 .spr .ch span{padding:1px 7px;border-radius:999px;font-size:.68rem;color:var(--mut);border:1px solid var(--line)}'
       '.v55 .spr .ch span.lv{color:#1a0710;border-color:transparent;background:linear-gradient(90deg,#38e1ff,#3dffa8)}'
       '.v55 .spr .ch span.nu{color:#e6dcff;border-color:rgba(155,92,255,.55);background:rgba(155,92,255,.16)}'
       '.v55 .spx p.spn{color:#e6dcff;padding:5px 9px;border-radius:10px;background:rgba(155,92,255,.12);border:1px solid rgba(155,92,255,.35)}'
       '.v55 .spr .lvp{font-size:.66rem;font-weight:800;color:#ff3d7f;margin-left:5px}'
       '.v55 .spr.sc .nm b{color:var(--ok,#3dffa8)}'
       '@media (max-width:420px){.v55 .spx{padding:10px}.v55 .spx th,.v55 .spx td{padding:4px 3px}.v55 .spx .hide-sm{display:none}}</style>')


def _pct(x, nd=0):
    return '—' if x is None else f'{100 * x:.{nd}f}%'


def _rawlift(s):
    return '—' if not s or s.get('lift') is None else f'{s["lift"]:.2f}×'


def _odds(w):
    return f'{math.exp(w):.2f}×'


def section_html(patterns, preds, info, weights, scorers, shared, lv, day, num_head='', empty_msg=None):
    """num_head / empty_msg / row 'num' + 'rank': numerology overlay (numerology_overlay_v62), display only; absent = unchanged."""
    import accuracy_v58 as acc
    prof = patterns.get('profile') or {}
    nights = prof.get('nights') or []
    span = f'{acc.short_day(nights[0])} – {acc.short_day(nights[-1])}' if nights else 'no nights'
    if patterns.get('status') == 'insufficient':
        return (f'{CSS}<section class="spx" aria-label="Anytime goal tonight"><p><b>Not enough scored nights yet</b> '
                f'({len(nights)} of {MIN_NIGHTS} needed, {prof.get("K", 0)} of {MIN_SCORERS} scorers). No probabilities are shown '
                f'rather than guessing.</p></section>')
    eff, k_sig = weights.get('eff') or 0.0, weights.get('k_sig') or 0
    head = (f'<div class="spk"><span>Recent fit: <b>{len(nights)}</b> nights ({_e(span)}), <b>{prof.get("K", 0)}</b> scorers / '
            f'{prof.get("N", 0)} skater-games</span><span>Tonight: <b>{lv.get("goals", 0)}</b> goals, <b>{k_sig}</b> scorers on the slate list</span>'
            f'<span>Tonight’s share of the weights: <b>{_pct(eff)}</b>'
            + ('' if k_sig >= TONIGHT_MIN_SCORERS else f' (starts at {TONIGHT_MIN_SCORERS} scorers)') + '</span></div>')
    # remaining players
    if not preds:
        body = f'<p>{_e(empty_msg)}</p>' if empty_msg else '<p>No skaters left to estimate (every game is final, or the slate list is not loaded yet).</p>'
    else:
        def _row(i, r):
            live = (f'<span class="lvp">LIVE · {r["remaining"]:.0f} min left</span>' if r['phase'] == 'live' else '')
            sub = (f'full game {_pct(r["p_full"])}' if r['phase'] == 'live' else '') + \
                  (f'{" · " if r["phase"] == "live" else ""}Model {_pct(r["mp"])}' if r.get('mp') is not None else ' · no Model p')
            return (f'<div class="spr"><span class="rk">{r.get("rank", i)}</span><span class="nm"><b>{_e(r["name"])}</b><small>{_e(r["pos"])} · '
                    f'{_e(r["team"])}{" vs " + _e(r["opp"]) if r.get("opp") else ""}</small>{live}</span>'
                    f'<span class="ft">{_pct(r["p"])}<small>{_e(sub)}</small></span><span class="ch">'
                    + ''.join(f'<span>{_e(c)}</span>' for c in r['chips']) + ''.join(f'<span class="lv">{_e(c)}</span>' for c in r['live'])
                    + ''.join(f'<span class="nu">{_e(c)}</span>' for c in r.get('num') or ())
                    + '</span></div>')
        body = ''.join(_row(i, r) for i, r in enumerate(preds, 1))
    # tonight's scorers
    if scorers:
        sc = ''.join(f'<div class="spr sc"><span class="rk">🚨</span><span class="nm"><b>{_e(s["name"])}</b><small>{_e(s["pos"])} · '
                     f'{_e(s["team"])}{" · " + str(s["goals"]) + "G" if s["goals"] > 1 else ""}</small></span><span class="ft"></span>'
                     f'<span class="ch">' + ''.join(f'<span>{_e(c)}</span>' for c in s['chips']) + '</span></div>' for s in scorers)
        sh = ('<p>Shared traits: share of tonight’s scorers vs other skaters in started games (time-weighted):</p><div class="spk">'
              + ''.join(f'<span>{_e(lab)} <b>{_pct(a)}</b> vs {_pct(b)}</span>' for lab, a, b in shared[:8]) + '</div>')
        sits = lv.get('situations') or {}
        tn = (f'<h4>Tonight’s scorers so far · primary live input</h4><p>{lv.get("goals", 0)} goals'
              + (' · ' + ' · '.join(f'{k} {v}' for k, v in sorted(sits.items(), key=lambda kv: -kv[1])) if sits else '')
              + ('' if lv.get('feed_ok', True) else ' · live score feed unavailable') + '. Left out of the list above.</p>' + sh + sc)
    else:
        tn = ('<h4>Tonight’s scorers so far · primary live input</h4><p>No goals yet on tonight’s slate: estimates use the '
              'recent-games fit only. They update as goals come in.</p>')
    # weights
    pw, tw = patterns.get('w_model') or patterns.get('w_traits'), weights.get('w_model') or weights.get('w_traits')
    lift = {s['key']: s for s in patterns.get('stats') or []}
    trs = ''.join(f'<tr><td>{_e(TRAIT[k][0])}</td><td class="n">{_odds(pw[i + 1])}</td><td class="n">{_odds(tw[i + 1])}</td>'
                  f'<td class="n hide-sm">{_rawlift(lift.get(k))}</td></tr>' for i, k in enumerate(KEYS)) if pw and tw else ''
    wt = ('<h4>What the fit weighs</h4><p>Odds multiplier per trait from the joint fit (other traits and the Model held fixed, '
          'so overlap counts once); raw lift is the trait on its own.</p><div class="sps"><table><thead><tr><th>Trait</th><th>Recent fit</th>'
          f'<th>With tonight</th><th class="hide-sm">Raw lift</th></tr></thead><tbody>{trs}</tbody></table></div>') if trs else ''
    notes = (f'<p>{info.get("scored", 0)} skater{"s" if info.get("scored", 0) != 1 else ""} who already scored '
             f'{"is" if info.get("scored", 0) == 1 else "are"} listed under tonight’s scorers; '
             f'{info.get("final_skipped", 0)} in final games are skipped. Live chips are context only, not in the %.</p>'
             f'<p>{_e(CAPTION)}</p>' + (f'<p>{_e(BACKTEST_NOTE)}</p>' if BACKTEST_NOTE else ''))
    return (f'{CSS}<section class="spx" aria-label="Anytime goal tonight">{head}<h4>Most likely to score · '
            f'{_e(acc.short_day(str(day)))} · still in play</h4>{num_head}{body}{tn}{wt}{notes}</section>')
