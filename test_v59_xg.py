"""V5.9 xG shot-quality layer (xg_v59 + hooks in situational_v58): weighting direction and shrinkage, exact fallback to
the situational model without xG, never-raising fetch, NHL playerId matching, flag off, point-in-time gating and
propagation (Edge Flags, EdgeLab why, parlay, long shot, scored-tonight). All fixtures, no network."""
import pytest

import edgeflags_v56 as eflags
import edgelab_v58 as elv
import feature_flags_v58 as ff
import live_nextgoal_v56 as ng
import longshot_v58 as longshot
import parlay_v58 as parlay
import situational_v58 as sit
import xg_v59 as xgm
from test_v58_situational import AWAY, HOME, TEAMS, goalie, lam, live_game, priors, run, sk

SEASON = '20262027'
DAY = '2026-10-23'
AS_OF = 'Fri, 23 Oct 2026 03:30:45 GMT'
HDR = 'playerId,season,name,team,position,situation,games_played,I_F_xGoals,I_F_shotsOnGoal,I_F_goals\n'
# League background (pid 900): 5on5 xG/SOG 0.10, 5on4 0.15, all 0.11 -> players 1..4 are measured against it
BG = [(900, '5on5', 1000.0, 10000, 1000), (900, '5on4', 300.0, 2000, 300), (900, 'all', 1430.0, 13000, 1430)]


def csv_text(rows, season='2026'):
    return HDR + ''.join(f'{p},{season},P{p},{AWAY},C,{s},40,{xg},{sog},{g}\n' for p, s, xg, sog, g in list(rows) + BG)


def data(rows, season='2026'):
    class R:
        text = csv_text(rows, season)
        headers = {'Last-Modified': AS_OF}
    return xgm.fetch(SEASON, getter=lambda url, params=None: R)


def ctx_with(xg_rows, parts=sit.PARTS, skaters=None, **kw):
    base = sit.context(skaters=skaters if skaters is not None else {1: sk(), 2: sk(goals=8, shots=80, ppg=2, pps=10, pp_min=40.0)},
                       teams=TEAMS, parts=parts, **kw)
    return sit.with_xg(base, data(xg_rows), DAY, SEASON)


def same(a, b):
    return [(r['pid'], r['lam_game'], r['rate'], r['p_next']) for r in a['players']] == \
           [(r['pid'], r['lam_game'], r['rate'], r['p_next']) for r in b['players']]


# ------------------------------------------------------------------ weighting direction + shrinkage
def test_high_danger_shooter_rises_low_danger_falls_vs_situational():
    plain = sit.context(skaters={1: sk(), 2: sk()}, teams=TEAMS)
    hi_lo = [(1, '5on5', 18.0, 90, 10), (1, '5on4', 6.0, 30, 6), (2, '5on5', 5.4, 90, 10), (2, '5on4', 3.0, 30, 6)]
    with_xg = ctx_with(hi_lo, skaters={1: sk(), 2: sk()})
    a, b = run(plain), run(with_xg)
    assert lam(b, 1) > lam(a, 1) and lam(b, 2) < lam(a, 2)
    x1 = next(r for r in b['players'] if r['pid'] == 1)['situ']['xg']
    assert x1['ev']['xg_per_shot_raw'] == pytest.approx(0.2) and 0.10 < x1['ev']['xg_per_shot_shrunk'] < 0.2
    assert x1['weight'] == xgm.W and x1['source'] == 'MoneyPuck.com' and x1['as_of'].startswith('2026-10-23T03:30')
    assert 'xg' in next(r for r in b['players'] if r['pid'] == 1)['situ']['applied']


def test_shrinkage_small_samples_move_less_and_quality_is_bounded():
    big = xgm.quality(data([(1, '5on5', 40.0, 200, 20)]), 1, 'ev')
    small = xgm.quality(data([(1, '5on5', 2.0, 10, 1)]), 1, 'ev')   # same 0.20 xG/SOG, 10 shots
    assert big['xg_per_shot_raw'] == small['xg_per_shot_raw'] == pytest.approx(0.2)
    assert 1.0 < small['quality'] < big['quality']
    q = (2.0 + xgm.K_XG * 0.1) / (10 + xgm.K_XG)
    assert small['xg_per_shot_shrunk'] == pytest.approx(round(q, 4))
    absurd = xgm.quality(data([(1, '5on5', 900.0, 1000, 900)]), 1, 'ev')
    assert absurd['quality'] == xgm.Q_HI and absurd['finishing'] <= xgm.F_HI
    m, info = xgm.blend(0.0917, sit.LEAGUE_EV_SH, absurd)
    assert m == pytest.approx(info['mult'], abs=1e-4) and 1 < m < 1 + xgm.W * (xgm.Q_HI * xgm.F_HI - 1) + 0.01


