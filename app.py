"""Null's Playbook V5.6 (NULL NHL engine V3.2): source-first NHL slate, descriptive player form, odds, numbers and EdgeLab.

V5.5: neon-arena redesign (v55_ui.py / v55_state.py), EdgeLab research tab (edgelab_v55.py), GitHub-upload safety.
V5.6: tabs split into tabs/*.py (every file < 100 KB), live next-goal model (live_nextgoal_v56.py) fed by official NHL
play-by-play, goalies + real H2H in Matchup Center (h2h_v56.py), Numbers by game (numboard_v56.py), edge flags (edgeflags_v56.py)."""
from datetime import date, datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo
import pandas as pd
import re
import requests
import streamlit as st
from nhl_data import get_schedule, load_team, SEASON
from rankings import rank_players
from matchups import defense_summary, attach_matchups
from backtesting import make_snapshot, score_snapshot, top_k_metrics
from signals import build_signals, universal_day
from auto_signals import fetch_metadata
from storylines_v36 import build_storylines, combined_table
from storyline_v37 import select_storyline_watch
from storyline_v38 import fetch_history, merge_history
from data_integrity_v381 import merge_profile_batches, coverage_audit
from diagnostics_v382 import diagnostic_summary
from schedule_validation_v384 import audit_schedule
from roster_schedule_v385 import audit_roster_and_history
from history_v386 import fetch_multi_history, merge_multi_history, missing_player_ids
from storyline_v387 import separate_leaders
from ranking_integrity_v3871 import assign_statistical_ranks, validate_statistical_ranks
from historical_coverage_v388 import historical_coverage
from player_intelligence_v54 import intelligence_from_state as intel_from_state, four_picks as intel_four_picks, LEADER_LABELS as INTEL_LABELS
import goalies_v54 as gk
import matchup_center_v54 as mc
import probable_goalies_v54 as pgk
import prediction_tracker_v54 as trk

import ui_theme_v53 as ui
import v55_ui as v5
import v55_state as v5state
import edgelab_v55 as edgelab
import live_nextgoal_v56 as ng
import live_feed_v56 as lf
import live_state_v56 as lstate
import h2h_v56 as h2h
import edgeflags_v56 as eflags
import numboard_v56 as numboard
import mc_goalies_v56 as mcg
import v56_ui as v56
import os, threading
from tabs import run_tab

# V5.3.1: brand favicon from assets/ (emoji fallback if the file is missing).
st.set_page_config(page_title="Null's Playbook | NHL", page_icon=ui.page_icon(), layout='wide', initial_sidebar_state='collapsed')
from playbook_odds import compare_odds, CSV_TEMPLATE
from odds_intelligence_v46 import attach_model, order_opportunities, quote_audit, quotes_for_market, price_label, normalized_name, identity_ambiguities
from odds_api_v45 import fetch_odds, OddsFeedError
from snapshot_store import load_snapshot
from numerology_v48 import universal_day as num_universal_day, gematria as num_gematria, analyze_game as num_analyze_game
from player_targets_v49 import slate_targets as num_slate_targets
from home_leaders_v52 import all_targets as home_all_targets, choose_leaders as home_choose_leaders, gematria_shortlist as home_gematria_shortlist
from streamlit_autorefresh import st_autorefresh
import scorers_tonight_v58 as sctn
import parlay_v58 as parlay
import longshot_v58 as longshot
import numbers_v58_ui as numv58
import feature_flags_v58 as np_flags
import edgelab_v58 as elv58
import storylines_v58 as slx
import venue_v58 as vn
import gem_match_v58 as gmx
import goalie_weak_v59 as gweak
import threat_badges_v59 as threat
import winprob_v59 as winprob
import situational_v58 as sit
import xg_v59 as xgm
# V5.8: display-only 'Scored tonight' badges in every model view (markdown/html/dataframe pass-through proxy).
st = sctn.MarkingStreamlit(st)

# V5.3: one design system (ui_theme_v53.py) replaces the eight ad-hoc style blocks.
st.markdown(ui.stylesheet(),unsafe_allow_html=True)
# V5.3.1: native app logo where supported (st.logo arrived after Streamlit 1.35).
if hasattr(st,'logo') and ui.logo_path('mark',fallback=True):  # V5.7: crowned-N mark (PNG for widest support)
    try:
        st.logo(ui.logo_path('mark',fallback=True),icon_image=ui.logo_path('mark',fallback=True))
    except Exception:  # unsupported signature/SVG: the inline brand still renders
        pass


