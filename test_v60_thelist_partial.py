"""the list: partial 1-2 game cards keep strict filters, no payout; full card unchanged; no Nyah branding."""
import pytest
import strict_card_v60 as sc
import strict_card_ui_v60 as ui
import strict_ledger_v60 as lg
from test_v60_strict_card import pool, NOW


def only(n):
    cs, ctx, q = pool()
    gids = sorted({c['game_id'] for c in cs})[:n]
    return [c for c in cs if c['game_id'] in gids], ctx, q


@pytest.mark.parametrize('n', [0, 1, 2, 3])
def test_counts(n):
    cs, ctx, q = only(n)
    rec = sc.build('2026-11-07', cs, ctx, q, NOW)
    html = ui.section_html(rec)
    assert '<h3>the list</h3>' in html
    if n == 3:
        assert len(rec['legs']) == 3 and 'partial_legs' not in rec
        assert 'Estimated independent-leg combined decimal price' in html and 'Partial card' not in html
    elif n == 0:
        assert not rec['legs'] and 'No qualifying 3-game card' in html
    else:
        assert rec['legs'] == [] and len(rec['partial_legs']) == n
        assert len({c['game_id'] for c in rec['partial_legs']}) == n
        assert f'Partial card · {n} of 3 legs' in html and 'combined decimal price' not in html
        assert 'no combined price shown' in html


def test_best_one_per_game():
    cs, ctx, q = only(2)
    rec = sc.build('2026-11-07', cs, ctx, q, NOW)
    for leg in rec['partial_legs']:
        assert leg['p'] == max(c['p'] for c in cs if c['game_id'] == leg['game_id'])


def test_filters_not_weakened_partial_explains():
    cs, ctx, q = pool()
    bad = {c['game_id'] for c in cs[2:]}
    q['rows'] = [r for r in q['rows'] if r['game'] not in {f"{c['team']} @ {c['opp']}" for c in cs if c['game_id'] in bad and not c['home']}]
    rec = sc.build('2026-11-07', cs, ctx, q, NOW)
    assert not rec['legs'] and {c['game_id'] for c in rec['partial_legs']} == {cs[0]['game_id']}
    assert 'no supported fresh real quote' in ui.section_html(rec)


@pytest.mark.parametrize('name', [None, '', '  ', 5])
def test_missing_name_rejected(name):
    cs, ctx, q = pool()
    for c in cs:
        c['name'] = name
    rec = sc.build('2026-11-07', cs, ctx, q, NOW)
    assert not rec['legs'] and not rec.get('partial_legs') and rec['reasons'].get('missing player name')
    assert 'None (' not in ui.section_html(rec)


def test_full_card_record_unchanged_and_ledger():
    rec = sc.build('2026-11-07', *pool(), NOW)
    assert 'partial_legs' not in rec and sc.digest(rec) == rec['id']
    with pytest.raises(ValueError):
        lg.add([], sc.build('2026-11-07', *only(2), NOW), 'card', None, None, '', False, NOW)


def test_no_nyah_branding():
    for n in (1, 3):
        html = ui.section_html(sc.build('2026-11-07', *only(n), NOW))
        assert 'Nyah' not in html and 'The List' not in html and 'strict 3-game card' not in html
