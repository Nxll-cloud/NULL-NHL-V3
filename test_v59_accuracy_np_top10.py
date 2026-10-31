"""V5.9: Home 'Model accuracy' card — NP leaderboard top-10 hit count next to the model's, plus its trend.

The NP leaderboard top 10 = Statistical rank 1..10 (V3.2 Adjusted Index) frozen in each entry's players[p][5];
fallback: the saved slate snapshot's rankings; else unknown (never guessed). Scored against the same real scorers."""
import copy
import html as _html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import accuracy_v58 as acc

HERE = Path(__file__).resolve().parent
DAY = '2026-10-23'
ENTRY = json.loads((HERE / 'snapshots' / 'accuracy' / f'{DAY}.json').read_text())
SNAP = json.loads((HERE / 'snapshots' / f'{DAY}.json').read_text())
SIDS = {s[0] for s in ENTRY['results']['scorers']}
NOW = datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc)
MACK, LEHK, GUENTZEL, BEDARD = 8477492, 8477476, 8477404, 8484144


def _no_net(*a, **k):
    raise AssertionError('no network')


def _strip(entry):
    """A scored entry as saved before the NP stat existed."""
    e = copy.deepcopy(entry)
    for k in ('np_top_hits', 'np_top_n'):
        e['summary'].pop(k, None)
    return e


def _head_and_trend(html):
    head = _html.unescape(re.search(r'<div class="npacc-h"><b>Model accuracy</b><span>(.*?)</span>', html).group(1))
    tr = _html.unescape(re.sub(r'<[^>]+>', '', re.search(r'<div class="npacc-tr">(.*?)</div>', html).group(1)))
    return head, tr


def test_np_top10_from_frozen_entry_is_4_of_10():
    top = acc.np_top_ids(ENTRY)
    assert len(top) == 10
    assert {p for p in top if p in SIDS} == {MACK, LEHK, GUENTZEL, BEDARD}
    assert acc._np_summary(ENTRY, SIDS) == {'np_top_hits': 4, 'np_top_n': 10}


def test_score_adds_np_and_keeps_model_numbers_and_hash():
    e = _strip(ENTRY)
    e.pop('results'); e['summary'] = None
    res = {'n_games': ENTRY['results']['n_games'], 'scorers': ENTRY['results']['scorers']}
    s = acc.score(e, res)['summary']
    assert (s['np_top_hits'], s['np_top_n']) == (4, 10)
    assert (s['top_hits'], s['top_n'], s['parlay_hits'], s['parlay_legs']) == (3, 10, 1, 4)
    assert (s['baseline']['top_hits'], s['baseline']['top_n']) == (3, 10)
    assert acc.verify(acc.score(e, res)) is True


def test_attach_np_on_read_leaves_frozen_fields_alone():
    e = _strip(ENTRY)
    out = acc.attach_np(e, lambda d: (_ for _ in ()).throw(AssertionError('snapshot not needed')))
    assert (out['summary']['np_top_hits'], out['summary']['np_top_n']) == (4, 10)
    assert {k: out[k] for k in acc.HASHED_KEYS} == {k: e[k] for k in acc.HASHED_KEYS}
    assert out['content_hash'] == e['content_hash'] and acc.verify(out) is True
    assert 'np_top_n' not in e['summary']   # input not mutated


def test_missing_np_falls_back_to_snapshot_then_none():
    e = _strip(ENTRY)
    e['players'] = [p[:5] for p in e['players']]   # an older entry without np_rank
    assert acc.np_top_ids(e) is None
    out = acc.attach_np(e, lambda d: SNAP)
    assert (out['summary']['np_top_hits'], out['summary']['np_top_n']) == (4, 10)
    gone = acc.attach_np(e, lambda d: None)
    assert gone['summary']['np_top_hits'] is None and gone['summary']['np_top_n'] is None
    comp = dict(_strip(ENTRY), compacted=True)   # compacted entry: never trust a trimmed player list
    assert acc.attach_np(comp, lambda d: None)['summary']['np_top_n'] is None


def test_trend_counts_only_nights_with_np():
    a = acc.attach_np(_strip(ENTRY))
    b = copy.deepcopy(a); b['day'] = '2026-10-22'
    b['summary'].update(np_top_hits=None, np_top_n=None)
    c = copy.deepcopy(a); c['day'] = '2026-10-21'
    c['summary'].update(np_top_hits=2, np_top_n=10)
    t = acc.trend([a, b, c])
    assert len(t['nights']) == 3 and (t['top_hits'], t['top_n']) == (9, 30)
    assert t['np'] == {'top_hits': 6, 'top_n': 20, 'nights': 2}
    assert acc.trend([b])['np'] is None


def test_card_header_and_trend_for_oct23(tmp_path):
    # The trend sums every scored night in the log dir; the nightly workflow keeps adding nights after Oct 23,
    # so pin the log to the Oct 23 entry alone (real file, real numbers) instead of the live snapshots/accuracy/.
    (tmp_path / f'{DAY}.json').write_text((HERE / 'snapshots' / 'accuracy' / f'{DAY}.json').read_text())
    html = acc.card_html(acc.view(NOW, _no_net, tmp_path, HERE / 'snapshots'))
    head, tr = _head_and_trend(html)
    assert 'model top-10 hit 3/10 (shots-share 3/10) · NP leaderboard top-10 hit 4/10 · parlay 1/4 legs' in head
    assert 'Last 1 night: top-10 hit 3/10' in tr and 'NP leaderboard 4/10' in tr


def test_card_without_np_shows_no_np_text():
    e = _strip(ENTRY)
    e['players'] = [p[:5] + [None] for p in e['players']]   # np_rank unknown for every player
    e = acc.attach_np(e, lambda d: None)
    v = {'shown': e, 'notes': [], 'trend': acc.trend([e]), 'pending': None}
    head, tr = _head_and_trend(acc.card_html(v))
    assert 'NP leaderboard' not in head and 'NP leaderboard' not in tr
    assert 'model top-10 hit 3/10' in head
