"""V5.9 goalie weakness by shooter position (goalie_pos_v59): fixture play-by-play counting (empty net / shootout
excluded), shrinkage + thresholds, no-data path, cache, Home render (hero duel + goalie cards) and flag. Offline."""
from datetime import datetime, timezone

import pytest

import feature_flags_v58 as flags
import goalie_pos_v59 as gp
import v55_ui as v5

G = 8481519                      # goalie in net
NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
POSN = {11: 'C', 12: 'L', 13: 'R', 14: 'D', 15: 'G'}


class Resp:
    def __init__(self, payload, code=200):
        self.payload, self.code = payload, code

    def raise_for_status(self):
        if self.code >= 400:
            raise RuntimeError(self.code)

    def json(self):
        return self.payload


def _pbp(gid, shots, state='OFF'):
    """shots: [(shooter, goalie, is_goal, periodType)]."""
    plays = [{'typeDescKey': 'goal' if g else 'shot-on-goal', 'periodDescriptor': {'periodType': pt},
              'details': {('scoringPlayerId' if g else 'shootingPlayerId'): s, 'goalieInNetId': gl}} for s, gl, g, pt in shots]
    plays.append({'typeDescKey': 'goal', 'periodDescriptor': {'periodType': 'REG'}, 'details': {'scoringPlayerId': 14}})  # empty net
    plays.append({'typeDescKey': 'missed-shot', 'periodDescriptor': {'periodType': 'REG'}, 'details': {'shootingPlayerId': 11, 'goalieInNetId': G}})
    return {'id': gid, 'gameState': state, 'plays': plays,
            'rosterSpots': [{'playerId': k, 'positionCode': v, 'teamId': 8} for k, v in POSN.items()]}


def test_extract_counts_by_position_excluding_empty_net_and_shootout():
    rec = gp.extract(_pbp(1, [(11, G, 1, 'REG'), (11, G, 0, 'REG'), (12, G, 0, 'OT'), (14, G, 1, 'REG'), (13, G, 1, 'SO'),
                              (13, 999, 0, 'REG'), (77, G, 1, 'REG')]))
    assert rec['g'][str(G)] == {'C': [2, 1], 'L': [1, 0], 'D': [1, 1]}       # SO, empty net, missed, unknown shooter out
    assert rec['g']['999'] == {'R': [1, 0]} and rec['state'] == 'OFF'
    assert gp.split([rec, rec], G)['C'] == {'shots': 4, 'goals': 2} and gp.split([rec], G)['R'] == {'shots': 0, 'goals': 0}


def _data(c=(400, 48), l=(200, 25), r=(200, 25), d=(300, 18)):
    return {'split': {'C': {'shots': c[0], 'goals': c[1]}, 'L': {'shots': l[0], 'goals': l[1]}, 'R': {'shots': r[0], 'goals': r[1]},
                      'D': {'shots': d[0], 'goals': d[1]}}, 'games': 40, 'window': '2025-26 to 2026-27'}


def test_weak_vs_d_with_shrinkage_and_thresholds():
    m = gp.marker(_data(d=(300, 36)))                          # 12% vs D, league 5.9%
    lg = gp.league_rate('D')
    assert m['weak'] == 'D' and m['ratio'] == pytest.approx((36 + gp.K * lg) / (300 + gp.K) / lg)
    assert 1.15 <= m['ratio'] < 36 / 300 / lg                   # shrunk toward league
    html = gp.chip(m, 'Spencer Knight')
    assert 'WEAK</i> vs D · 1.' in html and 'most G: C' in html and 'class="gpos weak"' in html
    assert 'D: 36 G / 300 SOG' in html and 'league 0.941' in html and '2025-26 to 2026-27' in html and 'empty net' in html


def test_small_sample_and_below_ratio_show_no_clear_split():
    m = gp.marker(_data(d=(90, 20)))                            # huge rate but < MIN_SHOTS vs D
    assert m['weak'] is None and 'no clear split' in gp.chip(m)
    m = gp.marker(_data())                                      # league-like everywhere
    assert m['weak'] is None and m['most'] == 'C' and m['most_share'] == pytest.approx(48 / 116)


def test_generally_bad_goalie_not_tagged_by_position():
    m = gp.marker(_data(c=(400, 72), l=(200, 37), r=(200, 37), d=(300, 27)))   # ~1.5x league vs everyone
    assert m['overall'] > 1.4 and all(m['rows'][p]['ratio'] >= 1.15 for p in 'CLR') and m['weak'] is None


def test_most_g_needs_enough_goals_and_no_data_path():
    m = gp.marker(_data(c=(60, 6), l=(30, 3), r=(20, 2), d=(40, 2)))
    assert m['most'] is None and m['weak'] is None and gp.chip(m) == ''        # too little to say anything
    assert gp.marker({'split': {}}) is None and gp.marker(None) is None and gp.chip(None) == ''


