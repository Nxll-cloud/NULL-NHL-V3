"""Validated, atomic daily snapshots generated outside the Streamlit process."""
import json
from datetime import datetime, timezone
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
