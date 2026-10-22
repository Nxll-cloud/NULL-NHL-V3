"""V5.4 Goalies: goals allowed per team, broken down by goalie.

Source: NHL official API ``club-stats/{team}/{season}/2`` (regular season,
api-web.nhle.com — same host and ``nhl_data.fetch_json`` client the app already
uses). Values are season-to-date at fetch time and are team-specific, so a
traded goalie appears separately under each club he played for. Descriptive
only; nothing here changes rankings.
"""
import math

import pandas as pd

GOALIE_COLUMNS = ['Team', 'Goalie', 'Player ID', 'GP', 'GS', 'GA', 'SA', 'Saves', 'TOI (sec)', 'GAA', 'SV%']
TEAM_COLUMNS = ['Team', 'Goalies', 'GP', 'GA', 'SA', 'Saves', 'TOI (sec)', 'GAA', 'SV%', 'Tone']
SORTS = {'Goals allowed': ('GA', False), 'GAA': ('GAA', False), 'Save %': ('SV%', True)}


def _num(value):
    try:
        if value is None or isinstance(value, bool):
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int(value):
    out = _num(value)
    return int(out) if out is not None and out >= 0 else 0


def _name(p):
    def part(k):
        v = p.get(k)
        return (v.get('default') if isinstance(v, dict) else v) or ''
    return f"{part('firstName')} {part('lastName')}".strip() or 'Unknown goalie'


def gaa(ga, toi_seconds):
    """Goals against per 60 minutes; None when ice time is zero/unknown (no divide-by-zero)."""
    ga, toi = _num(ga), _num(toi_seconds)
    if ga is None or toi is None or toi <= 0:
        return None
    return round(ga * 3600.0 / toi, 2)


def save_pct(saves, shots):
    s, sa = _num(saves), _num(shots)
    if s is None or sa is None or sa <= 0:
        return None
    return round(s / sa, 3)


def parse_club_goalies(payload, team):
    """club-stats payload -> list of goalie dicts. Malformed rows are skipped."""
    if not isinstance(payload, dict):
        return []
    rows = []
    for p in payload.get('goalies') or []:
        if not isinstance(p, dict):
            continue
        ga, sa, toi = _int(p.get('goalsAgainst')), _int(p.get('shotsAgainst')), _int(p.get('timeOnIce'))
        saves = _int(p.get('saves')) if p.get('saves') is not None else max(sa - ga, 0)
        row_gaa = gaa(ga, toi)
        if row_gaa is None and _int(p.get('gamesPlayed')) > 0:
            row_gaa = _num(p.get('goalsAgainstAverage'))
        row_sv = save_pct(saves, sa)
        if row_sv is None and sa > 0:
            row_sv = _num(p.get('savePercentage'))
        rows.append({'Team': str(team).upper(), 'Goalie': _name(p), 'Player ID': str(p.get('playerId') or ''),
                     'GP': _int(p.get('gamesPlayed')), 'GS': _int(p.get('gamesStarted')), 'GA': ga, 'SA': sa,
                     'Saves': saves, 'TOI (sec)': toi, 'GAA': row_gaa, 'SV%': row_sv})
    return rows


def fetch_team_goalies(team, season, fetch=None):
    """Network helper (wrapped by st.cache_data in app.py). ``fetch`` defaults to nhl_data.fetch_json."""
    if fetch is None:
        from nhl_data import fetch_json as fetch
    return parse_club_goalies(fetch(f'club-stats/{team}/{season}/2'), team)


def goalie_frame(rows):
    frame = pd.DataFrame(list(rows or []), columns=GOALIE_COLUMNS)
    if frame.empty:
        return frame
    # A goalie listed twice for one club (duplicate payload rows) is counted once.
    return frame.drop_duplicates(subset=['Team', 'Player ID', 'Goalie'], keep='first').reset_index(drop=True)


def team_summary(goalies, teams=None):
    """Per-team totals. Teams with no goalie data stay listed with zeros/None, never invented."""
    g = goalie_frame(goalies.to_dict('records') if isinstance(goalies, pd.DataFrame) else goalies)
    names = list(dict.fromkeys([str(t).upper() for t in (teams or [])] + (g['Team'].tolist() if not g.empty else [])))
    out = []
    for team in names:
        sub = g[g['Team'] == team] if not g.empty else g
        ga, sa, sv, toi = (int(sub[c].sum()) if not sub.empty else 0 for c in ('GA', 'SA', 'Saves', 'TOI (sec)'))
        out.append({'Team': team, 'Goalies': int(len(sub)), 'GP': int(sub['GS'].sum()) if not sub.empty else 0,
                    'GA': ga, 'SA': sa, 'Saves': sv, 'TOI (sec)': toi, 'GAA': gaa(ga, toi), 'SV%': save_pct(sv, sa), 'Tone': 'none'})
    return assign_tones(pd.DataFrame(out, columns=TEAM_COLUMNS))


def assign_tones(summary, metric='GA'):
    """Top third by metric -> 'opportunity' (leaky), bottom third -> 'stingy'. No-data teams -> 'none'."""
    s = summary.copy()
    if s.empty:
        return s
    higher_is_leaky = metric != 'SV%'
    has = s['Goalies'] > 0
    if metric in ('GAA', 'SV%'):
        has &= s[metric].notna()
    vals = pd.to_numeric(s.loc[has, metric], errors='coerce')
    s['Tone'] = 'none'
    s.loc[has, 'Tone'] = 'neutral'
    n = int(vals.notna().sum())
    if n >= 2:
        k = max(1, n // 3)
        ordered = vals.sort_values(ascending=not higher_is_leaky)
        s.loc[ordered.index[:k], 'Tone'] = 'opportunity'
        s.loc[ordered.index[-k:], 'Tone'] = 'stingy'
    return s


def sort_summary(summary, how='Goals allowed'):
    col, asc = SORTS.get(how, SORTS['Goals allowed'])
    s = assign_tones(summary, col)
    return s.sort_values([col, 'Team'], ascending=[asc, True], na_position='last').reset_index(drop=True)


def opponent_goalie_ga(summary, opponent):
    """Future hook for the player intelligence model (unused by rankings): opponent's GA/GAA/SV% or None."""
    if not isinstance(summary, pd.DataFrame) or summary.empty or not opponent:
        return None
    row = summary[summary['Team'] == str(opponent).upper()]
    if row.empty or int(row.iloc[0]['Goalies']) == 0:
        return None
    r = row.iloc[0]
    return {'GA': int(r['GA']), 'GAA': r['GAA'], 'SV%': r['SV%']}
