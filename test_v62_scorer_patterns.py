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
        (acc_dir / f'{d}.json').write_text(json.dumps({'day': d, 'games': ['1', '2'], 'results': {'scorers': sc}}))
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


def test_learns_over_represented_trait_and_rejects_flat_ones(window):
    acc_dir, snap_dir, feeds, nights = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    st = {s['key']: s for s in pat['stats']}
    assert pat['status'] == 'ok' and pat['profile']['nights'] == nights and pat['profile']['N'] == 14 * 40
    assert st['shots3']['kept'] and st['shots3']['n'] == 140 and st['shots3']['k'] == 70
    assert abs(st['shots3']['lift'] - (70 / 140) / (98 / 560)) < 1e-9
    assert not st['home']['kept'] and st['home']['why']            # home is not over-represented in the fixture
    assert not st['forward']['kept']                               # everyone is a forward -> lift 1.0
    assert pat['stats'][0]['key'] == 'shots3'                       # kept traits first


def test_insufficient_window_suggests_nothing(tmp_path):
    acc_dir, snap_dir = _write_window(tmp_path, _days(3), lambda i: [1, 2])
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, _feeds(_days(12)))
    assert pat['status'] == 'insufficient'
    h = sp.section_html(pat, [], {}, sp.tonight_live(None), [], TODAY)
    assert 'Not enough scored nights yet' in h and 'Who fits' not in h


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


def test_suggest_excludes_scorers_and_final_games_and_adds_live_signals(window):
    acc_dir, snap_dir, feeds, _ = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    games, rows = _slate(0)
    games[0]['Status'] = 'LIVE'
    lv = _live_ctx()
    assert lv['goalie']['HHH'] == ('Leaky Goalie', 3) and lv['shots'][9] == 4
    out, info = sp.suggest(rows, games, pat, lv, TODAY)
    pids = [r['pid'] for r in out]
    assert 1 not in pids and 13 not in pids and info['excluded_scored'] >= 1     # scored tonight -> left out
    assert not any(r['team'] in ('BBB', 'CCC') for r in out) and info['final_skipped'] == 20
    r9 = next(r for r in out if r['pid'] == 9)                                     # shooter on HHH, 4 SOG tonight
    assert any('Leaky Goalie, 3 allowed' in x for x in r9['live']) and any('4 SOG tonight' in x for x in r9['live'])
    r5 = next(r for r in out if r['pid'] == 5)
    assert any('Assisted tonight' in x for x in r5['live'])
    assert all(0 <= r['fit'] <= 100 for r in out) and [r['fit'] for r in out] == sorted((r['fit'] for r in out), reverse=True)
    assert all(r['matched'] or r['live'] for r in out)


def test_pregame_games_get_no_live_signals(window):
    acc_dir, snap_dir, feeds, _ = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    games, rows = _slate(0)
    for g in games:
        g['Status'] = 'FUT'
    out, info = sp.suggest(rows, games, pat, sp.tonight_live(None), TODAY)
    assert out and all(not r['live'] and r['phase'] == 'pregame' for r in out)
    assert {r['pid'] for r in out} == set(range(1, 11))          # only the shooters match the kept trait
    assert info['excluded_scored'] == 0


def test_tonight_check_needs_enough_scorers(window):
    acc_dir, snap_dir, feeds, _ = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    games, rows = _slate(0)
    lv = _live_ctx()
    assert sp.tonight_check(rows, games, pat, lv) == []           # 3 scorers < TONIGHT_MIN_SCORERS
    for p in (2, 6, 10):
        lv['scorers'][p] = 1
    chk = sp.tonight_check(rows, games, pat, lv)
    lab, share, slate, k = next(c for c in chk if c[0] == '3+ SOG/G L5')
    assert k == 6 and abs(share - 4 / 6) < 1e-9 and abs(slate - 5 / 20) < 1e-9


def test_section_html_labels_escapes_and_is_mobile_safe(window):
    acc_dir, snap_dir, feeds, _ = window
    pat = sp.build_patterns(TODAY, acc_dir, snap_dir, feeds)
    games, rows = _slate(0)
    rows[0]['Player'] = '<b>X</b>'
    for g in games:
        g['Status'] = 'FUT'
    out, info = sp.suggest(rows, games, pat, sp.tonight_live(None), TODAY)
    h = sp.section_html(pat, out, info, sp.tonight_live(None), [], TODAY)
    assert 'Pattern fit, not a probability' in h and 'Fit ' in h and '&lt;b&gt;X&lt;/b&gt;' in h and '<b>X</b>' not in h
    assert '@media (max-width:420px)' in h and 'overflow-x:auto' in h and 'Lift' in h
    assert 'probability of' not in h.lower() and '%' in h
    none = dict(pat, status='none', stats=[dict(s, kept=False, why='x') for s in pat['stats']])
    assert 'No trait cleared the bar' in sp.section_html(none, [], {}, sp.tonight_live(None), [], TODAY)


def test_display_only_and_wired_into_prediction_models():
    hits = [f.name for f in ROOT.rglob('*.py') if not f.name.startswith('test_') and f.name != 'scorer_patterns_v62.py'
            and f.parent.name != 'tabs' and re.search(r'^\s*(import|from) scorer_patterns_v62', f.read_text(errors='ignore'), re.M)]
    assert hits == []
    src = (ROOT / 'tabs' / 'predmodels.py').read_text()
    assert src.index('oav.section_html(oav.aggregate(') < src.index('# V6.2: Scorer Patterns') and 'pmv.layers_for' not in src
    mod = (ROOT / 'scorer_patterns_v62.py').read_text()
    assert 'open(' not in mod.replace('read_text', '') and 'write_text' not in mod     # never writes files
