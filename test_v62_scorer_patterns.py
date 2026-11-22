"""V6.2 Scorer Patterns (scorer_patterns_v62): offline fixtures only (no network)."""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import scorer_patterns_v62 as sp

ROOT = Path(__file__).resolve().parent
TODAY = '2026-11-22'


def _days(n, end=TODAY):
    d0 = date.fromisoformat(end)
    return [(d0 - timedelta(days=i)).isoformat() for i in range(n, 0, -1)]


def _row(pid, team, opp, s5, pos='C', g5=0.2, gp=0.2, rank=100, s10=None, gp_n=10):
    return {'Player': f'P{pid}', 'Player ID': pid, 'Team': team, 'Opponent': opp, 'Position': pos, 'Shots/G L5': s5,
            'Shots/G L10': s5 if s10 is None else s10, 'Goals/G L5': g5, 'Goals/G Prior': gp, 'Statistical rank': rank,
            'Opp GA/G L10': 3.0, 'Opp SA/G L10': 28, 'Prior GP': gp_n}


def _slate(day_i):
    """40 skaters in two games: pids 1-10 are high-volume shooters (s5=3.5), 11-40 low volume (s5=1.0)."""
    games = [{'Game ID': 1, 'Away': 'AAA', 'Home': 'HHH', 'Status': 'OFF'}, {'Game ID': 2, 'Away': 'BBB', 'Home': 'CCC', 'Status': 'OFF'}]
    teams = ['AAA', 'HHH', 'BBB', 'CCC']
    opp = {'AAA': 'HHH', 'HHH': 'AAA', 'BBB': 'CCC', 'CCC': 'BBB'}
    rows = [_row(p, teams[p % 4], opp[teams[p % 4]], 3.5 if p <= 10 else 1.0) for p in range(1, 41)]
    return games, rows


def _write_window(tmp, nights, scorers_fn):
    acc_dir, snap_dir = tmp / 'acc', tmp / 'snap'
    acc_dir.mkdir(exist_ok=True)
    snap_dir.mkdir(exist_ok=True)
    for i, d in enumerate(nights):
        games, rows = _slate(i)
        (snap_dir / f'{d}.json').write_text(json.dumps({'day': d, 'games': games, 'rankings': rows}))
        sc = [[p, f'P{p}', 'X', 1] for p in scorers_fn(i)]
        players = [[p, f'P{p}', 'X', 0.3 if p <= 10 else 0.1, p] for p in range(1, 41)]   # app Model p (pre-game)
        (acc_dir / f'{d}.json').write_text(json.dumps({'day': d, 'games': ['1', '2'], 'players': players, 'results': {'scorers': sc}}))
    return acc_dir, snap_dir


def _feeds(days, goals=None):
    """{day: compact feed}; goals {day: [(pid, team, strength, modifier, assists, gid)]}."""
    return {d: {'games': {'1': {'state': 'OFF', 'away': 'AAA', 'home': 'HHH'}}, 'goals': list((goals or {}).get(d, []))} for d in days}


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, 'MIN_SCORERS', 20)
    monkeypatch.setattr(sp, 'MIN_N', 50)
    monkeypatch.setattr(sp, 'MIN_K', 10)
    nights = _days(14)
    # Shooters (1-10): 5 of 10 score each night; low-volume (11-40): 2 of 30 score -> big lift for 'shots3'.
    acc_dir, snap_dir = _write_window(tmp_path, nights, lambda i: [1 + (i + k) % 10 for k in range(5)] + [11 + (i * 2) % 30, 12 + (i * 2) % 30])
    feeds = _feeds(_days(14 + 8, TODAY) + [TODAY])
    return acc_dir, snap_dir, feeds, nights


def test_descriptive_lifts_and_recent_fit(window):
    acc_dir, snap_dir, feeds, nights = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    st = {s['key']: s for s in pat['stats']}
    assert pat['status'] == 'ok' and pat['profile']['nights'] == nights and pat['profile']['N'] == 14 * 40
    assert st['shots3']['kept'] and st['shots3']['n'] == 140 and st['shots3']['k'] == 70
    assert abs(st['shots3']['lift'] - (70 / 140) / (98 / 560)) < 1e-9
    assert not st['home']['kept'] and st['home']['why']            # home is not over-represented in the fixture
    assert not st['forward']['kept']                               # everyone is a forward -> lift 1.0
    assert pat['stats'][0]['key'] == 'shots3'                       # kept traits first




