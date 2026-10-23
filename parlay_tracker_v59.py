"""V5.9 live four-leg parlay tracker: the Home 'Top four-leg parlay' card, upgraded (not duplicated).

Legs (price-free, display only):
  * Selection rule (V5.9 t80u): exactly the top four skaters by the model's anytime-goal chance
    (parlay_v58.p_anytime(lambda_game), the same number the card always showed), no one-per-game/team guard.
    Built with parlay_v58.candidates + parlay_v58.choose(per=None), i.e. the existing parlay construction.
  * Before puck drop the pick follows the model; at the first puck drop of the slate it is LOCKED for the slate date
    (session store) so it never reshuffles as the live model updates. A session that opens after puck drop reuses the
    frozen pre-game snapshot (snapshots/accuracy/DAY.json, frozen before the first start) when one exists, else it
    rebuilds from the pregame lambdas and says so.
  * Fewer than four priced candidates -> fallback: the top four of the live next-goal ranking (labelled).

Live status comes ONLY from the play-by-play the app already polls (tabs/live.py ``_v56_pbp``: the shared
live_nextgoal_v56.Poller, ~30 s live cadence, 25 s cache). This module never fetches, never schedules a refresh.

Regulation-only rules (the user's rule; some sportsbooks count overtime): a leg hits only with a goal in periods 1-3.
Shootout attempts are never goals (the parser drops them) and an overtime goal does not count. A leg without a
regulation goal is DEAD once its game reaches OT/SO or ends; the parlay is busted once any leg is dead.
"""
from __future__ import annotations

import parlay_v58 as parlay

K = 4
STORE_KEY = 'v59_parlay_track'
STARTED = ('live', 'final', 'shootout')
RULES = ('Regulation-only rules: a leg counts only with a goal in periods 1-3. Overtime goals and shootouts do not '
         'count; once a game reaches OT/SO or ends, a leg without a regulation goal is dead. Some sportsbooks count '
         'overtime goals for anytime scorers, so a book may settle differently.')
SOURCES = {
    'model': 'Top 4 by model chance (parlay construction)',
    'snapshot': 'Top 4 by model chance · frozen pre-game snapshot',
    'rebuilt': 'Top 4 by model chance · rebuilt from pregame model after puck drop',
    'fallback': 'Fallback: top 4 live next-goal targets',
}


# ------------------------------------------------------------------------------------------- leg selection
def _pregame_view(results):
    """The same results with every game treated as pregame and no goals (for a deterministic pregame candidate list)."""
    out = []
    for r in results or []:
        res = dict(r['result'], phase='pregame', players=[dict(p, goals=0) for p in r['result'].get('players') or []])
        out.append(dict(r, result=res))
    return out


def started(results):
    for r in results or []:
        if r['result'].get('phase') in STARTED:
            return True
        if str((r.get('score') or {}).get('state') or '').upper() in ('LIVE', 'CRIT', 'OFF', 'FINAL'):
            return True
    return False


def top_by_model(results, ranked_rows=None, out_ids=(), k=K):
    """Exactly the top k skaters by model chance (no correlation guard). [] when fewer than k are priced."""
    cands = parlay.candidates(_pregame_view(results), ranked_rows, out_ids, {})
    return parlay.choose(cands, k, per=None)


def top_next_goal(results, k=K, out_ids=()):
    """Fallback: top k of the live next-goal ranking across the slate (p_next, the Live Next Goal tab's order)."""
    rank = {c['pid']: c for c in parlay.candidates(_pregame_view(results), None, (), {})}
    rows = []
    for r in results or []:
        s = r['slate']
        for rec in r['result'].get('players') or []:
            if rec.get('p_next') is None or rec.get('pid') in out_ids:
                continue
            team = rec.get('team') or ''
            rows.append({'pid': rec.get('pid'), 'name': rec.get('name') or str(rec.get('pid')), 'team': team,
                         'opp': s['home'] if team == s['away'] else s['away'], 'home': team == s['home'],
                         'game': s.get('key') or f"{s['away']}@{s['home']}", 'game_id': str(s.get('game_id') or ''),
                         'start': s.get('start'), 'venue': s.get('venue') or '', 'p': parlay.p_anytime(rec.get('lam_game')) or 0.0,
                         'p_next': rec['p_next'], 'position': rec.get('pos'), 'model_rank': (rank.get(rec.get('pid')) or {}).get('model_rank') or '-',
                         'np_rank': None})
    rows.sort(key=lambda c: (-c['p_next'], c['name']))
    seen, legs = set(), []
    for c in rows:
        if c['pid'] not in seen:
            seen.add(c['pid'])
            legs.append(c)
    return legs[:k]


