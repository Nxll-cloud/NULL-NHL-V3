"""V5.9 Books top picks (books_picks_v59): reuse of odds_scorers_v59, freeze / score log, tab column."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import accuracy_v58 as acc
import books_picks_v59 as bp
import odds_scorers_v59 as oddsc
import prediction_models_v59 as pm

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / 'snapshots'


def _quotes():
    # p1: DK +150 / FD +130 / outlier MGM +400 -> median keeps it sane; p2: one book +120; p3: no NHL id
    return [{'player': 'A One', 'pid': '1', 'team': 'AAA', 'game': 'AAA @ HHH', 'book': 'DraftKings', 'american': '+150', 'updated': 'x'},
            {'player': 'A One', 'pid': '1', 'team': 'AAA', 'game': 'AAA @ HHH', 'book': 'FanDuel', 'american': '+130', 'updated': 'x'},
            {'player': 'A One', 'pid': '1', 'team': 'AAA', 'game': 'AAA @ HHH', 'book': 'BetMGM', 'american': '+400', 'updated': 'x'},
            {'player': 'B Two', 'pid': '2', 'team': 'HHH', 'game': 'AAA @ HHH', 'book': 'DraftKings', 'american': '+120', 'updated': 'x'},
            {'player': 'C Three', 'pid': '', 'team': 'HHH', 'game': 'AAA @ HHH', 'book': 'DraftKings', 'american': '-200', 'updated': 'x'}]


def _data(day='2026-10-24'):
    rows = oddsc.aggregate(_quotes())
    return {'day': day, 'source': oddsc.SOURCE_ESPN, 'rows': rows, 'updated': 'x', 'books': ['DraftKings', 'FanDuel', 'BetMGM'],
            'warnings': [], 'demo': False}


def test_picks_reuse_odds_scorers_rank_and_need_an_id():
    rows = _data()['rows']
    assert [r['player'] for r in rows][:1] == ['C Three']                # odds_scorers order: -200 first
    p = bp.picks(rows)
    assert [r['pid'] for r in p] == ['2', '1']                         # no-id row dropped; B (+120 .391) > A (median +150 .344)
    a = next(r for r in rows if r['pid'] == '1')
    assert a['consensus'] == pytest.approx(0.86 * 100 / 250)          # median of 3 books: outlier +400 ignored
    g = bp.gap(a)
    assert g['best'] == {'book': 'BetMGM', 'american': 400} and g['worst'] == {'book': 'FanDuel', 'american': 130}
    assert bp.gap(next(r for r in rows if r['pid'] == '2')) is None


def test_build_hash_and_score_by_player_id():
    rec = bp.build(_data(), '2026-10-24', '2026-10-24T23:00:00+00:00')
    assert bp.verify(rec) and rec['unmatched'] == 1 and [t[0] for t in rec['top']] == [2, 1] and not rec['demo']
    s = bp.score(rec, [[1, 'A One', 'AAA', 1], [9, 'X', 'AAA', 2]])
    assert s['results']['books_hits'] == 1 and s['results']['n_scorers'] == 2 and s['final']
    assert bp.verify(s)                                                # results sit outside the hash


def _snap(day, start):
    return {'schema': 1, 'day': day, 'updated_at': '2026-10-24T12:00:00+00:00',
            'games': [{'Away': 'AAA', 'Home': 'HHH', 'Start (UTC)': start, 'Status': 'FUT'}],
            'rankings': [{'Player': 'A One', 'Team': 'AAA', 'Player ID': 1, 'Statistical rank': 1}]}


def test_update_freezes_pregame_with_injected_fetch_then_scores(tmp_path, monkeypatch):
    day = '2026-10-24'
    snaps, accd, books = tmp_path / 'snapshots', tmp_path / 'acc', tmp_path / 'books'
    snaps.mkdir()
    (snaps / f'{day}.json').write_text(json.dumps(_snap(day, '2026-10-24T23:00:00Z')))
    calls = []
    monkeypatch.setattr(oddsc, 'load', lambda d, g, r, q, f, now=None: (calls.append(q), _data(d))[1])
    now = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
    assert acc.first_start(_snap(day, '2026-10-24T23:00:00Z')) and acc.is_pregame(_snap(day, '2026-10-24T23:00:00Z'))
    out = bp.update(now, snaps, books, accd, log=lambda *_: None)
    assert out == [f'froze {day} (ESPN (DraftKings))'] and calls == [None]      # api_quotes None: never an Odds API call
    assert bp.update(now, snaps, books, accd, log=lambda *_: None) == []        # fresh: no refetch within REFREEZE_MIN
    later = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    accd.mkdir()
    (accd / f'{day}.json').write_text(json.dumps({'day': day, 'results': {'scorers': [[1, 'A One', 'AAA', 1]]}}))
    monkeypatch.setattr(acc, 'load_entry', lambda d, root=None: json.loads((accd / f'{d}.json').read_text()) if (accd / f'{d}.json').exists() else None)
    assert f'scored {day}' in bp.update(later, snaps, books, accd, log=lambda *_: None)
    r = bp.load(day, books)
    assert r['results']['books_hits'] == 1 and bp.verify(r) and len(calls) == 1


def test_prune_locked_and_saved_log_valid():
    with pytest.raises(ValueError):
        bp.prune(root=ROOT)
    for r in bp.load_all(SNAP / 'accuracy_books'):
        assert bp.verify(r) and r['source'] in (oddsc.SOURCE_ESPN, oddsc.SOURCE_API) and r['demo'] is False
        assert (SNAP / 'accuracy_books' / f'{r["day"]}.json').stat().st_size < 100 * 1024


def test_coverage_note_is_precise_about_requested_books():
    for b in ('Hard Rock', 'Novig', 'Circa', 'DraftKings', 'Fanatics'):
        assert b in bp.COVERAGE_NOTE
    assert 'regions' not in Path(ROOT / 'books_picks_v59.py').read_text().split('def update')[1].split('def prune')[0]


def test_tab_column_and_nights_include_books():
    rec = bp.score(bp.build(_data('2026-10-23'), '2026-10-23'), [[2, 'B', 'HHH', 1]])
    ent = {'day': '2026-10-23', 'results': {'scorers': []}, 'summary': {'top_hits': 3, 'np_top_hits': 4, 'np_top_n': 10}}
    ns = pm.nights([], [ent], '2026-10-24', books_recs=[rec])
    assert ns[0]['books'] == 1 and ns[0]['books_n'] == 2 and ns[0]['model'] == 3 and ns[0]['blend'] is None
    t = pm.totals(ns)
    assert t['books'] == {'hits': 1, 'n': 2, 'nights': 1} and pm.leader(t) == ['books']   # 50% vs 30%
    assert '<th>Books</th>' in pm.nights_table(ns) and '1/2' in pm.nights_table(ns)
    tr = bp.tonight_rows('2026-10-24', bp.build(_data(), '2026-10-24'))
    assert [r['name'] for r in tr['rows']] == ['B Two', 'A One'] and tr['rows'][0]['stat'] == '39.1%'
    assert 'range +130 to +400' in tr['rows'][1]['layers'] and tr['source'].startswith('frozen pre-game')
    live = bp.tonight_rows('2026-10-24', None, _data())
    assert live['source'].startswith('live') and [r['pid'] for r in live['rows']] == [2, 1]
    assert bp.tonight_rows('2026-10-24', None, _data('2026-10-23'))['rows'] == []       # another day's prices: nothing
    page = pm.page_html({s: (tr if s == 'books' else {'source': 'x', 'rows': []}) for s in pm.SYSTEMS}, ns)
    assert page.count('class="pmc"') == 4 and 'Books top picks' in page and 'B Two' in page
