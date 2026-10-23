"""V5.8 Top Four-Leg Parlay (Home): the four anytime-goal picks with the best combined model chance.

Display only and price-free by design: no sportsbook prices, fair odds, implied probabilities or edges are computed or
shown here, and this module never calls an odds API.

Leg chance = the app's pregame next-goal model P(anytime goal) = 1 - exp(-lambda_game) (live_nextgoal_v56.p_anytime;
lambda_game includes the V5.8 situational layer when MODEL_SITUATIONAL is on),
an uncalibrated model estimate. Combined model chance = product of the four leg chances, i.e. it ASSUMES the legs are
independent. Correlation guard: by default at most one leg per game (which implies at most one per team), because two
skaters in the same game are positively correlated and the product would overstate the chance.

Selection is exact: with a one-per-game (or one-per-team) partition, the product is maximised by taking the best
candidate of each group and then the top-k groups (every factor is in (0, 1]).
Excluded: players whose game is final, players already scored tonight (their leg is settled, not a pick), players in
games already under way when ``exclude_started`` (fresh build after puck drop), and players listed out (injury/scratch).

V5.8 slate fix (small slates): one leg per game -> one leg per team -> if fewer than four teams are still eligible
(e.g. a 2-game night once one game has started, or a 1-game night), the best MIN_LEGS..3-leg pick, one leg per team,
with the leg count in the title and a plain note (``data['short']``). Fewer than MIN_LEGS teams -> no pick (empty state).
"""
import math

DEFAULT_LEGS = 4
MIN_LEGS = 2          # V5.8: smallest pick shown on a tiny slate (one leg per team)
WORDS = {2: 'two', 3: 'three', 4: 'four'}
NOTE = ('Combined model chance = product of the four leg chances (assumes the legs are independent; one leg per game '
        'by default to limit correlation). Model estimates, uncalibrated - not a probability guarantee and not betting advice.')
RG_LINE = 'For entertainment and research only. Never stake more than you can afford to lose. 21+ · Problem gambling? Call 1-800-GAMBLER.'


def p_anytime(lam):
    try:
        lam = float(lam)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lam) or lam <= 0:
        return None
    return 1 - math.exp(-lam)


def joint(ps):
    out = 1.0
    for p in ps:
        out *= p
    return out


def candidates(results, ranked_rows=None, out_ids=(), scored=None, exclude_started=False):
    """lstate.slate_results -> candidate legs (pregame model chance for everyone, live next-goal share as context)."""
    rank = {}
    for r in ranked_rows or []:
        try:
            rank[int(float(r.get('Player ID')))] = r
        except (TypeError, ValueError):
            continue
    out_ids, scored = set(out_ids or ()), scored or {}
    cands = []
    for r in results or []:
        s, res = r['slate'], r['result']
        phase = res.get('phase')
        if phase in ('final', 'shootout') or (exclude_started and phase == 'live'):
            continue
        for rec in res.get('players') or []:
            pid = rec.get('pid')
            if pid in out_ids or pid in scored or (rec.get('goals') or 0) > 0:
                continue
            p = p_anytime(rec.get('lam_game'))
            if p is None:
                continue
            team = rec.get('team') or ''
            opp = s['home'] if team == s['away'] else s['away']
            rr = rank.get(pid) or {}
            cands.append({'pid': pid, 'name': rec.get('name') or str(pid), 'team': team, 'opp': opp, 'home': team == s['home'],
                          'game': s.get('key') or f"{s['away']}@{s['home']}", 'game_id': str(s.get('game_id') or ''),
                          'start': s.get('start'), 'venue': s.get('venue') or '', 'phase': phase, 'p': p, 'p_next': rec.get('p_next') if phase == 'live' else None,
                          'np_rank': rr.get('Statistical rank'), 'form': rr.get('V3.2 Adjusted Index')})
    cands.sort(key=lambda c: (-c['p'], c['name']))
    for i, c in enumerate(cands, 1):
        c['model_rank'] = i
    return cands


