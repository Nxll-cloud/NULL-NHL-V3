"""V5.8 Home daily accuracy snapshot (offline; real captured NHL fixtures, no DEMO data)."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import accuracy_v58 as acc
import parlay_v58 as parlay

HERE = Path(__file__).resolve().parent
SNAP = json.loads((HERE / 'test_fixtures_v54' / 'slate_trimmed_20261022.json').read_text())   # real pre-game slate (21:11Z, puck drop 23:00Z)
SCORE = json.loads((HERE / 'test_fixtures_v58' / 'score_20261022_trimmed.json').read_text())  # real final score payload, same 3 games
NOW = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)   # 9 AM ET Oct 23 -> yesterday = Oct 22


class _R:
    def __init__(self, p, code=200):
        self.p, self.status_code = p, code

    def json(self):
        return self.p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def getter_for(payloads, calls=None):
    def get(url, timeout=None, **kw):
        if calls is not None:
            calls.append(url)
        for k, v in payloads.items():
            if url.endswith(k):
                return _R(v)
        raise ConnectionError('offline test: ' + url)
    return get


def write_snap(root, snap):
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{snap['day']}.json").write_text(json.dumps(snap))


def scored_entry():
    return acc.score(acc.predictions(SNAP, (), 'test', NOW), acc.results_from_score(SCORE), NOW)


# ------------------------------------------------------------------ dates
def test_eastern_yesterday_handles_utc_midnight():
    # 03:30 UTC Oct 23 is still Oct 22 in New York, so 'yesterday' is Oct 21
    assert acc.eastern_yesterday(datetime(2026, 10, 23, 3, 30, tzinfo=timezone.utc)).isoformat() == '2026-10-21'
    assert acc.eastern_yesterday(datetime(2026, 10, 23, 4, 30, tzinfo=timezone.utc)).isoformat() == '2026-10-22'
    assert acc.eastern_yesterday(datetime(2026, 10, 23, 4, 30)).isoformat() == '2026-10-22'   # naive = UTC
    assert acc.short_day('2026-10-22') == 'Oct 22'


def test_pregame_check_uses_first_puck_drop():
    assert acc.is_pregame(SNAP)
    late = dict(SNAP, updated_at='2026-10-22T23:05:00+00:00')
    assert not acc.is_pregame(late)


# ------------------------------------------------------------------ predictions + parlay
def test_predictions_are_the_pregame_model_and_parlay_matches_parlay_v58():
    e = acc.predictions(SNAP, (), 'test', NOW)
    assert e['n_players'] == len(e['players']) > 50 and e['snapshot_at'] == SNAP['updated_at']
    ranks = [p[4] for p in e['players']]
    assert ranks == sorted(ranks) and ranks[0] == 1
    assert all(0 < p[3] < 1 for p in e['players'])
    # deterministic: same snapshot -> same parlay, identical to parlay_v58 on an all-pregame slate
    assert acc.predictions(SNAP, (), 'x', NOW)['parlay']['legs'] == e['parlay']['legs']
    import matchup_center_v54 as mc, live_nextgoal_v56 as ng, live_state_v56 as ls
    res = ls.slate_results([dict(g, status='FUT') for g in mc.slate_games(SNAP['games'])], ng.priors_from_rankings(SNAP['rankings']), {}, {}, {})
    assert [l['pid'] for l in parlay.build(res, SNAP['rankings'])['legs']] == e['parlay']['legs']
    assert len(e['parlay']['legs']) == 4 and e['parlay']['derived'] and acc.PARLAY_NOTE in e['parlay']['note']


def test_out_players_are_excluded_from_the_rebuilt_parlay():
    e = acc.predictions(SNAP, (), 't', NOW)
    first = e['parlay']['legs'][0]
    e2 = acc.predictions(SNAP, {first}, 't', NOW)
    assert first not in e2['parlay']['legs'] and len(e2['parlay']['legs']) == 4


def test_flags_never_faked_without_real_openers():
    e = acc.predictions(SNAP, (), 't', NOW)
    assert e['flags'] == {'available': False, 'note': acc.FLAG_NA, 'flagged': []}
    rows = acc.rows(scored_entry())
    assert all(r['flag'] is None for r in rows)
    html = acc.card_html({'shown': scored_entry(), 'notes': [], 'trend': acc.trend([scored_entry()]), 'pending': None})
    assert 'Flag n/a (no saved prices)' in html and '<th class=n>Flag</th>' not in html


def test_flags_recorded_when_real_openers_are_saved():
    e = acc.predictions(SNAP, (), 't', NOW)
    pid, p = e['players'][0][0], e['players'][0][3]
    longshot_price = int(round(100 * (1 - (p - 0.05)) / (p - 0.05)))   # implied ~5 pts below the model
    e2 = acc.predictions(dict(SNAP, openers={str(pid): longshot_price, str(e['players'][1][0]): -500}), (), 't', NOW)
    assert e2['flags']['available'] and e2['flags']['flagged'] == [pid]


# ------------------------------------------------------------------ results + matching
def test_results_match_scorers_by_player_id_and_skip_shootout_goals():
    r = acc.results_from_score(SCORE)
    assert r['complete'] and r['n_games'] == 3
    assert sum(s[3] for s in r['scorers']) == sum(g['awayTeam']['score'] + g['homeTeam']['score'] for g in SCORE['games'])
    pastr = next(s for s in r['scorers'] if s[0] == 8477956)
    assert pastr[1] == 'David Pastrnak' and pastr[2] == 'BOS' and pastr[3] == 2
    so = json.loads(json.dumps(SCORE))
    g = so['games'][0]
    g['periodDescriptor'] = {'number': 5, 'periodType': 'SO'}
    g['homeTeam']['score'] += 1
    g['goals'].append({'periodDescriptor': {'periodType': 'SO'}, 'playerId': 1, 'teamAbbrev': g['homeTeam']['abbrev'], 'name': {'default': 'S. O'}})
    assert all(s[0] != 1 for s in acc.results_from_score(so)['scorers'])


def test_matching_is_by_id_not_name():
    e = acc.predictions(SNAP, (), 't', NOW)
    pid = e['players'][0][0]
    res = {'complete': True, 'n_games': 1, 'scorers': [[pid, 'Totally Different Name', 'XXX', 1], [999, e['players'][1][1], e['players'][1][2], 1]]}
    rows = {r['pid']: r for r in acc.rows(acc.score(e, res, NOW))}
    assert rows[pid]['rank'] == 1 and rows[pid]['p'] == e['players'][0][3]
    assert rows[999]['p'] is None and rows[999]['rank'] is None   # same name, different ID -> not matched


def test_pbp_fallback_when_goal_list_is_incomplete():
    broken = json.loads(json.dumps(SCORE))
    broken['games'][0]['goals'] = []
    gid = broken['games'][0]['id']
    pbp = {'awayTeam': {'id': 1, 'abbrev': 'NSH'}, 'homeTeam': {'id': 2, 'abbrev': 'BOS'},
           'rosterSpots': [{'playerId': 8477956, 'firstName': {'default': 'David'}, 'lastName': {'default': 'Pastrnak'}}],
           'plays': [{'typeDescKey': 'goal', 'periodDescriptor': {'periodType': 'REG'}, 'details': {'scoringPlayerId': 8477956, 'eventOwnerTeamId': 2}}]}
    r = acc.results_from_score(broken, lambda g: pbp if g == gid else None)
    assert [s for s in r['scorers'] if s[0] == 8477956][0][3] >= 1


def test_incomplete_slate_is_not_scored():
    live = json.loads(json.dumps(SCORE))
    live['games'][1]['gameState'] = 'LIVE'
    assert not acc.results_from_score(live)['complete']


# ------------------------------------------------------------------ summary, compaction, trend
def test_summary_numbers_and_compaction():
    e = scored_entry()
    s = e['summary']
    assert (s['n_scorers'], s['top_hits'], s['top_n'], s['parlay_hits'], s['parlay_legs']) == (22, 4, 10, 2, 4)
    assert s['n_modeled_scorers'] == 20 and s['flag_n'] is None
    assert s['mean_p'] < s['avg_p_scorers'] and abs(s['realized'] - 20 / s['n_players']) < 1e-4
    assert e['compacted'] and len(e['players']) < s['n_players']
    assert len(json.dumps(e)) < 100 * 1024


def test_trend_math():
    def ent(day, hits, n, ap, mp, real):
        return {'day': day, 'summary': {'top_hits': hits, 'top_n': n, 'avg_p_scorers': ap, 'mean_p': mp, 'realized': real}}
    t = acc.trend([ent('2026-10-20', 2, 10, .2, .15, .1), ent('2026-10-21', 5, 10, .3, .15, .2), {'day': '2026-10-22', 'summary': None}])
    assert t['top_hits'] == 7 and t['top_n'] == 20 and t['top_rate'] == pytest.approx(.35)
    assert t['avg_p_scorers'] == pytest.approx(.25) and t['realized'] == pytest.approx(.15)
    assert [x['day'] for x in t['nights']] == ['2026-10-20', '2026-10-21']
    many = [ent(f'2026-10-{d:02d}', 1, 10, .2, .1, .1) for d in range(1, 16)]
    assert len(acc.trend(many, 10)['nights']) == 10 and acc.trend(many, 10)['nights'][0]['day'] == '2026-10-06'
    assert acc.spark(acc.trend(many)['nights']).startswith('<svg')


# ------------------------------------------------------------------ view: yesterday / fallback / no snapshot
def test_view_shows_yesterday_from_the_log(tmp_path):
    acc.save_entry(scored_entry(), tmp_path / 'log')
    v = acc.view(NOW, getter_for({}), tmp_path / 'log', tmp_path / 'snaps')
    assert v['shown']['day'] == '2026-10-22' and not v['notes']
    html = acc.card_html(v)
    assert 'Oct 22 · 22 scorers · model top-10 hit 4/10 · parlay 2/4 legs' in html and 'D. Pastrnak</span> ×2' in html and '>David Pastrnak<' in html


def test_view_falls_back_to_latest_completed_slate(tmp_path):
    acc._LIVE.clear()
    acc.save_entry(scored_entry(), tmp_path / 'log')
    later = datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)   # yesterday = Oct 24: no snapshot, no log
    v = acc.view(later, getter_for({}), tmp_path / 'log', tmp_path / 'snaps')
    assert v['shown']['day'] == '2026-10-22'
    assert v['notes'][0] == 'No saved pre-game predictions for Oct 24.' and 'most recent completed slate: Oct 22' in v['notes'][1]


def test_no_snapshot_message(tmp_path):
    acc._LIVE.clear()
    v = acc.view(NOW, getter_for({}), tmp_path / 'log', tmp_path / 'snaps')
    assert v['shown'] is None and v['notes'] == ['No saved pre-game predictions for Oct 22.']
    assert 'No saved pre-game predictions for Oct 22.' in acc.card_html(v)


def test_on_the_fly_when_log_missing_and_post_drop_snapshot_rejected(tmp_path):
    acc._LIVE.clear()
    write_snap(tmp_path / 'snaps', SNAP)
    calls = []
    v = acc.view(NOW, getter_for({'score/2026-10-22': SCORE}, calls), tmp_path / 'log', tmp_path / 'snaps')
    assert v['shown']['day'] == '2026-10-22' and v['shown']['summary']['top_hits'] == 4
    # real sources only: NHL results (api-web) + V5.9 situational layer inputs (NHL stats API, MoneyPuck xG)
    assert any('api-web.nhle.com' in c for c in calls)
    assert all(c.startswith(('https://api-web.nhle.com/', 'https://api.nhle.com/stats/', 'https://moneypuck.com/')) for c in calls)
    acc._LIVE.clear()
    write_snap(tmp_path / 's2', dict(SNAP, updated_at='2026-10-22T23:30:00+00:00'))
    v2 = acc.view(NOW, getter_for({'score/2026-10-22': SCORE}), tmp_path / 'log2', tmp_path / 's2')
    assert v2['shown'] is None and 'after puck drop' in v2['notes'][0]


def test_pending_tonight_is_labelled_not_scored(tmp_path):
    acc._LIVE.clear()
    tonight = dict(SNAP, day='2026-10-23', updated_at='2026-10-23T09:00:00+00:00',
                   games=[dict(g, **{'Start (UTC)': '2026-10-23T23:00:00Z'}) for g in SNAP['games']])
    acc.save_entry(acc.predictions(tonight, (), 't', NOW), tmp_path / 'log')
    v = acc.view(NOW, getter_for({}), tmp_path / 'log', tmp_path / 'snaps')
    assert v['shown'] is None and v['pending']['day'] == '2026-10-23'
    assert 'Oct 23 is logged pre-game' in acc.card_html(v)


# ------------------------------------------------------------------ workflow update / no demo
def test_update_freezes_pregame_then_scores_after_final(tmp_path):
    snaps, log = tmp_path / 'snaps', tmp_path / 'log'
    write_snap(snaps, SNAP)
    pre = datetime(2026, 10, 22, 21, 30, tzinfo=timezone.utc)
    acc.update(pre, getter_for({}), snaps, log, injuries_fn=lambda: {'injuries': []}, log=lambda *_: None)
    e = acc.load_entry('2026-10-22', log)
    assert e and e['results'] is None and 'ESPN out list' in e['parlay']['note']
    # a post-drop rewrite of the snapshot never changes the frozen predictions
    write_snap(snaps, dict(SNAP, updated_at='2026-10-22T23:40:00+00:00', rankings=SNAP['rankings'][:5]))
    acc.update(datetime(2026, 10, 22, 23, 45, tzinfo=timezone.utc), getter_for({}), snaps, log, log=lambda *_: None)
    assert acc.load_entry('2026-10-22', log)['n_players'] == e['n_players']
    acc.update(NOW, getter_for({'score/2026-10-22': SCORE}), snaps, log, log=lambda *_: None)
    done = acc.load_entry('2026-10-22', log)
    assert done['summary']['top_hits'] == 4 and done['compacted']


def test_update_never_raises_when_feeds_are_down(tmp_path):
    write_snap(tmp_path / 'snaps', SNAP)
    acc.save_entry(acc.predictions(SNAP, (), 't', NOW), tmp_path / 'log')
    acc.update(NOW, getter_for({}), tmp_path / 'snaps', tmp_path / 'log', log=lambda *_: None)
    assert acc.load_entry('2026-10-22', tmp_path / 'log')['results'] is None


def test_no_demo_sources():
    src = (HERE / 'accuracy_v58.py').read_text()
    for bad in ('demo_line', 'load_demo', 'DEMO_FIXTURE', 'PLAYBOOK_V56_PBP_DIR', 'demo_odds'):
        assert bad not in src


def test_committed_log_files_are_valid_and_small():
    for p in (HERE / 'snapshots' / 'accuracy').glob('*.json'):
        e = json.loads(p.read_text())
        assert e['day'] == p.stem and e['schema'] == acc.SCHEMA and p.stat().st_size < 100 * 1024
        assert e['flags']['available'] is False or e['flags']['flagged'] is not None


def test_home_calls_the_card_once_below_the_long_shot():
    src = (HERE / 'tabs' / 'home.py').read_text()
    assert src.count("__import__('accuracy_v58').home_html()") == 1
    assert src.index('longshot.section_html') < src.index('accuracy_v58') < src.index('v5.render_home')
    wf = (HERE / '.github' / 'workflows' / 'precompute.yml').read_text()
    assert 'python accuracy_v58.py update' in wf and wf.index('accuracy_v58') < wf.index('git add -f -A snapshots/')
