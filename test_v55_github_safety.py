"""V5.5 GitHub-upload safety: size checker, .gitignore, snapshot pruning, monthly export, app without data."""
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import check_repo_size as crs
import prediction_tracker_v54 as trk
import snapshot_store as ss

HERE = Path(__file__).resolve().parent


def _mk(root, rel, size):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'wb') as f:
        f.truncate(size)
    return p


def test_check_repo_size_warn_fail_and_gitignore(tmp_path):
    (tmp_path / '.gitignore').write_text('data/\n*.zip\nsnapshots/*.json\n!snapshots/.gitkeep\n')
    _mk(tmp_path, 'app.py', 1000)
    _mk(tmp_path, 'big.bin', 60 * crs.MB)
    _mk(tmp_path, 'data/huge.sqlite', 200 * crs.MB)       # ignored
    _mk(tmp_path, 'release.zip', 200 * crs.MB)            # ignored
    _mk(tmp_path, 'snapshots/2026-01-01.json', 10)        # ignored
    _mk(tmp_path, 'snapshots/.gitkeep', 0)
    res = crs.check(tmp_path)
    names = [p for p, _ in res['files']]
    assert 'data/huge.sqlite' not in names and 'release.zip' not in names and 'snapshots/2026-01-01.json' not in names
    assert 'snapshots/.gitkeep' in names
    assert res['ok'] and [p for p, _ in res['warn']] == ['big.bin']
    assert res['top'][0][0] == 'big.bin'
    _mk(tmp_path, 'video.bin', 96 * crs.MB)
    res = crs.check(tmp_path)
    assert not res['ok'] and 'FAIL: video.bin' in crs.report(res)
    assert crs.main([str(tmp_path), '--top', '3']) == 1
    assert crs.check(tmp_path, use_gitignore=False)['fail']   # zip + sqlite counted when gitignore off


def test_top_n_limit(tmp_path):
    for i in range(20):
        _mk(tmp_path, f'f{i}.txt', i + 1)
    assert len(crs.check(tmp_path)['top']) == 15


def test_this_repo_passes():
    res = crs.check(HERE)
    assert res['ok'], crs.report(res)


def test_gitignore_has_required_rules():
    rules = (HERE / '.gitignore').read_text().splitlines()
    for r in ['venv/', '.venv/', 'env/', '__pycache__/', '.pytest_cache/', '*.zip', 'data/', '*.sqlite',
              'snapshots/*.json', '!snapshots/.gitkeep', '.streamlit/secrets.toml', '*.log', '*.mp4', '*.gif', 'playbook_screens/']:
        assert r in rules, r
    assert (HERE / 'snapshots' / '.gitkeep').exists()
    wf = (HERE / '.github/workflows/precompute.yml').read_text()
    assert 'git add -f' in wf and 'check_repo_size.py' in wf and 'prune' in wf


def test_prune_snapshots(tmp_path):
    for d in ['2026-01-01', '2026-08-23', '2026-08-24', '2026-10-22']:
        (tmp_path / f'{d}.json').write_text('{}')
    (tmp_path / '.gitkeep').write_text('')
    (tmp_path / 'notes.json').write_text('{}')
    (tmp_path / '2026-13-01.json').write_text('{}')     # not a real date: untouched
    today = date(2026, 10, 23)
    dry = ss.prune_snapshots(60, today=today, root=tmp_path, dry_run=True)
    assert [p.name for p in dry] == ['2026-01-01.json', '2026-08-23.json'] and (tmp_path / '2026-01-01.json').exists()
    gone = ss.prune_snapshots(60, today=today, root=tmp_path)
    assert [p.name for p in gone] == ['2026-01-01.json', '2026-08-23.json']
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ['.gitkeep', '2026-08-24.json', '2026-10-22.json', '2026-13-01.json', 'notes.json']
    assert ss.load_snapshot('2026-01-01', root=tmp_path) is None          # pruned -> treated as absent
    with pytest.raises(ValueError):
        ss.prune_snapshots(0, root=tmp_path)
    assert ss.prune_snapshots(60, root=tmp_path / 'missing') == []
    assert ss.DEFAULT_KEEP_DAYS >= 30


def test_monthly_export_roundtrip(tmp_path):
    conn = trk.connect(str(tmp_path / 't.sqlite'))
    for day in ('2026-09-30', '2026-10-01', '2026-10-15'):
        trk.save_predictions(conn, day, [{'player_key': f'id:{day}', 'source': 'statistical', 'player_id': '1', 'player': 'A B',
                                         'norm_name': 'a b', 'team': 'EDM', 'game_id': '1', 'rank': 1, 'score': 1.0, 'is_pick': 1}])
    assert trk.months(conn) == ['2026-10', '2026-09']
    data = json.loads(trk.export_month_json(conn, '2026-10'))
    assert {s['day'] for s in data['slates']} == {'2026-10-01', '2026-10-15'} and data['month'] == '2026-10'
    with pytest.raises(trk.TrackerError):
        trk.export_month_json(conn, 'october')
    other = trk.connect(str(tmp_path / 'o.sqlite'))
    trk.import_json(other, trk.export_month_json(conn, '2026-09'))
    assert [r['day'] for r in other.execute('SELECT day FROM slates')] == ['2026-09-30']


def test_app_runs_without_snapshot_or_data(monkeypatch, tmp_path):
    """No snapshot, no tracker DB, every network call failing: the app still renders every tab."""
    import requests
    import streamlit as st
    import snapshot_store
    from streamlit.testing.v1 import AppTest

    def offline(*a, **k):
        raise requests.ConnectionError('offline test')
    monkeypatch.setenv('PLAYBOOK_TRACKER_DB', str(tmp_path / 'nope' / 'tracker.sqlite'))
    monkeypatch.setattr(requests, 'get', offline)
    monkeypatch.setattr(snapshot_store, 'load_snapshot', lambda day, root=None: None)
    st.cache_data.clear()
    at = AppTest.from_file(str(HERE / 'app.py'), default_timeout=120)
    at.run()
    assert not at.exception
    labels = [t.label for t in at.tabs]
    assert labels[:6][-1] == '🧪 EdgeLab' and '📈 Track Record' not in labels   # V5.8: Track Record hidden by default