def test_window_excludes_today_and_future_and_signature_changes(window, tmp_path):
    acc_dir, snap_dir, feeds, nights = window
    (acc_dir / f'{TODAY}.json').write_text(json.dumps({'day': TODAY, 'results': {'scorers': [[1, 'P1', 'X', 1]]}}))
    assert TODAY not in sp.window_days(TODAY, acc_dir)
    sig = sp.signature('2026-11-23', acc_dir, snap_dir)
    (acc_dir / '2026-11-22.json').write_text(json.dumps({'day': TODAY, 'results': {'scorers': [[2, 'P2', 'X', 1]]}}))
    import os
    os.utime(acc_dir / '2026-11-22.json', ns=(10 ** 18, 10 ** 18))
    assert sp.signature('2026-11-23', acc_dir, snap_dir) != sig


def test_prior_totals_use_only_days_before_and_missing_day_disables_situational():
    d = '2026-11-10'
    goals = {'2026-11-09': [(7, 'AAA', 'pp', 'none', (8, 9), '1')], '2026-11-10': [(5, 'AAA', 'pp', 'none', (), '1')],
             '2026-11-05': [(7, 'AAA', 'ev', 'own-goal', (), '1')]}
    feeds = _feeds(_days(8, d) + [d], goals)
    pr = sp.prior_totals(d, feeds)
    assert pr['g'][7] == 1 and pr['pp'][7] == 1 and pr['a'][8] == 1 and 5 not in pr['g']   # same-day goal never leaks; own goal ignored
    feeds.pop('2026-11-06')
    assert sp.prior_totals(d, feeds) is None
    t = sp.traits_of(sp.features(_row(7, 'AAA', 'HHH', 2.0), True, None))
    assert t['ppg7'] is None and t['pts7'] is None and t['home'] is True


def test_parse_score_drops_shootout_and_flags_situations():
    payload = {'games': [{'id': 9, 'gameDate': TODAY, 'gameState': 'LIVE', 'awayTeam': {'abbrev': 'AAA'}, 'homeTeam': {'abbrev': 'HHH'},
                          'goals': [{'playerId': 1, 'teamAbbrev': 'AAA', 'strength': 'pp', 'goalModifier': 'none',
                                     'assists': [{'playerId': 2}], 'periodDescriptor': {'periodType': 'REG'}},
                                    {'playerId': 3, 'teamAbbrev': 'HHH', 'strength': 'ev', 'goalModifier': 'empty-net',
                                     'assists': [], 'periodDescriptor': {'periodType': 'REG'}},
                                    {'playerId': 4, 'teamAbbrev': 'HHH', 'strength': 'ev', 'periodDescriptor': {'periodType': 'SO'}}]},
                         {'id': 10, 'gameDate': '2026-11-21', 'gameState': 'OFF', 'goals': []}]}
    f = sp.parse_score(payload, TODAY)
    assert list(f['games']) == ['9'] and len(f['goals']) == 2
    lv = sp.tonight_live(f)
    assert lv['goals'] == 2 and dict(lv['situations']) == {'PP': 1, 'EN': 1} and lv['team_pp'] == {'AAA': 1}
    assert lv['allowed'] == {'HHH': 1}                               # EN goal not charged to AAA's goalie
    assert lv['assists'][2] == 1 and lv['scorers'][1] == 1 and lv['states'] == {'AAA': 'LIVE', 'HHH': 'LIVE'}


def test_fetch_score_caches_and_fails_soft(monkeypatch):
    monkeypatch.setattr(sp, '_FEED', sp._rg.BoundedTTL({'final': 100, 'live': 60, 'fail': 120}, cap=10))
    calls = []

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {'games': [{'id': 1, 'gameDate': '2026-11-01', 'gameState': 'OFF', 'awayTeam': {'abbrev': 'A'},
                               'homeTeam': {'abbrev': 'H'}, 'goals': []}]}

    def get(url, timeout=None, headers=None):
        calls.append(url)
        return R()
    assert sp.fetch_score('2026-11-01', get)['games']['1']['state'] == 'OFF'
    assert sp.fetch_score('2026-11-01', get) and len(calls) == 1         # cached

    def boom(url, timeout=None, headers=None):
        raise OSError('offline')
    assert sp.fetch_score('2026-11-02', boom) is None



