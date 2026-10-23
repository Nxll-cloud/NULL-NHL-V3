"""V5.6 Matchup Center goalie view: who is in net, the opposing threats he faces (ranked by the next-goal model),
each shooter's hardest goalie (reverse view) and REAL H2H flags. Pure; inputs come from the app's cached feeds.

Goalie in net, per team, first available of:
  1. play-by-play (live/final): goalieInNetId on the latest shot against that team ('in net (PBP)')
  2. starter feed (NHL boxscore / ESPN probables via probable_goalies_v54): 'confirmed' / 'probable'
  3. the club's season games-started leader from club-stats: 'season GS leader (starter not announced)'
"""
from __future__ import annotations

import h2h_v56 as h2h
import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import probable_goalies_v54 as pgk


def _sv(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f'{f:.3f}'.lstrip('0') if f <= 1 else f'{f:.1f}'


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gaa(v):
    try:
        return f'{float(v):.2f}'
    except (TypeError, ValueError):
        return None


def _goalie(row, status):
    return {'id': int(row['Player ID']) if str(row.get('Player ID', '')).isdigit() else None, 'name': row.get('Goalie'),
            'status': status, 'sv': _sv(row.get('SV%')), 'sv_f': _num(row.get('SV%')), 'gaa': _gaa(row.get('GAA')), 'gp': row.get('GP'), 'gs': row.get('GS')}


def team_goalies(goalie_rows, team):
    return [_goalie(r, 'season') for r in goalie_rows or [] if str(r.get('Team', '')).upper() == team]


def in_net_from_pbp(game, team):
    """Latest goalieInNetId on a shot by the other club (None if no such event)."""
    for e in reversed(game.get('events') or []):
        if e.get('team') != team and e.get('goalie') is not None:
            return int(e['goalie'])
    return None


def pick_goalie(team, game, starter, goalie_rows):
    rows = [r for r in goalie_rows or [] if str(r.get('Team', '')).upper() == team]
    gid = in_net_from_pbp(game or {}, team)
    if gid is not None:
        for r in rows:
            if str(r.get('Player ID')) == str(gid):
                return _goalie(r, 'in net (PBP)')
        name = ((game or {}).get('roster') or {}).get(gid, {}).get('name') or str(gid)
        return {'id': gid, 'name': name, 'status': 'in net (PBP)', 'sv': None, 'gaa': None}
    if starter and starter.get('status') in ('confirmed', 'probable'):
        r = pgk.match_stats({**starter, 'team': team}, rows)
        if r:
            return _goalie(r, starter['status'])
        return {'id': int(starter['goalie_id']) if str(starter.get('goalie_id', '')).isdigit() else None,
                'name': starter.get('goalie'), 'status': starter['status'], 'sv': None, 'gaa': None}
    if rows:
        best = max(rows, key=lambda r: (r.get('GS') or 0, r.get('GP') or 0))
        return _goalie(best, 'season GS leader (starter not announced)')
    return None


def _shooter(p, opp):
    return {'pid': p['pid'], 'name': p['name'], 'team': p['team'], 'opp': opp, 'rank': p.get('rank'), 'p_next': p.get('p_next'),
            'headshot': p.get('headshot', ''), 'pos': p.get('pos')}


def game_view(slate_game, result, game, starters, goalie_rows, h2h_data, top=5, priors=None, situ=None):
    """priors given -> finished games rank threats by the pregame prior (see threat_result); 'phase'/'basis' are reported.
    ``situ``: the app's situational layer (_v56_situ), so that prior matches every other surface."""
    phase = result.get('phase')
    basis_txt = 'live next-goal %' if phase == 'live' else 'pregame prior'
    if priors is not None:
        result, basis_txt = threat_result(result, game or {}, priors, slate_game['away'], slate_game['home'], situ=situ)
    a, h = slate_game['away'], slate_game['home']
    pairs = (h2h_data or {}).get('pairs') or {}
    goalies = {t: pick_goalie(t, game, (starters or {}).get(t), goalie_rows) for t in (a, h)}
    players = [p for p in result['players'] if p['team'] in (a, h)]
    shooters = [_shooter(p, h if p['team'] == a else a) for p in players]
    threats = {}
    for t in (a, h):  # threats the goalie of team t faces = the other club's shooters
        opp_shooters = [s for s in shooters if s['team'] != t]
        g = goalies[t]
        threats[t] = h2h.goalie_threats(pairs, g.get('id') if g else None, opp_shooters[:top])
    reverse = []
    for s in [x for x in shooters if x['team'] == a][:top] + [x for x in shooters if x['team'] == h][:top]:
        pool = team_goalies(goalie_rows, s['opp'])
        g, basis = h2h.hardest_goalie(pairs, s['pid'], pool)
        if g is None and pool:
            ranked = [x for x in pool if x['sv_f'] is not None and (x.get('gp') or 0) >= 3] or [x for x in pool if x['sv_f'] is not None]
            if ranked:
                g, basis = max(ranked, key=lambda x: x['sv_f']), 'season SV% (H2H < 3 SOG)'
        reverse.append({**s, 'goalie': g, 'basis': basis})
    top_shooters = sorted(shooters, key=lambda s: s.get('rank') or 999)
    flags = h2h.flag_game(pairs, top_shooters, goalies, top_n=3)
    return {'goalies': goalies, 'threats': threats, 'reverse': reverse, 'flags': flags, 'phase': phase, 'basis': basis_txt}


def threat_result(result, game, priors, away=None, home=None, situ=None):
    """Ranking used for the threat lists. Once a game is over (final / shootout) live next-goal % is 0 for everyone, so the
    threats fall back to the pregame prior of the same model (no Form), labelled. Returns (result, basis).
    V5.9: the shared calculation (live_state_v56.pregame_model) with the same situational layer as the live panels."""
    if result.get('phase') in ('final', 'shootout'):
        base = lstate.pregame_model(game.get('game_id'), game.get('away') or away, game.get('home') or home, priors, situ=situ)
        ng.rerank(base['players'], None)
        return base, 'pregame prior (game over)'
    return result, 'live next-goal %' if result.get('phase') == 'live' else 'pregame prior'


_PHASE_ORDER = {'live': 0, 'pregame': 1, 'shootout': 2, 'final': 3}


def sort_games(views, by_flag):
    """views: list of (slate_game, view). by_flag -> flagged games first (most flags); else live, upcoming, then finished
    games (slate order within each). A view without 'phase' keeps its slate position."""
    if by_flag:
        return sorted(views, key=lambda gv: (-len(gv[1]['flags']), gv[0].get('start') or ''))
    return sorted(views, key=lambda gv: _PHASE_ORDER.get(gv[1].get('phase'), 1))
