"""V5.8 EdgeLab (read-only): shared next-goal model p vs live anytime-goal prices."""
import math

import pandas as pd
import pytest

import edgeflags_v56 as eflags
import edgelab_v55 as el
import edgelab_v58 as elv
import live_nextgoal_v56 as lm
from v54_testkit import run_app

AT = 'player_goal_scorer_anytime'


def q(player, odds, book, t, market=AT):
    return {'player': player, 'market': market, 'american_odds': odds, 'sportsbook': book, 'updated_at': t, 'selection': 'Yes'}


def rec(pid, name, team, lam=0.3, rate=0.0, goals=0, rank=1):
    return {'pid': pid, 'name': name, 'team': team, 'lam_game': lam, 'rate': rate, 'goals': goals, 'rank': rank, 'delta': 0}


def res(players, phase='pregame', remaining=60.0, away='AAA', home='BBB'):
    return {'slate': {'away': away, 'home': home, 'start': '2026-10-22T23:00:00Z'}, 'label': phase,
            'result': {'phase': phase, 'remaining': remaining, 'players': players}}


def test_live_price_uses_latest_quote_per_book_and_averages():
    f = pd.DataFrame([q('A Player', 200, 'DK', '2026-10-22T20:00:00Z'), q('A Player', 150, 'DK', '2026-10-22T22:00:00Z'),
                      q('A Player', 120, 'FD', '2026-10-22T21:00:00Z'), q('A Player', -500, 'FD', '2026-10-22T19:00:00Z'),
                      q('A Player', 900, 'DK', '2026-10-22T23:00:00Z', market='player_points')])
    p = elv.live_prices(f)['a player']
    assert p['books'] == 2 and p['book_names'] == ['DK', 'FD']
    assert p['implied'] == pytest.approx((el.american_to_implied(150) + el.american_to_implied(120)) / 2)
    assert p['at'].startswith('2026-10-22T22:00')
    # opposite of Edge Flags, which keeps the earliest quote
    assert eflags.opening_lines(f)['a player']['implied'] != pytest.approx(p['implied'])
    assert elv.live_prices(None) == {} and elv.live_prices(pd.DataFrame()) == {}
    assert elv.live_prices(pd.DataFrame([q('Bad', 20, 'DK', '2026-10-22T20:00:00Z')])) == {}


def test_model_p_is_the_edge_flags_computation_pregame_and_live():
    pre = res([rec(1, 'A Player', 'AAA', lam=0.4)])
    live = res([rec(2, 'B Player', 'BBB', lam=0.4, rate=0.01)], phase='live', remaining=25.0)
    prices = {'a player': {'implied': 0.25, 'american': 300, 'books': 2, 'book_names': ['DK', 'FD'], 'at': None, 'source': 'live'}}
    priced, unpriced = elv.model_rows([pre, live], prices)
    assert priced[0]['model_p'] == pytest.approx(lm.p_anytime(eflags.player_lambda(pre['result']['players'][0], 'pregame', 60)))
    assert priced[0]['model_p'] == pytest.approx(1 - math.exp(-0.4))
    assert priced[0]['edge'] == pytest.approx(1 - math.exp(-0.4) - 0.25)
    assert unpriced[0]['model_p'] == pytest.approx(1 - math.exp(-0.25)) and unpriced[0]['edge'] is None


def test_sorting_biggest_edge_first_then_unpriced_by_model_p():
    players = [rec(1, 'Low Edge', 'AAA', lam=0.3), rec(2, 'High Edge', 'AAA', lam=0.5), rec(3, 'No Price Hi', 'BBB', lam=0.6),
               rec(4, 'No Price Lo', 'BBB', lam=0.1), rec(5, 'Negative', 'BBB', lam=0.1)]
    mk = lambda imp: {'implied': imp, 'american': 0, 'books': 1, 'book_names': ['DK'], 'at': None, 'source': 'live'}
    priced, unpriced = elv.model_rows([res(players)], {'low edge': mk(0.25), 'high edge': mk(0.2), 'negative': mk(0.3)})
    assert [r['name'] for r in priced] == ['High Edge', 'Low Edge', 'Negative']
    assert priced[-1]['edge'] < 0
    assert [r['name'] for r in unpriced] == ['No Price Hi', 'No Price Lo']
    html = elv.table_html(priced, unpriced)
    assert html.index('Negative') < html.index(elv.NO_PRICE) < html.index('No Price Hi')
    assert html.count(' pts') == 3                       # no edge number on unpriced rows


