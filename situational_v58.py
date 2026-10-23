"""V5.8 situational layer for the next-goal model (pure; network only in ``fetch_context``, which the app caches).

The V5.6 baseline is untouched and stays the anchor:
  base lambda = prior shots/game x shrunk sh%,   shrunk sh% = (G + 50 x 0.10) / (SOG + 50)   (live_nextgoal_v56)
Situational adjustments are layered on top, each bounded, logged per player and switchable (pp / goalie / line):

1. Power play split (needs the player's PP shots, PP goals, PP TOI and season shots/goals):
     EV volume   ev_spg  = max(prior shots/game - PP shots/game, 25% of prior)    (the app's L10 volume prior minus PP shots)
     EV sh%      sh_ev   = (G - PPG + 50 x LEAGUE_EV_SH) / (SOG - PPS + 50)
     PP volume   pp_spg  = PP shot rate/min x PP TOI/game x opp_factor
                 PP shot rate/min = (PPS + M_PP_MIN x LEAGUE_PP_S60/60) / (PP TOI min + M_PP_MIN)
     PP sh%      sh_pp   = (PPG + 50 x LEAGUE_PP_SH) / (PPS + 50)
     opp_factor  = (team PP opps/g / league) x (opponent times-shorthanded/g / league), each shrunk with 10 ghost games,
                   clamped to [0.75, 1.30]
     ev = ev_spg x sh_ev ; pp = pp_spg x sh_pp ; PP add = ev + pp - base
   LEAGUE_EV_SH is solved so the league mix of EV and PP shots still averages exactly LEAGUE_SH (10%):
     LEAGUE_EV_SH = (0.10 - F_PP x LEAGUE_PP_SH) / (1 - F_PP)  -> 0.0917.  The 10% / 50-ghost-shot anchor is kept.
2. Goalie: opposing starter (NHL boxscore starter flag / ESPN probable, the app's probable_goalies_v54), else the
   opponent's goalies weighted by shots against, else neutral 1.0.
     shrunk SV% = (saves + 600 x LEAGUE_SV) / (SA + 600);  goalie_mult = (1 - shrunk SV%) / (1 - LEAGUE_SV), [0.85, 1.15]
   Live: the goalie actually in the opponent's net (latest goalieInNetId on this team's shots) replaces the starter.
3. Line / deployment: EV TOI per game over the last 14 days vs the season (NHL stats timeonice report), shrunk toward 1
   with 3 ghost games, elasticity 0.5 (the shot prior is already L10), clamped [0.90, 1.10]; applied to the EV part.
   This is ice-time deployment, NOT linemate identity (no reliable pregame line source; see V58_NOTES.md).
Final:  lambda = (core + (line_mult - 1) x ev_part) x goalie_mult, ratio = lambda / base clamped to [0.5, 2.0],
        core = ev + pp with the PP split, else base; ev_part = ev with the split, else base.
V5.9 xG (part 'xg', xg_v59): shot quality from MoneyPuck xG/SOG scales the EV and PP sh% (or the whole base without
        the PP split) by mult = (W x T x Q x F + (1 - W) x sh) / sh; see xg_v59. No xG for a player -> mult exactly 1.
Live:   the player's per-minute rate is multiplied by the same ratio (current strength PP/SH/EN stays the team-level
        multiplier in live_nextgoal_v56). No situational data for a player (or every switch off) -> ratio exactly 1,
        i.e. the old numbers.

League constants: NHL stats API (api.nhle.com/stats/rest/en), 2025-26 regular season, fetched 2026-10-23:
  skater/summary 8,086 G on 73,022 SOG; skater/powerplay 1,595 PPG on 10,799 PP SOG over 62,183 individual PP minutes;
  goalie/summary SV% .896; team/powerplay 2.88 PP opportunities per team-game.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import xg_v59 as xgm

LEAGUE_SH = 0.10
K_SHRINK = 50
F_PP = 0.148                    # share of league SOG taken on the power play (10,799 / 73,022)
LEAGUE_PP_SH = 0.148            # league PP sh% (1,595 / 10,799)
LEAGUE_EV_SH = (LEAGUE_SH - F_PP * LEAGUE_PP_SH) / (1 - F_PP)
K_PP = 50
LEAGUE_PP_S60 = 10.42           # individual PP shots per 60 PP minutes
M_PP_MIN = 20.0                 # ghost PP minutes
LEAGUE_PP_OPP_PG = 2.88         # PP opportunities per team-game (fallback when the current season is too young)
TEAM_G0 = 10                    # ghost games for team PP / times-shorthanded rates
OPP_MIN, OPP_MAX = 0.75, 1.30
LEAGUE_SV = 0.896
K_SV = 600                      # ghost shots against
GOALIE_MIN, GOALIE_MAX = 0.85, 1.15
LINE_DAYS, LINE_K, LINE_ELASTICITY = 14, 3, 0.5
LINE_MIN, LINE_MAX = 0.90, 1.10
RATIO_MIN, RATIO_MAX = 0.5, 2.0
PARTS = ('pp', 'goalie', 'line', 'xg')   # V5.9: + 'xg' (shot quality, xg_v59)
STATS = 'https://api.nhle.com/stats/rest/en'


def _f(x, default=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _clamp(x, lo, hi):
    return min(hi, max(lo, x))


def _pid(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _last_team(abbrevs):
    parts = [p.strip().upper() for p in str(abbrevs or '').split(',') if p.strip()]
    return parts[-1] if parts else ''


# ---------------------------------------------------------------- parsing (stats API rows -> plain dicts)
def parse_skaters(summary=None, powerplay=None, toi_season=None, toi_recent=None):
    """-> {pid: {gp, goals, shots, pp_goals, pp_shots, pp_toi_min, ev_toi_pg, recent_ev_toi_pg, recent_gp}}.
    A field is None when its report did not include the player (that adjustment then stays neutral)."""
    out = {}

    def rec(pid):
        return out.setdefault(pid, {'gp': None, 'goals': None, 'shots': None, 'pp_goals': None, 'pp_shots': None,
                                    'pp_toi_min': None, 'ev_toi_pg': None, 'recent_ev_toi_pg': None, 'recent_gp': 0})
    for r in summary or []:
        pid = _pid(r.get('playerId'))
        if pid is not None:
            rec(pid).update(gp=_f(r.get('gamesPlayed')), goals=_f(r.get('goals')), shots=_f(r.get('shots')))
    for r in powerplay or []:
        pid = _pid(r.get('playerId'))
        if pid is not None:
            rec(pid).update(pp_goals=_f(r.get('ppGoals')), pp_shots=_f(r.get('ppShots')), pp_toi_min=_f(r.get('ppTimeOnIce')) / 60.0,
                            pp_gp=_f(r.get('gamesPlayed')))
    for r in toi_season or []:
        pid = _pid(r.get('playerId'))
        if pid is not None:
            rec(pid).update(ev_toi_pg=_f(r.get('evTimeOnIcePerGame'), None))
    for r in toi_recent or []:
        pid = _pid(r.get('playerId'))
        if pid is not None:
            rec(pid).update(recent_ev_toi_pg=_f(r.get('evTimeOnIcePerGame'), None), recent_gp=_f(r.get('gamesPlayed')))
    return out


def parse_teams(pp_rows=None, pk_rows=None, team_list=None):
    """team/powerplay + team/penaltykill (isAggregate=false: teamId) + /team (id -> triCode) -> {tri: {...}}."""
    tri = {_pid(t.get('id')): str(t.get('triCode') or t.get('rawTricode') or '').upper() for t in team_list or []}
    out = {}
    for rows, keys in ((pp_rows, ('ppOpportunities', 'pp_opps', 'pp_gp')), (pk_rows, ('timesShorthanded', 'times_sh', 'sh_gp'))):
        for r in rows or []:
            code = tri.get(_pid(r.get('teamId')))
            if not code:
                continue
            out.setdefault(code, {})
            out[code][keys[1]] = _f(r.get(keys[0]))
            out[code][keys[2]] = _f(r.get('gamesPlayed'))
    return out


def parse_goalies(rows=None):
    """goalie/summary rows -> [{'Team','Goalie','Player ID','SA','Saves'}] (format probable_goalies_v54.match_stats uses)."""
    out = []
    for r in rows or []:
        pid = _pid(r.get('playerId'))
        if pid is None:
            continue
        out.append({'Team': _last_team(r.get('teamAbbrevs')), 'Goalie': str(r.get('goalieFullName') or ''),
                    'Player ID': str(pid), 'SA': _f(r.get('shotsAgainst')), 'Saves': _f(r.get('saves'))})
    return out


def league_pp_opp_pg(teams):
    opps = sum(_f(t.get('pp_opps')) for t in (teams or {}).values())
    gp = sum(_f(t.get('pp_gp')) for t in (teams or {}).values())
    return opps / gp if gp >= 64 and opps > 0 else LEAGUE_PP_OPP_PG   # >= 2 games per team on average


# ---------------------------------------------------------------- components
def shrink(goals, shots, league, k):
    return (max(0.0, _f(goals)) + k * league) / (max(0.0, _f(shots)) + k)


def opp_factor(team, opp, teams, league=None):
    """Expected PP opportunities tonight vs a league-average matchup. None when either team is missing."""
    t, o = (teams or {}).get(team), (teams or {}).get(opp)
    if not t or not o or 'pp_opps' not in t or 'times_sh' not in o:
        return None
    lg = league or league_pp_opp_pg(teams)
    pp = (t['pp_opps'] + TEAM_G0 * lg) / (t.get('pp_gp', 0) + TEAM_G0)
    sh = (o['times_sh'] + TEAM_G0 * lg) / (o.get('sh_gp', 0) + TEAM_G0)
    return _clamp((pp / lg) * (sh / lg), OPP_MIN, OPP_MAX)


def goalie_mult_from(saves, sa):
    sv = (max(0.0, _f(saves)) + K_SV * LEAGUE_SV) / (max(0.0, _f(sa)) + K_SV)
    return _clamp((1 - sv) / (1 - LEAGUE_SV), GOALIE_MIN, GOALIE_MAX), sv


def line_mult(sk):
    season, recent, n = _f((sk or {}).get('ev_toi_pg'), 0), _f((sk or {}).get('recent_ev_toi_pg'), 0), _f((sk or {}).get('recent_gp'))
    if season <= 0 or recent <= 0 or n <= 0:
        return 1.0
    r = (n * (recent / season) + LINE_K) / (n + LINE_K)
    return _clamp(r ** LINE_ELASTICITY, LINE_MIN, LINE_MAX)


def pp_split(prior_pg, sk, factor):
    """(ev, pp) per-game goal expectations, or None without the PP / season inputs."""
    keys = ('gp', 'goals', 'shots', 'pp_goals', 'pp_shots', 'pp_toi_min')
    if not sk or any(sk.get(k) is None for k in keys) or sk['gp'] <= 0:
        return None
    pp_spg_season = sk['pp_shots'] / sk['gp']
    ev_spg = max(prior_pg - pp_spg_season, 0.25 * prior_pg)
    sh_ev = shrink(sk['goals'] - sk['pp_goals'], sk['shots'] - sk['pp_shots'], LEAGUE_EV_SH, K_SHRINK)
    rate = (sk['pp_shots'] + M_PP_MIN * LEAGUE_PP_S60 / 60.0) / (sk['pp_toi_min'] + M_PP_MIN)
    pp_spg = rate * (sk['pp_toi_min'] / sk['gp']) * (factor if factor is not None else 1.0)
    sh_pp = shrink(sk['pp_goals'], sk['pp_shots'], LEAGUE_PP_SH, K_PP)
    return ev_spg * sh_ev, pp_spg * sh_pp


# ---------------------------------------------------------------- context
def context(skaters=None, teams=None, goalies=None, starters=None, parts=PARTS, sources=None, errors=None):
    """Bundle everything the model needs. ``starters``: {game_key or (away, home): {team: starter dict}}."""
    by_pair = {}
    for k, v in (starters or {}).items():
        teams_in = tuple(sorted((v or {}).keys()))
        if isinstance(k, tuple):
            by_pair[tuple(sorted(k))] = v
        elif len(teams_in) == 2:
            by_pair[teams_in] = v
    return {'skaters': skaters or {}, 'teams': teams or {}, 'goalies': goalies or [], 'starters': by_pair,
            'parts': tuple(p for p in (parts or ()) if p in PARTS), 'league_pp_opp_pg': league_pp_opp_pg(teams),
            'sources': sources or {}, 'errors': errors or [], 'xg': None}


def with_xg(ctx, data, day=None, season=None):
    """V5.9: same context with MoneyPuck xG data attached (gated by xg_v59.for_day: season, staleness, point-in-time).
    Unusable data -> 'xg' is None and the reason goes to ctx['sources']['xg'], i.e. the situational model unchanged."""
    ctx = dict(ctx or context())
    d = xgm.for_day(data, day, season) if day is not None else (data or xgm.empty('no data'))
    ok = bool(d.get('players')) and 'xg' in (ctx.get('parts') or ())
    ctx['xg'] = d if ok else None
    ctx['sources'] = dict(ctx.get('sources') or {}, xg=(f"{xgm.SOURCE} (as of {d.get('as_of')})" if ok
                                                       else f"off: {d.get('error') or 'xg part disabled'}"))
    return ctx


def with_starters(ctx, starters):
    """Same context with fresh starters (starters are cached for 5 min, the stats for 3 h)."""
    fresh = context(starters=starters)
    return dict(ctx or context(), starters=fresh['starters'])


def _goalie_faced(ctx, team, opp, live_goalie_id=None):
    """Multiplier for ``team``'s shooters against ``opp``'s goalie: (mult, label, source)."""
    rows = [r for r in ctx['goalies'] if r['Team'] == opp]
    if live_goalie_id is not None:
        hit = next((r for r in ctx['goalies'] if r['Player ID'] == str(live_goalie_id)), None)
        if hit:
            m, _ = goalie_mult_from(hit['Saves'], hit['SA'])
            return m, hit['Goalie'], 'in net (live play-by-play)'
    st = starter_for(ctx, team, opp)   # the same starter the rankings label shows
    if st:
        import probable_goalies_v54 as pgk
        hit = pgk.match_stats(dict(st, team=st.get('team') or opp), rows)
        if hit:
            m, _ = goalie_mult_from(hit['Saves'], hit['SA'])
            return m, hit['Goalie'], f"{st['status']} starter"
    sa = sum(r['SA'] for r in rows)
    listed = st is not None
    if sa > 0:
        m, _ = goalie_mult_from(sum(r['Saves'] for r in rows), sa)
        return m, f'{opp} goalies', 'team average (SA-weighted' + ('; starter stats not matched)' if listed else ')')
    return 1.0, None, 'no goalie data (neutral)'


def starter_for(ctx, team, opp):
    """The starter listed for ``opp`` (the goalie ``team`` faces) by the app's probable-starter source, or None."""
    st = ((ctx or {}).get('starters') or {}).get(tuple(sorted((team, opp)))) or {}
    st = st.get(opp)
    return st if st and st.get('status') in ('confirmed', 'probable') and st.get('goalie') else None


