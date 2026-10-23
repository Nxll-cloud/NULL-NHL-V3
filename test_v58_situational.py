"""V5.8 situational next-goal layer (situational_v58): PP boost, goalie adjustment, line context, exact fallback,
propagation (scored players stay settled) and offline data fetch. All fixtures, no network."""
import math

import pytest

import edgeflags_v56 as eflags
import edgelab_v58 as elv
import feature_flags_v58 as ff
import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import parlay_v58 as parlay
import situational_v58 as sit

AWAY, HOME = 'AAA', 'BBB'


def priors():
    return {1: {'name': 'Pp Sniper', 'team': AWAY, 'pos': 'C', 'gp': 40, 'goals': 16, 'sog': 120, 'form': None, 'source': 'season'},
            2: {'name': 'Ev Grinder', 'team': AWAY, 'pos': 'L', 'gp': 40, 'goals': 8, 'sog': 80, 'form': None, 'source': 'season'},
            3: {'name': 'Home Wing', 'team': HOME, 'pos': 'R', 'gp': 40, 'goals': 10, 'sog': 100, 'form': None, 'source': 'season'},
            4: {'name': 'Home D', 'team': HOME, 'pos': 'D', 'gp': 40, 'goals': 3, 'sog': 60, 'form': None, 'source': 'season'}}


def sk(gp=40, goals=16, shots=120, ppg=6, pps=30, pp_min=120.0, ev=14.0, rev=None, rgp=0):
    return {'gp': gp, 'goals': goals, 'shots': shots, 'pp_goals': ppg, 'pp_shots': pps, 'pp_toi_min': pp_min,
            'ev_toi_pg': ev, 'recent_ev_toi_pg': rev, 'recent_gp': rgp}


TEAMS = {AWAY: {'pp_opps': 120, 'pp_gp': 40, 'times_sh': 115, 'sh_gp': 40},
         HOME: {'pp_opps': 115, 'pp_gp': 40, 'times_sh': 120, 'sh_gp': 40}}


def goalie(team, name, pid, sv, sa=1000):
    return {'Team': team, 'Goalie': name, 'Player ID': str(pid), 'SA': sa, 'Saves': round(sv * sa)}


def lam(res, pid):
    return next(r for r in res['players'] if r['pid'] == pid)['lam_game']


def run(ctx, game=None):
    return ng.model(game or ng.pregame_game(1, AWAY, HOME), priors(), situ=sit.Situ(ctx))


def live_game():
    g = dict(ng.pregame_game(7, AWAY, HOME, state='LIVE'), period=2, secs_remaining=600, away_score=1, home_score=0,
             away_sog=10, home_sog=8, situation='1551')
    g['events'] = [{'eid': 1, 'kind': 'goal', 'period': 1, 'ptype': 'REG', 'secs': 300, 'shooter': 1, 'team': AWAY,
                    'goalie': 99, 'strength': 'EV', 'shot_type': 'wrist', 'x': 70, 'y': 0, 'xg': 0.1, 'order': 1},
                   {'eid': 2, 'kind': 'sog', 'period': 2, 'ptype': 'REG', 'secs': 100, 'shooter': 2, 'team': AWAY,
                    'goalie': 99, 'strength': 'EV', 'shot_type': 'wrist', 'x': 60, 'y': 5, 'xg': 0.05, 'order': 2},
                   {'eid': 3, 'kind': 'sog', 'period': 2, 'ptype': 'REG', 'secs': 200, 'shooter': 3, 'team': HOME,
                    'goalie': 88, 'strength': 'EV', 'shot_type': 'slap', 'x': 60, 'y': 5, 'xg': 0.05, 'order': 3}]
    return g


# ------------------------------------------------------------------ no-info fallback = the old model, exactly
@pytest.mark.parametrize('game', [ng.pregame_game(1, AWAY, HOME), live_game()])
def test_no_info_fallback_reproduces_old_numbers_exactly(game):
    old = ng.model(game, priors())
    for ctx in (sit.context(), sit.context(parts=()), sit.context(skaters={99: sk()}, teams={'ZZZ': {}})):
        new = ng.model(game, priors(), situ=sit.Situ(ctx))
        assert [(r['pid'], r['lam_game'], r['rate'], r['p_next']) for r in new['players']] == \
               [(r['pid'], r['lam_game'], r['rate'], r['p_next']) for r in old['players']]
        assert new['p_team'] == old['p_team'] and new['p_none'] == old['p_none'] and new['team_rate'] == old['team_rate']
        assert all(r['situ']['ratio'] == 1.0 and r['situ']['applied'] == [] for r in new['players'])


