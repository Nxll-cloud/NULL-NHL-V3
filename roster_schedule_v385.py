"""V3.8.5 roster-membership and historical-schedule coverage diagnostics.

A season roster proves membership in that roster listing, NOT membership on a
specific past date. Historical schedule counts are never inferred from an
empty or malformed response. All evidence is descriptive.
"""
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from nhl_data import fetch_json, SEASON
from storyline_v38 import normalize_team, opponent_lookup


def roster_ids(payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid roster response')
    groups = ('forwards','defensemen','goalies')
    if not any(isinstance(payload.get(k),list) for k in groups):
        raise ValueError('Roster groups missing')
    return {str(int(p['id'])) for k in groups for p in (payload.get(k) or [])
            if isinstance(p,dict) and p.get('id') is not None}


def schedule_coverage(payload, team, opponent, day):
    if not isinstance(payload,dict) or not isinstance(payload.get('games'),list):
        return {'Schedule coverage status':'Unavailable / invalid response',
                'Completed games inspected':None,'Prior opponent meetings':None,
                'Pre-slate schedule entries':None,'Unrecognized schedule entries':None}
    cutoff=date.fromisoformat(day)
    completed=set(); meetings=set(); prior=0; invalid=0
    for g in payload['games']:
        try:
            d=date.fromisoformat(g['gameDate'])
            if d>=cutoff: continue
            if int(g.get('gameType',2))!=2: continue
            prior+=1
            gid=str(g['id'])
            a=normalize_team((g.get('awayTeam') or {}).get('abbrev'))
            h=normalize_team((g.get('homeTeam') or {}).get('abbrev'))
            if not gid or not a or not h or normalize_team(team) not in (a,h):
                invalid+=1; continue
            if g.get('gameState') in ('OFF','FINAL'):
                completed.add(gid)
                if {a,h}=={normalize_team(team),normalize_team(opponent)}:
                    meetings.add(gid)
            elif g.get('gameState') not in ('FUT','PRE','LIVE','CRIT'):
                invalid+=1
        except (KeyError,TypeError,ValueError):
            invalid+=1
    return {'Schedule coverage status':'Incomplete / review' if invalid else 'Parsed',
            'Completed games inspected':len(completed),
            'Prior opponent meetings':len(meetings),
            'Pre-slate schedule entries':prior,
            'Unrecognized schedule entries':invalid}


def audit_roster_and_history(rows,games,day,season=SEASON,roster_fetch=None,schedule_fetch=None,workers=6):
    roster_fetch=roster_fetch or (lambda team:fetch_json(f'roster/{team}/{season}'))
    schedule_fetch=schedule_fetch or (lambda team:fetch_json(f'club-schedule-season/{team}/{season}'))
    opponents=opponent_lookup(games)
    frame=pd.DataFrame(rows).copy()
    if frame.empty: return pd.DataFrame(),pd.DataFrame(),[]
    teams=sorted({normalize_team(t) for t in frame['Team'].dropna() if normalize_team(t) in opponents})
    records=[]; errors=[]
    def check(team):
        roster=schedule=None; problems=[]
        try: roster=roster_ids(roster_fetch(team))
        except Exception as e: problems.append(f'Roster: {type(e).__name__}: {e}')
        try: schedule=schedule_coverage(schedule_fetch(team),team,opponents[team],day)
        except Exception as e: problems.append(f'Schedule: {type(e).__name__}: {e}')
        if schedule is None: schedule=schedule_coverage(None,team,opponents[team],day)
        return team,roster,schedule,problems
    with ThreadPoolExecutor(max_workers=max(1,min(workers,12))) as pool:
        for result in as_completed([pool.submit(check,t) for t in teams]):
            team,roster,schedule,problems=result.result()
            if problems: errors.extend(f'{team}: {p}' for p in problems)
            records.append({'Team':team,'Upcoming opponent':opponents[team],
                            'Roster fetch status':'Verified roster response' if roster is not None else 'Unavailable',
                            'Roster IDs returned':len(roster) if roster is not None else None,
                            **schedule,'_roster_ids':roster})
    lookup={r['Team']:r for r in records}
    players=[]
    for _,r in frame.iterrows():
        team=normalize_team(r.get('Team')); entry=lookup.get(team)
        pid=str(r.get('Player ID','')).removesuffix('.0')
        ids=entry.get('_roster_ids') if entry else None
        membership=('Unverified — roster unavailable' if ids is None else
                    'Found on season roster' if pid in ids else 'NOT FOUND on assigned team roster')
        players.append({'Player ID':pid,'Player':r.get('Player',''), 'Assigned team':team,
                        'Upcoming opponent':opponents.get(team), 'Roster membership':membership,
                        'Roster source':f'https://api-web.nhle.com/v1/roster/{team}/{season}' if team else '',
                        'Historical schedule coverage':entry.get('Schedule coverage status') if entry else 'Unavailable',
                        'Completed team games inspected':entry.get('Completed games inspected') if entry else None,
                        'Prior team meetings':entry.get('Prior opponent meetings') if entry else None})
    for rec in records: rec.pop('_roster_ids',None)
    return pd.DataFrame(players),pd.DataFrame(records),errors
