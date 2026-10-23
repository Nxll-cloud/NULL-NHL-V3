"""V5.8 feature flags (one place). Track Record is hidden for now; its data and logging keep running.

SHOW_TRACK_RECORD = False hides the 📈 Track Record tab and every Track Record element (tab, Matchup Center track
badges). Prediction auto-save on Home, the tracker module and the SQLite DB are untouched.
Re-enable without a code change: set FEATURE_TRACK_RECORD = "true" in .streamlit/secrets.toml (or the env var
FEATURE_TRACK_RECORD=1). The env var wins over secrets; both win over the default below.

SHOW_RESEARCH_EXTRAS = False hides every Research section rendered below 'Top 10 Statistical Sleepers' (display only;
rankings, intelligence and the history job still run). Re-enable with FEATURE_RESEARCH_EXTRAS, same rules as above.
"""
import os

SHOW_TRACK_RECORD = False
SHOW_RESEARCH_EXTRAS = False
TRUE, FALSE = ('1', 'true', 'yes', 'on'), ('0', 'false', 'no', 'off')


def _parse(v):
    s = str(v).strip().lower()
    return True if s in TRUE else False if s in FALSE else None


def _flag(name, default, secrets=None, environ=None):
    env = (environ if environ is not None else os.environ).get(name)
    if env is not None and _parse(env) is not None:
        return _parse(env)
    try:
        val = secrets.get(name) if secrets is not None else None
    except Exception:  # no secrets.toml -> Streamlit raises; the default applies
        val = None
    if val is not None and _parse(val) is not None:
        return _parse(val)
    return default


def show_track_record(secrets=None, environ=None):
    return _flag('FEATURE_TRACK_RECORD', SHOW_TRACK_RECORD, secrets, environ)


def show_research_extras(secrets=None, environ=None):
    return _flag('FEATURE_RESEARCH_EXTRAS', SHOW_RESEARCH_EXTRAS, secrets, environ)


# V5.8 situational next-goal model (situational_v58). On by default; MODEL_SITUATIONAL = "false" (secrets) or
# MODEL_SITUATIONAL=0 (env) falls back to the V5.6 model exactly. MODEL_SITUATIONAL_PARTS picks the layers
# (comma list of pp, goalie, line, xg; default all). Env wins over secrets, as above.
MODEL_SITUATIONAL = True
MODEL_PARTS = ('pp', 'goalie', 'line', 'xg')   # V5.9: + 'xg' shot quality (xg_v59)


def _lookup(name, secrets, environ):
    env = (environ if environ is not None else os.environ).get(name)
    if env is not None:
        return env
    try:
        return secrets.get(name) if secrets is not None else None
    except Exception:  # no secrets.toml
        return None


def model_situational(secrets=None, environ=None):
    v = _parse(_lookup('MODEL_SITUATIONAL', secrets, environ)) if _lookup('MODEL_SITUATIONAL', secrets, environ) is not None else None
    return MODEL_SITUATIONAL if v is None else v


def model_parts(secrets=None, environ=None):
    v = _lookup('MODEL_SITUATIONAL_PARTS', secrets, environ)
    parts = MODEL_PARTS if v is None else tuple(p for p in (x.strip().lower() for x in str(v).split(',')) if p in MODEL_PARTS)
    return parts if model_xg(secrets, environ) else tuple(p for p in parts if p != 'xg')   # V5.9 MODEL_XG switch


# V5.9 shot-quality (xG) layer (xg_v59, MoneyPuck data). On by default; MODEL_XG = "false" (secrets) or MODEL_XG=0
# (env) drops 'xg' from the parts, i.e. the V5.8 situational model exactly. Needs MODEL_SITUATIONAL on.
MODEL_XG = True


def model_xg(secrets=None, environ=None):
    v = _parse(_lookup('MODEL_XG', secrets, environ)) if _lookup('MODEL_XG', secrets, environ) is not None else None
    return MODEL_XG if v is None else v



# V5.9 goalie weak-spot identifier on Home 'Matchup targets' (goalie_weak_v59; display only, never in the model).
# On by default; FEATURE_GOALIE_WEAK = "false" (secrets) or FEATURE_GOALIE_WEAK=0 (env) hides it. Env wins over secrets.
SHOW_GOALIE_WEAK = True


def show_goalie_weak(secrets=None, environ=None):
    return _flag('FEATURE_GOALIE_WEAK', SHOW_GOALIE_WEAK, secrets, environ)
