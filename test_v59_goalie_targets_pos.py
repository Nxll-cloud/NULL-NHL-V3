"""V5.9 position tag after each player name in Home's Matchup targets (the rows under each opposing goalie). Display only.
Position = the rankings 'Position' column (NHL roster positionCode) carried by v55_state.build_state; unknown -> no tag."""
import pathlib
import re


import v55_ui as v5

HERE = pathlib.Path(__file__).resolve().parent


def _p(pos, name='Some Player'):
    return {'player': name, 'player_id': '8470000', 'team': 'MTL', 'form_pct': 50, 'form_label': '50%', 'stat_rank': 3,
            'matches': 0, 'badges': [], 'jersey': 22, 'log': [], 'position': pos}


def test_target_row_tags_nhl_codes():
    for raw, shown in (('C', 'C'), ('L', 'LW'), ('R', 'RW'), ('D', 'D')):
        html = v5.target_row('20262027', 1, _p(raw))
        assert f'Some Player</span><span class="npos"' in html and f'>{shown}</span></b>' in html
        assert 'class="npg"' not in html


def test_unknown_position_no_tag_and_goalie_single_pill():
    for raw in (None, '', 'F', float('nan')):
        html = v5.target_row('20262027', 1, _p(raw))
        assert 'class="npos"' not in html and 'class="npg"' not in html
    g = v5.target_row('20262027', 1, _p('G'))
    assert g.count('class="npg"') == 1 and 'class="npos"' not in g and '>G</span>' in g


def test_name_is_escaped_and_truncates_separately():
    html = v5.target_row('20262027', 1, _p('R', "Kirby D'Astous <x>"))
    assert '<b class="tnp"><span class="tnn">Kirby D&#x27;Astous &lt;x&gt;</span>' in html




def test_matchup_section_tags_every_listed_player():
    fg = {'key': '1', 'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T23:00:00Z', 'game_id': '1'}
    data = {'season': '20262027', 'featured': fg, 'weak_side': None, 'goalies': {},
            'targets': {'MTL': [_p('R', 'Cole Caufield'), _p('D', 'Mike Matheson'), _p(None, 'No Data')], 'CHI': [_p('C', 'Connor Bedard')]}}
    html = v5.matchup_section(data)
    assert 'Cole Caufield</span><span class="npos" title="Right wing" aria-label="Right wing">RW</span>' in html
    assert 'Mike Matheson</span><span class="npos" title="Defenseman" aria-label="Defenseman">D</span>' in html
    assert 'Connor Bedard</span><span class="npos" title="Center" aria-label="Center">C</span>' in html
    assert 'No Data</span></b>' in html                       # unknown -> nothing guessed


def test_build_state_carries_rankings_position():
    """targets come from the rankings rows; Position is copied as-is (L/R/C/D), never guessed."""
    src = (HERE / 'v55_state.py').read_text(encoding='utf-8')
    assert "'position': rows.get(_pid(p.get('player_id')), {}).get('Position')" in src


def test_css_rule_present_and_sanitizer_safe():
    css = (HERE / 'assets' / 'v58.css').read_text(encoding='utf-8')
    assert '.v55 .tn b.tnp{display:flex' in css and '.v55 .tn b.tnp .tnn{' in css
    assert '@media (max-width:420px){.v55 .tn b.tnp{display:block;white-space:normal' in css   # phones: wrap, no 'Jord…'
    assert not re.search(r'<[/\w!]', css)
    v5.design_css('dark')   # raises if st.html would strip the style block
