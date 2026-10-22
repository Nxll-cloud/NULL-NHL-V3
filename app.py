"""Null's Playbook V5.4 (NULL NHL engine V3.2): source-first NHL slate, descriptive player form, odds and numbers."""
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

# V5.3: one design system (ui_theme_v53.py) replaces the eight ad-hoc style blocks.
st.markdown(ui.stylesheet(),unsafe_allow_html=True)
# V5.3.1: native app logo where supported (st.logo arrived after Streamlit 1.35).
if hasattr(st,'logo') and ui.logo_path('full'):
    try:
        st.logo(ui.logo_path('full'),icon_image=ui.logo_path('mark'))
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
np_selected_date=st.date_input('📅 NHL slate date',np_eastern_today(),key='playbook_v42_date')
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

@st.cache_data(ttl=pgk.STARTER_TTL_SECONDS, show_spinner=False)
def starters_cached(day, games_key):
    """V5.4: probable/confirmed starters, cached 5 min (pregame starters change slowly). Never raises."""
    games = [dict(zip(('key','game_id','away','home','status'), g)) for g in games_key]
    return pgk.fetch_starters(day, games)

@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def historical_cached(day, years, player_ids, games_signature, _ranked_rows, _games):
    return fetch_multi_history(_ranked_rows, _games, day, max_players=len(_ranked_rows), years=years)

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

np_home_tab,np_mc_tab,np_odds_tab,np_research_tab,np_numbers_tab,np_track_tab=st.tabs(['🏠 Home','🎯 Matchup Center','⚡ Odds','📊 Research','🔮 Numbers','📈 Track Record'])

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

    import html as _np_html
    _home_snapshot_note=('Snapshot '+str(np_snapshot['updated_at'])[:16].replace('T',' ')+' UTC') if np_snapshot is not None else 'Live fallback'
    st.markdown(ui.hero('V5.4 · NHL COMMAND CENTER','Your NHL command center.','Verified rankings · matchup intelligence · numbers · sportsbook price comparison',
        chips=[(f'📅 {np_day}','muted'),(_home_snapshot_note,'ok' if np_snapshot is not None else 'warn'),('Real NHL data only','stat')],brand_kind='full'),unsafe_allow_html=True)
    if np_snapshot is not None:
        st.caption('🟢 Saved rankings updated: '+str(np_snapshot['updated_at'])[:19].replace('T',' ')+' UTC · '+str(len(np_snapshot['rankings']))+' players · auto slate snapshots, 30-minute updates')
        if np_snapshot.get('errors'):
            st.caption(f'⚠️ {len(np_snapshot["errors"])} data retrieval warnings in saved snapshot')
    else:
        st.warning('No scheduled snapshot for this date yet. Live fallback may take 30 seconds or longer. Run the GitHub workflow to precompute it.')
    history_status(np_day, quiet=True)  # V5.3.1: Home never shows history/coverage status
    if st.session_state.get('v42_last_rank') and st.session_state.get('signals_day')==np_day:
        st.caption('Rankings last updated: '+st.session_state['v42_last_rank']['at'].astimezone(ZoneInfo('America/New_York')).strftime('%b %-d, %-I:%M %p ET'))
    try:
        np_games=np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day)
    except (requests.RequestException, ValueError, KeyError, TypeError) as np_err:
        np_games=[]
        st.warning(f'Unable to load matchups: {np_err}')
    np_games=[g for g in (np_games or []) if isinstance(g,dict)]
    np_ranked=st.session_state.get('signals_ranked')
    np_ready=isinstance(np_ranked,pd.DataFrame) and not np_ranked.empty and st.session_state.get('signals_day')==np_day
    _books=int(_np_shared_clean['sportsbook'].nunique()) if not _np_shared_clean.empty else '—'
    st.markdown(ui.stat_strip([('Games on slate',len(np_games),'odds'),('Ranked players',len(np_ranked) if np_ready else '—','stat'),
        ('Sportsbooks loaded',_books,'overlap'),('Universal day',num_universal_day(np_day),'gem')]),unsafe_allow_html=True)
    # V5.4: compact accuracy strip only (details live in the Track Record tab).
    _trk_conn,_trk_evals,_trk_records,_trk_err=np_track_state()
    _trk7=trk.rolling(_trk_evals,7)
    st.markdown(ui.track_strip(_trk7['rate'],_trk7['slates'],_trk7['hits'],_trk7['picks'],sum(1 for e in _trk_evals if e['status']=='pending')),unsafe_allow_html=True)
    _trk_badges=trk.badge_lookup(_trk_records)
    if np_games:
        st.markdown(ui.section('Matchup center','Tonight’s games · Eastern time','🏒','odds'),unsafe_allow_html=True)
        st.markdown('<div class="np-hscroll">'+''.join(ui.matchup_chip(g.get('Away',''),g.get('Home',''),format_game_time(g.get('Start (UTC)'))) for g in np_games[:16])+'</div>',unsafe_allow_html=True)
    else:
        st.info('No NHL games are scheduled for this date. Pick another date above.')
    # V5.2: four genuinely distinct leaders, computed from the selected day's slate.
    _home_targets=home_all_targets(np_games,np_ranked if np_ready else None,np_day)
    _home_leaders=home_choose_leaders(np_ranked if np_ready else None,_home_targets,_np_shared_discrepancies)
    st.markdown(ui.section('Four distinct slate leaders','One different player per category · unavailable categories are left empty, never invented','👑','stat'),unsafe_allow_html=True)
    _leader_meta=[('statistical','⚡ Statistical leader','stat'),('gematria','🔮 Gematria leader','gem'),('odds','📈 Price-gap leader','odds'),('overlap','🔗 Stats + numbers','overlap')]
    _leader_html=[]
    for _key,_label,_tone in _leader_meta:
        _p=_home_leaders.get(_key)
        if _p is None:
            _leader_html.append(ui.leader_card(_tone,_label))
            continue
        _form=ui.format_form_pct(_p.get('form'))
        _counts=[(f'D {len(_p.get("day",[]))}','day'),(f'T {len(_p.get("team_matches",[]))}','team'),(f'A {len(_p.get("arena_matches",[]))}','arena')]
        if _key=='statistical':
            _metric,_caption,_badges=_form,'Goal-scoring Form %',[('Stats','stat')]
        elif _key=='gematria':
            _metric,_caption,_badges=str(_p['matches']),'Symbolic matches (D/T/A)',_counts
        elif _key=='odds':
            _metric=price_label(_p.get('best_odds'))
            _caption=f'Best at {ui.esc(_p.get("best_sportsbook"),"sportsbook")}'
            _badges=[(f'+{ui.fmt_num(_p.get("gap_pct"))}% gap','odds'),('Unverified identity','muted')]
        else:
            _metric,_caption,_badges=f'{_p["matches"]} · {ui.format_form_pct(_p.get("form"))}','Matches · separate Form %',[('Stats','stat'),('Numbers','gem')]
        try:
            _tb=_trk_badges.get(trk.player_key(_p.get('player_id'),_p.get('player')))
        except trk.TrackerError:
            _tb=None
        if _tb: _badges=list(_badges)+[(_tb,'stat' if _tb.startswith('Hot') else 'muted')]
        _leader_html.append(ui.leader_card(_tone,_label,_p['player'],_p.get('team',''),_p.get('opponent',''),_p.get('player_id',''),_metric,_caption,_badges,season=SEASON))
    st.markdown('<div class="np-leads">'+''.join(_leader_html)+'</div>',unsafe_allow_html=True)
    # V5.4: Research's Player Intelligence picks, duplicated here from the SAME shared function.
    _np_intel,_=intel_from_state(st.session_state,np_day)
    _np_picks=intel_four_picks(_np_intel)
    st.markdown(ui.section('Player intelligence model','Same four picks as Research · form and storyline evidence are separate, not probabilities','🧠','overlap'),unsafe_allow_html=True)
    st.markdown(ui.intel_row([ui.intel_card(_k,_l,_np_picks.get(_k),season=SEASON) for _k,_l in INTEL_LABELS]),unsafe_allow_html=True)
    # V5.4: auto-save today's/future predictions (idempotent; never touches a locked slate).
    if _trk_conn is not None and np_ready and np_day>=np_eastern_today().isoformat():
        try:
            _trk_rows=trk.build_prediction_rows(assign_statistical_ranks(np_ranked.copy()),_home_leaders,np_games,home_gematria_shortlist(_home_targets,5))
            _trk_sig=(np_day,tuple(sorted((r['player_key'],r['source'],r['rank']) for r in _trk_rows)))
            if st.session_state.get('v54_trk_sig')!=_trk_sig:
                _starts=[g.get('Start (UTC)') for g in np_games if g.get('Start (UTC)')]
                _first=min(_starts) if _starts else None
                _lock=bool(_first) and datetime.now(timezone.utc)>=datetime.fromisoformat(str(_first).replace('Z','+00:00'))
                _res=trk.save_predictions(_trk_conn,np_day,_trk_rows,n_games=len(np_games),lock=_lock)
                st.session_state['v54_trk_sig']=_trk_sig
                st.session_state['v54_trk_status']=_res
        except Exception as _trk_exc:  # tracking must never break Home
            st.session_state['v54_trk_status']={'status':'error','error':str(_trk_exc)}
    st.markdown(ui.day_banner(np_day,num_universal_day(np_day)),unsafe_allow_html=True)
    st.markdown(ui.section('Strongest gematria alignments','Top ten symbolic matches across the slate · D = day, T = team, A = arena','🔮','gem'),unsafe_allow_html=True)
    _gem_cards=[ui.gem_card(_i,_p['player'],_p['team'],_p.get('player_id',''),_p['matches'],_p['form'],len(_p['day']),len(_p['team_matches']),len(_p['arena_matches']),season=SEASON)
                for _i,_p in enumerate(home_gematria_shortlist(_home_targets,10),1)]
    if _gem_cards: st.markdown('<div class="np-hscroll">'+''.join(_gem_cards)+'</div>',unsafe_allow_html=True)
    else: st.info('Player gematria rankings will appear when this slate’s roster rankings are available.')
    st.caption('Gematria matches are numerical coincidences, not evidence of a higher likelihood of scoring.')
    if _home_targets:
        st.markdown(ui.section('Player targets by matchup','Both teams are grouped under each game · expand for the top numerical matches per roster','🎯','team'),unsafe_allow_html=True)
        for _match in _home_targets:
            _g=_match['game'];_away=_g['away'];_home=_g['home']
            with st.expander(f'{_away}  vs  {_home} · {format_game_time(_g.get("start"))} · {_g["arena"] or "Venue unavailable"}'):
                _cols=st.columns(2)
                for _col,_side,_code in zip(_cols,('away','home'),(_away,_home)):
                    with _col:
                        _rows=[ui.team_head(_code,_g.get(_side+'_name') or _code,'Top numerical matches')]
                        for _ix,_p in enumerate(_match[_side+'_targets'][:3],1):
                            _rows.append(ui.target_row(_ix,_p['player'],_code,_p.get('player_id',''),_p['matches'],_p['form'],len(_p['day']),len(_p['team_matches']),len(_p['arena_matches']),season=SEASON))
                        st.markdown(''.join(_rows),unsafe_allow_html=True)
    if not np_ready:
        if np_games:
            st.info('⏳ Automatically loading the full NHL slate. This may take a few minutes on first load.')
    else:
        try:
            np_view=assign_statistical_ranks(np_ranked.copy())
        except (ValueError,KeyError,TypeError) as _rank_err:
            np_view=None
            st.warning(f'Statistical rankings could not be validated for display: {_rank_err}')
        if np_view is not None:
            np_view=merge_history(np_view, st.session_state.get('history_v38') if st.session_state.get('history_v38_day')==np_day else None)
            np_view=merge_multi_history(np_view, st.session_state.get('history_v386') if st.session_state.get('history_v386_day')==np_day else None)
            st.markdown(ui.section('Top statistical candidates','Ranked by the V3.2 adjusted index · shown as Form %','⚡','stat'),unsafe_allow_html=True)
            np_cards=[]
            for _,r in np_view.sort_values('Statistical rank').head(8).iterrows():
                t=r.get('Team','');rank=int(r.get('Statistical rank',0))
                np_cards.append(f'<div class="np-feature"><div class="np-feature-top"><span class="np-rank">#{rank}</span>{ui.avatar(ui.mug_url(t,r.get("Player ID"),SEASON),"lg")}</div>'
                                f'<b>{ui.esc(r.get("Player",""))}</b><small>{ui.logo(t,16)} {ui.esc(t)} · Rank #{rank}</small>'
                                f'<div class="np-feature-score">{ui.format_form_pct(r.get("V3.2 Adjusted Index"))}<span> FORM %</span></div></div>')
            st.markdown('<div class="np-feature-scroll">'+''.join(np_cards)+'</div>',unsafe_allow_html=True)
            st.markdown(ui.section('Statistical leaderboard','Top ten · Form % = share of the 100-point form benchmark (clipped at 100%)','📊','stat'),unsafe_allow_html=True)
            _adjust=st.toggle('Use track record to adjust rankings',value=False,key='v54_track_adjust',
                              help='OFF (default): rankings are unchanged and track record only adds badges. ON: this leaderboard is re-sorted by a bounded (±5%) track-record adjustment.') if hasattr(st,'toggle') else st.checkbox('Use track record to adjust rankings',value=False,key='v54_track_adjust')
            _board_src=trk.apply_track_record(np_view.sort_values('Statistical rank'),_trk_records,enabled=_adjust)
            np_cols=[c for c in ['Statistical rank','Player','Team','V3.2 Adjusted Index','Shots/G L5','Track adj'] if c in _board_src]
            _board=ui.with_form_pct(_board_src[np_cols].head(10)).drop(columns=['V3.2 Adjusted Index'])
            _cfg={'Statistical rank':st.column_config.NumberColumn('Rank',format='#%d',width='small'),
                'Shots/G L5':st.column_config.NumberColumn('Shots/G · L5',format='%.1f'),
                'Track adj':st.column_config.NumberColumn('Track adj',format='%+.3f')}
            _cfg.update(ui.form_pct_config(st,progress=True))
            st.dataframe(_board,hide_index=True,use_container_width=True,column_config=_cfg)
            if _adjust: st.caption('Track-record adjustment ON: order uses the raw V3.2 index × (1 + adj), adj capped at ±5% with ≥3 graded picks. The four leaders above are unchanged.')
            # V5.3.1: historical coverage is shown in Research only, never on Home.
    st.markdown(ui.section('Sportsbook price intelligence','Best available anytime-goal prices across books','📈','odds'),unsafe_allow_html=True)
    if not _np_shared_discrepancies.empty:
        st.caption(f"{len(_np_shared_clean):,} validated quotes · {_np_shared_clean['sportsbook'].nunique()} sportsbooks · {len(_np_shared_discrepancies)} comparable props")
        _np_home_best=_np_shared_discrepancies.assign(_gap=pd.to_numeric(_np_shared_discrepancies['decimal_price_improvement_pct'],errors='coerce')).sort_values('_gap',ascending=False,na_position='last').head(3)
        _rows=[]
        for _,_np_o in _np_home_best.iterrows():
            _rows.append(f'<div class="np-orow"><div><b>{ui.esc(_np_o["player"])}</b><br/><small>{ui.esc(_np_o["best_sportsbook"])} · +{ui.fmt_num(_np_o["_gap"])}% payout gap</small></div><strong>{ui.esc(price_label(_np_o["best_odds"]))}</strong></div>')
        st.markdown(''.join(_rows),unsafe_allow_html=True)
        st.caption('Open Odds for full comparisons. Prices are not verified player identities or scoring probabilities.')
    elif _np_live_error:
        st.warning(f'Odds feed unavailable: {_np_live_error}')
    elif _np_shared_error:
        st.warning(f'Odds validation issue: {_np_shared_error}')
    elif _np_key and _np_source != 'Uploaded CSV':
        st.info('Odds API connected, but no comparable goal-scorer quotes are currently available. Check Odds for coverage details.')
    else:
        st.info('No odds feed configured for this source. Add ODDS_API_KEY to Streamlit Secrets or upload a CSV in Odds.')
    st.markdown(ui.footer("NULL’S PLAYBOOK · HOME · MATCHUP CENTER · ODDS · RESEARCH · NUMBERS · TRACK RECORD"),unsafe_allow_html=True)


