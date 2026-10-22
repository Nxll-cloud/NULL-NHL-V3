"""V5.4 probable / confirmed starting goalies for Matchup Center.

Sources (checked against real responses on 2026-10-22):
1. NHL official api-web ``gamecenter/{gameId}/boxscore`` ->
   ``playerByGameStats.{awayTeam,homeTeam}.goalies[].starter`` (bool). That block
   only exists once a game has started (LIVE/CRIT/OFF), so it can confirm starters
   in-game/after, but pregame (FUT/PRE) the NHL feeds have no starter field.
   (``landing`` -> ``matchup.goalieComparison`` lists season *leaders*, not starters,
   and is deliberately NOT used as a starter source.)
2. Fallback / pregame: ESPN public scoreboard
   ``site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=YYYYMMDD`` ->
   ``events[].competitions[0].competitors[].probables[name=probableStartingGoalie]``
   with ``status.type`` 'confirmed' or 'expected' (-> 'probable').

Every result is normalized to
  {game_id, team, goalie_id, goalie, status: confirmed|probable|unknown, source, fetched_at}
and anything missing or failing becomes 'unknown' (no name). Stats are joined to
``goalies_v54`` rows by NHL player id, else by normalized name within the team.

Polling: pregame starters change slowly, so the app caches them for STARTER_TTL_SECONDS
(5 min) via st.cache_data and only refetches on a cache miss. This shares the
``live_scoring_future`` design (per-provider min interval + ``backoff_delay`` jitter);
when the live poller is wired, starters would be refreshed on its own slow lane
(>= 5 min pregame, once at puck drop from the NHL boxscore), never on the 30 s goal lane.
"""
from datetime import datetime, timezone

import requests

from odds_intelligence_v46 import normalized_name

STARTER_TTL_SECONDS = 300
TIMEOUT_SECONDS = 8
ESPN_URL = 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard'
ESPN_TO_NHL = {'SJ': 'SJS', 'NJ': 'NJD', 'LA': 'LAK', 'TB': 'TBL', 'UTAH': 'UTA', 'UTH': 'UTA', 'WAS': 'WSH',
               'MON': 'MTL', 'NAS': 'NSH', 'CLB': 'CBJ', 'LV': 'VGK', 'VEG': 'VGK', 'STLB': 'STL'}
STATUS_LABEL = {'confirmed': 'Confirmed starter', 'probable': 'Probable starter'}
STATS_ONLY_LABEL = 'Team goalie stats — starter not yet announced'


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _txt(v):
    return (v.get('default') if isinstance(v, dict) else v) or ''


def _pid(v):
    t = str(v if v is not None else '').strip()
    t = t[:-2] if t.endswith('.0') else t
    return t if t.isdigit() else None


def unknown(game_id, team, source='none', fetched_at=None):
    return {'game_id': str(game_id or ''), 'team': str(team or '').upper(), 'goalie_id': None, 'goalie': None,
            'status': 'unknown', 'source': source, 'fetched_at': fetched_at}


def espn_team(code):
    code = str(code or '').upper()
    return ESPN_TO_NHL.get(code, code)


def parse_nhl_boxscore(payload, fetched_at=None):
    """-> {team: starter dict}. Only goalies flagged ``starter: true`` count; none pregame."""
    out = {}
    if not isinstance(payload, dict):
        return out
    gid = str(payload.get('id') or '')
    stats = payload.get('playerByGameStats')
    stats = stats if isinstance(stats, dict) else {}
    for side in ('awayTeam', 'homeTeam'):
        info = payload.get(side)
        team = str((info.get('abbrev') if isinstance(info, dict) else '') or '').upper()
        block = stats.get(side)
        goalies = (block.get('goalies') if isinstance(block, dict) else None) or []
        goalies = goalies if isinstance(goalies, list) else []
        starters = [g for g in goalies if isinstance(g, dict) and g.get('starter') is True]
        if team and len(starters) == 1:
            g = starters[0]
            out[team] = {'game_id': gid, 'team': team, 'goalie_id': _pid(g.get('playerId')), 'goalie': _txt(g.get('name')) or None,
                         'status': 'confirmed', 'source': 'NHL boxscore (starter flag)', 'fetched_at': fetched_at}
    return out


