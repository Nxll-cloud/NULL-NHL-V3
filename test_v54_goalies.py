import pandas as pd

import goalies_v54 as gk
from v54_testkit import club_rows, load


def _p(pid, first, last, gp, gs, ga, sa, toi, **kw):
    return {'playerId': pid, 'firstName': {'default': first}, 'lastName': {'default': last}, 'gamesPlayed': gp,
            'gamesStarted': gs, 'goalsAgainst': ga, 'shotsAgainst': sa, 'timeOnIce': toi, **kw}


def test_gaa_and_save_pct_guard_divide_by_zero():
    assert gk.gaa(3, 3600) == 3.0 and gk.gaa(3, 0) is None and gk.gaa(None, 100) is None
    assert gk.save_pct(27, 30) == 0.9 and gk.save_pct(0, 0) is None


def test_parse_real_fixture_per_goalie():
    rows = club_rows()
    bos = [r for r in rows if r['Team'] == 'BOS']
    assert {r['Goalie'] for r in bos} == {'Joey DiPietro', 'Jeremy Swayman'} or len(bos) == 2
    for r in rows:
        assert r['GA'] >= 0 and (r['GAA'] is None or r['GAA'] >= 0)
        if r['TOI (sec)'] > 0:
            assert r['GAA'] == round(r['GA'] * 3600 / r['TOI (sec)'], 2)


def test_multiple_goalies_sum_per_team():
    payload = {'goalies': [_p(1, 'A', 'One', 5, 5, 10, 150, 18000), _p(2, 'B', 'Two', 3, 2, 9, 80, 9000)]}
    rows = gk.parse_club_goalies(payload, 'xyz')
    s = gk.team_summary(rows, ['XYZ'])
    r = s.iloc[0]
    assert r['GA'] == 19 and r['Goalies'] == 2 and r['GP'] == 7
    assert r['GAA'] == round(19 * 3600 / 27000, 2)


def test_zero_gp_goalie_and_missing_fields():
    rows = gk.parse_club_goalies({'goalies': [_p(3, 'C', 'Three', 0, 0, 0, 0, 0), {'playerId': 4}, 'junk', None]}, 'abc')
    assert rows[0]['GAA'] is None and rows[0]['SV%'] is None
    assert rows[1]['Goalie'] == 'Unknown goalie' and rows[1]['GA'] == 0


def test_empty_and_no_data_teams_listed_not_invented():
    assert gk.parse_club_goalies(None, 'BOS') == [] and gk.parse_club_goalies({'goalies': None}, 'BOS') == []
    s = gk.team_summary([], ['BOS', 'TOR'])
    assert s['GA'].tolist() == [0, 0] and set(s['Tone']) == {'none'} and s['GAA'].isna().all()
    assert gk.team_summary([], []).empty


def test_traded_goalie_counted_for_each_club_and_duplicates_once():
    g = _p(9, 'T', 'Traded', 4, 4, 12, 100, 14400)
    rows = gk.parse_club_goalies({'goalies': [g, g]}, 'AAA') + gk.parse_club_goalies({'goalies': [g]}, 'BBB')
    s = gk.team_summary(rows)
    assert dict(zip(s['Team'], s['GA'])) == {'AAA': 12, 'BBB': 12}


def test_tones_and_sorting():
    rows = club_rows()
    s = gk.sort_summary(gk.team_summary(rows), 'Goals allowed')
    assert s['GA'].tolist() == sorted(s['GA'].tolist(), reverse=True)
    assert s.iloc[0]['Tone'] == 'opportunity' and s.iloc[-1]['Tone'] == 'stingy'
    sv = gk.sort_summary(gk.team_summary(rows), 'Save %')
    assert sv.iloc[0]['Tone'] == 'opportunity'  # lowest SV% first = leakiest


def test_opponent_helper():
    s = gk.team_summary(club_rows())
    assert gk.opponent_goalie_ga(s, 'nsh')['GA'] == int(s[s['Team'] == 'NSH'].iloc[0]['GA'])
    assert gk.opponent_goalie_ga(s, 'ZZZ') is None and gk.opponent_goalie_ga(pd.DataFrame(), 'BOS') is None


def test_fetch_uses_injected_client_only():
    calls = []
    rows = gk.fetch_team_goalies('NSH', '20262027', fetch=lambda path: calls.append(path) or load('nhl_club_stats_goalies_20261022.json')['NSH'])
    assert calls == ['club-stats/NSH/20262027/2'] and rows
