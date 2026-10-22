import math

import pandas as pd
import pytest

import ui_theme_v53 as ui
from v54_testkit import slate


@pytest.mark.parametrize('raw,pct,text', [(0, 0.0, '0%'), (30.44, 30.44, '30%'), (49.5, 49.5, '50%'), (99.6, 99.6, '100%'),
                                          (100, 100.0, '100%'), (156.2, 100.0, '100%+'), ('72.4', 72.4, '72%')])
def test_conversion_and_rounding(raw, pct, text):
    assert ui.form_pct(raw) == pytest.approx(pct)
    assert ui.format_form_pct(raw) == text


@pytest.mark.parametrize('raw', [None, float('nan'), float('inf'), 'abc', '', True, [1]])
def test_missing_values_are_dash(raw):
    assert ui.form_pct(raw) is None
    assert ui.format_form_pct(raw) == '—'


def test_clipping_and_note_flag():
    assert ui.form_pct(-12) == 0.0 and ui.format_form_pct(-12) == '0%'
    assert ui.form_pct(250) == 100.0 and ui.form_clipped(250) and ui.form_clipped(-1) and not ui.form_clipped(80)


def test_monotonic_so_order_is_preserved():
    vals = [0, 5.5, 30, 99.9, 100]
    assert [ui.form_pct(v) for v in vals] == sorted(ui.form_pct(v) for v in vals)


def test_threshold_equivalence_overlap_eligibility():
    # The only form threshold in the app is `form > 0` (overlap / leader eligibility) -> Form % > 0 exactly.
    for raw in [0, 0.0001, 0.4, 1, 55, 140, -3]:
        assert (raw > 0) == (ui.form_pct(raw) > 0)


def test_with_form_pct_adds_numeric_column_and_keeps_raw():
    df = pd.DataFrame({'Player': ['A', 'B', 'C'], 'V3.2 Adjusted Index': [156.2, 50.0, None]})
    out = ui.with_form_pct(df)
    assert list(out.columns) == ['Player', 'Form %', 'V3.2 Adjusted Index']
    assert out['Form %'].tolist()[:2] == [100.0, 50.0] and math.isnan(out['Form %'].tolist()[2])
    assert pd.api.types.is_numeric_dtype(out['Form %'])
    assert out['V3.2 Adjusted Index'].equals(df['V3.2 Adjusted Index'])
    assert 'Form %' not in df.columns  # input not mutated
    assert ui.with_form_pct(out) is out  # idempotent
    other = pd.DataFrame({'x': [1]})
    assert ui.with_form_pct(other) is other


def test_column_config_is_numeric_percent():
    import streamlit as st
    cfg = ui.form_pct_config(st)
    assert 'Form %' in cfg
    assert 'Form %' in ui.form_pct_config(st, progress=True)


def test_rankings_unchanged_by_display_layer():
    ranked = pd.DataFrame(slate()['rankings'])
    before = ranked.copy()
    shown = ui.with_form_pct(ranked)
    assert ranked.equals(before)
    order_raw = ranked.sort_values('V3.2 Adjusted Index', ascending=False)['Player'].tolist()
    assert shown.sort_values('V3.2 Adjusted Index', ascending=False)['Player'].tolist() == order_raw


def test_cards_show_form_percent():
    row = ui.intel_card('statistical', 'TOP', {'Player': 'Jane', 'Team': 'BOS', 'V3.2 Adjusted Index': 64.6, 'Statistical rank': 1})
    assert '65%' in row and 'FORM %' in row
