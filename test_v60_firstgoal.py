"""V6.0 First Goal Intelligence (firstgoal_v60): aggregate math, empty board, freeze/score/verify, tab presence."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import firstgoal_v60 as fg

ROOT = Path(__file__).resolve().parent


def q(player, book, price, game='MIN @ EDM', updated='2026-10-30T18:00:00Z', pid=''):
    return {'player': player, 'team': '', 'game': game, 'book': book, 'price': price, 'updated': updated, 'pid': pid}


def test_conversions():
    assert fg.american_to_prob(100) == pytest.approx(0.5)
    assert fg.american_to_prob(900) == pytest.approx(0.1)
    assert fg.american_to_prob(-200) == pytest.approx(2 / 3)
    assert fg.fair_american(0.1) == 900
    assert fg.fair_american(2 / 3) == -200


def test_aggregate_median_best_gap_and_latest_quote():
    rows = fg.aggregate([q('A', 'DK', 900), q('A', 'FD', 1100), q('A', 'MGM', 800),
                         q('A', 'DK', 1000, updated='2026-10-30T19:00:00Z'), q('B', 'DK', 1500)])
    a = next(r for r in rows if r['player'] == 'A')
    assert a['books'] == 3 and a['best_odds'] == 1100 and a['best_book'] == 'FD'
    med = sorted([1 / 11, 1 / 12, 1 / 9])[1]           # DK latest = +1000
    assert a['median_pct'] == round(med * 100, 2)
    assert a['gap_pp'] == round((med - 1 / 12) * 100, 2)
    assert a['fair'] == fg.fair_american(med)
    assert rows[0]['player'] == 'A'                     # sorted by Books first


def test_empty_board_and_filters():
    assert fg.aggregate([]) == []
    assert fg.tonight_board('2026-10-30') == ('', [])
    html = fg.section_html('', [], [], status='No ODDS_API_KEY')
    assert 'No ODDS_API_KEY' in html and 'not model-calibrated' in html
    rows = fg.aggregate([q('A', 'DK', 900), q('A', 'FD', 2500), q('B', 'DK', 1500)])
    assert [r['player'] for r in fg.filter_board(rows, 2)] == ['A']
    assert [r['player'] for r in fg.filter_board(rows, 1, True)] == ['A']


def test_quotes_only_first_goal_market():
    recs = [{'market': 'player_goal_scorer_anytime', 'player': 'X', 'american_odds': 200, 'sportsbook': 'DK',
             'away_team': 'a', 'home_team': 'b', 'updated_at': 't'},
            {'market': fg.MARKET, 'player': 'Y', 'american_odds': 1200, 'sportsbook': 'DraftKings',
             'away_team': 'a', 'home_team': 'b', 'updated_at': 't'}]
    out = fg.quotes_from_records(recs)
    assert [o['player'] for o in out] == ['Y'] and out[0]['price'] == 1200


def _data():
    board = fg.aggregate([q('A', 'DK', 900, pid='1'), q('B', 'DK', 1200, pid='2'),
                          q('C', 'DK', 800, game='NJD @ VGK', pid='3'), q('D', 'DK', 1000, game='NJD @ VGK', pid='4')])
    return {'source': 'test', 'board': board}


def test_freeze_score_verify_first_goal_per_game():
    rec = fg.build(_data(), '2026-10-30', now=datetime(2026, 10, 30, 18, tzinfo=timezone.utc))
    assert fg.verify(rec) is True
    assert rec['favs']['MIN @ EDM'][0] == 1 and rec['favs']['NJD @ VGK'][0] == 3
    s = fg.score(rec, {'MIN @ EDM': 1, 'NJD @ VGK': 4})
    assert s['results']['games'] == 2 and s['results']['fav_hits'] == 1 and s['results']['top_hits'] == 2
    assert fg.verify(s) is True                          # scoring never changes the frozen hash
    tampered = dict(s, top=s['top'][::-1])
    assert fg.verify(tampered) is False
    assert 'game favourite scored first in 1/2' in fg.accuracy_line([s])


def test_save_load_and_prune_guard(tmp_path):
    rec = fg.build(_data(), '2026-10-30')
    fg.save(rec, tmp_path)
    assert fg.load('2026-10-30', tmp_path) == rec
    with pytest.raises(ValueError):
        fg.prune(root=tmp_path)


def test_update_without_key_skips_and_costs_nothing(tmp_path):
    calls = []
    out = fg.update(root=tmp_path, api_key='', getter=lambda *a, **k: calls.append(a), log=lambda *_: None)
    assert any('freeze skipped' in x for x in out) and not calls


def test_first_scorer_from_pbp_skips_shootout():
    pbp = {'gameState': 'OFF', 'awayTeam': {'id': 1, 'abbrev': 'MIN'}, 'homeTeam': {'id': 2, 'abbrev': 'EDM'},
           'rosterSpots': [{'playerId': 9, 'teamId': 1}, {'playerId': 8, 'teamId': 2}],
           'plays': [{'eventId': 2, 'typeDescKey': 'goal', 'periodDescriptor': {'number': 2, 'periodType': 'REG'},
                      'timeInPeriod': '05:00', 'details': {'scoringPlayerId': 8}},
                     {'eventId': 1, 'typeDescKey': 'goal', 'periodDescriptor': {'number': 1, 'periodType': 'REG'},
                      'timeInPeriod': '10:00', 'details': {'scoringPlayerId': 9}}]}
    assert fg.first_scorers_from_pbp(pbp) == ('OFF', 9)


def test_tabs_show_first_goal_separately():
    pm = (ROOT / 'tabs' / 'predmodels.py').read_text()
    rs = (ROOT / 'tabs' / 'research.py').read_text()
    assert 'fgv.section_html' in pm and "'First goal · separate market board'" in pm
    assert "st.subheader('🥅 First Goal Intelligence')" in rs
    i = rs.index("st.subheader('🥅 First Goal Intelligence')")
    assert rs.index('Top 10 Statistical Sleepers') < i
    import prediction_models_v59 as pmv
    assert pmv.SYSTEMS == ('model', 'np', 'blend', 'books')     # not blended into the four systems


def test_display_only_no_writes_to_accuracy_logs():
    src = (ROOT / 'firstgoal_v60.py').read_text()
    for bad in ('acc.save', 'save_entry', 'accuracy_books', 'accuracy_blend', "'accuracy'"):
        assert bad not in src
    for tab in ('predmodels.py', 'research.py'):
        t = (ROOT / 'tabs' / tab).read_text()
        assert 'fgv.save' not in t and 'fgv.update' not in t
    wf = (ROOT / '.github' / 'workflows' / 'precompute.yml').read_text()
    assert wf.index('books_picks_v59.py update') < wf.index('firstgoal_v60.py update')


def test_frozen_board_rows_have_all_v1_columns():
    rec = fg.build(_data(), '2026-10-30')
    src, rows = fg.tonight_board('2026-10-30', rec)
    assert src.startswith('frozen') and all(v is not None for v in fg.table_rows(rows)[0].values())
