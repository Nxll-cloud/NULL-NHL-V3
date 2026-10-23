"""V5.6 feature tests: real H2H (goalieInNetId), Matchup Center goalie view, edge flags, numbers-by-game,
UI fragments, per-file < 100 KB rule. Pure; no network (fake getters only)."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

import check_repo_size as crs
import edgelab_v55 as el
import edgeflags_v56 as ef
import h2h_v56 as h2h
import live_nextgoal_v56 as ng
import mc_goalies_v56 as mcg
import numboard_v56 as nb
import v56_ui as v56

HERE = Path(__file__).resolve().parent
F = HERE / 'test_fixtures_v56'


# ---------------------------------------------------------------- H2H
def test_extract_pairs_from_real_pbp():
    rec = h2h.extract_pairs(json.loads((F / 'pbp_2026020154.json').read_text()))
    assert rec['away'] == 'NSH' and rec['home'] == 'BOS' and rec['pairs']
    assert all(len(r) == 4 and r[2] in (0, 1) for r in rec['pairs'])
    goals = sum(r[2] for r in rec['pairs'])
    assert goals >= 1 and rec['names']


def test_extract_pairs_skips_empty_net_and_shootout():
    pbp = {'id': 9, 'awayTeam': {'id': 1, 'abbrev': 'A'}, 'homeTeam': {'id': 2, 'abbrev': 'H'}, 'plays': [
        {'typeDescKey': 'goal', 'periodDescriptor': {'periodType': 'REG'}, 'details': {'scoringPlayerId': 5, 'eventOwnerTeamId': 1}},
        {'typeDescKey': 'goal', 'periodDescriptor': {'periodType': 'SO'}, 'details': {'scoringPlayerId': 5, 'goalieInNetId': 7}},
        {'typeDescKey': 'shot-on-goal', 'periodDescriptor': {'periodType': 'REG'}, 'details': {'shootingPlayerId': 5, 'goalieInNetId': 7, 'eventOwnerTeamId': 1}}]}
    assert h2h.extract_pairs(pbp)['pairs'] == [[5, 7, 0, 'A']]


def test_aggregate_and_queries():
    recs = [{'pairs': [[5, 7, 1, 'A'], [5, 7, 0, 'A'], [6, 7, 0, 'A']], 'names': {'5': 'Five'}}, {'pairs': [[5, 7, 1, 'A'], [5, 8, 0, 'A']]}]
    pairs, names = h2h.aggregate(recs)
    assert pairs[(5, 7)] == {'sog': 3, 'goals': 2, 'games': 2} and names[5] == 'Five'
    assert h2h.vs(pairs, 5, None) is None
    t = h2h.goalie_threats(pairs, 7, [{'pid': 5}, {'pid': 9}])
    assert t[0]['h2h']['goals'] == 2 and t[1]['h2h'] is None
    g, basis = h2h.hardest_goalie({(5, 7): {'sog': 4, 'goals': 2, 'games': 2}, (5, 8): {'sog': 5, 'goals': 0, 'games': 2}}, 5, [{'id': 7}, {'id': 8}])
    assert g['id'] == 8 and basis == 'H2H'
    assert h2h.hardest_goalie(pairs, 5, [{'id': 8}]) == (None, None)       # < 3 H2H shots
    fl = h2h.flag_game(pairs, [{'pid': 5, 'opp': 'H', 'name': 'Five', 'rank': 1}, {'pid': 6, 'opp': 'H'}], {'H': {'id': 7, 'name': 'G7'}})
    assert len(fl) == 1 and fl[0]['goals'] == 2 and fl[0]['goalie'] == 'G7'


def test_seasons_and_coverage():
    assert h2h.seasons_since('20262027', 20242025) == [20242025, 20252026, 20262027]
    assert h2h.coverage_label('20262027').startswith('since 2024-25')
    assert '1 meeting scanned' in h2h.coverage_label('20262027', games=1)


def test_meetings_filter():
    sched = {'games': [
        {'id': 1, 'gameType': 2, 'gameState': 'OFF', 'gameDate': '2025-01-01', 'awayTeam': {'abbrev': 'A'}, 'homeTeam': {'abbrev': 'H'}},
        {'id': 2, 'gameType': 1, 'gameState': 'OFF', 'gameDate': '2025-01-02', 'awayTeam': {'abbrev': 'A'}, 'homeTeam': {'abbrev': 'H'}},
        {'id': 3, 'gameType': 2, 'gameState': 'FUT', 'gameDate': '2025-01-03', 'awayTeam': {'abbrev': 'H'}, 'homeTeam': {'abbrev': 'A'}},
        {'id': 4, 'gameType': 2, 'gameState': 'OFF', 'gameDate': '2026-12-01', 'awayTeam': {'abbrev': 'H'}, 'homeTeam': {'abbrev': 'A'}},
        {'id': 5, 'gameType': 2, 'gameState': 'FINAL', 'gameDate': '2025-02-01', 'awayTeam': {'abbrev': 'H'}, 'homeTeam': {'abbrev': 'X'}}]}
    assert [m['game_id'] for m in h2h.meetings([sched, sched], 'A', 'H', '2026-10-22')] == [1]


class _R:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_load_meetings_caches_and_index(tmp_path):
    pbp = json.loads((F / 'pbp_2026020154.json').read_text())
    sched = {'games': [{'id': 2026020154, 'gameType': 2, 'gameState': 'OFF', 'gameDate': '2026-10-22',
                        'awayTeam': {'abbrev': 'NSH'}, 'homeTeam': {'abbrev': 'BOS'}}]}
    calls = []

    def getter(url, timeout=None):
        calls.append(url)
        return _R(pbp if 'play-by-play' in url else sched)

    recs, errs = h2h.load_meetings('NSH', 'BOS', '2026-10-23', '20262027', getter, root=tmp_path)
    assert not errs and len(recs) == 1 and recs[0]['away'] == 'NSH'
    assert (tmp_path / '2026020154.json').exists() and list(tmp_path.glob('meetings_BOS_NSH_2026-10-23.json'))
    n = len(calls)

    def offline(url, timeout=None):
        raise ConnectionError('offline')

    recs2, errs2 = h2h.load_meetings('NSH', 'BOS', '2026-10-23', '20262027', offline, root=tmp_path)
    assert recs2 == recs and not errs2 and len(calls) == n          # served entirely from the local cache


def test_load_meetings_never_raises_offline(tmp_path):
    def offline(url, timeout=None):
        raise ConnectionError('offline')
    recs, errs = h2h.load_meetings('NSH', 'BOS', '2026-10-23', '20262027', offline, root=tmp_path)
    assert recs == [] and errs and not list(tmp_path.glob('meetings_*'))   # incomplete scan is not indexed


def test_cache_prune_cap_keeps_index(tmp_path):
    for i in range(5):
        h2h.cache_put({'game_id': i, 'pairs': [[1, 2, 0, 'A']] * 50}, root=tmp_path, cap=10 ** 9)
    (tmp_path / 'meetings_A_B_2026-10-22.json').write_text('[]')
    size = (tmp_path / '0.json').stat().st_size
    removed = h2h.prune(tmp_path, cap=size * 2)
    assert removed == 3 and (tmp_path / 'meetings_A_B_2026-10-22.json').exists()


# ---------------------------------------------------------------- Matchup Center goalie view
ROWS = [{'Team': 'BOS', 'Goalie': 'Jeremy Swayman', 'Player ID': '8480280', 'GP': 6, 'GS': 6, 'GA': 15, 'SA': 170, 'SV%': 0.912, 'GAA': 2.5},
        {'Team': 'BOS', 'Goalie': 'Backup B', 'Player ID': '1', 'GP': 3, 'GS': 1, 'GA': 4, 'SA': 60, 'SV%': 0.933, 'GAA': 2.1},
        {'Team': 'NSH', 'Goalie': 'Juuse Saros', 'Player ID': '8477424', 'GP': 7, 'GS': 7, 'GA': 20, 'SA': 200, 'SV%': 0.9, 'GAA': 2.9}]


def test_pick_goalie_order():
    pbp_game = {'events': [{'team': 'NSH', 'goalie': 1}], 'roster': {}}
    assert mcg.pick_goalie('BOS', pbp_game, None, ROWS)['name'] == 'Backup B'                      # PBP goalie in net
    conf = {'goalie': 'Jeremy Swayman', 'goalie_id': '8480280', 'status': 'confirmed'}
    g = mcg.pick_goalie('BOS', {'events': []}, conf, ROWS)
    assert g['status'] == 'confirmed' and g['sv'] == '.912' and g['gaa'] == '2.50'
    lead = mcg.pick_goalie('BOS', {'events': []}, {'status': 'unknown'}, ROWS)
    assert lead['name'] == 'Jeremy Swayman' and 'season GS leader' in lead['status']
    assert mcg.pick_goalie('XXX', {}, None, ROWS) is None


def test_game_view_threats_reverse_flags_and_sort():
    slate = {'away': 'NSH', 'home': 'BOS', 'start': '2026-10-22T23:00:00Z'}
    players = [{'pid': 10, 'name': 'N Ten', 'team': 'NSH', 'rank': 1, 'p_next': 0.1}, {'pid': 20, 'name': 'B Twenty', 'team': 'BOS', 'rank': 2, 'p_next': 0.05}]
    data = {'pairs': {(10, 8480280): {'sog': 5, 'goals': 2, 'games': 2}, (10, 1): {'sog': 4, 'goals': 0, 'games': 1}}, 'games': 2}
    v = mcg.game_view(slate, {'players': players}, {'events': []}, {'BOS': {'goalie': 'Jeremy Swayman', 'goalie_id': '8480280', 'status': 'probable'}}, ROWS, data)
    assert [t['pid'] for t in v['threats']['BOS']] == [10] and v['threats']['BOS'][0]['h2h']['goals'] == 2
    assert [t['pid'] for t in v['threats']['NSH']] == [20]
    rv = {r['pid']: r for r in v['reverse']}
    assert rv[10]['goalie']['name'] == 'Backup B' and rv[10]['basis'] == 'H2H'
    assert rv[20]['goalie']['name'] == 'Juuse Saros' and 'season SV%' in rv[20]['basis']
    assert len(v['flags']) == 1 and v['flags'][0]['shooter'] == 'N Ten'
    views = [({'start': 'a'}, {'flags': []}), ({'start': 'b'}, v)]
    assert mcg.sort_games(views, True)[0][1] is v and mcg.sort_games(views, False) == views


# ---------------------------------------------------------------- edge flags
def test_demo_lines_and_opening_lines():
    priors = {1: {'name': 'A. Player', 'gp': 10, 'goals': 5}, 2: {'name': '', 'gp': 0, 'goals': 0}}
    d = ef.demo_lines(priors)
    assert list(d) == ['a player'] and d['a player']['source'] == 'DEMO'
    q = pd.DataFrame([{'player': 'A Player', 'market': 'player_goal_scorer_anytime', 'american_odds': 150, 'updated_at': '2026-10-22T18:00:00Z', 'sportsbook': 'x'},
                      {'player': 'A Player', 'market': 'player_goal_scorer_anytime', 'american_odds': 120, 'updated_at': '2026-10-22T20:00:00Z', 'sportsbook': 'x'},
                      {'player': 'A Player', 'market': 'h2h', 'american_odds': -200, 'updated_at': '2026-10-22T10:00:00Z', 'sportsbook': 'x'}])
    o = ef.opening_lines(q)
    assert o['a player']['implied'] == pytest.approx(el.american_to_implied(150))   # earliest anytime quote
    store = ef.remember_openers({}, o)
    ef.remember_openers(store, {'a player': {'implied': 0.9}})
    assert store['a player']['implied'] == pytest.approx(el.american_to_implied(150))
    assert ef.opening_lines(pd.DataFrame()) == {}


def test_edges_math_and_settled():
    game = ng.pregame_game(1, 'AAA', 'HHH')
    priors = {11: {'name': 'A1 X', 'team': 'AAA', 'pos': 'C', 'gp': 10, 'goals': 5, 'sog': 30, 'form': 99, 'source': 'season'}}
    res = ng.model(game, priors)
    ng.rerank(res['players'], None)
    lines = {'a1 x': {'implied': 0.2, 'american': 400, 'source': 'DEMO'}}
    rows = ef.edges_for_game(res, lines, min_edge=0.03)
    r = rows[0]
    assert r['model_p'] == pytest.approx(1 - __import__('math').exp(-r['lambda']))
    assert r['edge'] == pytest.approx(r['model_p'] - 0.2) and r['flag'] == (r['edge'] >= 0.03)
    assert ef.game_flag(rows)['top'] is r
    live = dict(res, phase='live', remaining=30.0, players=[dict(res['players'][0], goals=1, rate=0.01)])
    lr = ef.edges_for_game(live, lines)[0]
    assert lr['settled'] and lr['edge'] is None and not lr['flag']
    fin = ef.edges_for_game(dict(res, phase='final'), lines)[0]
    assert fin['model_p'] is None and not fin['flag']


def test_model_p_ignores_form():
    game = ng.pregame_game(1, 'AAA', 'HHH')
    lo = {11: {'name': 'P', 'team': 'AAA', 'pos': 'C', 'gp': 10, 'goals': 5, 'sog': 30, 'form': 0, 'source': 'season'}}
    hi = {11: dict(lo[11], form=100)}
    a = ef.edges_for_game(ng.model(game, lo), {})[0]['model_p']
    b = ef.edges_for_game(ng.model(game, hi), {})[0]['model_p']
    assert a == b


# ---------------------------------------------------------------- numbers by game
def _t(player, day=(), arena=(), team=(), form=50):
    return {'player': player, 'day': list(day), 'arena_matches': list(arena), 'team_matches': list(team), 'matches': len(day) + len(arena) + len(team), 'form': form}


def test_threat_score_formula_and_tiers():
    assert nb.RAW_MAX == 18
    t = _t('x', day=['ENG'], arena=['RED'], team=['REV'])
    assert nb.threat_raw(t) == 6 and nb.threat_score(t) == 33 and nb.tier(6)[0] == 'blaze'
    assert [nb.tier(r)[0] for r in (5, 4, 3, 2, 1, 0)] == ['hot', 'hot', 'warm', 'warm', 'mild', 'cool']
    assert nb.threat_score(_t('y', day=[1, 2, 3], arena=[1, 2, 3], team=[1, 2, 3])) == 100


def test_game_board_sort_badge_arena():
    b = nb.game_board({'arena_values': {'ordinal_root': 7}}, [_t('a', team=['ENG']), _t('b')], [_t('c', arena=['ENG'], form=10), _t('d', arena=['ENG'], form=90)], limit=3)
    assert [p['player'] for p in b['players']] == ['d', 'c', 'a'] and len(b['all_players']) == 4
    assert b['badge'] == 3 and b['arena_hit'] and b['arena_players'] == ['d', 'c'] and b['arena_root'] == 7
    assert nb.game_board({'arena_values': None}, [], [])['arena_root'] is None


def test_existing_numerology_outputs_unchanged():
    import player_targets_v49 as pt
    src = (HERE / 'player_targets_v49.py').read_text()
    assert 'numboard' not in src and callable(pt.target_rows)    # V5.6 only reads the V4.9 rows


# ---------------------------------------------------------------- UI fragments
SAN = re.compile(r'<style[^>]*>(.*?)</style>', re.S)


def test_v56_css_sanitizer_safe_and_small():
    css = (HERE / 'assets' / 'v56.css').read_text()
    assert not re.search(r'<[A-Za-z/!]', css) and len(css.encode()) < 100 * 1024
    assert '@media' in css


def test_nextgoal_panel_and_badges():
    res = ng.model(ng.pregame_game(1, 'AAA', 'HHH'), {11: {'name': 'A <b>', 'team': 'AAA', 'pos': 'C', 'gp': 1, 'goals': 1, 'sog': 3, 'form': None, 'source': 'season'}})
    ng.rerank(res['players'], None)
    h = v56.nextgoal_panel(res, '20262027', 'Pregame', None, demo=True)
    assert 'ngp-wrap' in h and 'DEMO' in h and 'A &lt;b&gt;' in h and '<svg' not in h
    assert '▲2' in v56._arrow(2) and 'up' in v56._arrow(2) and '▼' in v56._arrow(-1) and v56._arrow(None)


def test_edge_card_and_flag_render():
    flag = {'top': None, 'flagged': False, 'other_flags': []}
    assert 'no edge' in v56.edge_card({'away': 'AAA', 'home': 'HHH'}, flag, [], '20262027', 'DEMO')
    assert v56.h2h_flag([], 'A @ H') == '' or 'h2hf' in v56.h2h_flag([], 'A @ H')


# ---------------------------------------------------------------- per-file < 100 KB
def test_every_repo_file_under_100kb():
    res = crs.check(HERE, max_file_kb=100)
    assert res['ok'] and not res['over_kb'], res['over_kb']


def test_max_file_kb_rule(tmp_path):
    (tmp_path / 'small.txt').write_bytes(b'x' * 1000)
    (tmp_path / 'big.bin').write_bytes(b'x' * (100 * 1024))
    res = crs.check(tmp_path, max_file_kb=100, use_gitignore=False)
    assert not res['ok'] and [Path(p).name for p, _ in res['over_kb']] == ['big.bin']
    assert crs.check(tmp_path, max_file_kb=0, use_gitignore=False)['ok']
    assert crs.main([str(tmp_path), '--no-gitignore']) == 1 and crs.MAX_FILE_KB == 100


def test_ci_and_hook_enforce_per_file_limit():
    for p in ('.github/workflows/tests.yml', '.github/workflows/precompute.yml', 'tools/pre-commit.sample'):
        assert '--max-file-kb 100' in (HERE / p).read_text(), p


def test_tabs_split_and_registered():
    import tabs
    assert tabs.TABS[-2:] == ('nextgoal', 'edgeflags') and tabs.TABS[0] == 'live'
    for name in tabs.TABS:
        assert (HERE / 'tabs' / f'{name}.py').exists()
    assert 'np-gk-grid' in (HERE / 'tabs' / 'matchup.py').read_text() and 'np-gk-grid' not in (HERE / 'tabs' / 'research.py').read_text()


def test_finished_game_threats_use_pregame_prior_and_phase_sort():
    priors = {11: {'name': 'A1 X', 'team': 'AAA', 'pos': 'C', 'gp': 10, 'goals': 5, 'sog': 30, 'form': None, 'source': 'season'},
              21: {'name': 'H1 Y', 'team': 'HHH', 'pos': 'C', 'gp': 10, 'goals': 2, 'sog': 20, 'form': None, 'source': 'season'}}
    game = ng.pregame_game(7, 'AAA', 'HHH')
    final = {'phase': 'final', 'players': [dict(p, p_next=0.0) for p in ng.model(game, priors)['players']]}
    res, basis = mcg.threat_result(final, game, priors)
    assert basis == 'pregame prior (game over)' and all(p['p_next'] > 0 for p in res['players'])
    v = mcg.game_view({'away': 'AAA', 'home': 'HHH'}, final, {'events': []}, {}, [], None, priors=priors)
    assert v['phase'] == 'final' and v['basis'].startswith('pregame prior') and v['threats']['HHH'][0]['p_next'] > 0
    views = [({'k': 1}, {'flags': [], 'phase': 'final'}), ({'k': 2}, {'flags': [], 'phase': 'live'}), ({'k': 3}, {'flags': [], 'phase': 'pregame'})]
    assert [g['k'] for g, _ in mcg.sort_games(views, False)] == [2, 3, 1]


def test_live_strip_idle_labels():
    items = [{'away': 'AAA', 'home': 'HHH', 'phase': 'final', 'label': 'Final', 'away_score': 1, 'home_score': 2, 'leader': None},
             {'away': 'AAA', 'home': 'HHH', 'phase': 'shootout', 'label': 'SO', 'away_score': 2, 'home_score': 2, 'leader': None}]
    h = v56.live_strip(items)
    assert 'final · no next goal' in h and 'shootout · not modelled' in h and 'model pending' not in h


def test_shootout_and_final_are_settled_with_outcome():
    game = ng.pregame_game(1, 'AAA', 'HHH')
    priors = {11: {'name': 'A1 X', 'team': 'AAA', 'pos': 'C', 'gp': 10, 'goals': 5, 'sog': 30, 'form': None, 'source': 'season'}}
    res = ng.model(game, priors)
    lines = {'a1 x': {'implied': 0.2, 'american': 400, 'source': 'DEMO'}}
    for ph in ('shootout', 'final'):
        r = ef.edges_for_game(dict(res, phase=ph, players=[dict(res['players'][0], goals=1)]), lines)[0]
        assert r['model_p'] is None and r['settled'] and r['outcome'] is True and not r['flag']
        html = v56.edge_card({'away': 'AAA', 'home': 'HHH'}, ef.game_flag([r]), [r], '20262027', 'Final')
        assert 'game over · scored' in html
    assert 'FINAL FINAL' not in v56.state_badge('final', 'Final') and 'FINAL/OT' in v56.state_badge('final', 'Final/OT')
