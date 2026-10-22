
import requests

BASE_URL = "https://api-web.nhle.com/v1"
TIMEOUT = 20


def fetch_json(url):
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_team_roster(team, season="20262027"):
    """Retrieve the official NHL team roster."""
    url = f"{BASE_URL}/roster/{team}/{season}"
    data = fetch_json(url)

    players = []

    for group in ("forwards", "defensemen", "goalies"):
        for player in data.get(group, []):
            first = player.get("firstName", {})
            last = player.get("lastName", {})

            players.append({
                "player_id": player.get("id"),
                "name": (
                    first.get("default", "")
                    + " "
                    + last.get("default", "")
                ).strip(),
                "team": team,
                "position": player.get("positionCode", ""),
                "group": group,
                "source_url": url,
            })

    return players


def get_player_stats(player_id):
    """Retrieve player season and game-log data."""
    url = f"{BASE_URL}/player/{player_id}/landing"
    data = fetch_json(url)

    featured = data.get("featuredStats", {})
    regular = featured.get("regularSeason", {})
    stats = regular.get("subSeason", {})

    return {
        "player_id": player_id,
        "goals": stats.get("goals"),
        "assists": stats.get("assists"),
        "points": stats.get("points"),
        "games_played": stats.get("gamesPlayed"),
        "shots": stats.get("shots"),
        "shooting_pct": stats.get("shootingPctg"),
        "source_url": url,
    }


def get_player_game_log(player_id, season="20262027"):
    """Retrieve a player's regular-season game log."""
    url = (
        f"{BASE_URL}/player/{player_id}"
        f"/game-log/{season}/2"
    )
    data = fetch_json(url)
    return data.get("gameLog", [])


def recent_goal_stats(game_log, count=5):
    """Calculate recent goals and shots from game logs."""
    games = sorted(
        game_log,
        key=lambda g: g.get("gameDate", ""),
        reverse=True,
    )[:count]

    return {
        "games": len(games),
        "goals": sum(g.get("goals", 0) or 0 for g in games),
        "shots": sum(g.get("shots", 0) or 0 for g in games),
    }
