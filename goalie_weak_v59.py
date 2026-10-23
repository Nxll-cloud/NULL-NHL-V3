"""V5.9 goalie weak-spot identifier for Home 'Matchup targets' (display only; the next-goal model is untouched).

Which opposing goalie a target skater (or his team) has historically beaten more than expected. REAL NHL data only:

Goalie = the opponent's listed starter from the SAME probable-starter feed the rankings label and the situational
model use (probable_goalies_v54 via starters_cached; status 'confirmed'/'probable' only, as situational_v58.starter_for),
mapped to his NHL id with the same probable_goalies_v54.match_stats. No listed starter -> no marker.

Data (api-web.nhle.com, cached on disk, never raises, offline -> no marker):
  1. ``player/{goalie}/game-log/{season}/{2|3}`` for seasons FIRST_SEASON..current: every game the goalie played,
     with opponent, shots against and goals against (all of his clubs, regular season + playoffs, before the slate day).
  2. ``gamecenter/{id}/play-by-play`` for the games he played against the skater's CURRENT team (h2h_v56 extract /
     cache, shared): each shot on goal / goal with ``goalieInNetId`` = him -> shooter-vs-goalie SOG and goals.
     Empty-net and shootout events excluded (h2h_v56.extract_pairs).

Markers (shrinkage, so tiny samples never trigger):
  * Player: shrunk rate = (G + K_PLAYER x P0) / (SOG + K_PLAYER), P0 = 1 - situational_v58.LEAGUE_SV. Shown when
    SOG >= MIN_SOG, G >= MIN_GOALS and shrunk rate >= PLAYER_RATIO x P0.
  * Team: the goalie's GA/SA vs the skater's team against his own GA/SA in all his games in the window, shrunk with
    K_TEAM shots toward his own rate. Shown when SA >= MIN_SA and shrunk ratio >= TEAM_RATIO.
Limits (stated in the tooltip): player history counts only games vs the skater's current team (shots taken while the
skater played for another club are missed); team history spans past rosters of that club.
"""
from __future__ import annotations

import html as _html
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import h2h_v56 as h2h

API = 'https://api-web.nhle.com/v1/'
FIRST_SEASON = 20212022
CACHE_DIR = Path(os.environ.get('PLAYBOOK_GWEAK_CACHE', Path(__file__).resolve().parent / 'data' / 'goalie_weak_cache'))
P0 = round(1 - 0.896, 3)          # league goals per shot on goal faced (situational_v58.LEAGUE_SV .896)
K_PLAYER, MIN_SOG, MIN_GOALS, PLAYER_RATIO = 20, 6, 2, 1.30
K_TEAM, MIN_SA, TEAM_RATIO = 400, 150, 1.10
LIVE = ('confirmed', 'probable')


def _esc(v):
    return _html.escape(str(v if v is not None else ''), quote=True)


def last_name(name):
    parts = str(name or '').split()
    return parts[-1] if parts else ''


def starter_goalie(starter, goalie_rows):
    """Listed starter -> {'id', 'name', 'status'} (NHL id via probable_goalies_v54.match_stats, else feed id) or None."""
    if not starter or starter.get('status') not in LIVE or not starter.get('goalie'):
        return None
    import probable_goalies_v54 as pgk
    hit = pgk.match_stats(starter, goalie_rows or [])
    gid = (hit or {}).get('Player ID') or starter.get('goalie_id')
    if not str(gid or '').isdigit():
        return None
    return {'id': int(gid), 'name': (hit or {}).get('Goalie') or starter['goalie'], 'status': starter['status']}


