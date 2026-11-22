"""V6.1 multi-book odds board: cents math, flags, best/worst, scope, fetch parsers, key discovery, empty states, app."""
from datetime import datetime, timezone

import pandas as pd
import pytest

import deploy_info_v61 as di
import odds_board_v61 as ob
from odds_api_v45 import OddsFeedError

DAY = '2026-11-22'
NOW = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)
GAMES = [{'Game ID': 1, 'Away': 'CAR', 'Home': 'NYR', 'Start (UTC)': '2026-11-22T17:30:00Z', 'Status': 'FUT'},
         {'Game ID': 2, 'Away': 'EDM', 'Home': 'STL', 'Start (UTC)': '2026-11-23T00:00:00Z', 'Status': 'FUT'}]
TEAMS = {'CAR': 'Carolina Hurricanes', 'NYR': 'New York Rangers', 'EDM': 'Edmonton Oilers', 'STL': 'St. Louis Blues'}


def q(book, price, *, player='', market='player_goal_scorer_anytime', sel='Yes', line='', away='CAR', home='NYR',
      when='2026-11-22T14:00:00Z', team='', source='The Odds API'):
    return {'event_id': f'e-{away}', 'player': player, 'team': team, 'market': market, 'selection': sel, 'line': line,
            'sportsbook': book, 'american_odds': price, 'updated_at': when, 'home_team': TEAMS[home], 'away_team': TEAMS[away],
            'commence_time': '2026-11-22T17:30:00Z' if away == 'CAR' else '2026-11-23T00:00:00Z', 'source': source}


# ---------------------------------------------------------------- cents math
@pytest.mark.parametrize('a,b,c', [(-110, -115, 5), (-110, 110, 20), (-105, 105, 10), (100, -100, 0), (-100, 100, 0),
                                   (110, 120, 10), (-200, -180, 20), (150, -150, 100), (+105, -110, 15), ('-110', '+110', 20)])
def test_cents_gap_continuous_across_even_money(a, b, c):
    assert ob.cents_gap(a, b) == c


def test_cents_scale_and_invalid_prices():
    assert ob.cents_scale(-110) == -10 and ob.cents_scale(110) == 10 and ob.cents_scale(100) == 0 == ob.cents_scale(-100)
    for bad in (None, True, 'x', 50, -99, float('nan'), float('inf')):
        assert ob.cents_scale(bad) is None
    assert ob.cents_gap(-110, None) is None
    assert ob.spread_cents([-110, -115, 105]) == 20 and ob.spread_cents([-110]) is None and ob.spread_cents([]) is None


def test_tight_and_discrepancy_flags_and_thresholds():
    assert ob.flag(4, 2) == 'tight' and ob.flag(5, 2) == '' and ob.flag(20, 3) == '' and ob.flag(21, 2) == 'disc'
    assert ob.flag(0, 1) == '' and ob.flag(None, 3) == ''                          # 2+ books required
    assert ob.flag(8, 2, tight=10) == 'tight' and ob.flag(12, 2, disc=10) == 'disc'
    assert ob.TIGHT_DEFAULT == 5 and ob.DISC_DEFAULT == 20


def test_best_and_worst_for_the_bettor():
    assert ob.best_worst({'A': -110, 'B': 105, 'C': -120}) == ({'B'}, {'C'})
    assert ob.best_worst({'A': 350, 'B': 400, 'C': 400, 'D': 300}) == ({'B', 'C'}, {'D'})   # ties all highlighted
    assert ob.best_worst({'A': -110, 'B': -110}) == (set(), set())                           # all equal: no colour
    assert ob.best_worst({'A': -110}) == (set(), set())


# ---------------------------------------------------------------- scope + rows
def _quotes():
    return pd.DataFrame([
        q('FanDuel', 300, player='Artemi Panarin'), q('DraftKings', 340, player='Artemi Panarin'),
        q('BetMGM', 325, player='Artemi Panarin'), q('williamhill_us', 320, player='Artemi Panarin'),
        q('FanDuel', 300, player='Artemi Panarin', sel='No'),                       # No side excluded
        q('FanDuel', 300, player='Artemi Panarin', line='0.5'),                     # a line on Yes excluded
        q('FanDuel', 500, player='Leon Draisaitl', away='EDM', home='STL'), q('Fanatics', 502, player='Leon Draisaitl', away='EDM', home='STL'),
        q('FanDuel', 220, player='Seth Jarvis', market='player_points', sel='Over', line='0.5'),
    ])


