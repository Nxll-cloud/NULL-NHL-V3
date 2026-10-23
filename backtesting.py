"""Strict pregame snapshot export and completed-boxscore scoring.

Snapshots are user-downloaded CSV files, not durable server-side records.
Only score snapshots captured before every scheduled game start.
"""
from datetime import datetime, timezone
import io
import pandas as pd
from nhl_data import fetch_json

COLUMNS = ["Snapshot UTC", "Slate date", "Game ID", "Player ID", "Player",
           "Team", "Baseline Form Index", "V3.2 Adjusted Index",
           "Defense Adjustment", "Adjustment status"]
# Audit P1.4: optional shots-share baseline column (older CSVs without it still validate and score).
SHOTS_COL = "Shots/G L5"
BASELINE_MODEL = "Shots/G baseline"

def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("Missing UTC timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone is required")
    return result.astimezone(timezone.utc)

def make_snapshot(ranked, games, day, captured=None):
    captured = captured or datetime.now(timezone.utc)
    if captured.tzinfo is None:
        raise ValueError("Capture time must have a timezone")
    starts = [parse_utc(g["Start (UTC)"]) for g in games]
    if not games or len(starts) != len(games) or captured >= min(starts):
        raise ValueError("Snapshot must precede every game start")
    if any(g.get("Status") not in ("FUT", "PRE") for g in games):
        raise ValueError("All games must be pregame")
    lookup = {}
    for g in games:
        for team in (g["Home"], g["Away"]):
            if team in lookup:
                raise ValueError("Team appears in multiple games")
            lookup[team] = g["Game ID"]
    result = []
    for r in ranked:
        if r["Team"] not in lookup or not r.get("Player ID"):
            continue
        result.append({
            "Snapshot UTC": captured.astimezone(timezone.utc).isoformat(),
            "Slate date": day,
            "Game ID": lookup[r["Team"]],
            "Player ID": r["Player ID"],
            "Player": r["Player"],
            "Team": r["Team"],
            "Baseline Form Index": r["Baseline Form Index"],
            "V3.2 Adjusted Index": r["V3.2 Adjusted Index"],
            "Defense Adjustment": r["Defense Adjustment"],
            "Adjustment status": r["Adjustment status"],
            SHOTS_COL: r.get(SHOTS_COL),
        })
    if not result:
        raise ValueError("No ranked players with IDs")
    return pd.DataFrame(result, columns=COLUMNS + [SHOTS_COL])

def validate_snapshot(frame):
    if not set(COLUMNS).issubset(frame.columns) or frame.empty:
        raise ValueError("Snapshot missing columns or rows")
    dates = frame["Slate date"].astype(str).unique()
    captures = frame["Snapshot UTC"].astype(str).unique()
    if len(dates) != 1 or len(captures) != 1:
        raise ValueError("Snapshot must have one slate date and capture time")
    capture = parse_utc(captures[0])
    if frame[["Player ID", "Game ID"]].isna().any().any():
        raise ValueError("Missing player or game identifiers")
    if frame["Player ID"].duplicated().any():
        raise ValueError("Duplicate player IDs")
    for key in ("Baseline Form Index", "V3.2 Adjusted Index"):
        frame[key] = pd.to_numeric(frame[key], errors="raise")
        if not frame[key].notna().all():
            raise ValueError("Missing index")
    return dates[0], capture

def boxscore_goals(box):
    """Map player ID to goals for players present in completed game boxscore."""
    if box.get("gameState") not in ("OFF", "FINAL"):
        raise ValueError("Game not final")
    groups = box.get("playerByGameStats")
    if not isinstance(groups, dict):
        raise ValueError("Missing player-by-game stats")
    goals = {}
    for side in ("awayTeam", "homeTeam"):
        team = groups.get(side)
        if not isinstance(team, dict):
            raise ValueError("Missing team player stats")
        for position in ("forwards", "defense"):
            players = team.get(position)
            if not isinstance(players, list):
                raise ValueError("Missing skater stats")
            for player in players:
                pid, scored = player.get("playerId"), player.get("goals")
                if not isinstance(pid, int) or not isinstance(scored, int) or scored < 0:
                    raise ValueError("Invalid skater ID/goals")
                if pid in goals:
                    raise ValueError("Duplicate skater")
                goals[pid] = scored
    return goals

def score_snapshot(frame, fetch=fetch_json):
    frame = frame.copy()
    day, capture = validate_snapshot(frame)
    results = []
    failures = []
    for game_id, subset in frame.groupby("Game ID"):
        try:
            box = fetch(f"gamecenter/{int(game_id)}/boxscore")
            if parse_utc(box["startTimeUTC"]) <= capture:
                raise ValueError("Snapshot timestamp is not pregame")
            if str(box.get("gameDate")) != day:
                raise ValueError("Game date mismatch")
            goals = boxscore_goals(box)
            for _, row in subset.iterrows():
                pid = int(row["Player ID"])
                if pid in goals:
                    results.append({**row.to_dict(), "Actual goals": goals[pid],
                                    "Scored": int(goals[pid] > 0), "Outcome status": "Verified boxscore"})
                else:
                    results.append({**row.to_dict(), "Actual goals": None,
                                    "Scored": None, "Outcome status": "Not in boxscore"})
        except (KeyError, ValueError, TypeError) as exc:
            failures.append(f"Game {game_id}: {exc}")
    return pd.DataFrame(results), failures

def top_k_metrics(scored, k_values=(5, 10, 20)):
    """Coverage-first hit metrics; missing outcomes make the top-K unscorable."""
    out = []
    if scored.empty:
        return pd.DataFrame()
    models = [("Baseline Form Index", "V3"), ("V3.2 Adjusted Index", "V3.2")]
    if SHOTS_COL in scored and pd.to_numeric(scored[SHOTS_COL], errors="coerce").notna().any():
        models.append((SHOTS_COL, BASELINE_MODEL))   # naive comparison: top K by recent shots per game
    for key, model in models:
        ordered = scored.assign(_k=pd.to_numeric(scored[key], errors="coerce")).sort_values(["_k", "Player ID"], ascending=[False, True])
        for k in k_values:
            top = ordered.head(k)
            if len(top) < k or top["Scored"].isna().any():
                out.append({"Model": model, "Top K": k, "Scorers": None,
                            "Hit rate": None, "Status": "Incomplete coverage"})
            else:
                hits = int(top["Scored"].sum())
                out.append({"Model": model, "Top K": k, "Scorers": hits,
                            "Hit rate": round(hits / k, 3), "Status": "Complete"})
    return pd.DataFrame(out)
