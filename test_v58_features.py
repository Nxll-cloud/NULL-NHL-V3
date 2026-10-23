"""V5.8 feature tests: TOP PICK / RUNNER-UP (Numbers), Track Record feature flag, scorer badges, CSS layers."""
import json
import re

import pytest

import feature_flags_v58 as flags
import numbers_v58_ui as nv
import scorers_tonight_v58 as sctn
import v55_ui as v5
from v54_testkit import HERE, run_app, markdown

F = HERE / 'test_fixtures_v56'
EXTRA = json.loads((F / 'slate_extra_2026020164.json').read_text())['games']


def _p(pid, name, team, raw):
    return {'player_id': str(pid), 'player': name, 'team': team, 'threat': raw, 'threat_raw': raw, 'tier': 'hot', 'colour': '#fff',
            'values': {}, 'day': [], 'team_matches': [], 'arena_matches': []}


def _tab(at, label):
    return next(t for t in at.tabs if t.label == label)


def _md(block):
    return ' '.join([m.value for m in block.markdown] + [h.value for h in block.get('html')])


# ----------------------------------------------------------------------------------------- TOP PICK / RUNNER-UP
def test_one_top_pick_and_one_runner_up_per_team():
    lists = [[_p(1, 'A One', 'BOS', 40), _p(2, 'B Two', 'BOS', 30), _p(3, 'C Three', 'BOS', 20), _p(4, 'D Four', 'NSH', 50),
              _p(5, 'E Five', 'NSH', 10)]]
    picks = nv.top_picks_per_team(lists)
    assert {t: [p['player'] for p in ps] for t, ps in picks.items()} == {'BOS': ['A One', 'B Two'], 'NSH': ['D Four', 'E Five']}
    ranks = nv.pick_ranks(picks)
    assert sorted(ranks.values()) == [1, 1, 2, 2]


def test_ties_break_on_model_p_then_name():
    lists = [[_p(1, 'Zed', 'BOS', 30), _p(2, 'Amy', 'BOS', 30), _p(3, 'Bob', 'BOS', 30)]]
    by_name = nv.top_picks_per_team(lists)['BOS']
    assert [p['player'] for p in by_name] == ['Amy', 'Bob']
    by_p = nv.top_picks_per_team(lists, model_p={'1': .4, '2': .2, '3': .3})['BOS']
    assert [p['player'] for p in by_p] == ['Zed', 'Bob']


def test_dedupe_across_lists_by_player_id():
    a = [_p(7, 'Same Guy', 'TOR', 20), _p(8, 'Other', 'TOR', 25)]
    b = [_p(7, 'Same Guy', 'TOR', 35)]     # the same player on a second list with a higher threat
    picks = nv.top_picks_per_team([a, b])['TOR']
    assert [p['player_id'] for p in picks] == ['7', '8'] and picks[0]['threat_raw'] == 35
    assert len({p['player_id'] for p in picks}) == len(picks)


def test_single_player_team_has_no_runner_up():
    picks = nv.top_picks_per_team([[_p(1, 'Solo', 'SJS', 10), _p(2, 'X', 'OTT', 5), _p(3, 'Y', 'OTT', 4)]])
    assert len(picks['SJS']) == 1 and len(picks['OTT']) == 2


def test_badges_rows_and_pinning():
    players = [_p(3, 'C', 'BOS', 20), _p(1, 'A', 'BOS', 40), _p(4, 'D', 'NSH', 50)]
    allp = players + [_p(2, 'B', 'BOS', 30)]          # B was cut by the players-per-game limit
    ranks = nv.pick_ranks(nv.top_picks_per_team([allp]))
    shown = nv.pin_board(players, allp, ranks)
    bos = [p['player'] for p in shown if p['team'] == 'BOS']
    assert bos[:2] == ['A', 'B'] and 'C' in bos
    assert [p['player'] for p in nv.pin_board(players, allp, ranks, pin=False)][:3] == ['C', 'A', 'D']   # sort active: highlight only
    r1 = nv.player_row(_p(1, 'A', 'BOS', 40), 1)
    r2 = nv.player_row(_p(2, 'B', 'BOS', 30), 2)
    assert 'class="npr t-hot pk1"' in r1 and '★ TOP PICK' in r1 and 'npk pk1' in r1
    assert 'class="npr t-hot pk2"' in r2 and '☆ RUNNER-UP' in r2 and 'npk pk2' in r2
    assert 'npk' not in nv.player_row(_p(3, 'C', 'BOS', 20), None)


def test_pick_css_rules():
    css = (HERE / 'assets' / 'v58.css').read_text()
    pk1 = re.search(r'\.npk\.pk1\{([^}]*)\}', css).group(1)
    pk2 = re.search(r'\.npk\.pk2\{([^}]*)\}', css).group(1)
    assert 'box-shadow' in pk1 and 'background:linear-gradient' in pk1
    assert 'box-shadow' not in pk2 and 'transparent' in pk2 and 'border:1px solid' in pk2
    assert '.npr.pk1 .npr-name{font-weight:800}' in css and '.npr.pk2 .npr-name{font-weight:600}' in css


# ----------------------------------------------------------------------------------------- Track Record flag
@pytest.mark.parametrize('env,secrets,want', [(None, {}, False), ('1', {}, True), ('off', {'FEATURE_TRACK_RECORD': 'true'}, False),
                                              (None, {'FEATURE_TRACK_RECORD': 'on'}, True), ('junk', {}, False)])
