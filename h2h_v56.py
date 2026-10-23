"""V5.6 shooter-vs-goalie head-to-head from REAL NHL play-by-play (no invented history).

Source: past meetings of the two clubs found via ``club-schedule-season/{team}/{season}`` (regular season + playoffs,
completed games before the slate date), then each meeting's ``gamecenter/{id}/play-by-play``. Every ``shot-on-goal``
and ``goal`` event carries ``goalieInNetId``, so for each (shooter, goalie) pair we count shots on goal and goals.
Shootout attempts and empty-net events (no goalie in net) are excluded.

Coverage window: seasons ``FIRST_SEASON`` (2024-25) to the current season. Limitation, stated in the UI: only meetings
between tonight's two clubs are scanned, so a goalie's history against a shooter from games with other clubs (e.g.
before a trade) is not included.

Cache: one compact JSON per game in ``data/h2h_cache`` (gitignored, excluded from the zip), pruned oldest-first above
``CACHE_CAP_BYTES``. Completed games never change, so cached files never expire.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = 'https://api-web.nhle.com/v1/'
FIRST_SEASON = 20242025
CACHE_DIR = Path(os.environ.get('PLAYBOOK_H2H_CACHE', Path(__file__).resolve().parent / 'data' / 'h2h_cache'))
CACHE_CAP_BYTES = 5 * 1024 * 1024
DONE = ('OFF', 'FINAL')


def season_label(season):
    s = str(season)
    return f'{s[:4]}-{s[6:8]}'


def seasons_since(current, first=FIRST_SEASON):
    cur = int(current)
    out, s = [], int(first)
    while s <= cur:
        out.append(s)
        y = s // 10000
        s = (y + 1) * 10000 + (y + 2)
    return out


def coverage_label(current, first=FIRST_SEASON, games=None):
    base = f'since {season_label(first)}'
    return base if games is None else f'{base} · {games} meeting{"s" if games != 1 else ""} scanned'


def extract_pairs(pbp):
    """PBP payload -> compact meeting record: [[shooter_id, goalie_id, is_goal, shooter_team], ...]."""
    away, home = pbp.get('awayTeam') or {}, pbp.get('homeTeam') or {}
    ids = {away.get('id'): away.get('abbrev'), home.get('id'): home.get('abbrev')}
    rows = []
    for p in pbp.get('plays') or []:
        kind = p.get('typeDescKey')
        if kind not in ('shot-on-goal', 'goal') or (p.get('periodDescriptor') or {}).get('periodType') == 'SO':
            continue
        d = p.get('details') or {}
        goalie = d.get('goalieInNetId')
        shooter = d.get('scoringPlayerId') if kind == 'goal' else d.get('shootingPlayerId')
        if goalie is None or shooter is None:
            continue  # empty net or malformed
        rows.append([int(shooter), int(goalie), int(kind == 'goal'), ids.get(d.get('eventOwnerTeamId'), '')])
    names = {}
    for s in pbp.get('rosterSpots') or []:
        if s.get('playerId') is not None:
            names[int(s['playerId'])] = ((s.get('firstName') or {}).get('default', '') + ' ' + (s.get('lastName') or {}).get('default', '')).strip()
    return {'game_id': pbp.get('id'), 'date': pbp.get('gameDate'), 'away': away.get('abbrev'), 'home': home.get('abbrev'),
            'pairs': rows, 'names': {str(k): v for k, v in names.items()}}


def meetings(schedule_payloads, team, opp, before_day):
    """Completed games between ``team`` and ``opp`` before ``before_day`` from club-schedule-season payloads."""
    out = {}
    for payload in schedule_payloads:
        for g in (payload or {}).get('games') or []:
            a, h = (g.get('awayTeam') or {}).get('abbrev'), (g.get('homeTeam') or {}).get('abbrev')
            if {a, h} != {team, opp} or g.get('gameType') not in (2, 3):
                continue
            if g.get('gameState') not in DONE or str(g.get('gameDate', '')) >= str(before_day):
                continue
            out[g['id']] = {'game_id': g['id'], 'date': g.get('gameDate'), 'away': a, 'home': h}
    return sorted(out.values(), key=lambda m: m['date'])


def _cache_path(game_id, root=None):
    return Path(root or CACHE_DIR) / f'{int(game_id)}.json'


def cache_get(game_id, root=None):
    p = _cache_path(game_id, root)
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def cache_put(record, root=None, cap=CACHE_CAP_BYTES):
    root = Path(root or CACHE_DIR)
    try:
        root.mkdir(parents=True, exist_ok=True)
        _cache_path(record['game_id'], root).write_text(json.dumps(record, separators=(',', ':')), encoding='utf-8')
        prune(root, cap)
    except OSError:
        pass  # read-only filesystem: the in-memory result is still returned


def prune(root=None, cap=CACHE_CAP_BYTES):
    root = Path(root or CACHE_DIR)
    files = sorted((p for p in root.glob('*.json') if not p.name.startswith('meetings_')), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    removed = 0
    while files and total > cap:
        f = files.pop(0)
        total -= f.stat().st_size
        f.unlink(missing_ok=True)
        removed += 1
    return removed


def load_meetings(team, opp, day, current_season, getter, root=None, workers=6, timeout=15):
    """Fetch (or read from cache) every past meeting's pairs. Returns (records, errors). Never raises."""
    errors, scheds = [], []
    idx = Path(root or CACHE_DIR) / f'meetings_{"_".join(sorted((team, opp)))}_{day}.json'
    try:
        games = json.loads(idx.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        games = None
    for season in (seasons_since(current_season) if games is None else ()):
        try:
            r = getter(f'{API}club-schedule-season/{team}/{season}', timeout=timeout)
            r.raise_for_status()
            scheds.append(r.json())
        except Exception as exc:
            errors.append(f'schedule {team} {season}: {type(exc).__name__}')
    if games is None:
        games = meetings(scheds, team, opp, day)
        if not errors:  # complete schedule scan -> the meeting list for this slate day never changes
            try:
                idx.parent.mkdir(parents=True, exist_ok=True)
                idx.write_text(json.dumps(games), encoding='utf-8')
            except OSError:
                pass

    def one(m):
        rec = cache_get(m['game_id'], root)
        if rec is not None:
            return rec
        r = getter(f'{API}gamecenter/{m["game_id"]}/play-by-play', timeout=timeout)
        r.raise_for_status()
        rec = extract_pairs(r.json())
        cache_put(rec, root)
        return rec

    records = []
    if games:
        with ThreadPoolExecutor(max_workers=min(workers, len(games))) as pool:
            for m, fut in [(m, pool.submit(one, m)) for m in games]:
                try:
                    records.append(fut.result())
                except Exception as exc:
                    errors.append(f'pbp {m["game_id"]}: {type(exc).__name__}')
    return records, errors


def aggregate(records):
    """records -> {(shooter, goalie): {'sog', 'goals', 'games'}} plus a name map."""
    pairs, names = {}, {}
    for rec in records or []:
        names.update({int(k): v for k, v in (rec.get('names') or {}).items()})
        seen = set()
        for shooter, goalie, goal, _team in rec.get('pairs') or []:
            k = (int(shooter), int(goalie))
            d = pairs.setdefault(k, {'sog': 0, 'goals': 0, 'games': 0})
            d['sog'] += 1
            d['goals'] += int(goal)
            if k not in seen:
                d['games'] += 1
                seen.add(k)
    return pairs, names


def vs(pairs, shooter, goalie):
    return pairs.get((int(shooter), int(goalie))) if shooter is not None and goalie is not None else None


def goalie_threats(pairs, goalie_id, shooters):
    """Opposing shooters (already sorted by next-goal probability) annotated with their H2H line vs this goalie."""
    out = []
    for s in shooters:
        h = vs(pairs, s.get('pid'), goalie_id) if goalie_id is not None else None
        out.append({**s, 'h2h': h})
    return out


def hardest_goalie(pairs, shooter_id, goalies, min_sog=3):
    """Among the opposing goalies, the one this shooter has the lowest goals/SOG against (>= min_sog H2H shots).

    Returns (goalie, basis) where basis is 'H2H' or None when the sample is too small (caller falls back to season SV%)."""
    best = None
    for g in goalies or []:
        h = vs(pairs, shooter_id, g.get('id'))
        if not h or h['sog'] < min_sog:
            continue
        rate = h['goals'] / h['sog']
        key = (rate, -h['sog'])
        if best is None or key < best[0]:
            best = (key, {**g, 'h2h': h})
    return (best[1], 'H2H') if best else (None, None)


def flag_game(pairs, top_shooters, goalie_by_team, top_n=3):
    """Flags: a top-``top_n`` next-goal shooter facing a goalie he has scored on before (REAL PBP H2H)."""
    flags = []
    for s in top_shooters[:top_n]:
        g = goalie_by_team.get(s.get('opp'))
        if not g:
            continue
        h = vs(pairs, s.get('pid'), g.get('id'))
        if h and h['goals'] > 0:
            flags.append({'shooter': s.get('name'), 'pid': s.get('pid'), 'team': s.get('team'), 'goalie': g.get('name'),
                          'goalie_id': g.get('id'), 'goalie_status': g.get('status', ''), 'goals': h['goals'], 'sog': h['sog'],
                          'games': h['games'], 'rank': s.get('rank')})
    return flags
