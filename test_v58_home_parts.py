"""V5.8 Home parts (parlay, long shot, order) and Storylines helpers - offline."""
import pytest

import longshot_v58 as ls
import parlay_v58 as parlay
import storylines_v58 as sl
import v55_ui as v5
from v54_testkit import run_app, markdown

BANNED = ('American', 'Implied', 'implied', 'Fair odds', 'fair odds', '+EV', 'Edge %', 'Odds:', 'Price', 'price')


def _c(pid, team, game, p, name=None):
    return {'pid': pid, 'name': name or f'P{pid}', 'team': team, 'opp': 'X', 'home': False, 'game': game, 'game_id': '1',
            'start': None, 'phase': 'pregame', 'p': p, 'p_next': None, 'np_rank': None, 'form': None, 'model_rank': pid}


def test_parlay_one_leg_per_game_and_exact_product():
    cands = [_c(1, 'A', 'g1', .5), _c(2, 'B', 'g1', .49), _c(3, 'C', 'g2', .4), _c(4, 'D', 'g3', .3), _c(5, 'E', 'g4', .2),
             _c(6, 'F', 'g5', .1)]
    legs = parlay.choose(cands, 4, 'game')
    assert [l['pid'] for l in legs] == [1, 3, 4, 5] and len({l['game'] for l in legs}) == 4
    assert parlay.joint([l['p'] for l in legs]) == pytest.approx(.5 * .4 * .3 * .2)
    html = parlay.section_html({'legs': legs, 'joint': .012, 'per': 'game'}, {}, {})
    assert 'Top four-leg parlay' in html and 'Combined model chance' in html and 'independent' in html
    assert not any(b in html for b in BANNED)


def test_parlay_leg_status_and_overall():
    leg = _c(1, 'A', 'g1', .5)
    assert parlay.leg_status(leg, {'players': {1: {}}}) == 'hit'
    assert parlay.leg_status(leg, None, {'g1': 'final'}) == 'lost'
    assert parlay.overall(['hit', 'pending']) == 'live' and parlay.overall(['hit'] * 4) == 'hit'
    assert parlay.overall(['lost', 'hit']) == 'lost'


def test_long_shot_band_excludes_parlay_and_needs_a_signal():
    cands = [_c(i, 'T', f'g{i}', p) for i, p in enumerate([.45, .40, .35, .30, .18, .15, .12, .08, .04], 1)]
    band = ls.in_band(cands)
    assert all(ls.P_FLOOR <= c['p'] <= ls.P_CAP for c in band) and 9 not in {c['pid'] for c in band}
    assert ls.pick(cands) is None                                     # no upside signal -> nobody
    gem = {'5': {'threat': 10, 'day': True, 'arena': False, 'team': False}, '6': {'threat': 90, 'day': True, 'arena': True, 'team': False}}
    best = ls.pick(cands, gem=gem)
    assert best['pid'] == 6
    assert ls.pick(cands, parlay_ids=[6], gem=gem)['pid'] == 5        # a parlay leg is never the long shot
    html = ls.section_html(best)
    assert 'Top long shot candidate' in html and not any(b in html for b in BANNED)
    assert 'No qualifying long shot tonight' in ls.section_html(None)


def test_storyline_helpers():
    assert sl.birthday_age('2000-10-22', '2026-10-22') == 26 and sl.birthday_age('2000-10-21', '2026-10-22') is None
    assert sl.milestone(49, 50) == ('goals', 50, 1) and sl.milestone(10, 98) == ('points', 100, 2) and sl.milestone(10, 20) is None
    st = sl.nhl_stints([{'leagueAbbrev': 'NHL', 'gameTypeId': 2, 'teamName': {'default': 'Boston Bruins'}, 'season': 20232024,
                         'gamesPlayed': 82, 'goals': 30, 'assists': 20, 'points': 50},
                        {'leagueAbbrev': 'AHL', 'gameTypeId': 2, 'teamName': {'default': 'Providence Bruins'}, 'season': 20222023}])
    assert list(st) == ['BOS'] and st['BOS']['gp'] == 82
    assert sl.team_abbr('Utah Hockey Club') == 'UTA'
    assert 500 < sl.haversine_km(sl.ARENAS['BOS'], sl.ARENAS['BUF']) < 700


def test_home_order_and_no_track_strip(monkeypatch, tmp_path):
    monkeypatch.delenv('FEATURE_TRACK_RECORD', raising=False)
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    home = next(t for t in at.tabs if t.label == '🏠 Home')
    html = ' '.join(h.value for h in home.get('html'))
    marks = ['<section class="sec"', '<section class="hero', '<section class="sec npp', 'Leaders', '<section class="sec nls']
    pos = [html.find(m) for m in marks]
    assert all(p >= 0 for p in pos), dict(zip(marks, pos))
    assert pos == sorted(pos), dict(zip(marks, pos))
    assert 'Track Record' not in html and 'class="sec track' not in html
    npp = html[html.find('class="sec npp'):html.find('class="pc gem')]
    assert not any(b in npp for b in BANNED)