def test_flag_off_means_no_situ_and_old_code_path():
    old = ng.model(ng.pregame_game(1, AWAY, HOME), priors())
    assert all('situ' not in r for r in old['players'])
    assert ff.model_situational(environ={'MODEL_SITUATIONAL': '0'}) is False
    assert ff.model_situational(secrets={'MODEL_SITUATIONAL': 'false'}, environ={}) is False
    assert ff.model_situational(secrets={'MODEL_SITUATIONAL': 'false'}, environ={'MODEL_SITUATIONAL': 'on'}) is True
    assert ff.model_situational(environ={}) is True
    assert ff.model_parts(environ={'MODEL_SITUATIONAL_PARTS': 'goalie, PP ,bogus'}) == ('goalie', 'pp')
    assert ff.model_parts(environ={}) == ('pp', 'goalie', 'line')


# ------------------------------------------------------------------ power play
def test_pp_boost_heavy_pp_shooter_beats_same_player_without_pp_time():
    heavy = sit.context(skaters={1: sk(ppg=8, pps=40, pp_min=160.0)}, teams=TEAMS, parts=('pp',))
    none_ = sit.context(skaters={1: sk(ppg=0, pps=0, pp_min=0.0)}, teams=TEAMS, parts=('pp',))
    bh, bn = run(heavy)['players'], run(none_)['players']
    h = next(r for r in bh if r['pid'] == 1)['situ']
    n = next(r for r in bn if r['pid'] == 1)['situ']
    assert h['applied'] == ['pp'] and h['pp'] > 0 and n['pp'] == 0 and n['pp_add'] < 0
    assert lam(run(heavy), 1) > lam(run(none_), 1)
    # more PP minutes at the same per-minute shot rate -> more PP expected goals
    more = sit.context(skaters={1: sk(ppg=8, pps=60, pp_min=240.0)}, teams=TEAMS, parts=('pp',))
    assert next(r for r in run(more)['players'] if r['pid'] == 1)['situ']['pp'] > h['pp']
    # players without stats-API rows stay on the old lambda
    assert lam(run(heavy), 3) == lam(ng.model(ng.pregame_game(1, AWAY, HOME), priors()), 3)


def test_pp_volume_scales_with_opponent_penalties_and_is_bounded():
    s = {1: sk()}
    lo = dict(TEAMS, **{HOME: {'pp_opps': 115, 'pp_gp': 40, 'times_sh': 60, 'sh_gp': 40}})
    hi = dict(TEAMS, **{HOME: {'pp_opps': 115, 'pp_gp': 40, 'times_sh': 400, 'sh_gp': 40}})
    f_lo = sit.opp_factor(AWAY, HOME, lo, 3.0)
    f_hi = sit.opp_factor(AWAY, HOME, hi, 3.0)
    assert sit.OPP_MIN <= f_lo < 1 < f_hi == sit.OPP_MAX
    assert lam(run(sit.context(skaters=s, teams=lo, parts=('pp',))), 1) < lam(run(sit.context(skaters=s, teams=hi, parts=('pp',))), 1)
    assert sit.opp_factor(AWAY, 'ZZZ', TEAMS) is None


def test_league_average_player_keeps_the_ten_percent_baseline():
    # EV and PP shrink targets are anchored so the league shot mix still converts at LEAGUE_SH (10 %)
    assert sit.F_PP * sit.LEAGUE_PP_SH + (1 - sit.F_PP) * sit.LEAGUE_EV_SH == pytest.approx(sit.LEAGUE_SH)
    assert sit.shrink(0, 0, 0.1, 50) == pytest.approx(0.1)


# ------------------------------------------------------------------ goalie
def test_goalie_adjustment_strong_lowers_weak_raises_and_clamps():
    strong = sit.context(goalies=[goalie(HOME, 'Wall Goalie', 30, 0.930)], parts=('goalie',))
    weak = sit.context(goalies=[goalie(HOME, 'Sieve Goalie', 31, 0.860)], parts=('goalie',))
    absurd = sit.context(goalies=[goalie(HOME, 'Perfect Goalie', 32, 1.0, sa=100000)], parts=('goalie',))
    base = lam(ng.model(ng.pregame_game(1, AWAY, HOME), priors()), 1)
    assert lam(run(strong), 1) < base < lam(run(weak), 1)
    assert lam(run(absurd), 1) == pytest.approx(base * sit.GOALIE_MIN, abs=1e-4)
    # the home skaters face AWAY's goalie: no AWAY goalie rows -> unchanged
    assert lam(run(strong), 3) == lam(ng.model(ng.pregame_game(1, AWAY, HOME), priors()), 3)
    m, sv = sit.goalie_mult_from(0, 0)
    assert m == 1.0 and sv == pytest.approx(sit.LEAGUE_SV)


