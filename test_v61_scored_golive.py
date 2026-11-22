"""V6.1 scored-tonight markers on a session opened before puck drop.

Root cause: the only timers that refresh live data (np_scorer_watch, the Live Next Goal fragments) got run_every=None when
no game was live at that full run, so a page opened pregame never picked up goals or scored-tonight badges until a manual
reload or the 30-minute timer. Real data: CAR @ NYR 2026-11-22 (game 2026020373), captured live at 4-1 in the 2nd."""
import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import scorers_tonight_v58 as sctn

HERE = Path(__file__).resolve().parent
F = HERE / 'test_fixtures_v56'
PBP = json.loads((F / 'pbp_live_2026020373.json').read_text())
SCORE = json.loads((F / 'score_20261122_live.json').read_text())
SCORERS = {8480762: ('Eric Robinson', 'CAR'), 8476459: ('Mika Zibanejad', 'NYR'), 8482809: ('Jackson Blake', 'CAR'),
           8482100: ('Alexander Nikishin', 'CAR'), 8480336: ('Sean Walker', 'CAR')}
DAY = '2026-11-22'


def _game():
    g = ng.parse_pbp(PBP)
    ng.validate_snapshot(PBP, g, '2026020373', None)
    return g


def test_real_car_nyr_scorers_by_player_id():
    rec = sctn.from_pbp({'2026020373': _game()}, DAY)
    got = {p: (r['name'], r['team']) for p, r in rec['players'].items()}
    assert got == SCORERS and all(r['goals'] == 1 for r in rec['players'].values())
    assert rec['players'][8476459]['events'][0]['strength'] == 'PP'          # Zibanejad P1 14:12 PPG
    for pid, (name, _) in SCORERS.items():
        b = sctn.badge_for(rec, pid=pid)
        assert 'class="npsc' in b and 'CAR @ NYR' in b
        assert sctn.badge_for(rec, pid=str(pid)) == b and sctn.badge_for(rec, pid=float(pid)) == b   # str / float ids
        assert 'npsc' in sctn.badge_for(rec, name=name)                         # unique-name fallback
        html = sctn.mark_html(f'<td>{name}</td>', rec)
        assert html.count('class="npsc') == 1
    assert sctn.badge_for(rec, pid=8478550) == ''                               # did not score
    ticker = sctn.ticker(rec)
    assert '5 players · 5 goals' in ticker and all(n in ticker for n, _ in SCORERS.values())


def test_real_score_feed_marks_only_car_nyr_due():
    scores = {k: v for k, v in __import__('live_feed_v56').parse_scores(SCORE).items()}
    assert scores['2026020373']['state'] == 'LIVE' and scores['2026020374']['state'] == 'FUT'
    due = [gid for gid, s in scores.items() if lstate.needs_pbp(s['state'])]
    assert due == ['2026020373']


GAMES = [{'game_id': '2026020373', 'start': '2026-11-22T17:30:00Z', 'status': 'PRE'},
         {'game_id': '2026020374', 'start': '2026-11-22T22:00:00Z', 'status': 'FUT'}]


def test_awaiting_live_window():
    t = lambda h, m=0: datetime(2026, 11, 22, h, m, tzinfo=timezone.utc)
    assert lstate.awaiting_live(GAMES, (), t(12)) is True                     # morning: games still to go live
    assert lstate.awaiting_live(GAMES, ('2026020373',), t(19, 45)) is True    # CAR@NYR live, BUF@TBL later
    assert lstate.awaiting_live(GAMES, ('2026020373', '2026020374'), t(22, 5)) is False
    assert lstate.awaiting_live(GAMES[:1], (), t(4)) is False                 # more than 12 h before puck drop
    assert lstate.awaiting_live(GAMES[:1], (), t(17, 30) + timedelta(hours=7)) is False   # long past, never went live
    assert lstate.awaiting_live([dict(GAMES[1], status='FINAL')], (), t(21)) is False
    assert lstate.awaiting_live([{'game_id': '1', 'start': 'bad', 'status': 'FUT'}], (), t(21)) is False
    assert lstate.awaiting_live([{'game_id': '1', 'start': '2026-11-22T22:00:00', 'status': 'FUT'}], (), t(21)) is True


