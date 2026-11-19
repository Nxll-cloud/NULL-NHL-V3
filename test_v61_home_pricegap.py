"""V6.1 Home 'Price-gap leader': Yes side only, this slate only, unstarted games only, game-scoped names, honest empty states."""
from datetime import datetime, timezone
import pandas as pd
import home_pricegap_v61 as hpg
from home_leaders_v52 import all_targets, choose_leaders
from playbook_odds import compare_odds
import v55_ui

DAY = '2026-11-19'
NOW = datetime(2026, 11, 20, 0, 45, tzinfo=timezone.utc)   # 7:45 PM ET: LAK@TOR (7 PM) is live, VAN@SEA (9:40 PM) is not
GAMES = [{'Game ID': 1, 'Away': 'LAK', 'Home': 'TOR', 'Venue': 'Scotiabank Arena', 'Start (UTC)': '2026-11-20T00:00:00Z', 'Status': 'FUT'},
         {'Game ID': 2, 'Away': 'MIN', 'Home': 'CGY', 'Venue': 'Scotiabank Saddledome', 'Start (UTC)': '2026-11-20T01:00:00Z', 'Status': 'FUT'},
         {'Game ID': 3, 'Away': 'VAN', 'Home': 'SEA', 'Venue': 'Climate Pledge Arena', 'Start (UTC)': '2026-11-20T02:40:00Z', 'Status': 'FUT'},
         {'Game ID': 4, 'Away': 'DAL', 'Home': 'PHI', 'Venue': 'Wells Fargo Center', 'Start (UTC)': '2026-11-20T03:00:00Z', 'Status': 'FUT'}]
PLAYERS = [('Corey Perry', 1, 'LAK', 30), ('Top Gun', 2, 'LAK', 99), ('Blake Coleman', 3, 'MIN', 40), ('Marco Rossi', 4, 'VAN', 33),
           ('Elias Pettersson', 5, 'VAN', 20), ('Elias Pettersson', 6, 'PHI', 21), ('David Perron', 7, 'DAL', 39), ('Gem Guy', 8, 'SEA', 10)]
RANKED = pd.DataFrame([{'Player': n, 'Player ID': i, 'Team': t, 'V3.2 Adjusted Index': f} for n, i, t, f in PLAYERS])
TEAMS = {'LAK': 'Los Angeles Kings', 'TOR': 'Toronto Maple Leafs', 'MIN': 'Minnesota Wild', 'CGY': 'Calgary Flames', 'VAN': 'Vancouver Canucks',
         'SEA': 'Seattle Kraken', 'DAL': 'Dallas Stars', 'PHI': 'Philadelphia Flyers', 'NSH': 'Nashville Predators'}


def q(player, sel, book, price, away, home, start, eid, market='player_goal_scorer_anytime'):
    return {'event_id': eid, 'player': player, 'team': '', 'market': market, 'selection': sel, 'line': '', 'sportsbook': book,
            'american_odds': price, 'updated_at': '2026-11-19T23:30:00Z', 'home_team': TEAMS[home], 'away_team': TEAMS[away],
            'commence_time': start, 'source': 'The Odds API'}


def pair(player, sel, a, b, away, home, start, eid):
    return [q(player, sel, 'BookA', a, away, home, start, eid), q(player, sel, 'BookB', b, away, home, start, eid)]


QUOTES = pd.DataFrame(
    pair('Corey Perry', 'Yes', 250, 700, 'LAK', 'TOR', '2026-11-20T00:00:00Z', 'e1')          # live game: stale vs in-play
    + pair('Blake Coleman', 'No', -1000, -250, 'MIN', 'CGY', '2026-11-20T01:00:00Z', 'e2')     # the NO side
    + pair('Blake Coleman', 'Yes', 250, 260, 'MIN', 'CGY', '2026-11-20T01:00:00Z', 'e2')
    + pair('David Perron', 'Yes', 200, 300, 'DAL', 'NSH', '2026-11-21T01:00:00Z', 'e3')       # tomorrow's back-to-back
    + pair('Gem Guy', 'Yes', 200, 240, 'VAN', 'SEA', '2026-11-20T02:40:00Z', 'e4'))       # the real leader


def targets():
    return all_targets(GAMES, RANKED, DAY)


def test_unscoped_shared_comparison_is_unchanged_and_shows_the_bug():
    _, disc = compare_odds(QUOTES)
    assert disc.iloc[0]['player'] == 'Corey Perry' and len(disc) == 5          # Odds tab data stays as before
    old = choose_leaders(RANKED, targets(), disc)['odds']
    assert old['player'] in ('Corey Perry', 'David Perron', 'Blake Coleman')   # pre-fix: a live / tomorrow / No-side gap


def test_scope_keeps_only_yes_tonight_unstarted():
    clean, disc, rep = hpg.scope(QUOTES, GAMES, DAY, NOW)
    assert set(disc['player']) == {'Gem Guy', 'Blake Coleman'}
    assert set(disc['selection']) == {'Yes'}
    assert rep['excluded'] == {'game started or final': 2, 'not the Yes side of anytime goal': 2, 'event not on this slate date': 2}
    assert rep['accepted'] == len(clean) == 4
    assert disc.iloc[0][['home_team_code', 'away_team_code']].tolist() == ['SEA', 'VAN']


