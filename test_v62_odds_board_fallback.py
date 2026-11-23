"""V6.2 multi-book odds board: free ESPN DraftKings fallback when the keyed feeds give no row, with the real reason."""
from datetime import datetime, timezone
import json

import pandas as pd
import requests

import odds_board_v61 as ob

DAY = '2026-11-23'
NOW = datetime(2026, 11, 23, 17, 30, tzinfo=timezone.utc)
GAMES = [{'Game ID': 2026020378, 'Away': 'CBJ', 'Home': 'NJD', 'Start (UTC)': '2026-11-24T00:00:00Z', 'Status': 'FUT'},
         {'Game ID': 2026020379, 'Away': 'LAK', 'Home': 'MTL', 'Start (UTC)': '2026-11-24T00:30:00Z', 'Status': 'FUT'}]
SB = json.load(open('test_fixtures_v59/espn_scoreboard_odds_20261123.json', encoding='utf-8'))
PROPS = [{'player': 'Jack Hughes', 'team': 'NJD', 'game': 'CBJ @ NJD', 'book': 'DraftKings', 'american': '+145',
          'updated': '2026-11-23T15:00:00Z'},
         {'player': 'Kirill Kaprizov', 'team': 'MIN', 'game': 'MIN @ SJS', 'book': 'DraftKings', 'american': '+120',
          'updated': '2026-11-23T15:00:00Z'},   # not on this (trimmed) slate -> excluded by the board's own scope
         {'player': '', 'game': 'CBJ @ NJD', 'american': '+300'}, {'player': 'X', 'game': 'CBJ @ NJD', 'american': '+50'}]


def test_espn_lines_frame_parses_real_scoreboard_shape():
    f = ob.espn_lines_frame(SB, fetched_at='2026-11-23T17:00:00+00:00')
    assert set(f['market']) == {'h2h', 'spreads', 'totals'} and set(f['sportsbook']) == {'DraftKings'}
    assert len(f) == 12   # 2 games x (2 ML + 2 puck line + over/under)
    cbj = f[(f['home_team'] == 'NJD') & (f['away_team'] == 'CBJ')]
    assert dict(zip(cbj[cbj.market == 'h2h']['selection'], cbj[cbj.market == 'h2h']['american_odds'])) == {'CBJ': 170, 'NJD': -205}
    tot = cbj[cbj.market == 'totals']
    assert set(tot['line']) == {'6.5'} and set(tot['selection']) == {'Over', 'Under'}
    canon, rep = ob.normalize(f, GAMES, DAY, now=NOW, market_filter='All game lines')
    rows = ob.build_rows(canon)
    assert len(rows) == 12 and rep['excluded'] == {} and {r['label'] for r in rows} >= {'CBJ ML', 'NJD -1.5', 'Over 6.5', 'LAK ML'}


def test_espn_lines_skip_started_games_and_bad_payloads():
    live = json.loads(json.dumps(SB))
    live['events'][0]['competitions'][0]['status']['type']['state'] = 'in'
    assert set(ob.espn_lines_frame(live)['home_team']) == {'MTL'}
    for bad in (None, [], {'events': None}, {'events': [{'competitions': []}, 'x']}):
        assert ob.espn_lines_frame(bad).empty


def test_fetch_espn_lines_never_raises():
    def boom(*a, **k):
        raise requests.ConnectionError('offline')
    f, err = ob.fetch_espn_lines(DAY, getter=boom)
    assert f.empty and 'ESPN unavailable' in err

    class R:
        status_code = 503
    f, err = ob.fetch_espn_lines(DAY, getter=lambda *a, **k: R())
    assert f.empty and '503' in err

    class OK:
        status_code = 200
        def json(self):
            return SB
    calls = []
    f, err = ob.fetch_espn_lines(DAY, getter=lambda url, **k: calls.append(url) or OK())
    assert err is None and len(f) == 12 and calls == [ob.ESPN_SCOREBOARD.format('20261123')]


