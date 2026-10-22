"""Source-linked NHL profile metadata for exploratory signals; no news assertions."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from nhl_data import fetch_json


def arena_lookup(games):
    """Read the NHL schedule's venue field when available; never infer from home team."""
    out = {}
    for game in games:
        arena = game.get('Venue')
        if isinstance(arena, str) and arena.strip():
            for team in (game.get('Home'), game.get('Away')):
                if team:
                    out[team] = arena.strip()
    return out


def profile_metadata(row, day, arenas=None):
    pid = row.get('Player ID')
    if not pid:
        raise ValueError('Missing player ID')
    profile = fetch_json(f'player/{int(pid)}/landing')
    if int(profile.get('playerId', -1)) != int(pid):
        raise ValueError('Player profile ID mismatch')
    dob = profile.get('birthDate') or ''
    if dob:
        parsed = date.fromisoformat(dob)
        if parsed > date.fromisoformat(day):
            raise ValueError('Invalid future birth date')
    jersey = profile.get('sweaterNumber')
    if jersey is not None and (not isinstance(jersey, int) or not 0 <= jersey <= 99):
        jersey = None
    team = row.get('Team')
    return {'Player ID': str(int(pid)), 'Jersey': '' if jersey is None else str(jersey),
            'Birth date': dob, 'Arena': (arenas or {}).get(team, ''),
            'Verified storyline': '', 'Source URL': f'https://api-web.nhle.com/v1/player/{int(pid)}/landing',
            'Metadata status': 'NHL profile returned; current jersey/team may differ on historical dates'}


def fetch_metadata(rows, day, games, max_players=50, workers=6):
    """Limit requests, collect per-player failures; caller supplies ranked order."""
    rows = list(rows)[:max_players]
    arenas = arena_lookup(games)
    records, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(profile_metadata, row, day, arenas): row for row in rows}
        for future in as_completed(futures):
            try:
                records.append(future.result())
            except Exception as exc:
                row = futures[future]
                errors.append(f"{row.get('Player', 'Unknown')}: {type(exc).__name__}: {exc}")
    return records, errors