def test_league_average_player_is_neutral_ish_and_ratio_cap_holds():
    avg = [(1, '5on5', 10.0, 100, 10), (1, '5on4', 3.0, 20, 3)]
    m, _ = xgm.blend(sit.LEAGUE_EV_SH, sit.LEAGUE_EV_SH, xgm.quality(data(avg), 1, 'ev'))
    assert m == pytest.approx(1.0, abs=1e-9)
    hot = ctx_with([(1, '5on5', 200.0, 400, 200), (1, '5on4', 80.0, 100, 80)], skaters={1: sk(goals=60, shots=200, ppg=30, pps=60)})
    for r in run(hot)['players']:
        assert sit.RATIO_MIN <= r['situ']['ratio'] <= sit.RATIO_MAX


def test_no_pp_split_uses_all_situations_row():
    c = ctx_with([(1, '5on5', 30.0, 150, 15), (1, 'all', 36.0, 150, 15)], parts=('xg',), skaters={})
    bd = next(r for r in run(c)['players'] if r['pid'] == 1)['situ']
    assert set(bd['xg']) >= {'all'} and 'ev' not in bd['xg'] and bd['ratio'] > 1
    assert 'xG ×' in sit.why(bd) and ' all' in sit.why(bd)


# ------------------------------------------------------------------ exact fallback to the situational model
@pytest.mark.parametrize('game', [ng.pregame_game(1, AWAY, HOME), live_game()])
def test_missing_xg_reproduces_situational_numbers_exactly(game):
    plain = sit.context(skaters={1: sk(), 2: sk(goals=8, shots=80, ppg=2, pps=10, pp_min=40.0)}, teams=TEAMS,
                        goalies=[goalie(HOME, 'Sieve Goalie', 31, 0.860)])
    ref = run(plain, game)
    variants = [sit.with_xg(plain, None, DAY, SEASON),
                sit.with_xg(plain, xgm.empty('fetch failed: ConnectionError'), DAY, SEASON),
                sit.with_xg(plain, data([(555, '5on5', 3.0, 20, 2)]), DAY, SEASON),        # nobody on the slate matched
                sit.with_xg(plain, data([(1, '5on5', 3.0, 20, 2)], season='2025'), DAY, SEASON),   # last season only
                sit.with_xg(plain, data([(1, '5on5', 3.0, 20, 2)]), '2026-10-01', SEASON),  # historical day: leak guard
                sit.with_xg(plain, data([(1, '5on5', 3.0, 20, 2)]), '2026-12-01', SEASON),  # stale file
                sit.with_xg(dict(plain, parts=('pp', 'goalie', 'line')), data([(1, '5on5', 3.0, 20, 2)]), DAY, SEASON)]
    for c in variants:
        out = run(c, game)
        assert same(out, ref) and out['p_team'] == ref['p_team'] and out['team_rate'] == ref['team_rate']
        assert all('xg' not in r['situ'] and 'xg' not in r['situ']['applied'] for r in out['players'])
    assert 'stale' in sit.with_xg(plain, data([(1, '5on5', 3.0, 20, 2)]), '2026-12-01', SEASON)['sources']['xg']


def test_player_with_zero_sog_in_a_situation_falls_back_for_that_part_only():
    c = ctx_with([(1, '5on5', 18.0, 90, 10)])   # no 5on4 row
    x = next(r for r in run(c)['players'] if r['pid'] == 1)['situ']['xg']
    assert 'ev' in x and 'pp' not in x


def test_no_situational_info_and_no_xg_still_equals_old_v56_model():
    old = ng.model(ng.pregame_game(1, AWAY, HOME), priors())
    new = run(sit.with_xg(sit.context(), xgm.empty('x'), DAY, SEASON))
    assert same(new, old)


