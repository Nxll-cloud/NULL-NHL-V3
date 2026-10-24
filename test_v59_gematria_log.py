"""V5.9 gematria history (gematria_log_v59): frozen-once dated records, results join, 90-day prune, last_n_days and the
Numbers page 'Arena-match scorers' strip. Offline fixtures only."""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import feature_flags_v58 as flags
import gematria_log_v59 as gl
import gem_match_v58 as gm
from numerology_v48 import analyze_game, universal_day
from player_targets_v49 import slate_targets

HERE = Path(__file__).resolve().parent
PRE = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)      # before the 00:00Z first puck drop
LATE = datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc)      # still Oct 23 in New York


def _snap(day='2026-10-23', updated='2026-10-23T17:00:00+00:00'):
    games = [{'Game ID': 2026020166, 'Away': 'MTL', 'Home': 'CHI', 'Start (UTC)': f'{day[:8]}{int(day[8:]) + 1:02d}T00:00:00Z', 'Status': 'FUT', 'Venue': 'United Center'},
             {'Game ID': 2026020167, 'Away': 'TBL', 'Home': 'COL', 'Start (UTC)': f'{day[:8]}{int(day[8:]) + 1:02d}T01:00:00Z', 'Status': 'FUT', 'Venue': 'Ball Arena'}]
    names = ['Cole Caufield', 'Nick Suzuki', 'Josh Anderson', 'Connor Bedard', 'Frank Nazar', 'Brandon Hagel', 'Nikita Kucherov',
             'Nathan MacKinnon', 'Cale Makar', 'Gabriel Landeskog', 'Ryan Donato', 'Jake Guentzel',
             'Lane Hutson', 'Juraj Slafkovsky', 'Teuvo Teravainen', 'Anthony Cirelli']
    teams = ['MTL', 'MTL', 'MTL', 'CHI', 'CHI', 'TBL', 'TBL', 'COL', 'COL', 'COL', 'CHI', 'TBL', 'MTL', 'MTL', 'CHI', 'TBL']
    rank = [{'Player': n, 'Team': t, 'Player ID': 100 + i, 'V3.2 Adjusted Index': 50 - i} for i, (n, t) in enumerate(zip(names, teams))]
    return {'schema': 1, 'day': day, 'updated_at': updated, 'games': games, 'rankings': rank, 'history': [], 'errors': []}


@pytest.fixture
def dirs(tmp_path):
    snaps = tmp_path / 'snapshots'
    (snaps / 'gematria').mkdir(parents=True)
    (snaps / 'accuracy').mkdir()
    return snaps, snaps / 'gematria'


def _write_snap(snaps, s):
    (snaps / f"{s['day']}.json").write_text(json.dumps(s))


class _Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def _score_payload(goals, state='OFF', ppd=False):
    def g(gid, a, h, sched='OK'):
        gs = [x for x in goals if x['gid'] == gid]
        return {'id': gid, 'gameState': state, 'gameScheduleState': sched,
                'awayTeam': {'abbrev': a, 'score': sum(x['team'] == a for x in gs)}, 'homeTeam': {'abbrev': h, 'score': sum(x['team'] == h for x in gs)},
                'periodDescriptor': {'periodType': 'REG'}, 'gameOutcome': {'lastPeriodType': 'REG'},
                'goals': [{'playerId': x['pid'], 'firstName': {'default': x['name'].split()[0]}, 'lastName': {'default': x['name'].split()[1]},
                           'teamAbbrev': x['team'], 'periodDescriptor': {'periodType': 'REG'}} for x in gs]}
    return {'games': [g(2026020166, 'MTL', 'CHI'), g(2026020167, 'TBL', 'COL', 'PPD' if ppd else 'OK')]}


def _getter(payload):
    def get(url, timeout=12):
        if '/score/' in url:
            return _Resp(payload)
        return _Resp({'playerByGameStats': {}, 'plays': [], 'rosterSpots': []})
    return get


