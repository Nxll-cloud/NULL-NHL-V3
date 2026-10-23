"""V5.5: build the Home/Matchup design state from the app's LIVE data (the same objects and selection
functions the V5.4 tabs use). Pure except for the two injectable fetchers (rosters for jersey numbers,
last-10 game logs for sparklines); every fetch failure degrades to 'no jersey' / 'game log unavailable'."""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import matchup_center_v54 as mc
import probable_goalies_v54 as pgk
import ui_theme_v53 as ui
from player_intelligence_v54 import LEADER_LABELS

NHL_ROSTER = 'https://api-web.nhle.com/v1/roster/{team}/current'
NHL_GAMELOG = 'https://api-web.nhle.com/v1/player/{pid}/game-log/{season}/2'


def fetch_roster_numbers(team, getter, timeout=10):
    """{player_id: sweater number} for one club. getter = requests.get-like."""
    r = getter(NHL_ROSTER.format(team=team), timeout=timeout)
    r.raise_for_status()
    j = r.json() or {}
    out = {}
    for grp in ('forwards', 'defensemen', 'goalies'):
        for p in j.get(grp) or []:
            if p.get('id') is not None and p.get('sweaterNumber') is not None:
                out[str(p['id'])] = p['sweaterNumber']
    return out


def fetch_game_log(pid, season, getter, timeout=10, last=10):
    r = getter(NHL_GAMELOG.format(pid=pid, season=season), timeout=timeout)
    r.raise_for_status()
    gl = sorted((r.json() or {}).get('gameLog') or [], key=lambda g: str(g.get('gameDate')))[-last:]
    return [{'date': g.get('gameDate'), 'opp': g.get('opponentAbbrev'), 'shots': g.get('shots') or 0,
             'goals': g.get('goals') or 0, 'points': g.get('points') or 0} for g in gl]


def safe_many(fn, keys, workers=8):
    """Run fn over keys in parallel; failures become missing entries (never raise)."""
    keys = [k for k in dict.fromkeys(keys) if k]
    out, errors = {}, []
    if not keys:
        return out, errors
    with ThreadPoolExecutor(max_workers=min(workers, len(keys))) as pool:
        futs = {k: pool.submit(fn, k) for k in keys}
        for k, f in futs.items():
            try:
                out[k] = f.result()
            except Exception as exc:  # network/HTTP/JSON
                errors.append(f'{k}: {type(exc).__name__}')
    return out, errors


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _pid(v):
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return ''


def _gline(g):
    return None if not g else {k: g.get(k) for k in ('Goalie', 'Player ID', 'Team', 'GP', 'GS', 'GA', 'GAA', 'SV%', 'Position')}


def track_summary(evals, rolling):
    """Real tracker evaluations -> ring/trend data. No graded slates -> empty rings (never demo numbers)."""
    evals = evals or []
    graded = sorted((e for e in evals if e.get('status') == 'evaluated'), key=lambda e: e['day'])
    return {'r7': rolling(evals, 7), 'r30': rolling(evals, 30), 'all': rolling(evals),
            'pending': sum(1 for e in evals if e.get('status') == 'pending'),
            'demo': any(e.get('demo') for e in evals),
            'trend': [{'day': e['day'], 'rate': e.get('hit_rate'), 'hits': len(e.get('hits') or []), 'picks': e.get('picks', 0)} for e in graded][-14:]}


