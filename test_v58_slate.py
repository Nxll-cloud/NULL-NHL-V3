"""V5.8 SLATE FAILURE regressions (2026-10-23).

What failed: the 'Precompute NHL slate' GitHub workflow. Its 05:18 UTC run force-added snapshots/2026-10-23.json
(108,020 bytes: a normal 2-game snapshot), and from then on every run failed the 'Repo size check' step, because
check_repo_size.py applied the hand-upload rule 'every file < 100 KB' to the bot's own tracked snapshot. No newer
snapshot can be committed (a 12-game slate is ~675 KB), so the app falls back to slow live loading.
Also covered: tiny slates (2-game / 1-game / 0-game), the midnight-ET rollover and the score-endpoint shape."""
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import check_repo_size as crs
import live_feed_v56 as lf
import nhl_data
import parlay_v58 as parlay
import scorers_tonight_v58 as sctn
import ui_theme_v53 as ui
import v54_testkit as kit

HERE = Path(__file__).resolve().parent
BANNED_ODDS = ('American', 'Implied', 'Fair odds', 'Edge', '+EV', 'Odds:', 'Price')


# ------------------------------------------------------------------------------------- 1. the workflow size check
def _git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True)


@pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')
def test_tracked_slate_snapshot_does_not_fail_repo_size_check(tmp_path):
    """Exactly the CI state after the bot's first commit: snapshots/*.json is gitignored but force-added (tracked)."""
    _git(tmp_path, 'init', '-q')
    (tmp_path / '.gitignore').write_text('snapshots/*.json\n')
    (tmp_path / 'snapshots').mkdir()
    (tmp_path / 'snapshots' / '2026-10-23.json').write_text('x' * 108020)      # the real failing size
    (tmp_path / 'snapshots' / '2026-10-24.json').write_text('x' * 690214)      # a 12-game slate
    (tmp_path / 'app.py').write_text('print(1)\n')
    _git(tmp_path, 'add', '-A')
    _git(tmp_path, 'add', '-f', 'snapshots/')
    res = crs.check(tmp_path, max_file_kb=100)
    assert res['ok'], crs.report(res)
    assert not res['over_kb'] and len(res['snapshots']) == 2
    assert crs.main([str(tmp_path), '--max-file-kb', '100']) == 0
    # the hand-upload rule still applies to everything else
    (tmp_path / 'big.py').write_text('#' * 150_000)
    (tmp_path / 'snapshots' / 'notes.json').write_text('x' * 150_000)           # not a dated snapshot -> not exempt
    _git(tmp_path, 'add', '-A')
    _git(tmp_path, 'add', '-f', 'snapshots/notes.json')
    res = crs.check(tmp_path, max_file_kb=100)
    assert not res['ok'] and {p for p, _ in res['over_kb']} == {'big.py', 'snapshots/notes.json'}


def test_slate_snapshot_has_its_own_cap(tmp_path):
    (tmp_path / 'snapshots').mkdir()
    (tmp_path / 'snapshots' / '2026-10-24.json').write_text('x' * 60_000)
    res = crs.check(tmp_path, max_file_kb=100, max_snapshot_kb=50, use_gitignore=False)
    assert not res['ok'] and res['over_snapshot_kb'] and 'slate snapshot limit' in crs.report(res)
    assert crs.is_snapshot('snapshots/2026-10-24.json') and not crs.is_snapshot('snapshots/x.json')
    assert not crs.is_snapshot('assets/2026-10-24.json')


def test_workflow_still_runs_the_size_check():
    wf = (HERE / '.github' / 'workflows' / 'precompute.yml').read_text()
    assert 'python check_repo_size.py' in wf and '--max-file-kb 100' in wf and '--max-snapshot-kb 0' not in wf


# ------------------------------------------------------------------------------------- 2. tiny slates (parlay)
def _results(games, phase=None):
    """games: [(away, home, [(pid, team, lam), ...])] -> live_state_v56.slate_results-shaped rows."""
    out = []
    for i, (a, h, players) in enumerate(games):
        out.append({'slate': {'away': a, 'home': h, 'key': f'{a}@{h}', 'game_id': 2026020100 + i, 'start': '2026-10-24T00:00:00Z'},
                    'result': {'phase': (phase or {}).get(f'{a}@{h}', 'pregame'),
                               'players': [{'pid': pid, 'name': f'P{pid}', 'team': t, 'lam_game': lam, 'goals': 0}
                                           for pid, t, lam in players]}})
    return out


TWO = [('MTL', 'CHI', [(1, 'MTL', .5), (2, 'MTL', .45), (3, 'CHI', .4), (4, 'CHI', .3)]),
       ('TBL', 'COL', [(5, 'TBL', .55), (6, 'TBL', .2), (7, 'COL', .6), (8, 'COL', .35)])]


def test_two_game_slate_relaxes_to_one_leg_per_team():
    d = parlay.build(_results(TWO))
    assert d['per'] == 'team' and not d['short'] and len(d['legs']) == 4
    assert sorted(l['team'] for l in d['legs']) == ['CHI', 'COL', 'MTL', 'TBL']
    html = parlay.section_html(d, {}, {})
    assert 'Top four-leg parlay' in html and 'one leg per team' in html
    assert not any(b in html for b in BANNED_ODDS)


