"""V5.6 Numbers by game: per-game player boards with a documented numerology 'threat score'.

Built only from the existing V4.9 signals (``player_targets_v49.target_rows``), whose outputs are unchanged:
  D = day matches   (player's English / Reduction / Reverse root equals the universal day number)
  A = arena matches (player's root equals the arena name's root, per method)
  T = team matches  (player's root equals his team name's root, per method)

Threat score (0-100) = round(100 * (3*D + 2*A + 1*T) / 18)   -- each of D, A, T counts 0..3 methods, so raw max = 18.
Weights: the day number is the headline signal of the Numbers tab, the arena is game-specific, the team is shared by
the whole roster, so it is weighted lowest. Tiers (raw points) -> colour (warm = high):
  >= 6 'blaze' (red) · 4-5 'hot' (orange) · 2-3 'warm' (amber) · 1 'mild' (yellow) · 0 'cool' (slate)
Per-game badge = number of players with a threat score > 0. Entertainment only, never a scoring probability.
"""
from __future__ import annotations

W_DAY, W_ARENA, W_TEAM = 3, 2, 1
RAW_MAX = 3 * (W_DAY + W_ARENA + W_TEAM)
TIERS = ((6, 'blaze', '#ff3b3b'), (4, 'hot', '#ff7a1a'), (2, 'warm', '#ffb020'), (1, 'mild', '#f5d90a'), (0, 'cool', '#64748b'))


def threat_raw(t):
    return W_DAY * len(t.get('day') or []) + W_ARENA * len(t.get('arena_matches') or []) + W_TEAM * len(t.get('team_matches') or [])


def threat_score(t):
    return round(100 * threat_raw(t) / RAW_MAX)


def tier(raw):
    for lo, name, colour in TIERS:
        if raw >= lo:
            return name, colour
    return TIERS[-1][1], TIERS[-1][2]


def game_board(analysis, away_targets, home_targets, limit=None):
    """One game's board: players of both clubs sorted by threat score (then matches, then Form), plus the badge."""
    players = []
    for t in list(away_targets or []) + list(home_targets or []):
        raw = threat_raw(t)
        name, colour = tier(raw)
        players.append({**t, 'threat_raw': raw, 'threat': threat_score(t), 'tier': name, 'colour': colour})
    players.sort(key=lambda p: (-p['threat_raw'], -p['matches'], -p['form'], p['player']))
    arena_hits = [p for p in players if p['arena_matches']]
    shown = players[:limit] if limit else players
    return {'game': analysis, 'players': shown, 'all_players': players,
            'badge': sum(1 for p in players if p['threat_raw'] > 0),
            'arena_hit': bool(arena_hits), 'arena_players': [p['player'] for p in arena_hits],
            'arena_root': (analysis.get('arena_values') or {}).get('ordinal_root')}


def slate_boards(slate_targets, limit=None):
    return [game_board(s['game'], s['away_targets'], s['home_targets'], limit) for s in slate_targets]