def np_eastern_today():
    """Slate dates follow the NHL's Eastern calendar, not the server clock (UTC on Streamlit Cloud)."""
    return ui.eastern_today()

with st.sidebar:
    st.markdown(ui.brand('full','sm'),unsafe_allow_html=True)
    st.caption('DATA · NUMBERS · EDGES')
    st.markdown('**🏒 NHL**')
    st.caption('Additional leagues require separate data feeds. NHL remains the live statistical engine.')
    st.divider()
    st.markdown('**Sportsbook intelligence**')
    st.caption('Automatic odds and optional CSV import.')


# Session-local 30-minute timer: reruns only while this Streamlit page is open.
# Data calls are cached independently and the user can force a refresh below.
st_autorefresh(interval=30 * 60 * 1000, key='playbook_v42_30min_timer')

# One shared date for every screen; a date change automatically invalidates the slate.
_np_date_col,_np_theme_col=st.columns([3,2])
with _np_date_col:
    np_selected_date=st.date_input('📅 NHL slate date',np_eastern_today(),key='playbook_v42_date')
with _np_theme_col:  # V5.5: server-side theme (native widget; no fake HTML toggles)
    _np_theme_opts=list(v5.THEMES)
    if hasattr(st,'segmented_control'):
        _np_theme_label=st.segmented_control('🎨 Theme',_np_theme_opts,default='Night',key='v55_theme')
    else:
        _np_theme_label=st.radio('🎨 Theme',_np_theme_opts,horizontal=True,key='v55_theme')
v5.set_theme(v5.theme_from_label(_np_theme_label or 'Night'))
st.markdown(v5.page_style(),unsafe_allow_html=True)
np_day=np_selected_date.isoformat()
# Load the last completed, validated snapshot before any live NHL API calls.
# Research uses the same session state so it does not recompute on each visit.
np_snapshot=load_snapshot(np_day)
if np_snapshot is not None:
    _previous=st.session_state.get('v44_snapshot_at')
    if _previous != (np_day, np_snapshot['updated_at']):
        st.session_state['signals_ranked']=pd.DataFrame(np_snapshot['rankings'])
        st.session_state['signals_day']=np_day
        st.session_state['v44_snapshot_at']=(np_day,np_snapshot['updated_at'])
        st.session_state['v42_last_rank']={'key':(np_day,3,True),'at':datetime.now(timezone.utc),'snapshot':True}
        if np_snapshot.get('history'):
            st.session_state['history_v386']=pd.DataFrame(np_snapshot['history'])
            st.session_state['history_v386_day']=np_day
            st.session_state['history_v386_years']=3

def np_goalie_columns(ranked, day, games):
    """V5.8: rankings 'Starting goalie' / 'Goalie adjustment' from the SAME probable-starter source (starters_cached) and
    the same situational goalie step the next-goal model uses. Never invents a starter; never raises."""
    if ranked is None or getattr(ranked, 'empty', True) or not games:
        return ranked
    try:
        sg=mc.slate_games(games)
        starters=starters_cached(day,tuple((g['key'],g['game_id'],g['away'],g['home'],g['status']) for g in sg))[0] if sg else {}
        parts=np_flags.model_parts(st.secrets) if np_flags.model_situational(st.secrets) else ()
        ctx=sit.with_starters(situ_cached(day,SEASON,parts) if 'goalie' in parts else sit.context(parts=()),starters)
        return pd.DataFrame(sit.goalie_columns(ranked.to_dict('records'),ctx))
    except Exception:  # keep the rankings visible even if the goalie lookup fails
        return ranked



@st.cache_data(ttl=1800, show_spinner=False)
def schedule_cached(day):
    return get_schedule(day)

@st.cache_data(ttl=1800, show_spinner=False)
def team_cached(team, day):
    return load_team(team, day, SEASON)

@st.cache_data(ttl=1800, show_spinner=False)
def defense_cached(team, day):
    return defense_summary(team, day, SEASON)