def build_state(*, day, season, games, ranked=None, targets=None, leaders=None, picks=None, ranked_with_stat=None,
                goalie_rows=None, starters=None, starters_fetched_at=None, discrepancies=None, track=None,
                snapshot_at=None, rosters_fn=None, logs_fn=None, price_label=str, track_badges=None):
    """Assemble the dict v55_ui.render_home consumes.

    games: raw slate rows (Away/Home/Start (UTC)/Status...) · leaders: home_leaders_v52.choose_leaders output
    picks: player_intelligence_v54.four_picks output · ranked_with_stat: assign_statistical_ranks(ranked)
    rosters_fn(teams) -> ({team: {pid: number}}, errors); logs_fn(pids) -> ({pid: [games]}, errors).
    Both optional; any exception from them degrades to no jerseys / 'game log unavailable'."""
    mg = mc.slate_games(games)
    leaders = leaders or {}
    picks = picks or {}
    lead = leaders.get('statistical')
    fg = None
    if lead:
        fg = mc.game_for_pick({'Team': lead.get('team'), 'opponent': lead.get('opponent')}, games)
    if fg is None and mg:
        fg = mg[0]
    rows = {}
    if isinstance(ranked, pd.DataFrame) and not ranked.empty and 'Player ID' in ranked:
        for _, r in ranked.iterrows():
            rows.setdefault(_pid(r.get('Player ID')), r.to_dict())
    srank = {}
    if isinstance(ranked_with_stat, pd.DataFrame) and not ranked_with_stat.empty and 'Statistical rank' in ranked_with_stat:
        for _, r in ranked_with_stat.iterrows():
            rk = pd.to_numeric(r.get('Statistical rank'), errors='coerce')
            if pd.notna(rk):
                srank[_pid(r.get('Player ID'))] = int(rk)
    pick_ids = [p.get('Player ID') for p in picks.values() if p]
    tg = mc.matchup_targets(targets or [], fg, ranked_with_stat, discrepancies, track_badges, pick_ids) if fg else {}
    weak = mc.weaker_goalie_side(goalie_rows or [], fg) if fg else None

    need_teams = ({fg['away'], fg['home']} if fg else set()) | {p.get('team') for p in leaders.values() if p} | {p.get('Team') for p in picks.values() if p}
    ids = {_pid(p.get('player_id')) for p in leaders.values() if p} | {_pid(p.get('Player ID')) for p in picks.values() if p}
    for lst in tg.values():
        ids |= {_pid(p.get('player_id')) for p in lst[:5]}
    jersey, errs = {}, []
    if rosters_fn:
        try:
            got, e = rosters_fn(tuple(sorted(t for t in need_teams if t)))
        except Exception as exc:
            got, e = {}, [f'rosters: {type(exc).__name__}']
        errs += list(e)
        for m in got.values():
            jersey.update({str(k): v for k, v in (m or {}).items()})
    logs = {}
    if logs_fn:
        try:
            logs, e = logs_fn(tuple(sorted(i for i in ids if i)))
        except Exception as exc:
            logs, e = {}, [f'game logs: {type(exc).__name__}']
        errs += list(e)

    def enrich(pid):
        r = rows.get(_pid(pid), {})
        idx = r.get('V3.2 Adjusted Index')
        return {'jersey': jersey.get(_pid(pid)), 'log': logs.get(_pid(pid)) or [], 'form_pct': ui.form_pct(idx), 'form_label': ui.format_form_pct(idx),
                'stat_rank': srank.get(_pid(pid)), 'shots_l5': _num(r.get('Shots/G L5')), 'goals_l5': _num(r.get('Goals/G L5')), 'position': r.get('Position')}

    out_leaders = {}
    for k, p in leaders.items():
        if not p:
            out_leaders[k] = None
            continue
        d = {x: p.get(x) for x in ('player', 'player_id', 'team', 'opponent', 'matches', 'form', 'gap_pct', 'best_sportsbook')}
        d.update(day_n=len(p.get('day') or []), team_n=len(p.get('team_matches') or []), arena_n=len(p.get('arena_matches') or []), **enrich(p.get('player_id')))
        if k == 'odds':
            d['best_odds_label'] = price_label(p.get('best_odds'))
        out_leaders[k] = d
    out_picks = {}
    for k, lbl in LEADER_LABELS:
        p = picks.get(k)
        out_picks[k] = None if not p else {'label': lbl, 'player': p.get('Player'), 'player_id': p.get('Player ID'), 'team': p.get('Team'),
                                            'opponent': p.get('Opponent'), 'flags': p.get('Storyline count'), **enrich(p.get('Player ID'))}
    out_targets = {t: [{'player': p.get('player'), 'player_id': p.get('player_id'), 'team': t, 'form_pct': ui.form_pct(p.get('form')),
                        'form_label': ui.format_form_pct(p.get('form')), 'stat_rank': p.get('stat_rank'), 'matches': p.get('matches'),
                        'badges': [b[0] for b in p.get('badges', [])], 'jersey': jersey.get(_pid(p.get('player_id'))),
                        'log': logs.get(_pid(p.get('player_id'))) or [], 'position': rows.get(_pid(p.get('player_id')), {}).get('Position')} for p in lst] for t, lst in tg.items()}
    goalies = {}
    if fg:
        smap = (starters or {}).get(fg['key'], {}) or {}
        for t in (fg['away'], fg['home']):
            s = smap.get(t)
            known = bool(s and s.get('status') in ('confirmed', 'probable'))
            goalies[t] = {'starter': s, 'starter_stats': _gline(pgk.match_stats(s, goalie_rows or [])) if known else None,
                          'starter_label': pgk.starter_label(s) if s else None, 'leakiest': _gline(mc.leakiest_goalie(goalie_rows or [], t))}
    return {'day': day, 'season': season, 'snapshot_at': snapshot_at, 'n_ranked': len(rows),
            'games': mg, 'featured': fg, 'weak_side': weak, 'leaders': out_leaders, 'picks': out_picks, 'targets': out_targets,
            'goalies': goalies, 'starters': {g['key']: (starters or {}).get(g['key'], {}) for g in mg},
            'starters_fetched_at': starters_fetched_at, 'track': track or {}, 'fetch_errors': errs}
