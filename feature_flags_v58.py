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


# Audit PP double-count fix (situational_v58 / live_nextgoal_v56; see MODEL_CARD.md 'Power play'). With it, a LIVE power
# play is priced once (team SITUATION_MULT['PP']): the player's PP split is only a neutral share ratio and PP shots count
# at EV xG. Pregame is unchanged. MODEL_PP_COHERENT = "false" (secrets) / =0 (env) restores the old stacking exactly.
# Default set from the 2026-04-04 backtest (backtests/audit_pp_2026-04-04.json): ON only with no log-loss regression.
MODEL_PP_COHERENT = True     # 2026-04-04 (situational on): log loss 3.4593 (off) -> 3.4284 (on), no regression


def model_pp_coherent(secrets=None, environ=None):
    v = _lookup('MODEL_PP_COHERENT', secrets, environ)
    p = _parse(v) if v is not None else None
    return MODEL_PP_COHERENT if p is None else p



# V5.9 goalie weak-spot identifier on Home 'Matchup targets' (goalie_weak_v59; display only, never in the model).
# On by default; FEATURE_GOALIE_WEAK = "false" (secrets) or FEATURE_GOALIE_WEAK=0 (env) hides it. Env wins over secrets.
SHOW_GOALIE_WEAK = True


def show_goalie_weak(secrets=None, environ=None):
    return _flag('FEATURE_GOALIE_WEAK', SHOW_GOALIE_WEAK, secrets, environ)

# V5.9: top-threat mini badges under Home's top-target card. FEATURE_THREAT_BADGES = "false" / =0 hides them.
SHOW_THREAT_BADGES = True


def show_threat_badges(secrets=None, environ=None):
    return _flag('FEATURE_THREAT_BADGES', SHOW_THREAT_BADGES, secrets, environ)

# V5.9: 'Fav MTL 52%' model win estimate on Tonight's Board tiles. FEATURE_WIN_PROB = "false" / =0 hides it.
SHOW_WIN_PROB = True


def show_win_prob(secrets=None, environ=None):
    return _flag('FEATURE_WIN_PROB', SHOW_WIN_PROB, secrets, environ)

# V5.9: Home 'Top four-leg parlay' becomes a live tracker (top 4 by model chance, locked at first puck drop, regulation
# only). FEATURE_PARLAY_TRACKER = "false" / =0 restores the V5.8 card exactly.
SHOW_PARLAY_TRACKER = True


def show_parlay_tracker(secrets=None, environ=None):
    return _flag('FEATURE_PARLAY_TRACKER', SHOW_PARLAY_TRACKER, secrets, environ)
