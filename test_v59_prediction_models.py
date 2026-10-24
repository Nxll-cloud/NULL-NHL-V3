"""V5.9 Prediction Models tab + the experimental blend log (prediction_models_v59)."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

import accuracy_v58 as acc
import prediction_models_v59 as pm

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / 'snapshots'


def _players():
    #        pid name team p model_rank np_rank
    return [[1, 'A One', 'AAA', 0.30, 1, 3], [2, 'B Two', 'AAA', 0.29, 2, 1], [3, 'C Three', 'HHH', 0.20, 3, 2],
            [4, 'D Four', 'HHH', 0.10, 4, 4]]


# ------------------------------------------------------------------ blend math
def test_blend_p_is_a_probability_and_monotone():
    for kind in ('rate', 'logit'):
        assert pm.blend_p(0.3, 0, 0.0, kind) == pytest.approx(0.3)
        assert pm.blend_p(0.3, 3, 0.5, kind) > pm.blend_p(0.3, 1, 0.5, kind) > 0.3
        assert 0 < pm.blend_p(0.999999, 5, 0.5, kind) < 1
    assert pm.blend_p(0.2, 2, 0.5, 'rate') == pytest.approx(1 - 0.8 ** 2)   # rate x (1 + 0.5*2) = 2x
    assert pm.blend_p(0.2, 1, 0.5, 'logit') == pytest.approx(1 / (1 + math.exp(-(math.log(0.25) + 0.5))))
    with pytest.raises(ValueError):
        pm.blend_p(0.2, 1, 0.1, 'nope')


def test_rank_order_uses_layer_hits():
    r0 = pm.rank_blend(_players(), {}, 0.2)
    assert [r['pid'] for r in r0] == [1, 2, 3, 4]                       # no hits: the model order
    r = pm.rank_blend(_players(), {2: 2, 3: 5}, 0.2)
    # 0.29 & 2 hits -> 1-0.71**1.4 = .381; 0.20 & 5 hits -> 1-0.8**2 = .360; 0.30 & 0 hits -> .300
    assert [x['pid'] for x in r] == [2, 3, 1, 4] and r[1]['hits'] == 5 and r[0]['rank'] == 1
    assert [x['pid'] for x in pm.rank_blend(_players(), {2: 2, 3: 5}, 0.0)] == [1, 2, 3, 4]   # w=0 == model


def test_rank_tie_break_model_chance_then_rank_then_pid():
    ps = [[9, 'X', 'T', 0.2, 2], [5, 'Y', 'T', 0.2, 1], [7, 'Z', 'T', 0.2, 1]]
    assert [x['pid'] for x in pm.rank_blend(ps, {}, 0.2)] == [5, 7, 9]
    # equal blended chance: the higher model chance wins
    ps2 = [[1, 'L', 'T', 0.1, 2], [2, 'H', 'T', 0.1, 1]]
    assert [x['pid'] for x in pm.rank_blend(ps2, {'1': 1}, 0.2)][0] == 1    # str keys accepted


def test_scoring_matches_accuracy_card_by_player_id():
    assert pm.top_hits([1, 2, 3], [3, 8]) == 1
    assert pm.model_top_ids(_players(), 2) == [1, 2]
    ll = pm.log_loss({1: 0.3, 2: 0.1}, [1])
    assert ll == pytest.approx((-math.log(0.3) - math.log(0.9)) / 2, abs=1e-5)


def test_grid_and_choose_tie_break():
    nt = [{'players': _players(), 'hits': {3: 5, 4: 5}, 'scorers': [3]}]
    res = pm.grid_eval(nt, [('rate', 0.0), ('rate', 0.5), ('rate', 1.0)], n=1)
    assert [r['top_hits'] for r in res] == [0, 1, 1]
    best = pm.choose(res)
    assert best['top_hits'] == 1 and best['log_loss'] == min(r['log_loss'] for r in res if r['top_hits'] == 1)
    same = [{'kind': 'rate', 'w': 0.35, 'top_hits': 2, 'log_loss': 0.4}, {'kind': 'rate', 'w': 0.1, 'top_hits': 2, 'log_loss': 0.4},
            {'kind': 'rate', 'w': 0.0, 'top_hits': 1, 'log_loss': 0.3}]
    assert pm.choose(same)['w'] == 0.1                   # tie on hits + log loss -> smallest w
    assert pm.choose(same[:1] + [dict(same[1], log_loss=0.41)])['w'] == 0.35   # log loss breaks hit ties


def test_documented_weights_are_in_the_grid_and_footnote():
    assert (pm.BLEND_KIND, pm.BLEND_W) in pm.GRID
    assert f'{pm.BLEND_W}' in pm.WEIGHT_NOTE and 'w = 0' in pm.WEIGHT_NOTE
    assert '801' in pm.EXPERIMENTAL_NOTE and 'overfit' in pm.EXPERIMENTAL_NOTE


# ------------------------------------------------------------------ layers reuse the Numbers code
def test_layers_reuse_all_layers_evaluate():
    snap = acc._load_snap('2026-10-23', SNAP)
    lay = pm.layers_for(snap, '2026-10-23')
    assert lay and all(0 <= v['n'] <= 5 and v['n'] == sum(v['met'].values()) for v in lay.values())
    assert set(next(iter(lay.values()))['met']) == {'day', 'position', 'arena', 'reverse', 'english'}
    assert pm.layers_for(snap, '2026-10-23') == lay      # deterministic


# ------------------------------------------------------------------ frozen log
def _fake_snap(day='2026-10-23', at='2026-10-23T15:00:00+00:00', start='2026-10-23T23:00:00Z'):
    s = acc._load_snap('2026-10-23', SNAP)
    return dict(s, day=day, updated_at=at, games=[dict(g, **{'Start (UTC)': start}) for g in s['games']])


def test_build_freeze_hash_and_rebuilt_label(tmp_path):
    ent = acc.load_entry('2026-10-23', SNAP / 'accuracy')
    before = json.dumps(ent, sort_keys=True)
    snap = _fake_snap()
    rec = pm.build(ent, snap, 'frozen', 'test', datetime(2026, 10, 23, 16, tzinfo=timezone.utc))
    assert rec['kind'] == 'frozen' and not rec['final'] and pm.verify(rec) and rec['weights'] == {'kind': pm.BLEND_KIND, 'w': pm.BLEND_W}
    assert rec['model_entry_hash'] == ent['content_hash'] and len(rec['top']) == 10
    assert json.dumps(ent, sort_keys=True) == before and acc.verify(ent)     # accuracy entry untouched
    rb = pm.build(ent, snap, 'rebuilt', 'test')
    assert rb['kind'] == 'rebuilt' and rb['final']
    with pytest.raises(ValueError):
        pm.build(ent, snap, 'live')
    scored = pm.score(rec, ent['results']['scorers'], model_hits=ent['summary']['top_hits'])
    assert pm.verify(scored)                                  # results sit outside the hash
    assert scored['results']['model_hits'] == ent['summary']['top_hits'] == 3
    assert scored['results']['blend_hits'] == pm.top_hits([t[0] for t in rec['top']], [s[0] for s in ent['results']['scorers']])
    tampered = dict(scored, top=scored['top'][::-1])
    assert pm.verify(tampered) is False
    p = pm.save(scored, tmp_path)
    assert p.stat().st_size < pm.MAX_BYTES and pm.load('2026-10-23', tmp_path)['content_hash'] == rec['content_hash']


def test_update_freezes_pregame_then_scores_and_never_touches_accuracy(tmp_path):
    day = '2026-10-23'
    acc_root, snap_root, root = tmp_path / 'acc', tmp_path / 'snaps', tmp_path / 'snapshots' / 'accuracy_blend'
    acc_root.mkdir(); snap_root.mkdir()
    ent = acc.load_entry(day, SNAP / 'accuracy')
    pre = dict(ent, results=None, summary=None, final=False, first_start='2026-10-23T23:00:00+00:00')
    acc.save_entry(pre, acc_root)
    (snap_root / f'{day}.json').write_text(json.dumps(_fake_snap()))
    raw = (acc_root / f'{day}.json').read_bytes()
    done = pm.update(datetime(2026, 10, 23, 16, tzinfo=timezone.utc), snap_root, root, acc_root, log=lambda *_: None)
    assert done == [f'froze {day}'] and pm.load(day, root)['kind'] == 'frozen'
    assert pm.update(datetime(2026, 10, 23, 17, tzinfo=timezone.utc), snap_root, root, acc_root, log=lambda *_: None) == []   # unchanged: no rewrite
    acc.save_entry(ent, acc_root)                      # the accuracy step scored it overnight
    raw = (acc_root / f'{day}.json').read_bytes()
    done = pm.update(datetime(2026, 10, 24, 12, tzinfo=timezone.utc), snap_root, root, acc_root, log=lambda *_: None)
    assert f'scored {day}' in done and f'final {day}' in done
    rec = pm.load(day, root)
    assert rec['kind'] == 'frozen' and rec['final'] and rec['results']['model_hits'] == 3 and pm.verify(rec)
    assert (acc_root / f'{day}.json').read_bytes() == raw          # accuracy log never written


def test_update_catch_up_is_labelled_rebuilt(tmp_path):
    acc_root, root = tmp_path / 'acc', tmp_path / 'snapshots' / 'accuracy_blend'
    acc_root.mkdir()
    acc.save_entry(acc.load_entry('2026-10-23', SNAP / 'accuracy'), acc_root)
    done = pm.update(datetime(2026, 10, 24, 12, tzinfo=timezone.utc), SNAP, root, acc_root, log=lambda *_: None)
    assert 'rebuilt 2026-10-23' in done and pm.load('2026-10-23', root)['kind'] == 'rebuilt'


def test_prune_is_locked_to_its_folder(tmp_path):
    with pytest.raises(ValueError):
        pm.prune(root=tmp_path)
    r = tmp_path / 'snapshots' / 'accuracy_blend'
    r.mkdir(parents=True)
    (r / '2026-01-01.json').write_text('{}'); (r / '2026-10-20.json').write_text('{}'); (r / 'notes.txt').write_text('x')
    gone = pm.prune(90, datetime(2026, 10, 24).date(), r)
    assert [p.name for p in gone] == ['2026-01-01.json'] and (r / 'notes.txt').exists()


def test_saved_logs_are_small_valid_and_labelled():
    recs = pm.load_all(SNAP / 'accuracy_blend')
    assert recs
    for r in recs:
        assert pm.verify(r) and r['kind'] in ('frozen', 'rebuilt')
        assert (SNAP / 'accuracy_blend' / f'{r["day"]}.json').stat().st_size < 100 * 1024
    for e in acc.load_all(SNAP / 'accuracy'):
        assert acc.verify(e) is not False                       # existing accuracy hashes still verify


# ------------------------------------------------------------------ tab view
def _ns():
    return [{'day': '2026-10-22', 'kind': 'rebuilt', 'top_n': 10, 'model': 3, 'np': 2, 'blend': 3, 'saved': False},
            {'day': '2026-10-23', 'kind': 'rebuilt', 'top_n': 10, 'model': 3, 'np': 4, 'blend': 4, 'saved': True}]


def test_summary_states_n_and_caveat():
    h = pm.summary_html(_ns())
    assert 'last 2 scored nights' in h and '7/20' in h and '6/20' in h and 'Small sample' in h and 'in-sample' in h
    assert 'Blend (experimental) leads' in h and '801' in h
    assert pm.leader(pm.totals(_ns())) == ['blend']
    assert 'No scored night yet' in pm.summary_html([])
    tie = [dict(_ns()[0], blend=3, np=3)]
    assert 'All systems are level' in pm.summary_html(tie)
    assert 'Books has only the nights frozen' in h          # no books night in _ns()


def test_nights_table_labels_rebuilt_and_saved():
    t = pm.nights_table(_ns())
    assert 'rebuilt' in t and 'saved · blend rebuilt' in t and t.index('Oct 23') < t.index('Oct 22')
    assert pm.skipped_days(_ns(), '2026-10-24', 3) == ['2026-10-21']
    assert '(rebuilt)' in pm.acc_line(_ns(), 'model') and pm.acc_line(_ns(), 'model').count('(rebuilt)') == 1


def test_nights_prefers_saved_accuracy_numbers():
    recs = [{'day': '2026-10-23', 'kind': 'rebuilt', 'results': {'model_hits': 9, 'np_hits': 9, 'blend_hits': 4, 'top_n': 10}}]
    ent = {'day': '2026-10-23', 'results': {'scorers': []}, 'summary': {'top_hits': 3, 'np_top_hits': 4, 'np_top_n': 10}}
    ns = pm.nights(recs, [ent], '2026-10-24')
    assert ns[0]['model'] == 3 and ns[0]['np'] == 4 and ns[0]['saved'] and ns[0]['blend'] == 4
    assert pm.nights(recs, [ent], '2026-10-23') == []                # tonight is never in the trend


def test_tonight_four_lists_from_frozen_logs():
    day = '2026-10-23'
    snap = acc._load_snap(day, SNAP)
    ent = acc.load_entry(day, SNAP / 'accuracy')
    rec = pm.build(ent, snap, 'rebuilt', 'test')
    t = pm.tonight(day, snap['rankings'], snap['games'], ent, rec)
    assert set(t) == set(pm.SYSTEMS) and all(len(t[s]['rows']) == 10 for s in ('model', 'np', 'blend'))
    assert [r['pid'] for r in t['model']['rows']] == pm.model_top_ids(ent['players'])
    assert [r['pid'] for r in t['np']['rows']] == acc.np_top_ids(ent, snap)
    assert all(r['stat'].startswith('Form ') for r in t['np']['rows'])
    assert all('layer' in r['layers'] for r in t['blend']['rows'])
    live = pm.tonight(day, snap['rankings'], snap['games'], None, None,
                      [{'pid': p[0], 'name': p[1], 'team': p[2], 'p': p[3], 'model_rank': p[4]} for p in ent['players']])
    assert [r['pid'] for r in live['blend']['rows']] == [t_[0] for t_ in rec['top']]   # on-the-fly == frozen ranking
    h = pm.page_html(t, _ns())
    assert h.count('class="pmc"') == 4 and 'EXPERIMENTAL' in h and 'Books top picks' in h and 'Circa' in h
    assert t['books']['rows'] == [] and t['books']['source'] == 'no book prices loaded'   # never invented


# ------------------------------------------------------------------ AppTest
@pytest.fixture(scope='module')
def app(tmp_path_factory):
    from v54_testkit import run_app
    m = pytest.MonkeyPatch()
    m.delenv('FEATURE_TRACK_RECORD', raising=False)
    at = run_app(m, tmp_path_factory.mktemp('pm'))
    yield at
    m.undo()


def test_tab_renders_with_four_sections_and_summary(app):
    at = app
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert labels[-1] == '🧠 Prediction Models' and labels[:9] == ['🏠 Home', '🎯 Matchup Center', '⚡ Odds', '📊 Research', '🔮 Numbers',
                                                                  '🧪 EdgeLab', '⏱ Live Next Goal', '🚩 Edge Flags', '📰 Storylines']
    tab = next(t for t in at.tabs if t.label == '🧠 Prediction Models')
    from v54_testkit import markdown
    txt = ' '.join([m.value for m in tab.markdown] + [h.value for h in tab.get('html')])
    assert 'Prediction Models' in txt and ('Which system' in txt or 'scored night' in txt)
    assert txt.count('class="pmc"') == 4 and 'Books top picks' in txt and 'Model' in txt and 'NP leaderboard' in txt and 'EXPERIMENTAL' in txt
    caps = ' '.join(c.value for c in tab.caption)
    assert '801' in caps and 'Weights:' in caps


def test_blend_module_is_display_only():
    """The gematria layers stay out of every scoring path: only the tab / workflow CLI import the blend module."""
    import re
    hits = [f.name for f in ROOT.rglob('*.py')
            if not f.name.startswith('test_') and f.name != 'prediction_models_v59.py' and f.parent.name != 'tabs'
            and re.search(r'^\s*(import|from) prediction_models_v59', f.read_text(errors='ignore'), re.M)]
    assert hits == []


def test_accuracy_card_is_on_prediction_models_and_not_on_home(app):
    """V5.9: the Model accuracy card (with its collapsed top-10 list) renders on the tab and nowhere on Home."""
    at = app
    tabs = {t.label: t for t in at.tabs}

    def text(t):
        return ' '.join([m.value for m in t.markdown] + [h.value for h in t.get('html')])
    home, pm = text(tabs['🏠 Home']), text(tabs['🧠 Prediction Models'])
    assert 'class="npacc"' not in home and 'Model accuracy' not in home and 'Daily accuracy snapshot' not in home
    assert pm.count('<section class="npacc"') == 1 and 'Model accuracy · detailed record' in pm
    assert '<details class="npacc-top"><summary>Model top 10 (pre-game)' in pm or 'No completed slate' in pm
