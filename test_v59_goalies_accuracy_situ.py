"""V5.9: the goalie views' pregame fallback (mc_goalies_v56.threat_result / game_view) and the accuracy log's frozen
predictions (accuracy_v58.predictions / update) use the SAME shared calculation + situational layer as Home, Matchup
Center and Live Next Goal (live_state_v56.model / pregame_model, situational_v58.layer). Offline, recorded fixtures."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import accuracy_v58 as acc
import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import matchup_center_v54 as mc
import mc_goalies_v56 as mcg
import situational_v58 as sit

HERE = Path(__file__).resolve().parent
SNAP = json.loads((HERE / 'test_fixtures_v54' / 'slate_trimmed_20261022.json').read_text())   # real pre-game slate
NOW = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)
ROWS = SNAP['rankings']
PRIORS = ng.priors_from_rankings(ROWS)
GAMES = mc.slate_games(SNAP['games'])
# very different goalies per team so the goalie part moves every shooter (team average, no listed starter)
SV = {'NSH': 0.860, 'BOS': 0.935, 'NYR': 0.940, 'TOR': 0.860, 'SJS': 0.865, 'OTT': 0.930}
GOALIES = [{'Team': t, 'Goalie': f'{t} Test Goalie', 'Player ID': str(900 + i), 'SA': 1000, 'Saves': round(sv * 1000)}
           for i, (t, sv) in enumerate(SV.items())]


def layer():
    return sit.layer(sit.context(goalies=GOALIES, parts=('goalie',)), {})


def ps(res):
    return {p['pid']: p['lam_game'] for p in res['players']}


def final_game():
    g = GAMES[0]
    return dict(ng.pregame_game(g['game_id'], g['away'], g['home']), state='OFF')


# ------------------------------------------------------------------ goalie views (mc_goalies_v56:115)
def test_goalie_view_prior_is_the_shared_calculation_with_the_layer():
    situ, g = layer(), final_game()
    final = {'phase': 'final', 'players': []}
    on, basis = mcg.threat_result(final, g, PRIORS, situ=situ)
    off, _ = mcg.threat_result(final, g, PRIORS)
    shared = lstate.pregame_model(g['game_id'], g['away'], g['home'], PRIORS, situ=situ)
    assert basis == 'pregame prior (game over)'
    assert ps(on) == ps(shared) and len(ps(on)) >= 10
    assert ps(on) != ps(off)                                     # the layer changes the numbers
    assert ps(off) == ps(lstate.pregame_model(g['game_id'], g['away'], g['home'], PRIORS))   # off = V5.6 exactly
    # ... and the same numbers the live panels' pregame base (ranked_result) uses for this game
    home = lstate.slate_results([dict(GAMES[0])], PRIORS, situ=situ)[0]['result']
    assert ps(home) == ps(on)


def test_game_view_threads_situ_to_the_fallback():
    situ, g, s = layer(), final_game(), GAMES[0]
    final = {'phase': 'final', 'players': []}
    on = mcg.game_view(s, final, g, {}, [], {}, priors=PRIORS, situ=situ)
    off = mcg.game_view(s, final, g, {}, [], {}, priors=PRIORS)
    key = lambda v: [(x['pid'], round(x['p_next'], 6)) for x in v['reverse']]
    shared = lstate.pregame_model(g['game_id'], g['away'], g['home'], PRIORS, situ=situ)
    ng.rerank(shared['players'], None)
    want = {p['pid']: round(p['p_next'], 6) for p in shared['players']}
    assert key(on) and all(want[pid] == p for pid, p in key(on))
    assert key(on) != key(off)


def test_matchup_tab_passes_the_app_layer_to_both_goalie_views():
    src = (HERE / 'tabs' / 'matchup.py').read_text(encoding='utf-8')
    assert src.count('mcg.game_view(') == 2 and src.count('priors=_v56_priors,situ=_v56_situ)') == 2
    assert 'ng.model(' not in (HERE / 'mc_goalies_v56.py').read_text(encoding='utf-8')


# ------------------------------------------------------------------ accuracy log (accuracy_v58:97)
def test_accuracy_predictions_use_the_shared_calculation_with_the_layer():
    situ = layer()
    on, off = acc.predictions(SNAP, (), 't', NOW, situ=situ), acc.predictions(SNAP, (), 't', NOW)
    want = {}
    for g in GAMES:
        for p in lstate.pregame_model(g['game_id'], g['away'], g['home'], PRIORS, situ=situ)['players']:
            want[p['pid']] = round(1 - math.exp(-p['lam_game']), 4)
    got = {r[0]: r[3] for r in on['players']}
    assert got and all(want[pid] == p for pid, p in got.items())
    assert got != {r[0]: r[3] for r in off['players']}
    assert off['model'] == acc.MODEL_TAG and on['model'].startswith('V5.9') and 'goalie' in on['model']


def test_situ_for_respects_the_flag_and_feeds(monkeypatch):
    monkeypatch.setenv('MODEL_SITUATIONAL', '0')
    assert acc.situ_for('2026-10-22') is None
    monkeypatch.setenv('MODEL_SITUATIONAL', '1')
    monkeypatch.setenv('MODEL_XG', '0')

    class R:
        def __init__(self, p):
            self.p = p

        def raise_for_status(self):
            pass

        def json(self):
            return self.p
    rows = [{'playerId': 900 + i, 'teamAbbrevs': t, 'goalieFullName': f'{t} G', 'shotsAgainst': 1000, 'saves': round(sv * 1000)}
            for i, (t, sv) in enumerate(SV.items())]

    def getter(url, params=None, **kw):
        if url.endswith('goalie/summary'):
            assert 'gameDate<"2026-10-22"' in params['cayenneExp']    # point-in-time: stats strictly before the slate day
            return R({'data': rows})
        raise ConnectionError('offline test')
    situ = acc.situ_for('2026-10-22', getter=getter)
    assert situ is not None and 'xg' not in situ.ctx['parts']
    a = acc.predictions(SNAP, (), 't', NOW, situ=situ)
    b = acc.predictions(SNAP, (), 't', NOW, situ=layer())
    assert [r[:4] for r in a['players']] == [r[:4] for r in b['players']]
    # every feed down -> neutral layer -> the V5.6 numbers exactly (only the tag differs)
    dead = acc.predictions(SNAP, (), 't', NOW, situ=acc.situ_for('2026-10-22', getter=lambda *a, **k: (_ for _ in ()).throw(ConnectionError())))
    assert [r[:4] for r in dead['players']] == [r[:4] for r in acc.predictions(SNAP, (), 't', NOW)['players']]


def test_workflow_freeze_uses_the_layer(tmp_path, monkeypatch):
    monkeypatch.setenv('MODEL_SITUATIONAL', '1')
    monkeypatch.setattr(acc, 'situ_for', lambda day, games=(), getter=None, starters=False, environ=None: layer())
    snaps, log = tmp_path / 'snaps', tmp_path / 'log'
    snaps.mkdir()
    (snaps / '2026-10-22.json').write_text(json.dumps(SNAP))
    pre = datetime(2026, 10, 22, 21, 30, tzinfo=timezone.utc)
    acc.update(pre, lambda *a, **k: (_ for _ in ()).throw(ConnectionError()), snaps, log, injuries_fn=lambda: {'injuries': []}, log=lambda *_: None)
    e = acc.load_entry('2026-10-22', log)
    assert e['model'].startswith('V5.9') and e['players'] == acc.predictions(SNAP, (), 't', NOW, situ=layer())['players']


def test_season_of():
    assert acc.season_of('2026-10-22') == '20262027' and acc.season_of('2027-03-01') == '20262027'
