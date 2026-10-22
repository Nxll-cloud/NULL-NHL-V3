"""NULL NHL V3.2: source-first NHL slate and descriptive player form."""
from datetime import date, datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo
import pandas as pd
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

st.set_page_config(page_title="Null's Playbook | NHL", page_icon='👑', layout='wide', initial_sidebar_state='collapsed')
from playbook_odds import compare_odds
from odds_intelligence_v46 import attach_model, order_opportunities, quote_audit, quotes_for_market, price_label, normalized_name, identity_ambiguities
from odds_api_v45 import fetch_odds, OddsFeedError
from snapshot_store import load_snapshot
from streamlit_autorefresh import st_autorefresh

st.markdown("""<style>
:root {color-scheme:dark}
.stApp {background:radial-gradient(ellipse at 25% 0%,#102b4c 0%,#070d1a 36%,#070b14 100%);color:#eaf4ff}
[data-testid="stSidebar"] {background:#081322;border-right:1px solid #1c3d5e}
[data-testid="stHeader"] {background:transparent}
h1,h2,h3 {color:#e8f5ff!important;letter-spacing:-.035em}
h1 {font-size:clamp(2rem,4vw,3.2rem)!important}
div.stButton>button[kind="primary"],div.stDownloadButton>button {border:1px solid #187fe9;background:#0a3261;color:#f1faff;border-radius:12px}
div.stButton>button:hover,div.stDownloadButton>button:hover {border-color:#38bdf8;color:white}
[data-testid="stMetric"] {border:1px solid #214264;background:linear-gradient(135deg,#0c213b,#091626);border-radius:14px;padding:14px}
[data-testid="stMetricValue"] {color:#5bd2ff}
[data-testid="stDataFrame"] {border-radius:12px;overflow:hidden}
[data-testid="stExpander"] {border:1px solid #1d3654;border-radius:12px}
.np-hero {border:1px solid #1763a2;border-radius:22px;padding:22px 25px;background:linear-gradient(115deg,#0c3762 0%,#0b2340 48%,#071528 100%);box-shadow:0 8px 35px #0005;margin-bottom:18px}
.np-kicker {font-size:.7rem;letter-spacing:.2em;font-weight:800;color:#69c9ff}
.np-title {font-size:clamp(2rem,5vw,3.6rem);font-weight:900;line-height:1.05;letter-spacing:-.05em;color:white;margin:8px 0}
.np-sub {color:#a5c5e4;font-size:.95rem;max-width:800px}
.np-tag {display:inline-block;background:#082b4c;border:1px solid #296b9e;color:#a8e7ff;padding:6px 10px;border-radius:999px;font-size:.75rem;margin-top:13px}
.np-player {border:1px solid #24466b;border-radius:15px;background:linear-gradient(140deg,#102947,#081523);padding:13px;margin:7px 0;min-height:120px}
.np-player-name {font-size:1.1rem;font-weight:800;color:#fff}
.np-muted {font-size:.78rem;color:#9bbbd6}
.np-head {height:76px;width:76px;object-fit:contain;float:right;filter:drop-shadow(0 4px 12px #0008)}
.np-team {height:22px;width:22px;object-fit:contain;vertical-align:middle}
@media(max-width:768px){.block-container {padding:1rem .8rem 5rem!important}.np-hero{padding:18px 15px;border-radius:17px}.np-player{min-height:110px} [data-testid="stMetric"]{padding:10px}}
</style>""",unsafe_allow_html=True)


