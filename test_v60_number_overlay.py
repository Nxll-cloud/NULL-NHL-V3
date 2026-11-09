"""Display-only English-root overlay on the existing post-limit/post-pinning Numbers rows."""
from copy import deepcopy
from pathlib import Path
import hashlib
import numbers_v58_ui as nv


def player(pid,team,root,raw,name=None):
    return {'player_id':str(pid),'player':name or f'OverlayPlayer{pid}','team':team,
            'values':{'ordinal_root':root,'reduction_root':root,'reverse_root':4},
            'day':[],'arena_matches':[],'team_matches':[],'matches':0,'form':30,
            'threat_raw':raw,'threat':round(raw/6*100),'tier':'cool','colour':'#64748b',
            'eng_total':100+pid,'shot_rate':2}


def board(second_root=4):
    ps=[player(1,'TOR',2,6),player(2,'TOR',second_root,5),player(3,'TOR',6,4),
        player(4,'BOS',5,6),player(5,'BOS',7,5),player(6,'BOS',9,4)]
    return {'game':{'away':'TOR','home':'BOS','arena':'','start':''},'players':[ps[0]],'all_players':ps,
            'badge':6,'arena_hit':False,'arena_players':[],'arena_root':None}


def test_off_parity_with_committed_renderer_snapshot_and_no_mutation():
    boards=[board()];before=deepcopy(boards)
    html=nv.boards_html(boards,9,overlay=False)
    assert html==nv.boards_html(boards,9)
    assert hashlib.sha256(html.encode()).hexdigest()==BASELINE_HASH
    nv.boards_html(boards,9,overlay=True)
    assert boards==before
    assert nv.boards_html(boards,9,overlay=False)==html


def test_on_filters_actual_current_rows_without_promotion_rerank_or_badge_change():
    b=board();html=nv.boards_html([b],9,overlay=True)
    assert nv.overlay_counts([b])==(4,1) # Limit one + existing per-team top-two pinning.
    assert 'OverlayPlayer2' in html and 'OverlayPlayer1' not in html
    assert 'OverlayPlayer3' not in html and 'OverlayPlayer6' not in html # Matching alternates are NOT backfilled.
    assert 'English root = 4' in html and 'Overlay match' in html
    assert 'Overlay ON · 1 of 4 current selections shown' in html
    assert 'RUNNER-UP</span>' in html # Existing second pick is not promoted to top pick.
    assert '⚑ 6 threats' in html # Baseline hot/threat badge remains untouched.
    assert b['all_players'][1]['threat_raw']==5


def test_english_only_zero_explicit_missing_not_zero_no_new_digit_transforms():
    for value in (None,'',float('nan'),float('inf'),True,False):
        assert nv.overlay_match(player(1,'TOR',value,1)) is None
    assert nv.overlay_match(player(1,'TOR',0,1))=='English root = 0'
    assert nv.overlay_match(player(1,'TOR','0',1))=='English root = 0'
    assert nv.overlay_match({'values':{}}) is None
    assert nv.overlay_match({'values':None}) is None
    assert nv.overlay_match(player(1,'TOR',2,1)) is None # Reverse field is 4; it must NOT count.
    assert nv.overlay_match(player(1,'TOR',1,1)) is None # Literal 10 is not reduced to 1.
    assert nv.overlay_match(player(1,'TOR',4.5,1)) is None
    for value in (4,10,9,3,6):
        assert nv.overlay_match(player(1,'TOR',value,1))==f'English root = {value}'


def test_no_matches_zero_not_fallback_and_source_is_existing_fields():
    b=board()
    for p in b['all_players']:p['values']['ordinal_root']=2
    assert nv.overlay_counts([b])==(4,0)
    html=nv.boards_html([b],9,overlay=True)
    assert '0 overlay matches in the current selection.' in html
    assert 'OverlayPlayer' not in html
    assert nv.overlay_counts([])==(0,0)


def test_integration_default_off_scope_and_slate_key():
    src=Path('tabs/numbers.py').read_text()
    # t191: the single 4,10,0,9,3,6 toggle migrated into per-day registry toggles (label/key legitimately changed;
    # the 2026-11-07 entry is the same numbers, now one of several independent default-OFF filters).
    assert "value=False,key=_num_dp.toggle_key(np_day,_e['date'])" in src
    assert 'overlay=_num_sel) if _num_overlay else' in src and 'numv58.overlay_counts(_nb_boards,_nb_mp,patterns=_num_sel)' in src
    assert src.index('_nb_mp=numv58.model_p_from_results')<src.index('_num_sel=[')<src.index('overlay=_num_sel) if _num_overlay else')
    assert 'after the existing per-game limit and top-pick pinning' in src
    assert nv.overlay_key('2026-11-07')!=nv.overlay_key('2026-11-08')
    reference=nv.reference_patterns_html()
    assert 'Possible date mapping: October 9th, 36.' in reference
    assert '2-21, 22, 20' in reference
    assert nv.FOLLOW_PATTERN==(4,10,0,9,3,6)


def test_streamlit_toggle_off_on_off_and_new_slate_data_reset():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('''
import streamlit as st
import numbers_v58_ui as nv
from test_v60_number_overlay import board
slate=st.selectbox('Slate',['2026-11-07','2026-11-08'])
boards=[board(4 if slate=='2026-11-07' else 2)]
on=st.toggle('Apply overlay',value=False,key=nv.overlay_key(slate))
base,matches=nv.overlay_counts(boards)
st.caption(f'Baseline {base}; matching {matches}; shown {matches if on else base}')
st.markdown(nv.boards_html(boards,9,overlay=on),unsafe_allow_html=True)
''').run()
    assert not app.exception and not app.toggle[0].value
    baseline=app.markdown[0].value
    assert 'OverlayPlayer1' in baseline and 'shown 4' in app.caption[0].value
    app.toggle[0].set_value(True).run()
    assert not app.exception and 'OverlayPlayer1' not in app.markdown[0].value
    assert 'OverlayPlayer2' in app.markdown[0].value and 'shown 1' in app.caption[0].value
    app.toggle[0].set_value(False).run()
    assert app.markdown[0].value==baseline
    app.toggle[0].set_value(True).run()
    app.selectbox[0].set_value('2026-11-08').run()
    assert not app.exception and not app.toggle[0].value
    assert 'matching 0' in app.caption[0].value
    app.toggle[0].set_value(True).run()
    assert '0 overlay matches' in app.markdown[0].value


# Byte-for-byte baseline generated from the original committed renderer (14876ae), same fixture.
BASELINE_HASH = 'b3f6bf681c8ce395d35d8c53a4b7fc12c63a3d056c9a83ff8abe72af9ec3b591'
