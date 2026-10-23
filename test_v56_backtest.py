"""V5.6 next-goal backtest: no lookahead, metrics, write-once baseline, opening-line CSV. Offline only."""
import json
from pathlib import Path

import pytest

import backtest_next_goal as bt
import live_nextgoal_v56 as ng

FIX = Path(__file__).parent / 'test_fixtures_v56'
DATE = '2026-10-22'


def _payloads():
    return [json.loads((FIX / f).read_text()) for f in ('pbp_2026020154.json', 'pbp_2026020162.json')]


def _logs(payloads):
    """Synthetic logs: 10 earlier games plus one ON the slate date and one after (both must be ignored)."""
    logs = {}
    for p in payloads:
        for s in p['rosterSpots']:
            pid = int(s['playerId'])
            rows = [{'gameDate': f'2026-10-{d:02d}', 'goals': pid % 2, 'shots': 2 + pid % 3} for d in range(8, 18)]
            rows += [{'gameDate': DATE, 'goals': 5, 'shots': 20}, {'gameDate': '2026-10-24', 'goals': 5, 'shots': 20}]
            logs[pid] = rows
    return logs


def _getter(payloads, logs):
    calls = []

    def get(url):
        calls.append(url)
        if '/schedule/' in url:
            return {'gameWeek': [{'date': DATE, 'games': [{'id': p['id'], 'gameType': 2} for p in payloads]}]}
        if '/play-by-play' in url:
            gid = int(url.split('/gamecenter/')[1].split('/')[0])
            return next(p for p in payloads if p['id'] == gid)
        if '/game-log/' in url:
            return {'gameLog': logs.get(int(url.split('/player/')[1].split('/')[0]), [])}
        raise AssertionError(url)
    get.calls = calls
    return get


def test_priors_only_use_games_before_the_slate():
    roster = {1: {'name': 'A', 'team': 'X', 'pos': 'C'}}
    logs = {1: [{'gameDate': '2026-04-02', 'goals': 1, 'shots': 3}, {'gameDate': '2026-04-04', 'goals': 3, 'shots': 9},
                {'gameDate': '2026-04-05', 'goals': 2, 'shots': 5}]}
    pr = bt.priors_as_of(logs, roster, '2026-04-04')[1]
    assert (pr['gp'], pr['goals'], pr['sog'], pr['form']) == (1.0, 1, 3.0, None)


def test_goal_moments_have_no_lookahead():
    p = _payloads()[0]
    n = 0
    for i, e, g, full in bt.goal_moments(p):
        n += 1
        assert all((x['period'], x['secs'], x['order']) <= (e['period'], e['secs'], e['order']) for x in g['events'])
        assert e not in g['events'] and len(g['events']) == i
        goals_before = [x for x in full['events'][:i] if x['kind'] == 'goal']
        assert (g['away_score'] or 0) + (g['home_score'] or 0) == len(goals_before)
        assert ng.phase(g) == 'live' and g['period'] == e['period']
    assert n == 6


def test_offline_run_metrics_and_baselines():
    pays = _payloads()
    r = bt.run_backtest(DATE, payloads=pays, logs=_logs(pays))
    h = r['headline']
    assert h['games'] == 2 and h['goals'] == 9 == len(r['records'])
    for k in (1, 3, 5):
        assert 0 <= h[f'game_top{k}'] <= 1 and 0 <= h[f'rand_team_top{k}'] <= 1
    assert h['log_loss'] > 0 and 0 <= h['brier'] <= 2
    rec = r['records'][0]
    for key in ('matchup', 'period', 'time', 'score_before', 'strength', 'top', 'top_q', 'scorer', 'rank', 'team_rank', 'q'):
        assert key in rec
    assert not any(k.startswith('_') for k in rec)
    assert {p['pattern'] for p in r['patterns']} >= {'even strength'}
    assert r['lines']['status'].startswith('blocked')
    assert r['slate_date'] == DATE and len(r['code_hash']) == 16


def test_baseline_is_write_once(tmp_path):
    path = tmp_path / 'baseline.json'
    a = {'slate_date': DATE, 'code_hash': 'x', 'headline': {'game_top1': 0.1, 'goals': 9}}
    b = {'slate_date': DATE, 'code_hash': 'y', 'headline': {'game_top1': 0.2, 'goals': 9}}
    assert bt.run_and_compare(a, path)['written'] is True
    before = path.read_bytes()
    out = bt.run_and_compare(b, path)
    assert out['written'] is False and path.read_bytes() == before
    assert out['deltas']['game_top1'] == {'now': 0.2, 'baseline': 0.1, 'delta': 0.1}
    assert out['deltas']['_meta'] == {'same_slate': True, 'same_code': False}
    with pytest.raises(bt.BaselineExists):
        bt.save_baseline(b, path)
    assert path.read_bytes() == before
    assert bt.run_and_compare(b, path, reset=True)['written'] is True
    assert json.loads(path.read_text())['code_hash'] == 'y'


