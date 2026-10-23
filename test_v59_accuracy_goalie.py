"""V5.9: goalie pill on the Home accuracy card. Position comes from per-game NHL data or the saved slate's roster, matched by
player ID; it is never guessed from names, and an unknown position shows no pill. Offline: real captured score payload plus
hand-built boxscore position blocks."""
import json
from datetime import datetime, timezone
from pathlib import Path

import accuracy_v58 as acc

HERE = Path(__file__).resolve().parent
SNAP = json.loads((HERE / 'test_fixtures_v54' / 'slate_trimmed_20261022.json').read_text())
SCORE = json.loads((HERE / 'test_fixtures_v58' / 'score_20261022_trimmed.json').read_text())
NOW = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)


def _scorers():
    return [(g['id'], int(x['playerId'])) for g in SCORE['games'] for x in g.get('goals') or [] if x.get('playerId') is not None]


def _box(goalie_pid, skater_pid):
    return {'playerByGameStats': {'awayTeam': {'goalies': [{'playerId': goalie_pid}], 'forwards': [{'playerId': skater_pid, 'position': 'C'}]},
                                  'homeTeam': {}}}


def test_boxscore_and_rosterspots_positions():
    assert acc.positions_from_boxscore(_box(1, 2)) == {1: 'G', 2: 'C'}
    assert acc.positions_from_pbp({'rosterSpots': [{'playerId': 3, 'positionCode': 'G'}, {'playerId': 4}]}) == {3: 'G'}


def test_card_pill_for_goalie_scorer_only():
    (gid_a, g_pid), (gid_b, s_pid) = _scorers()[0], next(x for x in _scorers() if x[1] != _scorers()[0][1])
    boxes = {gid_a: _box(g_pid, -1), gid_b: _box(-2, s_pid)} if gid_a != gid_b else {gid_a: _box(g_pid, s_pid)}
    res = acc.results_from_score(SCORE, None, lambda gid: boxes.get(gid) or {})
    assert res['positions'][str(g_pid)] == 'G' and res['positions'][str(s_pid)] == 'C'
    e = acc.score(acc.predictions(SNAP, (), 'test', NOW), res, NOW)
    rows = {r['pid']: r for r in acc.rows(e)}
    assert rows[g_pid]['position'] == 'G' and rows[s_pid]['position'] == 'C'
    html = acc.card_html({'shown': e, 'trend': {}, 'notes': []}, max_rows=99, snap_root=HERE / 'nonexistent')
    assert html.count('class="npg"') == 1   # exactly the one goalie scorer row


def test_unknown_position_no_pill_and_feed_failure_safe():
    def boom(gid):
        raise ConnectionError('offline')
    res = acc.results_from_score(SCORE, None, boom)
    assert res['positions'] == {}
    e = acc.score(acc.predictions(SNAP, (), 'test', NOW), res, NOW)
    assert 'positions' not in e['results'] and all(r['position'] is None for r in acc.rows(e))
    assert 'class="npg"' not in acc.card_html({'shown': e, 'trend': {}, 'notes': []}, max_rows=99, snap_root=HERE / 'nonexistent')


def test_snapshot_roster_positions_fallback(tmp_path):
    (tmp_path / f"{SNAP['day']}.json").write_text(json.dumps(SNAP))
    pos = acc.snapshot_positions(SNAP['day'], tmp_path)
    assert pos and 'G' not in set(pos.values())   # rankings are skaters only -> they never produce a goalie pill
    e = acc.score(acc.predictions(SNAP, (), 'test', NOW), acc.results_from_score(SCORE), NOW)
    assert 'class="npg"' not in acc.card_html({'shown': e, 'trend': {}, 'notes': []}, max_rows=99, snap_root=tmp_path)