def starting_goalie_label(st):
    """'Spencer Knight (Probable)' from the source's own status; 'Unconfirmed' only when no source lists a starter."""
    return f"{st['goalie']} ({str(st['status']).title()})" if st else 'Unconfirmed'


def goalie_columns(rows, ctx):
    """Rankings rows -> same rows with 'Starting goalie' (opponent's listed starter) and 'Goalie adjustment' (the
    next-goal model's SV% step for that row, computed by the same ``_goalie_faced`` the model calls, so the label and
    the model cannot disagree). ``ctx`` = ``context``/``with_starters`` output (parts decide whether goalie is on)."""
    ctx = ctx or context()
    out = []
    for r in rows or []:
        team, opp = str(r.get('Team') or '').upper(), str(r.get('Opponent') or '').upper()
        st = starter_for(ctx, team, opp) if team and opp else None
        if 'goalie' not in (ctx.get('parts') or ()):
            note = 'Not applied (situational goalie model off)'
        elif not team or not opp or opp == 'UNAVAILABLE':
            note = 'Not applied (opponent unknown)'
        else:
            m, name, src = _goalie_faced(ctx, team, opp)
            note = f'Applied ×{m:.2f} vs {name} ({src})' if name else 'Not applied (no goalie stats)'
        out.append(dict(r, **{'Starting goalie': starting_goalie_label(st), 'Goalie adjustment': note}))
    return out


