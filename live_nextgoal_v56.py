"""V5.6 live next-goal model (pure functions, no Streamlit, no network at import).

Inputs
  * NHL official play-by-play ``api-web.nhle.com/v1/gamecenter/{id}/play-by-play`` (parsed by ``parse_pbp``).
  * Season priors per skater from the app's existing rankings rows (``Prior GP``, ``Goals/G Prior``,
    ``Shots/G L10``) -- the same pre-slate numbers Research shows. Nothing is invented: a skater with no
    row falls back to the positional league prior and is labelled ``prior: league``.

Per skater i on team T (all rates per game-minute):
  shot rate     s_i = w * (in-game SOG_i / elapsed) + (1 - w) * (season SOG/GP shrunk to a positional mean) / 60,
                w = elapsed / (elapsed + PACE_TAU)                        (pace blend, moves to in-game with time)
  conversion    c_i = (1 - v) * shrunk sh% + v * mean in-game xG_i,       v = n_i / (n_i + XG_TAU), capped at XG_VMAX
                shrunk sh% = (G + K * LEAGUE_SH) / (SOG + K),             K = 50   (empirical-Bayes style)
  goal rate     r_i = s_i * c_i * form_mult_i                            (form_mult optional, bounded 0.9..1.1; Form is never a probability)
Team rate       L_T = sum_i r_i * situation multiplier (PP / SH / empty net, from the latest situationCode)
Horizon         R = remaining regulation minutes (or remaining OT minutes in OT); shootout excluded (no 'next goal').
Competing risk  P(any further goal) = 1 - exp(-(L_A + L_H) * R);  P(T scores next) = P(any) * L_T / (L_A + L_H)
Player          P(i scores next) = P(T) * r_i / sum_{j in T} r_j;     sum over everyone <= 1, the rest is 'no further goal'.
Per-game lambda (for EdgeLab-style edge flags): lambda_i = r_i * 60 pregame (r_i from the prior alone) -> p = 1 - exp(-lambda_i).

Heuristic priors (documented, not fitted): see the constants below. Probabilities are model estimates, uncalibrated.
"""
from __future__ import annotations

import math
import random
import time

# ---------------------------------------------------------------- constants (documented priors)
LEAGUE_SH = 0.10          # league shooting % on shots on goal (NHL ~9.5-10.5% in recent seasons)
K_SHRINK = 50             # pseudo-shots toward LEAGUE_SH
POS_SHOTS_PG = {'F': 2.0, 'D': 1.4}   # positional mean SOG per game for skaters
M_SHOTS = 5               # pseudo-games toward the positional mean
PACE_TAU = 30.0           # minutes; w = elapsed / (elapsed + PACE_TAU)
XG_TAU = 5.0              # in-game shots; v = n / (n + XG_TAU)
XG_VMAX = 0.5             # in-game xG never more than half the conversion estimate
FORM_MIN, FORM_MAX = 0.9, 1.1
REG_MINUTES = 60.0
OT_MINUTES = 5.0          # regular-season 3-on-3 OT
OT_RATE_MULT = 1.35       # 3-on-3 scoring pace vs 5-on-5 (heuristic)
SITUATION_MULT = {'PP': 1.6, 'SH': 0.55, 'EN_FOR': 1.25, 'EN_AGAINST': 2.6}
# xG logistic: logit = B0 + B_DIST * distance_ft + B_ANGLE * angle_deg + shot type + strength
B0, B_DIST, B_ANGLE = -0.35, -0.055, -0.012
SHOT_TYPE_ADJ = {'tip-in': 0.35, 'deflected': 0.35, 'bat': 0.2, 'snap': 0.05, 'wrist': 0.0, 'slap': -0.05,
                 'backhand': -0.1, 'poke': 0.0, 'between-legs': 0.1, 'cradle': 0.1, 'wrap-around': -0.35}
