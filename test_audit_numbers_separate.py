"""Audit P1.6: Gematria / Numbers picks are separate from model picks - Long Shot shows two labelled options and the
tracker reports model-only (Stats + Odds) hit rates apart from Numbers (Numbers + Overlap)."""
from pathlib import Path

import pytest

import longshot_v58 as ls
import prediction_tracker_v54 as trk
import ui_theme_v53 as ui

ROOT = Path(__file__).resolve().parent


def _c(pid, p):
    return {'pid': pid, 'name': f'P{pid}', 'team': 'TOR', 'opp': 'MTL', 'home': True, 'game': 'g', 'game_id': '1',
            'start': None, 'phase': 'pregame', 'p': p, 'p_next': None, 'np_rank': None, 'form': None, 'model_rank': pid}


CANDS = [_c(i, p) for i, p in enumerate([.45, .40, .35, .30, .18, .15, .12, .08, .04], 1)]
GEM = {'7': {'threat': 95, 'day': True, 'arena': True, 'team': True}}


def test_model_pick_ignores_gematria_and_storylines():
    base = ls.picks(CANDS)
    with_gem = ls.picks(CANDS, gem={str(c['pid']): {'threat': 100, 'day': True, 'arena': True, 'team': True} for c in CANDS},
                        stories={c['pid']: ['REVENGE', 'BDAY', 'HOMETOWN'] for c in CANDS})
    assert base['model']['pid'] == with_gem['model']['pid'] == 5   # highest in-band model chance
    assert base['model']['ls_score'] == with_gem['model']['ls_score']
    assert not any('Gematria' in s or 'Storyline' in s for s, _ in with_gem['model']['signals'])
    assert base['numbers'] is None                                  # no gematria/storyline signal -> no Numbers pick


def test_model_pick_uses_model_signals_only():
    pp = ls.picks(CANDS, jumps={8: 6}, edge_ids={8}, gem=GEM)
    assert pp['model']['pid'] == 5                                  # .18 > .08 x 1.4: model score = p x (1 + jump + edge)
    j = ls.picks([_c(5, .18), _c(6, .15), _c(1, .45), _c(2, .40)], jumps={6: 6}, edge_ids={6})
    assert j['model']['pid'] == 6 and {s for s, _ in j['model']['signals']} == {'Next-goal jump +6 ranks', 'Edge flag'}


def test_numbers_pick_separate_player_and_labelled():
    pp = ls.picks(CANDS, gem=GEM)
    assert pp['model']['pid'] == 5 and pp['numbers']['pid'] == 7 and pp['numbers']['lens'] == 'numbers'
    gem5 = {'5': {'threat': 95, 'day': True, 'arena': False, 'team': False}, **GEM}
    assert ls.picks(CANDS, gem=gem5)['numbers']['pid'] == 7      # never the same player as the model pick
    assert ls.picks(CANDS, parlay_ids=[5], gem=GEM)['model']['pid'] == 6   # parlay legs excluded from both
    html = ls.pair_html(pp, scored_ids={7: {}})
    assert 'Model pick' in html and 'Gematria / Numbers pick' in html
    assert 'Not a model pick; never counted in model hit rates' in html
    assert html.index('kind">Model pick') < html.index('kind">Gematria / Numbers pick') and html.count('✓ Scored') == 1
    assert 'No qualifying long shot tonight' in ls.pair_html(None)
    assert 'Nobody else in the band has a gematria' in ls.pair_html(ls.picks(CANDS))


def test_home_uses_the_pair():
    src = (ROOT / 'tabs' / 'home.py').read_text()
    assert 'longshot.picks(' in src and 'longshot.pair_html(' in src and 'longshot.pick(' not in src
    assert 'trk.model_rolling' in src


def _rec(name, sources):
    return {'player': name, 'player_key': 'n:' + name, 'team': 'TOR', 'sources': sources}


