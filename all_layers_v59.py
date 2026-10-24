"""Null's Playbook V5.9 · All-layer matches (Numbers tab curiosity layer, collapsed expander).

Presentation only. Lists the slate players who hit ALL five layers at once:
  day      - name English digit = universal day (player_targets_v49 day rule: English only)
  position - a label of the player's position (position_gematria_v59 labels: full names, both defenceman spellings,
             codes) has an English or Reverse digit equal to the day digit or the game's arena number
  arena    - the app's existing arena match (player_targets_v49: name English digit = arena English digit)
  reverse  - at least one hit is via the Reverse cipher (name Reverse vs the day / arena number, or a position label's)
  english  - at least one hit is via English (implied by the day layer)
Targets are single numbers: the day digit and the arena number (the arena name's English digit, as on the boards).
Reverse digit = 9 - English digit (9 stays 9), so one name never hits the same target with both ciphers.
Not imported by any scoring, ranking, tier, TOP PICK or match-table module.
"""
import html

from numerology_v48 import gematria
import pos_tag_v59 as _pos
import position_layers_v59 as _pl

CRITERIA = ('day', 'position', 'arena', 'reverse', 'english')
LABEL = {'day': 'Day', 'position': 'Position', 'arena': 'Arena', 'reverse': 'Reverse', 'english': 'English'}
CAPTION = ('Curiosity layer — not used in any score, rank, tier, TOP PICK or match table. A player is listed only when '
           'his name hits the day (English) and his game’s arena, a position label hits the day or arena number, and at '
           'least one hit is via Reverse and one via English.')


def _digits(text):
    v = gematria(text) if text else None
    return (v['ordinal_root'], v['reverse_root']) if v and v['letters'] else None


def evaluate(t, code, day_num, arena_num):
    """{'hits': [chip, ...], 'met': {criterion: bool}} for one player target dict."""
    hits, eng, rev = [], False, False
    nv = t.get('values') or gematria(str(t.get('player', '')))
    day = bool(t.get('day'))                     # app's day rule (English only)
    arena = bool(t.get('arena_matches'))         # app's arena match (English vs arena English)
    if day:
        hits.append('Day Eng'); eng = True
    if arena:
        hits.append('Arena Eng'); eng = True
    if nv.get('letters'):
        if day_num is not None and nv['reverse_root'] == day_num and nv['ordinal_root'] != day_num:
            hits.append('Day Rev'); rev = True
        if arena_num is not None and nv['reverse_root'] == arena_num:
            hits.append('Arena Rev'); rev = True
    pos = False
    for label in _pl.POS_LABELS.get(code or '', ()):
        text = _pl._TEXT[label]
        d = _digits(text)
        if not d:
            continue
        for cipher, digit in (('Eng', d[0]), ('Rev', d[1])):
            for target, num in (('day', day_num), ('arena', arena_num)):
                if num is not None and digit == num:
                    hits.append(f'{text}={target} {cipher}'); pos = True
                    eng = eng or cipher == 'Eng'; rev = rev or cipher == 'Rev'
    return {'hits': hits, 'met': {'day': day, 'position': pos, 'arena': arena, 'reverse': rev, 'english': eng}}


def rows(slate_targets, day_num, pmap=None, record=None, model_p=None):
    """(full matches, closest 4-of-5 with 'missed'), each sorted by numbers_v58_ui.pick_order."""
    from numboard_v56 import threat_raw
    from numbers_v58_ui import pick_order
    full, close, seen = [], [], set()
    for item in slate_targets or []:
        arena_num = _pl._root((item.get('game') or {}).get('arena'))
        for side in ('away_targets', 'home_targets'):
            for t in item.get(side) or []:
                key = t.get('player_id') or (t.get('team'), str(t.get('player', '')).casefold())
                if key in seen:
                    continue
                seen.add(key)
                code = _pos.lookup(pmap, t.get('player_id'), t.get('team'), t.get('player')) if pmap is not None else None
                ev = evaluate(t, code, day_num, arena_num)
                n = sum(ev['met'].values())
                if n < 4:
                    continue
                r = {**t, 'threat_raw': threat_raw(t), 'pos': code or '', 'hits': ev['hits'], 'met': ev['met'],
                     'missed': [c for c in CRITERIA if not ev['met'][c]],
                     'scored': _pl.scored(record, t.get('player_id'), t.get('player'))}
                (full if n == 5 else close).append(r)
    full.sort(key=lambda p: pick_order(p, model_p))
    close.sort(key=lambda p: pick_order(p, model_p))
    return full, close


def table_html(full, close, day_num, loaded=True, demo=False, close_limit=8):
    e = html.escape
    head = (f'<div class="sh"><h3>All-layer matches</h3><p>Day {e(str(day_num))} + position label + arena + a Reverse hit + '
            'an English hit, all at once · targets are the day digit and the arena number'
            + (' · 🚨 = scored tonight (DEMO replay data)' if demo else ' · 🚨 = scored tonight') + '</p></div>')
    cap = f'<p class="gm-note">{e(CAPTION)}</p>'
    if not loaded:
        return f'<section class="sec v58-gm v59-al">{head}<div class="gm-empty">All-layer matches appear once this slate’s rankings are loaded.</div>{cap}</section>'
    chip = lambda h: f'<span class="pl-c{" rv" if h.endswith("Rev") else ""}">{e(h)}</span>'
    sc = lambda p: (f'<span class="pl-s{" demo" if demo else ""}">{e(p["scored"])}{" demo" if demo else ""}</span>' if p['scored'] else '')
    if full:
        trs = ''.join(f'<tr class="gm-r"><td class="gm-p"><b>{e(str(p["player"]))}</b></td><td class="pl-pos">{e(p["pos"])}</td>'
                      f'<td class="pl-pos">{e(str(p.get("team", "")))}</td><td class="pl-sc">{sc(p)}</td></tr>'
                      f'<tr class="gm-c pl-ch"><td colspan="4">{"".join(chip(h) for h in p["hits"])}</td></tr>' for p in full)
        body = ('<div class="gm-w"><table class="gm"><thead><tr><th>Player</th><th title="Position">Pos</th><th>Team</th>'
                f'<th title="Scored tonight">🚨</th></tr></thead><tbody>{trs}</tbody></table></div>'
                f'<p class="gm-note">{len(full)} player{"s" if len(full) != 1 else ""} match all five layers</p>')
    else:
        items = ''.join(f'<li><b>{e(str(p["player"]))}</b> <span class="al-m">{e(p["pos"])} · {e(str(p.get("team", "")))}</span> '
                        f'<span class="al-x">missed {e(", ".join(LABEL[m] for m in p["missed"]))}</span>{sc(p)}</li>'
                        for p in close[:close_limit])
        more = f' · showing {close_limit} of {len(close)}' if len(close) > close_limit else ''
        body = ('<div class="gm-empty">No player matches all layers today.</div>'
                + (f'<div class="al-cl"><h4>Closest (4 of 5){e(more)}</h4><ul>{items}</ul></div>' if close
                   else '<div class="al-cl"><h4>Closest (4 of 5)</h4><p class="gm-note">No player hits 4 of the 5 layers either.</p></div>'))
    return f'<section class="sec v58-gm v59-al">{head}{body}{cap}</section>'
