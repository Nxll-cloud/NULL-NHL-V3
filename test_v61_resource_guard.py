"""V6.1 resource-limit fixes: bounded process caches, slimmed payloads with identical outputs, gc freeze, and the
history collector fragment that polls only while a job is pending."""
import ast
import gc
import sys
from pathlib import Path

import resource_guard_v61 as rg
import storylines_v58 as sl
import history_v386 as h
import xg_v59 as xgm

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- BoundedTTL
def test_bounded_ttl_hit_and_expiry():
    clock = [1000.0]
    c = rg.BoundedTTL({'a': 10}, cap=5, clock=lambda: clock[0])
    c.put('a', 1, 'x')
    assert c.get('a', 1) == (True, 'x')
    clock[0] += 9.9
    assert c.get('a', 1) == (True, 'x')
    clock[0] += 0.2
    assert c.get('a', 1) == (False, None)


def test_bounded_ttl_evicts_expired_on_write_and_caps():
    clock = [0.0]
    c = rg.BoundedTTL({'a': 10, 'b': 1000}, cap=4, sweep=5, clock=lambda: clock[0])
    for i in range(3):
        c.put('a', i, i)
    c.put('b', 'keep', 1)
    clock[0] = 20.0
    c.put('b', 'new', 2)            # sweep: the three expired 'a' entries go
    assert set(c.data) == {('b', 'keep'), ('b', 'new')}
    for i in range(10):
        clock[0] += 0.01
        c.put('b', i, i)
    assert len(c) == 4              # hard cap, oldest dropped first
    assert ('b', 9) in c.data and ('b', 'keep') not in c.data


def test_storylines_cache_is_bounded_and_ttl_semantics_unchanged(monkeypatch):
    sl._CACHE.clear()
    calls = []
    v = sl._cached('espn', 'k', lambda: calls.append(1) or {'v': 1})
    assert sl._cached('espn', 'k', lambda: calls.append(1) or {'v': 2}) is v and len(calls) == 1
    assert sl._STORE.cap <= 1500 and sl._CACHE is sl._STORE.data
    stored_at = sl._CACHE[('espn', 'k')][0]
    monkeypatch.setattr(sl.time, 'time', lambda: stored_at + sl._TTL['espn'] + 1)
    assert sl._cached('espn', 'k', lambda: {'v': 3}) == {'v': 3}
    sl._CACHE.clear()


# ---------------------------------------------------------------- slimmed payloads give identical outputs
LANDING = {
    'playerId': 8478402, 'firstName': {'default': 'Connor'}, 'lastName': {'default': 'Test'}, 'birthDate': '1997-11-22',
    'birthCity': {'default': 'Richmond Hill'}, 'birthStateProvince': {'default': 'Ontario'}, 'birthCountry': 'CAN',
    'careerTotals': {'regularSeason': {'goals': 398, 'points': 997, 'gamesPlayed': 700}, 'playoffs': {'goals': 40}},
    'last5Games': [{'gameDate': '2026-11-22', 'goals': 1, 'points': 2, 'gameTypeId': 2},
                   {'gameDate': '2026-11-20', 'goals': 1, 'points': 1, 'gameTypeId': 2}],
    'seasonTotals': [{'season': 20252026, 'leagueAbbrev': 'NHL', 'gameTypeId': 2, 'gamesPlayed': 80, 'goals': 50,
                      'points': 120, 'teamName': {'default': 'Edmonton Oilers'}, 'teamCommonName': {'default': 'Oilers'}},
                     {'season': 20262027, 'leagueAbbrev': 'NHL', 'gameTypeId': 2, 'gamesPlayed': 0, 'goals': 0,
                      'points': 0, 'teamName': {'default': 'Toronto Maple Leafs'}}],
    'featuredStats': {'x': list(range(50))}, 'awards': [{'trophy': 'Hart'}], 'currentTeamRoster': [{'id': i} for i in range(30)],
    'headshot': 'https://example.com/a.png', 'shopLink': 'https://example.com',
}


def test_slim_landing_keeps_only_read_fields_and_rows_identical():
    slim = sl.slim_landing(LANDING)
    assert set(slim) == set(sl.LANDING_KEYS) & set(LANDING)
    assert 'currentTeamRoster' not in slim and slim['seasonTotals'] is LANDING['seasonTotals']
    for day in ('2026-11-22', '2026-11-23', '2027-03-01'):
        for p in ({'pid': 1, 'name': 'C', 'team': 'TOR', 'opp': 'EDM', 'arena': 'TOR', 'team_gp': 20, 'score': 5, 'rank': 1},
                  {'pid': 1, 'name': 'C', 'team': 'TOR', 'opp': 'EDM', 'arena': 'EDM', 'team_gp': 0}):
            assert sl.landing_rows(p, slim, day) == sl.landing_rows(p, LANDING, day)
    assert sl.nhl_stints(slim.get('seasonTotals')) == sl.nhl_stints(LANDING.get('seasonTotals'))
    assert sl.nhl_seasons(slim.get('seasonTotals')) == sl.nhl_seasons(LANDING.get('seasonTotals'))
    assert sl.slim_landing(None) is None and sl.slim_landing([1]) == [1]


