"""NHL public API client. Historical features use only games before selected date."""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

BASE = 'https://api-web.nhle.com/v1'
SEASON = '20262027'


def fetch_json(path):
    url = f'{BASE}/{path}'
    response = requests.get(url, timeout=25, headers={'User-Agent': 'NULL-NHL-V3/0.2'})
    response.raise_for_status()
    return response.json()


def get_schedule(day):
    payload = fetch_json(f'schedule/{day}')
    games = []
    for item in payload.get('gameWeek', []):
        if item.get('date') != day:
            continue
        for game in item.get('games', []):
            games.append({'Game ID': game.get('id'), 'Away': game.get('awayTeam', {}).get('abbrev'),
                          'Home': game.get('homeTeam', {}).get('abbrev'),
                          'Start (UTC)': game.get('startTimeUTC'), 'Status': game.get('gameState')})
    return games


def get_roster(team, season=SEASON):
    data = fetch_json(f'roster/{team}/{season}')
    players = []
    for group in ('forwards', 'defensemen'):
        for p in data.get(group, []):
            players.append({'id': p.get('id'),
                            'Player': (p.get('firstName', {}).get('default', '') + ' ' + p.get('lastName', {}).get('default', '')).strip(),
                            'Team': team, 'Position': p.get('positionCode', '')})
    return [p for p in players if p['id']]


def get_game_log(player_id, season=SEASON):
    data = fetch_json(f'player/{player_id}/game-log/{season}/2')
    return data.get('gameLog', [])


def summarize_games(log, cutoff_day):
    """Strict pre-slate regular-season totals with per-player quality diagnostics.

    Excludes slate date and later dates. Invalid or duplicate records are not
    silently treated as valid games.
    """
    from datetime import date

    cutoff = date.fromisoformat(cutoff_day)
    previous, seen = [], set()
    invalid = duplicate = future = 0

    for game in log:
        try:
            game_date = date.fromisoformat(game["gameDate"])
            game_id = game["gameId"]
            goals = int(game["goals"])
            shots = int(game["shots"])
            if not game_id or goals < 0 or shots < 0 or goals > shots:
                raise ValueError("Invalid game statistics")
        except (KeyError, ValueError, TypeError):
            invalid += 1
            continue

        if game_date >= cutoff:
            future += 1
            continue
        if game_id in seen:
            duplicate += 1
            continue
        seen.add(game_id)
        previous.append({"date": game_date, "goals": goals, "shots": shots})

    previous.sort(key=lambda g: g["date"], reverse=True)

    def totals(n):
        sample = previous[:n]
        return {"GP": len(sample),
                "G": sum(g["goals"] for g in sample),
                "SOG": sum(g["shots"] for g in sample)}

    return {
        "L5": totals(5),
        "L10": totals(10),
        "Season": totals(len(previous)),
        "Quality": {
            "invalid_rows": invalid,
            "duplicate_rows": duplicate,
            "excluded_on_or_after_date": future,
            "usable_prior_games": len(previous),
        },
    }


def player_row(player, cutoff_day, season=SEASON):
    recent = summarize_games(get_game_log(player['id'], season), cutoff_day)
    s, l5, l10 = recent['Season'], recent['L5'], recent['L10']
    return {**player, 'GP': s['GP'], 'Goals': s['G'], 'Shots': s['SOG'],
            'Goals L5': l5['G'], 'Shots L5': l5['SOG'], 'GP L5': l5['GP'],
            'Goals L10': l10['G'], 'Shots L10': l10['SOG'], 'GP L10': l10['GP'],
            'Goals/Game': round(s['G']/s['GP'], 3) if s['GP'] else None,
            'Shots/Game': round(s['SOG']/s['GP'], 3) if s['GP'] else None,
            'Data status': ('Needs review' if recent['Quality']['invalid_rows'] or recent['Quality']['duplicate_rows']
                            else 'Historical log available' if s['GP'] else 'No prior games'),
            'Invalid rows': recent['Quality']['invalid_rows'],
            'Duplicate rows': recent['Quality']['duplicate_rows'],
            'Excluded future rows': recent['Quality']['excluded_on_or_after_date']}


def load_team(team, cutoff_day, season=SEASON, max_workers=5):
    roster = get_roster(team, season)
    rows, errors = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(player_row, p, cutoff_day, season): p for p in roster}
        for future in as_completed(futures):
            try:
                rows.append(future.result())
            except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                errors.append(f"{futures[future]['Player']}: {exc}")
    return sorted(rows, key=lambda x: (x['Goals'], x['Shots']), reverse=True), errors