@st.cache_data(ttl=1800, show_spinner=False)
def goalies_cached(teams, season):
    """V5.4: NHL club-stats goalie rows for the given teams (parallel, cached 30 min). Never raises."""
    rows, errors = [], []
    teams = [t for t in dict.fromkeys(teams) if t]
    if not teams:
        return rows, errors
    with ThreadPoolExecutor(max_workers=min(8, len(teams))) as pool:
        futures = {pool.submit(gk.fetch_team_goalies, t, season): t for t in teams}
        for f in as_completed(futures):
            try:
                rows.extend(f.result())
            except Exception as exc:  # network/HTTP/JSON -> team shown as 'No data'
                errors.append(f'{futures[f]}: {type(exc).__name__}')
    return rows, sorted(errors)

@st.cache_data(ttl=3 * 3600, show_spinner=False)
def situ_cached(day, season, parts):
    """V5.8: situational next-goal inputs (NHL stats API: PP / TOI / goalie / team PP reports, games before ``day``).
    Cached 3 h. Never raises: a failed report leaves its adjustment neutral.
    V5.9: with 'xg' in parts the MoneyPuck shot-quality data (xg_cached) is attached, gated per day by xg_v59.for_day."""
    ctx = sit.fetch_context(day, season, parts=parts)
    return sit.with_xg(ctx, xg_cached(season), day, season) if 'xg' in (parts or ()) else ctx

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def xg_cached(season):
    """V5.9: MoneyPuck season skater xG summary (one listed CSV, credited on screen). Cached 6 h. Never raises."""
    return xgm.fetch(season)

@st.cache_data(ttl=pgk.STARTER_TTL_SECONDS, show_spinner=False)
def starters_cached(day, games_key):
    """V5.4: probable/confirmed starters, cached 5 min (pregame starters change slowly). Never raises."""
    games = [dict(zip(('key','game_id','away','home','status'), g)) for g in games_key]
    return pgk.fetch_starters(day, games)

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def v55_rosters_cached(teams):
    """V5.5: jersey numbers for the Home design (NHL roster feed, parallel, cached 6 h). Never raises."""
    return v5state.safe_many(lambda t: v5state.fetch_roster_numbers(t, requests.get), teams)

@st.cache_data(ttl=900, show_spinner=False)
def v55_logs_cached(pids):
    """V5.5: last-10 game logs for sparklines (parallel, cached 15 min). Never raises."""
    return v5state.safe_many(lambda p: v5state.fetch_game_log(p, SEASON, requests.get), pids)

@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def historical_cached(day, years, player_ids, games_signature, _ranked_rows, _games):
    return fetch_multi_history(_ranked_rows, _games, day, max_players=len(_ranked_rows), years=years)

# ---------------------------------------------------------------- V5.6 live feeds (cached; never raise)
# PLAYBOOK_V56_PBP_DIR (preview/dev only): read {id}.json / score.json from a folder of real captured payloads instead of the network.
_V56_DIR=os.environ.get('PLAYBOOK_V56_PBP_DIR','')

def _v56_read(name):
    import json as _json
    with open(os.path.join(_V56_DIR,name),encoding='utf-8') as fh:
        return _json.load(fh)

@st.cache_data(ttl=25, show_spinner=False)
def v56_scores_cached(day):
    """Official score endpoint (states, scores, clock) for the board/live strip. Cached 25 s. Never raises."""
    try:
        return (lf.parse_scores(_v56_read('score.json')) if _V56_DIR else lf.fetch_scores(day, requests.get)), None
    except Exception as exc:
        return {}, f'{type(exc).__name__}'

@st.cache_data(ttl=25, show_spinner=False)
def v56_pbp_raw(game_id):
    """Raw play-by-play, cached 25 s (live cadence is 30 s). Raises on failure (exceptions are not cached)."""
    return _v56_read(f'{game_id}.json') if _V56_DIR else lf.fetch_pbp(game_id, requests.get)

@st.cache_resource(show_spinner=False)
def v56_pollers():
    """One Poller per game for the server process: last good state, eventId dedupe, backoff + jitter, stops when final."""
    return {}, threading.Lock()