def test_default_view_is_price_gap_scope_and_rows():
    canon, rep = ob.normalize(_quotes(), GAMES, DAY, now=NOW)
    rows = ob.build_rows(canon)
    labels = [r['label'] for r in rows]
    assert labels == ['Artemi Panarin', 'Leon Draisaitl']                           # anytime Yes only, slate order
    pan = rows[0]
    assert pan['prices'] == {'FanDuel': 300, 'DraftKings': 340, 'BetMGM': 325, 'Caesars': 320}
    assert pan['spread'] == 40 and pan['flag'] == 'disc' and pan['best'] == {'DraftKings'} and pan['worst'] == {'FanDuel'}
    assert rows[1]['spread'] == 2 and rows[1]['flag'] == 'tight'
    assert rep['excluded']['not the Yes side of anytime goal'] == 2
    assert ob.books(rows) == ['FanDuel', 'DraftKings', 'BetMGM', 'Caesars', 'Fanatics']
    props = ob.build_rows(ob.normalize(_quotes(), GAMES, DAY, now=NOW, market_filter='All player props')[0])
    assert 'Seth Jarvis · Over 0.5' in [r['label'] for r in props]


def test_started_games_and_off_slate_events_are_excluded():
    later = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)                     # CAR@NYR started
    rows = ob.build_rows(ob.normalize(_quotes(), GAMES, DAY, now=later)[0])
    assert [r['label'] for r in rows] == ['Leon Draisaitl']
    _, rep = ob.normalize(_quotes(), GAMES[1:], DAY, now=NOW)
    assert rep['excluded'].get('event not on this slate')


def test_newest_price_per_book_wins_when_sources_overlap():
    f = pd.DataFrame([q('FanDuel', 300, player='A B', when='2026-11-22T13:00:00Z'), q('FanDuel', 320, player='A B', when='2026-11-22T14:30:00Z', source='CSV'),
                      q('DraftKings', 310, player='A B')])
    r = ob.build_rows(ob.normalize(f, GAMES, DAY, now=NOW)[0])[0]
    assert r['prices']['FanDuel'] == 320 and r['sources']['FanDuel'] == 'CSV' and r['n'] == 2


def _lines():
    rows = []
    for book, (a_ml, h_ml, a_pl, h_pl, ov, un) in {'FanDuel': (130, -155, -175, 145, -110, -110), 'DraftKings': (135, -160, -170, 142, -115, -105),
                                                  'BetMGM': (125, -150, -180, 150, -105, -115)}.items():
        rows += [q(book, a_ml, market='h2h', sel=TEAMS['CAR'], team=TEAMS['CAR']), q(book, h_ml, market='h2h', sel=TEAMS['NYR'], team=TEAMS['NYR']),
                 q(book, a_pl, market='spreads', sel=TEAMS['CAR'], line='1.5'), q(book, h_pl, market='spreads', sel=TEAMS['NYR'], line='-1.5'),
                 q(book, ov, market='totals', sel='Over', line='6.5'), q(book, un, market='totals', sel='Under', line='6.5')]
    return pd.DataFrame(rows)


def test_game_lines_rows_labels_and_flags():
    rows = ob.build_rows(ob.normalize(_lines(), GAMES, DAY, now=NOW, market_filter='All game lines')[0])
    assert [r['label'] for r in rows] == ['CAR ML', 'NYR ML', 'CAR +1.5', 'NYR -1.5', 'Over 6.5', 'Under 6.5']
    over = rows[4]
    assert over['spread'] == 10 and over['best'] == {'BetMGM'} and over['worst'] == {'DraftKings'}
    under = rows[5]                                                                 # -105 vs -115 = 10
    assert under['spread'] == 10 and under['flag'] == ''
    ml = ob.build_rows(ob.normalize(_lines(), GAMES, DAY, now=NOW, market_filter='Moneyline')[0])
    assert [r['market'] for r in ml] == ['Moneyline', 'Moneyline']
    assert ob.normalize(_lines(), GAMES, DAY, now=NOW)[0] == []                    # default view: props only


