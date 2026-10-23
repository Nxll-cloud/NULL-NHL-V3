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


SHORT = {'ordinal_root': 'Eng', 'reduction_root': 'Red', 'reverse_root': 'Rev'}   # page METHODS order
RAW = {'ordinal_root': 'ordinal', 'reduction_root': 'reduction', 'reverse_root': 'reverse'}


def player_matches(name, day_num, arena_nums, arena_name='', arena_raw=None):
    """Single source of truth for a player's rows AND the calculation shown under them: the subtitle line reads the
    same cipher digits that decided the match, so the display can never disagree with the logic. Returns
    [{'type','number','cells':[{'field','short','raw','digit','target','hit'}],'arena'}], date row first.
    arena_raw: optional {cipher field: arena raw total}, used only for the tooltip."""
    v = gematria(name)
    if not v['letters']:
        return []
    out, day = [], int(day_num)
    cells = [{'field': f, 'short': SHORT[f], 'raw': int(v[RAW[f]]), 'digit': int(v[f]), 'target': day, 'hit': v[f] == day}
             for f, _ in METHODS]
    if any(c['hit'] for c in cells):
        out.append({'type': 'date', 'number': day, 'cells': cells, 'arena': ''})
    if arena_nums:   # one arena row; Number = the arena digit of the first matching cipher in page order (Eng, Red, Rev)
        cells = [{'field': f, 'short': SHORT[f], 'raw': int(v[RAW[f]]), 'digit': int(v[f]), 'target': int(arena_nums[f]),
                  'target_raw': (arena_raw or {}).get(f), 'hit': v[f] == arena_nums[f]} for f, _ in METHODS]
        hit = next((c['target'] for c in cells if c['hit']), None)
        if hit is not None:
            out.append({'type': 'arena', 'number': hit, 'cells': cells, 'arena': vn.clean(arena_name) or ''})
    return out


def player_rows(name, day_num, arena_nums):
    """[(match type, number)] for one player: at most one 'date' row and at most one 'arena' row."""
    return [(m['type'], m['number']) for m in player_matches(name, day_num, arena_nums)]


def rev_only(row):
    """True when the row matched ONLY through the Reverse cipher (English and Reduction both miss); same hit data as calc_line."""
    hits = {c['field'] for c in row.get('calc') or [] if c['hit']}
    return hits == {'reverse_root'}


def calc_line(row):
    """Short subtitle: 'Eng 6 · Red 7 ✓ · Rev 3 → day 7' or 'Eng 4=4 ✓ · Red 2≠8 · Rev 5≠1 → United Center'."""
    cells = row.get('calc') or []
    if row.get('Match type') == 'date':
        return ' · '.join(f"{c['short']} {c['digit']}" + (' ✓' if c['hit'] else '') for c in cells) + f" → day {cells[0]['target']}"
    return (' · '.join(f"{c['short']} {c['digit']}{'=' if c['hit'] else '≠'}{c['target']}" + (' ✓' if c['hit'] else '') for c in cells)
            + ' → ' + (row.get('arena') or 'arena'))


def calc_title(row):
    """Tooltip with the raw totals before reduction, e.g. 'Eng 96→6 vs day 7 · Red 34→7 vs day 7 ✓ · ...'."""
    out = []
    for c in row.get('calc') or []:
        t = f"{c['short']} {c['raw']}→{c['digit']}"
        if row.get('Match type') == 'arena':
            tr = c.get('target_raw')
            t += f" vs arena {tr}→{c['target']}" if tr is not None else f" vs arena {c['target']}"
        else:
            t += f" vs day {c['target']}"
        out.append(t + (' ✓' if c['hit'] else ''))
    return ' · '.join(out)


def match_table(slate_targets, day_num):
    """slate_targets (player_targets_v49.slate_targets) -> (rows, games_without_venue).
    rows: [{'Player','Match type','Number','player_id','team','calc','arena'}], date rows first, then arena rows.
    'calc' = the per-cipher digits that decided the match (rendered as the row's subtitle line, never as a column)."""
    rows, missing, seen = [], [], set()
    for s in slate_targets or []:
        g = s.get('game') or {}
        an = arena_number(g.get('arena'))
        ga = gematria(vn.clean(g.get('arena'))) if an is not None else None
        ar = {f: int(ga[RAW[f]]) for f, _ in METHODS} if ga else None
        if an is None:
            missing.append(f"{g.get('away', '')} @ {g.get('home', '')}")
        for t in list(s.get('away_targets') or []) + list(s.get('home_targets') or []):
            key = t.get('player_id') or (t.get('team'), str(t.get('player', '')).casefold())
            if key in seen:
                continue
            seen.add(key)
            for m in player_matches(t.get('player', ''), day_num, an, g.get('arena'), ar):
                rows.append({'Player': t.get('player', ''), 'Match type': m['type'], 'Number': m['number'],
                             'player_id': t.get('player_id', ''), 'team': t.get('team', ''),
                             'calc': m['cells'], 'arena': m['arena']})
    rows = [r for r in rows if r['Match type'] in MATCH_TYPES]   # hard filter: nothing but date / arena
    assert all(r['Match type'] in MATCH_TYPES for r in rows)
    rows.sort(key=lambda r: (MATCH_TYPES.index(r['Match type']), r['Number'], r['Player']))
    return rows, missing


def table_html(rows, missing, day_num, loaded=True):
    """Compact three-column table (Player | Match type | Number) for st.html; scrolls vertically, never horizontally."""
    e = html.escape
    head = (f'<div class="sh"><h3>Date &amp; arena matches</h3><p>Players whose name number equals tonight’s universal day '
            f'(<b>{e(str(day_num))}</b>) or their game’s arena number · same three ciphers as the boards · the line under each row shows each cipher’s digit vs the target (✓ = match; REV = Reverse cipher only) · entertainment only</p></div>')
    if not loaded:
        body = '<div class="gm-empty">Player matches appear once this slate’s rankings are loaded.</div>'
    elif not rows:
        body = '<div class="gm-empty">No player matches tonight’s date or arena numbers.</div>'
    else:
        trs = ''.join(f'<tr class="gm-r"><td class="gm-p"><b>{e(str(r["Player"]))}</b>'
                      + (' <span class="gm-rev" title="Matched through Reverse cipher only">REV</span>' if rev_only(r) else '')
                      + f'</td><td><span class="gm-t {r["Match type"]}">{r["Match type"]}</span></td>'
                      f'<td class="gm-n">{int(r["Number"])}</td></tr>'
                      + (f'<tr class="gm-c"><td colspan="3" title="{e(calc_title(r))}">{e(calc_line(r))}</td></tr>' if r.get('calc') else '')
                      for r in rows)
        body = (f'<div class="gm-w"><table class="gm"><thead><tr><th>Player</th><th>Match type</th><th>Number</th></tr></thead>'
                f'<tbody>{trs}</tbody></table></div>')
    nd, na = sum(r['Match type'] == 'date' for r in rows), sum(r['Match type'] == 'arena' for r in rows)
    note = f'{nd} date · {na} arena'
    if missing:
        note += f' · no arena number for {e(", ".join(missing))} (no venue in the NHL schedule)'
    return f'<section class="sec v58-gm">{head}{body}<p class="gm-note">{note}</p></section>'
