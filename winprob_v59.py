"""Null's Playbook V5.9 · favorite indicator on Tonight's Board (model estimate, not odds).

Inputs: ONLY the shared next-goal model result every surface uses (``_v56_results`` = live_state_v56.slate_results with
the situational/xG layer). No new data source; the app had no win probability anywhere before this.
* Pregame: each team's expected goals = the sum of its skaters' model ``lam_game`` (shots/g prior x shrunk shooting %
  x situational ratio: PP split, opposing listed starter, TOI deployment).
* Live (regulation): current score + remaining expected goals = team per-minute rate x situation multiplier x minutes left.
* Regulation result: two independent Poissons (Skellam difference); a regulation tie goes to OT/shootout split 50/50.
Nothing is shown for a game when a team has no model skaters / zero expected goals, when the game is final, or in
OT / shootout (the regulation model no longer applies). Display only: it never feeds rankings, picks or EdgeLab."""
import math
from html import escape

MAX_GOALS = 15
OT_SPLIT = 0.5


def _pois(lam, n=MAX_GOALS):
    p = [math.exp(-lam)]
    for k in range(1, n + 1):
        p.append(p[-1] * lam / k)
    return p


def regulation_probs(lam_a, lam_b, lead=0):
    """(P away ahead, P tie, P home ahead) after regulation; ``lead`` = away score - home score now."""
    pa, pb = _pois(lam_a), _pois(lam_b)
    win = tie = 0.0
    for i, x in enumerate(pa):
        for j, y in enumerate(pb):
            d = lead + i - j
            if d > 0:
                win += x * y
            elif d == 0:
                tie += x * y
    tot = sum(pa) * sum(pb)   # renormalise the (tiny) truncated tail
    win, tie = win / tot, tie / tot
    return win, tie, max(0.0, 1.0 - win - tie)


def win_prob(lam_a, lam_b, lead=0):
    """(P away wins, P home wins) incl. OT/SO split; they sum to 1."""
    w, t, l = regulation_probs(lam_a, lam_b, lead)
    pa = w + OT_SPLIT * t
    return pa, 1.0 - pa


def expected_goals(result):
    """{team: expected goals still to come} from the model result, or None when an input is missing."""
    g = (result or {}).get('game') or {}
    a, h = g.get('away'), g.get('home')
    ph = (result or {}).get('phase')
    if not a or not h or ph not in ('pregame', 'live'):
        return None
    if ph == 'live' and (g.get('ptype') in ('OT', 'SO') or int(g.get('period') or 0) > 3):
        return None
    if ph == 'pregame':
        lam = {a: 0.0, h: 0.0}
        n = {a: 0, h: 0}
        for p in result.get('players') or []:
            t = p.get('team')
            if t in lam and p.get('lam_game') is not None:
                lam[t] += float(p['lam_game']); n[t] += 1
        if not n[a] or not n[h]:
            return None
    else:
        rate, mult, rem = result.get('team_rate') or {}, result.get('team_mult') or {}, result.get('remaining')
        if a not in rate or h not in rate or rem is None:
            return None
        lam = {t: float(rate[t]) * float(mult.get(t, 1.0)) * float(rem) for t in (a, h)}
    if lam[a] <= 0 or lam[h] <= 0:
        return None
    return lam


def favorite(r):
    """One _v56_results row -> {team, pct, away, home, p_away, p_home, xg_away, xg_home, phase} or None."""
    res = (r or {}).get('result') or {}
    lam = expected_goals(res)
    if lam is None:
        return None
    g = res['game']; a, h = g['away'], g['home']
    lead = 0
    if res['phase'] == 'live':
        sa, sh = g.get('away_score'), g.get('home_score')
        if sa is None or sh is None:
            return None
        lead = int(sa) - int(sh)
    pa, ph = win_prob(lam[a], lam[h], lead)
    pct_a = round(pa * 100); pct_h = 100 - pct_a   # displayed pair always sums to 100
    team, pct = (a, pct_a) if pa >= ph else (h, pct_h)
    if pa == ph:
        team = h   # exact coin flip: show the home side (stated in the tooltip)
    return {'team': team, 'pct': pct, 'away': a, 'home': h, 'p_away': pct_a, 'p_home': pct_h,
            'xg_away': round(lam[a], 2), 'xg_home': round(lam[h], 2), 'phase': res['phase']}


def by_key(results, v2=False, ctx=None):
    """{slate game key: favorite dict} for games that have the inputs (others are simply absent).
    ``v2`` = feature_flags_v58.model_winprob_v2; ``ctx`` = the situational context (team GF/GA, skater TOI) or None."""
    out = {}
    for r in results or []:
        k = ((r or {}).get('slate') or {}).get('key')
        f = (favorite_v2(r, ctx) if v2 else favorite(r)) if k else None
        if f:
            out[k] = f
    return out