def live_goalie(game, team):
    """Goalie id in the opponent's net per the latest shot by ``team`` (None = unknown or empty net)."""
    for e in reversed((game or {}).get('events') or []):
        if e.get('team') == team and e.get('kind') in ('sog', 'goal', 'miss'):
            return e.get('goalie')
    return None


def _sh_ev_pp(sk):
    return (shrink(sk['goals'] - sk['pp_goals'], sk['shots'] - sk['pp_shots'], LEAGUE_EV_SH, K_SHRINK),
            shrink(sk['pp_goals'], sk['pp_shots'], LEAGUE_PP_SH, K_PP))


def breakdown(ctx, pid, team, opp, prior_pg, base, game=None, phase='pregame', rec=None):
    """Per-player situational breakdown. ratio == 1.0 exactly when nothing applies."""
    parts = ctx.get('parts') or ()
    sk = (ctx.get('skaters') or {}).get(pid)
    bd = {'base': base, 'ev': None, 'pp': None, 'pp_add': 0.0, 'opp_factor': None, 'goalie_mult': 1.0, 'goalie': None,
          'goalie_source': 'off', 'line_mult': 1.0, 'final': base, 'ratio': 1.0, 'applied': []}
    if base <= 0 or not parts:
        return bd
    core, ev_part = base, base
    xgd = ctx.get('xg') if 'xg' in parts else None
    xinfo = {}
    if 'pp' in parts:
        fac = opp_factor(team, opp, ctx.get('teams'), ctx.get('league_pp_opp_pg'))
        split = pp_split(prior_pg, sk, fac)
        if split is not None:
            ev, pp = split
            if xgd:   # V5.9: shot quality scales each situation's sh%
                sh_ev, sh_pp = _sh_ev_pp(sk)
                m_ev, xinfo['ev'] = xgm.blend(sh_ev, LEAGUE_EV_SH, xgm.quality(xgd, pid, 'ev'))
                m_pp, xinfo['pp'] = xgm.blend(sh_pp, LEAGUE_PP_SH, xgm.quality(xgd, pid, 'pp'))
                ev, pp = ev * m_ev, pp * m_pp
            core, ev_part = ev + pp, ev
            bd.update(ev=ev, pp=pp, pp_add=ev + pp - base, opp_factor=fac)
            bd['applied'].append('pp')
    if xgd and bd['ev'] is None and rec is not None:   # no PP split: one all-situations multiplier on base
        sh = shrink(rec.get('season_g', rec.get('goals')), rec.get('season_sog', rec.get('sog')), LEAGUE_SH, K_SHRINK)
        m_all, xinfo['all'] = xgm.blend(sh, LEAGUE_SH, xgm.quality(xgd, pid, 'all'))
        core, ev_part = core * m_all, ev_part * m_all
    xinfo = {k: v for k, v in xinfo.items() if v}
    if xinfo:
        bd['xg'] = dict(xinfo, weight=xgm.W, source=xgd.get('source'), as_of=xgd.get('as_of'))
        bd['applied'].append('xg')
    lm = line_mult(sk) if 'line' in parts else 1.0
    if lm != 1.0:
        bd['line_mult'] = lm
        bd['applied'].append('line')
    gm = 1.0
    if 'goalie' in parts:
        lg = live_goalie(game, team) if phase == 'live' else None
        gm, name, src = _goalie_faced(ctx, team, opp, lg)
        bd.update(goalie_mult=gm, goalie=name, goalie_source=src)
        if gm != 1.0:
            bd['applied'].append('goalie')
    if not bd['applied']:
        return bd
    final = (core + (lm - 1.0) * ev_part) * gm
    ratio = _clamp(final / base, RATIO_MIN, RATIO_MAX)
    bd.update(final=base * ratio, ratio=ratio)
    return bd


