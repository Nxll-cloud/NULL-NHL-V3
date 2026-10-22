"""Opponent defensive context from NHL completed regular-season boxscores.

No starting-goalie confirmation is inferred from boxscores.
"""
from datetime import date
import requests
from nhl_data import fetch_json

def prior_team_games(schedule, team, cutoff_day, limit=10):
    cutoff = date.fromisoformat(cutoff_day)
    games = []
    for game in schedule.get("games", []):
        try:
            day = date.fromisoformat(game["gameDate"])
            gid = game["id"]
            state = game.get("gameState")
            away = game.get("awayTeam", {}).get("abbrev")
            home = game.get("homeTeam", {}).get("abbrev")
            if day < cutoff and state in ("OFF", "FINAL") and team in (away, home):
                games.append((day, gid))
        except (KeyError, ValueError, TypeError):
            continue
    games.sort(reverse=True)
    return [gid for _, gid in games[:limit]]

def defense_summary(team, cutoff_day, season):
    """Return defensive stats with coverage and explicit unavailable values."""
    schedule = fetch_json(f"club-schedule-season/{team}/{season}")
    game_ids = prior_team_games(schedule, team, cutoff_day)
    records, failures = [], []
    for gid in game_ids:
        try:
            box = fetch_json(f"gamecenter/{gid}/boxscore")
            away, home = box["awayTeam"], box["homeTeam"]
            if away.get("abbrev") == team:
                opp = home
            elif home.get("abbrev") == team:
                opp = away
            else:
                raise ValueError("Team missing from boxscore")
            goals = opp.get("score")
            shots = opp.get("sog")
            if not isinstance(goals, int) or not isinstance(shots, int) or goals < 0 or shots < goals:
                raise ValueError("Goals or shots missing/invalid")
            records.append({"goals": goals, "shots": shots})
        except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
            failures.append(f"{gid}: {exc}")
    def avg(items, key):
        return round(sum(x[key] for x in items)/len(items), 2) if items else None
    return {
        "Opponent": team,
        "Defense GP L5": len(records[:5]),
        "Defense GA/G L5": avg(records[:5], "goals"),
        "Defense SA/G L5": avg(records[:5], "shots"),
        "Defense GP L10": len(records[:10]),
        "Defense GA/G L10": avg(records[:10], "goals"),
        "Defense SA/G L10": avg(records[:10], "shots"),
        "Games found": len(game_ids),
        "Games verified": len(records),
        "Boxscore errors": len(failures),
        "Error details": failures,
    }

def opponent_lookup(games):
    result = {}
    for game in games:
        home, away = game.get("Home"), game.get("Away")
        if home and away:
            result[home] = away
            result[away] = home
    return result

def attach_matchups(ranked, games, defensive):
    opponents = opponent_lookup(games)
    enriched = []
    for row in ranked:
        opponent = opponents.get(row["Team"])
        d = defensive.get(opponent, {})
        enriched.append({
            **row,
            "Opponent": opponent or "Unavailable",
            "Opp GA/G L5": d.get("Defense GA/G L5"),
            "Opp SA/G L5": d.get("Defense SA/G L5"),
            "Opp GA/G L10": d.get("Defense GA/G L10"),
            "Opp SA/G L10": d.get("Defense SA/G L10"),
            "Opp defense verified GP": d.get("Games verified", 0),
            "Starting goalie": "Unconfirmed",
            "Goalie adjustment": "Not applied",
        })
    return enriched
