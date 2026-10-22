"""Run independently with: python precompute_slate.py [YYYY-MM-DD]."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from nhl_data import SEASON, get_schedule, load_team
from rankings import rank_players
from matchups import defense_summary, attach_matchups
from ranking_integrity_v3871 import assign_statistical_ranks
from history_v386 import fetch_multi_history
from snapshot_store import save_snapshot

def compute(day, include_history=True):
    games = get_schedule(day)
    if not games:
        return save_snapshot(day, [], [], [], [])
    teams = sorted({g[t] for g in games for t in ("Home", "Away") if g.get(t)})
    rows, errors, defense = [], [], {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(load_team, team, day, SEASON): team for team in teams}
        for future in as_completed(jobs):
            team = jobs[future]
            try:
                part, problems = future.result()
                rows.extend(part)
                errors.extend(f"{team}: {e}" for e in problems)
            except Exception as exc:
                errors.append(f"{team}: {type(exc).__name__}: {exc}")
    if not rows:
        raise RuntimeError("No player records fetched; retaining previous snapshot")
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(defense_summary, team, day, SEASON): team for team in teams}
        for future in as_completed(jobs):
            team = jobs[future]
            try:
                defense[team] = future.result()
            except Exception as exc:
                errors.append(f"Defense {team}: {type(exc).__name__}: {exc}")
    ranked = assign_statistical_ranks(attach_matchups(rank_players(rows, 3), games, defense, adjust=True))
    if isinstance(ranked, pd.DataFrame):
        ranked = ranked.to_dict("records")
    else:
        ranked = list(ranked)
    if not ranked:
        raise RuntimeError("No eligible rankings; retaining previous snapshot")
    history = []
    if include_history:
        try:
            hist, hist_errors = fetch_multi_history(ranked, games, day, max_players=len(ranked), years=3)
            history = hist.to_dict("records") if isinstance(hist, pd.DataFrame) else list(hist)
            errors.extend(str(e) for e in hist_errors)
        except Exception as exc:
            errors.append(f"History: {type(exc).__name__}: {exc}")
    # pandas/numpy scalars and NaN must not corrupt the JSON snapshot.
    def clean(obj):
        return __import__('json').loads(pd.Series([obj]).to_json(orient='values'))[0]
    path = save_snapshot(day, clean(games), clean(ranked), clean(history), errors)
    print(f"Saved {len(ranked)} players, {len(history)} historical profiles to {path}")
    return path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("day", nargs="?", default=datetime.now(ZoneInfo("America/New_York")).date().isoformat())
    parser.add_argument("--skip-history", action="store_true")
    args = parser.parse_args()
    compute(args.day, include_history=not args.skip_history)