class Situ:
    """Callable handed to ``live_nextgoal_v56.model(..., situ=...)``."""

    def __init__(self, ctx):
        self.ctx = ctx

    def __call__(self, rec, team, opp, game, prior_pg, base, phase):
        return breakdown(self.ctx, rec.get('pid'), team, opp, prior_pg, base, game, phase, rec=rec)


def why(bd):
    """Compact one-line explanation (EdgeLab tooltip)."""
    if not bd or not bd.get('applied'):
        return 'baseline model (no situational data)'
    bits = [f"base {bd['base']:.2f}"]
    if 'pp' in bd['applied']:
        bits.append(f"PP {bd['pp_add']:+.2f}" + (f" (opps ×{bd['opp_factor']:.2f})" if bd.get('opp_factor') else ''))
    if bd.get('goalie_mult', 1.0) != 1.0:
        bits.append(f"goalie ×{bd['goalie_mult']:.2f}" + (f" {bd['goalie']}" if bd.get('goalie') else ''))
    if bd.get('line_mult', 1.0) != 1.0:
        bits.append(f"TOI ×{bd['line_mult']:.2f}")
    if bd.get('xg'):
        bits.append(xgm.why_bit(bd['xg']))
    return ' · '.join(bits) + f" → λ {bd['final']:.2f}"


