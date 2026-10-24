"""Null's Playbook V5.9 · Position + gematria layers (Numbers tab curiosity layer).

Presentation only. For every player on tonight's slate it lines up the layers the page already computes (Day = the
English-digit day rule, Arena / Team = the existing English-digit name matches from player_targets_v49.target_rows)
plus one extra curiosity layer: the player's position labels (position_gematria_v59.LABELS, both defenceman spellings
and the NHL codes) run through numerology_v48.gematria and compared, English digit only, with the day number and with
his game's arena number (the same English-digit arena comparison the app uses). Not imported by any scoring, ranking,
tier, TOP PICK or match-table module; nothing here feeds back into them.
"""
import html

from numerology_v48 import gematria
import position_gematria_v59 as _pg
import pos_tag_v59 as _pos

NOTE = ('Curiosity layer — does not affect any score, rank, tier, TOP PICK or match table. Layers = Day + Arena + Team '
        '+ Position (position counts once, whichever label fired).')

_TEXT = {label: text for label, text in _pg.LABELS}
# Position code -> the position_gematria_v59 labels that name that position (display labels, LABELS order).
POS_LABELS = {
    'C': ('Center', 'Forward', 'C'),
    'LW': ('Left Wing', 'Forward', 'L', 'LW'),
    'RW': ('Right Wing', 'Forward', 'R', 'RW'),
    'D': ('Defenseman (US)', 'Defenceman (Canadian)', 'Defense', 'D'),
    'G': ('Goalie', 'Goaltender', 'G'),
}
assert all(l in _TEXT for ls in POS_LABELS.values() for l in ls)


def _root(text):
    v = gematria(text) if text else None
    return v['ordinal_root'] if v and v['letters'] else None


def position_hits(code, day_num, arena_root):
    """['Defenceman=day', 'D=arena', ...] — each label text whose English digit equals the day / arena digit."""
    out = []
    for label in POS_LABELS.get(code or '', ()):
        text = _TEXT[label]
        r = _root(text)
        if r is None:
            continue
        if day_num is not None and r == day_num:
            out.append(f'{text}=day')
        if arena_root is not None and r == arena_root:
            out.append(f'{text}=arena')
    return out


def scored(record, pid, name):
    """'1G' / '2G' from the scorers_tonight_v58 record, else ''."""
    import scorers_tonight_v58 as _sc
    rec = _sc.lookup(record, pid, None) if pid else None
    if rec is None and name and record:
        rec = _sc.lookup(record, None, name)
    g = int((rec or {}).get('goals') or 0)
    return f'{g}G' if g > 0 else ''


def rows(slate_targets, day_num, pmap=None, record=None, model_p=None):
    """(rows with >=1 layer hit sorted Layers desc then numbers_v58_ui.pick_order, count of players with no hit)."""
    from numboard_v56 import threat_raw
    from numbers_v58_ui import pick_order
    out, none, seen = [], 0, set()
    for item in slate_targets or []:
        g = item.get('game') or {}
        arena_root = _root(g.get('arena'))
        for side in ('away_targets', 'home_targets'):
            for t in item.get(side) or []:
                key = t.get('player_id') or (t.get('team'), str(t.get('player', '')).casefold())
                if key in seen:
                    continue
                seen.add(key)
                code = _pos.lookup(pmap, t.get('player_id'), t.get('team'), t.get('player')) if pmap is not None else None
                ph = position_hits(code, day_num, arena_root)
                day, arena, team = bool(t.get('day')), bool(t.get('arena_matches')), bool(t.get('team_matches'))
                layers = int(day) + int(arena) + int(team) + int(bool(ph))
                if not layers:
                    none += 1
                    continue
                out.append({**t, 'threat_raw': threat_raw(t), 'pos': code or '', 'day_hit': day, 'arena_hit': arena,
                            'team_hit': team, 'pos_hits': ph, 'layers': layers,
                            'scored': scored(record, t.get('player_id'), t.get('player'))})
    out.sort(key=lambda p: (-p['layers'],) + tuple(pick_order(p, model_p)))
    return out, none


def table_html(data, none, day_num, loaded=True, demo=False):
    e = html.escape
    head = ('<div class="sh"><h3>Position + gematria layers</h3><p>Players on tonight’s slate with at least one layer hit · '
            f'D = day {e(str(day_num))} · A = arena · T = team · P = position label vs day / arena (English digit, labels '
            'from the position gematria table) · # = layers hit · 🚨 = scored tonight'
            + (' (DEMO replay data)' if demo else '') + '</p></div>')
    if not loaded:
        return (f'<section class="sec v58-gm v59-pl">{head}<div class="gm-empty">Layers appear once this slate’s rankings '
                f'are loaded.</div><p class="gm-note">{e(NOTE)}</p></section>')
    tick = lambda b: '<span class="pl-y">✓</span>' if b else '<span class="pl-n">·</span>'
    trs = []
    for p in data:
        chips = ''.join(f'<span class="pl-c">{e(h)}</span>' for h in p['pos_hits'])
        sc = f'<span class="pl-s{" demo" if demo else ""}">{e(p["scored"])}{" demo" if demo and p["scored"] else ""}</span>' if p['scored'] else ''
        trs.append(f'<tr class="gm-r"><td class="gm-p"><b>{e(str(p["player"]))}</b><small class="pl-tm">{e(str(p.get("team", "")))}</small></td>'
                   f'<td class="pl-pos">{e(p["pos"])}</td><td>{tick(p["day_hit"])}</td><td>{tick(p["arena_hit"])}</td>'
                   f'<td>{tick(p["team_hit"])}</td><td>{tick(bool(p["pos_hits"]))}</td><td class="gm-n">{p["layers"]}</td>'
                   f'<td class="pl-sc">{sc}</td></tr>'
                   + (f'<tr class="gm-c pl-ch"><td colspan="8">{chips}</td></tr>' if chips else ''))
    body = ('<div class="gm-w"><table class="gm"><thead><tr><th>Player</th><th title="Position">Pos</th><th title="Day">D</th>'
            '<th title="Arena">A</th><th title="Team">T</th><th title="Position layer">P</th><th title="Layers">#</th>'
            f'<th title="Scored tonight">🚨</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
            if data else '<div class="gm-empty">No player hits any layer tonight.</div>')
    note = f'{len(data)} with ≥1 layer · {none} player{"s" if none != 1 else ""} with no layer hit · {NOTE}'
    return f'<section class="sec v58-gm v59-pl">{head}{body}<p class="gm-note">{e(note)}</p></section>'