def test_track_flag_resolution(env, secrets, want):
    environ = {} if env is None else {'FEATURE_TRACK_RECORD': env}
    assert flags.show_track_record(secrets, environ) is want


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(scope='module')
def app_off(mp, tmp_path_factory):
    mp.delenv('FEATURE_TRACK_RECORD', raising=False)
    return run_app(mp, tmp_path_factory.mktemp('off'))


def test_track_record_hidden_by_default(app_off):
    at = app_off
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert '📈 Track Record' not in labels
    assert labels[:9] == ['🏠 Home', '🎯 Matchup Center', '⚡ Odds', '📊 Research', '🔮 Numbers', '🧪 EdgeLab', '⏱ Live Next Goal',
                          '🚩 Edge Flags', '📰 Storylines']
    text = markdown(at) + ' '.join(str(c.value) for c in at.caption) + ' '.join(str(i.value) for i in at.info)
    assert 'Track Record' not in text and 'Accuracy summary' not in text


def test_track_record_flag_on(monkeypatch, tmp_path):
    monkeypatch.setenv('FEATURE_TRACK_RECORD', '1')
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    assert '📈 Track Record' in [t.label for t in at.tabs]
    assert 'Accuracy summary' in _md(_tab(at, '📈 Track Record'))


def test_numbers_app_one_pick_and_runner_up_per_team(app_off):
    html = _md(_tab(app_off, '🔮 Numbers'))
    rows = re.findall(r'<li class="npr t-\w+( pk[12])?"[^>]*>.*?</li>', html, flags=re.S)
    assert rows
    per = {}
    for m in re.finditer(r'<li class="npr t-\w+ (pk[12])".*?<small>([A-Z]{3}) ·', html, flags=re.S):
        per.setdefault(m.group(2), []).append(m.group(1))
    assert per and set(per) <= {'NSH', 'BOS', 'NYR', 'TOR', 'SJS', 'OTT'}
    for team, got in per.items():
        assert got.count('pk1') == 1 and got.count('pk2') <= 1, (team, got)
    assert html.count('★ TOP PICK') >= len(per)


# ----------------------------------------------------------------------------------------- scorer badges
def _goal(eid, shooter, team, period=1, secs=100, strength='EV', ptype='REG', goalie=1):
    return {'kind': 'goal', 'eid': eid, 'shooter': shooter, 'team': team, 'period': period, 'secs': secs,
            'strength': strength, 'ptype': ptype, 'goalie': goalie}


def test_scorer_parse_multi_goal_shootout_and_dedupe():
    game = {'game_id': 1, 'away': 'NSH', 'home': 'BOS', 'roster': {8477956: {'name': 'David Pastrnak', 'team': 'BOS'}},
            'events': [_goal(1, 8477956, 'BOS'), _goal(2, 8477956, 'BOS', 2, 600, 'PP'), _goal(2, 8477956, 'BOS', 2, 600, 'PP'),
                       _goal(9, 8477956, 'BOS', 5, 0, ptype='SO')]}
    rec = sctn.from_pbp({'1': game}, '2026-10-22')
    r = rec['players'][8477956]
    assert r['goals'] == 2 and sctn.short(r) == '🚨 2G' and 'PPG' in sctn.tooltip(r)
    assert 'npsc multi' in sctn.badge(r) and 'demo' in sctn.badge(r, demo=True)


def test_scorer_lookup_id_then_unique_name():
    game = {'game_id': 1, 'away': 'NSH', 'home': 'BOS', 'roster': {5: {'name': 'Élias Lindholm', 'team': 'BOS'}},
            'events': [_goal(1, 5, 'BOS')]}
    rec = sctn.from_pbp({'1': game}, '2026-10-22')
    assert sctn.lookup(rec, pid='5.0')['goals'] == 1
    assert sctn.lookup(rec, name='Elias Lindholm')['goals'] == 1
    assert sctn.lookup(rec, pid=6) is None and sctn.lookup(rec, name='Nobody') is None


def test_scorer_badges_in_home_mc_numbers_edgelab(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path, extra_games=EXTRA,
                 pbp_files={'score.json': F / 'score_20261022_live.json', '2026020164.json': F / 'pbp_live_2026020164.json',
                            '2026020154.json': F / 'pbp_2026020154.json'})
    assert not at.exception
    for label in ('🏠 Home', '🎯 Matchup Center', '🔮 Numbers', '🧪 EdgeLab'):
        html = _md(_tab(at, label))
        assert 'class="npsc' in html, label
    assert 'DEMO replay' in markdown(at)   # fixture feeds are labelled DEMO


# ----------------------------------------------------------------------------------------- CSS layers
def test_v58_and_mobile_css_loaded_and_sanitizer_safe():
    css = v5.design_css('dark')
    assert '.npk.pk1' in css and '.v58-el .el-t' in css and '[data-baseweb="tab-list"]' in css
    mob = (HERE / 'assets' / 'mobile.css').read_text()
    assert '<' not in mob and '<' not in (HERE / 'assets' / 'v58.css').read_text()
    body = re.sub(r'/\*.*?\*/', '', mob, flags=re.S).strip()
    depth, top = 0, []
    i = 0
    while i < len(body):        # every top-level rule is an @media block
        if depth == 0 and body[i] not in ' \n\t':
            top.append(body[i:i + 6])
            j = body.index('{', i)
            depth, i = 1, j + 1
            continue
        depth += body[i] == '{'
        depth -= body[i] == '}'
        i += 1
    assert top and all(t == '@media' for t in top), top
    assert 'prefers-reduced-motion' in mob and 'min-height:44px' in mob
