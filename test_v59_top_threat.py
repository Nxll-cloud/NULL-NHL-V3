"""V5.9 Matchup Center TOP THREAT marker (top_threat_v59 + v56_ui.goalie_threats). Display only."""
import goalie_pos_v59 as gpos
import top_threat_v59 as tt
import v56_ui as v56


def _mark(c, l, r, d):
    """marker() from real-shaped split data: goals per position (shots = 10x goals)."""
    sp = {p: {'shots': g * 10, 'goals': g} for p, g in zip(gpos.POS, (c, l, r, d))}
    return gpos.marker({'split': sp, 'games': 50, 'window': '2025-26 + 2026-27'})


def _t(name, pos, p):
    return {'pid': name, 'name': name, 'pos': pos, 'p_next': p, 'rank': 1, 'h2h': None}


THREATS = [_t('A', 'L', .060), _t('B', 'C', .045), _t('C1', 'C', .039), _t('W', 'R', .050), _t('D1', 'D', .030)]


def test_rule_marks_highest_threat_in_top_giveup_position():
    m = _mark(20, 8, 9, 5)                      # most goals on him: centers
    assert tt.top_position(m) == 'C'
    assert tt.marked(THREATS, m) == [1]         # B (C, 4.5%), not A (higher % but LW)
    m = _mark(5, 8, 20, 4)                      # most: R -> RW; NHL code 'R' on the threat maps to RW
    assert tt.top_position(m) == 'RW'
    assert tt.marked(THREATS, m) == [3]
    assert tt.marked([_t('X', 'RW', .02)], m) == [0]   # 'RW' spelling maps the same way


def test_tie_marks_all_at_shown_precision():
    m = _mark(20, 8, 9, 5)
    ts = [_t('F', 'C', .0391), _t('J', 'C', .0389), _t('S', 'C', .031), _t('L', 'L', .05)]
    assert tt.marked(ts, m) == [0, 1]           # both show 3.9%


def test_none_in_position_marks_nothing():
    m = _mark(20, 8, 9, 5)
    ts = [_t('P', 'L', .048), _t('K', 'R', .044), _t('Q', 'D', .029), _t('Gen', 'F', .05), _t('N', '', .04)]
    assert tt.marked(ts, m) == []
    html = v56.goalie_threats({'name': 'Jake Allen'}, 'NJD', ts, '20262027', '', pos_mark=m)
    assert 'TOP THREAT' not in html and 'gtr top' not in html and 'most G: C' in html


def test_no_position_data_marks_nothing():
    assert tt.marked(THREATS, None) == []
    assert tt.marked(THREATS, gpos.marker({'split': {}})) == []
    assert tt.marked(THREATS, _mark(5, 4, 3, 2)) == []      # < MIN_GOALS_SHARE goals -> no top position
    assert tt.marked([_t('B', 'C', None)], _mark(20, 8, 9, 5)) == []
    html = v56.goalie_threats({'name': 'G'}, 'NYR', THREATS, '20262027', '', pos_mark=None)
    assert 'TOP THREAT' not in html and 'gpos' not in html


def test_card_renders_badge_on_marked_row_only():
    m = _mark(20, 8, 9, 5)
    html = v56.goalie_threats({'name': 'Darcy Kuemper'}, 'LAK', THREATS, '20262027', '', pos_mark=m)
    assert html.count('class="gtr top"') == 1 and html.count('TOP THREAT · C') == 1
    row = html.split('class="gtr top"')[1].split('class="gtr')[0]
    assert '<b>B</b>' in row and 'class="ttop"' in row
    css = open('assets/v56.css').read()
    assert '.v55 .gtr .ttop{grid-column:3/-1' in css   # own grid line: % / H2H columns keep the V5.9 alignment
