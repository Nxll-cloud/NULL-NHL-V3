"""Null's Playbook V5.9 · Prediction Models tab. Executed by tabs.run_tab() inside the app's namespace.

Four systems side by side (2 x 2 on tablets, stacked on phones): the model (goal chance), the NP statistical
leaderboard, the EXPERIMENTAL blend (model chance x gematria layer hits, prediction_models_v59) and the books top
picks (odds_scorers_v59 consensus, books_picks_v59). Display only: reads the frozen logs (snapshots/accuracy/,
accuracy_blend/, accuracy_books/) through short caches and reuses the app's already-loaded _np_odds_scorers; no git
history, no extra odds call and no network work at page load.
Nothing here feeds the model, the NP ranks, the parlay or the accuracy card."""
import prediction_models_v59 as pmv


@st.cache_data(ttl=600, show_spinner=False)
def _pm_logs(sig):
    """Blend records + accuracy entries + books records (sig = file names + mtimes, so a new freeze shows at once)."""
    import books_picks_v59 as _bp
    return pmv.load_all(), _pm_acc_all(), _bp.load_all()


def _pm_acc_all():
    import accuracy_v58 as _acc
    return [_acc.attach_np(e, lambda d: _acc._load_snap(d, _acc.SNAP_DIR)) for e in _acc.load_all()]


def _pm_sig():
    out = []
    import books_picks_v59 as _bp
    for d in (pmv.ROOT, pmv.acc.LOG_DIR, _bp.ROOT):
        try:
            out += [(p.name, p.stat().st_mtime_ns) for p in sorted(pmv.Path(d).glob('????-??-??.json'))]
        except OSError:
            pass
    return tuple(out)


@st.cache_data(ttl=600, show_spinner=False)
def _pm_card(yday, sig):
    """The Model accuracy card (moved here from Home in V5.9; accuracy_v58.home_html unchanged apart from the top-10
    list). Keyed on Eastern 'yesterday' (so the midnight rollover still switches the night) + the log signature."""
    return pmv.acc.home_html()


@st.cache_data(ttl=900, show_spinner=False)
def _pm_layers(day, key, _rankings, _games):
    return pmv.layers_for({'day': day, 'rankings': _rankings, 'games': _games}, day)


st.markdown(v5.tab_head('NULL’S PLAYBOOK · PREDICTION MODELS', 'Prediction Models',
    'Testing four ways to rank tonight’s goal scorers, each scored the same way: how many of its top 10 actually scored',
    chips=[('Model · NP · Blend · Books', 'team'), ('Scored by player ID', 'odds'), ('Testing · blend is experimental', 'warn')], tone='neon'),
    unsafe_allow_html=True)
try:
    _pm_recs, _pm_accs, _pm_books = _pm_logs(_pm_sig())
    _pm_ns = pmv.nights(_pm_recs, _pm_accs, np_day, books_recs=_pm_books)
    _pm_rank_df = st.session_state.get('signals_ranked')
    _pm_rows = (_pm_rank_df.to_dict('records') if isinstance(_pm_rank_df, pd.DataFrame) and st.session_state.get('signals_day') == np_day
                else ((np_snapshot or {}).get('rankings') or []))
    _pm_games = (np_snapshot or {}).get('games') or []
    _pm_entry = next((e for e in _pm_accs if e.get('day') == np_day), None)
    _pm_rec = next((r for r in _pm_recs if r.get('day') == np_day), None)
    _pm_cands = None
    _pm_lay = None
    if not (_pm_entry and _pm_entry.get('players')):
        try:
            _pm_cands = parlay.candidates(_v56_results, _v56_rows)
        except Exception:
            _pm_cands = []
    if not (_pm_rec and _pm_rec.get('top')) and _pm_rows:
        _pm_lay = _pm_layers(np_day, (len(_pm_rows), len(_pm_games)), _pm_rows, _pm_games)
    _pm_t = pmv.tonight(np_day, _pm_rows, _pm_games, _pm_entry, _pm_rec, _pm_cands, _pm_lay,
                        next((r for r in _pm_books if r.get('day') == np_day), None), globals().get('_np_odds_scorers'))
    _pm_scored = [int(p) for p in ((st.session_state.get(sctn.STATE_KEY) or {}).get('players') or {})]
    v5.html_block(st, pmv.summary_html(_pm_ns))
    st.markdown(v5.sec_head(f'Tonight’s top 10 · {pmv.acc.short_day(np_day)}',
                            'Model = goal chance · NP = statistical rank (Form %) · Blend = boosted chance + layers hit · Books = no-vig consensus'),
                unsafe_allow_html=True)
    v5.html_block(st, pmv.page_html(_pm_t, _pm_ns, _pm_scored))
    st.markdown(v5.sec_head('Model accuracy · detailed record',
                            'The Model column’s full scoring for the last completed slate: every scorer, ranks, trend'),
                unsafe_allow_html=True)
    v5.html_block(st, _pm_card(pmv.acc.eastern_yesterday().isoformat(), _pm_sig()))
    st.markdown(v5.sec_head('Night by night', f'Top-10 hits for each system over the last {pmv.TREND_N} nights'), unsafe_allow_html=True)
    _pm_skip = pmv.skipped_days(_pm_ns, np_day)
    v5.html_block(st, pmv.CSS + '<section class="pms" aria-label="Night by night">' + (pmv.nights_table(_pm_ns) or '<p>No scored night yet.</p>')
                  + (f'<p class="pmf">Skipped {len(_pm_skip)} night{"s" if len(_pm_skip) != 1 else ""} with no clean pre-game snapshot '
                     f'({pmv._e(", ".join(pmv.acc.short_day(d) for d in _pm_skip))}).</p>' if _pm_skip else '')
                  + '<p class="pmf">Saved = the Home accuracy card’s own frozen pre-game entry. Rebuilt = recomputed after the night '
                    'from the latest pre-game slate snapshot (no starters / injuries at freeze time), never a live freeze. Books nights are '
                    'only the ones frozen pre-game by the workflow (no odds were saved before its log started).</p></section>')
    st.caption('🧪 ' + pmv.EXPERIMENTAL_NOTE)
    st.caption('Weights: ' + pmv.WEIGHT_NOTE)
except Exception as _pm_exc:  # never break the app
    st.markdown(v5.empty_state('Prediction models unavailable', f'{type(_pm_exc).__name__}: the frozen logs could not be read.'),
                unsafe_allow_html=True)
