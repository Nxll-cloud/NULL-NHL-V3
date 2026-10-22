import pandas as pd

import matchup_center_v54 as mc

GAMES = [{'Game ID': 2026020155, 'Away': 'NYR', 'Home': 'TOR', 'Start (UTC)': '2026-10-22T23:00:00Z'},
         {'Game ID': '2026020154', 'Away': 'NSH', 'Home': 'BOS', 'Start (UTC)': '2026-10-22T23:00:00Z'},
         {'Game ID': '2026020154', 'Away': 'NSH', 'Home': 'BOS', 'Start (UTC)': '2026-10-22T23:00:00Z'},
         {'Away': 'NSH', 'Home': ''}, 'junk']


def tgt(pid, name, team, form, matches=0):
    return {'player_id': pid, 'player': name, 'team': team, 'form': form, 'matches': matches, 'day': [], 'arena_matches': []}


TARGETS = [{'game': {'away': 'NSH', 'home': 'BOS', 'arena': 'TD Garden'},
            'away_targets': [tgt('1', 'Filip Forsberg', 'NSH', 80, 2), tgt('2', 'Steven Stamkos', 'NSH', 60)],
            'home_targets': [tgt('3', 'David Pastrnak', 'BOS', 120, 3), tgt('3', 'David Pastrnak', 'BOS', 120, 3)]},
           {'game': {'away': 'NYR', 'home': 'TOR', 'arena': 'Scotiabank Arena'},
            'away_targets': [tgt('4', 'Artemi Panarin', 'NYR', 90)], 'home_targets': []}]


def test_slate_games_dedupes_and_skips_invalid():
    g = mc.slate_games(GAMES)
    assert [x['key'] for x in g] == ['2026020154', '2026020155']
    assert mc.find_game(GAMES, '2026020155')['home'] == 'TOR' and mc.find_game(GAMES, 'nope') is None
    assert mc.game_key({'Away': 'a', 'Home': 'b', 'Start (UTC)': 's'}) == 'A@B@s'


def test_card_maps_to_game_teams():
    g = mc.game_for_pick({'Team': 'TOR', 'Opponent': 'NYR', 'Player': 'X'}, GAMES)
    assert g['key'] == '2026020155' and g['focus_team'] == 'TOR' and g['opponent'] == 'NYR'
    assert mc.game_for_pick({'team': 'bos'}, GAMES)['opponent'] == 'NSH'


def test_pick_not_on_slate_or_missing():
    assert mc.game_for_pick({'Team': 'EDM'}, GAMES) is None
    assert mc.game_for_pick(None, GAMES) is None and mc.game_for_pick({'Team': ''}, GAMES) is None


def test_team_in_two_games_prefers_listed_opponent():
    games = GAMES + [{'Game ID': 2026020199, 'Away': 'BOS', 'Home': 'TOR', 'Start (UTC)': '2026-10-22T20:00:00Z'}]
    assert mc.game_for_pick({'Team': 'BOS', 'Opponent': 'NSH'}, games)['key'] == '2026020154'
    assert mc.game_for_pick({'Team': 'BOS'}, games)['key'] == '2026020199'  # earliest start


def test_matchup_targets_filtered_to_game_and_deduped():
    game = mc.find_game(GAMES, '2026020154')
    ranked = pd.DataFrame({'Player ID': ['3', '1'], 'Player': ['David Pastrnak', 'Filip Forsberg'], 'Team': ['BOS', 'NSH'], 'Statistical rank': [1, 30]})
    odds = pd.DataFrame({'player': ['Filip Forsberg'], 'decimal_price_improvement_pct': [7.25], 'best_odds': ['+300'], 'best_sportsbook': ['Book']})
    out = mc.matchup_targets(TARGETS, game, ranked, odds, {'id:3': 'Hot when predicted'}, leaders=['3'])
    assert set(out) == {'NSH', 'BOS'} and len(out['BOS']) == 1
    assert 'Artemi Panarin' not in str(out)
    labels = [b[0] for b in out['BOS'][0]['badges']]
    assert labels == ['Stats', 'Numbers', 'Overlap', 'Intel pick', 'Hot when predicted']
    fors = out['NSH'][0]
    assert fors['player'] == 'Filip Forsberg' and 'Odds +7.2%' in [b[0] for b in fors['badges']] or 'Odds +7.3%' in [b[0] for b in fors['badges']]
    assert mc.matchup_targets(TARGETS, None) == {}
    assert mc.matchup_targets([], game) == {'NSH': [], 'BOS': []}


def test_leakiest_goalie_ties_and_missing():
    rows = [{'Team': 'BOS', 'Goalie': 'A', 'GP': 3, 'GA': 9, 'GAA': 3.0}, {'Team': 'BOS', 'Goalie': 'B', 'GP': 5, 'GA': 15, 'GAA': 3.0},
            {'Team': 'BOS', 'Goalie': 'C', 'GP': 2, 'GA': 20, 'GAA': None}, {'Team': 'BOS', 'Goalie': 'D', 'GP': 0, 'GA': 0, 'GAA': None},
            {'Team': 'NSH', 'Goalie': 'E', 'GP': 4, 'GA': 8, 'GAA': 2.0}]
    assert mc.leakiest_goalie(rows, 'bos')['Goalie'] == 'B'  # tie on GAA -> more GA
    assert mc.leakiest_goalie(rows, 'TOR') is None
    assert mc.leakiest_goalie([{'Team': 'X', 'Goalie': 'C', 'GP': 2, 'GA': 5, 'GAA': float('nan')}], 'X')['Goalie'] == 'C'
    game = {'away': 'NSH', 'home': 'BOS'}
    assert mc.weaker_goalie_side(rows, game) == 'NSH'  # NSH shooters face BOS's leakier goalie
    assert mc.weaker_goalie_side(rows, {'away': 'NSH', 'home': 'TOR'}) is None
    assert mc.weaker_goalie_side(rows, None) is None