st.markdown("""<style>
.np-match-scroll,.np-feature-scroll{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;padding:8px 0 16px;scrollbar-width:thin}
.np-match{flex:0 0 174px;scroll-snap-align:start;border:1px solid #235581;border-radius:16px;padding:14px;background:linear-gradient(145deg,#102c4a,#071321);display:flex;flex-direction:column;gap:9px;text-align:center}
.np-match-logos{display:flex;justify-content:space-around;align-items:center;gap:8px}.np-match-logos img{width:48px;height:48px;object-fit:contain}.np-match-logos span{color:#74b9ed;font-size:11px}.np-match small,.np-feature small{color:#a6c0da;font-size:12px}
.np-feature{flex:0 0 205px;scroll-snap-align:start;border:1px solid #2362a2;border-radius:17px;padding:14px;background:linear-gradient(145deg,#12365c,#071321);display:flex;flex-direction:column;gap:7px}
.np-feature-top{height:108px;display:flex;justify-content:space-between}.np-photo{height:110px;width:110px;object-fit:contain}.np-rank{color:#62d8ff;font-weight:800}.np-feature b{font-size:16px;color:white}.np-feature-score{color:#6fe0a0;font-size:25px;font-weight:800}.np-feature-score span{font-size:9px;color:#a9c1d5;font-weight:600}
.np-mobile-footer{display:none}
@media(max-width:768px){.np-match{flex-basis:145px}.np-feature{flex-basis:185px}.np-mobile-footer{display:block;text-align:center;color:#91c9ed;font-size:11px;letter-spacing:.04em;padding:18px 0 12px}.stTabs [data-baseweb="tab-list"]{gap:5px;position:sticky;top:0;z-index:10;background:#071322;padding:7px 0}.stTabs [data-baseweb="tab"]{padding:8px 11px;font-size:14px}}
</style>""",unsafe_allow_html=True)


st.markdown("""<style>
@media(max-width:768px){
 [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important}
 [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"]{width:auto!important;min-width:0!important;flex:none!important}
 [data-testid="stMetric"]{min-height:76px!important}
 [data-testid="stToolbar"]{display:none!important}
 .np-hero{padding:16px 17px!important;margin-bottom:10px!important;border-radius:16px!important}
 .np-title{font-size:1.85rem!important;line-height:1.06!important}
 .np-sub{font-size:.78rem!important}
 [data-testid="stMetric"]{padding:7px 9px!important;border-radius:11px!important}
 [data-testid="stMetricLabel"]{font-size:.67rem!important}
 [data-testid="stMetricValue"]{font-size:1.22rem!important}
 .np-feature{flex-basis:166px!important;padding:11px!important}
 .np-feature-top{height:88px!important}
 .np-photo{height:92px!important;width:94px!important}
 .np-feature-score{font-size:21px!important}
 .np-match{flex-basis:134px!important;padding:10px!important}
 .np-match-logos img{height:38px!important;width:38px!important}
 .stTabs [data-baseweb="tab-list"]{position:sticky;top:0;z-index:30;justify-content:space-around;box-shadow:0 5px 15px #0007}
 .stTabs [data-baseweb="tab"]{font-weight:700!important;font-size:13px!important}
 .block-container{padding-top:1.3rem!important}
}
</style>""",unsafe_allow_html=True)

with st.sidebar:
    st.markdown('### 👑 Null’s Playbook')
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
np_selected_date=st.date_input('📅 NHL slate date',date.today(),key='playbook_v42_date')
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
def history_status(day):
    job=st.session_state.get('v43_history_job')
    if not job or job['day'] != day:
        return
    future=job['future']
    if not future.done():
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
        st.warning(f'History unavailable: {type(exc).__name__}: {exc}')