def parse_espn_scoreboard(payload, fetched_at=None):
    """-> {(away, home): {team: starter dict}} keyed by NHL abbreviations."""
    out = {}
    if not isinstance(payload, dict):
        return out
    for ev in payload.get('events') or []:
        comps = ((ev or {}).get('competitions') or [{}])[0] or {}
        teams, starters = {}, {}
        for c in comps.get('competitors') or []:
            if not isinstance(c, dict):
                continue
            team = espn_team((c.get('team') or {}).get('abbreviation'))
            teams[c.get('homeAway')] = team
            for p in c.get('probables') or []:
                if not isinstance(p, dict) or p.get('name') != 'probableStartingGoalie':
                    continue
                ath = p.get('athlete') or {}
                name = ath.get('fullName') or ath.get('displayName')
                stype = str(((p.get('status') or {}).get('type')) or '').lower()
                status = 'confirmed' if stype == 'confirmed' else ('probable' if stype in ('expected', 'probable', 'likely') else 'unknown')
                if name and status != 'unknown':
                    starters[team] = {'game_id': '', 'team': team, 'goalie_id': None, 'espn_id': str(ath.get('id') or p.get('playerId') or ''),
                                      'goalie': name, 'status': status, 'source': 'ESPN scoreboard (probables)', 'fetched_at': fetched_at}
        if teams.get('away') and teams.get('home'):
            out[(teams['away'], teams['home'])] = starters
    return out


def combine(game, nhl=None, espn=None, fetched_at=None):
    """Starter per team for one slate game: NHL starter flag first, ESPN second, else unknown."""
    gid, away, home = str(game.get('game_id') or ''), game['away'], game['home']
    espn_game = (espn or {}).get((away, home)) or {}
    out = {}
    for team in (away, home):
        s = (nhl or {}).get(team) or espn_game.get(team)
        out[team] = {**s, 'game_id': gid} if s else unknown(gid, team, 'NHL + ESPN (no starter listed)', fetched_at)
    return out


def _get(url, params=None, session=None):
    r = (session or requests).get(url, params=params, timeout=TIMEOUT_SECONDS, headers={'User-Agent': 'NULL-NHL-V5.4'})
    r.raise_for_status()
    return r.json()


def fetch_starters(day, games, session=None, getter=None):
    """Network wrapper (cached in app.py). Never raises: failures become 'unknown' + an error string."""
    getter = getter or (lambda url, params=None: _get(url, params, session))
    fetched = _now()
    errors, espn = [], {}
    nhl_by_game = {}
    for g in games:
        if str(g.get('status') or '').upper() in ('LIVE', 'CRIT', 'OFF', 'FINAL') and g.get('game_id'):
            try:
                nhl_by_game[g['game_id']] = parse_nhl_boxscore(getter(f'https://api-web.nhle.com/v1/gamecenter/{g["game_id"]}/boxscore'), fetched)
            except Exception as exc:  # graceful: treated as unknown
                errors.append(f'NHL boxscore {g["game_id"]}: {type(exc).__name__}')
    try:
        espn = parse_espn_scoreboard(getter(ESPN_URL, {'dates': str(day).replace('-', '')}), fetched)
    except Exception as exc:
        errors.append(f'ESPN scoreboard: {type(exc).__name__}')
    return {g['key']: combine(g, nhl_by_game.get(g.get('game_id')), espn, fetched) for g in games}, errors, fetched


def match_stats(starter, goalie_rows):
    """Attach goalies_v54 stats to a starter: NHL id first, then unique normalized name in the team."""
    if not starter or starter.get('status') == 'unknown' or not starter.get('goalie'):
        return None
    team = starter.get('team')
    rows = [r for r in goalie_rows or [] if str(r.get('Team', '')).upper() == team]
    if starter.get('goalie_id'):
        for r in rows:
            if str(r.get('Player ID')) == str(starter['goalie_id']):
                return r
    key = normalized_name(starter['goalie'])
    hits = [r for r in rows if normalized_name(r.get('Goalie', '')) == key]
    if not hits and '.' in starter['goalie']:  # NHL boxscore short names like "J. Woll": initial + last name
        first, _, last = starter['goalie'].partition('.')
        hits = [r for r in rows if normalized_name(r.get('Goalie', '')).endswith(normalized_name(last))
                and normalized_name(r.get('Goalie', '')).startswith(normalized_name(first)[:1])]
    return hits[0] if len(hits) == 1 else None


def starter_label(starter):
    return STATUS_LABEL.get((starter or {}).get('status'), STATS_ONLY_LABEL)