def _dt(v):
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def from_snapshot(entry, results, ranked_rows=None, out_ids=(), k=K):
    """Frozen pre-game accuracy-log entry -> top k by its frozen model chance, with display info from the slate."""
    if not entry or not entry.get('players'):
        return []
    fs, fz = _dt(entry.get('first_start')), _dt(entry.get('frozen_at'))
    if fs is None or fz is None or fz >= fs:        # only a snapshot frozen before the first puck drop counts
        return []
    info = {c['pid']: c for c in parlay.candidates(_pregame_view(results), ranked_rows, (), {})}
    out_ids = set(out_ids or ())
    legs = []
    for p in sorted(entry['players'], key=lambda p: (-(p[3] or 0), str(p[1]))):
        pid = p[0]
        if pid in out_ids or pid not in info:
            continue
        legs.append(dict(info[pid], p=float(p[3]), model_rank=p[4], np_rank=p[5] if p[5] is not None else info[pid].get('np_rank')))
        if len(legs) == k:
            break
    return legs if len(legs) == k else []


def snapshot_entry(day):
    """The frozen pre-game accuracy-log entry for the slate (snapshots/accuracy/DAY.json), or None. File read only."""
    try:
        import accuracy_v58 as acc
        return acc.load_entry(str(day))
    except Exception:
        return None


def _pack(legs, source, locked, now=None):
    return {'legs': legs, 'joint': parlay.joint([l['p'] for l in legs]) if legs else None, 'source': source,
            'source_label': SOURCES[source], 'locked': locked, 'locked_at': now, 'per': None, 'short': False, 'k': K}


def resolve(store, day, results, ranked_rows=None, out_ids=(), snapshot_entry=None, now=None):
    """Session lock. Pregame: follow the model. First puck drop: freeze the current pick. Late session: snapshot/rebuild."""
    cur = store.get(STORE_KEY)
    if cur and cur.get('day') != day:
        cur = None
    if cur and cur['data'].get('locked'):
        return cur['data']
    is_started = started(results)
    if cur and is_started and cur['data'].get('legs'):
        data = dict(cur['data'], locked=True, locked_at=now)
    elif not is_started:
        legs = top_by_model(results, ranked_rows, out_ids)
        data = _pack(legs, 'model', False) if legs else _pack(top_next_goal(results, K, set(out_ids or ())), 'fallback', False)
    else:
        legs = from_snapshot(snapshot_entry, results, ranked_rows, out_ids)
        src = 'snapshot'
        if not legs:
            legs, src = top_by_model(results, ranked_rows, out_ids), 'rebuilt'
        data = _pack(legs, src, True, now) if legs else _pack(top_next_goal(results, K, set(out_ids or ())), 'fallback', True, now)
    if not data['legs']:
        data['locked'] = False          # nothing to lock yet; try again on the next run
    store[STORE_KEY] = {'day': day, 'data': data}
    return data


# ------------------------------------------------------------------------------------------- live leg status
def _clock(period, secs):
    secs = int(secs or 0)
    return f'P{period} {secs // 60:02d}:{secs % 60:02d}'


def _phase(game, result=None, score=None):
    if game:
        import live_nextgoal_v56 as ng
        return ng.phase(game)
    st = str((score or {}).get('state') or '').upper()
    if st in ('OFF', 'FINAL'):
        return 'final'
    return (result or {}).get('phase') or 'pregame'