np_home_tab,np_odds_tab,np_research_tab=st.tabs(['🏠 Home','⚡ Odds','📊 Research'])
with np_home_tab:

    import html as _np_html
    from datetime import date as _np_date
    st.markdown("""<div class="np-hero"><div class="np-kicker">👑 NULL'S PLAYBOOK · V4.4</div><div class="np-title">Your NHL command center.</div><div class="np-sub">Verified rankings · matchup intelligence · historical storylines · sportsbook price comparison</div></div>""", unsafe_allow_html=True)
    st.caption('Auto slate snapshots · scheduled 30-minute updates · three prior seasons · real NHL data only')
    if np_snapshot is not None:
        st.caption('🟢 Saved rankings updated: '+np_snapshot['updated_at'][:19].replace('T',' ')+' UTC · '+str(len(np_snapshot['rankings']))+' players')
        if np_snapshot.get('errors'):
            st.caption(f'⚠️ {len(np_snapshot["errors"])} data retrieval warnings in saved snapshot')
    else:
        st.warning('No scheduled snapshot for this date yet. Live fallback may take 30 seconds or longer. Run the GitHub workflow to precompute it.')
    history_status(np_day)
    if st.session_state.get('v42_last_rank') and st.session_state.get('signals_day')==np_day:
        st.caption('Rankings last updated: '+st.session_state['v42_last_rank']['at'].astimezone(ZoneInfo('America/New_York')).strftime('%b %-d, %-I:%M %p ET'))
    try:
        np_games=np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day)
    except (requests.RequestException, ValueError, KeyError, TypeError) as np_err:
        np_games=[]
        st.warning(f'Unable to load matchups: {np_err}')
    if np_games:
        st.markdown('#### 🏒 Matchup center')
        np_games_html=[]
        for g in np_games[:16]:
            a=_np_html.escape(str(g.get('Away',''))); h=_np_html.escape(str(g.get('Home','')))
            np_games_html.append(f'<div class="np-match"><div class="np-match-logos"><img loading="lazy" src="https://assets.nhle.com/logos/nhl/svg/{a}_light.svg" alt="{a}"/><span>VS</span><img loading="lazy" src="https://assets.nhle.com/logos/nhl/svg/{h}_light.svg" alt="{h}"/></div><b>{a} · {h}</b><small>{_np_html.escape(format_game_time(g.get("Start (UTC)")))}</small></div>')
        st.markdown('<div class="np-match-scroll">'+''.join(np_games_html)+'</div>',unsafe_allow_html=True)
    np_ranked=st.session_state.get('signals_ranked')
    np_ready=isinstance(np_ranked,pd.DataFrame) and not np_ranked.empty and st.session_state.get('signals_day')==np_day
    np_a,np_b,np_c=st.columns(3)
    np_a.metric('Games on slate',len(np_games))
    np_b.metric('Ranked players',len(np_ranked) if np_ready else '—')
    np_c.metric('Sportsbooks loaded',st.session_state['playbook_odds_data']['sportsbook'].nunique() if isinstance(st.session_state.get('playbook_odds_data'),pd.DataFrame) and 'sportsbook' in st.session_state['playbook_odds_data'] else '—')
    if not np_ready:
        st.info('⏳ Automatically loading the full NHL slate and three seasons of opponent history. This may take a few minutes on first load.')
    else:
        np_view=assign_statistical_ranks(np_ranked.copy())
        np_view=merge_history(np_view, st.session_state.get('history_v38') if st.session_state.get('history_v38_day')==np_day else None)
        np_view=merge_multi_history(np_view, st.session_state.get('history_v386') if st.session_state.get('history_v386_day')==np_day else None)
        st.markdown('#### ⚡ Top statistical candidates')
        np_cards=[]
        for _,r in np_view.sort_values('Statistical rank').head(8).iterrows():
            n=_np_html.escape(str(r.get('Player',''))); t=_np_html.escape(str(r.get('Team','')))
            pid=r.get('Player ID'); pid=str(int(pid)) if pd.notna(pid) and str(pid).replace('.0','').isdigit() else ''
            img=f'https://assets.nhle.com/mugs/nhl/20262027/{t}/{pid}.png' if pid else ''
            idx=float(r.get('V3.2 Adjusted Index',0))
            rank=int(r.get('Statistical rank',0))
            np_cards.append(f'<div class="np-feature"><div class="np-feature-top"><span class="np-rank">#{rank}</span><img loading="lazy" class="np-photo" src="{img}" alt="Player portrait"/></div><b>{n}</b><small><img style="width:18px;height:18px;vertical-align:middle;object-fit:contain" src="https://assets.nhle.com/logos/nhl/svg/{t}_light.svg" alt=""/> {t} · Rank #{rank}</small><div class="np-feature-score">{idx:.1f}<span> FORM SCORE</span></div></div>')
        st.markdown('<div class="np-feature-scroll">'+''.join(np_cards)+'</div>',unsafe_allow_html=True)
        st.markdown('#### 📊 Statistical leaderboard')
        np_cols=[c for c in ['Statistical rank','Player','Team','V3.2 Adjusted Index','Shots/G L5'] if c in np_view]
        st.dataframe(np_view.sort_values('Statistical rank')[np_cols].head(10),hide_index=True,use_container_width=True)
        if st.session_state.get('history_v386_day')==np_day:
            np_cov=historical_coverage(np_view)
            st.markdown('#### 📋 Historical coverage')
            st.progress(np_cov['fraction'])
            st.caption(f"{np_cov['complete']} / {np_cov['total']} complete · {np_cov['partial']} partial · {np_cov['not_fetched']} not fetched")
    if 'playbook_odds_data' in st.session_state:
        try:
            _,np_disc=compare_odds(st.session_state['playbook_odds_data'])
            if not np_disc.empty:
                st.markdown('#### ⚡ Top sportsbook price discrepancies')
                st.caption('Open Odds Intelligence to compare the biggest price gaps across sportsbooks.')
        except ValueError:
            pass
    else:
        st.markdown('#### ⚡ Sportsbook price intelligence')
        st.info('No sportsbook odds connected. Open **Odds** to upload real quotes and compare identical props.')
    st.markdown('<div class="np-mobile-footer">👑 <b>PLAYBOOK</b> &nbsp; · &nbsp; HOME &nbsp; · &nbsp; ODDS &nbsp; · &nbsp; RESEARCH</div>',unsafe_allow_html=True)

