"""V6.0: scored-tonight pills on the Prediction Models tab's four top-10 lists (display only, player-ID match).
Reuses scorers_tonight_v58 (the record built from the polled play-by-play). Offline."""
import json
import re
from pathlib import Path

import accuracy_v58 as acc
import prediction_models_v59 as pm
import scorers_tonight_v58 as sctn

ROOT = Path(__file__).resolve().parent


def _rows(pids, prefix):
    return [{'rank': i, 'pid': p, 'name': f'{prefix} {p}', 'team': 'AAA', 'pos': '', 'stat': '10.0%', 'layers': ''}
            for i, p in enumerate(pids, 1)]


def _t():
    return {'model': {'source': 'frozen pre-game model', 'rows': _rows([1, 2, 3, 4], 'Model')},
            'np': {'source': 'NP', 'rows': _rows([5, 1, 6, 7], 'Np')},
            'blend': {'source': 'frozen', 'rows': _rows([2, 8, 1, 9], 'Blend')},
            'books': {'source': 'books', 'rows': _rows([10, 11, 1, 12], 'Books')}}


def _rec(goals, demo=False, day='2026-10-24'):
    """goals {pid: n} -> a scorer record built by the real from_pbp parser (one synthetic game)."""
    ev, eid = [], 0
    for pid, n in goals.items():
        for _ in range(n):
            eid += 1
            ev.append({'kind': 'goal', 'eid': eid, 'shooter': pid, 'team': 'AAA', 'period': 1, 'ptype': 'REG', 'secs': 60 * eid,
                       'strength': 'EV', 'goalie': 99})
    roster = {pid: {'name': f'Player {pid}', 'team': 'AAA'} for pid in goals}
    return sctn.from_pbp({'g1': {'game_id': 'g1', 'away': 'AAA', 'home': 'HHH', 'roster': roster, 'events': ev}}, day, demo)


def _cols(h):
    return re.findall(r'<div class="pmc".*?(?=<div class="pmc"|$)', h, re.S)


def _badged(col):
    """pids of rows carrying a pill, from 'prefix pid</b><span class="npsc'."""
    return [int(m) for m in re.findall(r' (\d+)</b><span class="npsc', col)]


def test_scored_rows_badged_in_all_four_systems_by_id():
    h = pm.page_html(_t(), [], record=_rec({1: 1, 8: 2}))
    cols = _cols(h)
    assert len(cols) == 4
    assert [sorted(_badged(c)) for c in cols] == [[1], [1], [1, 8], [1]]   # model, np, blend, books
    assert h.count('class="npsc') == 5 and h.count('class="npsc multi') == 1 and '🚨 2G' in h and h.count('🚨 G<') == 4
    assert h.count('class="pmr sc"') == 5                                  # same rows keep the green name
    assert 'Scored tonight (AAA @ HHH)' in h                               # shared tooltip


def test_no_badge_when_nobody_scored():
    for rec in (None, _rec({}), sctn.empty('2026-10-24')):
        h = pm.page_html(_t(), [], record=rec)
        assert 'class="npsc' not in h and 'pmr sc' not in h
    assert pm.page_html(_t(), []) == pm.page_html(_t(), [], record=_rec({}))   # identical to the no-record page


def test_matching_is_by_player_id_not_name():
    t = _t()
    t['model']['rows'][1]['name'] = 'Player 1'            # same name as the scorer, different id (2)
    rec = _rec({1: 1})
    h = pm.page_html(t, [], record=rec)
    model = _cols(h)[0]
    assert _badged(model) == [1] and 'Player 1</b><span class="npsc' not in model
    assert pm.scored_badge(rec, '1') and pm.scored_badge(rec, 1.0) and not pm.scored_badge(rec, 2)
    assert pm.scored_badge(rec, None) == '' and pm.scored_badge(None, 1) == ''


def test_demo_record_marks_badge_as_demo():
    h = pm.page_html(_t(), [], record=_rec({1: 1}, demo=True))
    assert 'class="npsc demo"' in h and 'DEMO replay' in h


def test_real_frozen_lists_badge_scorers_and_leave_frozen_data_unchanged():
    """Oct 23's frozen pre-game lists + that night's real scorers: every listed scorer (by id) gets a pill; the
    frozen entry / blend record and their hashes are untouched by rendering."""
    day = '2026-10-23'
    snap = acc._load_snap(day, ROOT / 'snapshots')
    ent = acc.load_entry(day, ROOT / 'snapshots' / 'accuracy')
    rec = pm.build(ent, snap, 'rebuilt', 'test')
    before = json.dumps([ent, rec], sort_keys=True, default=str)
    t = pm.tonight(day, snap['rankings'], snap['games'], ent, rec)
    goals = {int(s[0]): int(s[3]) for s in ent['results']['scorers']}
    srec = _rec(goals, day=day)
    h = pm.page_html(t, [], record=srec)
    for s, col in zip(pm.SYSTEMS, _cols(h)):
        want = [r['pid'] for r in t[s]['rows'] if int(r['pid']) in goals]
        assert col.count('class="npsc') == len(want), s
    model_hits = sum(1 for r in t['model']['rows'] if int(r['pid']) in goals)
    assert model_hits == ent['summary']['top_hits']        # the pills agree with the saved top-10 hit count
    assert json.dumps([ent, rec], sort_keys=True, default=str) == before and pm.verify(rec)


def test_tab_reads_live_record_outside_long_caches_and_bypasses_name_pass():
    src = (ROOT / 'tabs' / 'predmodels.py').read_text()
    assert '_pm_sc_rec = sctn.active(st.session_state, np_day)' in src
    assert "v5.html_block(getattr(st, '_st', st), pmv.page_html(_pm_t, _pm_ns, _pm_scored, _pm_sc_rec))" in src
    cached = re.findall(r'@st\.cache_data\([^)]*\)\ndef (\w+)\(([^)]*)\):\n((?:    .*\n|\n)*?)(?=\n\S|@)', src)
    assert cached and not any('sctn' in body or 'STATE_KEY' in body for _, _, body in cached)