def test_cli_first_run_writes_then_never_overwrites(tmp_path, capsys):
    pays = _payloads()
    get = _getter(pays, _logs(pays))
    path = tmp_path / 'b.json'
    assert bt.main(['--date', DATE, '--baseline', str(path)], getter=get) == 0
    assert 'baseline written' in capsys.readouterr().out
    first = path.read_bytes()
    bt.main(['--date', DATE, '--baseline', str(path), '--json', str(path)], getter=get)
    out = capsys.readouterr().out
    assert 'baseline unchanged' in out and path.read_bytes() == first
    bt.main(['--baseline', str(path)], getter=get)          # date defaults to the baseline's slate
    assert path.read_bytes() == first
    bt.main(['--date', DATE, '--baseline', str(path), '--reset-baseline'], getter=get)
    assert 'baseline written' in capsys.readouterr().out
    bt.main(['--baseline-only', '--baseline', str(path)], getter=get)
    assert 'goals 9 in 2 games' in capsys.readouterr().out
    assert all('api-web.nhle.com' in u for u in get.calls)


def test_opening_lines_csv_devig_and_compare(tmp_path):
    f = tmp_path / 'lines.csv'
    f.write_text(','.join(bt.LINE_COLUMNS) + '\n'
                 '# comment row\n'
                 '2026-10-22,1,Ann,10,X,BookA,yes,+150,2026-10-21T10:00Z\n'
                 '2026-10-22,1,Ann,10,X,BookA,yes,+300,2026-10-22T10:00Z\n'
                 '2026-10-22,1,Ann,10,X,BookA,no,-200,2026-10-21T10:00Z\n'
                 '2026-10-22,1,Bob,11,X,BookA,yes,+400,2026-10-21T10:00Z\n')
    rows = bt.load_opening_lines(f)
    assert len(rows) == 3                                   # later +300 quote is not the opener
    m = bt.devig(rows)
    ann, bob = m[('1', '10')], m[('1', '11')]
    py, pn = 100 / 250, 200 / 300
    assert ann['two_sided'] and ann['p'] == pytest.approx(py / (py + pn))
    assert not bob['two_sided'] and bob['p'] == pytest.approx(0.2)
    games = [{'game_id': 1}]
    pre = {1: [{'pid': 10, 'name': 'Ann', 'p_any': 0.5, 'scored': True}, {'pid': 11, 'name': 'Bob', 'p_any': 0.1, 'scored': False},
               {'pid': 12, 'name': 'Cy', 'p_any': 0.3, 'scored': False}]}
    c = bt.compare_lines(games, pre, m)
    assert c['n'] == 2 and c['positive_edge_n'] == 1 and c['positive_edge_hit'] == 1.0
    assert c['rows'][0]['edge'] == pytest.approx(0.5 - ann['p'], abs=1e-4)


def test_lines_csv_rejects_bad_input(tmp_path):
    f = tmp_path / 'bad.csv'
    f.write_text('player,odds\nAnn,+100\n')
    with pytest.raises(ValueError):
        bt.load_opening_lines(f)
    with pytest.raises(ValueError):
        bt.implied('+50')


def test_template_and_stored_baseline():
    tpl = (bt.ROOT / 'backtests' / 'opening_lines_template.csv').read_text().splitlines()
    assert tpl[0].split(',') == bt.LINE_COLUMNS and bt.load_opening_lines(bt.ROOT / 'backtests' / 'opening_lines_template.csv') == []
    base = bt.load_baseline()
    assert base is not None and bt.BASELINE_PATH.stat().st_size < 100 * 1024
    assert base['slate_date'] == '2026-04-04' and base['season'] == '20252026'
    assert {'model_version', 'code_hash', 'headline', 'records', 'calibration_next_goal', 'patterns'} <= set(base)
    assert base['headline']['goals'] == len(base['records']) > 50
    assert base['lines']['n'] == 0 and base['lines']['status'].startswith('blocked')


def test_season_for():
    assert bt.season_for('2026-04-04') == '20252026' and bt.season_for('2026-10-22') == '20262027'


def test_app_l10_prior_mode():
    roster = {1: {'name': 'A', 'team': 'X', 'pos': 'C'}}
    rows = [{'gameDate': f'2026-03-{d:02d}', 'goals': 0, 'shots': 1} for d in range(1, 11)]
    rows += [{'gameDate': f'2026-03-{d:02d}', 'goals': 1, 'shots': 4} for d in range(11, 21)]
    pr = bt.priors_as_of({1: rows}, roster, '2026-04-04', mode='app_l10')[1]
    assert (pr['gp'], pr['goals'], pr['sog']) == (20.0, 10, 80.0)
    assert bt.priors_as_of({1: rows}, roster, '2026-04-04')[1]['sog'] == 50.0
