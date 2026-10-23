"""V5.8 feature flags (one place). Track Record is hidden for now; its data and logging keep running.

SHOW_TRACK_RECORD = False hides the 📈 Track Record tab and every Track Record element (tab, Matchup Center track
badges). Prediction auto-save on Home, the tracker module and the SQLite DB are untouched.
Re-enable without a code change: set FEATURE_TRACK_RECORD = "true" in .streamlit/secrets.toml (or the env var
FEATURE_TRACK_RECORD=1). The env var wins over secrets; both win over the default below.
"""
import os

SHOW_TRACK_RECORD = False
TRUE, FALSE = ('1', 'true', 'yes', 'on'), ('0', 'false', 'no', 'off')


def _parse(v):
    s = str(v).strip().lower()
    return True if s in TRUE else False if s in FALSE else None


def show_track_record(secrets=None, environ=None):
    env = (environ if environ is not None else os.environ).get('FEATURE_TRACK_RECORD')
    if env is not None and _parse(env) is not None:
        return _parse(env)
    try:
        val = secrets.get('FEATURE_TRACK_RECORD') if secrets is not None else None
    except Exception:  # no secrets.toml -> Streamlit raises; the default applies
        val = None
    if val is not None and _parse(val) is not None:
        return _parse(val)
    return SHOW_TRACK_RECORD
