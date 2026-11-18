"""V6.1 jersey numbers for the Numbers tab: roster sweater numbers joined by NHL Player ID.

Source: the public NHL roster feed (api-web.nhle.com/v1/roster/{team}/current, no key) via
v55_state.fetch_roster_numbers. Every failure leaves the jersey missing (None); nothing here raises.
Match rule (t201): the RAW sweater number (no digit reduction) is in that date's daily pattern numbers
(daily_patterns_v60 entry_for: saved entry if present, else the auto-computed one). A missing jersey never
matches; 0 matches only when the stored value is actually 0.
"""
from __future__ import annotations
import math

COLUMN = 'Jersey'
NOTE = ('Jersey (new, t201): a player’s raw sweater number equal to one of the day’s pattern numbers. '
        'Joined from the public NHL roster by Player ID. Not part of the historical Numbers backtest.')


def norm(v):
    """int sweater number, or None for missing/blank/NaN/bool/non-whole."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or not f.is_integer() or f < 0:
        return None
    return int(f)


def pid_key(v):
    try:
        f = float(v)
        return str(int(f)) if math.isfinite(f) else ''
    except (TypeError, ValueError):
        return str(v or '').strip()


def merge_maps(team_maps):
    """{team: {pid: n}} -> {pid: n} (ints only)."""
    out = {}
    for m in (team_maps or {}).values():
        for pid, n in (m or {}).items():
            j = norm(n)
            if j is not None:
                out[pid_key(pid)] = j
    return out


def fetch_map(teams, getter=None):
    """-> ({pid: jersey}, errors). Never raises."""
    try:
        import v55_state
        if getter is None:
            import requests
            getter = requests.get
        maps, errors = v55_state.safe_many(lambda t: v55_state.fetch_roster_numbers(t, getter), list(teams))
        return merge_maps(maps), errors
    except Exception as exc:  # import/network/anything: jersey stays missing
        return {}, [f'Jersey rosters: {type(exc).__name__}']


def fill_records(records, roster_map):
    """New list of dicts with 'Jersey' filled from roster_map by Player ID where missing. Existing values kept."""
    out = []
    for r in records or []:
        r = dict(r)
        j = norm(r.get(COLUMN))
        if j is None:
            j = (roster_map or {}).get(pid_key(r.get('Player ID')))
        r[COLUMN] = norm(j)
        out.append(r)
    return out


def missing_teams(records):
    return sorted({str(r.get('Team') or '').upper() for r in records or [] if norm(r.get(COLUMN)) is None and r.get('Team')})


def fill_frame(frame, map_fn):
    """Render-time fallback for snapshots saved before the Jersey column. map_fn(teams_tuple) -> {team: {pid: n}}.
    Returns the frame unchanged when nothing is missing; never raises (on failure jersey stays missing)."""
    try:
        import pandas as pd
        recs = frame.to_dict('records')
        teams = missing_teams(recs)
        if COLUMN in frame.columns and not teams:
            return frame
        try:
            rmap = merge_maps(map_fn(tuple(teams))) if teams else {}
        except Exception:
            rmap = {}
        filled = fill_records(recs, rmap)
        out = frame.copy()
        out[COLUMN] = pd.Series([r[COLUMN] for r in filled], index=frame.index, dtype='object')
        return out
    except Exception:
        return frame


def hit(jersey, numbers):
    """Raw (unreduced) sweater number in the day's numbers. Missing never matches."""
    j = norm(jersey)
    return j is not None and j in tuple(numbers or ())


def label(jersey):
    return f'Jersey #{norm(jersey)}'


def coverage(records):
    recs = list(records or [])
    return (sum(norm(r.get(COLUMN)) is not None for r in recs), len(recs))


def text(jersey):
    """'#21' or '—' (missing)."""
    j = norm(jersey)
    return f'#{j}' if j is not None else '—'


def tag(p, key='jersey'):
    """Compact jersey tag after a player name: '#21', or '—' when missing. '' for legacy rows without the field."""
    if not isinstance(p, dict) or key not in p:
        return ''
    j = norm(p.get(key))
    if j is None:
        return '<span class="npr-jn none" title="Jersey number unavailable">—</span>'
    return f'<span class="npr-jn" title="Jersey number">#{j}</span>'