STRENGTH_ADJ = {'PP': 0.25, 'SH': -0.15, 'EV': 0.0, 'EN': 2.5}
XG_MIN, XG_MAX, XG_MAX_EN = 0.01, 0.6, 0.95
XG_DEFAULT = 0.075        # shot with missing coordinates
NET_X = 89.0
SHOT_TYPES = {'shot-on-goal': 'sog', 'goal': 'goal', 'missed-shot': 'miss', 'blocked-shot': 'block'}
LIVE_STATES = ('LIVE', 'CRIT')
FINAL_STATES = ('OFF', 'FINAL', 'OVER')
PRE_STATES = ('FUT', 'PRE')


def _f(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _secs(mmss):
    try:
        m, s = str(mmss).split(':')
        return int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def pos_group(pos):
    return 'D' if str(pos or '').upper().startswith('D') else 'F'


# ---------------------------------------------------------------- xG
def strength_for(situation_code, shooter_is_home):
    """'abcd' = away goalie, away skaters, home skaters, home goalie -> EV / PP / SH / EN (opponent net empty)."""
    s = str(situation_code or '')
    if len(s) != 4 or not s.isdigit():
        return 'EV'
    ag, ask, hsk, hg = (int(c) for c in s)
    own, opp, opp_goalie = (hsk, ask, ag) if shooter_is_home else (ask, hsk, hg)
    if opp_goalie == 0:
        return 'EN'
    if own > opp:
        return 'PP'
    if own < opp:
        return 'SH'
    return 'EV'


def net_x_for(shooter_is_home, home_defending_side, x=None, zone=None):
    """Attacked net's x. Home defends 'right' (x=+89) -> home attacks x=-89. Falls back to the offensive-zone sign."""
    side = str(home_defending_side or '').lower()
    if side in ('left', 'right'):
        home_net = NET_X if side == 'right' else -NET_X
        return -home_net if shooter_is_home else home_net
    if x is not None and zone == 'O' and x != 0:
        return math.copysign(NET_X, x)
    return None


def shot_xg(x, y, net_x, shot_type=None, strength='EV'):
    """Logistic xG on distance and angle with shot-type and strength adjustments, clipped. Heuristic priors."""
    if strength == 'EN' and (x is None or y is None or net_x is None):
        return 0.8
    if x is None or y is None or net_x is None:
        return XG_DEFAULT
    x, y = _f(x), _f(y)
    to_line = abs(net_x) - x * math.copysign(1, net_x)       # >0 in front of the goal line
    dist = math.hypot(to_line, y)
    angle = math.degrees(math.atan2(abs(y), to_line))        # 0 = straight on, >90 = behind the net
    logit = B0 + B_DIST * dist + B_ANGLE * angle + SHOT_TYPE_ADJ.get(str(shot_type or '').lower(), 0.0) + STRENGTH_ADJ.get(strength, 0.0)
    p = 1 / (1 + math.exp(-logit))
    return round(min(XG_MAX_EN if strength == 'EN' else XG_MAX, max(XG_MIN, p)), 4)


# ---------------------------------------------------------------- PBP parsing
def _name(spot):
    first = ((spot.get('firstName') or {}).get('default') or '').strip()
    last = ((spot.get('lastName') or {}).get('default') or '').strip()
    return (first + ' ' + last).strip() or str(spot.get('playerId'))


def parse_pbp(payload):
    """Official PBP JSON -> compact game dict. Shootout attempts are dropped; events keyed by eventId (deduped)."""
    if not isinstance(payload, dict):
        raise ValueError('play-by-play payload is not an object')
    away, home = payload.get('awayTeam') or {}, payload.get('homeTeam') or {}
    ids = {away.get('id'): away.get('abbrev'), home.get('id'): home.get('abbrev')}
    home_id = home.get('id')
    roster = {}
    for spot in payload.get('rosterSpots') or []:
        pid = spot.get('playerId')
        if pid is None:
            continue
        roster[int(pid)] = {'name': _name(spot), 'team': ids.get(spot.get('teamId'), ''), 'pos': spot.get('positionCode', ''),
                            'number': spot.get('sweaterNumber'), 'headshot': spot.get('headshot', '')}
    events, last_sit = {}, ''
    for p in payload.get('plays') or []:
        pd_ = p.get('periodDescriptor') or {}
        ptype = pd_.get('periodType', 'REG')
        if p.get('situationCode') and ptype != 'SO':
            last_sit = p['situationCode']
        kind = SHOT_TYPES.get(p.get('typeDescKey'))
        if not kind or ptype == 'SO':
            continue
        eid = p.get('eventId')
        if eid is None or eid in events:
            continue
        d = p.get('details') or {}
        shooter = d.get('scoringPlayerId') if kind == 'goal' else d.get('shootingPlayerId')
        if shooter is None:
            continue
        shooter = int(shooter)
        team = (roster.get(shooter) or {}).get('team') or ids.get(d.get('eventOwnerTeamId'), '')
        is_home = team == home.get('abbrev')
        strength = strength_for(p.get('situationCode'), is_home)
        x, y = d.get('xCoord'), d.get('yCoord')
        nx = net_x_for(is_home, p.get('homeTeamDefendingSide'), x, d.get('zoneCode'))
        events[eid] = {'eid': eid, 'kind': kind, 'period': pd_.get('number', 0), 'ptype': ptype,
                       'secs': (_secs(p.get('timeInPeriod')) or 0), 'shooter': shooter, 'team': team,
                       'goalie': d.get('goalieInNetId'), 'strength': strength, 'shot_type': d.get('shotType'),
                       'x': x, 'y': y, 'xg': shot_xg(x, y, nx, d.get('shotType'), strength),
                       # audit PP fix: the same shot without the PP logit bonus (used only with MODEL_PP_COHERENT)
                       'xg_ev': shot_xg(x, y, nx, d.get('shotType'), 'EV') if strength == 'PP' else None,
                       'order': p.get('sortOrder', 0), 'sit': str(p.get('situationCode') or '')}
    clock = payload.get('clock') or {}
    pdesc = payload.get('periodDescriptor') or {}
    return {'game_id': payload.get('id'), 'date': payload.get('gameDate'), 'start': payload.get('startTimeUTC'),
            'state': payload.get('gameState', ''), 'away': away.get('abbrev', ''), 'home': home.get('abbrev', ''),
            'away_score': away.get('score'), 'home_score': home.get('score'), 'away_sog': away.get('sog'), 'home_sog': home.get('sog'),
            'period': pdesc.get('number', 0), 'ptype': pdesc.get('periodType', 'REG'),
            'secs_remaining': clock.get('secondsRemaining'), 'intermission': bool(clock.get('inIntermission')),
            'situation': last_sit, 'roster': roster,
            'events': sorted(events.values(), key=lambda e: (e['period'], e['secs'], e['order']))}


def pregame_game(game_id, away, home, start=None, state='FUT'):
    """Game dict before any play-by-play exists (or when it is unavailable): priors only."""
    return {'game_id': game_id, 'date': None, 'start': start, 'state': state, 'away': away, 'home': home,
            'away_score': None, 'home_score': None, 'away_sog': None, 'home_sog': None, 'period': 0, 'ptype': 'REG',
            'secs_remaining': None, 'intermission': False, 'situation': '', 'roster': {}, 'events': []}


def merge_events(known, new_events):
    """Dedupe by eventId. Returns (merged dict eid->event, number of genuinely new events)."""
    merged, added = dict(known or {}), 0
    for e in new_events or []:
        if e.get('eid') is None:
            continue
        if e['eid'] not in merged:
            added += 1
        merged[e['eid']] = e
    return merged, added


def truncate(game, upto):
    """Replay helper: the game as it stood after its first ``upto`` shot events (clock inferred from the last one).
    Strength comes from the last replayed event's own situationCode (V5.9); unknown -> '' (neutral, no PP/SH/EN multiplier)."""
    evs = game['events'][:max(0, upto)]
    g = dict(game, events=evs)
    if upto >= len(game['events']):
        return g
    last = evs[-1] if evs else {'period': 1, 'secs': 0, 'ptype': 'REG'}
    goals = [e for e in evs if e['kind'] == 'goal']
    g.update(state='LIVE', period=last['period'], ptype=last['ptype'], intermission=False,
             secs_remaining=max(0, (OT_MINUTES * 60 if last['ptype'] == 'OT' else 1200) - last['secs']),
             away_score=sum(e['team'] == game['away'] for e in goals), home_score=sum(e['team'] == game['home'] for e in goals),
             away_sog=sum(e['team'] == game['away'] and e['kind'] in ('sog', 'goal') for e in evs),
             home_sog=sum(e['team'] == game['home'] and e['kind'] in ('sog', 'goal') for e in evs), situation=last.get('sit') or '')
    return g


# ---------------------------------------------------------------- clock
def phase(game):
    st = str(game.get('state', '')).upper()
    if st in FINAL_STATES:
        return 'final'
    if st in PRE_STATES or not st:
        return 'pregame'
    if game.get('ptype') == 'SO':
        return 'shootout'
    return 'live'


def elapsed_remaining(game):
    """(elapsed game-minutes, remaining horizon minutes). Shootout -> remaining 0 (excluded)."""
    ph = phase(game)
    if ph == 'pregame':
        return 0.0, REG_MINUTES
    if ph in ('final', 'shootout'):
        return REG_MINUTES, 0.0
    period, ptype = int(game.get('period') or 1), game.get('ptype', 'REG')
    rem = game.get('secs_remaining')
    rem = _f(rem, 1200.0) / 60.0
    if ptype == 'OT' or period > 3:
        return REG_MINUTES + max(0.0, OT_MINUTES - rem), max(0.0, rem)
    return (period - 1) * 20 + (20 - rem), max(0.0, (3 - period) * 20 + rem)


# ---------------------------------------------------------------- priors
def shrunk_sh(goals, sog, k=K_SHRINK, league=LEAGUE_SH):
    goals, sog = max(0.0, _f(goals)), max(0.0, _f(sog))
    return (goals + k * league) / (sog + k)


def prior_shots_pg(sog, gp, pos):
    mean = POS_SHOTS_PG[pos_group(pos)]
    return (max(0.0, _f(sog)) + M_SHOTS * mean) / (max(0.0, _f(gp)) + M_SHOTS)


def priors_from_rankings(rows):
    """rankings rows (dicts) -> {player_id: prior}. Season SOG = Shots/G L10 x min(GP,10) scaled to GP (exact when GP<=10)."""
    out = {}
    for r in rows or []:
        try:
            pid = int(float(r.get('Player ID')))
        except (TypeError, ValueError):
            continue
        gp = max(0.0, _f(r.get('Prior GP')))
        g = round(_f(r.get('Goals/G Prior')) * gp)
        sog = _f(r.get('Shots/G L10')) * gp
        form = r.get('Form %', r.get('Form Index'))
        out[pid] = {'name': r.get('Player', ''), 'team': str(r.get('Team', '')).upper(), 'pos': r.get('Position', ''),
                    'gp': gp, 'goals': g, 'sog': sog, 'form': _f(form, None) if form is not None else None, 'source': 'season'}
    return out


def form_mult(form_pct):
    """Optional bounded multiplier from Form % (0..100): 0.9 at 0, 1.1 at 100. Never a probability."""
    if form_pct is None:
        return 1.0
    f = min(100.0, max(0.0, _f(form_pct)))
    return FORM_MIN + (FORM_MAX - FORM_MIN) * f / 100.0


def pace_weight(elapsed):
    e = max(0.0, _f(elapsed))
    return e / (e + PACE_TAU)


def situation_mult(situation_code, team_is_home):
    s = str(situation_code or '')
    if len(s) != 4 or not s.isdigit():
        return 1.0
    ag, ask, hsk, hg = (int(c) for c in s)
    own_g, opp_g = (hg, ag) if team_is_home else (ag, hg)
    m = 1.0
    st = strength_for(s, team_is_home)
    if st == 'PP':
        m *= SITUATION_MULT['PP']
    elif st == 'SH':
        m *= SITUATION_MULT['SH']
    if opp_g == 0:
        m *= SITUATION_MULT['EN_AGAINST']
    if own_g == 0:
        m *= SITUATION_MULT['EN_FOR']
    return m


# ---------------------------------------------------------------- model
def model(game, priors=None, use_form=False, lineup=None, situ=None):
    """Next-goal probabilities for one game. ``lineup``: optional {pid: {...}} restricting to dressed skaters.

    ``situ``: optional V5.8 situational layer (``situational_v58.Situ``). None = the V5.6 model exactly. With it, each
    skater's pregame lambda and live per-minute rate are scaled by the bounded ratio it returns (PP split, opposing
    goalie, TOI deployment); the per-player breakdown is kept in ``rec['situ']``. Ratio 1.0 (no data) = old numbers.
    Audit PP fix: with ``situ.pp_coherent`` (feature_flags_v58.MODEL_PP_COHERENT) the live PP is priced ONCE, by the
    team multiplier SITUATION_MULT['PP']: the player's PP split becomes a neutral share ratio and PP shots count at
    their EV xG. Pregame (and situ None / flag off) is unchanged."""
    priors = priors or {}
    coherent = bool(getattr(situ, 'pp_coherent', False))
    ph = phase(game)
    elapsed, remaining = elapsed_remaining(game)
    w = pace_weight(elapsed)
    teams = (game.get('away', ''), game.get('home', ''))
    roster = game.get('roster') or {}
    players = {}

    def ensure(pid, team=None):
        if pid in players:
            return players[pid]
        pr = priors.get(pid) or {}
        ro = roster.get(pid) or {}
        pos = ro.get('pos') or pr.get('pos') or 'F'
        if str(pos).upper() == 'G':
            return None
        rec = {'pid': pid, 'name': ro.get('name') or pr.get('name') or str(pid), 'team': ro.get('team') or pr.get('team') or team or '',
               'pos': pos, 'number': ro.get('number'), 'headshot': ro.get('headshot', ''), 'prior_source': pr.get('source', 'league'),
               'gp': pr.get('gp', 0.0), 'season_g': pr.get('goals', 0), 'season_sog': pr.get('sog', 0.0), 'form': pr.get('form'),
               'sog': 0, 'att': 0, 'goals': 0, 'xg': 0.0, 'xg_sog': 0.0}
        players[pid] = rec
        return rec

    # dressed skaters (roster spots) for both teams, else everyone with a prior on either team
    pool = lineup if lineup is not None else {pid: r for pid, r in roster.items() if str(r.get('pos', '')).upper() != 'G'}
    pool_kind = 'lineup' if lineup is not None else 'roster'
    if not pool:
        pool, pool_kind = {pid: p for pid, p in priors.items() if p.get('team') in teams}, 'priors'
    for pid, r in pool.items():
        if (r.get('team') or (priors.get(pid) or {}).get('team')) in teams:
            ensure(pid, r.get('team'))
    for e in game.get('events') or []:
        rec = ensure(e['shooter'], e['team'])
        if rec is None:
            continue
        rec['att'] += 1
        # audit PP fix (MODEL_PP_COHERENT, situational layer only): PP shots count at their EV xG, since the team's
        # PP is already priced by SITUATION_MULT['PP'] - the +0.25 logit PP bonus is not stacked on top of it.
        xg = e['xg_ev'] if coherent and e.get('xg_ev') is not None else e['xg']
        rec['xg'] += xg
        if e['kind'] in ('sog', 'goal'):
            rec['sog'] += 1
            rec['xg_sog'] += xg
        if e['kind'] == 'goal':
            rec['goals'] += 1

    team_rate = {t: 0.0 for t in teams}
    for rec in players.values():
        if rec['team'] not in team_rate:
            continue
        prior_pg = prior_shots_pg(rec['season_sog'], rec['gp'], rec['pos'])
        in_rate = rec['sog'] / elapsed if elapsed > 0 else 0.0
        s = w * in_rate + (1 - w) * prior_pg / 60.0
        sh = shrunk_sh(rec['season_g'], rec['season_sog'])
        v = min(XG_VMAX, rec['sog'] / (rec['sog'] + XG_TAU)) if rec['sog'] else 0.0
        conv = (1 - v) * sh + v * (rec['xg_sog'] / rec['sog'] if rec['sog'] else 0.0)
        fm = form_mult(rec['form']) if use_form else 1.0
        rate = s * conv * fm
        lam_game = prior_pg * sh * fm
        if situ is not None:
            bd = situ(rec, rec['team'], teams[0] if rec['team'] == teams[1] else teams[1], game, prior_pg, lam_game, ph)
            rec['situ'] = bd
            if bd and bd.get('ratio', 1.0) != 1.0:
                rate, lam_game = rate * bd['ratio'], bd['final']
        rec.update(prior_pg=round(prior_pg, 3), shot_rate=s, shrunk_sh=sh, conv=conv, rate=rate, lam_game=round(lam_game, 4))
        team_rate[rec['team']] += rate
    if coherent and ph == 'live':
        # audit PP fix: the live PP share only re-splits a team's rate between its players; the team total is the one
        # without the share (so PP scoring is added once, by SITUATION_MULT['PP'] below)
        neutral = {t: 0.0 for t in teams}
        for rec in players.values():
            if rec['team'] in neutral and 'rate' in rec:
                bd = rec.get('situ') or {}
                r, rn = bd.get('ratio', 1.0), bd.get('ratio_neutral')
                neutral[rec['team']] += rec['rate'] / r * rn if rn is not None and r > 0 else rec['rate']
        for t in teams:
            f = neutral[t] / team_rate[t] if team_rate[t] > 0 else 1.0
            if f != 1.0:
                for rec in players.values():
                    if rec['team'] == t and 'rate' in rec:
                        rec['rate'] *= f
                team_rate[t] = neutral[t]

    mult = {t: situation_mult(game.get('situation'), t == teams[1]) if ph == 'live' else 1.0 for t in teams}
    if ph == 'live' and (game.get('ptype') == 'OT' or int(game.get('period') or 0) > 3):
        mult = {t: m * OT_RATE_MULT for t, m in mult.items()}
    lam = {t: team_rate[t] * mult[t] for t in teams}
    total = sum(lam.values())
    p_any = 1 - math.exp(-total * remaining) if total > 0 and remaining > 0 else 0.0
    p_team = {t: (p_any * lam[t] / total if total > 0 else 0.0) for t in teams}
    out = []
    for rec in players.values():
        t = rec['team']
        if t not in team_rate:
            continue
        share = rec['rate'] / team_rate[t] if team_rate[t] > 0 else 0.0
        rec['p_next'] = p_team[t] * share
        out.append(rec)
    out.sort(key=lambda r: (-r['p_next'], -r['sog'], r['name']))
    return {'phase': ph, 'elapsed': round(elapsed, 2), 'remaining': round(remaining, 2), 'pace_weight': round(w, 3),
            'team_rate': team_rate, 'team_mult': mult, 'p_team': p_team, 'p_any': p_any, 'p_none': 1 - p_any,
            'pool': pool_kind, 'players': out, 'game': {k: game.get(k) for k in ('game_id', 'away', 'home', 'away_score', 'home_score',
                                                               'away_sog', 'home_sog', 'period', 'ptype', 'state', 'situation', 'intermission')}}


def rerank(players, previous_ranks=None):
    """Assign rank (1 = most likely next scorer) and delta vs the previous ranks (+ = moved up, None = new; no history -> 0)."""
    prev = previous_ranks or {}
    ranks = {}
    for i, p in enumerate(players, 1):
        p['rank'] = i
        old = prev.get(p['pid'])
        p['delta'] = 0 if previous_ranks is None else (old - i) if old is not None else None
        ranks[p['pid']] = i
    return ranks


def arrow(delta):
    if delta is None:
        return 'new'
    return 'up' if delta > 0 else 'down' if delta < 0 else 'same'


def per_game_lambda(rec):
    """Pregame per-game goal expectation for one skater (prior shots/game x shrunk sh%)."""
    return max(0.0, _f(rec.get('lam_game')))


def p_anytime(lam):
    return 1 - math.exp(-max(0.0, _f(lam)))


# ---------------------------------------------------------------- polling
def cadence(phase_name, minutes_to_start=None):
    """Seconds until the next poll: ~30 s live, slower pregame, None = stop (final)."""
    if phase_name == 'final':
        return None
    if phase_name in ('live', 'shootout'):
        return 30
    if minutes_to_start is not None and minutes_to_start <= 30:
        return 120
    return 600


def backoff(attempt, base=30, cap=600, rand=random.random):
    """Exponential backoff with full-range jitter in [50%, 100%] of min(cap, base * 2^attempt)."""
    d = min(cap, base * (2 ** max(0, attempt)))
    return d * (0.5 + 0.5 * rand())


class Poller:
    """One game's poller: keeps the last good parsed state, dedupes events, backs off on failure.

    ``fetch(game_id)`` returns the raw PBP dict or raises. Clock and jitter are injectable for tests."""

    def __init__(self, game_id, fetch, clock=time.time, rand=random.random):
        self.game_id, self.fetch, self.clock, self.rand = game_id, fetch, clock, rand
        self.last_good, self.events, self.failures, self.next_due = None, {}, 0, 0.0
        self.last_error, self.updated_at, self.new_events = None, None, 0

    def due(self):
        if self.last_good is not None and phase(self.last_good) == 'final':
            return False
        return self.clock() >= self.next_due

    def poll(self, force=False):
        if not force and not self.due():
            return self.last_good
        try:
            game = parse_pbp(self.fetch(self.game_id))
        except Exception as exc:  # network / HTTP / JSON: keep the last good state
            self.failures += 1
            self.last_error = f'{type(exc).__name__}: {exc}'
            self.next_due = self.clock() + backoff(self.failures - 1, rand=self.rand)
            return self.last_good
        self.events, self.new_events = merge_events(self.events, game['events'])
        game['events'] = sorted(self.events.values(), key=lambda e: (e['period'], e['secs'], e.get('order', 0)))
        self.last_good, self.failures, self.last_error, self.updated_at = game, 0, None, self.clock()
        c = cadence(phase(game))
        self.next_due = float('inf') if c is None else self.clock() + c
        return game


# ---------------------------------------------------------------- fixture trimming (DEMO replay < 100 KB)
def trim_payload(payload):
    """Keep only what parse_pbp needs from a real PBP payload (used to build the DEMO fixture)."""
    keep_types = set(SHOT_TYPES) | {'period-start', 'period-end', 'game-end', 'penalty'}
    plays = []
    for p in payload.get('plays') or []:
        if p.get('typeDescKey') not in keep_types:
            continue
        d = p.get('details') or {}
        dk = {k: d[k] for k in ('xCoord', 'yCoord', 'zoneCode', 'shotType', 'shootingPlayerId', 'scoringPlayerId',
                                'goalieInNetId', 'eventOwnerTeamId') if k in d}
        plays.append({k: p[k] for k in ('eventId', 'periodDescriptor', 'timeInPeriod', 'situationCode', 'homeTeamDefendingSide',
                                        'typeDescKey', 'sortOrder') if k in p} | {'details': dk})
    team = lambda t: {k: t.get(k) for k in ('id', 'abbrev', 'score', 'sog')}
    spots = [{k: s.get(k) for k in ('teamId', 'playerId', 'firstName', 'lastName', 'sweaterNumber', 'positionCode', 'headshot')}
             for s in payload.get('rosterSpots') or []]
    return {'id': payload.get('id'), 'gameDate': payload.get('gameDate'), 'startTimeUTC': payload.get('startTimeUTC'),
            'gameState': payload.get('gameState'), 'periodDescriptor': payload.get('periodDescriptor'), 'clock': payload.get('clock'),
            'awayTeam': team(payload.get('awayTeam') or {}), 'homeTeam': team(payload.get('homeTeam') or {}),
            'plays': plays, 'rosterSpots': spots, '_source': 'api-web.nhle.com/v1/gamecenter/{id}/play-by-play (trimmed)'}
