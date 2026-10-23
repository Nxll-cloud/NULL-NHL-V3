"""V5.9: TOP PICK tie-break order (threat points -> model chance -> form -> shot rate -> raw English total -> player id,
never alphabetical) and the restored day rule (English OR Reverse digit equal to the universal day is a day match)."""
import pandas as pd

import gem_match_v58 as gmx
import gematria_log_v59 as gl
import numbers_v58_ui as nv
from numerology_v48 import gematria
from player_targets_v49 import DAY_METHODS, target_rows


def _p(pid, name, raw=3, form=50.0, shot=2.0, eng=100, **kw):
    return {'player_id': str(pid), 'player': name, 'team': 'BOS', 'threat_raw': raw, 'form': form, 'form_known': True,
            'shot_rate': shot, 'eng_total': eng, **kw}


def _first(ps, mp=None):
    return sorted(ps, key=lambda p: nv.pick_order(p, mp))[0]['player']


def test_stage1_threat_points_beat_everything():
    assert _first([_p(1, 'Aaa', raw=2, form=99, shot=9, eng=999), _p(2, 'Zzz', raw=3, form=0, shot=0, eng=1)], {'1': .9, '2': .01}) == 'Zzz'


def test_stage2_model_chance():
    assert _first([_p(1, 'Aaa', form=99, shot=9, eng=999), _p(2, 'Zzz', form=1, shot=0, eng=1)], {'1': .10, '2': .20}) == 'Zzz'
    assert _first([_p(1, 'Aaa'), _p(2, 'Zzz')], {'2': .05}) == 'Zzz'           # missing model chance ranks lowest


def test_stage3_form_index():
    mp = {'1': .2, '2': .2}
    assert _first([_p(1, 'Aaa', form=40, shot=9, eng=999), _p(2, 'Zzz', form=60, shot=0, eng=1)], mp) == 'Zzz'
    assert _first([_p(1, 'Aaa', form=-5.0), _p(2, 'Zzz', form_known=False, form=0.0)], mp) == 'Aaa'   # missing form lowest, even below negative


def test_stage4_shot_rate():
    mp = {'1': .2, '2': .2}
    assert _first([_p(1, 'Aaa', shot=1.5, eng=999), _p(2, 'Zzz', shot=3.0, eng=1)], mp) == 'Zzz'
    assert _first([_p(1, 'Aaa', shot=None), _p(2, 'Zzz', shot=0.2)], mp) == 'Zzz'
    assert _first([_p(1, 'Aaa', shot=float('nan')), _p(2, 'Zzz', shot=0.0)], mp) == 'Zzz'


def test_stage5_raw_english_total_then_id_never_name():
    mp = {'1': .2, '2': .2}
    assert _first([_p(1, 'Aaa', eng=120), _p(2, 'Zzz', eng=150)], mp) == 'Zzz'
    assert _first([_p(2, 'Aaa'), _p(1, 'Zzz')], mp) == 'Zzz'                   # full tie: player id (1 < 2), not the name
    assert _first([_p(2, 'Aaa'), _p(1, 'Zzz')]) == 'Zzz'
    picks = nv.top_picks_per_team([[_p(2, 'Aaa'), _p(1, 'Zzz'), _p(3, 'Mmm', shot=5)]], {})['BOS']
    assert [p['player'] for p in picks] == ['Mmm', 'Zzz']


def test_target_rows_carry_form_and_shot_rate():
    rows = pd.DataFrame([{'Player': 'Aa Bb', 'Team': 'MTL', 'Player ID': 1, 'V3.2 Adjusted Index': 12.5, 'Shots/G L5': 2.4, 'Shots/G L10': 3.0},
                         {'Player': 'Cc Dd', 'Team': 'MTL', 'Player ID': 2, 'V3.2 Adjusted Index': None, 'Shots/G L5': None, 'Shots/G L10': 1.1},
                         {'Player': 'Ee Ff', 'Team': 'MTL', 'Player ID': 3}])
    by = {r['player_id']: r for r in target_rows(rows, 'MTL', 'Montreal Canadiens', 'Bell Centre', '2026-10-23')}
    assert (by['1']['form'], by['1']['form_known'], by['1']['shot_rate']) == (12.5, True, 2.4)
    assert (by['2']['form'], by['2']['form_known'], by['2']['shot_rate']) == (0.0, False, 1.1)
    assert (by['3']['form_known'], by['3']['shot_rate']) == (False, None)


def test_reverse_day_match_restored_everywhere():
    assert DAY_METHODS == (('ordinal_root', 'English'), ('reverse_root', 'Reverse'))
    v = gematria('Cale Makar')
    assert (v['ordinal_root'], v['reverse_root']) == (2, 7)
    rows = pd.DataFrame([{'Player': 'Cale Makar', 'Team': 'COL', 'Player ID': 8480069, 'V3.2 Adjusted Index': 50}])
    t = target_rows(rows, 'COL', 'Colorado Avalanche', 'Ball Arena', '2026-10-23')[0]          # universal day 7
    assert t['day'] == ['Reverse']
    assert gmx.player_rows('Cale Makar', 7, None) == [('date', 7)]
    table, _ = gmx.match_table([{'game': {'arena': 'Ball Arena'}, 'away_targets': [t], 'home_targets': []}], 7)
    date_rows = [r for r in table if r['Match type'] == 'date']
    assert date_rows and gmx.rev_only(date_rows[0])
    h = gmx.table_html(table, [], 7)
    assert 'class="gm-rev"' in h and 'REV = Reverse cipher only' in h


def test_gematria_log_follows_the_restored_rule(monkeypatch):
    import player_targets_v49 as pt
    h = gl.method_hash()
    monkeypatch.setattr(pt, 'DAY_METHODS', (('ordinal_root', 'English'),))      # the narrowed rule hashes differently
    assert gl.method_hash() != h