def test_leader_is_the_real_pregame_gap():
    _, disc, _ = hpg.scope(QUOTES, GAMES, DAY, NOW)
    L = choose_leaders(RANKED, targets(), disc)
    assert L['odds']['player'] == 'Gem Guy' and L['odds']['team'] == 'SEA' and L['odds']['gap_pct'] == 13.33
    assert L['odds']['best_odds'] == 240 and L['odds']['best_sportsbook'] == 'BookB'


def test_before_puck_drop_live_game_counts():
    early = datetime(2026, 11, 19, 23, 0, tzinfo=timezone.utc)
    _, disc, _ = hpg.scope(QUOTES, GAMES, DAY, early)
    assert disc.iloc[0]['player'] == 'Corey Perry'


def test_final_status_excluded_even_before_start_time():
    games = [dict(g, Status='OFF') if g['Game ID'] == 3 else g for g in GAMES]
    _, disc, rep = hpg.scope(QUOTES, games, DAY, NOW)
    assert 'Gem Guy' not in set(disc['player'])


def test_same_name_resolved_by_game_not_ambiguous():
    quotes = pd.DataFrame(pair('Elias Pettersson', 'Yes', 300, 400, 'VAN', 'SEA', '2026-11-20T02:40:00Z', 'e9'))
    _, disc, _ = hpg.scope(quotes, GAMES, DAY, NOW)
    L = choose_leaders(RANKED, targets(), disc)
    assert str(L['odds']['player_id']) == '5' and L['odds']['team'] == 'VAN'
    _, unscoped = compare_odds(quotes)
    assert choose_leaders(RANKED, targets(), unscoped)['odds'] is None      # legacy name-only path still refuses ambiguity


def test_name_from_other_game_never_matches():
    quotes = pd.DataFrame(pair('Gem Guy', 'Yes', 200, 300, 'MIN', 'CGY', '2026-11-20T01:00:00Z', 'e2'))
    _, disc, _ = hpg.scope(quotes, GAMES, DAY, NOW)
    assert choose_leaders(RANKED, targets(), disc)['odds'] is None


def test_csv_team_rows_map_to_slate():
    csv = pd.DataFrame([{'player': 'Gem Guy', 'team': 'SEA', 'market': 'player_goal_scorer_anytime', 'selection': 'Yes', 'sportsbook': b,
                         'american_odds': p, 'updated_at': '2026-11-19T20:00:00Z', 'event_id': 'x', 'line': ''} for b, p in (('A', 150), ('B', 175))])
    _, disc, _ = hpg.scope(csv, GAMES, DAY, NOW)
    assert disc.iloc[0]['player'] == 'Gem Guy'
    assert choose_leaders(RANKED, targets(), disc)['odds']['player'] == 'Gem Guy'


def test_bad_inputs_never_raise():
    for bad in (None, pd.DataFrame(), pd.DataFrame([{'player': 'x'}]), pd.DataFrame([{'market': None, 'selection': float('nan')}])):
        clean, disc, rep = hpg.scope(bad, GAMES, DAY, NOW)
        assert disc.empty
    assert hpg.scope(QUOTES, [], DAY, NOW)[1].empty


def test_empty_reasons_are_honest():
    no = pd.DataFrame()
    assert hpg.empty_reason('Automatic API', False, None, None, no, {}, no, False)[0] == 'Load sportsbook odds to unlock'
    assert hpg.empty_reason('Automatic API', True, 'Provider timed out.', None, no, {}, no, False)[0] == 'Odds feed unavailable'
    assert hpg.empty_reason('Automatic API', True, None, None, no, {}, no, False)[0] == 'No live quotes right now'
    late = datetime(2026, 11, 20, 4, 0, tzinfo=timezone.utc)
    _, disc, rep = hpg.scope(QUOTES, GAMES, DAY, late)
    t, b = hpg.empty_reason('Automatic API', True, None, None, QUOTES, rep, disc, False)
    assert t == 'No pre-game price gap tonight' and 'game started or final' in b
    assert hpg.empty_reason('Automatic API', True, None, None, QUOTES, rep, disc, True) == (None, None)


def test_card_renders_leader_and_reasoned_empty_state():
    base = {'season': '20262027', 'picks': {}, 'leaders': {'statistical': None, 'gematria': None, 'overlap': None,
            'odds': {'player': 'Marco Rossi', 'team': 'VAN', 'opponent': 'SEA', 'player_id': 4, 'gap_pct': 13.33,
                     'best_sportsbook': 'BookB', 'best_odds_label': '+240'}}}
    html = v55_ui.leaders_row(base)
    assert 'Price-gap leader' in html and '+240' in html and '+13.3% gap' in html and 'BookB' in html
    empty = dict(base, leaders=dict(base['leaders'], odds=None), odds_empty=('No pre-game price gap tonight', 'Excluded: game started or final (2).'))
    html = v55_ui.leaders_row(empty)
    assert 'No pre-game price gap tonight' in html and 'Load sportsbook odds to unlock' not in html
    assert 'Load sportsbook odds to unlock' in v55_ui.leaders_row(dict(base, leaders=dict(base['leaders'], odds=None)))   # legacy default kept