def test_record_contents_match_the_numbers_page_and_carry_method_hash():
    s = _snap()
    rec = gl.build(s, PRE)
    assert rec['day'] == '2026-10-23' and rec['universal_day'] == universal_day('2026-10-23') == 7
    assert rec['method_version'] == gl.METHOD_VERSION and re.fullmatch(r'[0-9a-f]{12}', rec['method_hash']) and rec['method_hash'] == gl.method_hash()
    assert rec['frozen_at'] == PRE.isoformat(timespec='seconds') and rec['frozen_late'] is False and rec['reconstructed'] is False
    uc = rec['games'][0]
    assert uc['game'] == 'MTL@CHI' and uc['arena'] == 'United Center' and uc['arena_eng'] == [138, 3] and uc['arena_rev'] == [186, 6]
    # same rows as the Numbers page table (gem_match_v58.match_table on player_targets_v49.slate_targets)
    import pandas as pd
    from home_leaders_v52 import TEAM_NAMES
    an = [analyze_game(g, s['day'], TEAM_NAMES) for g in s['games']]
    rows, _ = gm.match_table(slate_targets(an, pd.DataFrame(s['rankings']), s['day']), 7)
    page = sorted((int(r['player_id']), r['Match type']) for r in rows)
    mine = sorted((m['pid'], k) for m in rec['matched'] for k in m['match'] if k in ('date', 'arena'))
    assert page == mine and rec['counts']['date'] + rec['counts']['arena'] == len(rows)
    m = rec['matched'][0]
    assert set(m) == {'pid', 'name', 'team', 'game', 'eng', 'rev', 'match'} and all(set(v) <= set(gl.FIELDS) for v in m['match'].values())
    assert len(rec['players']) == 16 and rec['counts']['arena'] == 4 and rec['players_cols'] == ['pid', 'team', 'eng_total', 'rev_total']
    assert len(gl._dump(rec)) < 100 * 1024


def test_numbers_page_team_names_are_the_same_dict():
    src = (HERE / 'tabs' / 'research.py').read_text()
    assert eval(re.search(r"_TEAM_NAMES = (\{.*?\})", src).group(1)) == gl.team_names()


def test_freeze_once_never_overwritten(dirs):
    snaps, root = dirs
    _write_snap(snaps, _snap())
    assert gl.update(PRE, _getter({}), snaps, root, log=lambda *_: None, environ={}) == ['froze 2026-10-23']
    first = (root / '2026-10-23.json').read_text()
    s2 = _snap(updated='2026-10-23T23:30:00+00:00')
    s2['rankings'] = s2['rankings'][:3]                          # roster changed in a later snapshot
    _write_snap(snaps, s2)
    assert gl.update(PRE, _getter({}), snaps, root, log=lambda *_: None, environ={}) == []
    assert gl.freeze(s2, root, PRE) is None
    assert (root / '2026-10-23.json').read_text() == first


def test_late_catch_up_is_flagged(dirs):
    snaps, root = dirs
    _write_snap(snaps, _snap())
    assert gl.update(LATE, _getter({}), snaps, root, log=lambda *_: None, environ={}) == ['froze 2026-10-23 (late)']
    assert gl.load('2026-10-23', root)['frozen_late'] is True


def test_results_join_and_postponed_excluded(dirs):
    snaps, root = dirs
    _write_snap(snaps, _snap())
    gl.update(PRE, _getter({}), snaps, root, log=lambda *_: None, environ={})
    rec = gl.load('2026-10-23', root)
    arena = [m for m in rec['matched'] if 'arena' in m['match']]
    a1 = next(m for m in arena if m['game'] == 'MTL@CHI')
    a2 = next((m for m in arena if m['game'] == 'TBL@COL'), None)
    goals = [{'gid': 2026020166, 'pid': a1['pid'], 'name': a1['name'], 'team': a1['team']}]
    if a2:
        goals.append({'gid': 2026020167, 'pid': a2['pid'], 'name': a2['name'], 'team': a2['team']})
    # still in progress: no results yet
    nxt = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)
    assert gl.update(nxt, _getter(_score_payload(goals, state='LIVE')), snaps, root, log=lambda *_: None, environ={}) == []
    assert gl.update(nxt, _getter(_score_payload(goals, ppd=True)), snaps, root, log=lambda *_: None, environ={}) == ['results 2026-10-23']
    r = gl.load('2026-10-23', root)
    assert r['results']['postponed'] == ['TBL@COL'] and r['results']['complete'] is True
    assert r['results']['scored'][str(a1['pid'])] == 1
    assert {k: v for k, v in r.items() if k != 'results'} == rec            # matches untouched by the results write
    night = gl.last_n_days(1, 'arena', '2026-10-24', root)[0]
    assert night['status'] == 'ok' and night['count'] == 1 and night['who'] == [(a1['name'], a1['team'], 1)]
    assert night['of'] == sum(1 for m in arena if m['game'] == 'MTL@CHI')   # postponed game's players excluded


