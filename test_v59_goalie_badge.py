"""V5.9: Home 'G' goalie pill. Goalie status from position data only; skaters and missing positions get none. Offline."""
from datetime import datetime, timezone

import goalies_v54 as gk
import longshot_v58 as ls
import parlay_v58 as parlay
import position_badge_v59 as pb
import probable_goalies_v54 as pgk
import v55_ui as v5
from v54_testkit import HERE

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def test_goalie_badge_from_position_only():
    assert 'class="npg"' in pb.goalie_badge('G') and '>G</span>' in pb.goalie_badge('g ')
    assert 'class="npg"' in pb.goalie_badge({'abbreviation': 'G'})
    for pos in ('C', 'L', 'R', 'D', 'F', 'Goalie Guy', '', None, 0):
        assert pb.goalie_badge(pos) == '', pos
    assert pb.position_of({'Position': 'G'}) == 'G' and pb.position_of({'pos': 'D'}) == 'D'
    assert pb.position_of({'goalie': 'Name Only'}) is None and pb.goalie_badge(pb.position_of({'goalie': 'Name Only'})) == ''
    assert pb.goalie_row_class('G') == ' is-g' and pb.goalie_row_class('C') == '' and pb.goalie_row_class(None) == ''


def test_sources_record_goalie_position():
    rows = gk.parse_club_goalies({'goalies': [{'playerId': 1, 'firstName': {'default': 'A'}, 'lastName': {'default': 'Keeper'},
                                               'gamesPlayed': 2, 'goalsAgainst': 3, 'shotsAgainst': 50, 'timeOnIce': 7200}]}, 'bos')
    assert rows[0]['Position'] == 'G'
    box = {'id': 9, 'awayTeam': {'abbrev': 'BOS'}, 'homeTeam': {'abbrev': 'NSH'},
           'playerByGameStats': {'awayTeam': {'goalies': [{'playerId': 1, 'name': {'default': 'A. Keeper'}, 'starter': True}]},
                                 'homeTeam': {'goalies': []}}}
    assert pgk.parse_nhl_boxscore(box)['BOS']['position'] == 'G'
    assert 'position' not in pgk.unknown('9', 'NSH')                    # no starter -> no position -> no badge


def _board(starter):
    g = {'key': 'BOS@NSH', 'away': 'BOS', 'home': 'NSH', 'start': '2026-10-23T00:00:00Z', 'game_id': '1'}
    return v5.scoreboard({'games': [g], 'starters': {'BOS@NSH': {'BOS': starter, 'NSH': {'status': 'unknown'}}}}, NOW)


def test_board_pill_for_starter_with_position_only():
    html = _board({'goalie': 'Jeremy Swayman', 'status': 'confirmed', 'position': 'G'})
    assert html.count('class="npg"') == 1 and 'Swayman</span><span class="npg"' in html
    assert 'class="npg"' not in _board({'goalie': 'Jeremy Swayman', 'status': 'confirmed'})     # no position data


def _p(pos):
    return {'player': 'Some Player', 'player_id': '1', 'team': 'BOS', 'opponent': 'NSH', 'position': pos, 'form_pct': 50,
            'form_label': '50', 'stat_rank': 1, 'log': []}


def test_leader_cards_and_target_rows():
    assert 'class="npg"' in v5.player_card('20262027', 'Test', 'stat', _p('G'), '', '', '')
    assert 'is-g' in v5.player_card('20262027', 'Test', 'stat', _p('G'), '', '', '')
    for pos in ('C', None):
        assert 'class="npg"' not in v5.player_card('20262027', 'Test', 'stat', _p(pos), '', '', '')
        assert 'class="npg"' not in v5.target_row('20262027', 1, _p(pos))
    assert 'Some Player</span><span class="npg"' in v5.target_row('20262027', 1, _p('G'))


def test_goalie_card_and_duel():
    s = {'Goalie': 'A Keeper', 'Player ID': '1', 'Team': 'BOS', 'GP': 2, 'GA': 3, 'GAA': 2.5, 'SV%': .91}
    g = {'leakiest': dict(s, Position='G')}
    assert 'A Keeper<span class="npg"' in v5.goalie_card('20262027', 'BOS', g, 'leaky')
    assert 'class="npg"' not in v5.goalie_card('20262027', 'BOS', {'leakiest': s}, 'leaky')


def _c(pos):
    c = {'pid': 5, 'name': 'Long Guy', 'team': 'BOS', 'opp': 'NSH', 'home': False, 'game': 'g1', 'game_id': '1', 'start': None,
         'phase': 'pregame', 'p': .15, 'p_next': None, 'np_rank': None, 'form': None, 'model_rank': 1, 'why': ['x'], 'signals': []}
    if pos is not None:
        c['position'] = pos
    return c


def test_long_shot_and_parlay_pill():
    assert 'Long Guy<span class="npg"' in ls.section_html(_c('G'))
    assert 'class="npg"' not in ls.section_html(_c('R')) and 'class="npg"' not in ls.section_html(_c(None))
    d = {'legs': [_c('G'), dict(_c('C'), pid=6, name='Skater Guy', game='g2')], 'joint': .02, 'per': 'game'}
    assert parlay.section_html(d, {}, {}).count('class="npg"') == 1


def test_goalie_pill_css():
    css = (HERE / 'assets' / 'v58.css').read_text()
    assert '.v55 .npg{' in css and 'white-space:nowrap' in css.split('.v55 .npg{')[1].split('}')[0]
    assert 'font:700 12px' in css and '.v55 .npg' in (HERE / 'assets' / 'mobile.css').read_text()


def test_espn_position_shapes():
    assert pgk._espn_position({'abbreviation': 'G'}) == 'G' and pgk._espn_position('G') == 'G' and pgk._espn_position(None) == 'G'


def test_board_tile_layout_keeps_pill_inside():
    css = (HERE / 'assets' / 'v58.css').read_text()
    assert '.v55 .tile .row>.sg{grid-column:2/-1;grid-row:2' in css and '.v55 .tile .row>.scr{grid-column:3;grid-row:1}' in css
    assert 'text-overflow:ellipsis' in css.split('.v55 .sg .sgn{')[1].split('}')[0]
