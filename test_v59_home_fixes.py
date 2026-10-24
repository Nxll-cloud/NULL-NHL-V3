"""V5.9 Home fixes: featured board tile spacing + Live next goal strip opens the Live Next Goal tab."""
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