def test_nhl_fetch_slims_landings_only(monkeypatch):
    import nhl_data
    sl._CACHE.clear()
    monkeypatch.setattr(nhl_data, 'fetch_json', lambda path: dict(LANDING) if path.endswith('/landing') else {'standings': [1], 'extra': 2})
    assert set(sl.nhl_fetch('player/1/landing')) <= set(sl.LANDING_KEYS)
    assert sl.nhl_fetch('standings/2026-11-22') == {'standings': [1], 'extra': 2}
    sl._CACHE.clear()


def _log():
    base = {'gameId': 0, 'gameDate': '', 'teamAbbrev': 'TOR', 'opponentAbbrev': 'EDM', 'homeRoadFlag': 'H', 'gameTypeId': 2,
            'goals': 0, 'assists': 0, 'points': 0, 'shots': 2, 'pim': 0, 'toi': '18:00', 'plusMinus': 1, 'powerPlayGoals': 0,
            'shorthandedGoals': 0, 'gameWinningGoals': 0, 'otGoals': 0, 'shifts': 22, 'commonName': {'default': 'Leafs'},
            'opponentCommonName': {'default': 'Oilers'}}
    out = []
    for i in range(1, 40):
        g = dict(base, gameId=2024020000 + i, gameDate=f'2025-{1 + i // 28:02d}-{1 + i % 28:02d}', goals=i % 3, assists=i % 2,
                 points=i % 3 + i % 2, shots=3 + i % 4, opponentAbbrev=('EDM', 'MTL', 'BOS')[i % 3],
                 teamAbbrev='EDM' if i < 10 else 'TOR')
        out.append(g)
    out[5].pop('assists')      # absent keys stay absent
    return out


def test_compact_log_identical_history_and_storyline_facts():
    full = _log()
    comp = h.compact_log(full)
    assert all(set(g) <= set(h.LOG_KEYS) for g in comp) and 'assists' not in comp[5]
    row = {'Player ID': 7, 'Player': 'P', 'Team': 'TOR'}
    seasons = ['20242025']
    for opp in ('EDM', 'MTL', 'BOS', 'NYR'):
        assert h.summarize_player(row, '2026-11-22', opp, {'20242025': comp}, seasons) == \
            h.summarize_player(row, '2026-11-22', opp, {'20242025': full}, seasons)
        for day in ('2025-01-20', '2026-11-22'):
            assert sl.vs_summary(comp, opp, day) == sl.vs_summary(full, opp, day)
            left = sl.left_date(full, opp)
            assert sl.left_date(comp, opp) == left
            assert sl.former_status(comp, opp, left, day)[0] == sl.former_status(full, opp, left, day)[0]
    assert h.compact_log(None) is None and h.compact_log({'x': 1}) == {'x': 1}


def test_season_log_is_bounded_and_compact(monkeypatch):
    monkeypatch.setattr(h, 'get_game_log', lambda pid, season: _log())
    h.season_log.cache_clear()
    out = h.season_log(1, '20242025')
    assert out == h.compact_log(_log()) and h.season_log.cache_info().maxsize <= 1500
    h.season_log.cache_clear()


def test_point_in_time_cache_keeps_one_season():
    cache = {'20232024': ([], {}), '20242025': ([], {})}
    xgm.point_in_time('2025-01-10', '20242025', getter=lambda url: (_ for _ in ()).throw(RuntimeError('cached hit only')), cache=cache)
    assert set(cache) == {'20232024', '20242025'}          # a hit never evicts
    assert xgm.PIT_MAX_SEASONS == 1
    src = (HERE / 'xg_v59.py').read_text()
    assert 'while len(cache) >= PIT_MAX_SEASONS' in src


# ---------------------------------------------------------------- gc freeze
def test_freeze_imports_once_and_thaw():
    rg.thaw()
    try:
        assert rg.freeze_imports() is True
        assert gc.get_freeze_count() > 0
        assert rg.freeze_imports() is False
        rg.thaw()
        assert gc.get_freeze_count() == 0 and sys.modules['_np_gc_state'].frozen is False
    finally:
        rg.thaw()


# ---------------------------------------------------------------- history collector fragment
def _app_tree():
    return ast.parse((HERE / 'app.py').read_text(encoding='utf-8'))


def test_history_status_polls_only_while_pending():
    src = (HERE / 'app.py').read_text(encoding='utf-8')
    tree = _app_tree()
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert not fns['history_status'].decorator_list            # no always-on 10 s fragment
    assert "_history_status_poll=st.fragment(run_every='10s')(_history_status_body)" in src
    assert 'np_rguard.freeze_imports()' in src
    ns = {'st': type('S', (), {'session_state': {}})()}
    exec(compile(ast.Module(body=[fns['history_pending']], type_ignores=[]), 'app.py', 'exec'), ns)
    pend = ns['history_pending']
    assert pend('2026-11-22') is False
    ns['st'].session_state['v43_history_job'] = {'day': '2026-11-22', 'key': 'k1', 'future': None}
    assert pend('2026-11-22') is True and pend('2026-11-21') is False
    ns['st'].session_state['v43_history_completed'] = 'k1'
    assert pend('2026-11-22') is False


def test_research_starts_collector_right_after_submitting_job():
    src = (HERE / 'tabs' / 'research.py').read_text(encoding='utf-8')
    i = src.index("st.session_state['v43_history_job']={'day':day")
    assert 'history_status(day, quiet=True)' in src[i:i + 300]