def test_poller_pregame_near_puck_drop_polls_every_two_minutes():
    pre = dict(PBP, gameState='FUT', plays=[], clock={}, awayTeam=dict(PBP['awayTeam'], score=0, sog=0),
               homeTeam=dict(PBP['homeTeam'], score=0, sog=0))
    start = datetime.fromisoformat(PBP['startTimeUTC'].replace('Z', '+00:00')).timestamp()
    for offset, want in ((-300, 120), (-3 * 3600, 600), (120, 120)):
        p = ng.Poller('2026020373', lambda gid: pre, clock=lambda: start + offset, rand=lambda: 0.0)
        assert p.poll() is not None and p.next_due - (start + offset) == want
    live = ng.Poller('2026020373', lambda gid: PBP, clock=lambda: start + 3600)
    assert ng.phase(live.poll()) == 'live' and live.next_due - (start + 3600) == 30
    assert ng.minutes_to_start({'start': 'x'}, 0) is None


def test_watcher_runs_while_a_game_awaits_go_live():
    src = (HERE / 'app.py').read_text(encoding='utf-8')
    assert "@st.fragment(run_every=('45s' if _v56_live_n else '60s' if _np_watch_go_live else None))" in src
    assert "if _np_watch_go_live and np_go_live_changed():" in src
    for k in ("'v56_pbp_due'", "'_v56_pbp_due0'", "'_v56_pbp_live0'", "'_v56_go_live': False"):
        assert k in src                                                       # safe defaults when the live section fails
    live = (HERE / 'tabs' / 'live.py').read_text(encoding='utf-8')
    assert 'def v56_pbp_due(' in live and '_v56_go_live=(not _v56_live_n)' in live
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'np_go_live_changed')
    assert any(isinstance(n, ast.ExceptHandler) for n in ast.walk(fn))           # never raises inside the fragment


def test_go_live_changed_logic():
    tree = ast.parse((HERE / 'app.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'np_go_live_changed')
    state = {'scores': {}, 'pbp': {}}
    ns = {'np_day': DAY, 'ng': ng, '_v56_pbp_due0': (), '_v56_pbp_live0': (),
          'v56_scores_cached': lambda day: (state['scores'], None),
          'v56_pbp_due': lambda scores: tuple(g for g, s in scores.items() if lstate.needs_pbp(s.get('state'))),
          'v56_collect': lambda force=False: (state['pbp'], {})}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'app.py', 'exec'), ns)
    assert ns['np_go_live_changed']() is False                                # still pregame
    state['scores'] = {'2026020373': {'state': 'LIVE'}}
    assert ns['np_go_live_changed']() is True                                 # puck drop -> one full rerun
    ns['_v56_pbp_due0'] = ('2026020373',)
    state['pbp'] = {'2026020373': _game()}
    assert ns['np_go_live_changed']() is True                                 # PBP turned live since that run
    ns['_v56_pbp_live0'] = ('2026020373',)
    assert ns['np_go_live_changed']() is False                                # no rerun loop
    ns['v56_scores_cached'] = lambda day: (_ for _ in ()).throw(RuntimeError('feed down'))
    assert ns['np_go_live_changed']() is False


def test_app_live_car_nyr_shows_markers(monkeypatch, tmp_path):
    from v54_testkit import run_app, markdown
    extra = [{'Game ID': 2026020373, 'Away': 'CAR', 'Home': 'NYR', 'Start (UTC)': '2026-11-22T17:30:00Z', 'Status': 'LIVE',
              'Venue': 'Madison Square Garden'}]
    at = run_app(monkeypatch, tmp_path, games=['CAR@NYR'], extra_games=extra,
                 pbp_files={'score.json': F / 'score_20261122_live.json', '2026020373.json': F / 'pbp_live_2026020373.json'})
    assert not at.exception
    text = markdown(at)
    assert 'Scored tonight · 5 players · 5 goals' in text
    assert all(n in text for n, _ in SCORERS.values())
    assert text.count('class="npsc') >= 5


def test_scored_badge_never_clipped_by_ellipsis_css():
    v56 = (HERE / 'assets' / 'v56.css').read_text(encoding='utf-8')
    v58 = (HERE / 'assets' / 'v58.css').read_text(encoding='utf-8')
    for css, sel in ((v56, '.v55 .ngn b:has(.npsc){'), (v56, '.v55 .gtr b:has(.npsc){'), (v58, '.v58-num .npr-name:has(.npsc){')):
        rule = css.split(sel, 1)[1].split('}', 1)[0]
        assert 'overflow:visible' in rule and 'white-space:normal' in rule
    # the unbadged rows keep their one-line ellipsis
    assert '.v55 .ngn b{display:block;color:var(--ink);font:700 .92rem var(--fb);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' in v56