def test_probable_starter_beats_team_average_and_live_goalie_beats_starter():
    rows = [goalie(HOME, 'Starter Guy', 30, 0.930), goalie(HOME, 'Backup Guy', 31, 0.870)]
    starters = {'g1': {AWAY: {'team': AWAY, 'goalie': None, 'status': 'unknown'}, HOME: {'team': HOME, 'goalie': 'Starter Guy', 'status': 'probable'}}}
    team_avg = sit.context(goalies=rows, parts=('goalie',))
    with_st = sit.with_starters(team_avg, starters)
    s_avg = next(r for r in run(team_avg)['players'] if r['pid'] == 1)['situ']
    s_st = next(r for r in run(with_st)['players'] if r['pid'] == 1)['situ']
    assert s_avg['goalie_source'].startswith('team average') and s_st['goalie_source'] == 'probable starter'
    assert s_st['goalie'] == 'Starter Guy' and s_st['goalie_mult'] < s_avg['goalie_mult']
    # live: the backup (id 31) is in net per play-by-play
    g = live_game()
    for e in g['events']:
        if e['team'] == AWAY:
            e['goalie'] = 31
    s_live = next(r for r in run(with_st, g)['players'] if r['pid'] == 1)['situ']
    assert s_live['goalie'] == 'Backup Guy' and s_live['goalie_source'].startswith('in net') and s_live['goalie_mult'] > 1
    assert sit.live_goalie(g, AWAY) == 31 and sit.live_goalie(g, 'ZZZ') is None


def test_live_rate_scaled_by_the_same_ratio():
    ctx = sit.context(goalies=[goalie(HOME, 'Sieve Goalie', 31, 0.860)], parts=('goalie',))
    old = {r['pid']: r for r in ng.model(live_game(), priors())['players']}
    new = {r['pid']: r for r in run(ctx, live_game())['players']}
    assert new[1]['rate'] == pytest.approx(old[1]['rate'] * new[1]['situ']['ratio'])
    assert new[1]['situ']['ratio'] > 1 and new[3]['rate'] == old[3]['rate']


# ------------------------------------------------------------------ line / TOI context
def test_line_mult_promotion_demotion_and_bounds():
    assert sit.line_mult(sk(ev=14.0, rev=17.0, rgp=6)) > 1
    assert sit.line_mult(sk(ev=14.0, rev=10.0, rgp=6)) < 1
    assert sit.line_mult(sk(ev=14.0, rev=40.0, rgp=50)) == sit.LINE_MAX
    assert sit.line_mult(sk(ev=14.0, rev=1.0, rgp=50)) == sit.LINE_MIN
    assert sit.line_mult(sk(ev=14.0, rev=None, rgp=0)) == 1.0
    ctx = sit.context(skaters={2: sk(ev=12.0, rev=16.0, rgp=6)}, parts=('line',))
    bd = next(r for r in run(ctx)['players'] if r['pid'] == 2)['situ']
    assert bd['applied'] == ['line'] and bd['final'] == pytest.approx(bd['base'] * bd['line_mult'])


def test_combined_breakdown_logged_bounded_and_why_string():
    ctx = sit.context(skaters={1: sk(rev=16.0, rgp=5)}, teams=TEAMS, goalies=[goalie(HOME, 'Sieve Goalie', 31, 0.860)])
    r = next(x for x in run(ctx)['players'] if x['pid'] == 1)
    bd = r['situ']
    assert set(bd['applied']) == {'pp', 'goalie', 'line'}
    assert sit.RATIO_MIN <= bd['ratio'] <= sit.RATIO_MAX and r['lam_game'] == round(bd['final'], 4)
    expect = (bd['ev'] + bd['pp'] + (bd['line_mult'] - 1) * bd['ev']) * bd['goalie_mult']
    assert bd['final'] == pytest.approx(expect)
    w = sit.why(bd)
    assert 'base' in w and 'PP' in w and 'BBB goalies' in w and len(w) < 200