# ---------------------------------------------------------------- audit win% fix (MODEL_WINPROB_V2)
# League rates, NHL regular seasons 2023-24, 2024-25, 2025-26 pooled (3,936 games; api-web.nhle.com/v1/standings on the
# last regular-season day: homeGoalsFor/homeGamesPlayed, roadGoalsFor/roadGamesPlayed, otLosses, home/road
# regulation, regulation+OT and total wins). Goals include the +1 the league credits for a shootout win.
LEAGUE_HOME_GPG = 3.2073     # 12,624 home goals / 3,936 games
LEAGUE_AWAY_GPG = 2.9794     # 11,727 road goals / 3,936 games
LEAGUE_GPG = (LEAGUE_HOME_GPG + LEAGUE_AWAY_GPG) / 2   # one team, neutral ice
HOME_MULT = LEAGUE_HOME_GPG / LEAGUE_GPG               # 1.037: home ice on expected goals
AWAY_MULT = LEAGUE_AWAY_GPG / LEAGUE_GPG               # 0.963
REG_TIE_RATE = 868 / 3936    # 0.2205 of games tied after 60 minutes (otLosses: every OT/SO game has exactly one)
OT_HOME = 456 / 868          # 0.5253 of OT + shootout wins go to the home team (311 OT + 145 SO of 868)
DRESSED_F, DRESSED_D = 12, 6  # 18 dressed skaters when the roster is not out yet
TEAM_W = 0.5                 # blend: team GF/GA rate vs the (rescaled) skater-sum split
TEAM_K = 10.0                # team GF/GA shrunk to the league mean with K games
V2_NOTE = ('18 dressed skaters, team GF/GA blend, home ice ×1.037, regulation ties at the league rate (22%), '
           'OT/shootout 52.5% home (NHL 2023-26)')


def _tie_inflate():
    """Poisson under-counts regulation ties (about 16% vs the real 22%): one factor, set at league-average scoring."""
    _, t, _ = regulation_probs(LEAGUE_AWAY_GPG, LEAGUE_HOME_GPG)
    return REG_TIE_RATE / t


TIE_INFLATE = _tie_inflate()


def win_prob_v2(lam_a, lam_h, lead=0, tie_scale=1.0):
    """(P away wins, P home wins) with ties inflated to the league rate (``tie_scale`` 0..1 of the inflation: the
    remaining share of regulation live) and the real home OT/SO share. Win/loss keep their ratio; they sum to 1."""
    w, t, l = regulation_probs(lam_a, lam_h, lead)
    k = 1.0 + (TIE_INFLATE - 1.0) * max(0.0, min(1.0, tie_scale))
    t2 = min(0.9, t * k) if t > 0 else 0.0
    rest = w + l
    if rest > 0:
        w, l = w * (1 - t2) / rest, l * (1 - t2) / rest
    pa = w + (1 - OT_HOME) * t2
    return pa, 1.0 - pa


def dressed(players, pool=None, toi=None):
    """The skaters that count: all of them when the model pool is the real roster/lineup, else the top 12 F + 6 D per
    team by season EV TOI/game (situational ctx skaters), falling back to the shots/g prior when TOI is missing."""
    if pool in ('roster', 'lineup'):
        return list(players or [])
    toi = toi or {}

    def key(p):
        t = (toi.get(p.get('pid')) or toi.get(str(p.get('pid'))) or {}).get('ev_toi_pg')
        return (0 if t else 1, -(t or 0.0), -float(p.get('prior_pg') or 0.0), -float(p.get('gp') or 0.0), str(p.get('name')))
    out = []
    for team in dict.fromkeys(p.get('team') for p in players or []):
        ps = sorted((p for p in players if p.get('team') == team), key=key)
        f = [p for p in ps if str(p.get('pos') or 'F').upper()[:1] != 'D'][:DRESSED_F]
        d = [p for p in ps if str(p.get('pos') or 'F').upper()[:1] == 'D'][:DRESSED_D]
        out += f + d
    return out


def team_rates(a, h, teams):
    """(away, home) neutral-ice expected goals from team GF/GA per game (shrunk to the league mean), or None."""
    ta, th = (teams or {}).get(a) or {}, (teams or {}).get(h) or {}
    if any(t.get(k) is None for t in (ta, th) for k in ('gf_pg', 'ga_pg')):
        return None

    def shr(t, k):
        n = float(t.get('team_gp') or 0.0)
        return (float(t[k]) * n + LEAGUE_GPG * TEAM_K) / (n + TEAM_K)
    return shr(ta, 'gf_pg') * shr(th, 'ga_pg') / LEAGUE_GPG, shr(th, 'gf_pg') * shr(ta, 'ga_pg') / LEAGUE_GPG


