"""V5.6 glue between the slate, the score/PBP feeds and the next-goal model (pure; the app injects cached fetchers).

Rank arrows: each game's ranks are remembered per *distinct* model input (event count + clock + phase). The first
time a game is seen its arrows compare with the pregame prior ranking; after that, with the previous update.
"""
from __future__ import annotations

import live_nextgoal_v56 as ng
import live_feed_v56 as lf

PHASE_FROM_SCORE = {'FUT': 'pregame', 'PRE': 'pregame', 'LIVE': 'live', 'CRIT': 'live', 'OFF': 'final', 'FINAL': 'final', 'OVER': 'final'}


def needs_pbp(score_state, slate_status=''):
    st = str(score_state or slate_status or '').upper()
    return st in ('LIVE', 'CRIT', 'OFF', 'FINAL', 'OVER')


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
    return (ng.event_revision(game.get('events')), game.get('period'), game.get('secs_remaining'),
            game.get('state'), game.get('situation'), game.get('away_score'), game.get('home_score'))


def model(game, priors, use_form=False, situ=None):
    """V5.9: the ONE next-goal calculation every surface shares (tabs/live.py, Live Next Goal DEMO, goalie views,
    accuracy log): the V5.6 model plus the situational layer ``situ`` (situational_v58.layer; None = V5.6 exactly)."""
    return ng.model(game, priors, use_form=use_form, situ=situ)


def pregame_model(game_id, away, home, priors, use_form=False, situ=None):
    """The same calculation on the pregame (no events) version of a game."""
    return model(ng.pregame_game(game_id, away, home), priors, use_form=use_form, situ=situ)


def ranked_result(game, priors, memory, key, use_form=False, situ=None):
    """Model + rank arrows with per-game memory. ``memory`` is a dict the caller persists (session_state)."""
    res = model(game, priors, use_form=use_form, situ=situ)
    mem = memory.get(key)
    sig = signature(game)
    if mem is None:
        base = pregame_model(game.get('game_id'), game['away'], game['home'], priors, use_form=use_form, situ=situ)
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


def feed_status(game, score=None, missing=False):
    """Presentation safety gate. Never changes rates, eligibility or the model's math."""
    score = score or {}
    ph = ng.phase(game)
    score_ph = PHASE_FROM_SCORE.get(str(score.get('state') or '').upper())
    score_so = score.get('ptype') == 'SO' or score.get('label') == 'SO' or '/SO' in score.get('label', '')
    display = ('final' if ph == 'final' or score_ph == 'final' else
               'shootout' if ph == 'shootout' or score_so else
               'live' if ph == 'live' or score_ph == 'live' else 'pregame')
    warnings = []
    if missing and score_ph in ('live', 'final'):
        warnings.append('Play-by-play unavailable or incomplete; awaiting synchronization, no active next-goal highlight.')
    elif ph == 'live':
        if not score:
            warnings.append('Score feed unavailable; synchronization unverified.')
        elif score_ph == 'pregame':
            warnings.append('Score and play-by-play phases disagree; awaiting synchronization.')
        if not ng.goal_totals_match(game):
            warnings.append('PBP goal history and score disagree; awaiting complete history.')
    if score_ph == 'live' and ph == 'pregame' and not missing:
        warnings.append('Score and play-by-play phases disagree; awaiting synchronization.')
    if ph == 'live' and score_ph == 'final':
        warnings.append('Score feed is final; awaiting final play-by-play.')
    if ph == 'final' and score_ph == 'live':
        warnings.append('Play-by-play is final; score feed has not synchronized.')
    # Exact score agreement matters in BOTH directions. SO is never a next-goal market.
    if ph == 'live' and score_ph == 'live' and not score_so:
        a = (game.get('away_score'), game.get('home_score'))
        b = (score.get('away_score'), score.get('home_score'))
        if any(v is None for v in a + b):
            warnings.append('Score totals unavailable; awaiting synchronization.')
        elif a != b:
            warnings.append('Score and play-by-play totals disagree; awaiting synchronization.')
    if game.get('pbp_warning'):
        warnings.append(game['pbp_warning'])
    if missing and not warnings:
        warnings.append('Play-by-play unavailable; no active next-goal highlight.')
    active = display in ('live', 'pregame') and not warnings and not missing
    return {'candidates_active': active, 'display_phase': display, 'feed_warning': ' '.join(warnings)}


def slate_results(games, priors, scores=None, pbp=None, memory=None, use_form=False, situ=None):
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
                note = 'Play-by-play unavailable right now; no active next-goal highlight.'
            parsed = ng.pregame_game(gid, g['away'], g['home'], g.get('start'))
        res = ranked_result(parsed, priors, memory, gid, use_form, situ)
        res.update(feed_status(parsed, sc, missing=pbp.get(gid) is None and needs_pbp(sc.get('state') or g.get('status'))))
        if res['feed_warning']:
            note = res['feed_warning']
        if pbp.get(gid) is None and needs_pbp(sc.get('state') or g.get('status')):
            res.update(history_available=False, pbp_clock='unavailable',
                       display_scores=(sc.get('away_score'), sc.get('home_score')))
        label = game_label(parsed) or sc.get('label', '')
        out.append({'slate': g, 'game': parsed, 'result': res, 'label': label, 'note': note, 'score': sc})
    return out


def strip_items(results):
    items = []
    for r in results:
        g, res = r['game'], r['result']
        sc = r.get('score') or {}
        ph = res.get('display_phase', res['phase'])
        lead = res['players'][0] if res['players'] and ph == 'live' and res.get('candidates_active', True) else None
        items.append({'away': g['away'], 'home': g['home'], 'phase': ph, 'label': r['label'] or ('Pregame' if ph == 'pregame' else ''),
                      'feed_warning': res.get('feed_warning', ''), 'last_scorer': res.get('last_scorer'),
                      'history_available': res.get('history_available', True),
                      'pbp_clock': res.get('pbp_clock'), 'pbp_fetched_at': res.get('pbp_fetched_at'),
                      'away_score': g.get('away_score') if g.get('away_score') is not None else sc.get('away_score'),
                      'home_score': g.get('home_score') if g.get('home_score') is not None else sc.get('home_score'), 'leader': lead,
                      'venue': (r.get('slate') or {}).get('venue') or ''})
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