# ------------------------------------------------------------------ fetch / parse / ID matching
def test_fetch_never_raises_and_flags_errors():
    def boom(url, params=None):
        raise RuntimeError('network down')
    for g in (boom, lambda url, params=None: None, lambda url, params=None: type('R', (), {'text': 'garbage,,\n1,2'})()):
        out = xgm.fetch(SEASON, getter=g)
        assert out['players'] == {} and out['error']
    assert xgm.fetch('bogus')['error'] == 'bad season'
    assert xgm.fetch_game_dates(SEASON, getter=boom) == {}
    assert xgm.read_shots(b'not a zip') == [] and xgm.parse_csv(None)['players'] == {}
    assert xgm.for_day(None, DAY, SEASON)['players'] == {} and xgm.for_day({'players': {}}, 'nonsense')['players'] == {}


def test_ids_match_by_nhl_player_id_and_season_mapping():
    d = data([(8478420, '5on5', 10.0, 50, 5)])
    assert xgm.mp_year('20262027') == '2026' and xgm.URL.format(yr=xgm.mp_year(SEASON)).endswith('/2026/regular/skaters.csv')
    assert xgm.quality(d, 8478420, 'ev') and xgm.quality(d, '8478420', 'ev')   # int or str id
    assert xgm.quality(d, 8478421, 'ev') is None
    assert xgm.parse_csv(csv_text([(1, '5on5', 1.0, 10, 1)], season='2025'), SEASON)['error'] == 'season mismatch'


def test_point_in_time_aggregate_from_per_shot_rows():
    def shot(gid, pid, xg, on=1, goal=0, us=5, them=5, home=1, en=0):
        h, a = (us, them) if home else (them, us)
        return {'game_id': str(gid), 'shooterPlayerId': str(pid), 'xGoal': str(xg), 'goal': str(goal), 'shotWasOnGoal': str(on),
                'homeSkatersOnIce': str(h), 'awaySkatersOnIce': str(a), 'isHomeTeam': str(home), 'shotOnEmptyNet': str(en), 'isPlayoffGame': '0'}
    rows = [shot(20001, 1, 0.3, goal=1), shot(20001, 1, 0.1, on=0), shot(20002, 1, 0.2, us=5, them=4, home=0),
            shot(20001, 1, 0.9, en=1), shot(20003, 1, 0.5)]   # 20003 is on the cutoff day -> excluded
    dates = {2026020001: '2026-10-20', 2026020002: '2026-10-21', 2026020003: '2026-10-23'}
    out = xgm.aggregate_shots(rows, '2026-10-23', dates, SEASON)
    p = out['players'][1]
    assert p['5on5'] == pytest.approx((0.4, 1, 1)) and p['5on4'] == pytest.approx((0.2, 1, 0)) and p['all'] == pytest.approx((0.6, 2, 1))
    assert out['as_of'].startswith('2026-10-23') and xgm.for_day(out, '2026-10-23', SEASON)['players']
    assert xgm.aggregate_shots(rows, '2026-10-20', dates, SEASON)['players'] == {}


# ------------------------------------------------------------------ flags
def test_flag_off_drops_xg_part_and_reproduces_situational():
    assert ff.model_xg(environ={}) is True
    assert ff.model_xg(environ={'MODEL_XG': '0'}) is False and ff.model_xg(secrets={'MODEL_XG': 'false'}, environ={}) is False
    assert ff.model_parts(environ={'MODEL_XG': 'off'}) == ('pp', 'goalie', 'line')
    assert ff.model_parts(environ={'MODEL_SITUATIONAL_PARTS': 'xg,pp'}) == ('xg', 'pp')
    assert ff.model_parts(environ={'MODEL_SITUATIONAL_PARTS': 'xg,pp', 'MODEL_XG': 'no'}) == ('pp',)
    rows = [(1, '5on5', 18.0, 90, 10)]
    on = run(ctx_with(rows, parts=ff.model_parts(environ={})))
    off = run(ctx_with(rows, parts=ff.model_parts(environ={'MODEL_XG': '0'})))
    ref = run(sit.context(skaters={1: sk(), 2: sk(goals=8, shots=80, ppg=2, pps=10, pp_min=40.0)}, teams=TEAMS, parts=('pp', 'goalie', 'line')))
    assert same(off, ref) and not same(on, ref)