def _ev(day, hits, misses):
    groups = {}
    for g, srcs in trk.GROUPS.items():
        h = sum(1 for r in hits if set(r['sources']) & set(srcs))
        p = h + sum(1 for r in misses if set(r['sources']) & set(srcs))
        groups[g] = {'picks': p, 'hits': h, 'rate': h / p if p else None}
    by = {s: {'picks': sum(s in r['sources'] for r in hits + misses), 'hits': sum(s in r['sources'] for r in hits)} for s in trk.SOURCES}
    return {'status': 'evaluated', 'day': day, 'hits': hits, 'misses': misses, 'picks': len(hits) + len(misses),
            'hit_rate': len(hits) / (len(hits) + len(misses)), 'by_source': by, 'groups': groups}


EVALS = [_ev('2026-10-20', [_rec('Gem', ['Numbers']), _rec('Ov', ['Overlap'])], [_rec('S1', ['Stats']), _rec('S2', ['Stats', 'Odds'])]),
         _ev('2026-10-21', [_rec('S1', ['Stats', 'Numbers'])], [_rec('G2', ['Numbers']), _rec('O1', ['Odds'])])]


def test_model_rates_exclude_numbers_only_picks():
    m, n, all_ = trk.rolling(EVALS, group='model'), trk.rolling(EVALS, group='numbers'), trk.rolling(EVALS)
    assert (m['hits'], m['picks']) == (1, 4)          # S1 miss, S2 miss, S1 hit, O1 miss - no Gem/Ov/G2
    assert (n['hits'], n['picks']) == (3, 4)          # Gem hit, Ov hit, S1(+Numbers) hit, G2 miss
    assert (all_['hits'], all_['picks']) == (3, 7)
    assert trk.model_rolling(EVALS) == m and trk.numbers_rolling(EVALS) == n
    big = [_ev(f'2026-09-{i:02d}', [_rec(f'G{i}', ['Numbers'])] * 3, [_rec(f'S{i}', ['Stats'])] * 3) for i in range(1, 8)]
    assert trk.rolling(big, group='model')['picks'] == 21 and trk.rolling(big, group='model')['rate'] == 0.0
    assert trk.pooled_rate(big) == trk.PRIOR_RATE      # model rate 0 -> fallback prior; Numbers hits never lift it
    t = trk.trend(EVALS, 'model')
    assert list(t['Hit rate']) == [0.0, 0.5]


def test_player_records_and_source_table_are_model_only():
    recs = trk.player_records(EVALS)
    assert set(recs['Player']) == {'S1', 'S2', 'O1'}   # Gem / Ov / G2 never on the leaderboard or badges
    src = trk.source_breakdown(EVALS)
    assert list(src['Source']) == ['Stats', 'Odds', 'Numbers', 'Overlap']
    assert list(src['Group']) == ['Model', 'Model', 'Numbers (not a model)', 'Numbers (not a model)']


def test_evaluate_slate_reports_groups(tmp_path):
    conn = trk.connect(tmp_path / 't.sqlite')
    day = '2026-10-22'
    def row(name, src, pid):
        return {'player_key': f'id:{pid}', 'source': src, 'player_id': pid, 'player': name, 'norm_name': name.lower(),
                'team': 'TOR', 'game_id': '9', 'rank': 1, 'score': 1.0, 'is_pick': 1}
    trk.save_predictions(conn, day, [row('Model Guy', 'Stats', 1), row('Gem Guy', 'Numbers', 2)], n_games=1)
    trk.record_game_results(conn, day, '9', [{'player': 'Gem Guy', 'player_id': 2, 'team': 'TOR', 'goals': 1}], final=True)
    ev = trk.evaluate_slate(conn, day)
    assert ev['groups']['model'] == {'picks': 1, 'hits': 0, 'rate': 0.0}
    assert ev['groups']['numbers'] == {'picks': 1, 'hits': 1, 'rate': 1.0}
    assert ev['model_rate'] == 0.0 and trk.rolling([ev], group='model')['rate'] == 0.0
    card = ui.slate_card(ev)
    assert '0% model hit rate' in card and 'Numbers (gematria, not a model): 1/1' in card
    conn.close()


def test_track_tab_shows_groups_separately():
    src = (ROOT / 'tabs' / 'track.py').read_text()
    assert 'trk.model_rolling' in src and 'trk.numbers_rolling' in src and "trk.trend(_tevals, 'model')" in src
