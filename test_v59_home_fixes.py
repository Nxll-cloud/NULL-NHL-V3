"""V5.9 Home fixes: featured board tile spacing + Live next goal strip (now on the Live Next Goal tab, no tap-jump there; opens the tab elsewhere)."""
import pathlib
import v56_ui as v56
import v55_ui as v5

ROOT = pathlib.Path(__file__).parent
ITEMS = [{'away': 'AAA', 'home': 'HHH', 'phase': 'live', 'label': 'P1 10:00', 'away_score': 0, 'home_score': 1,
          'leader': {'name': 'A1 Xyz', 'p_next': 0.15}}]


def test_live_strip_is_one_accessible_tap_target():
    h = v56.live_strip(ITEMS)
    assert 'data-ngtab="Live Next Goal"' in h and 'role="link"' in h and 'tabindex="0"' in h
    assert 'aria-label="Open the Live Next Goal tab"' in h and 'class="lstrip"' in h
    assert 'next: Xyz 15%' in h                       # data unchanged
    assert v56.live_strip([]) == ''


def test_js_routes_strip_taps_and_enter_to_the_tab_without_touching_threat_badges():
    js = (ROOT / 'assets' / 'v55.js').read_text()
    assert "closest('[data-ngtab]')" in js and "'keydown'" in js and "ev.key !== 'Enter'" in js
    assert "closest('a[data-ng]')" in js             # threat-badge handler still present (and wins inside the strip)
    v5.check_sanitizer_safe('js', js)


def test_featured_label_has_its_own_line():
    css = (ROOT / 'assets' / 'v58.css').read_text()
    assert '.v55 .tile.feat:before{position:static;display:block' in css
    assert '.v55 .ngjump{cursor:pointer' in css
    v5.check_sanitizer_safe('css', v5.design_css('dark'))


def test_strip_without_jump_has_no_tap_affordance_and_same_data():
    h = v56.live_strip(ITEMS, jump=False)
    for bad in ('data-ngtab', 'ngjump', 'role="link"', 'tabindex', 'aria-label="Open', 'tap to open'):
        assert bad not in h, bad
    assert 'class="lstrip"' in h and 'next: Xyz 15%' in h and 'Live next goal' in h
    assert v56.live_strip([], jump=False) == ''


def test_strip_moved_from_home_to_live_next_goal_tab_below_banner():
    home = (ROOT / 'tabs' / 'home.py').read_text()
    assert 'live_strip' not in home                   # gone from Home entirely
    ng = (ROOT / 'tabs' / 'nextgoal.py').read_text()
    body = ng.split('"""', 2)[2]                      # code after the module docstring
    code = [l for l in body.splitlines() if l.strip() and not l.lstrip().startswith('#')]
    assert code[0].startswith("st.markdown(v5.tab_head('NULL’S PLAYBOOK · LIVE','Live Next Goal'")   # banner first
    assert code[2].startswith('if _v56_results:')                                                     # strip second
    assert code[3].strip() == 'v5.html_block(st,v56.live_strip(lstate.strip_items(_v56_results),jump=False))'
    assert ng.index('v5.tab_head(') < ng.index('live_strip(')  # strip directly below the tab header
