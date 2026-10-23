"""Audit P1.7b: frozen entries carry a SHA-256 content hash, model version and model-source hash; final at first puck drop."""
import json
import re
from datetime import datetime, timedelta, timezone

import accuracy_v58 as acc

DAY = '2026-10-22'
FS = datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc)


def snap():
    rows = [{'Player ID': 100 + i, 'Player': f'P{i}', 'Team': 'TOR' if i % 2 else 'MTL', 'Prior GP': 20, 'Goals/G Prior': .3,
             'Shots/G L10': 2.5, 'Position': 'C', 'Opponent': 'MTL' if i % 2 else 'TOR'} for i in range(8)]
    return {'day': DAY, 'updated_at': '2026-10-22T18:00:00Z', 'rankings': rows,
            'games': [{'Away': 'MTL', 'Home': 'TOR', 'Start (UTC)': FS.isoformat(), 'Status': 'FUT', 'Game ID': '2025020100'}]}


def test_entry_carries_hash_version_and_source_hash():
    e = acc.predictions(snap(), now=FS - timedelta(hours=3))
    assert re.fullmatch(r'[0-9a-f]{64}', e['content_hash']) and re.fullmatch(r'[0-9a-f]{64}', e['model_source_hash'])
    assert e['model_version'] == acc.MODEL_VERSION and e['final'] is False
    assert e['model_source_hash'] == acc.model_source_hash()
    assert acc.verify(e) is True
    rt = json.loads(json.dumps(e))                   # survives the JSON log round trip
    assert acc.verify(rt) is True


def test_hash_detects_tampering_but_not_results():
    e = acc.predictions(snap(), now=FS - timedelta(hours=3))
    scored = acc.score(e, {'n_games': 1, 'scorers': [[100, 'P0', 'MTL', 1]]}, now=FS + timedelta(hours=4))
    assert acc.verify(scored) is True                # results / summary are not part of the frozen content
    bad = json.loads(json.dumps(e))
    if bad['players']:
        bad['players'][0][3] = 0.99
    else:
        bad['mean_p'] = 0.99
    assert acc.verify(bad) is False
    assert acc.verify({'day': DAY}) is None          # pre-P1.7b entries: unverifiable, not failed


def test_model_source_hash_changes_with_source(tmp_path):
    for f in acc.MODEL_SOURCES:
        (tmp_path / f).write_text('x')
    h1 = acc.model_source_hash(tmp_path)
    (tmp_path / acc.MODEL_SOURCES[0]).write_text('y')
    assert acc.model_source_hash(tmp_path) != h1


def test_final_at_first_puck_drop():
    e = acc.predictions(snap(), now=FS - timedelta(minutes=1))
    assert acc.finalize(e, FS - timedelta(seconds=1)) is e and not e['final']
    f = acc.finalize(e, FS)
    assert f['final'] is True and f['final_at'] == FS.isoformat() and acc.verify(f) is True
    late = acc.predictions(snap(), now=FS + timedelta(hours=1))   # catch-up / backfill after puck drop
    assert late['final'] is True


def test_update_marks_final_and_never_refreezes(tmp_path):
    snaps, logs = tmp_path / 'snaps', tmp_path / 'acc'
    snaps.mkdir()
    (snaps / f'{DAY}.json').write_text(json.dumps(snap()))
    e = acc.predictions(snap(), now=FS - timedelta(hours=2))
    acc.save_entry(e, logs)
    done = acc.update(now=FS + timedelta(minutes=5), getter=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')),
                      snap_root=snaps, root=logs, injuries_fn=lambda: [], log=lambda *_: None)
    got = acc.load_entry(DAY, logs)
    assert got['final'] is True and got['content_hash'] == e['content_hash'] and f'final {DAY}' in done


def test_card_footer_shows_provenance():
    e = acc.finalize(acc.predictions(snap(), now=FS - timedelta(hours=1)), FS)
    line = acc.provenance_line(e)
    assert e['content_hash'][:12] in line and '(verified)' in line and 'final at first puck drop' in line
    assert acc.provenance_line({}) == ''