def _live_ctx():
    feed = {'games': {'1': {'state': 'LIVE', 'away': 'AAA', 'home': 'HHH'}, '2': {'state': 'OFF', 'away': 'BBB', 'home': 'CCC'}},
            'goals': [(1, 'AAA', 'ev', 'none', (5,), '1'), (13, 'HHH', 'ev', 'none', (), '1'), (13, 'HHH', 'pp', 'none', (), '1'),
                      (17, 'HHH', 'ev', 'none', (), '1')]}
    ev = [{'kind': 'goal', 'shooter': 13, 'goalie': 50}, {'kind': 'goal', 'shooter': 13, 'goalie': 50},
          {'kind': 'goal', 'shooter': 17, 'goalie': 50}, {'kind': 'goal', 'shooter': 1, 'goalie': 60}] + \
         [{'kind': 'sog', 'shooter': 9, 'goalie': 60}] * 4
    pbp = {'1': {'state': 'LIVE', 'away': 'AAA', 'home': 'HHH', 'roster': {50: {'name': 'Leaky Goalie', 'team': 'AAA'},
                                                                           60: {'name': 'Other G', 'team': 'HHH'}}, 'events': ev}}
    return sp.tonight_live(feed, pbp)



def test_insufficient_window_shows_no_probabilities(tmp_path):
    acc_dir, snap_dir = _write_window(tmp_path, _days(3), lambda i: [1, 2])
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, _feeds(_days(12)))
    assert pat['status'] == 'insufficient' and pat['w_traits'] is None
    h = sp.section_html(pat, [], {}, {}, [], [], sp.tonight_live(None), TODAY)
    assert 'Not enough scored nights yet' in h and 'Most likely' not in h


def test_joint_fit_counts_overlap_once(window):
    """Two perfectly overlapping traits: a joint fit splits the weight instead of double-counting it."""
    import numpy as np
    rows = []
    rng = np.random.default_rng(0)
    for _ in range(4000):
        a = rng.random() < 0.2
        y = rng.random() < (0.35 if a else 0.10)
        rows.append(({'shots3': a, 'hot': a}, y))
    X = [[1.0, 1.0 if t['shots3'] else 0.0, 1.0 if t['hot'] else 0.0] for t, _y in rows]
    w, _ = sp.fit(X, [1.0 if y else 0.0 for _t, y in rows], lam=1.0)
    single, _ = sp.fit([x[:2] for x in X], [1.0 if y else 0.0 for _t, y in rows], lam=1.0)
    assert abs((w[1] + w[2]) - single[1]) < 0.05 and abs(w[1] - w[2]) < 1e-6   # shared, not added twice