# ------------------------------------------------------------------ propagation: scored stay settled
def test_scored_players_stay_excluded_downstream_with_situ_on():
    ctx = sit.context(goalies=[goalie(HOME, 'Sieve Goalie', 31, 0.860), goalie(AWAY, 'Other', 32, 0.9)])
    g = live_game()
    res = run(ctx, g)
    item = {'slate': {'away': AWAY, 'home': HOME, 'start': None, 'key': 'k', 'status': 'LIVE'}, 'label': 'live', 'result': res}
    scored = {1}
    priced, unpriced = elv.model_rows([item], {}, scored_ids=scored)
    assert 1 not in {r['pid'] for r in priced + unpriced}
    cands = parlay.candidates([item], scored=scored)
    assert 1 not in {c['pid'] for c in cands}
    # model p downstream is the situational lambda
    row = next(r for r in unpriced if r['pid'] == 2)
    rec2 = next(r for r in res['players'] if r['pid'] == 2)
    assert row['model_p'] == pytest.approx(ng.p_anytime(eflags.player_lambda(rec2, 'live', res['remaining'])))
    assert row['why'] and 'goalie ×' in row['why']
    assert 'title="' in elv.table_html([], unpriced)


def test_slate_results_threads_situ_through_both_model_calls():
    ctx = sit.context(goalies=[goalie(HOME, 'Sieve Goalie', 31, 0.860)], parts=('goalie',))
    games = [{'key': 'k', 'game_id': 1, 'away': AWAY, 'home': HOME, 'start': None, 'venue': '', 'status': 'FUT'}]
    old = lstate.slate_results(games, priors())
    new = lstate.slate_results(games, priors(), situ=sit.Situ(ctx))
    lo = next(r for r in old[0]['result']['players'] if r['pid'] == 1)
    ln = next(r for r in new[0]['result']['players'] if r['pid'] == 1)
    assert ln['lam_game'] > lo['lam_game'] and ln['situ']['goalie'] == 'BBB goalies'


# ------------------------------------------------------------------ parsing + offline fetch
def test_parsers_and_fetch_context_never_raises():
    s = sit.parse_skaters([{'playerId': 1, 'gamesPlayed': 10, 'goals': 3, 'shots': 30}],
                          [{'playerId': 1, 'ppGoals': 1, 'ppShots': 6, 'ppTimeOnIce': 1800, 'gamesPlayed': 10}],
                          [{'playerId': 1, 'evTimeOnIcePerGame': 840}], [{'playerId': 1, 'evTimeOnIcePerGame': 900, 'gamesPlayed': 4}])
    assert s[1]['pp_toi_min'] == 30.0 and s[1]['recent_gp'] == 4 and s[1]['ev_toi_pg'] == 840
    t = sit.parse_teams([{'teamId': 8, 'ppOpportunities': 30, 'gamesPlayed': 10}], [{'teamId': 8, 'timesShorthanded': 28, 'gamesPlayed': 10}],
                        [{'id': 8, 'triCode': 'MTL'}])
    assert t == {'MTL': {'pp_opps': 30, 'pp_gp': 10, 'times_sh': 28, 'sh_gp': 10}}
    gl = sit.parse_goalies([{'playerId': 5, 'goalieFullName': 'Traded Guy', 'teamAbbrevs': 'CHI, MTL', 'saves': 90, 'shotsAgainst': 100}])
    assert gl[0]['Team'] == 'MTL' and gl[0]['Player ID'] == '5'
    assert sit.league_pp_opp_pg({}) == sit.LEAGUE_PP_OPP_PG

    def boom(url, params=None):
        raise OSError('offline')
    ctx = sit.fetch_context('2026-10-23', '20262027', getter=boom)
    assert ctx['skaters'] == {} and ctx['errors']
    res = run(ctx)
    assert all(r['situ']['ratio'] == 1.0 for r in res['players'])


# ------------------------------------------------------------------ rankings label == model starter
def ranking_rows():
    return [{'Player': 'Pp Sniper', 'Team': AWAY, 'Opponent': HOME, 'Starting goalie': 'Unconfirmed', 'Goalie adjustment': 'Not applied'},
            {'Player': 'Home Wing', 'Team': HOME, 'Opponent': AWAY, 'Starting goalie': 'Unconfirmed', 'Goalie adjustment': 'Not applied'}]