with np_odds_tab:
    import html as _odds_html
    _odds_src_now=st.session_state.get('v46_source','Automatic API')
    st.markdown(ui.hero('NULL’S PLAYBOOK · ODDS INTELLIGENCE','Odds Intelligence','Find the strongest prices. Compare the market. Follow your model.',
        chips=[(f'Source · {_odds_src_now}','odds'),('API connected' if _np_key else 'No API key · CSV import available','ok' if _np_key else 'warn'),('Anytime goal scorer','muted')],tone='odds'),unsafe_allow_html=True)
    api_df=_np_live_quotes
    if _np_live_error:
        st.warning(f'Live prices unavailable: {_np_live_error}')
    elif not _np_key:
        st.info('Connect your odds feed in app secrets to enable automatic price comparison. CSV import is also available.')
    elif _np_live_warnings:
        st.caption(f'Coverage notice: {len(_np_live_warnings)} events could not be retrieved.')
    with st.expander('⚙️ Import & display preferences',expanded=False):
        source_choice=st.radio('Odds source',['Automatic API','Uploaded CSV','Combine both'],horizontal=False,key='v46_source')
        uploaded_odds=st.file_uploader('Optional CSV odds import',type=['csv'],key='playbook_odds_upload')
        if uploaded_odds is not None:
            try:
                st.session_state['playbook_odds_data']=pd.read_csv(uploaded_odds,dtype={'event_id':str,'line':str})
            except (ValueError,UnicodeError) as exc:
                st.warning(f'CSV could not be read: {exc}')
        st.download_button('CSV template',CSV_TEMPLATE,file_name='playbook_odds_template.csv',mime='text/csv')
        st.caption('Quote coverage depends on your data subscription. Credentials and technical source fields are not displayed.')
    source_choice=st.session_state.get('v46_source','Automatic API')
    csv_df=st.session_state.get('playbook_odds_data')
    selected_frames=[]
    if source_choice in ('Automatic API','Combine both') and isinstance(api_df,pd.DataFrame) and not api_df.empty:
        selected_frames.append(api_df)
    if source_choice in ('Uploaded CSV','Combine both') and isinstance(csv_df,pd.DataFrame) and not csv_df.empty:
        selected_frames.append(csv_df)
    if selected_frames:
        raw_quotes=pd.concat(selected_frames,ignore_index=True)
        try:
            price_rows,discrepancies=compare_odds(raw_quotes)
            audit=quote_audit(raw_quotes,price_rows)
            st.session_state['v46_odds_count']=int(price_rows['sportsbook'].nunique())
            _best_gap=pd.to_numeric(discrepancies.get('decimal_price_improvement_pct'),errors='coerce') if not discrepancies.empty else pd.Series(dtype=float)
            st.markdown(ui.stat_strip([('Sportsbooks',int(price_rows['sportsbook'].nunique()),'odds'),('Matched props',len(discrepancies),'overlap'),
                ('Valid quotes',f'{len(price_rows):,}','muted'),('Largest gap',(ui.fmt_num(_best_gap.max())+'%') if _best_gap.notna().any() else '—','stat')]),unsafe_allow_html=True)
            if audit['excluded_or_consolidated']:
                st.caption(f"{audit['received']:,} received · {audit['accepted']:,} retained · {audit['excluded_or_consolidated']:,} excluded or duplicate quotes consolidated")
            else:
                st.caption(f"{audit['accepted']:,} validated quotes")
            if discrepancies.empty:
                st.info('No identical player props currently have prices from at least two sportsbooks.')
            else:
                model_ranked=st.session_state.get('signals_ranked')
                if not (isinstance(model_ranked,pd.DataFrame) and st.session_state.get('signals_day')==np_day):
                    model_ranked=None
                combined=attach_model(discrepancies,model_ranked)
                st.markdown(ui.section('Market scanner','Identical event, market and line compared across books','📈','odds'),unsafe_allow_html=True)
                st.caption('Identity verification is required before a price gap can be considered actionable. Name-only provider quotes are unverified.')
                f1,f2,f3,f4=st.columns(4)
                with f1:
                    view_mode=st.selectbox('Sort by',['Biggest discrepancy','Model-backed','Longshots'],key='v46_mode')
                with f2:
                    book_min=st.selectbox('Books compared',[2,3,4,5],key='v46_min_books')
                with f3:
                    rank_limit=st.selectbox('Statistical shortlist',['All players','Top 25','Top 50','Top 100'],key='v47_rank_filter')
                with f4:
                    identity_view=st.selectbox('Identity review',['All quotes (unverified)','Flagged name collisions only'],key='v47_identity_view')
                show=combined[combined['sportsbooks_compared']>=book_min]
                if rank_limit!='All players':
                    show=show[pd.to_numeric(show['model_rank'],errors='coerce')<=int(rank_limit.split()[-1])]
                if identity_view=='Flagged name collisions only':
                    show=show[show['identity_status'].str.startswith('Ambiguous',na=False)]
                show=order_opportunities(show,view_mode)
                st.caption('Price gaps compare identical events and markets. A large gap does not establish positive expected value.')
                if show.empty:
                    st.info('No props match these filters.')
                else:
                    _overview=show.head(30)[[c for c in ['player','team','best_odds','best_sportsbook','worst_odds','worst_sportsbook','sportsbooks_compared','decimal_price_improvement_pct','model_rank'] if c in show]].copy()
                    for _c in ('best_odds','worst_odds'):
                        if _c in _overview: _overview[_c]=_overview[_c].map(price_label)
                    _overview['decimal_price_improvement_pct']=pd.to_numeric(_overview['decimal_price_improvement_pct'],errors='coerce')
                    _gmax=float(_overview['decimal_price_improvement_pct'].max()) if _overview['decimal_price_improvement_pct'].notna().any() else 0.0
                    with st.expander('📋 Compact comparison table',expanded=False):
                        st.dataframe(_overview,hide_index=True,use_container_width=True,column_config={
                            'player':'Player','team':'Team','best_odds':'Best','best_sportsbook':'Best book','worst_odds':'Low','worst_sportsbook':'Low book',
                            'sportsbooks_compared':st.column_config.NumberColumn('Books',format='%d'),
                            'decimal_price_improvement_pct':st.column_config.ProgressColumn('Payout gap',format='%.1f%%',min_value=0.0,max_value=max(_gmax,1.0)),
                            'model_rank':st.column_config.NumberColumn('Model rank',format='#%d')})
                    for ix,(_,r) in enumerate(show.head(30).iterrows()):
                        rank=pd.to_numeric(r.get('model_rank'),errors='coerce')
                        rank_text=f"Model #{int(rank)}" if pd.notna(rank) else "Model rank unavailable"
                        _team=r.get('team','')
                        _team='' if pd.isna(_team) else _team
                        st.markdown(ui.odds_card(r['player'],_team,r.get('player_id',''),price_label(r['best_odds']),r['best_sportsbook'],price_label(r['worst_odds']),r['worst_sportsbook'],
                            r['decimal_price_improvement_pct'],r['sportsbooks_compared'],rank_text,r.get('identity_status','Unverified'),season=SEASON),unsafe_allow_html=True)
                        with st.expander(f'Compare all sportsbook prices · {r["player"]}',expanded=False):
                            options=quotes_for_market(price_rows,r)
                            options=options[['sportsbook','american_odds','updated_at']].copy()
                            options.columns=['Sportsbook','American odds','Updated (UTC)']
                            options['American odds']=options['American odds'].map(price_label)
                            options['Updated (UTC)']=pd.to_datetime(options['Updated (UTC)'],utc=True,errors='coerce').dt.strftime('%b %d · %H:%M UTC')
                            st.dataframe(options,hide_index=True,use_container_width=True)
                    if len(show)>30:
                        st.caption(f'Showing 30 of {len(show)} opportunities. Download the complete comparison below.')
                    st.download_button('Export all comparisons',show.to_csv(index=False),file_name='nulls_playbook_v46_odds.csv',mime='text/csv')
                if model_ranked is None:
                    st.caption('Model rankings for the selected date are not loaded yet; price discrepancies remain available.')
        except ValueError as exc:
            st.warning(f'Unable to validate current quotes: {exc}')
    else:
        st.info('No sportsbook quotes available for the selected source.')


