"""V5.9 goalie weak-spot identifier (goalie_weak_v59): marker on a real gap, hidden on small samples, no-data fallback,
goalie = the same listed starter the situational model / rankings label use. Offline (fake getter, tmp caches)."""
from datetime import datetime, timezone

import pytest

import feature_flags_v58 as flags
import goalie_weak_v59 as gw
import h2h_v56 as h2h
import situational_v58 as sit
import v55_ui as v5

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
KNIGHT = {'id': 8481519, 'name': 'Spencer Knight', 'status': 'probable'}
ROWS = [{'Team': 'CHI', 'Goalie': 'Spencer Knight', 'Player ID': '8481519', 'SA': 500, 'Saves': 455, 'Position': 'G'},
        {'Team': 'CHI', 'Goalie': 'Arvid Soderblom', 'Player ID': '8480000', 'SA': 300, 'Saves': 265, 'Position': 'G'}]


class Resp:
    def __init__(self, payload, code=200):
        self.payload, self.code = payload, code

    def raise_for_status(self):
        if self.code >= 400:
            raise RuntimeError(self.code)

    def json(self):
        return self.payload


def _pbp(gid, shots):
    """shots: [(shooter, goalie, is_goal)] by MTL (team id 8) on CHI (id 16)."""
    plays = [{'typeDescKey': 'goal' if g else 'shot-on-goal', 'periodDescriptor': {'periodType': 'REG'},
              'details': {('scoringPlayerId' if g else 'shootingPlayerId'): s, 'goalieInNetId': gl, 'eventOwnerTeamId': 8}}
             for s, gl, g in shots]
    plays.append({'typeDescKey': 'goal', 'periodDescriptor': {'periodType': 'REG'},   # empty net: excluded
                  'details': {'scoringPlayerId': 1, 'eventOwnerTeamId': 8}})
    return {'id': gid, 'gameDate': '2025-01-03', 'awayTeam': {'id': 8, 'abbrev': 'MTL'}, 'homeTeam': {'id': 16, 'abbrev': 'CHI'},
            'plays': plays, 'rosterSpots': []}


def _getter(logs, pbps, calls=None):
    def get(url, timeout=None):
        if calls is not None:
            calls.append(url)
        if '/game-log/' in url:
            season, gt = url.rsplit('/', 2)[-2:]
            return Resp({'gameLog': logs.get((int(season), int(gt)), [])})
        if 'play-by-play' in url:
            return Resp(pbps[int(url.split('/')[-2])])
        raise AssertionError(url)
    return get


def _log(gid, date, opp, sa, ga):
    return {'gameId': gid, 'gameDate': date, 'teamAbbrev': 'CHI', 'opponentAbbrev': opp, 'shotsAgainst': sa, 'goalsAgainst': ga}


@pytest.fixture
def caches(tmp_path, monkeypatch):
    monkeypatch.setattr(h2h, 'CACHE_DIR', tmp_path / 'h2h')
    monkeypatch.setattr(gw, 'CACHE_DIR', tmp_path / 'gw')
    return tmp_path


def test_marker_shown_on_real_gap_and_hidden_on_small_sample(caches):
    shots = [(11, 8481519, 1)] * 3 + [(11, 8481519, 0)] * 11 + [(22, 8481519, 1), (22, 8481519, 0)] + [(33, 8480000, 1)] * 5
    logs = {(20242025, 2): [_log(2024020616, '2025-01-03', 'MTL', 30, 4), _log(2024020001, '2024-10-10', 'BOS', 30, 2)],
            (20262027, 2): [_log(2026020999, '2026-10-30', 'MTL', 30, 9)]}   # after the slate day: ignored
    data = gw.load(8481519, 'MTL', '2026-10-23', 20262027, _getter(logs, {2024020616: _pbp(2024020616, shots)}))
    assert data['split']['gp'] == 1 and data['split']['sa'] == 30 and data['pbp_games'] == 1 and not data['errors']
    assert data['shooters'][11] == {'sog': 14, 'goals': 3, 'games': 1}
    assert 33 not in data['shooters'] and 1 not in data['shooters']   # other goalie's shots and the empty-net goal excluded
    rows, n = gw.annotate([{'player_id': '11'}, {'player_id': 22.0}, {'player_id': None}], data, KNIGHT)
    assert n == 1 and rows[0]['goalie_weak']['goals'] == 3 and rows[0]['goalie_weak']['ratio'] >= gw.PLAYER_RATIO
    assert rows[1]['goalie_weak'] is None and rows[2]['goalie_weak'] is None   # 1 G on 2 SOG: tiny sample, no marker
    tag = gw.row_tag(rows[0]['goalie_weak'])
    assert 'class="gwk"' in tag and '<b>Knight</b> <b>· 3 G / 14 SOG</b>' in tag and 'since 2021-22' in tag and 'not in the model' in tag
    assert gw.team_marker(data['split'], KNIGHT, 'MTL') is None          # 30 SA vs MTL < MIN_SA


def test_shrinkage_thresholds():
    assert gw.player_marker({'sog': 5, 'goals': 3, 'games': 2}, KNIGHT) is None      # under MIN_SOG
    assert gw.player_marker({'sog': 40, 'goals': 1, 'games': 9}, KNIGHT) is None     # under MIN_GOALS
    assert gw.player_marker({'sog': 30, 'goals': 3, 'games': 9}, KNIGHT) is None     # 10%: no gap after shrinkage
    assert gw.player_marker({'sog': 21, 'goals': 5, 'games': 9}, KNIGHT)['ratio'] > 1.6
    split = {'sa': 600, 'ga': 75, 'gp': 20, 'sa_all': 5000, 'ga_all': 450}
    m = gw.team_marker(split, KNIGHT, 'MTL')
    assert m and m['sv_vs'] == 0.875 and m['sv_all'] == 0.91 and 'class="gwk team"' in gw.team_chip(m) and '.875 SV% vs MTL</b>' in gw.team_chip(m)
    assert gw.team_marker(dict(split, ga=58), KNIGHT, 'MTL') is None                # small gap
    assert gw.team_marker(dict(split, sa=100, ga=20), KNIGHT, 'MTL') is None        # under MIN_SA


