"""Offline next-goal cycle, authoritative corrections and presentation safety regressions."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

import live_nextgoal_v56 as ng
import live_state_v56 as ls
import scorers_tonight_v58 as scored
import v56_ui as ui
from test_v56_model import Clock, PRIORS, _slate, payload, play


def raw(plays=(), **kwargs):
    return payload(list(plays), **kwargs)


def nonshot():
    return {'eventId': 99, 'typeDescKey': 'faceoff', 'periodDescriptor': {'number': 1, 'periodType': 'REG'},
            'timeInPeriod': '05:00', 'details': {}}


def corrected_sequence(*bodies):
    seq = iter(bodies)
    def fetch(_):
        b = next(seq)
        if isinstance(b, Exception):
            raise b
        return deepcopy(b)
    clock = Clock()
    poller = ng.Poller(1, fetch, clock=clock, rand=lambda: 1)
    return poller, clock


def score_for(g, **extra):
    return dict(state=g['state'], away_score=g['away_score'], home_score=g['home_score'], **extra)


def result(g, sc=None, mem=None):
    return ls.slate_results(_slate(), PRIORS, {'1': sc or score_for(g)}, {'1': g}, mem or {})[0]['result']


def test_new_goal_same_player_can_remain_top_and_badge_is_history():
    before = ng.parse_pbp(raw())
    after = ng.parse_pbp(raw([play(1, 'goal')]))
    a, b = ng.model(before, PRIORS), result(after)
    assert a['players'][0]['pid'] == b['players'][0]['pid'] == 11
    assert b['players'][0]['goals'] == 1 and b['players'][0]['p_next'] > 0
    assert b['goal_cycle'] != a['goal_cycle'] and b['last_scorer']['shooter'] == 11
    badge = scored.from_pbp({'1': after}, after['date'])
    h = ui.nextgoal_panel(b, '20262027', scored=badge)
    assert 'Last confirmed scorer: A1 X (AAA)' in h
    assert 'Current next-goal candidates' in h and 'Previous scorers remain eligible' in h
    assert 'npsc' in h and '<small>next goal</small>' in h


def test_different_player_can_become_current_leader_after_event():
    g = ng.parse_pbp(raw())
    a = ng.model(g, PRIORS)
    goals = [play(i, 'goal', shooter=21, team_id=2, x=-85) for i in range(1, 8)]
    b = result(ng.parse_pbp(raw(goals)))
    assert a['players'][0]['pid'] == 11 and b['players'][0]['pid'] == 21
    assert b['last_scorer']['shooter'] == 21
    assert {p['pid'] for p in a['players']} == {p['pid'] for p in b['players']}


@pytest.mark.parametrize('replacement', [[], [play(1, 'shot-on-goal')], [play(1, 'missed-shot')]])
def test_overturned_goal_removed_or_reclassified(replacement):
    old = raw([nonshot(), play(1, 'goal')])
    new = raw([nonshot()] + replacement)
    p, _ = corrected_sequence(old, new)
    first = p.poll()
    latest = p.poll(force=True)
    assert ng.goal_revision(first['events']) != ng.goal_revision(latest['events'])
    assert not any(e['kind'] == 'goal' for e in latest['events'])
    assert result(latest)['last_scorer'] is None
    assert not scored.from_pbp({'1': latest}, latest['date'])['players']
    assert sum(r['goals'] for r in result(latest)['players']) == 0


def test_same_id_same_count_corrected_scorer_and_credit_invalidates_ranks():
    a = raw([play(1, 'goal')])
    b = raw([play(1, 'goal', shooter=21, team_id=2)])
    p, _ = corrected_sequence(a, b, b)
    g1 = p.poll(); memory = {}
    r1 = ls.ranked_result(g1, PRIORS, memory, '1')
    g2 = p.poll(force=True)
    r2 = ls.ranked_result(g2, PRIORS, memory, '1')
    assert len(g1['events']) == len(g2['events'])
    assert ls.signature(g1) != ls.signature(g2)
    assert r1['goal_cycle'] != r2['goal_cycle']
    assert r2['last_scorer']['name'] == 'H1 X'
    assert r2['rank_basis'] == 'vs previous update'
    signature = memory['1']['sig']; previous = dict(memory['1']['prev'])
    g3 = p.poll(force=True)
    r3 = ls.ranked_result(g3, PRIORS, memory, '1')
    assert memory['1']['sig'] == signature and memory['1']['prev'] == previous
    assert r3['goal_cycle'] == r2['goal_cycle']
    assert [r['p_next'] for r in r3['players']] == [r['p_next'] for r in r2['players']]
    badge = scored.from_pbp({'1': g3}, g3['date'])
    assert scored.lookup(badge, 11) is None and scored.lookup(badge, 21)['goals'] == 1


@pytest.mark.parametrize('field,value', [('secs', 301), ('period', 2), ('team', 'HHH'), ('ptype', 'OT')])
def test_meaningful_goal_revision_not_count(field, value):
    g = ng.parse_pbp(raw([play(1, 'goal')]))
    revised = deepcopy(g); revised['events'][0][field] = value
    assert ng.goal_revision(g['events']) != ng.goal_revision(revised['events'])
    assert ls.signature(g) != ls.signature(revised)


@pytest.mark.parametrize('broken', ['empty', 'partial', 'incremental', 'missing_plays', 'missing_shooter',
                                     'truncated', 'bad_score', 'bad_sog', 'wrong_game', 'error'])
def test_invalid_partial_or_failed_fetch_never_wipes_confirmed_goal(broken):
    old = raw([nonshot(), play(1, 'goal')])
    new = deepcopy(old)
    if broken == 'empty':
        new = raw([])
    elif broken == 'partial':
        new['partial'] = True
    elif broken == 'incremental':
        new['hasMore'] = True
    elif broken == 'missing_plays':
        del new['plays']
    elif broken == 'missing_shooter':
        del new['plays'][1]['details']['scoringPlayerId']
    elif broken == 'truncated':
        new['plays'] = [nonshot()]
    elif broken == 'bad_score':
        new['awayTeam']['score'] = 2
    elif broken == 'bad_sog':
        new['awayTeam']['sog'] = 5
    elif broken == 'wrong_game':
        new['id'] = 2
    else:
        new = ConnectionError('offline')
    p, _ = corrected_sequence(old, new, old)
    g = p.poll(); revision = ng.goal_revision(g['events']); fetched = g['pbp_fetched_at']
    failed = p.poll(force=True)
    assert ng.goal_revision(failed['events']) == revision
    assert failed['pbp_fetched_at'] == fetched and p.failures == 1
    assert not result(failed)['candidates_active'] and result(failed)['feed_warning']
    recovered = p.poll(force=True)
    assert result(recovered)['candidates_active'] and not result(recovered)['feed_warning']


def test_incremental_mode_cannot_establish_complete_snapshot():
    p = ng.Poller(1, lambda _: raw([play(1, 'goal')]), full_snapshot=False)
    assert p.poll() is None and p.failures == 1


@pytest.mark.parametrize('scores', [(0, 0), (2, 0), (1, 1)])
def test_score_mismatch_both_directions_suppresses_panel_and_strip_then_recovers(scores):
    g = ng.parse_pbp(raw([play(1, 'goal')]))
    sc = dict(state='LIVE', away_score=scores[0], home_score=scores[1])
    rows = ls.slate_results(_slate(), PRIORS, {'1': sc}, {'1': g}, {})
    r = rows[0]['result']; html = ui.nextgoal_panel(r, '20262027')
    assert not r['candidates_active'] and 'totals disagree' in r['feed_warning']
    assert '<small>next goal</small>' not in html and 'Awaiting synchronized feeds' in html
    strip = ls.strip_items(rows)
    assert strip[0]['leader'] is None and 'next:' not in ui.live_strip(strip)
    recovered = result(g)
    assert recovered['candidates_active'] and recovered['players'][0]['p_next'] > 0


@pytest.mark.parametrize('state,ptype', [('FINAL', 'REG'), ('OFF', 'OT'), ('LIVE', 'SO'), ('FINAL', 'SO')])
def test_final_ot_shootout_hide_active_predictions(state, ptype):
    period = 5 if ptype == 'SO' else 4 if ptype == 'OT' else 3
    p = raw([play(1, 'goal', period=1), play(2, 'goal', shooter=21, team_id=2),
             play(3, 'goal', period=5, ptype='SO')], state=state, period=period, ptype=ptype)
    if ptype == 'SO':
        p['awayTeam']['score'] += 1  # official SO deciding point must NOT be a skater goal
    g = ng.parse_pbp(p)
    assert ng.goal_totals_match(g) and len(ng.goal_revision(g['events'])) == 2
    r = result(g, score_for(g, label='Final/SO' if ptype == 'SO' else 'Final'))
    assert not r['candidates_active']
    html = ui.nextgoal_panel(r, '20262027')
    assert 'Historical skater summary' in html and '<small>next goal</small>' not in html
    assert 'class="ngbar"' not in html
    assert r['last_scorer']['shooter'] == 21


@pytest.mark.parametrize('score_state', ['LIVE', 'CRIT', 'OFF', 'FINAL', 'OVER'])
def test_missing_pbp_never_highlights_live_or_final_prior(score_state):
    rows = ls.slate_results(_slate(), PRIORS, {'1': {'state': score_state, 'away_score': 2, 'home_score': 1}}, {}, {})
    r = rows[0]['result']
    assert not r['candidates_active']
    assert ls.strip_items(rows)[0]['leader'] is None
    h = ui.nextgoal_panel(r, '20262027')
    assert '<small>next goal</small>' not in h and 'unavailable' in r['feed_warning']
    assert 'No confirmed play-by-play skater history' in h and 'history unavailable' in h
    assert 'PBP game clock: unavailable' in h


def test_final_score_before_live_pbp_suppresses_and_live_score_after_final_pbp_stays_suppressed():
    live = ng.parse_pbp(raw([play(1, 'goal')]))
    a = result(live, score_for(live) | {'state': 'FINAL'})
    assert a['display_phase'] == 'final' and not a['candidates_active']
    final = deepcopy(live); final['state'] = 'FINAL'
    b = result(final, score_for(live))
    assert b['display_phase'] == 'final' and not b['candidates_active']


def test_stale_warning_unavailable_score_and_future_not_invented():
    g = ng.parse_pbp(raw([play(1, 'goal')]))
    g['pbp_warning'] = 'PBP snapshot is stale; retaining last good data.'
    r = result(g)
    assert not r['candidates_active'] and 'stale' in r['feed_warning']
    del g['pbp_warning']
    rows = ls.slate_results(_slate(), PRIORS, {}, {'1': g}, {})
    assert not rows[0]['result']['candidates_active']
    html = ui.nextgoal_panel(result(g), '20262027', updated='pretend provider time')
    assert 'local fetch time unavailable' in html and 'pretend provider time' not in html
    assert 'PBP game clock: P1 15:00 left' in html
    g['pbp_fetched_at'] = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    assert 'locally fetched 2026-01-01 00:00:00 UTC' in ui.nextgoal_panel(result(g), '20262027')


def test_assist_and_official_goal_credit_not_own_goal_shooter_invention():
    goal = play(1, 'goal', shooter=21, team_id=2)
    goal['details']['assist1PlayerId'] = 11
    g = ng.parse_pbp(raw([goal]))
    assert g['events'][0]['shooter'] == 21 and g['events'][0]['team'] == 'HHH'
    r = result(g)
    assert next(p for p in r['players'] if p['pid'] == 11)['goals'] == 0
    assert r['last_scorer']['name'] == 'H1 X'


def test_model_probabilities_unchanged_by_presentation_safety_gate():
    g = ng.parse_pbp(raw([play(1, 'goal')]))
    baseline = ng.model(g, PRIORS)
    gated = result(g, {'state': 'LIVE', 'away_score': 0, 'home_score': 0})
    assert [(p['pid'], p['p_next'], p['rate']) for p in baseline['players']] == [
        (p['pid'], p['p_next'], p['rate']) for p in gated['players']]


def test_manual_refresh_updates_corrected_goal_and_strip_together(monkeypatch, tmp_path):
    """Actual app/fragment path on captured data; no requests leave the test fixture router."""
    import json
    from pathlib import Path
    from v54_testkit import HERE, run_app
    monkeypatch.setenv('MODEL_XG', '0')
    monkeypatch.setenv('MODEL_SITUATIONAL', '0')
    f = HERE / 'test_fixtures_v56'
    gid = '2026020164'
    pbp = json.loads((f / f'pbp_live_{gid}.json').read_text())
    board = json.loads((f / 'score_20261022_live.json').read_text())
    files = {'score.json': f / 'score_20261022_live.json', gid + '.json': f / f'pbp_live_{gid}.json'}
    extra = json.loads((f / f'slate_extra_{gid}.json').read_text())['games']
    at = run_app(monkeypatch, tmp_path, extra_games=extra, pbp_files=files)
    assert not at.exception
    def tab_html():
        tab = next(t for t in at.tabs if t.label == '⏱ Live Next Goal')
        return ' '.join(h.value for h in tab.get('html'))
    before = tab_html()
    assert 'Last confirmed scorer: Brandon Montour (SEA)' in before
    assert 'Current next-goal candidates' in before
    # Official review changes the final goal into a saved shot; event ID and SOG stay the same.
    goal = next(p for p in reversed(pbp['plays']) if p['typeDescKey'] == 'goal')
    goal['typeDescKey'] = 'shot-on-goal'
    goal['details']['shootingPlayerId'] = goal['details'].pop('scoringPlayerId')
    tid = goal['details']['eventOwnerTeamId']
    side = 'awayTeam' if pbp['awayTeam']['id'] == tid else 'homeTeam'
    pbp[side]['score'] -= 1
    for g in board['games']:
        if str(g['id']) == gid:
            g[side]['score'] -= 1
    (tmp_path / 'pbp' / (gid + '.json')).write_text(json.dumps(pbp))
    (tmp_path / 'pbp' / 'score.json').write_text(json.dumps(board))
    at.button(key='v56_ng_refresh').click().run()
    assert not at.exception
    after = tab_html()
    assert 'Last confirmed scorer: Brandon Montour (SEA)' not in after
    assert 'Current next-goal candidates' in after
    # Both mini strip and detailed panel show the revised last scorer, not a frozen settled pick.
    expected = ng.last_confirmed_scorer(ng.parse_pbp(pbp))['name']
    assert after.count('Last confirmed scorer: ' + expected) >= 2
    assert 'locally fetched ' in after and 'totals disagree' not in after
