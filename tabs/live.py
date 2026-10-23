"""V5.6 shared live state (not a tab body): slate games, score endpoint, per-game PBP pollers and the next-goal model.

Runs once per script run before the tabs so Home (board scores + live strip), Matchup Center, Live Next Goal and
Edge Flags all read the same numbers. Network only through the cached, never-raising fetchers defined in app.py."""

try:
    _v56_games_raw=np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day)
except (requests.RequestException, ValueError, KeyError, TypeError):
    _v56_games_raw=[]
_v56_games=mc.slate_games([g for g in (_v56_games_raw or []) if isinstance(g,dict)])
_v56_ranked=st.session_state.get('signals_ranked')
_v56_rows=_v56_ranked.to_dict('records') if isinstance(_v56_ranked,pd.DataFrame) and st.session_state.get('signals_day')==np_day else []
_v56_priors=ng.priors_from_rankings(_v56_rows)
_v56_now=datetime.now(timezone.utc)
_v56_scores,_v56_scores_err=v56_scores_cached(np_day) if _v56_games else ({},None)
_v56_force=st.session_state.pop('v56_force_refresh',False)


def v56_collect(force=False):
    """Poll every game that has (or should have) play-by-play. Returns ({game_id: parsed}, {game_id: poller})."""
    pbp, pollers = {}, {}
    for g in _v56_games:
        gid = str(g.get('game_id') or '')
        if not gid:
            continue
        state = (_v56_scores.get(gid) or {}).get('state')
        if state is None and v5.game_state(g, _v56_now) in ('live', 'done'):
            state = 'LIVE'  # score endpoint unavailable: the clock says the game has started
        if not lstate.needs_pbp(state, g.get('status')):
            continue
        parsed, p = v56_poll(gid, force)
        pollers[gid] = p
        if parsed is not None:
            pbp[gid] = parsed
    return pbp, pollers


_v56_pbp,_v56_pollers=v56_collect(_v56_force)
_v56_mem=st.session_state.setdefault('v56_rank_mem',{})
_v56_results=lstate.slate_results(_v56_games,_v56_priors,_v56_scores,_v56_pbp,_v56_mem)
_v56_by_key={r['slate']['key']:r for r in _v56_results}
_v56_live_n=sum(1 for r in _v56_results if r['result']['phase']=='live')


def v56_updated(gid):
    p = _v56_pollers.get(str(gid))
    if p is None or p.updated_at is None:
        return None
    return datetime.fromtimestamp(p.updated_at, timezone.utc).strftime('%H:%M:%S UTC')