def v56_poll(game_id, force=False):
    pollers, lock = v56_pollers()
    with lock:
        p = pollers.get(str(game_id))
        if p is None:
            p = pollers[str(game_id)] = ng.Poller(str(game_id), v56_pbp_raw)
        if force:
            v56_pbp_raw.clear()
        return p.poll(force=force), p

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def v56_h2h_cached(matchups, day, season):
    """REAL shooter-vs-goalie H2H from past meetings' PBP for every (away, home) pair (local file cache, 5 MB cap).
    Parallel across games, cached 6 h (completed games never change). Never raises."""
    def one(pair):
        records, errors = h2h.load_meetings(pair[0], pair[1], day, season, requests.get)
        pairs, names = h2h.aggregate(records)
        return {'pairs': pairs, 'names': names, 'games': len(records), 'errors': errors,
                'dates': sorted(r.get('date') or '' for r in records)}
    if not matchups:
        return {}
    with ThreadPoolExecutor(max_workers=min(6, len(matchups))) as pool:
        return dict(zip(matchups, pool.map(one, matchups)))

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def v59_goalie_weak_cached(goalie_id, team, day, season):
    """V5.9: REAL goalie game logs + PBP of his games vs ``team`` (goalie_weak_v59; disk cache). Never raises."""
    return gweak.load(goalie_id, team, day, season, requests.get)

def format_game_time(raw):
    try:
        return datetime.fromisoformat(str(raw).replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%-I:%M %p ET')
    except (TypeError, ValueError, OverflowError):
        return 'Time pending'

@st.cache_resource
def history_executor():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix='playbook-history')

@st.fragment(run_every='10s')
def history_status(day, quiet=False):
    job=st.session_state.get('v43_history_job')
    if not job or job['day'] != day:
        return
    future=job['future']
    if not future.done():
        if not quiet:
            st.caption('⏳ Three-season opponent history is updating separately. Rankings remain usable.')
        return
    if st.session_state.get('v43_history_completed') == job['key']:
        return
    st.session_state['v43_history_completed']=job['key']
    try:
        history, errors=future.result()
        st.session_state['history_v386']=history
        st.session_state['history_v386_day']=day
        st.session_state['history_v386_years']=3
        st.session_state['history_v386_errors']=errors
        st.session_state['v42_history_loaded_at']=datetime.now(timezone.utc)
        st.rerun()
    except Exception as exc:
        st.session_state['v531_history_error']=f'{type(exc).__name__}: {exc}'
        if not quiet:
            st.warning(f'History unavailable: {type(exc).__name__}: {exc}')


# V5.1: Load sportsbook data once for all tabs, not only inside Odds.
# Streamlit executes tab bodies in order; Home must not depend on Odds running first.
@st.cache_data(ttl=1800,show_spinner=False)
def np_live_odds_cached(api_key, regions, markets):
    return fetch_odds(api_key,regions=regions,markets=markets)

def np_api_key():
    try:
        return st.secrets.get('ODDS_API_KEY','')
    except (FileNotFoundError, KeyError):
        return ''


_np_live_quotes=pd.DataFrame()
_np_live_error=None
_np_live_warnings=[]
_np_key=np_api_key()
if _np_key:
    try:
        _np_live_quotes,_np_live_warnings=np_live_odds_cached(_np_key,'us','player_goal_scorer_anytime')
    except (OddsFeedError,ValueError,KeyError,TypeError) as _exc:
        _np_live_error=str(_exc)
_np_csv_quotes=st.session_state.get('playbook_odds_data')
_np_source=st.session_state.get('v46_source','Automatic API')
_np_frames=[]
if _np_source in ('Automatic API','Combine both') and not _np_live_quotes.empty:
    _np_frames.append(_np_live_quotes)
if _np_source in ('Uploaded CSV','Combine both') and isinstance(_np_csv_quotes,pd.DataFrame) and not _np_csv_quotes.empty:
    _np_frames.append(_np_csv_quotes)
_np_shared_quotes=pd.concat(_np_frames,ignore_index=True) if _np_frames else pd.DataFrame()
_np_shared_clean=pd.DataFrame()
_np_shared_discrepancies=pd.DataFrame()
_np_shared_error=None
if not _np_shared_quotes.empty:
    try:
        _np_shared_clean,_np_shared_discrepancies=compare_odds(_np_shared_quotes)
    except (ValueError,KeyError,TypeError) as _exc:
        _np_shared_error=str(_exc)