def _getter(logs, pbps, calls):
    def get(url, timeout=None):
        calls.append(url)
        if '/game-log/' in url:
            season, gt = url.rsplit('/', 2)[-2:]
            return Resp({'gameLog': logs.get((int(season), int(gt)), [])})
        if 'play-by-play' in url:
            return Resp(pbps[int(url.split('/')[-2])])
        raise AssertionError(url)
    return get


def test_load_window_cache_and_offline(tmp_path):
    log = lambda gid, date: {'gameId': gid, 'gameDate': date, 'teamAbbrev': 'CHI', 'opponentAbbrev': 'MTL', 'shotsAgainst': 30, 'goalsAgainst': 3}
    logs = {(20242025, 2): [log(2024020001, '2025-01-03')], (20252026, 2): [log(2025020001, '2025-11-03')],
            (20262027, 2): [log(2026020001, '2026-10-10'), log(2026020099, '2026-10-30')]}
    pbps = {2025020001: _pbp(2025020001, [(11, G, 1, 'REG')] * 3), 2026020001: _pbp(2026020001, [(14, G, 0, 'REG')] * 5)}
    calls = []
    d = gp.load(G, '2026-10-24', 20262027, _getter(logs, pbps, calls), root=tmp_path / 'p', gweak_root=tmp_path / 'w')
    assert d['window'] == '2025-26 to 2026-27' and d['games'] == 2 and not d['errors']     # 2024-25 + future game out
    assert d['split']['C'] == {'shots': 3, 'goals': 3} and d['split']['D'] == {'shots': 5, 'goals': 0}
    assert not any('2024020001' in u for u in calls)
    def offline(url, timeout=None):
        raise ConnectionError('offline')
    again = gp.load(G, '2026-10-24', 20262027, offline, root=tmp_path / 'p', gweak_root=tmp_path / 'w')
    assert again['split'] == d['split']                                                   # disk caches reused
    cold = gp.load(G, '2026-10-24', 20262027, offline, root=tmp_path / 'x', gweak_root=tmp_path / 'y')
    assert cold['games'] == 0 and cold['errors'] and gp.marker(cold) is None


def _state():
    fg = {'key': '1', 'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T00:00:00Z', 'game_id': '1', 'venue': 'United Center'}
    st = lambda name, pid: {'Goalie': name, 'Player ID': pid, 'GAA': 2.8, 'SV%': .905, 'GP': 10, 'GA': 28, 'Team': 'CHI'}
    return {'season': '20262027', 'day': '2026-10-23', 'featured': fg, 'games': [fg], 'targets': {'MTL': [], 'CHI': []},
            'goalies': {'CHI': {'starter': {'team': 'CHI', 'goalie': 'Spencer Knight', 'status': 'probable'},
                                'starter_label': 'Probable starter', 'starter_stats': st('Spencer Knight', str(G)),
                                'leakiest': st('Arvid Soderblom', '8480000')},
                        'MTL': {'starter': {'team': 'MTL', 'goalie': 'Jakub Dobes', 'status': 'unknown'}}}}


def test_home_marks_render_on_duel_and_goalie_cards():
    state, asked = _state(), []
    def loader(gid):
        asked.append(gid)
        return _data(d=(300, 36)) if gid == G else _data()
    stat = gp.home_marks(state, loader)
    assert sorted(asked) == [8480000, G] and stat['shown'] == 2 and not stat['errors']
    hero = v5.hero(state, NOW)
    assert hero.count('class="gpos weak"') == 1 and 'WEAK</i> vs D' in hero
    assert hero.index('Spencer Knight') < hero.index('class="gpos weak"')
    starter = v5.goalie_card('20262027', 'CHI', state['goalies']['CHI'], 'starter')
    leaky = v5.goalie_card('20262027', 'CHI', state['goalies']['CHI'], 'leaky')
    assert 'WEAK</i> vs D' in starter and 'no clear split' in leaky and 'WEAK' not in leaky
    assert 'gpos' not in v5.goalie_card('20262027', 'MTL', state['goalies']['MTL'], 'starter')


def test_home_marks_loader_failure_never_breaks_and_flag():
    state = _state()
    def boom(gid):
        raise ConnectionError('offline')
    stat = gp.home_marks(state, boom)
    assert stat['shown'] == 0 and stat['errors'] and 'gpos' not in v5.hero(state, NOW)
    assert 'gpos' not in v5.hero(_state(), NOW)                # never annotated (flag off) -> nothing rendered
    assert gp.row_chip(None, None) == '' and gp.row_chip({'pos_marks': 'bad'}, {'Player ID': 1}) == ''
    assert flags.show_goalie_pos(environ={}) is True and flags.show_goalie_pos(environ={'FEATURE_GOALIE_POS': '0'}) is False
    assert flags.show_goalie_pos(secrets={'FEATURE_GOALIE_POS': 'false'}, environ={}) is False


def test_league_baseline_is_documented_real_counts():
    assert sum(s for s, _ in gp.LEAGUE.values()) == 72544 and sum(g for _, g in gp.LEAGUE.values()) == 7578
    assert gp.league_rate('D') < gp.league_rate('C') < gp.league_rate('R')