@st.cache_data(ttl=1800,show_spinner=False)
def np_live_odds_cached(api_key, regions, markets):
    return fetch_odds(api_key,regions=regions,markets=markets)

def np_api_key():
    try:
        return st.secrets.get('ODDS_API_KEY','')
    except (FileNotFoundError, KeyError):
        return ''

with np_odds_tab:
    import html as _odds_html
    st.markdown("""<div class="np-odds-hero"><div class="np-kicker">NULL’S PLAYBOOK · V4.6</div><div class="np-odds-title">Odds Intelligence<span class="np-dot">.</span></div><div class="np-odds-sub">Find the strongest prices. Compare the market. Follow your model.</div></div>""",unsafe_allow_html=True)
    api_key=np_api_key()
    regions='us'
    markets='player_goal_scorer_anytime'
    api_df=None
    if api_key:
        try:
            with st.spinner('Syncing available NHL goal-scorer prices…'):
                api_df,api_warnings=np_live_odds_cached(api_key,regions,markets)
            if api_warnings:
                st.caption(f'Coverage notice: {len(api_warnings)} events could not be retrieved.')
        except (OddsFeedError,ValueError) as exc:
            st.warning(f'Live prices unavailable: {exc}')
    else:
        st.info('Connect your odds feed in app secrets to enable automatic price comparison. CSV import is also available.')
    with st.expander('⚙️ Import & display preferences',expanded=False):
        source_choice=st.radio('Odds source',['Automatic API','Uploaded CSV','Combine both'],horizontal=False,key='v46_source')
        uploaded_odds=st.file_uploader('Optional CSV odds import',type=['csv'],key='playbook_odds_upload')
        if uploaded_odds is not None:
            try:
                st.session_state['playbook_odds_data']=pd.read_csv(uploaded_odds,dtype={'event_id':str,'line':str})
            except (ValueError,UnicodeError) as exc:
                st.warning(f'CSV could not be read: {exc}')
        st.download_button('CSV template','player,team,market,selection,sportsbook,american_odds,updated_at,event_id,line\\n',file_name='playbook_odds_template.csv',mime='text/csv')
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
            c1,c2,c3=st.columns(3)
            c1.metric('Sportsbooks',int(price_rows['sportsbook'].nunique()))
            c2.metric('Matched props',len(discrepancies))
            c3.metric('Valid quotes',len(price_rows))
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
                st.markdown('#### ⚡ Market scanner')
                st.caption('Identity verification is required before a price gap can be considered actionable. Name-only provider quotes are unverified.')
                f1,f2=st.columns(2)
                with f1:
                    view_mode=st.selectbox('Sort by',['Biggest discrepancy','Model-backed','Longshots'],key='v46_mode')
                with f2:
                    book_min=st.selectbox('Books compared',[2,3,4,5],key='v46_min_books')
                rank_limit=st.selectbox('Statistical shortlist',['All players','Top 25','Top 50','Top 100'],key='v47_rank_filter')
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
                    for ix,(_,r) in enumerate(show.head(30).iterrows()):
                        player=_odds_html.escape(str(r['player']))
                        book=_odds_html.escape(str(r['best_sportsbook']))
                        low_book=_odds_html.escape(str(r['worst_sportsbook']))
                        team=_odds_html.escape(str(r.get('team','')))
                        rank=r.get('model_rank')
                        rank_text=f"Model #{int(rank)}" if pd.notna(rank) else "Model rank unavailable"
                        pid=str(r.get('player_id',''))
                        mug=f'https://assets.nhle.com/mugs/nhl/20262027/{team}/{pid}.png' if team and pid else ''
                        photo=f'<img class="np-odds-photo" src="{mug}" loading="lazy" alt="Player portrait"/>' if mug else '<div class="np-odds-avatar">🏒</div>'
                        gap=float(r['decimal_price_improvement_pct'])
                        identity_note=_odds_html.escape(str(r.get('identity_status','Unverified')))
                        status_color='#ffbb70' if 'Ambiguous' in identity_note else '#9cb7cc'
                        st.markdown(f"""<div class="np-odds-card"><div class="np-odds-card-head">{photo}<div class="np-odds-player"><div class="np-odds-name">{player}</div><div class="np-odds-context">{team} · {rank_text} · {int(r['sportsbooks_compared'])} books</div><div class="np-odds-identity" style="color:{status_color}">{identity_note}</div></div><div class="np-odds-price">{price_label(r['best_odds'])}<small>{book}</small></div></div><div class="np-odds-card-foot"><span>LOW {price_label(r['worst_odds'])} · {low_book}</span><strong>+{gap:.1f}% payout difference</strong></div></div>""",unsafe_allow_html=True)
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
        st.subheader('🏆 NULL NHL — Four Distinct Leaders')
        st.caption('Evidence-first, pre-slate storylines. Former-team and injury/news claims are not inferred.')
    st.caption('Scheduled 30-minute snapshots when available · live fallback for unsaved dates · three prior seasons · not calibrated probabilities')
    day = np_day

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
                        st.markdown(f'''<div class="np-player" style="min-height:100px;text-align:center"><div class="np-muted">{_html.escape(str(game.get('Start (UTC)','')))}</div><div style="display:flex;justify-content:center;align-items:center;gap:13px;margin-top:9px"><img alt="{away}" src="https://assets.nhle.com/logos/nhl/svg/{away}_light.svg" style="height:38px;width:38px;object-fit:contain"/><b>{away} vs {home}</b><img alt="{home}" src="https://assets.nhle.com/logos/nhl/svg/{home}_light.svg" style="height:38px;width:38px;object-fit:contain"/></div></div>''',unsafe_allow_html=True)
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
    st.caption('Goal-scoring form score is a relative index, NOT a scoring probability. Opponent goals/shots allowed '
               'adjust the form score by at most 15% where coverage is sufficient. '
               'Goalie starters are unconfirmed and no goalie adjustment is applied.')
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
                st.dataframe(pd.DataFrame(ranked), hide_index=True, use_container_width=True)
                st.download_button('Download rankings CSV', pd.DataFrame(ranked).to_csv(index=False),
                                   file_name=f'null-nhl-v3-2-{day}.csv', mime='text/csv')
                st.caption('Statistical sleepers (NOT verified betting longshots): players outside the top 20 '
                           'with at least 2 shots per game over the last 5 games.')
                watch = [r for r in ranked[20:] if r['Shots/G L5'] >= 2]
                if watch:
                    st.dataframe(pd.DataFrame(watch[:20]), hide_index=True, use_container_width=True)
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
                    st.dataframe(scored, hide_index=True, use_container_width=True)
                    st.download_button('Download scored snapshot CSV', scored.to_csv(index=False),
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
    metadata = None
    if meta_file is not None:
        try:
            metadata = pd.read_csv(meta_file, dtype=str).fillna('')
            if 'Player ID' not in metadata.columns:
                st.warning('Metadata needs a Player ID column; metadata ignored.')
                metadata = None
        except (ValueError, pd.errors.ParserError) as exc:
            st.warning(f'Metadata could not be loaded: {exc}')
    if st.session_state.get('auto_signal_day') == day and 'auto_signal_metadata' in st.session_state:
        automatic = st.session_state['auto_signal_metadata']
        if metadata is None:
            metadata = automatic
        else:
            metadata = pd.concat([metadata, automatic], ignore_index=True).drop_duplicates(subset=['Player ID'], keep='first')
    if 'signals_ranked' in st.session_state and st.session_state.get('signals_day') == day:
        signals = build_signals(st.session_state['signals_ranked'], day, metadata)
        st.caption(f'{len(signals)} players evaluated. Pattern overlap counts are descriptive, '
                   'not confidence scores. Missing biographical data remains unavailable.')
        st.dataframe(signals, hide_index=True, use_container_width=True)
        storylines = build_storylines(st.session_state['signals_ranked'], metadata if metadata is not None else pd.DataFrame(), day)
        combined = combined_table(st.session_state['signals_ranked'], signals, storylines)
        combined = merge_history(combined, st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None)
        combined = merge_multi_history(combined, st.session_state.get('history_v386') if st.session_state.get('history_v386_day') == day else None)
        validate_statistical_ranks(combined)
        top_stories, storyline_sleepers, featured = select_storyline_watch(combined)
        v387 = separate_leaders(combined)
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
            labels = [('statistical','TOP STATISTICAL GOALSCORER'),('storyline','TOP STORYLINE CANDIDATE'),('overlap','BEST MODEL + STORYLINE OVERLAP'),('longshots','STATISTICAL SLEEPER')]
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
                photo=f'<img class="np-research-photo" src="https://assets.nhle.com/mugs/nhl/20262027/{team}/{pid}.png" alt="Player portrait" loading="lazy"/>' if pid else '<div class="np-research-placeholder">🏒</div>'
                history_text=f'{goals} goals in {gp} previous meetings' if history_ok else 'Opponent history unavailable or insufficient'
                st.markdown(f"""<div class="np-research-card"><div class="np-research-eyebrow">{label}</div><div class="np-research-row">{photo}<div class="np-research-person"><div class="np-research-name">{name}</div><div class="np-research-team">{team} · Statistical rank #{rank}</div><div class="np-research-form">{form:.1f} <small>GOAL-SCORING FORM SCORE</small></div></div></div><div class="np-research-stats"><div><b>{shots:.1f}</b><small>Shots/game · L5</small></div><div><b>{goals if history_ok else '—'}</b><small>Opponent goals</small></div><div><b>{flags}</b><small>Storyline flags</small></div></div><div class="np-research-note">{history_text} · {evidence:.1f} storyline points</div></div>""",unsafe_allow_html=True)
                with st.expander(f'Detailed analysis · {lead.get("Player", "Player")}',expanded=False):
                    st.caption(f'Statistical rank #{rank} · Goal-scoring form score {form:.1f} · Storyline evidence {evidence:.2f}')
                    st.write('**Evidence:**',lead.get('Verified data flags','Not available'))
                    st.caption('Historical opponent data: '+str(lead.get('Historical coverage','Unavailable')))
                    st.caption('Form score is a relative statistical index, not a goal probability. Storyline evidence is a separate heuristic.')
            st.caption('Storyline evidence points are an explicitly heuristic display index: 2 per historical goal (max 10), 6 × historical goals/game (max 1.5), historical shots/10 (max 50 shots), plus 1.5 per sourced flag (max 5). Historical components require complete requested seasons and ≥3 meetings. They are NOT validated predictive weights.')
            for key,title in [('statistical','Top 10 Statistical'),('storyline','Top 10 Storylines'),('overlap','Top 10 Overlap'),('longshots','Top 10 Statistical Sleepers')]:
                st.subheader(title)
                frame=v387[key]
                if frame.empty: st.info('No eligible players in currently loaded data.')
                else:
                    cols=['Player','Team','Statistical rank','Storyline rank','Storyline evidence score','Storyline count','Historical opponent GP','Historical opponent goals','Historical opponent shots','Shots/G L5','Verified data flags']
                    st.dataframe(frame[[c for c in cols if c in frame]],hide_index=True,use_container_width=True)
                    st.download_button('Download '+title+' CSV',frame.to_csv(index=False),file_name=f'null-v387-{key}-{day}.csv',mime='text/csv',key=f'v387_{key}')
        st.download_button('Download top 10 storyline watchlist CSV', top_stories.to_csv(index=False), file_name=f'null-v381-top10-{day}.csv', mime='text/csv')
        st.subheader('V3.8.2 Data Integrity Audit')
        audit = coverage_audit(combined, st.session_state.get('auto_signal_metadata') if st.session_state.get('auto_signal_day') == day else None,
                               st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None)
        st.dataframe(pd.DataFrame([audit]), hide_index=True, use_container_width=True)
        if audit['Histories fetched'] < audit['Eligible players']:
            st.info('Opponent-history coverage is partial; zero flags on unfetched players do not mean no storyline.')
        st.download_button('Download ALL evaluated players + storyline evidence CSV', combined.to_csv(index=False),
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
        st.dataframe(filtered, hide_index=True, use_container_width=True)
        st.download_button('Download combined V3.6 CSV', filtered.to_csv(index=False), file_name=f'null-v36-combined-{day}.csv', mime='text/csv')
        st.download_button('Download experimental signals CSV', signals.to_csv(index=False),
                           file_name=f'null-experimental-signals-{day}.csv', mime='text/csv')
    else:
        st.info('Run Rank Entire Slate for this date to populate the experimental signals table.')

st.markdown("""<style>
.np-odds-hero{background:linear-gradient(125deg,#102e52,#091527 65%,#0a1122);border:1px solid #285b88;border-radius:21px;padding:24px 22px;margin:8px 0 18px;box-shadow:0 16px 40px #0004}
.np-odds-title{font-size:clamp(1.9rem,5vw,3rem);letter-spacing:-.055em;font-weight:850;line-height:1.1;color:#fff;margin:7px 0}.np-dot{color:#4bd6ff}.np-odds-sub{color:#a4c1da;font-size:.88rem}
.np-odds-card{border:1px solid #244b71;background:linear-gradient(125deg,#112e4b,#091626);border-radius:17px;padding:13px 14px;margin:11px 0 3px;box-shadow:0 7px 25px #0004}
.np-odds-card-head{display:flex;align-items:center;gap:10px}.np-odds-photo,.np-odds-avatar{height:66px;width:61px;object-fit:contain;flex-shrink:0}.np-odds-avatar{display:grid;place-items:center;background:#173552;border-radius:12px}
.np-odds-player{min-width:0;flex:1}.np-odds-name{color:#fff;font-size:1.03rem;font-weight:800;line-height:1.2}.np-odds-context{color:#91acc4;font-size:.72rem;margin-top:5px}
.np-odds-price{color:#69e2ad;font-weight:850;font-size:1.6rem;text-align:right;white-space:nowrap;letter-spacing:-.04em}.np-odds-price small{display:block;color:#b8d3e9;font-size:.7rem;font-weight:500;letter-spacing:0}
.np-odds-card-foot{border-top:1px solid #294560;margin-top:11px;padding-top:9px;display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap;font-size:.74rem;color:#a9bdd1}.np-odds-card-foot strong{color:#59d5ff}
@media(max-width:768px){.np-odds-hero{padding:17px 15px}.np-odds-card{padding:11px}.np-odds-photo,.np-odds-avatar{width:52px;height:58px}.np-odds-price{font-size:1.35rem}.np-odds-name{font-size:.96rem}}
</style>""",unsafe_allow_html=True)

st.markdown("""<style>
.np-research-card{background:linear-gradient(125deg,#12365a 0%,#0a192c 75%);border:1px solid #315d84;border-radius:19px;padding:17px;margin:13px 0 4px;box-shadow:0 12px 32px #0004}
.np-research-eyebrow{color:#66d9ff;font-weight:850;font-size:.66rem;letter-spacing:.12em;margin-bottom:9px}
.np-research-row{display:flex;align-items:center;gap:13px}.np-research-photo,.np-research-placeholder{height:99px;width:85px;object-fit:contain;flex-shrink:0}.np-research-placeholder{display:grid;place-items:center;background:#153553;border-radius:12px}
.np-research-person{flex:1;min-width:0}.np-research-name{color:#fff;font-size:1.16rem;font-weight:850}.np-research-team{color:#a6bfd4;font-size:.76rem;margin-top:3px}.np-research-form{color:#68e0af;font-size:1.65rem;font-weight:850;margin-top:8px;letter-spacing:-.04em}.np-research-form small{display:block;color:#9fbcd2;font-size:.58rem;letter-spacing:.05em;font-weight:600}
.np-research-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:12px}.np-research-stats>div{background:#193a57;border-radius:10px;padding:9px}.np-research-stats b{display:block;font-size:1.05rem;color:#fff}.np-research-stats small{display:block;font-size:.64rem;color:#abc2d6}.np-research-note{color:#b7ccdf;font-size:.76rem;line-height:1.5;margin-top:12px}
.np-odds-identity{font-size:.64rem;margin-top:5px}
@media(max-width:768px){.np-research-card{padding:13px}.np-research-photo,.np-research-placeholder{height:86px;width:71px}.np-research-name{font-size:1.04rem}}
</style>""",unsafe_allow_html=True)