def test_filter_rows_flag_and_search():
    rows = ob.build_rows(ob.normalize(_quotes(), GAMES, DAY, now=NOW)[0])
    assert [r['label'] for r in ob.filter_rows(rows, 'Tight')] == ['Leon Draisaitl']
    assert [r['label'] for r in ob.filter_rows(rows, 'Discrepancy')] == ['Artemi Panarin']
    assert [r['label'] for r in ob.filter_rows(rows, 'All', 'rangers')] == ['Artemi Panarin']
    assert [r['label'] for r in ob.filter_rows(rows, 'All', 'EDM @ STL')] == ['Leon Draisaitl']
    assert ob.filter_rows(rows, 'All', 'zzz') == []


# ---------------------------------------------------------------- html
def test_table_html_colours_legend_sticky_and_escaping():
    rows = ob.build_rows(ob.normalize(_quotes(), GAMES, DAY, now=NOW)[0])
    h = ob.table_html(rows, ob.books(rows))
    assert 'Best price' in h and 'Worst price' in h and 'TIGHT &lt; 5¢' in h and 'DISCREPANCY &gt; 20¢' in h
    assert '<td class="best" title="DraftKings · The Odds API">+340</td>' in h and '<td class="worst" title="FanDuel · The Odds API">+300</td>' in h
    assert '<td class="obd-na">—</td>' in h and '40¢<span class="obd-f disc">DISCREPANCY</span>' in h and 'CAR @ NYR' in h
    assert 'class="obd-s"' in h and 'obd-w' in h
    bad = [dict(rows[0], label='<script>x</script>')]
    assert '<script>' not in ob.table_html(bad, ob.books(bad))
    css = open('assets/v58.css', encoding='utf-8').read()
    assert '.v61-obd .obd-t .obd-s{position:sticky;left:0' in css and 'overflow-x:auto' in css and '@media (max-width:600px){.v61-obd' in css


# ---------------------------------------------------------------- empty states
def test_empty_states_reuse_price_gap_reasons():
    E = lambda **k: ob.empty_reason(**{**dict(market_filter='Anytime goal (Yes)', source='Automatic API', has_key=False, live_error=None,
                                               shared_error=None, quotes=pd.DataFrame(), report={}, games=GAMES, now=NOW), **k})
    assert E()[0] == 'Odds key not found'
    assert E(market_filter='Moneyline')[0] == 'Odds key not found'
    assert E(has_key=True, live_error='Odds provider rate limit or quota reached (429).')[0] == 'Odds feed unavailable'
    assert E(has_key=True)[0] == 'No live quotes right now'
    assert E(games=[])[0] == 'No games on this slate'
    assert E(now=datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc))[0] == 'Every game has started'
    assert E(has_key=True, market_filter='Total', lines_error='The Odds API: x')[0] == 'Game lines unavailable'
    assert E(has_key=True, n_rows_unfiltered=3)[0] == 'No lines match these filters'
    assert 'Odds key not found' in ob.table_html([], [], empty=E())


# ---------------------------------------------------------------- fetchers + keys
class _R:
    def __init__(self, payload, status=200):
        self.p, self.status_code = payload, status

    def json(self):
        return self.p


class _S:
    def __init__(self, *payloads):
        self.payloads, self.calls = list(payloads), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        p = self.payloads.pop(0)
        return p if isinstance(p, _R) else _R(p)


