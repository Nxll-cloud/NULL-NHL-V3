"""V5.8 arena names on slate displays: parsing, missing venues, and the Tonight's Board / Numbers header renders."""
from datetime import datetime, timezone

import live_feed_v56 as lf
import matchup_center_v54 as mc
import nhl_data
import numboard_v56 as nb
import numbers_v58_ui as numv58
import ui_theme_v53 as ui
import v55_ui as v5
import v56_ui as v56
import venue_v58 as vn

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


def test_clean_and_api_parsing():
    assert vn.clean({'default': ' United  Center '}) == 'United Center'
    assert vn.from_api({'venue': {'default': 'Bell Centre'}}) == 'Bell Centre'
    for bad in (None, float('nan'), '', '  ', 'None', 'nan', 'NaN', '<NA>', {'default': None}, {}, 'Venue unavailable'):
        assert vn.clean(bad) == ''
    assert vn.from_api({}) == '' and vn.from_api(None) == ''


def test_schedule_and_score_endpoints_carry_venue(monkeypatch):
    payload = {'gameWeek': [{'date': '2026-10-23', 'games': [
        {'id': 1, 'awayTeam': {'abbrev': 'MTL'}, 'homeTeam': {'abbrev': 'CHI'}, 'startTimeUTC': '2026-10-24T00:00:00Z',
         'gameState': 'FUT', 'venue': {'default': 'United Center'}},
        {'id': 2, 'awayTeam': {'abbrev': 'BOS'}, 'homeTeam': {'abbrev': 'TOR'}, 'startTimeUTC': '2026-10-23T23:00:00Z', 'gameState': 'FUT'}]}]}
    monkeypatch.setattr(nhl_data, 'fetch_json', lambda path: payload)
    by = {r['Home']: r for r in nhl_data.get_schedule('2026-10-23')}
    assert by['CHI']['Venue'] == 'United Center' and by['TOR']['Venue'] is None   # no venue -> None (never guessed)
    sc = lf.parse_scores({'games': [{'id': 9, 'gameState': 'FUT', 'awayTeam': {'abbrev': 'A'}, 'homeTeam': {'abbrev': 'B'},
                                     'venue': {'default': 'Canada Life Centre'}}, {'id': 10, 'gameState': 'FUT'}]})
    assert sc['9']['venue'] == 'Canada Life Centre' and sc['10']['venue'] == ''


def test_slate_games_and_backfill_never_invent():
    games = mc.slate_games([{'Game ID': 1, 'Away': 'MTL', 'Home': 'CHI', 'Start (UTC)': 'x', 'Venue': 'United Center'},
                            {'Game ID': 2, 'Away': 'BOS', 'Home': 'TOR', 'Start (UTC)': 'y', 'Venue': float('nan')},
                            {'Game ID': 3, 'Away': 'NYR', 'Home': 'NJD', 'Start (UTC)': 'z'}])   # older snapshot: no Venue key
    by = {g['home']: g for g in games}
    assert by['CHI']['venue'] == 'United Center' and by['TOR']['venue'] == '' and by['NJD']['venue'] == ''
    vn.fill(games, {'2': {'venue': 'Scotiabank Arena'}})
    assert by['TOR']['venue'] == 'Scotiabank Arena' and by['NJD']['venue'] == ''   # only the real score-endpoint value
    assert vn.label('United Center') == ' · 📍 United Center' and vn.label(None) == ''


def _board_data(venue):
    return {'games': [{'key': 'k1', 'game_id': '1', 'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T00:00:00Z', 'status': 'FUT', 'venue': venue}]}


def test_tonights_board_shows_arena_and_hides_missing():
    h = v5.scoreboard(_board_data('United Center'), NOW)
    assert 'class="vn tvn"' in h and 'United Center' in h and '📍' in h
    for missing in (None, '', 'None', float('nan')):
        out = v5.scoreboard(_board_data(missing), NOW)
        assert 'class="vn' not in out and 'None' not in out and 'nan' not in out.lower().replace('nannounced', '')


def test_featured_and_matchup_center_headers():
    g = _board_data('United Center')['games'][0]
    assert 'United Center' in v5.versus_bar(g, NOW) and 'vn hvn' in v5.versus_bar(g, NOW)
    bare = dict(g, venue=None)
    assert 'vn hvn' not in v5.versus_bar(bare, NOW) and '<em' not in v5.versus_bar(bare, NOW).split('class="vs"')[1].split('</div>')[0]


def _nboard(arena):
    return nb.game_board({'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T00:00:00Z', 'arena': arena,
                          'arena_values': {'ordinal_root': 7} if arena else None}, [], [])


def test_numbers_header_arena_and_missing():
    h = numv58.game_board(_nboard('United Center'), 5)
    assert 'United Center' in h and '= 7' in h
    for missing in (None, '', 'None'):
        out = numv58.game_board(_nboard(missing), 5)
        assert 'Arena unavailable' not in out and 'None' not in out and 'class="nga' not in out


def test_other_lists_render_arena_only_when_known():
    assert 'United Center' in ui.matchup_bar('MTL', 'CHI', '8:00 PM', 'United Center')
    assert 'unavailable' not in ui.matchup_bar('MTL', 'CHI', '8:00 PM', None).lower()
    assert ui.arena_line(None) == '' and 'United Center' in ui.arena_line('United Center')
    items = [{'away': 'MTL', 'home': 'CHI', 'phase': 'pregame', 'label': 'Pregame', 'leader': None, 'venue': 'United Center'},
             {'away': 'BOS', 'home': 'TOR', 'phase': 'pregame', 'label': 'Pregame', 'leader': None}]
    strip = v56.live_strip(items)
    assert strip.count('class="vn"') == 1 and 'United Center' in strip
    assert '<' not in open(v5.ASSETS / 'v58.css').read() and '.vn' in open(v5.ASSETS / 'v58.css').read()