def test_no_data_and_offline_fallback(caches):
    def down(url, timeout=None):
        raise ConnectionError('offline')
    data = gw.load(8481519, 'MTL', '2026-10-23', 20262027, down)
    assert data['errors'] and data['shooters'] == {} and data['split']['sa'] == 0
    rows, n = gw.annotate([{'player_id': '11'}], data, KNIGHT)
    assert n == 0 and rows[0]['goalie_weak'] is None and gw.row_tag(None) == '' and gw.team_chip(None) == ''
    assert gw.starter_goalie({'status': 'unknown', 'goalie': None}, ROWS) is None
    assert gw.starter_goalie({'status': 'probable', 'goalie': 'Nobody Known', 'team': 'CHI'}, ROWS) is None   # no NHL id -> nothing


def test_cache_reused_offline(caches):
    calls = []
    logs = {(20242025, 2): [_log(2024020616, '2025-01-03', 'MTL', 30, 4)]}
    get = _getter(logs, {2024020616: _pbp(2024020616, [(11, 8481519, 1)])}, calls)
    first = gw.load(8481519, 'MTL', '2026-10-23', 20262027, get)
    n = len(calls)
    def down(url, timeout=None):
        raise ConnectionError('offline')
    again = gw.load(8481519, 'MTL', '2026-10-23', 20262027, down)
    assert n > 0 and again['shooters'] == first['shooters'] and again['split'] == first['split'] and not again['errors']


def test_goalie_matches_probable_starter_used_by_model():
    starters = {'1': {'MTL': {'team': 'MTL', 'goalie': 'Jakub Dobes', 'status': 'probable'},
                      'CHI': {'team': 'CHI', 'goalie': 'Spencer Knight', 'status': 'probable', 'goalie_id': None}}}
    st_model = sit.starter_for(sit.context(goalies=ROWS, starters=starters), 'MTL', 'CHI')
    g = gw.starter_goalie(starters['1']['CHI'], ROWS)
    _, model_name, _ = sit._goalie_faced(sit.context(goalies=ROWS, starters=starters), 'MTL', 'CHI')
    assert st_model['goalie'] == 'Spencer Knight' and g == KNIGHT and model_name == g['name']
    assert sit.starting_goalie_label(st_model) == 'Spencer Knight (Probable)'
    # Unlisted ('unknown') starter: the model falls back to the team average and the identifier shows nothing.
    assert gw.starter_goalie({'team': 'CHI', 'goalie': 'Spencer Knight', 'status': 'unknown'}, ROWS) is None


def _state():
    fg = {'key': '1', 'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T00:00:00Z', 'game_id': '1', 'venue': 'United Center'}
    tgt = lambda pid, name, team: {'player': name, 'player_id': pid, 'team': team, 'form_pct': 50, 'form_label': '50%', 'stat_rank': 3,
                                   'matches': 0, 'badges': [], 'jersey': 22, 'log': [], 'position': 'R'}
    return {'season': '20262027', 'featured': fg, 'weak_side': None, 'games': [fg],
            'targets': {'MTL': [tgt('11', 'Cole Caufield', 'MTL'), tgt('22', 'Nick Suzuki', 'MTL')], 'CHI': [tgt('33', 'Connor Bedard', 'CHI')]},
            'goalies': {'CHI': {'starter': {'team': 'CHI', 'goalie': 'Spencer Knight', 'status': 'probable'}},
                        'MTL': {'starter': {'team': 'MTL', 'goalie': 'Jakub Dobes', 'status': 'unknown'}}}}


def test_home_markers_render_on_matchup_rows():
    state, asked = _state(), []
    def loader(gid, team):
        asked.append((gid, team))
        return {'shooters': {11: {'sog': 14, 'goals': 3, 'games': 4}, 22: {'sog': 8, 'goals': 1, 'games': 4}},
                'split': {'sa': 118, 'ga': 13, 'gp': 4, 'sa_all': 4320, 'ga_all': 423}, 'window': '2021-22', 'errors': []}
    stat = gw.home_markers(state, ROWS, loader)
    assert asked == [(8481519, 'MTL')]                         # only the listed starter; MTL's 'unknown' starter -> no lookup
    assert stat['marked'] == 1 and stat['team'] == 0 and stat['checked'] == 3
    html = v5.matchup_section(state)
    assert html.count('class="gwk"') == 1 and 'vs G</i> <b>Knight</b> <b>· 3 G / 14 SOG</b>' in html and html.count('class="gwr"') == 1 and 'class="gwk-l"' in html
    assert html.index('Cole Caufield') < html.index('class="gwk"') < html.index('Nick Suzuki')


def test_home_markers_loader_failure_and_flag():
    state = _state()
    def boom(gid, team):
        raise ConnectionError('offline')
    stat = gw.home_markers(state, ROWS, boom)
    assert stat['marked'] == 0 and stat['errors'] and 'gwk' not in v5.matchup_section(state)
    assert 'gwk' not in v5.matchup_section(_state())          # never annotated (flag off) -> nothing rendered
    assert flags.show_goalie_weak(environ={}) is True and flags.show_goalie_weak(environ={'FEATURE_GOALIE_WEAK': '0'}) is False
    assert flags.show_goalie_weak(secrets={'FEATURE_GOALIE_WEAK': 'false'}, environ={}) is False