def test_fetch_game_lines_one_bulk_call_and_parsing():
    ev = [{'id': 'e1', 'home_team': 'New York Rangers', 'away_team': 'Carolina Hurricanes', 'commence_time': '2026-11-22T17:30:00Z',
           'bookmakers': [{'key': 'fanduel', 'title': 'FanDuel', 'last_update': '2026-11-22T14:00:00Z', 'markets': [
               {'key': 'h2h', 'outcomes': [{'name': 'New York Rangers', 'price': -150}, {'name': 'Carolina Hurricanes', 'price': 128}]},
               {'key': 'spreads', 'outcomes': [{'name': 'New York Rangers', 'price': 150, 'point': -1.5}, {'name': 'Carolina Hurricanes', 'price': -50}]},
               {'key': 'totals', 'outcomes': [{'name': 'Over', 'price': -110, 'point': 6.5}, {'name': 'Under', 'price': -110}]}]}]}]
    s = _S(ev)
    f, w = ob.fetch_game_lines('k', session=s)
    assert len(s.calls) == 1 and s.calls[0][0].endswith('/sports/icehockey_nhl/odds') and s.calls[0][1]['markets'] == 'h2h,spreads,totals'
    assert sorted(f['market']) == ['h2h', 'h2h', 'spreads', 'totals'] and f.attrs['feed_status']['event_requests'] == 1
    with pytest.raises(OddsFeedError) as e:
        ob.fetch_game_lines('k', session=_S(_R({}, 429)))
    assert e.value.code == 'quota'
    from odds_feed_cache_v60 import QuoteCache                                      # works through the shared 30-min cache
    f2, _w = QuoteCache().get(lambda key, **kw: ob.fetch_game_lines(key, session=_S(ev), **{k: v for k, v in kw.items() if k != 'event_cache'}),
                              'k', 'us', ob.GAME_MARKETS)
    assert len(f2) == 4 and f2.attrs['feed_status']['cache_seconds'] == 1800
    with pytest.raises(OddsFeedError):
        ob.fetch_game_lines('', session=_S([]))


def test_fetch_sgo_lines_documented_shape_header_auth_and_pagination():
    ev = {'eventID': 'X1', 'teams': {'home': {'names': {'long': 'New York Rangers', 'short': 'NYR'}},
                                     'away': {'names': {'long': 'Carolina Hurricanes', 'short': 'CAR'}}},
          'status': {'started': False, 'startsAt': '2026-11-22T17:30:00.000Z'},
          'odds': {'points-home-game-ml-home': {'byBookmaker': {'fanduel': {'odds': '-148', 'available': True, 'lastUpdatedAt': '2026-11-22T14:10:00Z'},
                                                               'draftkings': {'odds': '-155', 'available': False}}},
                   'points-all-game-ou-over': {'byBookmaker': {'betmgm': {'odds': '-112', 'overUnder': '6.5', 'available': True}}},
                   'points-home-game-sp-home': {'byBookmaker': {'caesars': {'odds': '+150'}}}}}       # no spread value: skipped
    started = dict(ev, eventID='X2', status={'started': True})
    s = _S({'success': True, 'data': [ev], 'nextCursor': 'c1'}, {'success': True, 'data': [started]})
    f = ob.fetch_sgo_lines('secret-key', session=s)
    assert len(s.calls) == 2 and s.calls[0][2] == {'x-api-key': 'secret-key'} and 'secret-key' not in str(s.calls[0][1])
    assert s.calls[1][1]['cursor'] == 'c1' and s.calls[0][1]['leagueID'] == 'NHL' and 'points-all-game-ou-over' in s.calls[0][1]['oddID']
    assert sorted(zip(f['sportsbook'], f['american_odds'])) == [('BetMGM', -112), ('FanDuel', -148)]
    rows = ob.build_rows(ob.normalize(f, GAMES, DAY, now=NOW, market_filter='All game lines')[0])
    assert [r['label'] for r in rows] == ['NYR ML', 'Over 6.5']


def test_failover_only_on_auth_or_quota():
    calls = []

    def get(k):
        calls.append(k)
        if k == 'p':
            raise OddsFeedError('q', code='quota')
        return 'ok'
    assert ob.with_failover(get, [('p', 'primary'), ('b', 'backup')]) == ('ok', 'backup') and calls == ['p', 'b']

    def net(k):
        raise OddsFeedError('n', code='network')
    with pytest.raises(OddsFeedError):
        ob.with_failover(net, [('p', 'primary'), ('b', 'backup')])
    assert ob.with_failover(lambda k: k, [('', 'primary'), ('b', 'backup')]) == ('b', 'backup')


