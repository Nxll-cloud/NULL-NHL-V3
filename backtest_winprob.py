"""Audit win% backtest: pregame model win estimate (winprob_v59) vs the final result, V5.9 estimate vs MODEL_WINPROB_V2.

Same inputs as backtest_next_goal.py (official play-by-play, priors from game logs dated BEFORE the slate, optional
point-in-time situational layer) plus team GF/GA per game from the NHL stats API team/summary report (games before the
slate). Scored on P(home wins) with log loss, Brier and pick accuracy. Writes only the --json path given (never the
next-goal baseline).

  python backtest_winprob.py --date 2026-04-04 --situ --json backtests/audit_winprob_2026-04-04.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import backtest_next_goal as bt
import live_nextgoal_v56 as ng
import winprob_v59 as wp


def team_context(date, getter=None):
    """{'teams': {tri: {gf_pg, ga_pg, team_gp}}} from team/summary strictly before ``date`` (situational_v58 parser)."""
    import situational_v58 as sit
    ctx = sit.fetch_context(date, bt.season_for(date), getter=getter, parts=())
    return {'teams': ctx.get('teams') or {}, 'skaters': ctx.get('skaters') or {}}


def score(rows, key):
    ps = [(min(1 - 1e-6, max(1e-6, r[key])), r['home_won']) for r in rows]
    n = len(ps)
    if not n:
        return None
    ll = -sum(math.log(p if y else 1 - p) for p, y in ps) / n
    br = sum((p - y) ** 2 for p, y in ps) / n
    acc = sum((p >= 0.5) == bool(y) for p, y in ps) / n
    return {'n': n, 'log_loss': round(ll, 4), 'brier': round(br, 4), 'accuracy': round(acc, 4),
            'mean_p_home': round(sum(p for p, _ in ps) / n, 4)}


def game_rows(date, payloads, logs, situ=None, ctx=None, drop_roster=False):
    """One row per game: p_home under V5.9 and V2. ``drop_roster``: price pregame from priors only (the app before
    rosters are out), which exercises the 18-dressed selection."""
    rows = []
    for p in payloads:
        g0 = ng.parse_pbp(p)
        roster = g0['roster']
        plogs = {pid: logs.get(pid) or logs.get(str(pid)) or [] for pid in roster}
        priors = bt.priors_as_of(plogs, roster, date)
        game = ng.pregame_game(g0['game_id'], g0['away'], g0['home']) | ({} if drop_roster else {'roster': roster})
        res = ng.model(game, priors, situ=situ)
        r = {'result': res, 'slate': {'key': f"{g0['away']}@{g0['home']}"}}
        lam1 = wp.expected_goals(res)
        e2 = wp.expected_goals_v2(res, ctx)
        if lam1 is None or e2 is None or g0['away_score'] is None:
            continue
        a, h = g0['away'], g0['home']
        f2 = wp.favorite_v2(r, ctx)
        rows.append({'game_id': g0['game_id'], 'matchup': f'{a}@{h}', 'final': f"{g0['away_score']}-{g0['home_score']}",
                     'home_won': int(g0['home_score'] > g0['away_score']),
                     'p_home_v59': round(wp.win_prob(lam1[a], lam1[h])[1], 4),
                     'p_home_v2': round(wp.win_prob_v2(e2['lam'][a], e2['lam'][h])[1], 4),
                     'xg_v59': [round(lam1[a], 2), round(lam1[h], 2)], 'xg_v2': [round(e2['lam'][a], 2), round(e2['lam'][h], 2)],
                     'range_v2_fav_pct': [f2['lo'], f2['hi']], 'team_norm': e2['team_norm'], 'n_skaters': e2['n']})
    return rows


def run(date, situ_on=False, getter=None):
    getter = getter or bt.cached(bt.http_getter, bt.CACHE_DIR)
    payloads, logs = bt.fetch_slate(date, getter)
    situ = bt.situ_layer(date, payloads, True) if situ_on else None
    ctx = (situ.ctx if situ is not None else None) or team_context(date)
    out = {'slate_date': date, 'situational': situ_on, 'pp_coherent': True if situ_on else None,
           'teams_with_gf_ga': sum(1 for t in (ctx.get('teams') or {}).values() if 'gf_pg' in t), 'variants': {}}
    for name, drop in (('roster', False), ('priors_only_18_dressed', True)):
        rows = game_rows(date, payloads, logs, situ, ctx, drop)
        out['variants'][name] = {'v59': score(rows, 'p_home_v59'), 'v2': score(rows, 'p_home_v2'), 'games': rows}
    v = out['variants']['roster']
    out['decision'] = {'rule': 'MODEL_WINPROB_V2 default ON only if V2 log loss <= V5.9 log loss on 2026-04-04 (roster variant)',
                       'v59_log_loss': v['v59']['log_loss'], 'v2_log_loss': v['v2']['log_loss'],
                       'regression': v['v2']['log_loss'] > v['v59']['log_loss']}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--date', action='append', required=True)
    ap.add_argument('--situ', action='store_true')
    ap.add_argument('--json', default=None)
    a = ap.parse_args(argv)
    res = [run(d, a.situ) for d in a.date]
    for r in res:
        for name, v in r['variants'].items():
            print(r['slate_date'], name, 'V5.9', v['v59'], '| V2', v['v2'])
    if a.json:
        if Path(a.json).resolve() == bt.BASELINE_PATH.resolve():
            ap.error('refusing to write over the next-goal baseline')
        Path(a.json).write_text(json.dumps(res[0] if len(res) == 1 else res, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