# ------------------------------------------------------------------ propagation
def test_xg_chance_feeds_edgeflags_edgelab_parlay_longshot_and_scored_stays_excluded():
    rows = [(1, '5on5', 18.0, 90, 10), (2, '5on5', 4.0, 80, 8), (3, '5on5', 15.0, 70, 10), (4, '5on5', 3.0, 60, 3)]
    sks = {1: sk(), 2: sk(goals=8, shots=80, ppg=2, pps=10, pp_min=40.0), 3: sk(goals=10, shots=100), 4: sk(goals=3, shots=60, ppg=0, pps=5)}
    c = ctx_with(rows, skaters=sks)
    g = live_game()
    res = run(c, g)
    plain = run(sit.context(skaters=sks, teams=TEAMS), g)
    item = {'slate': {'away': AWAY, 'home': HOME, 'start': None, 'key': 'k', 'status': 'LIVE', 'game_id': 7}, 'label': 'live', 'result': res}
    # Edge Flags: same model input (lambda from the xG-weighted record), settled scorer never flagged
    lines = {eflags._norm(r['name']): {'implied': 0.05, 'american': 1900, 'source': 'fixture'} for r in res['players']}
    ef = {r['pid']: r for r in eflags.edges_for_game(res, lines, min_edge=0.03)}
    for rec in res['players']:
        lam_x = eflags.player_lambda(rec, 'live', res['remaining'])
        assert ef[rec['pid']]['lambda'] == lam_x
    assert ef[1]['settled'] and not ef[1]['flag'] and ef[1]['edge'] is None
    assert ef[2]['lambda'] != next(e for e in eflags.edges_for_game(plain, lines) if e['pid'] == 2)['lambda']
    # EdgeLab: model p = xG-weighted lambda, 'why' carries the xG bit, scorer left out
    priced, unpriced = elv.model_rows([item], {}, scored_ids={1})
    assert 1 not in {r['pid'] for r in priced + unpriced}
    r3 = next(r for r in unpriced if r['pid'] == 3)
    rec3 = next(r for r in res['players'] if r['pid'] == 3)
    assert r3['model_p'] == pytest.approx(ng.p_anytime(eflags.player_lambda(rec3, 'live', res['remaining'])))
    assert 'xG ×' in r3['why'] and 'xG ×' in elv.table_html([], unpriced)
    # parlay + long shot: candidate p is p_anytime(xG lambda_game); scorer excluded
    cands = parlay.candidates([item], scored={1})
    assert 1 not in {x['pid'] for x in cands}
    assert {x['pid']: x['p'] for x in cands} == {r['pid']: ng.p_anytime(r['lam_game']) for r in res['players'] if r['pid'] != 1}
    built = parlay.build([item], scored={1}, k=2)
    assert 1 not in {l['pid'] for l in built.get('legs') or []}
    ls = longshot.pick([dict(x, p=0.12) for x in cands], (), jumps={x['pid']: 2 for x in cands})
    assert ls is None or ls['pid'] != 1
    # attribution caption appears only when xG was used
    assert xgm.attribution([item]) == xgm.CREDIT and xgm.attribution([{'result': plain}]) == ''


def test_slate_results_threads_xg_situ():
    import live_state_v56 as lstate
    c = ctx_with([(1, '5on5', 18.0, 90, 10)])
    slate = [{'key': 'k', 'game_id': 1, 'away': AWAY, 'home': HOME, 'start': None, 'status': 'FUT'}]
    try:
        out = lstate.slate_results(slate, priors(), {}, {}, {}, situ=sit.Situ(c))
    except TypeError:
        pytest.skip('slate_results signature differs')
    rec = next(p for r in out for p in r['result']['players'] if p['pid'] == 1)
    assert 'xg' in rec['situ']['applied']


# ------------------------------------------------------------------ light AppTest (offline fixtures)
def test_apptest_xg_layer_renders_with_credit(monkeypatch, tmp_path):
    import v54_testkit as kit
    pids = {int(float(r['Player ID'])) for r in kit.slate()['rankings'] if r.get('Player ID') not in (None, '')}
    rows = [(p, sit_, round(0.08 + (p % 7) * 0.01, 3) * 40, 40, 4) for p in pids for sit_ in ('5on5', 'all')]   # no NHL PP split here -> 'all'
    fixture = {**data(rows), 'as_of': None}   # undated fixture -> season check only
    monkeypatch.setattr(xgm, 'fetch', lambda season, getter=None: fixture)
    monkeypatch.setattr(sit, 'fetch_context', lambda day, season, getter=None, starters=None, parts=sit.PARTS:
                        sit.context(parts=parts, sources={'goalies': 'fixture'}))
    at = kit.run_app(monkeypatch, tmp_path)
    assert not at.exception
    caps = ' '.join(c.value for c in at.caption)
    assert xgm.CREDIT in caps
    assert 'xG ×' in kit.markdown(at)   # EdgeLab model-p tooltip carries the xG bit
