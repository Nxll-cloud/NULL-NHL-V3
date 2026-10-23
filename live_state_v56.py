"""V5.6 glue between the slate, the score/PBP feeds and the next-goal model (pure; the app injects cached fetchers).

Rank arrows: each game's ranks are remembered per *distinct* model input (event count + clock + phase). The first
time a game is seen its arrows compare with the pregame prior ranking; after that, with the previous update.
"""
from __future__ import annotations

import live_nextgoal_v56 as ng
import live_feed_v56 as lf

PHASE_FROM_SCORE = {'FUT': 'pregame', 'PRE': 'pregame', 'LIVE': 'live', 'CRIT': 'live', 'OFF': 'final', 'FINAL': 'final'}


def needs_pbp(score_state, slate_status=''):
    st = str(score_state or slate_status or '').upper()
    return st in ('LIVE', 'CRIT', 'OFF', 'FINAL')


def game_label(game):
    ph = ng.phase(game)
    if ph == 'final':
        return 'Final' + ('/' + game['ptype'] if game.get('ptype') in ('OT', 'SO') else '')
    if ph in ('live', 'shootout'):
        secs = game.get('secs_remaining')
        clock = {'inIntermission': game.get('intermission'),
                 'timeRemaining': f'{int(secs) // 60:02d}:{int(secs) % 60:02d}' if secs is not None else None}
        return lf.period_label(game.get('period'), game.get('ptype'), clock)
    return ''


def signature(game):
    return (len(game.get('events') or []), game.get('period'), game.get('secs_remaining'), game.get('state'))


def ranked_result(game, priors, memory, key, use_form=False):
    """Model + rank arrows with per-game memory. ``memory`` is a dict the caller persists (session_state)."""
    res = ng.model(game, priors, use_form=use_form)
    mem = memory.get(key)
    sig = signature(game)
    if mem is None:
        base = ng.model(ng.pregame_game(game.get('game_id'), game['away'], game['home']), priors, use_form=use_form)
        prev = ng.rerank(base['players'], None)
        basis = 'vs pregame prior'
        if ng.phase(game) == 'pregame':
            prev, basis = None, 'pregame prior'
        mem = {'sig': None, 'prev': prev, 'cur': None, 'basis': basis}
    if mem['sig'] != sig:
        if mem['cur'] is not None:
            mem['prev'], mem['basis'] = mem['cur'], 'vs previous update'
        mem['sig'] = sig
    mem['cur'] = ng.rerank(res['players'], mem['prev'])
    memory[key] = mem
    res['rank_basis'] = mem['basis']
    return res


def slate_results(games, priors, scores=None, pbp=None, memory=None, use_form=False):
    """games: matchup_center slate_games rows. scores: live_feed.parse_scores. pbp: {game_id: parsed game}.

    Returns one dict per game: {'slate', 'game', 'result', 'label', 'note', 'score'}."""
    scores, pbp, memory = scores or {}, pbp or {}, (memory if memory is not None else {})
    out = []
    for g in games:
        gid = str(g.get('game_id') or '')
        sc = scores.get(gid) or {}
        parsed = pbp.get(gid)
        note = ''
        if parsed is None:
            state = sc.get('state') or g.get('status') or 'FUT'
            if needs_pbp(state):
                note = 'Play-by-play unavailable right now; showing the pregame prior.'
            parsed = ng.pregame_game(gid, g['away'], g['home'], g.get('start'))
        res = ranked_result(parsed, priors, memory, gid, use_form)
        label = game_label(parsed) or sc.get('label', '')
        out.append({'slate': g, 'game': parsed, 'result': res, 'label': label, 'note': note, 'score': sc})
    return out


def strip_items(results):
    items = []
    for r in results:
        g, res = r['game'], r['result']
        sc = r.get('score') or {}
        lead = res['players'][0] if res['players'] and res['phase'] == 'live' else None
        items.append({'away': g['away'], 'home': g['home'], 'phase': res['phase'], 'label': r['label'] or ('Pregame' if res['phase'] == 'pregame' else ''),
                      'away_score': g.get('away_score') if g.get('away_score') is not None else sc.get('away_score'),
                      'home_score': g.get('home_score') if g.get('home_score') is not None else sc.get('home_score'), 'leader': lead})
    order = {'live': 0, 'shootout': 1, 'pregame': 2, 'final': 3}
    return sorted(items, key=lambda i: order.get(i['phase'], 9))


def tile_scores(results):
    """{game_key: {'away','home','label','phase'}} for the Home board tiles."""
    out = {}
    for r in results:
        g, res = r['game'], r['result']
        a = g.get('away_score') if g.get('away_score') is not None else (r.get('score') or {}).get('away_score')
        h = g.get('home_score') if g.get('home_score') is not None else (r.get('score') or {}).get('home_score')
        if a is None or h is None or res['phase'] == 'pregame':
            continue
        out[r['slate']['key']] = {'away': a, 'home': h, 'label': r['label'], 'phase': res['phase']}
    return out