_np_scorer_slot=st.container()  # V5.8: 'Scored tonight' header chip (filled after the live state below)
# V5.8: Track Record is hidden behind one feature flag (feature_flags_v58); its tracker/DB/auto-save keep running.
np_show_track=np_flags.show_track_record(st.secrets)
_np_tab_labels=['🏠 Home','🎯 Matchup Center','⚡ Odds','📊 Research','🔮 Numbers']+(['📈 Track Record'] if np_show_track else [])+['🧪 EdgeLab','⏱ Live Next Goal','🚩 Edge Flags','📰 Storylines']
_np_tab_map=dict(zip(_np_tab_labels,st.tabs(_np_tab_labels)))
np_home_tab,np_mc_tab,np_odds_tab,np_research_tab,np_numbers_tab=(_np_tab_map[k] for k in _np_tab_labels[:5])
np_track_tab=_np_tab_map.get('📈 Track Record')
np_edgelab_tab,np_nextgoal_tab,np_edgeflags_tab,np_storylines_tab=(_np_tab_map[k] for k in _np_tab_labels[-4:])
# V5.8: rankings 'Starting goalie' / 'Goalie adjustment' read the same starter source as the model
if st.session_state.get('signals_day')==np_day and 'signals_ranked' in st.session_state:
    st.session_state['signals_ranked']=np_goalie_columns(st.session_state['signals_ranked'],np_day,
        np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day))
run_tab('live', globals())  # V5.6: shared live state (scores, PBP, next-goal model) for Home, Matchup Center and the new tabs
# V5.8: one scorer record per slate date from the same polled play-by-play (a new date starts empty).
sctn.for_slate(st.session_state, np_day, sctn.from_pbp(_v56_pbp, np_day, demo=bool(_V56_DIR)))

def np_scorer_signature(rec):
    return tuple(sorted((p, r['goals']) for p, r in ((rec or {}).get('players') or {}).items()))

@st.fragment(run_every=('45s' if _v56_live_n else None))
def np_scorer_watch():
    """Header chip; while a game is live it re-polls PBP (cached ~25 s) and reruns the app only when a new goal lands."""
    rec = st.session_state.get(sctn.STATE_KEY)
    if _v56_live_n:
        try:
            _pbp, _ = v56_collect(False)
            fresh = sctn.from_pbp(_pbp, np_day, demo=bool(_V56_DIR))
        except Exception:
            fresh = rec
        if fresh is not None and np_scorer_signature(fresh) != np_scorer_signature(rec):
            sctn.for_slate(st.session_state, np_day, fresh)
            st.rerun()
    chip = sctn.ticker(rec)
    if chip:
        st._st.markdown(v5.inline(chip, 'v58-sc'), unsafe_allow_html=True)

with _np_scorer_slot:
    np_scorer_watch()

def np_tracker():
    """V5.4: open the prediction tracker store; None (with the reason) if the filesystem refuses."""
    try:
        return trk.connect(), None
    except Exception as exc:  # read-only or unavailable filesystem
        return None, f'{type(exc).__name__}: {exc}'

def np_track_state():
    conn, err = np_tracker()
    if conn is None:
        return None, [], pd.DataFrame(), err
    try:
        evals = trk.history(conn)
        return conn, evals, trk.player_records(evals), None
    except Exception as exc:
        return conn, [], pd.DataFrame(), f'{type(exc).__name__}: {exc}'

with np_home_tab:
    run_tab('home', globals())

with np_odds_tab:
    run_tab('odds', globals())

with np_research_tab:
    run_tab('research', globals())

with np_numbers_tab:
    run_tab('numbers', globals())

with np_mc_tab:
    run_tab('matchup', globals())

with np_edgelab_tab:
    run_tab('edgelab', globals())

if np_track_tab is not None:  # V5.8: hidden unless FEATURE_TRACK_RECORD is on
    with np_track_tab:
        run_tab('track', globals())

with np_nextgoal_tab:
    run_tab('nextgoal', globals())

with np_edgeflags_tab:
    run_tab('edgeflags', globals())

with np_storylines_tab:
    run_tab('storylines', globals())

