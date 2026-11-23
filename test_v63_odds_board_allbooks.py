"""V6.3 multi-book odds board: every book the feeds return is a column (no allowlist), book picker, us+us2 regions,
SportsGameOdds anytime props in the same request, readable unknown book titles, DraftKings-only fallback labelled."""
from datetime import datetime, timezone
import json

import pandas as pd

import odds_api_v45 as oa
import odds_board_v61 as ob
from odds_feed_cache_v60 import QuoteCache

DAY = '2026-11-23'
NOW = datetime(2026, 11, 23, 17, 30, tzinfo=timezone.utc)
GAMES = [{'Game ID': 2026020378, 'Away': 'CBJ', 'Home': 'NJD', 'Start (UTC)': '2026-11-24T00:00:00Z', 'Status': 'FUT'}]
FX = json.load(open('test_fixtures_v59/odds_allbooks_20261123.json', encoding='utf-8'))
NINE = ['FanDuel', 'DraftKings', 'BetMGM', 'Caesars', 'Fanatics', 'BetRivers', 'Bally Bet', 'Hard Rock Bet', 'theScore Bet']


class _R:
    def __init__(self, p, code=200):
        self.p, self.status_code = p, code

    def json(self):
        return self.p


class _S:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {}), headers))
        if url.endswith('/sports/icehockey_nhl/events'):
            return _R(FX['events'])
        if '/events/' in url:
            return _R(FX['event_odds'][url.split('/events/')[1].split('/')[0]])
        if url.endswith('/sports/icehockey_nhl/odds'):
            return _R(FX['bulk_lines'])
        if 'sportsgameodds' in url:
            return _R(FX['sgo'])
        return _R({}, 404)


def test_anytime_feed_keeps_every_book_one_call_per_event_with_us_us2():
    s = _S()
    f, _w = oa.fetch_odds('k', regions=ob.DEFAULT_REGIONS, session=s)
    odds_calls = [c for c in s.calls if '/events/' in c[0]]
    assert len(odds_calls) == 1 and odds_calls[0][1]['regions'] == 'us,us2' and 'bookmakers' not in odds_calls[0][1]
    rows = ob.build_rows(ob.normalize(f, GAMES, DAY, now=NOW)[0])
    assert len(rows) == 2 and all(r['n'] == 9 for r in rows)
    assert ob.books(rows) == NINE[:5] + ['Bally Bet', 'BetRivers', 'Hard Rock Bet', 'theScore Bet']   # DraftKings kept in place
    hughes = next(r for r in rows if r['label'] == 'Jack Hughes')
    assert hughes['best'] == {'Hard Rock Bet'} and hughes['worst'] == {'Fanatics'} and hughes['spread'] == 25 and hughes['flag'] == 'disc'
    h = ob.table_html(rows, ob.books(rows))
    for b in NINE:
        assert f'<th class="obd-b">{b}</th>' in h


def test_game_lines_one_bulk_call_regions_passed_through_load_lines():
    s = _S()
    seen = []

    def cache_get(fetch, key, regions, markets):
        seen.append((regions, markets))
        return QuoteCache().get(lambda k, **kw: fetch(k, session=s, **{x: v for x, v in kw.items() if x != 'event_cache'}),
                                key, regions, markets)
    f, notes, err = ob.load_lines(cache_get, 'k', {'backup': None, 'sgo': None}, regions='us,us2')
    assert err is None and seen == [('us,us2', ob.GAME_MARKETS)] and len(s.calls) == 1 and s.calls[0][1]['regions'] == 'us,us2'
    rows = ob.build_rows(ob.normalize(f, GAMES, DAY, now=NOW, market_filter='All game lines')[0])
    assert len(rows) == 4 and all(set(r['prices']) == set(NINE) for r in rows)
    assert ob.load_lines.__defaults__ == ('us',)      # direct callers unchanged


def test_regions_secret_parsing():
    assert ob.regions_from(None) == 'us,us2' and ob.regions_from('') == 'us,us2' and ob.regions_from(5) == 'us,us2'
    assert ob.regions_from('us') == 'us' and ob.regions_from(' US , us2, us_ex ,us') == 'us,us2,us_ex'
    assert ob.regions_from('us;drop table') == 'us,us2' and ob.regions_from('xx,eu') == 'eu'
    app = open('app.py', encoding='utf-8').read()
    assert "np_live_odds_cached(_np_key,_np_regions,'player_goal_scorer_anytime')" in app and "_np_regions=np_odds_regions()" in app
    assert "'us','player_goal_scorer_anytime'" not in app


