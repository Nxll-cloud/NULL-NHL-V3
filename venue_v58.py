"""V5.8 arena names on slate displays.

Source: the NHL ``schedule/{date}`` (gameWeek[].games[].venue.default) and ``score/{date}`` (games[].venue.default)
payloads, threaded through the slate rows as ``Venue`` (raw schedule rows / snapshots) and ``venue``
(matchup_center_v54.slate_games rows). Older snapshots without a venue simply show no arena line: never 'None',
never 'nan', never a name guessed from the home team.
"""
from __future__ import annotations

import html

PIN = '📍'
_BAD = {'', 'none', 'nan', '<na>', 'null', 'n/a', 'unavailable', 'venue unavailable', 'arena unavailable'}


def clean(v):
    """Arena text or '' (None, NaN, blanks and placeholder strings -> ''). Accepts the raw API {'default': ...} too."""
    if isinstance(v, dict):
        v = v.get('default')
    if v is None or (isinstance(v, float) and v != v):
        return ''
    s = ' '.join(str(v).split())
    return '' if s.lower() in _BAD else s


def from_api(game):
    """Raw NHL schedule/score game dict -> arena text or ''."""
    return clean((game or {}).get('venue')) if isinstance(game, dict) else ''


def of(game):
    """Arena of a slate row: slate_games rows ('venue'), schedule rows / snapshots ('Venue'), numerology rows ('arena')."""
    if not isinstance(game, dict):
        return ''
    for k in ('venue', 'Venue', 'arena'):
        s = clean(game.get(k))
        if s:
            return s
    return ''


def by_game(games):
    """{game_id str: arena} and {(away, home): arena} from any slate rows (only real, non-empty arenas)."""
    out = {}
    for g in games or []:
        a = of(g)
        if not a:
            continue
        gid = g.get('game_id', g.get('Game ID'))
        if gid not in (None, ''):
            out[str(gid)] = a
        away, home = g.get('away', g.get('Away')), g.get('home', g.get('Home'))
        if away and home:
            out[(str(away), str(home))] = a
    return out


def label(v, sep=' · '):
    """Plain-text suffix for selectbox / expander labels: ' · 📍 United Center' or ''."""
    s = clean(v)
    return f'{sep}{PIN} {s}' if s else ''


def tag(v, cls='vn'):
    """Compact HTML arena line (pin + name, ellipsised by CSS, full name in the tooltip) or '' when unknown."""
    s = clean(v)
    if not s:
        return ''
    e = html.escape(s)
    return f'<small class="{cls}" title="{e}"><i aria-hidden="true">{PIN}</i>{e}</small>'


def fill(games, scores):
    """Backfill missing arenas on slate_games rows from parse_scores output (same game id, real API venue). In place."""
    for g in games or []:
        if isinstance(g, dict) and not clean(g.get('venue')):
            g['venue'] = clean(((scores or {}).get(str(g.get('game_id') or '')) or {}).get('venue'))
    return games