def choose(cands, k=DEFAULT_LEGS, per='game'):
    """Best k legs by product of chances. per: 'game' (default), 'team', or None (no correlation guard)."""
    best = {}
    for c in sorted(cands, key=lambda c: (-c['p'], c['name'])):
        g = c[per] if per else c['pid']
        if g not in best:
            best[g] = c
    legs = sorted(best.values(), key=lambda c: (-c['p'], c['name']))[:k]
    return legs if len(legs) == k else []


def leg_status(leg, scorer_record=None, phases=None):
    """'hit' (scored tonight) / 'lost' (game final, no goal) / 'live' / 'pending'."""
    players = (scorer_record or {}).get('players') or {}
    if leg['pid'] in players or str(leg['pid']) in players:
        return 'hit'
    ph = (phases or {}).get(leg['game'], leg.get('phase'))
    if ph in ('final', 'shootout'):
        return 'lost'
    return 'live' if ph == 'live' else 'pending'


def overall(statuses):
    if any(s == 'lost' for s in statuses):
        return 'lost'
    if statuses and all(s == 'hit' for s in statuses):
        return 'hit'
    return 'live' if any(s in ('live', 'hit') for s in statuses) else 'pending'


def support(leg, picks=None, gem=None, stories=None):
    """Backing-signal chips (text, tone). picks: {pid: [labels]}; gem: {pid: {'day': [...], 'team': [...], 'arena': [...]}};
    stories: {pid: [tags]}."""
    chips = [(f'Model #{leg["model_rank"]} · {leg["p"] * 100:.0f}%', 'neon')]
    if leg.get('np_rank') is not None:
        try:
            chips.append((f'NP rank #{int(leg["np_rank"])}', 'stat'))
        except (TypeError, ValueError):
            pass
    if leg.get('p_next') is not None:
        chips.append((f'Next-goal {leg["p_next"] * 100:.0f}%', 'hot'))
    for lbl in (picks or {}).get(leg['pid'], []):
        chips.append((f'Intel: {lbl}', 'gem'))
    for tag in (stories or {}).get(leg['pid'], [])[:2]:
        chips.append((f'Storyline: {tag.title()}', 'gem'))
    g = (gem or {}).get(str(leg['pid'])) or (gem or {}).get(leg['pid']) or {}
    kinds = [k for k in ('day', 'team', 'arena') if g.get(k)]
    if kinds:
        chips.append(('Gematria match: ' + ' + '.join(kinds), 'gem'))
    return chips


def gem_index(targets):
    """home_leaders_v52.all_targets -> {player_id str: {'day', 'team', 'arena'}} (cipher labels per kind)."""
    out = {}
    for m in targets or []:
        for side in ('away_targets', 'home_targets'):
            for t in m.get(side) or []:
                if t.get('player_id'):
                    out[str(t['player_id'])] = {'day': t.get('day') or [], 'team': t.get('team_matches') or [], 'arena': t.get('arena_matches') or []}
    return out


def build(results, ranked_rows=None, out_ids=(), scored=None, k=DEFAULT_LEGS, per='game'):
    """Fresh pick. Before puck drop everything is eligible; after it only games not yet started are used."""
    started = any((r['result'].get('phase') in ('live', 'final', 'shootout')) for r in results or [])
    cands = candidates(results, ranked_rows, out_ids, scored, exclude_started=started)
    legs = choose(cands, k, per)
    if not legs and per == 'game':      # fewer than k eligible games: relax to one leg per team (labelled in the header)
        legs, per = choose(cands, k, 'team'), 'team'
    short = False
    if not legs and per == 'team':      # V5.8: fewer than k eligible teams (tiny slate): best smaller pick, clearly labelled
        teams = len({c['team'] for c in cands})
        for n in range(min(k - 1, teams), MIN_LEGS - 1, -1):
            legs = choose(cands, n, 'team')
            if legs:
                short = True
                break
    return {'legs': legs, 'joint': joint([l['p'] for l in legs]) if legs else None, 'built_after_start': started, 'per': per,
            'short': short, 'k': k}