def test_espn_prop_frame_is_anytime_yes_scoped_to_slate():
    f = ob.espn_prop_frame(PROPS, GAMES)
    assert len(f) == 2 and set(f['selection']) == {'Yes'} and set(f['market']) == {'player_goal_scorer_anytime'}
    assert f.iloc[0]['commence_time'] == '2026-11-24T00:00:00Z'
    canon, rep = ob.normalize(f, GAMES, DAY, now=NOW)
    rows = ob.build_rows(canon)
    assert [r['label'] for r in rows] == ['Jack Hughes'] and rows[0]['prices'] == {'DraftKings': 145}
    assert rep['excluded'] == {'event not on this slate': 1}


def _odds_api_props():
    return pd.DataFrame([{'event_id': 'e1', 'player': 'Jack Hughes', 'team': '', 'market': 'player_goal_scorer_anytime',
                          'selection': 'Yes', 'line': '', 'sportsbook': b, 'american_odds': p, 'updated_at': '2026-11-23T16:00:00Z',
                          'home_team': 'New Jersey Devils', 'away_team': 'Columbus Blue Jackets',
                          'commence_time': '2026-11-24T00:00:00Z', 'source': 'The Odds API'} for b, p in (('FanDuel', 150), ('BetMGM', 140))])


def test_fallback_only_for_empty_groups_and_api_sources():
    calls = []
    props = lambda: calls.append('props') or PROPS
    lines = lambda: calls.append('lines') or (ob.espn_lines_frame(SB), None)
    api = _odds_api_props()
    q, used, notes = ob.with_espn_fallback(api, GAMES, DAY, 'Anytime goal (Yes)', 'Automatic API', props, lines, now=NOW)
    assert used == [] and q is api and calls == []           # keyed feed has rows: unchanged, ESPN never called
    q, used, _ = ob.with_espn_fallback(api, GAMES, DAY, 'Everything', 'Automatic API', props, lines, now=NOW)
    assert used == ['lines'] and calls == ['lines']          # props from the API stay; only the empty lines group is filled
    calls.clear()
    q, used, _ = ob.with_espn_fallback(pd.DataFrame(), GAMES, DAY, 'Anytime goal (Yes)', 'Automatic API', props, lines, now=NOW)
    assert used == ['props'] and calls == ['props'] and set(q['source']) == {ob.ESPN_SOURCE}
    q, used, _ = ob.with_espn_fallback(pd.DataFrame(), GAMES, DAY, 'Moneyline', 'Uploaded CSV', props, lines, now=NOW)
    assert used == [] and q.empty                            # CSV-only source: never mixed with ESPN
    q, used, notes = ob.with_espn_fallback(pd.DataFrame(), GAMES, DAY, 'Moneyline', 'Combine both', props,
                                           lambda: (pd.DataFrame(), 'ESPN returned HTTP 503.'), now=NOW)
    assert used == [] and notes == ['ESPN game lines: ESPN returned HTTP 503.']


def test_fallback_note_names_the_multibook_reason():
    reason = ob.empty_reason('Anytime goal (Yes)', 'Automatic API', False, None, None, pd.DataFrame(), {}, GAMES, now=NOW)
    assert reason[0] == 'Odds key not found'
    note = ob.fallback_note(['props'], reason)
    assert 'DraftKings anytime-goal prices (1 book)' in note and 'Multi-book feed: Odds key not found.' in note
    reason = ob.empty_reason('Moneyline', 'Automatic API', True, None, None, pd.DataFrame(), {}, GAMES, now=NOW,
                             lines_error='The Odds API: Odds provider rate limit or quota reached (429).')
    assert '429' in ob.fallback_note(['lines'], reason)


def test_odds_tab_wiring_uses_fallback_after_keyed_sources():
    src = open('tabs/odds.py', encoding='utf-8').read()
    assert src.index('_obd.load_lines(') < src.index('_obd.with_espn_fallback(') < src.index('_obd.build_rows(')
    assert "not in ('No games on this slate','Every game has started')" in src
    app = open('app.py', encoding='utf-8').read()
    assert 'def np_espn_lines(day):' in app and app.index('def np_espn_scorer_quotes') < app.index('def np_espn_lines')