def test_scorer_must_score_in_the_matched_game():
    rec = {'games': [{'gid': 1, 'game': 'MTL@CHI'}], 'matched': [{'pid': 5, 'name': 'X Y', 'team': 'MTL', 'game': 'MTL@CHI', 'match': {'arena': []}}]}
    pay = {'games': [{'id': 1, 'gameScheduleState': 'OK'}]}
    assert gl.join_results(rec, pay, {'scorers': [[5, 'X Y', 'TOR', 1]]})['results']['scored'] == {'5': 0}   # traded: other team
    assert gl.join_results(rec, pay, {'scorers': [[5, 'X Y', 'MTL', 2]]})['results']['scored'] == {'5': 2}


def _rec(root, day, **kw):
    p = Path(root) / f'{day}.json'
    p.write_text(json.dumps({'schema': 1, 'day': day, **kw}))
    return p


def test_prune_day90_kept_day91_deleted_non_dates_untouched(dirs):
    snaps, root = dirs
    today = date(2026, 10, 23)
    keep = _rec(root, '2026-07-25')        # 90 days before
    gone = _rec(root, '2026-07-24')        # 91 days before
    other = root / 'notes.json'
    other.write_text('{}')
    odd = root / '2026-07-01.json.bak'
    odd.write_text('{}')
    acc = snaps / 'accuracy' / '2026-01-01.json'
    acc.write_text('{}')
    slate = snaps / '2026-01-01.json'
    slate.write_text('{}')
    assert gl.prune(90, today, root, dry_run=True) == [gone] and gone.exists()     # dry run lists only
    assert gl.prune(90, today, root) == [gone]
    assert keep.exists() and not gone.exists() and other.exists() and odd.exists() and acc.exists() and slate.exists()


def test_prune_is_locked_to_snapshots_gematria(dirs):
    snaps, root = dirs
    for bad in (snaps, snaps / 'accuracy', root.parent.parent):
        with pytest.raises(ValueError):
            gl.prune(90, date(2026, 10, 23), bad)
    with pytest.raises(ValueError):
        gl.prune(0, date(2026, 10, 23), root)


def test_prune_uses_new_york_date_not_utc_or_mtime(dirs, monkeypatch):
    _, root = dirs
    p = _rec(root, '2026-07-24')
    # 02:30 UTC Oct 24 is still Oct 23 in New York -> 2026-07-24 is 91 days old: deleted; 2026-07-25 kept
    q = _rec(root, '2026-07-25')
    monkeypatch.setattr(gl, 'eastern_today', lambda now=None: gl.ET and datetime(2026, 10, 24, 2, 30, tzinfo=timezone.utc).astimezone(gl.ET).date())
    import os
    os.utime(q, (0, 0))                                       # ancient mtime is ignored
    assert gl.prune(90, None, root) == [p] and q.exists()
    assert gl.eastern_today(datetime(2026, 10, 24, 2, 30, tzinfo=timezone.utc)) == date(2026, 10, 23)


def _night(root, day, results=None, **kw):
    matched = [{'pid': 1, 'name': 'Ann Bee', 'team': 'MTL', 'game': 'MTL@CHI', 'match': {'arena': ['ordinal_root']}},
               {'pid': 2, 'name': 'Cid Dee', 'team': 'CHI', 'game': 'MTL@CHI', 'match': {'arena': ['ordinal_root'], 'date': ['reverse_root']}},
               {'pid': 3, 'name': 'Eve Fox', 'team': 'CHI', 'game': 'MTL@CHI', 'match': {'date': ['ordinal_root']}}]
    _rec(root, day, games=[{'gid': 1, 'game': 'MTL@CHI'}], matched=matched, results=results, **kw)


def test_last_n_days_and_average(dirs):
    _, root = dirs
    _night(root, '2026-10-20', {'complete': True, 'postponed': [], 'scored': {'1': 1, '2': 2, '3': 1}})
    _night(root, '2026-10-21', {'complete': True, 'postponed': [], 'scored': {'1': 0, '2': 0, '3': 1}})
    _night(root, '2026-10-22', None)
    n = gl.last_n_days(3, 'arena', '2026-10-23', root)
    assert [x['day'] for x in n] == ['2026-10-20', '2026-10-21', '2026-10-22']
    assert [(x['status'], x['count'], x['of']) for x in n] == [('ok', 2, 2), ('ok', 0, 2), ('pending', None, 2)]
    assert n[0]['who'] == [('Ann Bee', 'MTL', 1), ('Cid Dee', 'CHI', 2)]
    assert gl.average(n) == (1.0, 2)
    assert gl.last_n_days(3, 'date', '2026-10-23', root)[0]['count'] == 2
    assert [x['status'] for x in gl.last_n_days(2, 'arena', '2026-10-20', root)] == ['missing', 'missing']
    with pytest.raises(ValueError):
        gl.last_n_days(3, 'name', '2026-10-23', root)