def lock(store, day, sig, fresh_fn, results):
    """Per-slate lock: recompute while no game has started (follows rankings), freeze once the slate is under way."""
    started = any((r['result'].get('phase') in ('live', 'final', 'shootout')) for r in results or [])
    cur = store.get('parlay')
    if cur and cur.get('day') == day and (started or cur.get('sig') == sig):
        return cur['data']
    data = fresh_fn()
    store['parlay'] = {'day': day, 'sig': sig, 'data': data}
    return data


# ------------------------------------------------------------------------------------------------- presentation
STATUS = {'hit': ('✓', 'Hit'), 'lost': ('✕', 'No goal'), 'live': ('●', 'Live'), 'pending': ('○', 'Pending')}


def section_html(data, statuses, chips_by_pid, empty_reason='', scored=None):
    """Home section (st.html fragment). Price-free: chances, ranks and signals only."""
    import scorers_tonight_v58 as sctn
    import v55_ui as v5
    import venue_v58 as vn
    legs = (data or {}).get('legs') or []
    head = '<div class="sh"><h3>Top four-leg parlay {badge}</h3><p>The four anytime-goal picks with the best combined model chance · {guard}</p></div>'
    guard = {'game': 'one leg per game', 'team': 'fewer than four eligible games, so one leg per team (same-game legs are correlated)', None: 'no correlation guard'}.get((data or {}).get('per', 'game'), 'one leg per game')
    if legs and (data or {}).get('short'):   # V5.8 small slate: say plainly that this is not a four-leg pick
        n = len(legs)
        w = WORDS.get(n, str(n))
        head = (f'<div class="sh"><h3>Top {w}-leg parlay {{badge}}</h3><p>Only {n} teams still have eligible skaters on this slate, '
                f'so this is a {w}-leg pick (not four) with the best combined model chance · {{guard}}</p></div>')
        guard = 'one leg per team (same-game legs are correlated)'
    note = NOTE if len(legs) in (0, 4) else NOTE.replace('the four leg chances', f'the {WORDS.get(len(legs), len(legs))} leg chances')
    if not legs:
        body = (f'<div class="npp-empty"><b>No parlay pick yet</b><p>{v5.esc(empty_reason or "Needs this slate’s rankings and at least two teams with eligible (not finished, not scored, not ruled out) skaters.")}</p></div>')
        return f'<section class="sec npp">{head.format(badge="", guard=guard)}{body}</section>'
    ov = overall([statuses.get(l['pid'], 'pending') for l in legs])
    ic, txt = STATUS[ov]
    badge = f'<span class="npp-ov s-{ov}">{ic} {txt}</span>'
    cards = []
    for i, l in enumerate(legs, 1):
        s = statuses.get(l['pid'], 'pending')
        sic, stxt = STATUS[s]
        where = f'{v5.esc(l["team"])} {"vs" if l.get("home") else "@"} {v5.esc(l["opp"])}'
        when = v5.et_time(l.get('start')) if l.get('start') else ''
        cards.append(f'''<article class="npp-leg s-{s}" style="{v5.team_vars(l['team'])}"><div class="npp-top"><span class="npp-n">{i}</span>{v5.logo(l['team'], 'npp-lg')}
<div class="npp-id"><b class="npp-name">{v5.esc(l['name'])}{sctn.badge_for(scored, l.get('pid'), l.get('name'))}</b><small>{where}{' · ' + v5.esc(when) if when else ''}</small>{vn.tag(l.get('venue'))}</div>
<span class="npp-st s-{s}" title="Leg status">{sic} {stxt}</span></div>
<div class="npp-p"><span class="lbl">Model chance</span><strong>{l['p'] * 100:.1f}%</strong></div>
<div class="cats">{v5.chips(chips_by_pid.get(l['pid'], []))}</div></article>''')
    after = ' · built after puck drop from games not yet started' if data.get('built_after_start') else ''
    return (f'<section class="sec npp">{head.format(badge=badge, guard=guard)}'
            f'<div class="npp-sum"><span class="lbl">Combined model chance</span><strong>{data["joint"] * 100:.1f}%</strong>'
            f'<small>{v5.esc(note)}{v5.esc(after, "")}</small></div><div class="npp-grid">{"".join(cards)}</div>'
            f'<p class="npp-rg">{v5.esc(RG_LINE)}</p></section>')