with np_research_tab:
    storyline_top = st.container()
    with storyline_top:
        st.markdown(ui.brand_title('Research · Four Distinct Leaders','Evidence-first, pre-slate storylines. Former-team and injury/news claims are not inferred.'),unsafe_allow_html=True)
        if st.session_state.get('v531_history_error'):
            st.warning(f"History unavailable: {st.session_state['v531_history_error']}")
        _v531_job=st.session_state.get('v43_history_job')
        if _v531_job and _v531_job.get('day')==np_day and not _v531_job['future'].done():
            st.caption('⏳ Three-season opponent history is updating separately. Rankings remain usable.')
    st.caption('Scheduled 30-minute snapshots when available · live fallback for unsaved dates · three prior seasons · not calibrated probabilities')
    day = np_day
    # V5.4: Goalies · Goals Allowed (descriptive; rankings unchanged).
    with st.container():
        st.markdown(ui.section('Goalies: Goals Allowed','Per team, by goalie · season to date · NHL club-stats','🥅','odds'),unsafe_allow_html=True)
        _gk_all=st.checkbox('Show all NHL teams (not just tonight’s slate)',value=False,key='v54_gk_all')
        _gk_teams=sorted(mc.TEAM_NAMES) if _gk_all else sorted({t for g in mc.slate_games(np_games) for t in (g['away'],g['home'])})
        if not _gk_teams:
            st.info('No teams on this slate. Pick a date with games, or show all NHL teams.')
        else:
            _gk_rows,_gk_err=goalies_cached(tuple(_gk_teams),SEASON)
            _gk_sort=st.radio('Sort teams by',list(gk.SORTS),horizontal=True,key='v54_gk_sort')
            _gk_sum=gk.sort_summary(gk.team_summary(_gk_rows,_gk_teams),_gk_sort)
            st.markdown('<div class="np-gk-legend"><span><i style="background:#fb923c"></i>Leaky (top third) · more goals allowed = more scoring chances for shooters facing them</span>'
                        '<span><i style="background:#38bdf8"></i>Stingy (bottom third)</span><span><i style="background:#64748b"></i>Middle / no data</span></div>',unsafe_allow_html=True)
            _gk_df=gk.goalie_frame(_gk_rows)
            _cards=[]
            for _i,_r in _gk_sum.iterrows():
                _g=_gk_df[_gk_df['Team']==_r['Team']].sort_values(['GA','GP'],ascending=[False,False]).to_dict('records') if not _gk_df.empty else []
                _cards.append(ui.goalie_card(_r['Team'],mc.TEAM_NAMES.get(_r['Team'],_r['Team']),_r,_g,_r['Tone'],_i+1))
            st.markdown('<div class="np-gk-grid">'+''.join(_cards)+'</div>',unsafe_allow_html=True)
            st.caption('Source: NHL official API club-stats/{team}/'+SEASON+'/2 (regular season, team-specific: a traded goalie is listed under each club). '
                       'GAA = GA × 60 / time on ice (— when no ice time). Season-to-date at fetch time, cached 30 min. Not used in any ranking.')
            if _gk_err:
                with st.expander(f'{len(_gk_err)} goalie requests failed'):
                    st.write(_gk_err)

    if st.button('↻ Refresh now', key='v42_manual_refresh'):
        schedule_cached.clear()
        team_cached.clear()
        defense_cached.clear()
        historical_cached.clear()
        st.session_state.pop('v42_last_rank', None)
        st.info('A saved snapshot is active when available. To force a fresh complete slate, run the GitHub Actions workflow.')
        st.session_state.pop('v42_history_attempt', None)
        st.session_state.pop('v43_history_completed', None)
        st.rerun()

    try:
        games = np_snapshot['games'] if np_snapshot is not None else schedule_cached(day)
        st.caption(f'Data updated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC')
        
        st.subheader('Full NHL Slate')
        if games:
            st.markdown('#### 🏒 Matchup Center')
            # Official NHL team logos; a broken image does not affect data retrieval.
            import html as _html
            for offset in range(0,min(len(games),12),3):
                cols=st.columns(min(3,len(games)-offset))
                for col,game in zip(cols,games[offset:offset+3]):
                    away=_html.escape(str(game.get('Away','')))
                    home=_html.escape(str(game.get('Home','')))
                    with col:
                        st.markdown(f'''<div class="np-player" style="min-height:100px;text-align:center"><div class="np-muted">{_html.escape(format_game_time(game.get('Start (UTC)')))}</div><div style="display:flex;justify-content:center;align-items:center;gap:13px;margin-top:9px"><img alt="{away}" src="https://assets.nhle.com/logos/nhl/svg/{away}_light.svg" style="height:38px;width:38px;object-fit:contain"/><b>{away} vs {home}</b><img alt="{home}" src="https://assets.nhle.com/logos/nhl/svg/{home}_light.svg" style="height:38px;width:38px;object-fit:contain"/></div></div>''',unsafe_allow_html=True)
            with st.expander('Full NHL slate data'):
                st.dataframe(pd.DataFrame(games), hide_index=True, use_container_width=True)
            st.metric('Slate Games', len(games))
        else:
            st.info('No games found for this date.')
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f'Schedule request failed: {exc}')
        games = []

    st.divider()
    st.subheader('Player Statistics Explorer')
    st.caption('Only regular-season game-log entries dated before the selected slate date are counted. '
               'This prevents date leakage but does not independently verify game completion or historical roster membership.')
    if games:
        teams = sorted({g[t] for g in games for t in ('Home','Away') if g.get(t)})
        team = st.selectbox('Team on slate', teams)
        if st.button('Load Player Statistics'):
            try:
                with st.spinner('Loading NHL player game logs...'):
                    rows, errors = team_cached(team, day)
                if rows:
                    st.dataframe(pd.DataFrame(rows).drop(columns=['id']), hide_index=True, use_container_width=True)
                    st.caption(f'Roster and player statistics · Season {SEASON}')
                    flagged = sum(r['Data status'] == 'Needs review' for r in rows)
                    missing = sum(r['GP'] == 0 for r in rows)
                    c1, c2, c3 = st.columns(3)
                    c1.metric('Players loaded', len(rows))
                    c2.metric('Flagged records', flagged)
                    c3.metric('No prior games', missing)
                    if flagged or errors:
                        st.warning('Incomplete or questionable records detected. Do not use for prediction backtests.')
                    st.caption('Historical roster caveat: the current roster endpoint may include players '
                               'who were not on this team on the selected date. Historical membership is not verified.')
                else:
                    st.warning('No player game logs returned.')
                if errors:
                    st.warning(f'{len(errors)} players could not be loaded; incomplete coverage.')
                    with st.expander('Request errors'):
                        st.write(errors)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                st.error(f'Player data request failed: {exc}')
    else:
        st.info('Choose a date with games to explore player statistics.')

    st.divider()
    st.subheader('V3.2 Goal-Scorer Rankings')
    st.caption('Goal-scoring Form % is a relative index (share of the 100-point benchmark, clipped at 100%), NOT a scoring probability. Opponent goals/shots allowed '
               'adjust the Form index (shown as Form %) by at most 15% where coverage is sufficient. '
               'No goalie adjustment is applied to these rankings; probable starters are shown for information in Matchup Center.')
    if games:
        min_games = st.slider('Minimum prior games per player', 1, 10, 3)
        use_defense = st.checkbox('Apply opponent defense adjustment', value=True)
        # Auto-run on first open, selected-date change, or after the 30-minute interval.
        # Never silently replace an older pregame snapshot with a current-time reconstruction.
        _v42_key=(day,int(min_games),bool(use_defense))
        _v42_last=st.session_state.get('v42_last_rank')
        _v42_due=(np_snapshot is None and (not _v42_last or _v42_last.get('key')!=_v42_key
                  or datetime.now(timezone.utc)-_v42_last['at']>=timedelta(minutes=30)
                  or st.session_state.get('signals_day')!=day))
        if games and _v42_due:
            st.info('⏳ Auto-analyzing all teams for the selected date…')
            teams_to_load = sorted({g[t] for g in games for t in ('Home', 'Away') if g.get(t)})
            all_rows, all_errors = [], []
            progress = st.progress(0, text='Loading all teams')
            # Fetch independent team rosters concurrently instead of serially.
            # Keep worker count modest to avoid overwhelming the NHL endpoints.
            with ThreadPoolExecutor(max_workers=6) as pool:
                jobs={pool.submit(team_cached, code, day):code for code in teams_to_load}
                for i, job in enumerate(as_completed(jobs), start=1):
                    team_code=jobs[job]
                    try:
                        team_rows, team_errors=job.result()
                        all_rows.extend(team_rows)
                        all_errors.extend([f'{team_code}: {e}' for e in team_errors])
                    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                        all_errors.append(f'{team_code}: {exc}')
                    progress.progress(i/len(teams_to_load),text=f'Loaded {i}/{len(teams_to_load)} teams')
            ranked = rank_players(all_rows, min_games)
            defensive, defense_errors = {}, []
            with ThreadPoolExecutor(max_workers=6) as pool:
                jobs={pool.submit(defense_cached, code, day):code for code in teams_to_load}
                for job in as_completed(jobs):
                    team_code=jobs[job]
                    try:
                        defensive[team_code]=job.result()
                    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                        defense_errors.append(f'{team_code}: {exc}')
            ranked = assign_statistical_ranks(attach_matchups(ranked, games, defensive, adjust=use_defense)).to_dict('records')
            coverage = pd.DataFrame([
                {k:v for k,v in d.items() if k != 'Error details'}
                for d in defensive.values()
            ])
            st.metric('Teams requested', len(teams_to_load))
            st.metric('Players eligible for form ranking', len(ranked))
            st.metric('Opponent defenses retrieved', len(defensive))
            st.caption('Defensive rates are goals/shots allowed per completed game, using up to 10 '
                       'games before the slate date. Goalies are NOT confirmed.')
            if not coverage.empty:
                with st.expander('Defensive data coverage and audit'):
                    st.dataframe(coverage, hide_index=True, use_container_width=True)
            if defense_errors:
                st.warning(f'{len(defense_errors)} defensive team requests failed.')
                with st.expander('Defensive request errors'):
                    st.write(defense_errors)
            partial = [d['Opponent'] for d in defensive.values()
                       if d['Games verified'] < d['Games found']]
            if partial:
                st.warning(f'Incomplete defensive boxscore coverage: {", ".join(partial)}')
            if not defensive:
                st.warning('No opponent defensive context available. Form rankings are unadjusted.')
            if ranked:
                st.session_state['signals_ranked'] = pd.DataFrame(ranked)
                st.session_state['signals_day'] = day
                st.session_state['v42_last_rank']={'key':_v42_key,'at':datetime.now(timezone.utc)}
                st.session_state['v42_needs_home_refresh']=True
                try:
                    snapshot = make_snapshot(ranked, games, day)
                    st.download_button('Save PRE-GAME snapshot CSV (keep this file)',
                                       snapshot.to_csv(index=False),
                                       file_name=f'null-pregame-{day}.csv', mime='text/csv')
                    st.caption('Snapshot is saved to YOUR device only. Download before the first puck drop. '
                               'A later download cannot recreate a genuine pregame prediction.')
                except (KeyError, ValueError, TypeError) as exc:
                    st.info(f'Pregame snapshot unavailable: {exc}')
                st.dataframe(ui.with_form_pct(pd.DataFrame(ranked)), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
                st.download_button('Download rankings CSV', ui.with_form_pct(pd.DataFrame(ranked)).to_csv(index=False),
                                   file_name=f'null-nhl-v3-2-{day}.csv', mime='text/csv')
                st.caption('Statistical sleepers (NOT verified betting longshots): players outside the top 20 '
                           'with at least 2 shots per game over the last 5 games.')
                watch = [r for r in ranked[20:] if r['Shots/G L5'] >= 2]
                if watch:
                    st.dataframe(ui.with_form_pct(pd.DataFrame(watch[:20])), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
                else:
                    st.info('No players met the longshot-watchlist rule.')
            else:
                st.warning('No eligible players found.')
            if all_errors:
                st.warning(f'{len(all_errors)} player/team requests failed; ranking coverage is incomplete.')
                with st.expander('Missing-data details'):
                    st.write(all_errors)
            st.warning('Current roster membership is not historical lineup verification. '
                       'Do not use this ranking as a historical pregame prediction or calibrated probability.')
    else:
        st.info('Select a date with games to calculate full-slate form rankings.')
    st.divider()
    st.subheader('V3.3 Historical Backtesting')
    st.caption('Upload a CSV saved before the first game started. The app does not persist snapshots. '
               'This evaluates eligible roster-based predictions, not historically verified lineups.')
    uploaded = st.file_uploader('Upload a pregame snapshot CSV', type=['csv'])
    if uploaded is not None:
        try:
            saved = pd.read_csv(uploaded)
            st.caption(f'Loaded {len(saved)} snapshot rows. Outcomes require completed NHL boxscores.')
            if st.button('Score snapshot against final NHL boxscores'):
                with st.spinner('Checking final boxscores...'):
                    scored, failures = score_snapshot(saved)
                if failures:
                    st.warning('Some games could not be verified. Incomplete results are excluded from metrics.')
                    with st.expander('Boxscore errors'):
                        st.write(failures)
                if not scored.empty:
                    st.dataframe(top_k_metrics(scored), hide_index=True, use_container_width=True)
                    st.dataframe(ui.with_form_pct(scored), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
                    st.download_button('Download scored snapshot CSV', ui.with_form_pct(scored).to_csv(index=False),
                                       file_name='null-scored-snapshot.csv', mime='text/csv')
                    st.caption('Top-K hit rate = players scoring at least one goal / K; not betting ROI, '
                               'calibration, or proof of predictive improvement.')
                else:
                    st.warning('No completed, verifiable games were available.')
        except (ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
            st.error(f'Snapshot could not be processed: {exc}')
    st.divider()
    st.subheader('V3.5 Auto Storyline, Numerology & Gematria')
    st.caption('Exploratory patterns only. NOT goal probabilities, predictive evidence, or betting edges. '
               'This section does not change the statistical rankings or backtests.')
    st.write(f'Universal day (YYYYMMDD digit reduction): **{universal_day(day)}**')
    st.caption('Name Pythagorean: A=1 through I=9, repeating. English ordinal: A=1 through Z=26. '
               'All totals reduce to 1–9 without master-number exceptions. ASCII letters only.')
    st.caption('Optional metadata CSV columns: Player ID, Jersey, Birth date (YYYY-MM-DD), Arena, '
               'Verified storyline, Source URL. Only sourced storyline text is displayed. '
               'Names, arena spellings, and birthdays require independent verification.')
    st.caption('NHL player profiles supply birthdays and current jersey numbers; arenas come from schedules. Historical team membership, news, injuries, former-team matches and milestones remain unverified.')
    auto_limit = st.select_slider('NHL profiles to fetch (top-ranked players)', options=[10, 25, 50, 100, 250, 500], value=500)
    if st.button('Fetch NHL player biographies and arenas'):
        if 'signals_ranked' not in st.session_state or st.session_state.get('signals_day') != day:
            st.warning('Run Rank Entire Slate first.')
        else:
            with st.spinner('Retrieving source-linked NHL profiles...'):
                data, errors = fetch_metadata(st.session_state['signals_ranked'].to_dict('records'), day, games, max_players=auto_limit)
            prior = st.session_state.get('auto_signal_metadata', pd.DataFrame()) if st.session_state.get('auto_signal_day') == day else pd.DataFrame()
            st.session_state['auto_signal_metadata'] = merge_profile_batches(prior, pd.DataFrame(data))
            st.session_state['auto_signal_day'] = day
            st.success(f'Fetched {len(data)} profiles; {len(errors)} unavailable.')
            if errors:
                with st.expander('Profile retrieval errors'):
                    st.write(errors)
    st.subheader('V3.8 Opponent History & Season Milestone Evidence')
    st.caption('Fetch pre-slate regular-season NHL game logs. Opponent flags require at least 2 prior meetings and 2 goals; season milestones mean one goal from 10, 20, 30, etc. Not career milestones.')
    history_limit = st.select_slider('Players for opponent history (top ranked)', options=[10, 25, 50, 100, 250, 500], value=50, key='history_limit')
    if st.button('Fetch opponent history and milestone evidence'):
        if 'signals_ranked' not in st.session_state or st.session_state.get('signals_day') != day:
            st.warning('Rank Entire Slate first.')
        else:
            with st.spinner('Fetching pre-slate NHL game logs...'):
                history_data, history_errors = fetch_history(st.session_state['signals_ranked'].to_dict('records'), games, day, max_players=history_limit)
            prior_history = st.session_state.get('history_v38', pd.DataFrame()) if st.session_state.get('history_v38_day') == day else pd.DataFrame()
            st.session_state['history_v38'] = merge_profile_batches(prior_history, history_data)
            st.session_state['history_v38_day'] = day
            st.success(f'History retrieved for {len(history_data)} players; {len(history_errors)} unavailable.')
            if history_errors:
                with st.expander('History fetch errors'):
                    st.write(history_errors)
    meta_file = st.file_uploader('Optional additional sourced storyline metadata CSV', type=['csv'], key='signal_meta')
    # V5.4: one shared pipeline (player_intelligence_v54) feeds Research and the Home featured row.
    _intel, _intel_warnings = intel_from_state(st.session_state, day)
    for _w in _intel_warnings:
        st.warning(_w)
    if _intel is not None:
        signals = _intel['signals']
        st.caption(f'{len(signals)} players evaluated. Pattern overlap counts are descriptive, '
                   'not confidence scores. Missing biographical data remains unavailable.')
        st.dataframe(ui.with_form_pct(signals), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
        storylines = _intel['storylines']
        combined = _intel['combined']
        top_stories, storyline_sleepers, featured = _intel['top_stories'], _intel['storyline_sleepers'], _intel['featured']
        v387 = _intel['v387']
        with storyline_top:
            coverage_stats = historical_coverage(combined)
            st.markdown('#### 📋 Historical Data Coverage')
            st.progress(coverage_stats['fraction'])
            cov1, cov2, cov3 = st.columns(3)
            cov1.metric('Complete histories', f"{coverage_stats['complete']}/{coverage_stats['total']}")
            cov2.metric('Partial / unavailable', coverage_stats['partial'])
            cov3.metric('Not fetched', coverage_stats['not_fetched'])
            st.caption(f"{coverage_stats['percent']:.1f}% of ranked players have complete requested-season history. Only complete records count toward historical storyline evidence; incomplete coverage may change the leaders.")
            st.caption('Statistical form, sourced storyline strength, top-20 overlap and descriptive sleeper are separate rankings. None is a calibrated scoring probability.')
            st.markdown('### Player Intelligence')
            st.caption('Four independent leaders · statistical form and historical storylines are not scoring probabilities')
            labels = INTEL_LABELS
            for key,label in labels:
                lead=v387['leaders'][key]
                if lead is None:
                    st.info(f'{label}: insufficient data for this date')
                    continue
                import html
                pid=lead.get('Player ID')
                pid=str(int(pid)) if pd.notna(pid) and str(pid).replace('.0','').isdigit() else ''
                team=html.escape(str(lead.get('Team','')))
                name=html.escape(str(lead.get('Player','')))
                rank=int(lead['Statistical rank'])
                form=float(lead['V3.2 Adjusted Index'])
                shots=float(lead['Shots/G L5'])
                flags=int(lead['Storyline count'])
                evidence=float(lead['Storyline evidence score'])
                history_ok=lead.get('Historical coverage')=='Complete, >=3 meetings'
                gp=int(lead['Historical opponent GP']) if history_ok else 0
                goals=int(lead['Historical opponent goals']) if history_ok else 0
                photo=f'<img class="np-research-photo" src="https://assets.nhle.com/mugs/nhl/{SEASON}/{team}/{pid}.png" alt="Player portrait" loading="lazy"/>' if pid else '<div class="np-research-placeholder">🏒</div>'
                history_text=f'{goals} goals in {gp} previous meetings' if history_ok else 'Opponent history unavailable or insufficient'
                st.markdown(f"""<div class="np-research-card"><div class="np-research-eyebrow">{label}</div><div class="np-research-row">{photo}<div class="np-research-person"><div class="np-research-name">{name}</div><div class="np-research-team">{team} · Statistical rank #{rank}</div><div class="np-research-form">{ui.format_form_pct(form)} <small>GOAL-SCORING FORM %</small></div></div></div><div class="np-research-stats"><div><b>{shots:.1f}</b><small>Shots/game · L5</small></div><div><b>{goals if history_ok else '—'}</b><small>Opponent goals</small></div><div><b>{flags}</b><small>Storyline flags</small></div></div><div class="np-research-note">{history_text} · {evidence:.1f} storyline points</div></div>""",unsafe_allow_html=True)
                with st.expander(f'Detailed analysis · {lead.get("Player", "Player")}',expanded=False):
                    st.caption(f'Statistical rank #{rank} · Goal-scoring Form {ui.format_form_pct(form)} ({form:.1f} pts) · Storyline evidence {evidence:.2f}')
                    st.write('**Evidence:**',lead.get('Verified data flags','Not available'))
                    st.caption('Historical opponent data: '+str(lead.get('Historical coverage','Unavailable')))
                    st.caption('Form % is a relative statistical index (share of the 100-point benchmark), not a goal probability. Storyline evidence is a separate heuristic.')
            st.caption('Storyline evidence points are an explicitly heuristic display index: 2 per historical goal (max 10), 6 × historical goals/game (max 1.5), historical shots/10 (max 50 shots), plus 1.5 per sourced flag (max 5). Historical components require complete requested seasons and ≥3 meetings. They are NOT validated predictive weights.')
            for key,title in [('statistical','Top 10 Statistical'),('storyline','Top 10 Storylines'),('overlap','Top 10 Overlap'),('longshots','Top 10 Statistical Sleepers')]:
                st.subheader(title)
                frame=v387[key]
                if frame.empty: st.info('No eligible players in currently loaded data.')
                else:
                    cols=['Player','Team','Statistical rank','Storyline rank','Storyline evidence score','Storyline count','Historical opponent GP','Historical opponent goals','Historical opponent shots','Shots/G L5','Verified data flags']
                    st.dataframe(ui.with_form_pct(frame[[c for c in cols if c in frame]]),hide_index=True,use_container_width=True,column_config=ui.form_pct_config(st))
                    st.download_button('Download '+title+' CSV',ui.with_form_pct(frame).to_csv(index=False),file_name=f'null-v387-{key}-{day}.csv',mime='text/csv',key=f'v387_{key}')
        st.download_button('Download top 10 storyline watchlist CSV', ui.with_form_pct(top_stories).to_csv(index=False), file_name=f'null-v381-top10-{day}.csv', mime='text/csv')
        st.subheader('V3.8.2 Data Integrity Audit')
        audit = coverage_audit(combined, st.session_state.get('auto_signal_metadata') if st.session_state.get('auto_signal_day') == day else None,
                               st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None)
        st.dataframe(pd.DataFrame([audit]), hide_index=True, use_container_width=True)
        if audit['Histories fetched'] < audit['Eligible players']:
            st.info('Opponent-history coverage is partial; zero flags on unfetched players do not mean no storyline.')
        st.download_button('Download ALL evaluated players + storyline evidence CSV', ui.with_form_pct(combined).to_csv(index=False),
                           file_name=f'null-v381-full-storylines-{day}.csv', mime='text/csv')
        st.download_button('Download data coverage audit CSV', pd.DataFrame([audit]).to_csv(index=False),
                           file_name=f'null-v381-audit-{day}.csv', mime='text/csv')
        st.subheader('V3.8.2 Opponent, Milestone & Birthday Diagnostics')
        st.caption('These checks distinguish no detected opponent meetings from missing game logs. Near-milestones (2–3 goals away) are informational watch items, not verified storyline flags.')
        history_for_audit = st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None
        profiles_for_audit = st.session_state.get('auto_signal_metadata') if st.session_state.get('auto_signal_day') == day else None
        diagnostic = diagnostic_summary(combined, profiles_for_audit, history_for_audit, day)
        st.dataframe(pd.DataFrame([diagnostic]), hide_index=True, use_container_width=True)
        if diagnostic['Histories fetched'] and diagnostic['Total prior opponent meetings'] == 0:
            st.warning('Zero prior opponent meetings found. This can be normal early in the season, but check NHL game-log opponent codes before drawing conclusions.')
        if history_for_audit is not None and not history_for_audit.empty:
            diagnostic_cols = ['Player','Team','Player ID','Opponent','Vs opponent GP','Vs opponent goals','Log rows received','Log rows valid pre-slate','Log rows excluded','Opponent match method','Opponent normalized','Raw opponent samples','Distinct raw opponent values','Rows missing opponent code','Opponent match diagnostic','Season goals (log)','Milestone distance','Milestone watch (not a flag)','V3.8 status']
            st.dataframe(history_for_audit[[c for c in diagnostic_cols if c in history_for_audit]], hide_index=True, use_container_width=True)
            st.download_button('Download opponent-history diagnostics CSV', history_for_audit.to_csv(index=False), file_name=f'null-v382-opponent-diagnostics-{day}.csv', mime='text/csv')
        st.subheader('V3.8.4 Official Schedule & Player Assignment Audit')
        st.caption('Cross-checks the displayed slate against the official NHL schedule, then checks prior completed team meetings. A player may have zero personal games even when the teams met earlier.')
        if st.button('Validate official schedule and opponent assignments'):
            with st.spinner('Checking official slate and prior team schedules...'):
                try:
                    schedule_games, schedule_players, schedule_errors = audit_schedule(
                        st.session_state['signals_ranked'].to_dict('records'), games, day)
                    st.session_state['schedule_v384'] = (schedule_games, schedule_players, schedule_errors)
                    st.session_state['schedule_v384_day'] = day
                except Exception as exc:
                    st.error(f'Schedule validation unavailable: {type(exc).__name__}: {exc}')
        if st.session_state.get('schedule_v384_day') == day and 'schedule_v384' in st.session_state:
            sg, sp, se = st.session_state['schedule_v384']
            st.dataframe(sg, hide_index=True, use_container_width=True)
            st.dataframe(sp, hide_index=True, use_container_width=True)
            if se:
                st.warning(f'{len(se)} team schedule(s) could not be retrieved; their historical counts are unavailable, not zero.')
                with st.expander('Team schedule errors'):
                    st.write(se)
            st.download_button('Download V3.8.4 schedule and player audit CSV', sp.to_csv(index=False),
                               file_name=f'null-v384-schedule-audit-{day}.csv', mime='text/csv')
        st.subheader('V3.8.5 Roster & Historical Schedule Verification')
        st.caption('Checks NHL season-roster membership by player ID and counts completed pre-slate team games. Season-roster membership does not establish the player was on that team on the selected historical date.')
        if st.button('Verify player rosters and historical schedule coverage'):
            with st.spinner('Fetching independent team rosters and schedules...'):
                try:
                    rp, rt, re = audit_roster_and_history(st.session_state['signals_ranked'].to_dict('records'),games,day)
                    st.session_state['v385_audit']=(rp,rt,re)
                    st.session_state['v385_day']=day
                except Exception as exc:
                    st.error(f'V3.8.5 audit unavailable: {type(exc).__name__}: {exc}')
        if st.session_state.get('v385_day')==day and 'v385_audit' in st.session_state:
            rp,rt,re=st.session_state['v385_audit']
            st.metric('Players checked',len(rp))
            if not rp.empty:
                st.metric('Players not found on assigned roster',int((rp['Roster membership']=='NOT FOUND on assigned team roster').sum()))
                st.dataframe(rp,hide_index=True,use_container_width=True)
                st.download_button('Download V3.8.5 player roster audit CSV',rp.to_csv(index=False),file_name=f'null-v385-roster-{day}.csv',mime='text/csv')
            if not rt.empty:
                st.dataframe(rt,hide_index=True,use_container_width=True)
                st.download_button('Download V3.8.5 team schedule coverage CSV',rt.to_csv(index=False),file_name=f'null-v385-team-coverage-{day}.csv',mime='text/csv')
            if re:
                st.warning(f'{len(re)} retrieval/validation errors; unavailable data is not counted as zero.')
                with st.expander('V3.8.5 retrieval errors'): st.write(re)
        # V4.2: three prior seasons for the ENTIRE ranked slate, automatically.
        _v42_ranked=st.session_state.get('signals_ranked')
        if isinstance(_v42_ranked,pd.DataFrame) and not _v42_ranked.empty and st.session_state.get('signals_day')==day:
            _v42_ids=tuple(_v42_ranked['Player ID'].astype(str).tolist())
            _v42_games_sig=tuple(sorted(str(g.get('Game ID','')) for g in games))
            _v42_hist_key=(day,3,_v42_ids,_v42_games_sig)
            if st.session_state.get('history_v386_day') != day and st.session_state.get('v42_history_attempt')!=_v42_hist_key:
                st.session_state['v42_history_attempt']=_v42_hist_key
                # Return control to the page immediately. The completed future is
                # collected by the 10-second status fragment at the top of Home.
                job=history_executor().submit(historical_cached, day, 3, _v42_ids,
                    _v42_games_sig, _v42_ranked.to_dict('records'), games)
                st.session_state['v43_history_job']={'day':day,'key':_v42_hist_key,'future':job}
            if st.session_state.get('history_v386_day')!=day:
                st.caption('Three-season opponent history is updating separately; statistical rankings are available.')
        st.subheader('V3.8.6 Multi-Season Opponent Storylines')
        st.caption('Previous NHL regular seasons only, with per-season source links and missing-data warnings. Descriptive history is NOT a calibrated goalscorer probability.')
        v386_count = st.select_slider('Players for manual history recheck',options=[10,25,50,100,250,500],value=500,key='v386_count')
        v386_years = st.selectbox('Previous seasons to inspect manually',options=[1,2,3],index=2,key='v386_years')
        if st.button('Fetch multi-season opponent history'):
            with st.spinner('Retrieving prior-season player game logs...'):
                try:
                    h386, e386 = fetch_multi_history(st.session_state['signals_ranked'].to_dict('records'),games,day,max_players=v386_count,years=v386_years)
                    if st.session_state.get('history_v386_day')==day and st.session_state.get('history_v386_years')==v386_years:
                        h386=merge_profile_batches(st.session_state.get('history_v386'),h386)
                    st.session_state['history_v386']=h386
                    st.session_state['history_v386_day']=day
                    st.session_state['history_v386_years']=v386_years
                    st.session_state['history_v386_errors']=e386
                    st.rerun()  # Re-render the four leader cards above with newly fetched evidence.
                    st.success(f'{len(h386)} player histories loaded; {len(e386)} season retrieval errors.')
                except Exception as exc:
                    st.error(f'Multi-season history unavailable: {type(exc).__name__}: {exc}')
        if st.session_state.get('history_v386_day')==day and st.session_state.get('history_v386_years')==v386_years:
            h386=st.session_state['history_v386']
            if not h386.empty:
                st.metric('Players with complete prior-season data',int((h386['Historical data status']=='Complete').sum()))
                st.metric('Historical storyline flags',int(h386['Historical storyline flag'].fillna('').ne('').sum()))
                st.dataframe(h386,hide_index=True,use_container_width=True)
                st.download_button('Download V3.8.6 historical opponent evidence CSV',h386.to_csv(index=False),file_name=f'null-v386-historical-{day}.csv',mime='text/csv')
            if st.session_state.get('history_v386_errors'):
                st.warning('Some season logs were unavailable; partial history is not treated as zero.')
                with st.expander('Multi-season retrieval errors'): st.write(st.session_state['history_v386_errors'])
        if st.session_state.get('v385_day')==day and 'v385_audit' in st.session_state:
            missing=missing_player_ids(st.session_state['signals_ranked'],st.session_state['v385_audit'][0])
            if missing:
                st.warning(f'{len(missing)} ranked player(s) missing from V3.8.5 roster audit:')
                st.dataframe(pd.DataFrame(missing),hide_index=True,use_container_width=True)
            else:
                st.caption('All currently ranked player IDs are present in the V3.8.5 roster audit.')
        st.download_button('Download V3.8.2 audit CSV', pd.DataFrame([diagnostic]).to_csv(index=False), file_name=f'null-v382-audit-{day}.csv', mime='text/csv')
        st.subheader('V3.8.2 Combined Statistical + Experimental Explorer')
        st.caption('Statistical form and experimental overlaps are separate columns. Neither is a calibrated goal probability. Former-team, milestone and news claims are marked unverified.')
        only_stories = st.checkbox('Show only sourced storyline flags', value=False)
        minimum_overlap = st.slider('Minimum experimental pattern overlaps', 0, 5, 0)
        longshot_only = st.checkbox('Statistical sleeper watch (outside top 20, L5 shots/game >= 2)', value=False)
        # Statistical rank was assigned before any storyline merge; never overwrite it here.
        filtered = combined[combined['Pattern overlaps'] >= minimum_overlap]
        if only_stories: filtered = filtered[filtered['Storyline count'] > 0]
        if longshot_only: filtered = filtered[(filtered['Statistical rank'] > 20) & (filtered['Shots/G L5'] >= 2)]
        st.dataframe(ui.with_form_pct(filtered), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
        st.download_button('Download combined V3.6 CSV', ui.with_form_pct(filtered).to_csv(index=False), file_name=f'null-v36-combined-{day}.csv', mime='text/csv')
        st.download_button('Download experimental signals CSV', ui.with_form_pct(signals).to_csv(index=False),
                           file_name=f'null-experimental-signals-{day}.csv', mime='text/csv')
    else:
        st.info('Run Rank Entire Slate for this date to populate the experimental signals table.')


# V4.8 recreational number analysis; not used by statistical rankings.
_TEAM_NAMES = {'ANA':'Anaheim Ducks','BOS':'Boston Bruins','BUF':'Buffalo Sabres','CAR':'Carolina Hurricanes','CBJ':'Columbus Blue Jackets','CGY':'Calgary Flames','CHI':'Chicago Blackhawks','COL':'Colorado Avalanche','DAL':'Dallas Stars','DET':'Detroit Red Wings','EDM':'Edmonton Oilers','FLA':'Florida Panthers','LAK':'Los Angeles Kings','MIN':'Minnesota Wild','MTL':'Montreal Canadiens','NJD':'New Jersey Devils','NSH':'Nashville Predators','NYI':'New York Islanders','NYR':'New York Rangers','OTT':'Ottawa Senators','PHI':'Philadelphia Flyers','PIT':'Pittsburgh Penguins','SEA':'Seattle Kraken','SJS':'San Jose Sharks','STL':'St Louis Blues','TBL':'Tampa Bay Lightning','TOR':'Toronto Maple Leafs','UTA':'Utah Mammoth','VAN':'Vancouver Canucks','VGK':'Vegas Golden Knights','WPG':'Winnipeg Jets','WSH':'Washington Capitals'}
with np_numbers_tab:
    import html as _num_html
    _day_num=num_universal_day(np_day)
    st.markdown(ui.hero('NULL’S PLAYBOOK · NUMBERS','Numerology & Gematria','Daily numbers · team names · game arenas · player name roots',
        chips=[(f'Universal day {_day_num}','gem'),('D = day','day'),('T = team','team'),('A = arena','arena'),('Entertainment only','warn')],tone='gem'),unsafe_allow_html=True)
    st.markdown(ui.day_banner(np_day,_day_num,'Full date digit sum, reduced to one digit'),unsafe_allow_html=True)
    st.caption('Symbolic patterns for entertainment only. These values do not predict scoring or betting outcomes.')
    with st.expander('ⓘ How numbers are calculated'):
        st.write('Universal day: sum every digit of YYYY-MM-DD and reduce to one digit. English ordinal: A=1 through Z=26. Full reduction: reduce each letter to a single digit, sum, and reduce again. Reverse ordinal: A=26 through Z=1. Punctuation and spaces are ignored. Arena names come from the game schedule.')
    try:
        _games_num=np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day)
    except (requests.RequestException,ValueError,KeyError):
        _games_num=[]
        st.warning('Unable to retrieve the schedule for this date.')
    _analyses=[num_analyze_game(g,np_day,_TEAM_NAMES) for g in _games_num]
    if not _analyses:
        st.info('No scheduled NHL games found for the selected date.')
    else:
        st.markdown(ui.stat_strip([('Games',len(_analyses),'odds'),('Teams',len({t for r in _analyses for t in (r['away'],r['home'])}),'team'),
            ('Arenas',f'{sum(bool(r["arena"]) for r in _analyses)}/{len(_analyses)}','arena'),('Day alignments',sum(len(r['matches']) for r in _analyses),'gem')]),unsafe_allow_html=True)
        _num_view=st.radio('Explore',['Games','Player Targets','Team Numbers','Arena Numbers','Player Matches','Insights'],horizontal=True,key='v48_view')
        if _num_view=='Games':
            for r in _analyses:
                a,h=r['away_values'],r['home_values']
                away,home=_num_html.escape(r['away']),_num_html.escape(r['home'])
                venue=_num_html.escape(r['arena'] or 'Arena unavailable')
                venue_number=r['arena_values']['ordinal_root'] if r['arena_values'] else '—'
                matches=''.join(ui.badge(m,'gem') for m in r['matches'][:3]) or ui.badge('No direct day-number matches','muted')
                start=format_game_time(r['start'])
                st.markdown(f'<div class="np-num-match"><div class="np-num-top"><span>{start}</span><span>{venue}</span></div><div class="np-num-versus"><div>{ui.logo(away,52)}<b>{away}</b><small>ENG {a["ordinal_root"]} · RED {a["reduction_root"]} · REV {a["reverse_root"]}</small></div><div class="np-num-center"><strong>{_day_num}</strong><small>DAY</small><span>VS</span><strong class="np-num-green">{venue_number}</strong><small>ARENA</small></div><div>{ui.logo(home,52)}<b>{home}</b><small>ENG {h["ordinal_root"]} · RED {h["reduction_root"]} · REV {h["reverse_root"]}</small></div></div><div class="np-num-foot">{matches}</div></div>',unsafe_allow_html=True)
                with st.expander(f'View details · {away} @ {home}'):
                    for label,name,v in [('Away team',r['away_name'],a),('Home team',r['home_name'],h),('Arena',r['arena'],r['arena_values'])]:
                        if v is None:
                            st.caption('Arena name unavailable from game schedule.')
                        else:
                            st.markdown(f'**{label}: {name}**')
                            st.caption(f'English ordinal {v["ordinal"]} → {v["ordinal_root"]} · Full reduction {v["reduction"]} → {v["reduction_root"]} · Reverse {v["reverse"]} → {v["reverse_root"]}')
        elif _num_view=='Player Targets':
            _ranked_targets=st.session_state.get('signals_ranked')
            if not (isinstance(_ranked_targets,pd.DataFrame) and st.session_state.get('signals_day')==np_day):
                _ranked_targets=None
            st.markdown(ui.section('Team player targets','Every matchup · both teams · numerical patterns','🎯','gem'),unsafe_allow_html=True)
            if _ranked_targets is None:
                st.info('Load the slate snapshot to see player targets for each team.')
            else:
                _mode=st.segmented_control('Player view',['Numbers','Statistics','Overlap'],default='Numbers',key='v50_mode')
                _c1,_c2=st.columns(2)
                with _c1: _limit=st.selectbox('Players per team',[3,5,10],key='v50_limit')
                with _c2: _only_matches=st.toggle('Matches only',value=False,key='v50_matches_only')
                _targets=num_slate_targets(_analyses,_ranked_targets,np_day)
                def _v50_sort(targets):
                    candidates=[t for t in targets if t['matches']>0] if _only_matches else list(targets)
                    if _mode=='Statistics':
                        candidates.sort(key=lambda t:(-t['form'],-t['matches'],t['player']))
                    elif _mode=='Overlap':
                        candidates.sort(key=lambda t:(-int(t['matches']>0 and t['form']>0),-t['matches'],-t['form'],t['player']))
                    return candidates
                def _v50_team(code,name,targets):
                    ordered=_v50_sort(targets)
                    st.markdown(ui.team_head(code,name,f'{len(ordered)} roster players shown in ranking'),unsafe_allow_html=True)
                    for ix,t in enumerate(ordered[:_limit],1):
                        st.markdown(ui.target_row(ix,t['player'],code,t['player_id'],t['matches'],t['form'],len(t['day']),len(t['team_matches']),len(t['arena_matches']),season=SEASON),unsafe_allow_html=True)
                        with st.expander(f'Why {t["player"]}? · {code}',expanded=False):
                            st.caption(f'Player full-name roots: English {t["values"]["ordinal_root"]}, reduction {t["values"]["reduction_root"]}, reverse {t["values"]["reverse_root"]}.')
                            st.write(f'Day {_day_num}: {", ".join(t["day"]) or "no match"}')
                            st.write(f'Team: {", ".join(t["team_matches"]) or "no match"}')
                            st.write(f'Arena: {", ".join(t["arena_matches"]) or "no match"}')
                            st.caption('Coincidence counts are not probabilities; Form % is a separate statistical signal.')
                    if len(ordered)>_limit:
                        with st.expander(f'See {len(ordered)-_limit} more · {code}'):
                            for t in ordered[_limit:]:
                                st.write(f'{t["player"]} · {t["matches"]} matches · Form {ui.format_form_pct(t["form"])}')
                for item in _targets:
                    r=item['game']; away,home=r['away'],r['home']
                    venue=_num_html.escape(r['arena'] or 'Venue unavailable')
                    st.markdown(ui.matchup_bar(away,home,format_game_time(r['start']),r['arena']),unsafe_allow_html=True)
                    _away_col,_home_col=st.columns(2,gap='small')
                    with _away_col: _v50_team(away,r['away_name'],item['away_targets'])
                    with _home_col: _v50_team(home,r['home_name'],item['home_targets'])
                    st.divider()
                with st.expander('What do D, T and A mean?'):
                    st.write('D = Universal Day; T = team-name gematria; A = arena-name gematria. The number beside each letter counts matching methods (English ordinal, reduction, reverse).')
                    st.write('Numbers ranks symbolic coincidences. Statistics ranks the existing Form index (shown as Form %). Overlap brings players with both numerical matches and a positive statistical score to the top; it is not a calibrated goal probability.')
                st.caption('Recreational numerical patterns only. Not verified predictors of goals or betting outcomes.')
        elif _num_view=='Team Numbers':
            teams={r['away']:(r['away_name'],r['away_values']) for r in _analyses}
            teams.update({r['home']:(r['home_name'],r['home_values']) for r in _analyses})
            for code,(name,v) in sorted(teams.items()):
                st.markdown(ui.num_value_row(name,v,'team'),unsafe_allow_html=True)
        elif _num_view=='Arena Numbers':
            for r in _analyses:
                v=r['arena_values']
                if v:
                    st.markdown(ui.num_value_row(r['arena'],v,'arena'),unsafe_allow_html=True)
                else:
                    st.caption(f'{r["away"]} @ {r["home"]}: Arena unavailable')
        elif _num_view=='Player Matches':
            ranked=st.session_state.get('signals_ranked')
            if isinstance(ranked,pd.DataFrame) and not ranked.empty and st.session_state.get('signals_day')==np_day and 'Player' in ranked:
                matched=[]
                for _,player in ranked.iterrows():
                    v=num_gematria(player.get('Player',''))
                    methods=[k.replace('_root','').replace('_',' ') for k in ('ordinal_root','reduction_root','reverse_root') if v[k]==_day_num]
                    if methods:
                        matched.append({'Player':player['Player'],'Team':player.get('Team',''),'Matching methods':', '.join(methods)})
                st.dataframe(pd.DataFrame(matched,columns=['Player','Team','Matching methods']),hide_index=True,use_container_width=True)
                st.caption('Number matches only, not goal-scoring recommendations.')
            else:
                st.info('Player names will appear after rankings for this date are loaded.')
        else:
            st.metric('Day-number alignments',sum(len(r['matches']) for r in _analyses))
            st.write('Alignments count exact digit-root matches across team and arena names. A higher count does not imply a better scoring chance.')




# ============================================================ V5.4 Matchup Center
def _mc_set_query(key):
    if hasattr(st, 'query_params'):
        try:
            if key: st.query_params['matchup'] = key
            elif 'matchup' in st.query_params: del st.query_params['matchup']
        except Exception:
            pass

def _mc_open(key):
    st.session_state['v54_mc_game'] = key
    st.session_state['v54_mc_select'] = key
    _mc_set_query(key)

def _mc_back():
    st.session_state['v54_mc_game'] = None
    st.session_state['v54_mc_select'] = '—'
    _mc_set_query(None)

def _mc_pick():
    _sel = st.session_state.get('v54_mc_select')
    st.session_state['v54_mc_game'] = None if _sel in (None, '—') else _sel
    _mc_set_query(st.session_state['v54_mc_game'])

with np_mc_tab:
    st.markdown(ui.hero('NULL’S PLAYBOOK · MATCHUP CENTER','Matchup Center','Start from a pick · open its game · see both rosters’ targets and the goalies they face',
        chips=[(f'📅 {np_day}','muted'),(f'{len(mc.slate_games(np_games))} games','odds')]),unsafe_allow_html=True)
    _mc_games = mc.slate_games(np_games)
    _mc_keys = [g['key'] for g in _mc_games]
    if 'v54_mc_game' not in st.session_state and hasattr(st, 'query_params'):
        try:
            _qp = st.query_params.get('matchup')
            st.session_state['v54_mc_game'] = _qp if _qp in _mc_keys else None
        except Exception:
            st.session_state['v54_mc_game'] = None
    _mc_intel, _ = intel_from_state(st.session_state, np_day)
    _mc_picks = intel_four_picks(_mc_intel)
    st.markdown(ui.section('Player intelligence picks','Same four picks as Home and Research · open a card’s game below','🧠','overlap'),unsafe_allow_html=True)
    _mc_cols = st.columns(4)
    for _col,(_k,_l) in zip(_mc_cols, INTEL_LABELS):
        _g = mc.game_for_pick(_mc_picks.get(_k), np_games)
        with _col:  # card and its button share a column, so they stay together when columns stack on mobile
            st.markdown(ui.intel_row([ui.intel_card(_k,_l,_mc_picks.get(_k),season=SEASON)], solo=True),unsafe_allow_html=True)
            if _g:
                st.button(f'Open {_g["focus_team"]} vs {_g["opponent"]}', key=f'v54_mc_open_{_k}', on_click=_mc_open, args=(_g['key'],), use_container_width=True)
            elif _mc_picks.get(_k):
                st.caption('This player’s game is not on the loaded slate.')
            else:
                st.caption('No pick yet for this category.')
    _labels = {'—': 'Choose any slate game…'}
    _labels.update({g['key']: f'{g["away"]} @ {g["home"]} · {format_game_time(g["start"])}' for g in _mc_games})
    if st.session_state.get('v54_mc_select') not in ['—'] + _mc_keys:
        st.session_state['v54_mc_select'] = st.session_state.get('v54_mc_game') if st.session_state.get('v54_mc_game') in _mc_keys else '—'
    st.selectbox('Open any game on the slate', ['—'] + _mc_keys, format_func=lambda k: _labels.get(k, k), key='v54_mc_select', on_change=_mc_pick)
    _sel_key = st.session_state.get('v54_mc_game')
    _game = mc.find_game(np_games, _sel_key) if _sel_key else None
    if _sel_key and _game is None:
        st.warning('That matchup is not on the selected slate. Choose another game.')
        st.button('← Back to overview', key='v54_mc_back_missing', on_click=_mc_back)
    elif _game is None:
        if not _mc_games:
            st.info('No NHL games are scheduled for this date. Pick another date on Home.')
        else:
            st.markdown(ui.section('Tonight’s games','Pick a card above or any game in the selector','🏒','odds'),unsafe_allow_html=True)
            st.markdown('<div class="np-hscroll">'+''.join(ui.matchup_chip(g['away'],g['home'],format_game_time(g['start'])) for g in _mc_games)+'</div>',unsafe_allow_html=True)
    else:
        st.button('← Back to overview', key='v54_mc_back', on_click=_mc_back)
        st.markdown(ui.matchup_bar(_game['away'],_game['home'],format_game_time(_game['start']),_game['venue']),unsafe_allow_html=True)
        st.markdown(ui.section('Player targets by matchup','Both rosters · ranked by Form % · badges show which signals agree','🎯','team'),unsafe_allow_html=True)
        _gk_rows,_gk_err = goalies_cached((_game['away'],_game['home']),SEASON)
        _st_map,_st_err,_st_at = starters_cached(np_day, ((_game['key'],_game['game_id'],_game['away'],_game['home'],_game['status']),))
        _starters = _st_map.get(_game['key'], {})
        try:
            _mc_ranked = assign_statistical_ranks(np_ranked.copy()) if np_ready else None
        except (ValueError, KeyError, TypeError):
            _mc_ranked = None
        _pick_ids = [p.get('Player ID') for p in _mc_picks.values() if p]
        _targets = mc.matchup_targets(_home_targets, _game, _mc_ranked, _np_shared_discrepancies, _trk_badges, _pick_ids)
        _weak = mc.weaker_goalie_side(_gk_rows, _game)
        _order = [_weak] + [t for t in (_game['away'], _game['home']) if t != _weak] if _weak else [_game['away'], _game['home']]
        _cols = st.columns(2)
        for _col, _team in zip(_cols, _order):
            _opp = _game['home'] if _team == _game['away'] else _game['away']
            with _col:
                st.markdown(ui.team_head(_team, mc.TEAM_NAMES.get(_team, _team), f'Shooters facing {_opp} goaltending'),unsafe_allow_html=True)
                if _team == _weak:
                    st.markdown('<span class="np-mc-side">▲ FACES THE LEAKIER GOALIE (BY GAA)</span>',unsafe_allow_html=True)
                _s = _starters.get(_opp)
                if _s and _s.get('status') in ('confirmed','probable'):
                    st.markdown(ui.goalie_spotlight(_opp, pgk.match_stats(_s, _gk_rows), 'starter', _s, _s.get('fetched_at')),unsafe_allow_html=True)
                st.markdown(ui.goalie_spotlight(_opp, mc.leakiest_goalie(_gk_rows, _opp), 'leaky', starter_known=bool(_s and _s.get('status') in ('confirmed','probable'))),unsafe_allow_html=True)
                _list = _targets.get(_team, [])
                if _list:
                    st.markdown(''.join(ui.target_card(i, p, _team, SEASON) for i, p in enumerate(_list, 1)),unsafe_allow_html=True)
                else:
                    st.info('Player targets appear once this slate’s rankings load.' if not np_ready else 'No ranked players for this team.')
        st.caption('Starter status comes only from the feeds (NHL boxscore starter flag once a game begins; ESPN probables pregame), cached 5 min. '
                   'The leakiest-goalie card is team season stats and is never labelled the starter. Badges: Stats = top-20 Form; Numbers = ≥2 symbolic matches; '
                   'Overlap = both; Odds = validated price gap. None is a scoring probability.')
        if _gk_err or _st_err:
            with st.expander('Data warnings'):
                st.write(list(_gk_err) + list(_st_err))
    st.markdown(ui.footer("NULL’S PLAYBOOK · MATCHUP CENTER"),unsafe_allow_html=True)


# ============================================================ V5.4 Track Record
with np_track_tab:
    st.markdown(ui.hero('NULL’S PLAYBOOK · TRACK RECORD','Track Record','Every pick saved per slate · graded against final results · learns slowly and transparently',
        chips=[(f'📅 {np_day}','muted'),('Local SQLite store','stat')]),unsafe_allow_html=True)
    _tconn,_tevals,_trecs,_terr = np_track_state()
    if _tconn is None:
        st.error(f'Prediction store unavailable: {_terr}')
    else:
        if any(e.get('demo') for e in _tevals):
            st.warning('DEMO DATA: this store contains seeded demonstration slates, not real results.')
        st.caption(f'Store: {trk.db_path()} · Streamlit Community Cloud storage is ephemeral (lost on reboot/redeploy); export JSON below to keep history.')
        _r7,_r30,_rall = trk.rolling(_tevals,7), trk.rolling(_tevals,30), trk.rolling(_tevals)
        _pct = lambda r: '—' if r['rate'] is None else f"{r['rate']*100:.0f}%"
        st.markdown(ui.stat_strip([('Last 7 slates',_pct(_r7),'overlap'),('Last 30 slates',_pct(_r30),'stat'),
            ('All graded picks',f"{_rall['hits']}/{_rall['picks']}",'odds'),('Pending slates',sum(1 for e in _tevals if e['status']=='pending'),'gem')]),unsafe_allow_html=True)
        _status = st.session_state.get('v54_trk_status')
        _info = trk.slate_info(_tconn, np_day)
        _c1,_c2 = st.columns([3,2])
        with _c1:
            st.markdown(ui.section('Predictions for '+np_day,'Auto-saved for today and future slates · locked at first puck drop','🔒','stat'),unsafe_allow_html=True)
            if _info:
                st.caption(('🔒 Locked '+str(_info['locked_at'])[:16].replace('T',' ')+' UTC') if _info['locked'] else '🟡 Saved, not locked yet (re-saved when rankings change)')
            else:
                st.caption('No predictions saved for this slate yet.')
            if _status and _status.get('status') == 'error':
                st.warning('Auto-save failed: ' + str(_status.get('error')))
        with _c2:
            if st.button('🔒 Lock predictions', key='v54_lock', disabled=bool(_info and _info['locked']), use_container_width=True):
                try:
                    if not _info:
                        if not np_ready:
                            raise trk.TrackerError('Rankings for this slate are not loaded yet.')
                        trk.save_predictions(_tconn, np_day, trk.build_prediction_rows(assign_statistical_ranks(np_ranked.copy()), _home_leaders, np_games,
                                             home_gematria_shortlist(_home_targets,5)), n_games=len(np_games), lock=True, retro=np_day < np_eastern_today().isoformat())
                    else:
                        trk.lock_slate(_tconn, np_day)
                    st.success('Predictions locked. They will not be overwritten.')
                except (trk.TrackerError, ValueError, KeyError, TypeError) as _exc:
                    st.warning(str(_exc))
        if _tevals:
            st.markdown(ui.section('Recent slates','Newest first · pending slates are excluded from every rate','🗂️','overlap'),unsafe_allow_html=True)
            st.markdown('<div class="np-slates">'+''.join(ui.slate_card(e) for e in sorted(_tevals,key=lambda e:e['day'],reverse=True)[:9])+'</div>',unsafe_allow_html=True)
            _trend = trk.trend(_tevals)
            if not _trend.empty:
                st.markdown(ui.section('Hit-rate trend','Per slate and rolling 7 slates (%)','📈','stat'),unsafe_allow_html=True)
                st.line_chart((_trend.set_index('Slate')*100).round(1))
            st.markdown(ui.section('By source','Stats · Numbers · Odds · Overlap picks','🧩','gem'),unsafe_allow_html=True)
            _src = trk.source_breakdown(_tevals)
            _src['Hit rate'] = _src['Hit rate'].map(lambda v: None if v is None else round(v*100,1))
            st.dataframe(_src, hide_index=True, use_container_width=True, column_config={'Hit rate': st.column_config.NumberColumn('Hit rate', format='%.1f%%')})
            st.markdown(ui.section('Player leaderboard','Shrunk hit rate (prior strength 10) · badges need ≥3 graded picks','🏅','odds'),unsafe_allow_html=True)
            if _trecs.empty:
                st.info('No graded picks yet.')
            else:
                _show = _trecs.drop(columns=['player_key']).copy()
                for _c in ('Hit rate','Shrunk rate'): _show[_c] = (_show[_c]*100).round(1)
                _show['Adjustment'] = (_show['Adjustment']*100).round(1)
                if 'Badge' in _show: _show['Badge'] = _show['Badge'].fillna('—')
                st.dataframe(_show.head(25), hide_index=True, use_container_width=True, column_config={
                    'Hit rate': st.column_config.NumberColumn('Hit rate', format='%.1f%%'),
                    'Shrunk rate': st.column_config.NumberColumn('Shrunk rate', format='%.1f%%'),
                    'Adjustment': st.column_config.NumberColumn('Adj (toggle ON)', format='%+.1f%%')})
        else:
            st.info('No history yet. Predictions are saved automatically when a slate’s rankings load; enter results after games are final.')
        st.markdown(ui.section('Enter results','Manual entry per game · or import final NHL results','✍️','team'),unsafe_allow_html=True)
        _tg = mc.slate_games(np_games)
        if not _tg:
            st.info('No games on this slate to enter results for.')
        else:
            with st.form('v54_results_form'):
                _gsel = st.selectbox('Game', [g['key'] for g in _tg], format_func=lambda k: next((f"{g['away']} @ {g['home']}" for g in _tg if g['key']==k), k), key='v54_res_game')
                _gg = next(g for g in _tg if g['key']==_gsel)
                _roster = []
                if np_ready:
                    for _, _r in np_ranked[np_ranked['Team'].isin([_gg['away'],_gg['home']])].iterrows():
                        _roster.append({'player': str(_r['Player']), 'player_id': ui.player_id(_r.get('Player ID')), 'team': str(_r['Team'])})
                _roster.sort(key=lambda p: (p['team'], p['player']))
                _ms = st.multiselect('Goal scorers (roster)', list(range(len(_roster))), format_func=lambda i: f"{_roster[i]['player']} · {_roster[i]['team']}", key='v54_res_ms')
                _free = st.text_area('Other scorers (free text, one per line or comma-separated)', key='v54_res_free', help='Matched to the roster by accent-insensitive name; unmatched names are saved by name.')
                _final = st.checkbox('Game is final', value=True, key='v54_res_final')
                _sub = st.form_submit_button('Save results')
            if _sub:
                _names = [n for n in re.split(r'[\n,;]+', _free or '') if n.strip()]
                _matched, _unmatched = trk.resolve_names(_names, _roster)
                _scorers = [{**_roster[i], 'goals': 1} for i in _ms] + [{**m, 'goals': 1} for m in _matched] + [{'player': n.strip(), 'goals': 1, 'team': ''} for n in _unmatched]
                try:
                    _n = trk.record_game_results(_tconn, np_day, _gg['game_id'] or _gg['key'], _scorers, source='manual', final=_final)
                    st.success(f'Saved {_n} scorer(s) for {_gg["away"]} @ {_gg["home"]}.')
                    if _unmatched:
                        st.warning('Saved by name (no unique roster match): ' + ', '.join(_unmatched))
                except trk.TrackerError as _exc:
                    st.warning(str(_exc))
            if st.button('⬇️ Import final results from NHL', key='v54_nhl_import'):
                _done, _skip = 0, []
                for _g in _tg:
                    try:
                        _events, _is_final = trk.fetch_final_goals(_g['game_id'])
                    except trk.TrackerError as _exc:
                        _skip.append(str(_exc)); continue
                    if not _is_final:
                        _skip.append(f"{_g['away']} @ {_g['home']}: not final yet"); continue
                    _sc = trk.events_to_scorers(_events).get(str(_g['game_id']), [])
                    trk.record_game_results(_tconn, np_day, _g['game_id'], _sc, source='nhl', final=True); _done += 1
                st.success(f'Imported {_done} final game(s).') if _done else st.info('No final games imported.')
                if _skip:
                    with st.expander(f'{len(_skip)} game(s) skipped'):
                        st.write(_skip)
        _e1,_e2 = st.columns(2)
        with _e1:
            st.download_button('Export history (JSON)', trk.export_json(_tconn), file_name='nulls_playbook_track_record.json', mime='application/json', key='v54_export')
        with _e2:
            _imp = st.file_uploader('Import history (JSON)', type=['json'], key='v54_import')
            if _imp is not None and st.button('Merge import', key='v54_import_go'):
                try:
                    trk.import_json(_tconn, _imp.getvalue().decode('utf-8'))
                    st.success('History merged (locked slates kept as they were).')
                except (trk.TrackerError, ValueError, UnicodeDecodeError) as _exc:
                    st.warning(f'Import failed: {_exc}')
        with st.expander('How grading and learning work'):
            st.markdown('- **Pick**: the four Home leaders, the statistical top 10, the gematria top 5. Ranks 11–15 are a watch band.\n'
                        '- **Hit**: a pick who scored ≥1 goal in a final game. **Near-miss**: a watch-band player who scored, or a pick with an assist but no goal.\n'
                        '- **Unpredicted**: a scorer in a final game who was not a pick. Pending games/slates are excluded from rates.\n'
                        '- **Learning**: shrunk rate = (hits + 10·p0)/(picks + 10); adjustment = clamp(0.5·(shrunk−p0)/p0, ±5%), only with ≥3 graded picks; '
                        'applied only when “Use track record to adjust rankings” is ON (default OFF).')
    st.markdown(ui.footer("NULL’S PLAYBOOK · TRACK RECORD"),unsafe_allow_html=True)
