import probable_goalies_v54 as pgk
from v54_testkit import club_rows, load

GAMES = [{'key': '2026020154', 'game_id': '2026020154', 'away': 'NSH', 'home': 'BOS', 'status': 'FUT'},
         {'key': '2026020156', 'game_id': '2026020156', 'away': 'SJS', 'home': 'OTT', 'status': 'FUT'},
         {'key': '2026020152', 'game_id': '2026020152', 'away': 'PHI', 'home': 'BUF', 'status': 'OFF'}]


def test_nhl_boxscore_final_uses_starter_flag_only():
    out = pgk.parse_nhl_boxscore(load('nhl_boxscore_final_2026020152.json'), 't')
    assert out['PHI']['goalie'] == 'D. Vladar' and out['PHI']['goalie_id'] == '8478435' and out['PHI']['status'] == 'confirmed'
    assert out['BUF']['goalie'] == 'U. Luukkonen'
    assert 'starter flag' in out['PHI']['source']


def test_nhl_pregame_has_no_starter():
    assert pgk.parse_nhl_boxscore(load('nhl_boxscore_pregame_2026020154.json')) == {}
    assert pgk.parse_nhl_boxscore(None) == {} and pgk.parse_nhl_boxscore({'playerByGameStats': 'x'}) == {}


def test_two_flagged_starters_is_ambiguous():
    p = load('nhl_boxscore_final_2026020152.json')
    for g in p['playerByGameStats']['awayTeam']['goalies']:
        g['starter'] = True
    assert 'PHI' not in pgk.parse_nhl_boxscore(p)


def test_espn_probables_confirmed_vs_expected_and_team_mapping():
    out = pgk.parse_espn_scoreboard(load('espn_scoreboard_20261022.json'), 't')
    assert out[('NSH', 'BOS')]['BOS']['status'] == 'confirmed' and out[('NSH', 'BOS')]['NSH']['status'] == 'probable'
    assert out[('SJS', 'OTT')]['SJS']['goalie'] == 'Yaroslav Askarov'  # ESPN 'SJ' -> NHL 'SJS'
    assert out[('NSH', 'BOS')]['NSH']['source'] == 'ESPN scoreboard (probables)'


def test_espn_missing_fields_are_unknown_not_invented():
    payload = {'events': [{'competitions': [{'competitors': [
        {'homeAway': 'home', 'team': {'abbreviation': 'BOS'}, 'probables': [{'name': 'probableStartingGoalie', 'athlete': {}, 'status': {'type': 'confirmed'}}]},
        {'homeAway': 'away', 'team': {'abbreviation': 'NSH'}, 'probables': [{'name': 'other', 'athlete': {'fullName': 'X'}}, 'junk']}]}]},
        {'competitions': []}, None]}
    out = pgk.parse_espn_scoreboard(payload)
    assert out == {('NSH', 'BOS'): {}}
    c = pgk.combine(GAMES[0], None, out)
    assert c['BOS']['status'] == 'unknown' and pgk.starter_label(c['BOS']) == pgk.STATS_ONLY_LABEL
    assert pgk.STATS_ONLY_LABEL == 'Team goalie stats — starter not yet announced'


def test_combine_prefers_nhl_over_espn():
    nhl = pgk.parse_nhl_boxscore(load('nhl_boxscore_final_2026020152.json'))
    espn = {('PHI', 'BUF'): {'PHI': {'team': 'PHI', 'goalie': 'Someone Else', 'status': 'probable', 'source': 'ESPN'}}}
    c = pgk.combine(GAMES[2], nhl, espn)
    assert c['PHI']['goalie'] == 'D. Vladar' and c['PHI']['game_id'] == '2026020152'


def test_fetch_starters_with_fake_getter_and_graceful_failures():
    calls = []

    def getter(url, params=None):
        calls.append(url)
        if 'boxscore' in url:
            return load('nhl_boxscore_final_2026020152.json')
        return load('espn_scoreboard_20261022.json')
    starters, errors, fetched = pgk.fetch_starters('2026-10-22', GAMES, getter=getter)
    assert errors == [] and fetched
    assert sum('boxscore' in u for u in calls) == 1  # only the final game hits the NHL boxscore
    assert starters['2026020154']['BOS']['goalie'] == 'Michael DiPietro'
    assert starters['2026020152']['PHI']['status'] == 'confirmed'

    def broken(url, params=None):
        raise ConnectionError('down')
    starters, errors, _ = pgk.fetch_starters('2026-10-22', GAMES, getter=broken)
    assert len(errors) == 2 and all(s['status'] == 'unknown' for g in starters.values() for s in g.values())


def test_match_stats_by_id_name_and_initial():
    rows = club_rows() + [{'Team': 'PHI', 'Goalie': 'Dan Vladar', 'Player ID': '8478435', 'GP': 3},
                          {'Team': 'BUF', 'Goalie': 'Ukko-Pekka Luukkonen', 'Player ID': '', 'GP': 3}]
    assert pgk.match_stats({'team': 'PHI', 'goalie': 'D. Vladar', 'goalie_id': '8478435', 'status': 'confirmed'}, rows)['Goalie'] == 'Dan Vladar'
    assert pgk.match_stats({'team': 'BUF', 'goalie': 'U. Luukkonen', 'status': 'confirmed'}, rows)['Goalie'] == 'Ukko-Pekka Luukkonen'
    assert pgk.match_stats({'team': 'BOS', 'goalie': 'Michael DiPietro', 'status': 'confirmed'}, rows)['Team'] == 'BOS'
    assert pgk.match_stats({'team': 'BOS', 'goalie': 'Nobody Here', 'status': 'confirmed'}, rows) is None
    assert pgk.match_stats(pgk.unknown('1', 'BOS'), rows) is None


def test_labels():
    assert pgk.starter_label({'status': 'confirmed'}) == 'Confirmed starter'
    assert pgk.starter_label({'status': 'probable'}) == 'Probable starter'
    assert pgk.starter_label(None) == pgk.STATS_ONLY_LABEL
    assert pgk.STARTER_TTL_SECONDS == 300


def test_leaky_card_never_claims_starter_unless_feed_says_so():
    import ui_theme_v53 as ui
    g = {'Team': 'BOS', 'Goalie': 'Jeremy Swayman', 'GP': 8, 'GA': 16, 'GAA': 2.0, 'SV%': .92}
    leaky = ui.goalie_spotlight('BOS', g, kind='leaky')
    assert 'Confirmed starter' not in leaky and 'Probable starter' not in leaky and 'starter not yet announced' in leaky
    known = ui.goalie_spotlight('BOS', g, kind='leaky', starter_known=True)
    assert 'Confirmed starter' not in known and 'not necessarily' in known
    st = ui.goalie_spotlight('BOS', g, kind='starter', starter={'status': 'confirmed', 'goalie': 'Jeremy Swayman', 'source': 'ESPN scoreboard (probables)'},
                             fetched_at='2026-10-22T21:00:00+00:00')
    assert 'Confirmed starter' in st and 'ESPN' in st
