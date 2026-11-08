"""Only panel section colours change; labels, state gates and model output stay intact."""
from copy import deepcopy
from pathlib import Path
import re

import pytest

import live_nextgoal_v56 as ng
import live_state_v56 as ls
import v56_ui as ui
from test_v56_model import PRIORS, payload, play

ROOT = Path(__file__).resolve().parent


@pytest.mark.parametrize('state,ptype,warning', [('LIVE', 'REG', ''), ('LIVE', 'REG', 'Awaiting feeds'),
                                                ('FINAL', 'REG', ''), ('OFF', 'OT', ''), ('LIVE', 'SO', '')])
def test_two_colour_hooks_keep_content_and_state_behavior(state, ptype, warning):
    game = ng.parse_pbp(payload([play(1, 'goal')], state=state, ptype=ptype))
    result = ng.model(game, PRIORS)
    if warning:
        result.update(candidates_active=False, feed_warning=warning)
    untouched = deepcopy(result)
    html = ui.nextgoal_panel(result, '20262027')
    assert result == untouched
    assert html.count('class="ngnote ng-last-confirmed"') == 1
    assert html.count('class="ngnote ng-current-candidates"') == 1
    assert '<p class="ngnote ng-last-confirmed">Last confirmed scorer: A1 X (AAA)' in html
    assert 'Previous scorers remain eligible to score again.' in html
    assert 'PBP game clock:' in html and 'local fetch time unavailable' in html
    active = state == 'LIVE' and ptype == 'REG' and not warning
    assert ('Current next-goal candidates' in html) == bool(active)
    assert ('<small>next goal</small>' in html) == bool(active)
    assert ('Historical skater summary' in html) == (state in ('FINAL', 'OFF') or ptype == 'SO')


def test_accents_are_distinct_existing_palette_tokens_and_scoped_colour_only():
    css = (ROOT / 'assets/v56.css').read_text()
    marker = '/* Next-goal panel: history (violet) versus current candidates (cyan); no geometry changes. */'
    rules = css.split(marker)[1]
    parsed = re.findall(r'([^{}]+)\{([^{}]+)\}', rules)
    assert len(parsed) == 4
    assert all(selector.strip().startswith('.v55 .ngp-wrap .ngnote') for selector, _ in parsed)
    assert '.ngnote.ng-last-confirmed{--ng-section-accent:var(--neon2)}' in rules
    assert '.ngnote.ng-current-candidates{--ng-section-accent:var(--neon)}' in rules
    assert 'var(--ink)' in rules and 'color-mix(in srgb,var(--ng-section-accent) 8%,transparent)' in rules
    assert 'box-shadow:inset 0 -2px 0' in rules
    allowed = {'--ng-section-accent', 'color', 'background', 'box-shadow'}
    for _, declarations in parsed:
        assert all(part.split(':', 1)[0].strip() in allowed for part in declarations.split(';') if part.strip())


@pytest.mark.parametrize('theme', ['dark', 'light', 'contrast'])
def test_all_themes_supply_adaptive_accents_without_mobile_geometry_changes(theme):
    import v55_ui as v5
    css = v5.design_css(theme)
    assert '--neon:' in css and '--neon2:' in css and '--ink:' in css
    assert '.ngnote.ng-last-confirmed' in css and '.ngnote.ng-current-candidates' in css
    assert 'ng-last-confirmed' not in (ROOT / 'assets/mobile.css').read_text()
    assert 'ng-current-candidates' not in (ROOT / 'assets/mobile.css').read_text()
