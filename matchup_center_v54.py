"""V5.4 Matchup Center logic (pure; no Streamlit, no network).

* ``slate_games``      - de-duplicated slate games (by Game ID, then away/home/start).
* ``game_for_pick``    - the slate game of a player-intelligence pick (team + opponent).
* ``matchup_targets``  - ranked player targets for the two teams of one game,
                         reusing ``home_leaders_v52.flatten_targets`` (player_targets_v49).
* ``leakiest_goalie``  - the goalie with the most goals allowed per 60 for a team,
                         from ``goalies_v54`` rows.

Badge rules (descriptive, never probabilities):
  Stats   = slate statistical rank <= 20 (same top-20 used by the Research overlap list)
  Numbers = >= 2 symbolic matches (day / team / arena)
  Overlap = Stats and Numbers both true
  Odds    = a unique accent-insensitive name match in the validated odds comparison
"""
import pandas as pd

from home_leaders_v52 import flatten_targets, TEAM_NAMES
import venue_v58
from odds_intelligence_v46 import normalized_name

STATS_TOP = 20
NUMBERS_MIN = 2


def _code(value):
    return str(value or '').strip().upper()


def _pid(value):
    text = str(value if value is not None else '').strip()
    if text.endswith('.0'):
        text = text[:-2]
    return text if text.isdigit() else ''


def game_key(game):
    gid = _pid(game.get('Game ID') or game.get('game_id'))
    return gid or f"{_code(game.get('Away'))}@{_code(game.get('Home'))}@{game.get('Start (UTC)') or ''}"


def slate_games(games):
    """Valid games once each, in start order. Rows without both teams are skipped."""
    seen, out = set(), []
    for g in games or []:
        if not isinstance(g, dict) or not _code(g.get('Away')) or not _code(g.get('Home')):
            continue
        k = game_key(g)
        if k in seen:
            continue
        seen.add(k)
        out.append({'key': k, 'game_id': _pid(g.get('Game ID')), 'away': _code(g.get('Away')), 'home': _code(g.get('Home')),
                    'start': g.get('Start (UTC)') or '', 'venue': venue_v58.of(g), 'status': g.get('Status') or ''})
    return sorted(out, key=lambda g: (str(g['start']), g['away']))


def find_game(games, key):
    for g in slate_games(games):
        if g['key'] == str(key):
            return g
    return None


def game_for_pick(pick, games):
    """Return the slate game for a pick, or None (no pick / team not on slate).

    If a team appears in more than one slate game (doubleheader-style duplicates),
    the game against the pick's listed opponent wins; otherwise the earliest start."""
    if not pick:
        return None
    team = _code(pick.get('Team') or pick.get('team'))
    opp = _code(pick.get('Opponent') or pick.get('opponent'))
    if not team:
        return None
    cands = [g for g in slate_games(games) if team in (g['away'], g['home'])]
    if not cands:
        return None
    exact = [g for g in cands if opp and opp in (g['away'], g['home']) and opp != team]
    game = (exact or cands)[0]
    return {**game, 'focus_team': team, 'opponent': game['home'] if game['away'] == team else game['away']}


def _odds_names(discrepancies):
    out = {}
    if isinstance(discrepancies, pd.DataFrame) and not discrepancies.empty and 'player' in discrepancies:
        gap = pd.to_numeric(discrepancies.get('decimal_price_improvement_pct'), errors='coerce') \
            if 'decimal_price_improvement_pct' in discrepancies else pd.Series([float('nan')] * len(discrepancies))
        for (_, row), g in zip(discrepancies.iterrows(), gap):
            key = normalized_name(row.get('player', ''))
            if key and pd.notna(g):
                best = out.get(key)
                if best is None or g > best['gap']:
                    out[key] = {'gap': float(g), 'price': row.get('best_odds'), 'book': row.get('best_sportsbook')}
    return out


def matchup_targets(targets, game, ranked=None, discrepancies=None, track_badges=None, leaders=(), limit=8):
    """{team: [target dicts]} for the game's two teams, ranked by Form Score then symbolic matches."""
    if not game:
        return {}
    teams = (game['away'], game['home'])
    stat_rank = {}
    if isinstance(ranked, pd.DataFrame) and not ranked.empty and 'Statistical rank' in ranked:
        for _, r in ranked.iterrows():
            rk = pd.to_numeric(r.get('Statistical rank'), errors='coerce')
            if pd.notna(rk):
                stat_rank[_pid(r.get('Player ID')) or (_code(r.get('Team')), str(r.get('Player', '')).casefold())] = int(rk)
    players = [p for p in flatten_targets(targets or []) if _code(p.get('team')) in teams]
    names = {}
    for p in players:
        names.setdefault(normalized_name(p.get('player', '')), []).append(p)
    odds = _odds_names(discrepancies)
    leader_ids = {_pid(x) for x in leaders if _pid(x)}
    out = {t: [] for t in teams}
    seen = set()
    for p in players:
        ident = _pid(p.get('player_id')) or (_code(p.get('team')), str(p.get('player', '')).casefold())
        if ident in seen:
            continue
        seen.add(ident)
        rank = stat_rank.get(ident)
        matches = int(p.get('matches') or 0)
        stats_b, num_b = rank is not None and rank <= STATS_TOP, matches >= NUMBERS_MIN
        badges = []
        if stats_b: badges.append(('Stats', 'stat'))
        if num_b: badges.append(('Numbers', 'gem'))
        if stats_b and num_b: badges.append(('Overlap', 'overlap'))
        nkey = normalized_name(p.get('player', ''))
        o = odds.get(nkey) if len(names.get(nkey, [])) == 1 else None
        if o: badges.append((f"Odds +{o['gap']:.1f}%", 'odds'))
        if _pid(p.get('player_id')) in leader_ids: badges.append(('Intel pick', 'overlap'))
        tb = (track_badges or {}).get('id:' + _pid(p.get('player_id'))) if _pid(p.get('player_id')) else None
        if tb: badges.append((tb, 'stat' if tb.startswith('Hot') else 'muted'))
        out[_code(p.get('team'))].append({**p, 'stat_rank': rank, 'badges': badges, 'odds': o})
    for t in out:
        out[t].sort(key=lambda p: (-(p.get('form') or 0), p['stat_rank'] or 10**6, -(p.get('matches') or 0), p.get('player', '')))
        out[t] = out[t][:limit]
    return out


def leakiest_goalie(goalie_rows, team):
    """Goalie with the highest GAA among goalies who played; ties -> more GA, then more GP, then name.
    Goalies with GP>0 but unknown GAA rank after known ones (by GA). None if the team has no goalie who played."""
    team = _code(team)
    rows = [g for g in (goalie_rows or []) if _code(g.get('Team')) == team and int(g.get('GP') or 0) > 0]
    if not rows:
        return None

    def key(g):
        gaa = g.get('GAA')
        known = gaa is not None and gaa == gaa
        return (0 if known else 1, -(gaa if known else 0), -int(g.get('GA') or 0), -int(g.get('GP') or 0), str(g.get('Goalie', '')))
    return sorted(rows, key=key)[0]


def weaker_goalie_side(goalie_rows, game):
    """Team code whose shooters face the leakier opposing goalie, or None when it can't be told."""
    if not game:
        return None
    ga, gh = leakiest_goalie(goalie_rows, game['away']), leakiest_goalie(goalie_rows, game['home'])
    if not ga or not gh or ga.get('GAA') is None or gh.get('GAA') is None or ga['GAA'] == gh['GAA']:
        return None
    return game['home'] if ga['GAA'] > gh['GAA'] else game['away']
