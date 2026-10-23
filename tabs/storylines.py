"""Null's Playbook V5.8 · Storylines tab. Executed by tabs.run_tab() inside the app's namespace.
Real data only (NHL api-web + ESPN public feeds + GeoNames); display only, never feeds rankings. See storylines_v58."""
import html as _sl_html
import storylines_v58 as slx

st.markdown(v5.tab_head('NULL’S PLAYBOOK · STORYLINES','Storylines',
    'Revenge games, former teams, birthdays, first games, hometowns, matchup history, streaks and the last 36h of news for tonight’s slate',
    chips=[('NHL API + ESPN','team'),('Display only · not in rankings','odds'),('New dads: not tracked','warn')],tone='gem'),unsafe_allow_html=True)
_sl_ranked=st.session_state.get('signals_ranked')
_sl_ready=isinstance(_sl_ranked,pd.DataFrame) and not _sl_ranked.empty and st.session_state.get('signals_day')==np_day
_sl_rows_in=_sl_ranked.to_dict('records') if _sl_ready else []
if _sl_ready and 'Statistical rank' not in _sl_ranked:
    _sl_rows_in=assign_statistical_ranks(_sl_ranked.copy()).to_dict('records')
_sl_games=[g for g in (_v56_games or []) if g.get('away') and g.get('home')]
_sl_key=(np_day,tuple(sorted(f"{g['away']}@{g['home']}" for g in _sl_games)),len(_sl_rows_in))
try:
    _sl_intel,_=intel_from_state(st.session_state,np_day)
    _sl_picks=intel_four_picks(_sl_intel)
except Exception:
    _sl_picks={}
_sl_pick_ids={}
for _k,_lbl in INTEL_LABELS:
    _p=(_sl_picks or {}).get(_k) or {}
    try: _sl_pick_ids.setdefault(int(float(_p.get('Player ID'))),[]).append(_lbl.title())
    except (TypeError,ValueError): pass
_c1,_c2,_c3=st.columns([2,2,1])
with _c1: _sl_q=st.text_input('Search player / team / story',key='v58_sl_q',placeholder='e.g. revenge, TOR, birthday')
with _c2: _sl_groups=st.multiselect('Groups',list(slx.GROUPS),default=list(slx.GROUPS),key='v58_sl_groups')
with _c3: _sl_force=st.button('↻ Rebuild',key='v58_sl_rebuild',use_container_width=True)

def _sl_build(progress,_day=np_day,_games=_sl_games,_rows=_sl_rows_in):
    cur=str(slx.season_of(_day))
    return slx.build(_day,_games,_rows,slx.nhl_fetch,lambda pid,s:slx.nhl_log(pid,s,cur),slx.espn_fetch,progress=progress)

if not _sl_games:
    st.info('No NHL games for this date, so there are no storylines to build.')
else:
    _sl_job=slx.job_for(_sl_key,_sl_build,force=_sl_force)
    _sl_job._t.join(timeout=1.5)

    @st.fragment(run_every=('3s' if _sl_job.running else None))
    def np_storylines_view():
        j=slx.job_for(_sl_key,_sl_build)
        if j.running:
            st.markdown(v5.inline(f'<div class="sl-wait"><b>Building tonight’s storylines…</b><span>{j.done}/{j.total or "?"} player profiles loaded · '
                                  'the rest of the app stays usable</span></div>','v58-sl'),unsafe_allow_html=True)
            return
        if j.error or not j.result:
            st.warning(f'Storylines could not be built: {j.error or "no result"}. Nothing is shown rather than guessed.')
            return
        res=j.result
        rows=[r for r in res['rows'] if r['group'] in _sl_groups]
        q=slx.norm(_sl_q)
        if q:
            rows=[r for r in rows if q in slx.norm(' '.join(str(r.get(k) or '') for k in ('tag','player','team','opp','story','detail','group')))]
        cnt=slx.counters(res['rows'])
        st.markdown(ui.stat_strip([('Revenge games',cnt['Revenge games'],'warn'),('Former teams',cnt['Former teams'],'gem'),
            ('Bdays · 1st games · hometowns',cnt['Birthdays / first games / hometowns'],'team'),
            ('News stories',cnt['News stories'] if res.get('feeds_ok') else 'n/a','odds')]),unsafe_allow_html=True)
        st.markdown(v5.inline('<p class="sl-legend"><b>Legend</b> '+_sl_html.escape(slx.LEGEND)+' · NP FORM = Null’s Playbook Form % (relative index, not a probability) · '
                              '★ = tonight’s Top storyline candidate / intel pick · New dads are not tracked (no reliable free source).</p>','v58-sl'),unsafe_allow_html=True)
        body=[]
        for g,rs in slx.grouped(rows):
            if g not in _sl_groups: continue
            body.append(f'<tr class="sl-g"><th colspan="7">{_sl_html.escape(g)} <span>{len(rs)}</span></th></tr>')
            if not rs:
                msg='ESPN feeds unavailable right now - no news shown (never invented).' if g==slx.G_NEWS and not res.get('feeds_ok') else 'Nothing on tonight’s slate.'
                body.append(f'<tr class="sl-none"><td colspan="7">{msg}</td></tr>')
            for r in rs:
                star=''.join(f'<span class="sl-star" title="{_sl_html.escape(x)}">★ {_sl_html.escape(x)}</span>' for x in _sl_pick_ids.get(r.get('pid'),[]))
                story=_sl_html.escape(r['story'])
                if r.get('link'): story=f'<a href="{_sl_html.escape(r["link"])}" target="_blank" rel="noopener">{story}</a>'
                score=ui.format_form_pct(r['score']) if r.get('score') is not None else '—'
                body.append(f'<tr><td><span class="sl-tag t-{slx.norm(r["tag"]).replace(" ","-")}">{_sl_html.escape(r["tag"])}</span></td>'
                            f'<td class="sl-p"><b>{_sl_html.escape(r["player"] or "—")}</b>{star}</td><td>{_sl_html.escape(r["team"] or "—")}</td>'
                            f'<td>{_sl_html.escape(r["opp"] or "—")}</td><td class="sl-n">{score}</td><td class="sl-s">{story}</td>'
                            f'<td class="sl-d">{_sl_html.escape(r["detail"])} <small>· {_sl_html.escape(r["source"])}</small></td></tr>')
        st.markdown(v5.inline('<div class="sl-wrap"><table class="sl-t"><thead><tr><th>Tag</th><th>Player</th><th>TM</th><th>OPP</th><th>NP FORM</th>'
                              '<th>Story</th><th>Detail</th></tr></thead><tbody>'+''.join(body)+'</tbody></table></div>','v58-sl'),unsafe_allow_html=True)
        src=' · '.join(f'{k}: {v}' for k,v in res['sources'].items())
        st.caption(f'Built {res["built_at"][:16].replace("T"," ")} UTC for {res["n_players"]} slate skaters · {src} · hometowns via GeoNames (CC BY 4.0), ≤{slx.HOME_KM} km from the home arena.'
                   +(f' · {len(res["errors"])} fetch issue(s) skipped.' if res['errors'] else ''))
        if not _sl_ready:
            st.caption('Rankings are not built for this date yet, so NP FORM and the VS OPP / streak rows (top 40 by NP rank) are empty. Build rankings on Home.')
    np_storylines_view()
