"""Validated, atomic daily snapshots generated outside the Streamlit process."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCHEMA = 1
ROOT = Path(__file__).parent / "snapshots"

def snapshot_path(day, root=ROOT):
    datetime.strptime(day, "%Y-%m-%d")
    return Path(root) / f"{day}.json"

def load_snapshot(day, root=ROOT):
    path = snapshot_path(day, root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("updated_at"), str):
            return None
        if data.get("schema") != SCHEMA or data.get("day") != day:
            return None
        if not isinstance(data.get("games"), list) or not isinstance(data.get("rankings"), list):
            return None
        if data["games"] and not data["rankings"]:
            return None
        datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        return data
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        return None

def save_snapshot(day, games, rankings, history=None, errors=None, root=ROOT):
    path = snapshot_path(day, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "day": day,
               "updated_at": datetime.now(timezone.utc).isoformat(),
               "games": games, "rankings": rankings,
               "history": history or [], "errors": errors or []}
    import os, tempfile
    with tempfile.NamedTemporaryFile("w", dir=path.parent, suffix=".tmp", delete=False, encoding="utf-8") as f:
        temp = Path(f.name)
        json.dump(payload, f, allow_nan=False)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


# ---- V5.5: GitHub-size safety --------------------------------------------------------------------------
DEFAULT_KEEP_DAYS = 60   # conservative: two months of slates stay in the repo
_SNAP_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def prune_snapshots(keep_days=DEFAULT_KEEP_DAYS, today=None, root=ROOT, dry_run=False):
    """Delete snapshots/YYYY-MM-DD.json files dated more than keep_days before today. Only files whose name
    is exactly a date are touched (.gitkeep and anything else is never deleted). Returns the pruned paths
    (sorted). dry_run=True only lists them. The app treats a missing snapshot as 'no snapshot' and falls
    back to live data, so pruning never breaks the app."""
    if int(keep_days) < 1:
        raise ValueError("keep_days must be >= 1")
    today = today or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=int(keep_days))
    root = Path(root)
    out = []
    if not root.is_dir():
        return out
    for p in sorted(root.iterdir()):
        m = _SNAP_NAME.match(p.name)
        if not m or not p.is_file():
            continue
        try:
            d = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if d < cutoff:
            out.append(p)
            if not dry_run:
                p.unlink()
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Snapshot housekeeping (V5.5)")
    ap.add_argument("command", choices=["prune"])
    ap.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    gone = prune_snapshots(a.keep_days, dry_run=a.dry_run)
    print(("Would prune " if a.dry_run else "Pruned ") + f"{len(gone)} snapshot(s) older than {a.keep_days} days" +
          "".join(f"\n  {p.name}" for p in gone))
