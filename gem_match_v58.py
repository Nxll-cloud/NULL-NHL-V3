"""V5.8 Gematria match table: players whose name numbers equal tonight's universal day ("date") or their game's arena
number ("arena"). Same ciphers as the rest of the Numbers page (player_targets_v49.METHODS: English ordinal, full
reduction, reverse ordinal; digit roots). Arena numbers come only from the real NHL venue name; games without a venue
get no arena rows. Recreational number coincidences, never a scoring signal."""
from __future__ import annotations

import html

from numerology_v48 import gematria
from player_targets_v49 import METHODS
import venue_v58 as vn

MATCH_TYPES = ('date', 'arena')   # the ONLY match types the table may show
COLUMNS = ('Player', 'Match type', 'Number')


def arena_number(arena):
    """{cipher field: digit root} for a real arena name, or None when the arena is unknown (never guessed)."""
    a = vn.clean(arena)
    if not a:
        return None
    g = gematria(a)
    if not g['letters']:
        return None
    return {f: g[f] for f, _ in METHODS}


def player_rows(name, day_num, arena_nums):
    """[(match type, number)] for one player: at most one 'date' row and at most one 'arena' row."""
    v = gematria(name)
    if not v['letters']:
        return []
    out = []
    if any(v[f] == day_num for f, _ in METHODS):
        out.append(('date', int(day_num)))
    if arena_nums:   # one arena row: the first matching cipher in page order (English, Reduction, Reverse)
        hit = next((arena_nums[f] for f, _ in METHODS if v[f] == arena_nums[f]), None)
        if hit is not None:
            out.append(('arena', int(hit)))
    return out


def match_table(slate_targets, day_num):
    """slate_targets (player_targets_v49.slate_targets) -> (rows, games_without_venue).
    rows: [{'Player','Match type','Number','player_id','team'}], date rows first, then arena rows."""
    rows, missing, seen = [], [], set()
    for s in slate_targets or []:
        g = s.get('game') or {}
        an = arena_number(g.get('arena'))
        if an is None:
            missing.append(f"{g.get('away', '')} @ {g.get('home', '')}")
        for t in list(s.get('away_targets') or []) + list(s.get('home_targets') or []):
            key = t.get('player_id') or (t.get('team'), str(t.get('player', '')).casefold())
            if key in seen:
                continue
            seen.add(key)
            for mt, n in player_rows(t.get('player', ''), day_num, an):
                rows.append({'Player': t.get('player', ''), 'Match type': mt, 'Number': n,
                             'player_id': t.get('player_id', ''), 'team': t.get('team', '')})
    rows = [r for r in rows if r['Match type'] in MATCH_TYPES]   # hard filter: nothing but date / arena
    assert all(r['Match type'] in MATCH_TYPES for r in rows)
    rows.sort(key=lambda r: (MATCH_TYPES.index(r['Match type']), r['Number'], r['Player']))
    return rows, missing


def table_html(rows, missing, day_num, loaded=True):
    """Compact three-column table (Player | Match type | Number) for st.html; scrolls vertically, never horizontally."""
    e = html.escape
    head = (f'<div class="sh"><h3>Date &amp; arena matches</h3><p>Players whose name number equals tonight’s universal day '
            f'(<b>{e(str(day_num))}</b>) or their game’s arena number · same three ciphers as the boards · entertainment only</p></div>')
    if not loaded:
        body = '<div class="gm-empty">Player matches appear once this slate’s rankings are loaded.</div>'
    elif not rows:
        body = '<div class="gm-empty">No player matches tonight’s date or arena numbers.</div>'
    else:
        trs = ''.join(f'<tr><td class="gm-p"><b>{e(str(r["Player"]))}</b></td><td><span class="gm-t {r["Match type"]}">{r["Match type"]}</span></td>'
                      f'<td class="gm-n">{int(r["Number"])}</td></tr>' for r in rows)
        body = (f'<div class="gm-w"><table class="gm"><thead><tr><th>Player</th><th>Match type</th><th>Number</th></tr></thead>'
                f'<tbody>{trs}</tbody></table></div>')
    nd, na = sum(r['Match type'] == 'date' for r in rows), sum(r['Match type'] == 'arena' for r in rows)
    note = f'{nd} date · {na} arena'
    if missing:
        note += f' · no arena number for {e(", ".join(missing))} (no venue in the NHL schedule)'
    return f'<section class="sec v58-gm">{head}{body}<p class="gm-note">{note}</p></section>'
