"""V5.6 per-tab modules.

app.py used to hold every tab inline (~97 KB). Each tab now lives in ``tabs/<name>.py`` and is executed with
``run_tab(name, globals())`` inside its ``with <tab>:`` block, i.e. in the app's own namespace, so the code,
widget keys, caching and scoring semantics are exactly what they were inline. Tracebacks point at the tab file.
"""
from functools import lru_cache
from pathlib import Path

TAB_DIR = Path(__file__).resolve().parent
TABS = ('live', 'home', 'odds', 'research', 'numbers', 'matchup', 'edgelab', 'track', 'nextgoal', 'edgeflags')


@lru_cache(maxsize=None)
def _code(name, mtime):
    path = TAB_DIR / f'{name}.py'
    return compile(path.read_text(encoding='utf-8'), str(path), 'exec')


def run_tab(name, ns):
    path = TAB_DIR / f'{name}.py'
    exec(_code(name, path.stat().st_mtime), ns)
