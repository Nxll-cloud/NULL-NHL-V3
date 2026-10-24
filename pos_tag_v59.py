"""V5.9: compact position tag after player names on the Numbers tab (display only).

Position comes ONLY from real NHL data: the rankings ``Position`` column (NHL roster ``positionCode``) or a position
field already on the record. NHL codes map C->C, L->LW, R->RW, D->D, G->G. Unknown / missing -> no tag (never guessed
from a name). Goalies reuse the existing goalie pill (position_badge_v59.goalie_badge) so a 'G' is never shown twice.
Not used by any score, rank, tier, TOP PICK or sort.
"""
import html as _html
import math

import position_badge_v59 as pb

CODE_MAP = {'C': 'C', 'L': 'LW', 'R': 'RW', 'D': 'D', 'G': 'G', 'LW': 'LW', 'RW': 'RW'}
LABEL = {'C': 'Center', 'LW': 'Left wing', 'RW': 'Right wing', 'D': 'Defenseman', 'G': 'Goalie'}


def code(position):
    """NHL position value -> 'C' | 'LW' | 'RW' | 'D' | 'G', or None when unknown."""
    if isinstance(position, dict):
        position = position.get('abbreviation') or position.get('code')
    if not isinstance(position, str):
        return None
    return CODE_MAP.get(position.strip().upper())


def tag(position):
    """'<span class="npos">LW</span>' (goalies: the existing 'G' pill), '' when unknown."""
    c = code(position)
    if c is None:
        return ''
    if c == 'G':
        return pb.goalie_badge('G')
    t = _html.escape(LABEL[c])
    return f'<span class="npos" title="{t}" aria-label="{t}">{c}</span>'


def _pid(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return str(int(f)) if math.isfinite(f) else None


def pos_map(ranked):
    """{'id': {pid: code}, 'name': {(TEAM, name.casefold()): code}} from a rankings DataFrame ('' -> skipped)."""
    out = {'id': {}, 'name': {}}
    try:
        if ranked is None or ranked.empty or 'Position' not in ranked.columns:
            return out
        rows = ranked[[c for c in ('Player', 'Player ID', 'Team', 'Position') if c in ranked.columns]].to_dict('records')
    except AttributeError:
        return out
    for r in rows:
        c = code(r.get('Position'))
        if c is None:
            continue
        pid = _pid(r.get('Player ID'))
        if pid:
            out['id'][pid] = c
        name = str(r.get('Player') or '').strip()
        if name:
            out['name'][(str(r.get('Team') or '').upper(), name.casefold())] = c
    return out


def lookup(pmap, pid=None, team=None, name=None, record=None):
    """Position code for one listed player: a position already on the record, then id, then (team, name); else None."""
    if record is not None:
        c = code(pb.position_of(record))
        if c:
            return c
    if not pmap:
        return None
    p = _pid(pid)
    if p and p in pmap.get('id', {}):
        return pmap['id'][p]
    if name:
        return pmap.get('name', {}).get((str(team or '').upper(), str(name).strip().casefold()))
    return None


def tag_for(pmap, pid=None, team=None, name=None, record=None):
    c = lookup(pmap, pid, team, name, record)
    return tag(c) if c else ''