# ---------------------------------------------------------------- network (wrapped by st.cache_data in app.py)
def _cayenne(season, day, since=None):
    s = f'gameTypeId=2 and seasonId<={season} and seasonId>={season} and gameDate<"{day}"'
    return s + (f' and gameDate>="{since}"' if since else '')


def fetch_context(day, season, getter=None, starters=None, parts=PARTS):
    """All inputs strictly before ``day``. Never raises: a failed report leaves its adjustment neutral."""
    if getter is None:
        import requests

        def getter(url, params=None):
            r = requests.get(url, params=params, timeout=20, headers={'User-Agent': 'NULL-NHL-V5.8'})
            r.raise_for_status()
            return r.json()
    since = (date.fromisoformat(str(day)) - timedelta(days=LINE_DAYS)).isoformat()
    plan = {'summary': ('skater/summary', None), 'powerplay': ('skater/powerplay', None), 'toi_season': ('skater/timeonice', None),
            'toi_recent': ('skater/timeonice', since), 'team_pp': ('team/powerplay', None), 'team_pk': ('team/penaltykill', None),
            'goalies': ('goalie/summary', None), 'teams': ('team', None)}
    got, errors, sources = {}, [], {}
    for key, (path, since_) in plan.items():
        params = None if key == 'teams' else {'isAggregate': 'false', 'isGame': 'false', 'limit': -1, 'start': 0,
                                               'cayenneExp': _cayenne(season, day, since_)}
        try:
            payload = getter(f'{STATS}/{path}', params)
            got[key] = (payload or {}).get('data') or []
            sources[key] = f'{STATS}/{path}'
        except Exception as exc:  # network / HTTP / JSON -> that input is missing
            got[key] = []
            errors.append(f'{key}: {type(exc).__name__}')
    return context(parse_skaters(got['summary'], got['powerplay'], got['toi_season'], got['toi_recent']),
                   parse_teams(got['team_pp'], got['team_pk'], got['teams']), parse_goalies(got['goalies']),
                   starters, parts, sources, errors)
