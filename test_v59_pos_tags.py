"""V5.9 position tags after player names on the Numbers tab (display only)."""
import pathlib
import re

import pandas as pd

import gem_match_v58 as gmx
import gematria_log_v59 as gemlog
import numbers_v58_ui as nv
import pos_tag_v59 as pt
import scorers_tonight_v58 as sctn
import ui_theme_v53 as ui

HERE = pathlib.Path(__file__).resolve().parent
RANKED = pd.DataFrame([
    {'Player': 'Mike Matheson', 'Player ID': 8476875, 'Team': 'MTL', 'Position': 'D'},
    {'Player': 'Josh Anderson', 'Player ID': 8476981, 'Team': 'MTL', 'Position': 'R'},
    {'Player': 'Gabriel Landeskog', 'Player ID': 8476455, 'Team': 'COL', 'Position': 'L'},
    {'Player': 'Jake Evans', 'Player ID': 8478133, 'Team': 'MTL', 'Position': 'C'},
    {'Player': 'Mystery Man', 'Player ID': 1, 'Team': 'MTL', 'Position': ''},
])
PMAP = pt.pos_map(RANKED)


def _p(pid, name, team, threat=50):
    return {'player': name, 'player_id': str(pid), 'team': team, 'tier': 'hot', 'colour': '#f00', 'threat': threat,
            'threat_raw': 3, 'matches': 1, 'day': ['English'], 'arena_matches': [], 'team_matches': [], 'form': 10,
            'values': {'ordinal_root': 7, 'reduction_root': 7, 'reverse_root': 2}, 'eng_total': 100}


def test_code_mapping_and_unknown():
    assert [pt.code(x) for x in ('C', 'L', 'R', 'D', 'G', 'lw', ' rw ')] == ['C', 'LW', 'RW', 'D', 'G', 'LW', 'RW']
    assert pt.code('') is None and pt.code(None) is None and pt.code('F') is None and pt.code(float('nan')) is None
    assert pt.tag(None) == '' and pt.tag('X') == ''
    assert '>LW</span>' in pt.tag('L') and 'class="npos"' in pt.tag('L')


def test_lookup_by_id_then_name_never_guess():
    assert pt.lookup(PMAP, '8476875') == 'D' and pt.lookup(PMAP, 8476981.0) == 'RW'
    assert pt.lookup(PMAP, None, 'COL', 'gabriel landeskog') == 'LW'
    assert pt.lookup(PMAP, '1', 'MTL', 'Mystery Man') is None          # blank position -> no tag
    assert pt.lookup(PMAP, '999', 'BOS', 'Nobody') is None
    assert pt.tag_for(None, '8476875') == ''


def test_goalie_uses_existing_pill_once():
    g = pt.tag('G')
    assert 'class="npg"' in g and 'npos' not in g and g.count('>G<') == 1
    gm = pd.DataFrame([{'Player': 'Sam Montembeault', 'Player ID': 5, 'Team': 'MTL', 'Position': 'G'}])
    row = nv.player_row(_p(5, 'Sam Montembeault', 'MTL'), None, pt.tag_for(pt.pos_map(gm), '5'))
    assert row.count('>G</span>') == 1


def test_board_row_has_tag_next_to_name_and_pick_badge():
    row = nv.player_row(_p(8476875, 'Mike Matheson', 'MTL'), 1, pt.tag_for(PMAP, '8476875'))
    assert re.search(r'<b class="npr-name">Mike Matheson</b><span class="npos"[^>]*>D</span><span class="npk pk1"', row)
    assert 'npos' not in nv.player_row(_p(1, 'Mystery Man', 'MTL'), None, pt.tag_for(PMAP, '1'))
    board = {'game': {'away': 'MTL', 'home': 'COL', 'arena': 'Ball Arena'}, 'players': [_p(8476455, 'Gabriel Landeskog', 'COL')],
             'all_players': None, 'arena_hit': False, 'arena_players': [], 'arena_root': 3, 'badge': 1}
    assert '>LW</span>' in nv.boards_html([board], 7, pmap=PMAP)
    assert 'npos' not in nv.boards_html([board], 7)                       # no map -> unchanged output


def test_match_table_and_targets_and_history_tags():
    rows = [{'Player': 'Josh Anderson', 'Match type': 'date', 'Number': 7, 'player_id': '8476981', 'team': 'MTL'}]
    out = gmx.table_html(rows, [], 7, pmap=PMAP)
    assert '<b>Josh Anderson</b><span class="npos"' in out and '>RW</span>' in out
    assert 'npos' not in gmx.table_html(rows, [], 7)
    tr = ui.target_row(1, 'Jake Evans', 'MTL', '8478133', 1, 10, 1, 0, 0, pos_tag=pt.tag_for(PMAP, '8478133'))
    assert 'Jake Evans<span class="npos"' in tr and '>C</span>' in tr
    nights = [{'status': 'ok', 'label': 'Fri', 'day': '2026-10-23', 'count': 1, 'of': 2, 'who': [('Mike Matheson', 'MTL', 1)]}]
    assert 'Mike Matheson<span class="npos"' in gemlog.strip_html(nights, pmap=PMAP)


def _record(name='Mike Matheson', pid=8476875, goals=1):
    return {'day': '2026-10-23', 'demo': False, 'names': {sctn.norm(name): pid},
            'players': {pid: {'name': name, 'goals': goals, 'game': 'MTL@COL', 'events': [{'time': 'P1 05:00'}]}}}


def test_scored_badge_still_attaches_once_with_tag():
    rec = _record()
    row = nv.player_row(_p(8476875, 'Mike Matheson', 'MTL'), 1, pt.tag_for(PMAP, '8476875'))
    marked = sctn.mark_html(row, rec)
    assert marked.count('class="npsc') == 1
    assert re.search(r'Mike Matheson<span class="npsc[^"]*"[^>]*>[^<]*</span></b><span class="npos"', marked)
    assert sctn.mark_html(marked, rec).count('class="npsc') == 1            # second pass adds nothing
    tbl = gmx.table_html([{'Player': 'Mike Matheson', 'Match type': 'date', 'Number': 7, 'player_id': '8476875', 'team': 'MTL'}], [], 7, pmap=PMAP)
    assert sctn.mark_html(tbl, rec).count('class="npsc') == 1
    tr = ui.target_row(1, 'Mike Matheson', 'MTL', '8476875', 1, 10, 1, 0, 0, pos_tag=pt.tag_for(PMAP, '8476875'))
    assert sctn.mark_html(tr, rec).count('class="npsc') == 1


def test_numbers_tab_wires_every_list():
    src = (HERE / 'tabs' / 'numbers.py').read_text()
    for needle in ('boards_html(_nb_boards,_day_num,_nb_mp,pmap=_num_pmap)', "loaded=_gm_targets is not None,pmap=_num_pmap)",
                   'pos_tag=_postag.tag_for(_num_pmap,', "strip_html(gemlog.last_n_days(3,'arena',np_day),pmap=_num_pmap)",
                   "'Pos':_postag.code(player.get('Position'))"):
        assert needle in src, needle


def test_css_rule_present():
    assert re.search(r'\.npos\{[^}]*white-space:nowrap', (HERE / 'assets' / 'v58.css').read_text())