def test_rankings_label_and_model_agree_on_probable_starter():
    rows = [goalie(HOME, 'Spencer Knight', 30, 0.905), goalie(HOME, 'Backup Guy', 31, 0.870),
            goalie(AWAY, 'Jakub Dobes', 40, 0.880)]
    # ESPN-style probables (no NHL id), keyed by (away, home) like probable_goalies_v54.fetch_starters
    starters = {(AWAY, HOME): {HOME: {'team': HOME, 'goalie_id': None, 'goalie': 'Spencer Knight', 'status': 'probable',
                                      'source': 'ESPN scoreboard (probables)'},
                               AWAY: {'team': AWAY, 'goalie_id': None, 'goalie': 'Jakub Dobes', 'status': 'confirmed',
                                      'source': 'ESPN scoreboard (probables)'}}}
    ctx = sit.with_starters(sit.context(goalies=rows), starters)
    out = sit.goalie_columns(ranking_rows(), ctx)
    assert out[0]['Starting goalie'] == 'Spencer Knight (Probable)'
    assert out[1]['Starting goalie'] == 'Jakub Dobes (Confirmed)'
    res = run(ctx)
    for row, pid in ((out[0], 1), (out[1], 3)):
        bd = next(r for r in res['players'] if r['pid'] == pid)['situ']
        name = row['Starting goalie'].split(' (')[0]
        assert bd['goalie'] == name and bd['goalie_source'].endswith('starter')
        assert row['Goalie adjustment'] == f"Applied ×{bd['goalie_mult']:.2f} vs {name} ({bd['goalie_source']})"
    # flag off: label still from the source, note says not applied
    off = sit.goalie_columns(ranking_rows(), sit.with_starters(sit.context(goalies=rows, parts=('pp',)), starters))
    assert off[0]['Starting goalie'] == 'Spencer Knight (Probable)' and off[0]['Goalie adjustment'].startswith('Not applied')


def test_rankings_label_unconfirmed_only_without_a_listed_starter():
    rows = [goalie(HOME, 'Spencer Knight', 30, 0.905)]
    for starters in ({}, {(AWAY, HOME): {HOME: {'team': HOME, 'goalie': None, 'status': 'unknown'}}}):
        ctx = sit.with_starters(sit.context(goalies=rows), starters)
        out = sit.goalie_columns(ranking_rows(), ctx)
        assert out[0]['Starting goalie'] == 'Unconfirmed' and out[1]['Starting goalie'] == 'Unconfirmed'
        bd = next(r for r in run(ctx)['players'] if r['pid'] == 1)['situ']
        assert bd['goalie_source'] == 'team average (SA-weighted)'
        assert out[0]['Goalie adjustment'] == f"Applied ×{bd['goalie_mult']:.2f} vs {HOME} goalies (team average (SA-weighted))"
        # no AWAY goalie stats at all -> neutral, and the note says so
        assert out[1]['Goalie adjustment'] == 'Not applied (no goalie stats)'
        assert next(r for r in run(ctx)['players'] if r['pid'] == 3)['situ']['goalie_mult'] == 1.0
    # listed starter whose stats cannot be matched: label shows the starter, note says team average was used
    st = {(AWAY, HOME): {HOME: {'team': HOME, 'goalie': 'Call Up Kid', 'status': 'probable'}}}
    out = sit.goalie_columns(ranking_rows(), sit.with_starters(sit.context(goalies=rows), st))
    assert out[0]['Starting goalie'] == 'Call Up Kid (Probable)' and 'starter stats not matched' in out[0]['Goalie adjustment']


# ------------------------------------------------------------------ light AppTest (offline fixtures)
def test_apptest_rankings_label_matches_espn_probables_and_tabs_render(monkeypatch, tmp_path):
    import v54_testkit as kit
    import probable_goalies_v54 as pgk
    gl = [dict(r, **{'Player ID': str(r['Player ID'])}) for r in kit.club_rows()]   # real captured club-stats goalie rows
    monkeypatch.setattr(sit, 'fetch_context', lambda day, season, getter=None, starters=None, parts=sit.PARTS:
                        sit.context(goalies=gl, parts=parts, sources={'goalies': 'fixture'}))
    at = kit.run_app(monkeypatch, tmp_path)
    assert not at.exception
    ranked = at.session_state['signals_ranked']
    espn = pgk.parse_espn_scoreboard(kit.load('espn_scoreboard_20261022.json'))
    listed = {(a, h, t): s for (a, h), v in espn.items() for t, s in v.items()}
    checked = 0
    for r in ranked.to_dict('records'):
        opp, team = r['Opponent'], r['Team']
        s = next((s for (a, h, t), s in listed.items() if t == opp and {a, h} == {team, opp}), None)
        assert r['Starting goalie'] == (f"{s['goalie']} ({s['status'].title()})" if s else 'Unconfirmed')
        if s:
            checked += 1
            assert r['Goalie adjustment'].startswith('Applied') or r['Goalie adjustment'].startswith('Not applied')
    assert checked > 0
    page = kit.markdown(at)
    assert 'Unconfirmed' not in ' '.join(ranked[ranked['Starting goalie'] != 'Unconfirmed']['Starting goalie'])
    assert 'title="base' in page   # EdgeLab model-p cell carries the situational "why"
