"""V5.9 Matchup Center goalie-threat cards: TOP THREAT marker (display only; never used by any score or rank).

Rule, per goalie card (each goalie of each game is judged on his own):
  1. The goalie's top give-up position = goalie_pos_v59.marker()['most']: the shooter position (C / LW / RW / D) with
     the MOST goals scored on him (largest share of his goals), current + previous season, regular season + playoffs,
     all strengths, empty-net and shootout goals excluded. It needs >= goalie_pos_v59.MIN_GOALS_SHARE goals; below
     that (or no data at all) there is no top position and therefore no marker. This is the 'most G: X NN%' the card shows.
  2. Among the opposing threats LISTED on the card, keep those whose real NHL position code maps to that position
     (NHL C->C, L->LW, R->RW, D->D via pos_tag_v59.code; a missing or generic 'F' position never matches).
  3. Mark the one with the highest threat value = the card's own next-goal % (p_next, the value the card ranks by),
     compared at the precision the card shows (0.1 %). Ties at that value -> all of them are marked.
  No listed threat in that position, no p_next, or no position data -> nothing is marked (never guessed).
"""
from __future__ import annotations

import html as _html

import goalie_pos_v59 as gpos
import pos_tag_v59 as ptag


def top_position(mark):
    """marker() output -> 'C' | 'LW' | 'RW' | 'D' or None."""
    most = (mark or {}).get('most')
    return gpos.LABEL.get(most) if most else None


def _shown(p):
    try:
        return round(float(p) * 100, 1)
    except (TypeError, ValueError):
        return None


def marked(threats, mark):
    """Indexes (into ``threats``) of the TOP THREAT row(s); [] when the rule cannot apply."""
    pos = top_position(mark)
    if pos is None:
        return []
    cand = [(i, _shown(t.get('p_next'))) for i, t in enumerate(threats or []) if ptag.code(t.get('pos')) == pos]
    cand = [(i, v) for i, v in cand if v is not None]
    if not cand:
        return []
    best = max(v for _, v in cand)
    return [i for i, v in cand if v == best]


def badge(mark):
    """Row badge: 'TOP THREAT · C' with a plain-English tooltip."""
    pos = top_position(mark)
    share = (mark or {}).get('most_share') or 0
    tip = (f'Highest next-goal % among the listed threats who play {pos}, the position that has scored the most goals on '
           f'this goalie ({share * 100:.0f}% of his goals, {mark.get("window", "")}). Display only.')
    return f'<span class="ttop" title="{_html.escape(tip, quote=True)}">TOP THREAT · {pos}</span>'
