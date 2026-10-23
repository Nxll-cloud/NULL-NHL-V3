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


def by_key(results):
    """{slate game key: favorite dict} for games that have the inputs (others are simply absent)."""
    out = {}
    for r in results or []:
        k = ((r or {}).get('slate') or {}).get('key')
        f = favorite(r) if k else None
        if f:
            out[k] = f
    return out


def pill(f):
    """Compact 'MTL 52%' pill for a board tile; '' when there is no estimate."""
    if not f:
        return ''
    basis = 'now, from the live score + remaining expected goals' if f['phase'] == 'live' else 'pregame'
    tip = (f'Model estimate, not odds ({basis}): {f["away"]} {f["p_away"]}% · {f["home"]} {f["p_home"]}%. '
           f'Expected goals {f["away"]} {f["xg_away"]:.2f} vs {f["home"]} {f["xg_home"]:.2f} from the next-goal model '
           f'(xG + situational); Poisson regulation, OT/shootout split 50/50.')
    t = escape(tip, quote=True)
    return (f'<span class="wpf" title="{t}" aria-label="{t}"><i>Fav</i> <b>{escape(str(f["team"]))} {f["pct"]}%</b></span>')


def legend(fav):
    """Board caption addition, only when at least one tile shows a 'Fav' pill."""
    return ' · <span class="wpf-l"><b>Fav</b> = model win estimate (next-goal model, not odds)</span>' if fav else ''