def test_load_lines_merges_sources_and_reports_errors():
    def cache_get(fetch, key, regions, markets):
        if fetch is ob.fetch_game_lines:
            if key == 'p':
                raise OddsFeedError('rate limit (429).', code='quota')
            return _lines(), []
        return pd.DataFrame([q('Fanatics', 140, market='h2h', sel=TEAMS['CAR'], team=TEAMS['CAR'], source='SportsGameOdds')]), []
    extra = {'backup': ('b', 'secrets: top-level ODDS_API_KEY_2'), 'sgo': ('s', 'secrets: top-level SGO_API_KEY'), 'other': []}
    f, notes, err = ob.load_lines(cache_get, 'p', extra)
    assert err is None and 'Fanatics' in set(f['sportsbook']) and any('backup Odds API key' in n for n in notes)
    assert not any(v in ' '.join(notes) for v in ('"b"', "'s'"))
    f2, _n, err2 = ob.load_lines(lambda *a: (_ for _ in ()).throw(OddsFeedError('down', code='network')), 'p', {'sgo': None, 'backup': None})
    assert f2.empty and 'The Odds API: down' in err2


def test_key_discovery_locations_only_and_sidebar_stamp():
    sec = {'ODDS_API_KEY': 'aaa', 'ODDS_API_KEY_2': 'bbb', 'SGO_API_KEY': 'ccc', 'ODDSJAM_API_KEY': 'ddd'}
    x = di.find_extra_keys(sec, environ={}, primary='aaa')
    assert x['backup'] == ('bbb', 'secrets: top-level ODDS_API_KEY_2') and x['sgo'] == ('ccc', 'secrets: top-level SGO_API_KEY')
    assert x['other'] == ['ODDSJAM_API_KEY']
    cap = di.sidebar_caption({'commit': 'abc'}, 'secrets: top-level ODDS_API_KEY', x)
    for v in ('aaa', 'bbb', 'ccc', 'ddd'):
        assert v not in cap
    assert 'Backup Odds API key: found (secrets: top-level ODDS_API_KEY_2' in cap and 'SportsGameOdds key: found' in cap
    assert di.sidebar_caption({'commit': 'abc'}, None) == di.sidebar_caption({'commit': 'abc'}, None, None)   # old stamp unchanged
    same = di.find_extra_keys({'ODDS_API_KEY': 'aaa', 'THE_ODDS_API_KEY': 'aaa'}, environ={}, primary='aaa')
    assert same['backup'] is None                                                   # same value is not a second key
    alias = di.find_extra_keys({'ODDS_API_KEY': 'aaa', 'THE_ODDS_API_KEY': 'zzz'}, environ={}, primary='aaa')
    assert alias['backup'] == ('zzz', 'secrets: top-level THE_ODDS_API_KEY')
    sect = di.find_extra_keys({'odds': {'api_key': 'aaa', 'backup_key': 'yyy'}, 'sportsgameodds': {'api_key': 'sss'}}, environ={}, primary='aaa')
    assert sect['backup'] == ('yyy', 'secrets: [odds] backup_key') and sect['sgo'] == ('sss', 'secrets: [sportsgameodds] api_key')
    assert di.find_extra_keys({}, environ={}) == {'backup': None, 'sgo': None, 'other': []}
    assert 'not found' in di.extra_caption(di.find_extra_keys({}, environ={}))


def test_odds_tab_wiring_appends_section_only():
    src = open('tabs/odds.py', encoding='utf-8').read()
    assert src.index("st.info('No sportsbook quotes available for the selected source.')") < src.index('import odds_board_v61 as _obd')
    for k in ("key='v61_obd_market'", "key='v61_obd_flag'", "key='v61_obd_search'", "key='v61_obd_tight'", "key='v61_obd_disc'"):
        assert k in src
    app = open('app.py', encoding='utf-8').read()
    assert "if _exc0.code not in ('auth','quota') or not _np_extra_keys.get('backup')" in app


def test_apptest_odds_tab_board_empty_state(monkeypatch, tmp_path):
    """Offline AppTest (no odds key): the board renders with the honest no-key reason; game-line market too."""
    import streamlit as st
    from v54_testkit import run_app
    st.cache_data.clear()
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    html = lambda: ' '.join(h.value for t in at.tabs if 'Odds' in t.label for h in t.get('html')) + ' '.join(
        m.value for t in at.tabs if 'Odds' in t.label for m in t.markdown)
    h = html()
    assert 'Multi-book odds board' in h and ('Odds key not found' in h or 'Every game has started' in h or 'No games on this slate' in h)
    sb = next(w for w in at.selectbox if w.key == 'v61_obd_market')
    sb.set_value('Moneyline').run()
    assert not at.exception and 'Multi-book odds board' in html()