def leg_state(leg, game=None, result=None, score=None):
    """One leg vs the polled PBP game. -> {'status': hit|live|pending|dead, 'goal': 'P2 12:41 · COL 2-1'|None, 'note'}."""
    pid = leg['pid']
    team = leg.get('team') or ''
    events = sorted([e for e in (game or {}).get('events') or [] if e.get('kind') == 'goal' and e.get('ptype') != 'SO'],
                    key=lambda e: (e.get('period') or 0, e.get('secs') or 0, e.get('order') or 0))
    score_t = {}
    ot_goal = None
    for e in events:
        score_t[e.get('team')] = score_t.get(e.get('team'), 0) + 1
        try:
            shooter = int(e.get('shooter'))
        except (TypeError, ValueError):
            continue
        if shooter != pid:
            continue
        reg = e.get('ptype', 'REG') == 'REG' and int(e.get('period') or 0) <= 3
        if reg:
            mine = score_t.get(team, 0)
            theirs = sum(v for t, v in score_t.items() if t != team)
            return {'status': 'hit', 'goal': f'{_clock(e.get("period"), e.get("secs"))} · {team} {mine}-{theirs}',
                    'note': 'Regulation goal'}
        ot_goal = ot_goal or e
    ph = _phase(game, result, score)
    in_ot = bool(game) and ph == 'live' and ((game.get('ptype') == 'OT') or int(game.get('period') or 0) > 3)
    if ot_goal is not None:
        return {'status': 'dead', 'goal': None, 'note': 'OT goal does not count (regulation only)'}
    if ph == 'shootout' or in_ot:
        return {'status': 'dead', 'goal': None, 'note': 'No regulation goal · game went to ' + ('SO' if ph == 'shootout' else 'OT')}
    if ph == 'final':
        if not game:
            return {'status': 'pending', 'goal': None, 'note': 'Final · waiting for play-by-play'}
        return {'status': 'dead', 'goal': None, 'note': 'Final · no regulation goal'}
    if ph == 'live':
        return {'status': 'live', 'goal': None, 'note': 'In progress'}
    return {'status': 'pending', 'goal': None, 'note': 'Not started'}


def states(data, pbp, results):
    """{pid: leg_state} for the locked legs, from the shared polled PBP."""
    by_gid = {str(r['slate'].get('game_id') or ''): r for r in results or []}
    out = {}
    for l in (data or {}).get('legs') or []:
        gid = str(l.get('game_id') or '')
        r = by_gid.get(gid) or {}
        out[l['pid']] = leg_state(l, (pbp or {}).get(gid) or (pbp or {}).get(int(gid) if gid.isdigit() else gid), r.get('result'), r.get('score'))
    return out


def summary(st_by_pid, n=None):
    vals = [s['status'] for s in (st_by_pid or {}).values()]
    n = n if n is not None else len(vals)
    hit, dead, live = vals.count('hit'), vals.count('dead'), vals.count('live')
    pending = n - hit - dead
    overall = 'busted' if dead else 'won' if n and hit == n else 'live' if (live or hit) else 'pending'
    return {'n': n, 'hit': hit, 'dead': dead, 'pending': pending, 'live': live, 'overall': overall,
            'text': f'{hit} of {n} legs hit'}


def phase_signature(pbp):
    """Changes when a game starts, enters OT/SO or ends (used by the EXISTING scorer-watch fragment to rerun Home)."""
    out = []
    for gid, g in sorted((pbp or {}).items(), key=lambda kv: str(kv[0])):
        if isinstance(g, dict):
            out.append((str(gid), str(g.get('state') or ''), str(g.get('ptype') or ''), int(g.get('period') or 0) > 3))
    return tuple(out)


# ------------------------------------------------------------------------------------------- presentation
ICON = {'hit': ('✓', 'Scored'), 'dead': ('✕', 'Dead'), 'live': ('●', 'Live'), 'pending': ('○', 'Pending')}
BANNER = {'won': ('🏆', 'All 4 legs hit'), 'busted': ('✕', 'Parlay busted'), 'live': ('●', 'Live'), 'pending': ('○', 'Pending')}


