"""Pregame opponent defense from completed NHL boxscores; descriptive adjustment only."""
from datetime import date
import math
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

def _valid_rate(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

def league_defense_baseline(defensive, min_gp=3):
    """Equal-weight eligible teams; no external or fabricated league constants."""
    eligible = []
    for d in defensive.values():
        if (d.get("Games verified", 0) >= min_gp
            and d.get("Boxscore errors", 0) == 0
            and all(_valid_rate(d.get(k)) for k in
                    ("Defense GA/G L5", "Defense SA/G L5",
                     "Defense GA/G L10", "Defense SA/G L10"))):
            eligible.append(d)
    if len(eligible) < 4:
        return None
    return {
        key: sum(d[key] for d in eligible) / len(eligible)
        for key in ("Defense GA/G L5", "Defense SA/G L5",
                    "Defense GA/G L10", "Defense SA/G L10")
    }

def attach_matchups(ranked, games, defensive, adjust=True):
    opponents = opponent_lookup(games)
    baseline = league_defense_baseline(defensive)
    enriched = []
    for row in ranked:
        opponent = opponents.get(row["Team"])
        d = defensive.get(opponent, {})
        base = row["Form Index"]
        reason = "Applied"
        factor = 1.0
        keys = ("Defense GA/G L5", "Defense GA/G L10",
                "Defense SA/G L5", "Defense SA/G L10")
        if not adjust:
            reason = "Disabled"
        elif baseline is None:
            reason = "Insufficient league baseline"
        elif (d.get("Games verified", 0) < 3 or d.get("Boxscore errors", 0) != 0
              or not all(_valid_rate(d.get(k)) for k in keys)):
            reason = "Insufficient opponent coverage"
        elif any(baseline[k] <= 0 for k in keys):
            reason = "Invalid league baseline"
        else:
            # Weighted rate ratios; capped to limit sensitivity to small samples.
            ga_ratio = (0.6 * d[keys[0]] / baseline[keys[0]]
                        + 0.4 * d[keys[1]] / baseline[keys[1]])
            sa_ratio = (0.6 * d[keys[2]] / baseline[keys[2]]
                        + 0.4 * d[keys[3]] / baseline[keys[3]])
            raw = 0.6 * ga_ratio + 0.4 * sa_ratio
            factor = max(0.85, min(1.15, 1 + 0.5 * (raw - 1)))
        enriched.append({
            **row,
            "Baseline Form Index": base,
            "Defense Adjustment": round((factor - 1) * 100, 1),
            "V3.2 Adjusted Index": round(base * factor, 1),
            "Adjustment status": reason,
            "Opponent": opponent or "Unavailable",
            "Opp GA/G L5": d.get("Defense GA/G L5"),
            "Opp SA/G L5": d.get("Defense SA/G L5"),
            "Opp GA/G L10": d.get("Defense GA/G L10"),
            "Opp SA/G L10": d.get("Defense SA/G L10"),
            "Opp defense verified GP": d.get("Games verified", 0),
            "Starting goalie": "Unconfirmed",
            "Goalie adjustment": "Not applied",
        })
    enriched.sort(key=lambda x: (-x["V3.2 Adjusted Index"], -x["Shots/G L5"], x["Player"]))
    return enriched
