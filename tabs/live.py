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
vn.fill(_v56_games,_v56_scores)   # V5.8: older snapshots without a Venue get the score endpoint's real arena (never guessed)


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
_v56_situ=None   # V5.8: situational layer (PP split, opposing goalie, TOI deployment); off -> the V5.6 model exactly
if _v56_games and _v56_priors and np_flags.model_situational(st.secrets):
    _v56_parts=np_flags.model_parts(st.secrets)
    _v56_st=starters_cached(np_day,tuple((g['key'],g['game_id'],g['away'],g['home'],g['status']) for g in _v56_games))[0] if 'goalie' in _v56_parts else {}
    _v56_situ=sit.layer(situ_cached(np_day,SEASON,_v56_parts,xg_cutoff(np_day,_v56_games)),_v56_st)


def v56_slate_results(scores=None, pbp=None, memory=None, use_form=False):
    """V5.9: the ONE next-goal path for every surface (Home, Matchup Center, Live Next Goal, Edge Flags): same priors and
    the same situational layer ``_v56_situ`` (None when MODEL_SITUATIONAL is off, i.e. the V5.6 model exactly)."""
    return lstate.slate_results(_v56_games,_v56_priors,_v56_scores if scores is None else scores,_v56_pbp if pbp is None else pbp,
                                _v56_mem if memory is None else memory,use_form=use_form,situ=_v56_situ)


def v56_model(game, use_form=False):
    """One game through the same model + situational layer (used by the Live Next Goal DEMO replay)."""
    return lstate.model(game,_v56_priors,use_form=use_form,situ=_v56_situ)


_v56_results=v56_slate_results()
_v56_by_key={r['slate']['key']:r for r in _v56_results}
_v56_live_n=sum(1 for r in _v56_results if r['result']['phase']=='live')


def v56_updated(gid):
    p = _v56_pollers.get(str(gid))
    if p is None or p.updated_at is None:
        return None
    return datetime.fromtimestamp(p.updated_at, timezone.utc).strftime('%H:%M:%S UTC')