def test_sgo_props_same_request_bet365_and_unknown_titles():
    s = _S()
    f = ob.fetch_sgo_lines('sgo-key', session=s)
    assert len(s.calls) == 1 and ob.SGO_PROP_ODD_ID in s.calls[0][1]['oddID'] and 'points-home-game-ml-home' in s.calls[0][1]['oddID']
    props = f[f['player'] != '']
    assert sorted(zip(props['player'], props['sportsbook'], props['american_odds'])) == [
        ('Jack Hughes', 'Pinnacle', 142), ('Jack Hughes', 'Some Newbook', 165), ('Jack Hughes', 'bet365', 150),
        ('Kirill Marchenko', 'bet365', 240)]           # DraftKings 'available: False' skipped; name from the ID fallback
    assert set(f[f['player'] == '']['market']) == {'h2h'}
    cache = QuoteCache()
    get = lambda fetch, key, regions, markets: cache.get(lambda k, **kw: (ob.fetch_sgo_lines(k, session=s), []), key, regions, markets)
    extra = {'backup': None, 'sgo': ('sgo-key', 'secrets: top-level SGO_API_KEY')}
    p, note, err = ob.load_sgo_props(get, extra)
    lines, _n, _e = ob.load_lines(get, '', extra)
    assert err is None and len(p) == 4 and note == 'SportsGameOdds: 4 prop quotes' and len(lines) == 2 and (lines['player'] == '').all()
    assert len(s.calls) == 2                            # props + lines share one cached SGO response
    e, n, x = ob.load_sgo_props(get, {'sgo': None})
    assert e.empty and n is None and x is None


def test_all_sources_merge_into_one_board():
    s = _S()
    api, _w = oa.fetch_odds('k', regions='us,us2', session=s)
    sgo = ob.fetch_sgo_lines('x', session=s)
    rows = ob.build_rows(ob.normalize(pd.concat([api, sgo[sgo['player'] != '']]), GAMES, DAY, now=NOW)[0])
    hughes = next(r for r in rows if r['label'] == 'Jack Hughes')
    assert hughes['n'] == 12 and {'bet365', 'Pinnacle', 'Some Newbook', 'DraftKings'} <= set(hughes['prices'])
    assert len(ob.books(rows)) == 12


def test_book_names_readable_and_known_ids():
    assert ob.book_name('williamhill_us') == 'Caesars' and ob.book_name('espnbet') == 'theScore Bet'
    assert ob.book_name('theScore Bet') == 'theScore Bet' and ob.book_name('bet365') == 'bet365'
    assert ob.book_name('hardrockbet') == 'Hard Rock Bet' and ob.book_name('Hard Rock Bet (AZ)') == 'Hard Rock Bet (AZ)'
    assert ob.book_name('some_newbook') == 'Some Newbook' and ob.book_name('prizepicks') == 'PrizePicks'
    assert ob.book_name('Brand New Book') == 'Brand New Book' and ob.book_name('') == ''


def test_restrict_books_recomputes_flags_and_drops_empty_rows():
    s = _S()
    f, _w = oa.fetch_odds('k', regions='us,us2', session=s)
    rows = ob.build_rows(ob.normalize(f, GAMES, DAY, now=NOW)[0])
    assert ob.restrict_books(rows, None) is rows
    two = ob.restrict_books(rows, ['DraftKings', 'FanDuel'])
    hughes = next(r for r in two if r['label'] == 'Jack Hughes')
    assert hughes['prices'] == {'FanDuel': 145, 'DraftKings': 150} and hughes['n'] == 2 and hughes['spread'] == 5
    assert hughes['best'] == {'DraftKings'} and hughes['flag'] == ''
    assert ob.restrict_books(rows, []) == [] and ob.restrict_books(rows, ['Nobody']) == []
    one = ob.restrict_books(rows, ['DraftKings'])
    assert all(r['n'] == 1 and r['flag'] == '' and r['best'] == set() for r in one)
    assert next(r for r in rows if r['label'] == 'Jack Hughes')['n'] == 9      # original rows untouched


def test_draftkings_only_fallback_is_labelled():
    note = ob.fallback_note(['props'], ('Odds key not found', 'ODDS_API_KEY was not found.'))
    assert note.startswith('Only DraftKings is available right now') and 'own column once that feed works' in note


def test_odds_tab_book_picker_wiring():
    src = open('tabs/odds.py', encoding='utf-8').read()
    assert "st.multiselect(f'Sportsbooks ({len(_obd_books_all)} available)',_obd_books_all,default=_obd_books_all" in src
    assert src.index('_obd.build_rows(') < src.index('_obd.restrict_books(') < src.index('_obd.filter_rows(')
    assert '_obd.load_sgo_props(' in src and 'regions=_np_regions' in src
    assert 'bookmakers' not in src and 'bookmakers=' not in open('odds_api_v45.py', encoding='utf-8').read()