def test_map_update_shrinks_small_tonight_samples():
    import numpy as np
    w0 = [-2.0, 0.5]
    X = [[1.0, 1.0]] * 3 + [[1.0, 0.0]] * 3
    y = [1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    w_small, eff_small = sp.fit(X, y, w0=w0, tau=sp.TAU)
    w_big, eff_big = sp.fit(X * 50, y * 50, w0=w0, tau=sp.TAU)
    assert eff_small < 0.05 < eff_big < 1 and abs(w_small[1] - 0.5) < abs(w_big[1] - 0.5)


def _results(phases):
    """Minimal _v56_results: {team pair: (phase, elapsed, remaining)} with lam_game per player."""
    out = []
    for (away, home), (ph, el, rem), players in phases:
        out.append({'slate': {'away': away, 'home': home}, 'result': {'phase': ph, 'elapsed': el, 'remaining': rem,
                                                                      'players': [{'pid': p, 'lam_game': lam} for p, lam in players]}})
    return out


def _tonight(window, phases=('live', 'final')):
    acc_dir, snap_dir, feeds, _ = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    games, rows = _slate(0)
    lv = _live_ctx()
    res = _results([(('AAA', 'HHH'), (phases[0], 30.0, 30.0), [(p, 0.3 if p <= 10 else 0.1) for p in range(1, 41)]),
                    (('BBB', 'CCC'), (phases[1], 60.0, 0.0), [])])
    tr = sp.tonight_rows(rows, games, pat, lv, res)
    return pat, tr, lv


def test_probabilities_exclude_scorers_and_finals_and_scale_live_minutes(window):
    pat, tr, lv = _tonight(window)
    assert pat['status'] == 'ok' and pat['w_model'] and pat['w_traits']
    w = sp.update_tonight(pat, tr)
    assert w['k_sig'] == 3 and w['eff'] > 0             # 3 scorers on the slate list -> tonight's data used
    preds, info = sp.predict(tr, w, lv)
    pids = {r['pid'] for r in preds}
    assert not pids & {1, 13, 17} and info['scored'] == 3 and info['final_skipped'] == 20
    for r in preds:
        assert 0 < r['p'] < 1 and r['p'] <= r['p_full'] + 1e-12
        assert abs(r['p'] - (1 - (1 - r['p_full']) ** 0.5)) < 1e-9          # 30 of 60 minutes left
    assert [r['p'] for r in preds] == sorted((r['p'] for r in preds), reverse=True)
    r9 = next(r for r in preds if r['pid'] == 9)
    assert any('SOG tonight' in c for c in r9['live']) and any('Facing Leaky Goalie' in c for c in r9['live'])


def test_tonight_update_needs_enough_scorers_and_moves_toward_their_traits(window):
    pat, tr, lv = _tonight(window)
    for r in tr:
        r['goals'] = 0
    w0 = sp.update_tonight(pat, tr)
    assert w0['eff'] == 0 and w0['w_model'] == pat['w_model']                 # no scorers yet -> recent fit only
    for r in tr:                                                              # shooters (1-10) on AAA/HHH all score
        if r['pid'] <= 10 and r['team'] in ('AAA', 'HHH'):
            r['goals'] = 1
    w1 = sp.update_tonight(pat, tr, tau=1.0)
    i = sp.KEYS.index('shots3') + 1
    assert w1['w_traits'][i] > pat['w_traits'][i]


def test_scorer_profile_lists_tonight_scorers_and_shared_traits(window):
    pat, tr, lv = _tonight(window)
    sc, shared = sp.scorer_profile(tr)
    assert {s['name'] for s in sc} == {'P1', 'P13', 'P17'} and next(s for s in sc if s['name'] == 'P13')['goals'] == 2
    lab, a, b = next(x for x in shared if x[0] == '3+ SOG/G L5')
    assert abs(a - 1 / 3) < 1e-9 and 0 < b < 1


def test_pregame_rows_use_full_game_and_no_live_chips(window):
    acc_dir, snap_dir, feeds, _ = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    games, rows = _slate(0)
    for g in games:
        g['Status'] = 'FUT'
    tr = sp.tonight_rows(rows, games, pat, sp.tonight_live(None), [])
    preds, info = sp.predict(tr, sp.update_tonight(pat, tr), sp.tonight_live(None), top=50)
    assert len(preds) == 40 and all(r['phase'] == 'pregame' and not r['live'] and abs(r['p'] - r['p_full']) < 1e-12 for r in preds)
    assert all(r['mp'] is None for r in preds)                                # no Model p -> traits-only fit
    assert {r['pid'] for r in preds[:10]} == set(range(1, 11))


def test_section_html_probability_framing_escapes_and_mobile(window):
    pat, tr, lv = _tonight(window)
    next(r for r in tr if r['pid'] == 9)['name'] = '<b>X</b>'
    w = sp.update_tonight(pat, tr)
    preds, info = sp.predict(tr, w, lv)
    sc, shared = sp.scorer_profile(tr)
    h = sp.section_html(pat, preds, info, w, sc, shared, lv, TODAY)
    assert 'Most likely to score' in h and 'Tonight’s scorers so far · primary live input' in h and 'LIVE · 30 min left' in h
    assert '&lt;b&gt;X&lt;/b&gt;' in h and '<b>X</b>' not in h
    assert 'estimate' in h.lower() and 'Fit ' not in h and 'pattern fit' not in h.lower()
    assert '@media (max-width:420px)' in h and 'overflow-x:auto' in h and 'With tonight' in h
    assert sp.BACKTEST_NOTE in h.replace('&quot;', '"').replace('&#x27;', "'")


def test_display_only_and_wired_into_edgelab_only():
    hits = [f.name for f in ROOT.rglob('*.py') if not f.name.startswith('test_') and f.name != 'scorer_patterns_v62.py'
            and f.parent.name != 'tabs' and re.search(r'^\s*(import|from) scorer_patterns_v62', f.read_text(errors='ignore'), re.M)]
    assert hits == []
    el = (ROOT / 'tabs' / 'edgelab.py').read_text()
    pm = (ROOT / 'tabs' / 'predmodels.py').read_text()
    assert 'import scorer_patterns_v62' in el and 'scorer_patterns_v62 as' not in pm and '_sp_patterns' not in pm
    assert 'elv58.table_html' not in el and '_el_scope' not in el           # former EdgeLab view no longer rendered
    mod = (ROOT / 'scorer_patterns_v62.py').read_text()
    assert 'write_text' not in mod and "open(" not in mod.replace('read_text', '')
