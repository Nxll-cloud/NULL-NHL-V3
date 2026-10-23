"""V5.6 real-time edge flags: V5.6 next-goal model vs the opening anytime-goal line.

Math (EdgeLab's, unchanged): implied = ``edgelab_v55.american_to_implied(odds)``; edge = model_p - implied.
Model p = 1 - exp(-lambda), lambda = the player's goal expectation from the V5.6 model (``live_nextgoal_v56``):
  * pregame / pregame prior: lambda = prior shots/game x shrunk sh%  (per-game expectation, ``lam_game``; V5.8: times the
    bounded situational ratio from ``situational_v58`` when MODEL_SITUATIONAL is on - opener, threshold and UI unchanged)
  * live: lambda = r_i x remaining minutes (expectation for the rest of the game); a player who already scored is
    'settled' (the anytime prop has won) and is never flagged.
  * final / shootout (regulation + OT over; the anytime market ignores shootout goals): settled, model p is None,
    'outcome' = scored or not; nothing is flagged.
Form % is NOT used (it is an index, not a probability).

Opening line: the earliest-timestamped anytime-goal quote per player in the loaded quotes (Odds API snapshot and/or CSV),
averaged over books at that timestamp. The Odds API's current-odds endpoint has no historical openers, so this is
'earliest observed', and the UI says so. With no key and no CSV the DEMO set below is used, labelled DEMO everywhere.
Moneyline flags are not produced: the model has no win-probability component.
"""
from __future__ import annotations

import math

import pandas as pd

import edgelab_v55 as el
import live_nextgoal_v56 as lm

MIN_EDGE = 0.03
DEMO_LABEL = 'DEMO opening lines — synthetic, not sportsbook prices'
DEMO_VIG = 0.05
ANYTIME_MARKETS = ('player_goal_scorer_anytime', 'anytime goal', 'anytime goalscorer', 'anytime goal scorer')


def implied_to_american(p):
    p = min(0.95, max(0.02, float(p)))
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def demo_line(goals_pg):
    """Deterministic DEMO price: season goals/game blended with a 0.30 baseline, +5% vig. Clearly not a real price."""
    lam = 0.6 * max(0.0, float(goals_pg or 0)) + 0.4 * 0.30
    p = min(0.6, max(0.08, 1 - math.exp(-lam))) * (1 + DEMO_VIG)
    return implied_to_american(p)


def _norm(name):
    return ' '.join(str(name or '').replace('.', ' ').split()).casefold()


def opening_lines(quotes):
    """quotes DataFrame (player, market, american_odds, updated_at, sportsbook) -> {player_casefold: line dict}."""
    if not isinstance(quotes, pd.DataFrame) or quotes.empty or not {'player', 'american_odds'}.issubset(quotes.columns):
        return {}
    q = quotes.copy()
    if 'market' in q.columns:
        m = q['market'].astype(str).str.lower()
        q = q[m.apply(lambda s: any(k in s for k in ANYTIME_MARKETS))]
    if q.empty:
        return {}
    q['_t'] = pd.to_datetime(q.get('updated_at'), errors='coerce', utc=True)
    out = {}
    for player, grp in q.groupby(q['player'].map(_norm)):
        first = grp[grp['_t'] == grp['_t'].min()] if grp['_t'].notna().any() else grp
        imps = []
        for o in first['american_odds']:
            try:
                imps.append(el.american_to_implied(float(o)))
            except (el.EdgeLabError, TypeError, ValueError):
                continue
        if not imps:
            continue
        imp = sum(imps) / len(imps)
        t = first['_t'].min()
        out[player] = {'implied': imp, 'american': implied_to_american(imp), 'books': len(imps),
                       'at': None if pd.isna(t) else t.isoformat(), 'source': 'quotes'}
    return out


def demo_lines(priors):
    return {_norm(p['name']): {'implied': el.american_to_implied(demo_line(p['goals'] / p['gp'] if p['gp'] else 0)),
                               'american': demo_line(p['goals'] / p['gp'] if p['gp'] else 0), 'books': 0, 'at': None, 'source': 'DEMO'}
            for p in priors.values() if p.get('name')}


def player_lambda(rec, phase_name, remaining):
    if phase_name in ('final', 'shootout'):  # regulation/OT is over; the anytime market excludes shootout goals
        return None
    if phase_name == 'live':
        return max(0.0, rec.get('rate', 0.0)) * max(0.0, remaining)
    return lm.per_game_lambda(rec)


def edges_for_game(result, lines, min_edge=MIN_EDGE, top_n=None):
    """Model result (live_nextgoal_v56.model) + opening lines -> rows sorted by next-goal rank."""
    rows = []
    ph, rem = result['phase'], result['remaining']
    for rec in result['players'][:top_n] if top_n else result['players']:
        line = lines.get(_norm(rec['name']))
        lam = player_lambda(rec, ph, rem)
        over = ph in ('final', 'shootout')
        settled = (ph == 'live' and rec.get('goals', 0) > 0) or over
        p = None if lam is None else lm.p_anytime(lam)
        edge = None if (p is None or line is None or settled) else p - line['implied']
        rows.append({'pid': rec['pid'], 'name': rec['name'], 'team': rec['team'], 'rank': rec.get('rank'), 'delta': rec.get('delta'),
                     'lambda': lam, 'model_p': p, 'implied': None if line is None else line['implied'],
                     'american': None if line is None else line['american'], 'line_source': None if line is None else line['source'],
                     'edge': edge, 'settled': settled, 'outcome': (rec.get('goals', 0) > 0) if over or settled else None, 'flag': edge is not None and edge >= min_edge, 'headshot': rec.get('headshot', '')})
    return rows


def game_flag(rows):
    """Pair the game with its top-ranked shooter; the game is flagged when that shooter's edge clears the threshold."""
    top = rows[0] if rows else None
    others = [r for r in rows[1:] if r['flag']]
    return {'top': top, 'flagged': bool(top and top['flag']), 'other_flags': others}


def remember_openers(store, lines):
    """Keep the FIRST line seen per player (store persists across reruns/refreshes for the slate day)."""
    for k, v in (lines or {}).items():
        store.setdefault(k, v)
    return store