def section_html(data, st_by_pid, chips_by_pid, empty_reason='', scored=None):
    import position_badge_v59 as pb
    import scorers_tonight_v58 as sctn
    import v55_ui as v5
    import venue_v58 as vn
    esc = v5.esc
    legs = (data or {}).get('legs') or []
    if not legs:
        return (f'<section class="sec npp npt"><div class="sh"><h3>Top four-leg parlay</h3><p>Live tracker · top four by model chance</p></div>'
                f'<div class="npp-empty"><b>No parlay pick yet</b><p>{esc(empty_reason or "Needs this slate’s rankings: legs are the top four skaters by model chance.")}</p></div></section>')
    sm = summary(st_by_pid, len(legs))
    ov = sm['overall']
    bic, btxt = BANNER[ov]
    lock = ('🔒 Locked at first puck drop' if data.get('locked') else 'Follows the model until first puck drop, then locks')
    cards = []
    for i, l in enumerate(legs, 1):
        s = (st_by_pid or {}).get(l['pid']) or {'status': 'pending', 'goal': None, 'note': 'Not started'}
        sic, stxt = ICON[s['status']]
        where = f'{esc(l["team"])} {"vs" if l.get("home") else "@"} {esc(l["opp"])}'
        when = v5.et_time(l.get('start')) if l.get('start') else ''
        goal = (f'<div class="npt-goal" title="Goal time (elapsed in period) and the score right after it">🚨 {esc(s["goal"])}</div>' if s.get('goal')
                else f'<div class="npt-note">{esc(s.get("note"), "")}</div>')
        cards.append(f'''<article class="npp-leg npt-leg s-{s['status']}" style="{v5.team_vars(l['team'])}"><div class="npp-top"><span class="npp-n">{i}</span>{v5.logo(l['team'], 'npp-lg')}
<div class="npp-id"><b class="npp-name"><span class="npt-nm">{esc(l['name'])}</span>{pb.goalie_badge(pb.position_of(l))}{sctn.badge_for(scored, l.get('pid'), l.get('name'))}</b><small>{where}{' · ' + esc(when) if when else ''}</small>{vn.tag(l.get('venue'))}</div>
<span class="npp-st npt-st s-{s['status']}" title="{esc(RULES)}">{sic} {stxt}</span></div>{goal}
<div class="npp-p"><span class="lbl">Model chance</span><strong>{l['p'] * 100:.1f}%</strong></div>
<div class="cats">{v5.chips(chips_by_pid.get(l['pid'], []))}</div></article>''')
    counts = f'<span class="npt-c c-hit">{sm["hit"]} hit</span><span class="npt-c c-pend">{sm["pending"]} pending</span><span class="npt-c c-dead">{sm["dead"]} dead</span>'
    extra = ''
    if ov == 'won':
        extra = '<div class="npt-win" role="status"><b>All four legs hit</b><span>Every leg scored in regulation tonight.</span></div>'
    elif ov == 'busted':
        dead = [l for l in legs if ((st_by_pid or {}).get(l['pid']) or {}).get('status') == 'dead']
        extra = ('<div class="npt-bust" role="status"><b>Parlay busted</b><span>'
                 + esc(' · '.join(f'{l["name"]}: {(st_by_pid[l["pid"]] or {}).get("note", "")}' for l in dead)) + '</span></div>')
    note = (f'Combined model chance = product of the four leg chances (assumes independence; the top four may share a game, '
            f'so it can overstate). Model estimates, uncalibrated - not betting advice.')
    return (f'<section class="sec npp npt pt-{ov}"><div class="sh"><h3>Top four-leg parlay <span class="npp-ov npt-ov s-{ov}">{bic} {btxt}</span></h3>'
            f'<p>Live tracker · <span class="npt-src">{esc(data.get("source_label"))}</span> · {esc(lock)} '
            f'<span class="npt-rule" title="{esc(RULES)}" aria-label="{esc(RULES)}">ⓘ Regulation only</span></p></div>'
            f'<div class="npp-sum npt-sum"><strong class="npt-hit">{sm["text"]}</strong><span class="npt-cs">{counts}</span>'
            f'<span class="npt-j"><span class="lbl">Combined model chance</span> <b>{data["joint"] * 100:.1f}%</b></span>'
            f'<small>{esc(note)}</small></div>{extra}<div class="npp-grid">{"".join(cards)}</div>'
            f'<p class="npp-rg">{esc(parlay.RG_LINE)}</p></section>')