def test_strip_states(dirs):
    _, root = dirs
    # empty: no history at all
    h0 = gl.strip_html(gl.last_n_days(3, 'arena', '2026-10-23', root))
    assert 'History starts tonight' in h0 and '<b>0</b>' not in h0
    # three nights with results
    for d, sc in (('2026-10-20', {'1': 1}), ('2026-10-21', {'2': 1}), ('2026-10-22', {'1': 1, '2': 2})):
        _night(root, d, {'complete': True, 'postponed': [], 'scored': sc})
    h3 = gl.strip_html(gl.last_n_days(3, 'arena', '2026-10-23', root))
    assert h3.count('class="gh-c ok"') == 3 and '3-night avg' in h3 and '<b>1.3</b>' in h3 and 'of 2' in h3
    assert '<details' in h3 and 'Cid Dee <span>CHI</span> ×2' in h3 and 'Arena-match scorers' in h3
    # missing night -> dash + no saved data; average relabeled
    (root / '2026-10-21.json').unlink()
    hm = gl.strip_html(gl.last_n_days(3, 'arena', '2026-10-23', root))
    assert 'no saved data' in hm and '<b>–</b>' in hm and '2-night avg' in hm and '<b>1.5</b>' in hm
    # pending -> excluded from the average
    _night(root, '2026-10-21', None)
    hp = gl.strip_html(gl.last_n_days(3, 'arena', '2026-10-23', root))
    assert 'pending' in hp and '2-night avg' in hp
    # reconstructed -> est. tag + one-line note
    _night(root, '2026-10-21', {'complete': True, 'postponed': [], 'scored': {}}, reconstructed=True)
    he = gl.strip_html(gl.last_n_days(3, 'arena', '2026-10-23', root))
    assert 'gh-est' in he and 'est.</em>' in he and gl.EST_NOTE in he and '3-night avg' in he
    assert not re.search(r'<[/\w!]', gl.strip_html.__doc__ or '')


def test_strip_css_is_sanitizer_safe_and_single_row():
    css = (HERE / 'assets' / 'v58.css').read_text()
    part = css.split('V5.9 gematria history strip')[1]
    assert '.gh-row{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:nowrap}' in part
    assert not re.search(r'<[/\w!]', part)


def test_flag_and_numbers_page_wiring(dirs):
    snaps, root = dirs
    assert flags.show_gem_history(secrets={}, environ={}) is True
    assert flags.show_gem_history(secrets={}, environ={'FEATURE_GEM_HISTORY': '0'}) is False
    _write_snap(snaps, _snap())
    assert gl.update(PRE, _getter({}), snaps, root, log=lambda *_: None, environ={'FEATURE_GEM_HISTORY': '0'}) == []
    assert not list(root.iterdir())
    src = (HERE / 'tabs' / 'numbers.py').read_text()
    i, j = src.index("gemlog.strip_html(gemlog.last_n_days(3,'arena',np_day)"), src.index('gmx.table_html(')
    assert src.index('np_flags.show_gem_history(st.secrets)') < i < j and 'except Exception:' in src[i:j]
    assert src.count('gemlog.') == 2


def test_workflow_steps_never_block_the_commit():
    wf = (HERE / '.github' / 'workflows' / 'precompute.yml').read_text()
    assert 'python gematria_log_v59.py update || echo' in wf and 'python gematria_log_v59.py prune --keep-days 90 || echo' in wf
    assert wf.index('accuracy_v58.py update') < wf.index('gematria_log_v59.py update') < wf.index('snapshot_store.py prune')
    assert wf.index('snapshot_store.py prune') < wf.index('gematria_log_v59.py prune') < wf.index('check_repo_size.py') < wf.index('git add -f -A snapshots/')


def test_no_games_night_and_size_guard(dirs, monkeypatch):
    snaps, root = dirs
    s = _snap('2026-10-25')
    s['games'], s['rankings'] = [], []
    rec = gl.build(s, PRE)
    assert rec['no_games'] and rec['results']['complete']
    gl.save(rec, root)
    assert gl.last_n_days(1, 'arena', '2026-10-26', root)[0]['status'] == 'no_games'
    monkeypatch.setattr(gl, 'MAX_BYTES', 500)
    big = gl.build(_snap(), PRE)
    assert big['players'] == [] and big['players_dropped'] is True and big['matched']