def test_two_game_slate_after_first_puck_drop_gives_labelled_two_leg_pick():
    d = parlay.build(_results(TWO, {'MTL@CHI': 'live'}))       # only TBL@COL is still eligible for a fresh build
    assert d['short'] and len(d['legs']) == 2 and {l['team'] for l in d['legs']} == {'TBL', 'COL'}
    assert d['joint'] == pytest.approx(parlay.p_anytime(.55) * parlay.p_anytime(.6))
    html = parlay.section_html(d, {}, {})
    assert 'Top two-leg parlay' in html and 'Only 2 teams' in html and 'not four' in html
    assert 'product of the two leg chances' in html and 'four leg chances' not in html
    assert not any(b in html for b in BANNED_ODDS)


def test_one_game_and_zero_game_slates():
    d = parlay.build(_results(TWO[:1]))
    assert d['short'] and len(d['legs']) == 2
    d3 = parlay.build(_results([TWO[0], ('NJD', 'SEA', [(9, 'NJD', .3)])]))     # 3 eligible teams -> three-leg pick
    assert d3['short'] and len(d3['legs']) == 3 and 'Top three-leg parlay' in parlay.section_html(d3, {}, {})
    d0 = parlay.build([])
    assert d0['legs'] == [] and d0['joint'] is None and not d0['short']
    html = parlay.section_html(d0, {}, {})
    assert 'No parlay pick yet' in html and 'at least two teams' in html
    d1 = parlay.build(_results([('MTL', 'CHI', [(1, 'MTL', .5)])]))           # only one eligible team -> no pick
    assert d1['legs'] == []


def test_all_games_final_gives_no_pick():
    d = parlay.build(_results(TWO, {'MTL@CHI': 'final', 'TBL@COL': 'final'}))
    assert d['legs'] == [] and 'No parlay pick yet' in parlay.section_html(d, {}, {})


# ------------------------------------------------------------------------------------- 3. midnight ET rollover
def test_slate_date_rolls_over_on_eastern_midnight_not_utc():
    utc = timezone.utc
    assert str(ui.eastern_today(datetime(2026, 10, 23, 3, 59, tzinfo=utc))) == '2026-10-22'   # 11:59 PM EDT
    assert str(ui.eastern_today(datetime(2026, 10, 23, 4, 0, tzinfo=utc))) == '2026-10-23'    # midnight EDT
    assert str(ui.eastern_today(datetime(2026, 10, 23, 6, 21, tzinfo=utc))) == '2026-10-23'   # the report time
    assert str(ui.eastern_today(datetime(2026, 12, 2, 4, 30, tzinfo=utc))) == '2026-12-01'    # EST (UTC-5)


def test_scorer_record_resets_on_rollover():
    state = {}
    rec = {'day': '2026-10-22', 'demo': False, 'players': {8478483: {'goals': 1}}, 'names': {}}
    sctn.for_slate(state, '2026-10-22', rec)
    assert sctn.active(state, '2026-10-22') and sctn.active(state, '2026-10-23') is None
    assert sctn.for_slate(state, '2026-10-23', rec)['players'] == {}        # yesterday's goals never leak into today


# ------------------------------------------------------------------------------------- 4. endpoint shapes
def test_score_endpoint_shape_gameweek_without_games(monkeypatch):
    """/v1/score/{day} (2026-10-23): games at the top level; gameWeek entries are counts only (no 'games' key)."""
    payload = {'prevDate': '2026-10-22', 'currentDate': '2026-10-23', 'nextDate': '2026-10-24',
               'gameWeek': [{'date': '2026-10-23', 'dayAbbrev': 'FRI', 'numberOfGames': 2}], 'oddsPartners': [],
               'games': [{'id': 2026020166, 'gameState': 'FUT', 'awayTeam': {'abbrev': 'MTL'}, 'homeTeam': {'abbrev': 'CHI'}}]}
    out = lf.parse_scores(payload)
    assert list(out) == ['2026020166'] and out['2026020166']['away'] == 'MTL'
    assert lf.parse_scores({'gameWeek': [{'date': '2026-10-23'}]}) == {} and lf.parse_scores(None) == {}
    # the schedule parser must not KeyError on the same count-only gameWeek shape
    monkeypatch.setattr(nhl_data, 'fetch_json', lambda path: {'gameWeek': [{'date': '2026-10-23', 'numberOfGames': 2}]})
    assert nhl_data.get_schedule('2026-10-23') == []


# ------------------------------------------------------------------------------------- 5. full app on tiny slates
def _clean(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_app_two_game_slate(monkeypatch, tmp_path):
    at = kit.run_app(monkeypatch, tmp_path, games=['NSH@BOS', 'NYR@TOR'])
    _clean(at)
    html = kit.markdown(at)
    assert 'parlay' in html and ('Top four-leg parlay' in html or 'Top two-leg parlay' in html or 'No parlay pick yet' in html)
    assert 'SJS' not in ' '.join(h.value for h in at.get('html') if 'npp' in h.value)


def test_app_zero_game_slate(monkeypatch, tmp_path):
    at = kit.run_app(monkeypatch, tmp_path, games=[])
    _clean(at)