def expected_goals_v2(result, ctx=None):
    """{'lam': {team: expected goals still to come}, 'alts': [other {team: lam} for the range], 'n': {team: skaters},
    'team_norm': bool} or None. Pregame: skater sum over the 18 dressed, rescaled so both teams together match the
    team GF/GA total, blended TEAM_W with the team GF/GA split, then home ice. Live: the model's remaining expected goals
    (in-game pace already in it) with home ice. None in OT/SO, final, or when a team has no skaters."""
    g = (result or {}).get('game') or {}
    a, h = g.get('away'), g.get('home')
    ph = (result or {}).get('phase')
    if not a or not h or ph not in ('pregame', 'live'):
        return None
    if ph == 'live' and (g.get('ptype') in ('OT', 'SO') or int(g.get('period') or 0) > 3):
        return None
    home = {a: AWAY_MULT, h: HOME_MULT}
    teams = (ctx or {}).get('teams') or {}
    if ph == 'live':
        base = expected_goals(result)
        if base is None:
            return None
        lam = {t: base[t] * home[t] for t in (a, h)}
        return {'lam': lam, 'alts': [base], 'n': None, 'team_norm': False}
    ps = dressed(result.get('players') or [], result.get('pool'), (ctx or {}).get('skaters'))
    sk = {a: 0.0, h: 0.0}
    n = {a: 0, h: 0}
    for p in ps:
        if p.get('team') in sk and p.get('lam_game') is not None:
            sk[p['team']] += float(p['lam_game']); n[p['team']] += 1
    if not n[a] or not n[h] or sk[a] <= 0 or sk[h] <= 0:
        return None
    tr = team_rates(a, h, teams)
    alts = [{t: sk[t] * home[t] for t in (a, h)}]
    if tr is None:
        lam = dict(alts[0])
    else:
        team = {a: tr[0], h: tr[1]}
        k = (team[a] + team[h]) / (sk[a] + sk[h])
        lam = {t: (TEAM_W * team[t] + (1 - TEAM_W) * k * sk[t]) * home[t] for t in (a, h)}
        alts += [{t: team[t] * home[t] for t in (a, h)}, {t: k * sk[t] * home[t] for t in (a, h)}]
    return {'lam': lam, 'alts': alts, 'n': n, 'team_norm': tr is not None}


def favorite_v2(r, ctx=None):
    """favorite() under MODEL_WINPROB_V2: same keys plus 'lo'/'hi' (range of the favourite's % over the inputs:
    skater-only, team-only, rescaled skaters), 'v2': True and 'team_norm'."""
    res = (r or {}).get('result') or {}
    e = expected_goals_v2(res, ctx)
    if e is None:
        return None
    g = res['game']; a, h = g['away'], g['home']
    lead, scale = 0, 1.0
    if res['phase'] == 'live':
        sa, sh = g.get('away_score'), g.get('home_score')
        if sa is None or sh is None:
            return None
        lead = int(sa) - int(sh)
        scale = max(0.0, min(1.0, float(res.get('remaining') or 0.0) / 60.0))
    lam = e['lam']
    pa, ph = win_prob_v2(lam[a], lam[h], lead, scale)
    pct_a = round(pa * 100); pct_h = 100 - pct_a
    team, pct = (a, pct_a) if pa >= ph else (h, pct_h)
    if pa == ph:
        team = h
    fav_is_away = team == a
    rng = [pa] + [win_prob_v2(x[a], x[h], lead, scale)[0] for x in e['alts']]
    rng = [round((p if fav_is_away else 1 - p) * 100) for p in rng]
    return {'team': team, 'pct': pct, 'away': a, 'home': h, 'p_away': pct_a, 'p_home': pct_h,
            'xg_away': round(lam[a], 2), 'xg_home': round(lam[h], 2), 'phase': res['phase'],
            'lo': min(rng), 'hi': max(rng), 'v2': True, 'team_norm': e['team_norm']}


def pill(f):
    """Compact 'MTL 52%' pill for a board tile; '' when there is no estimate."""
    if not f:
        return ''
    basis = 'now, from the live score + remaining expected goals' if f['phase'] == 'live' else 'pregame'
    tip = (f'Model estimate, not odds ({basis}): {f["away"]} {f["p_away"]}% · {f["home"]} {f["p_home"]}%. '
           f'Expected goals {f["away"]} {f["xg_away"]:.2f} vs {f["home"]} {f["xg_home"]:.2f} from the next-goal model '
           + ((f'(xG + situational; {V2_NOTE}{"" if f.get("team_norm") else "; team GF/GA unavailable"}); '
               f'range {f["lo"]}–{f["hi"]}% across skater-only / team-only inputs.') if f.get('v2') else
              '(xG + situational); Poisson regulation, OT/shootout split 50/50.'))
    t = escape(tip, quote=True)
    return (f'<span class="wpf" title="{t}" aria-label="{t}"><i>Fav</i> <b>{escape(str(f["team"]))} {f["pct"]}%</b></span>')


def legend(fav):
    """Board caption addition, only when at least one tile shows a 'Fav' pill."""
    return ' · <span class="wpf-l"><b>Fav</b> = model win estimate (next-goal model, not odds)</span>' if fav else ''
