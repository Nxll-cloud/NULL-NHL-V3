"""t201: one-off backfill of the 'Jersey' column into an existing slate snapshot (public NHL roster feed, by Player ID).

Usage: python jersey_backfill_v61.py [YYYY-MM-DD ...]   (default: current Eastern date)
Only missing jerseys are filled; every other snapshot field is kept. Fetch failures leave the value null.
"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import jersey_v61 as jy
from snapshot_store import load_snapshot, save_snapshot


def backfill(day, fetch=None):
    data = load_snapshot(day)
    if data is None:
        print(f'{day}: no valid snapshot; nothing to backfill')
        return None
    teams = jy.missing_teams(data['rankings'])
    rmap, problems = (fetch or jy.fetch_map)(teams) if teams else ({}, [])
    rows = jy.fill_records(data['rankings'], rmap)
    known, total = jy.coverage(rows)
    save_snapshot(day, data['games'], rows, data.get('history'), list(data.get('errors') or []) + [str(p) for p in problems])
    print(f'{day}: jersey known for {known}/{total} ranked players ({len(problems)} roster fetch problems)')
    return known, total


if __name__ == '__main__':
    days = sys.argv[1:] or [datetime.now(ZoneInfo('America/New_York')).date().isoformat()]
    for d in days:
        backfill(d)