# ---- data ---------------------------------------------------------------------------------------------------------
def _read(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _write(p, obj):
    try:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(json.dumps(obj, separators=(',', ':')), encoding='utf-8')
    except OSError:
        pass


def parse_game_log(payload, game_type):
    out = []
    for g in (payload or {}).get('gameLog') or []:
        try:
            out.append({'game_id': int(g['gameId']), 'date': str(g.get('gameDate') or ''), 'team': g.get('teamAbbrev'),
                        'opp': g.get('opponentAbbrev'), 'sa': int(g.get('shotsAgainst') or 0), 'ga': int(g.get('goalsAgainst') or 0),
                        'type': game_type})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def goalie_games(goalie_id, day, current_season, getter, root=None, timeout=15):
    """Every game the goalie played FIRST_SEASON..current before ``day``. Returns (games, errors). Never raises.
    Past seasons are cached for good; the current season per slate day."""
    root = Path(root or CACHE_DIR)
    games, errors = [], []
    for season in h2h.seasons_since(current_season, FIRST_SEASON):
        for gt in (2, 3):
            cur = int(season) == int(current_season)
            p = root / (f'glog_{int(goalie_id)}_{season}_{gt}' + (f'_{day}' if cur else '') + '.json')
            got = _read(p)
            if got is None:
                try:
                    r = getter(f'{API}player/{int(goalie_id)}/game-log/{season}/{gt}', timeout=timeout)
                    r.raise_for_status()
                    got = parse_game_log(r.json(), gt)
                    _write(p, got)
                except Exception as exc:
                    errors.append(f'game log {goalie_id} {season}/{gt}: {type(exc).__name__}')
                    got = []
            games += got
    return [g for g in games if g['date'] and g['date'] < str(day)], errors


def team_split(games, opp):
    vs_ = [g for g in games if g.get('opp') == opp]
    return {'sa': sum(g['sa'] for g in vs_), 'ga': sum(g['ga'] for g in vs_), 'gp': len(vs_),
            'sa_all': sum(g['sa'] for g in games), 'ga_all': sum(g['ga'] for g in games), 'gp_all': len(games),
            'first': min((g['date'] for g in vs_), default=None), 'last': max((g['date'] for g in vs_), default=None)}


def shooter_counts(records, goalie_id, team):
    """h2h_v56 meeting records -> {shooter_id: {'sog', 'goals', 'games'}} for shots by ``team`` on this goalie."""
    out = {}
    for rec in records or []:
        seen = set()
        for shooter, goalie, goal, tm in rec.get('pairs') or []:
            if int(goalie) != int(goalie_id) or (team and tm and tm != team):
                continue
            d = out.setdefault(int(shooter), {'sog': 0, 'goals': 0, 'games': 0})
            d['sog'] += 1
            d['goals'] += int(goal)
            if shooter not in seen:
                d['games'] += 1
                seen.add(shooter)
    return out


def load(goalie_id, team, day, current_season, getter, root=None, workers=6, timeout=15):
    """Everything the markers need for ``team``'s shooters vs this goalie. Never raises."""
    games, errors = goalie_games(goalie_id, day, current_season, getter, root, timeout)
    split = team_split(games, team)
    vs_games = [g for g in games if g.get('opp') == team]

    def one(g):
        rec = h2h.cache_get(g['game_id'])
        if rec is None:
            r = getter(f'{API}gamecenter/{g["game_id"]}/play-by-play', timeout=timeout)
            r.raise_for_status()
            rec = h2h.extract_pairs(r.json())
            h2h.cache_put(rec)
        return rec

    records = []
    if vs_games:
        with ThreadPoolExecutor(max_workers=min(workers, len(vs_games))) as pool:
            for g, fut in [(g, pool.submit(one, g)) for g in vs_games]:
                try:
                    records.append(fut.result())
                except Exception as exc:
                    errors.append(f'pbp {g["game_id"]}: {type(exc).__name__}')
    return {'goalie_id': int(goalie_id), 'team': team, 'split': split, 'shooters': shooter_counts(records, goalie_id, team),
            'pbp_games': len(records), 'errors': errors, 'window': h2h.season_label(FIRST_SEASON)}


# ---- markers -------------------------------------------------------------------------------------------------------
def player_marker(h, goalie, window=None):
    """{'goals','sog','games','rate','ratio','goalie',...} when the shrunk gap is meaningful, else None."""
    if not h or not goalie or h.get('sog', 0) < MIN_SOG or h.get('goals', 0) < MIN_GOALS:
        return None
    shrunk = (h['goals'] + K_PLAYER * P0) / (h['sog'] + K_PLAYER)
    ratio = shrunk / P0
    if ratio < PLAYER_RATIO:
        return None
    return {'kind': 'player', 'goalie': goalie.get('name'), 'goalie_id': goalie.get('id'), 'status': goalie.get('status'),
            'goals': h['goals'], 'sog': h['sog'], 'games': h.get('games'), 'shrunk': round(shrunk, 3), 'ratio': round(ratio, 2),
            'window': window or h2h.season_label(FIRST_SEASON)}


def team_marker(split, goalie, team, window=None):
    if not split or not goalie or split.get('sa', 0) < MIN_SA or not split.get('sa_all'):
        return None
    own = split['ga_all'] / split['sa_all']
    if own <= 0:
        return None
    shrunk = (split['ga'] + K_TEAM * own) / (split['sa'] + K_TEAM)
    ratio = shrunk / own
    if ratio < TEAM_RATIO:
        return None
    return {'kind': 'team', 'goalie': goalie.get('name'), 'goalie_id': goalie.get('id'), 'status': goalie.get('status'), 'team': team,
            'sv_vs': round(1 - split['ga'] / split['sa'], 3), 'sv_all': round(1 - own, 3), 'sa': split['sa'], 'ga': split['ga'],
            'gp': split['gp'], 'ratio': round(ratio, 2), 'window': window or h2h.season_label(FIRST_SEASON)}


def annotate(targets, data, goalie):
    """Home target dicts (player_id) -> same dicts with 'goalie_weak' (player marker or None). Returns (rows, n_marked)."""
    out, n = [], 0
    shooters = (data or {}).get('shooters') or {}
    for p in targets or []:
        try:
            h = shooters.get(int(float(p.get('player_id'))))
        except (TypeError, ValueError):
            h = None
        m = player_marker(h, goalie, (data or {}).get('window')) if data else None
        n += m is not None
        out.append(dict(p, goalie_weak=m))
    return out, n


def _sv(x):
    return f'{x:.3f}'.lstrip('0')


def row_tag(m):
    """Compact pill for a target row: 'vs G Knight · 3 G / 14 SOG'. '' when no marker."""
    if not m or m.get('kind') != 'player':
        return ''
    tip = (f"Weak spot: {m['goalie']} ({str(m.get('status') or '').title()} starter). {m['goals']} goals on {m['sog']} shots on goal in "
           f"{m.get('games') or '?'} game(s) vs him since {m['window']} (NHL play-by-play, his games vs this club; "
           f"empty-net and shootout excluded). Shrunk rate {m['shrunk']:.3f} vs league {P0:.3f} per shot. Display only, not in the model.")
    return (f'<span class="gwk" title="{_esc(tip)}" aria-label="{_esc(tip)}"><i>vs G</i> <b>{_esc(last_name(m["goalie"]))}</b>'
            f' <b>· {m["goals"]} G / {m["sog"]} SOG</b></span>')


def row_cell(m):
    """Full-width grid cell under a target row (so the pill never clips at 320 px). '' when no marker."""
    tag = row_tag(m)
    return f'<div class="gwr">{tag}</div>' if tag else ''


def team_chip(m):
    """Column-head chip for the team-level split: 'Knight vs MTL · .872 SV% (his .905)'. '' when no marker."""
    if not m or m.get('kind') != 'team':
        return ''
    tip = (f"Weak spot: {m['goalie']} has a {_sv(m['sv_vs'])} save % vs {m['team']} ({m['ga']} GA on {m['sa']} shots, {m['gp']} games "
           f"since {m['window']}, NHL goalie game logs, all his clubs) vs {_sv(m['sv_all'])} in all his games. Past {m['team']} rosters "
           f"included. Display only, not in the model.")
    return (f'<span class="gwk team" title="{_esc(tip)}" aria-label="{_esc(tip)}"><i>vs G</i> <b>{_esc(last_name(m["goalie"]))}</b>'
            f' <b>· {_sv(m["sv_vs"])} SV% vs {_esc(m["team"])}</b> <em>(his {_sv(m["sv_all"])})</em></span>')


def home_markers(state, goalie_rows, loader, limit=5):
    """Attach markers to v55_state.build_state output in place (featured game only, the rows Home shows).

    For each side t: goalie = starter_goalie(state['goalies'][opp]['starter']); data = loader(goalie_id, t) (cached
    ``load``; any exception -> no markers). Sets target['goalie_weak'] and state['goalies'][opp]['weak_team'].
    Returns {'marked': n_rows_with_player_marker, 'team': n_team_chips, 'checked': n_rows, 'errors': [...]}."""
    fg = (state or {}).get('featured')
    out = {'marked': 0, 'team': 0, 'checked': 0, 'errors': []}
    if not fg:
        return out
    for t in (fg['away'], fg['home']):
        opp = fg['home'] if t == fg['away'] else fg['away']
        og = (state.get('goalies') or {}).get(opp)
        goalie = starter_goalie((og or {}).get('starter'), goalie_rows)
        rows = (state.get('targets') or {}).get(t) or []
        data = None
        if goalie:
            try:
                data = loader(goalie['id'], t)
            except Exception as exc:
                out['errors'].append(f'{opp} goalie weak-spot: {type(exc).__name__}')
            out['errors'] += list((data or {}).get('errors') or [])
        head, rest = rows[:limit], rows[limit:]
        marked, n = annotate(head, data, goalie) if data else ([dict(p, goalie_weak=None) for p in head], 0)
        state.setdefault('targets', {})[t] = marked + rest
        out['marked'] += n
        out['checked'] += len(head)
        if og is not None:
            og['weak_team'] = team_marker((data or {}).get('split'), goalie, t, (data or {}).get('window')) if data else None
            out['team'] += og['weak_team'] is not None
    return out


def legend(state, limit=5):
    """' · vs G = ...' basis line for the Matchup targets lede when any pill/chip is on screen, else ''."""
    fg = (state or {}).get('featured') or {}
    rows = [p for t in (fg.get('away'), fg.get('home')) for p in ((state.get('targets') or {}).get(t) or [])[:limit]]
    team = any((g or {}).get('weak_team') for g in ((state or {}).get('goalies') or {}).values())
    if not team and not any(p.get('goalie_weak') for p in rows):
        return ''
    return (f' · <span class="gwk-l"><b>vs G</b> = tonight’s listed opposing starter’s history vs this skater ({MIN_GOALS}+ G on '
            f'{MIN_SOG}+ SOG, shrunk to the league rate; NHL play-by-play) or vs this club (his save % there vs his own; NHL goalie '
            f'game logs), since {h2h.season_label(FIRST_SEASON)} · display only, not in the model</span>')