def test_exclusions_scored_final_and_shootout():
    live = res([rec(1, 'Scored', 'AAA', rate=.02, goals=1), rec(2, 'Open', 'AAA', rate=.02), rec(3, 'Scored By Id', 'BBB', rate=.02)],
               phase='live', remaining=20)
    fin = res([rec(4, 'Final Guy', 'CCC')], phase='final', remaining=0, away='CCC', home='DDD')
    so = res([rec(5, 'Shootout Guy', 'EEE')], phase='shootout', remaining=0, away='EEE', home='FFF')
    priced, unpriced = elv.model_rows([live, fin, so], {}, scored_ids={3})
    assert [r['name'] for r in priced + unpriced] == ['Open']


def test_quote_options_still_validates_prices():
    f = pd.DataFrame([{'player': 'Real Player', 'selection': 'Yes', 'market': 'Anytime goal', 'american_odds': 250, 'sportsbook': 'DK', 'team': 'EDM'},
                      {'player': 'Bad Price', 'selection': 'Yes', 'market': 'Anytime goal', 'american_odds': 20, 'sportsbook': 'DK', 'team': 'EDM'}])
    assert [o['player'] for o in el.quote_options(f)] == ['Real Player']


# ---- AppTests ------------------------------------------------------------------------------------------------
BANNED = ('Bankroll', 'Kelly', 'Stake', 'Min Edge', 'DEMO', 'Your price, your probability', 'Scorecard')


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


def _tab(at, label):
    return next(t for t in at.tabs if t.label == label)


def _text(tab):
    parts = [m.value for m in tab.markdown] + [c.value for c in tab.caption] + [h.value for h in tab.get('html')]
    parts += [getattr(w, 'label', '') or '' for w in list(tab.button) + list(tab.slider) + list(tab.number_input) + list(tab.tabs)]
    return ' '.join(parts)


def test_apptest_no_prices_empty_state_lists_model_p(mp, tmp_path_factory):
    at = run_app(mp, tmp_path_factory.mktemp('el0'))
    assert not at.exception
    txt = _text(_tab(at, '🧪 EdgeLab'))
    assert elv.NO_PRICES_TITLE in txt and 'class="el-t"' in txt and elv.NO_PRICE in txt
    assert ' pts<' not in txt                             # no edge numbers without prices
    for word in BANNED:
        assert word not in txt, word


def test_apptest_with_fixture_live_prices(mp, tmp_path_factory):
    f = pd.DataFrame([q('Auston Matthews', 140, 'DraftKings', '2026-10-22T21:00:00Z'), q('Auston Matthews', 120, 'FanDuel', '2026-10-22T21:05:00Z'),
                      q('Macklin Celebrini', 300, 'DraftKings', '2026-10-22T21:00:00Z')])
    at = run_app(mp, tmp_path_factory.mktemp('el1'), session={'playbook_odds_data': f, 'v46_source': 'Uploaded CSV'})
    assert not at.exception
    txt = _text(_tab(at, '🧪 EdgeLab'))
    assert elv.NO_PRICES_TITLE not in txt and elv.LIVE_LABEL in txt
    assert txt.count(' pts<') == 2 and '2 books' in txt and 'Auston Matthews' in txt
    assert txt.index('Matthews') < txt.index(elv.NO_PRICE + ' · model chance only')
    for word in BANNED:
        assert word not in txt, word
    assert not any(k and str(k).startswith('edgelab_') for k in (getattr(w, 'key', None) for w in list(at.button) + list(at.slider)))
