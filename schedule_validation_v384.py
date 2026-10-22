"""Independent schedule and team-assignment checks for the selected NHL slate.

An empty historical opponent count is not an error if the official team schedule
also shows no previous head-to-head meetings. Missing API data is not a zero.
"""
from datetime import date
import pandas as pd
from nhl_data import fetch_json, get_schedule, SEASON
from storyline_v38 import normalize_team, opponent_lookup


def validate_slate_games(display_games, official_games):
    expected = {(normalize_team(g.get('Away')), normalize_team(g.get('Home'))): str(g.get('Game ID')) for g in official_games}
    records = []
    for g in display_games:
        away, home = normalize_team(g.get('Away')), normalize_team(g.get('Home'))
        key = (away, home)
        official_id = expected.get(key)
        status = ('Verified official slate matchup' if official_id is not None and official_id == str(g.get('Game ID'))
                  else 'Mismatch or unavailable official matchup')
        records.append({'Away':away, 'Home':home, 'Dashboard game ID':g.get('Game ID'),
                        'Official game ID':official_id, 'Schedule status':status})
    return pd.DataFrame(records)


def prior_team_meetings(team, opponent, day, schedule):
    """Return prior completed head-to-head count, or None if schedule is invalid."""
    if not isinstance(schedule, dict) or not isinstance(schedule.get('games'), list):
        return None
    cutoff = date.fromisoformat(day)
    seen = set()
    for g in schedule['games']:
        try:
            gd = date.fromisoformat(g['gameDate'])
            gid = str(g['id'])
            away = normalize_team((g.get('awayTeam') or {}).get('abbrev'))
            home = normalize_team((g.get('homeTeam') or {}).get('abbrev'))
            state = g.get('gameState')
            if gd < cutoff and state in ('OFF','FINAL') and {away,home} == {normalize_team(team), normalize_team(opponent)}:
                seen.add(gid)
        except (ValueError, KeyError, TypeError):
            continue
    return len(seen)


def audit_schedule(rows, games, day, season=SEASON, schedule_fetch=None, team_fetch=None):
    schedule_fetch = schedule_fetch or get_schedule
    team_fetch = team_fetch or (lambda team: fetch_json(f'club-schedule-season/{team}/{season}'))
    official = schedule_fetch(day)
    game_audit = validate_slate_games(games, official)
    opponents = opponent_lookup(games)
    players = pd.DataFrame(rows).copy()
    if players.empty:
        return game_audit, pd.DataFrame(), []
    team_schedules, errors = {}, []
    for team in sorted(set(players['Team'].dropna()) & set(opponents)):
        try:
            team_schedules[team] = team_fetch(team)
        except Exception as exc:
            errors.append(f'{team}: {type(exc).__name__}: {exc}')
            team_schedules[team] = None
    records=[]
    for _,r in players.iterrows():
        team = r['Team']; opp = opponents.get(team)
        meetings = prior_team_meetings(team,opp,day,team_schedules.get(team)) if opp else None
        game_ok = not game_audit.empty and bool(((((game_audit['Away']==normalize_team(team)) | (game_audit['Home']==normalize_team(team))) & (game_audit['Schedule status']=='Verified official slate matchup')).any()))
        records.append({'Player ID':str(r.get('Player ID','')), 'Player':r.get('Player',''), 'Team':team,
                        'Upcoming opponent':opp, 'Official slate match verified':game_ok,
                        'Prior team meetings (official schedule)':meetings,
                        'Schedule audit status':('Unverified slate assignment' if not game_ok else
                                                 'Historical schedule unavailable' if meetings is None else
                                                 'Confirmed no prior team meetings' if meetings == 0 else
                                                 'Prior team meetings found')})
    return game_audit, pd.DataFrame(records), errors
