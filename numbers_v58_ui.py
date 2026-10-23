"""V5.8 Numbers (numerology & gematria) presentation: clearer hierarchy, explicit number -> meaning mapping.

Presentation only. Every value comes unchanged from numerology_v48 / player_targets_v49 / numboard_v56 (same matches,
same threat score formula, same tiers and colours, same per-game grouping, sort and limit). Colour is never the only
cue: each tier also has an icon and a word, and each match chip says what it matched (DAY / ARENA / TEAM), which
number, and by which cipher.
"""
from datetime import date

import v55_ui as v5
import venue_v58 as vn
from numboard_v56 import TIERS, W_DAY, W_ARENA, W_TEAM, RAW_MAX

esc = v5.esc
TIER_ICON = {'blaze': '🔥', 'hot': '♨', 'warm': '▲', 'mild': '◆', 'cool': '○'}
TIER_RANGE = {'blaze': '5–6 pts', 'hot': '3–4 pts', 'warm': '2 pts', 'mild': '1 pt', 'cool': '0 pts'}
METHOD_FIELD = (('English', 'ordinal_root', 'ENG'), ('Reduction', 'reduction_root', 'RED'), ('Reverse', 'reverse_root', 'REV'))
CIPHERS = (('English ordinal', 'A=1 … Z=26', 'Add every letter, reduce to one digit'),
           ('Full reduction', 'each letter → 1–9', 'Reduce each letter first, then the sum'),
           ('Reverse ordinal', 'A=26 … Z=1', 'Alphabet backwards, reduced to one digit'))


def day_digits(day):
    d = date.fromisoformat(day) if isinstance(day, str) else day
    digits = [int(x) for x in d.strftime('%Y%m%d')]
    return digits, sum(digits)


def tonight_strip(day, day_num, analyses, boards=None):
    """'Tonight's numbers': the day number big with its derivation, the three ciphers, and slate counts."""
    digits, total = day_digits(day)
    chain = '+'.join(str(x) for x in digits) + f' = {total}' + (f' → {day_num}' if total != day_num else '')
    games = len(analyses or [])
    arenas_hit = sum(1 for b in boards or [] if b.get('arena_hit'))
    day_players = sum(1 for b in boards or [] for p in b.get('all_players') or [] if p.get('day'))
    day_hits = sum(len(r['matches']) for r in analyses or [])
    cards = [f'''<div class="ntn hero"><span class="lbl">Universal day</span><strong class="big">{esc(day_num)}</strong>
<p>{esc(chain)}</p><em>A player whose name reduces to <b>{esc(day_num)}</b> scores a <b>DAY</b> match</em></div>''']
    for name, rule, how in CIPHERS:
        cards.append(f'<div class="ntn"><span class="lbl">{esc(name)}</span><strong>{esc(rule)}</strong><p>{esc(how)}</p></div>')
    facts = (f'<div class="ntf"><span><b>{games}</b> games</span><span><b>{day_hits}</b> team/arena names equal {esc(day_num)}</span>'
             + (f'<span><b>{day_players}</b> players match the day</span><span><b>{arenas_hit}</b>/{games} arenas matched by a player</span>' if boards is not None else '')
             + '</div>')
    return f'<section class="sec ntn-wrap"><div class="sh"><h3>Tonight’s numbers</h3><p>{esc(day)} · entertainment only, not a scoring probability</p></div><div class="ntg">{"".join(cards)}</div>{facts}</section>'


def legend():
    items = ''.join(f'<li class="t-{n}" style="--c:{c}"><span class="ti">{TIER_ICON[n]}</span><b>{n.title()}</b><small>{TIER_RANGE[n]}</small></li>' for _, n, c in TIERS)
    return (f'<section class="nlg nleg-v58"><div class="nlg-h"><b>How to read a row</b><span>Score 0–100 = ({W_DAY}·DAY + {W_ARENA}·ARENA + {W_TEAM}·TEAM) ÷ {RAW_MAX} × 100 · '
            f'each counts once (0 or 1) when the player’s name number equals that target · ring fill = score · '
            f'Eng = the full name’s English total before reducing to one digit</span></div>'
            '<p class="nlg-k">The three ciphers are not independent: Reduction always gives the same digit as English, and '
            'Reverse mirrors English (the two digits always add up to 9, e.g. 7 and 2). So each name has one number, and it is counted once.</p>'
            f'<ul class="nlg-t" aria-label="Threat tiers, warm = higher">{items}</ul>'
            '<p class="nlg-k"><span class="mc d">DAY</span> matches the universal day · <span class="mc a">ARENA</span> matches the game’s arena name · '
            '<span class="mc t">TEAM</span> matches his own team name · warm colours = higher score; every tier also has its icon and word</p>'
            '<p class="nlg-k"><span class="npk pk1">★ TOP PICK</span> each team’s highest score on the slate · <span class="npk pk2">☆ RUNNER-UP</span> its second · '
            'ties: score, then model chance, then name</p></section>')


def _numbers(p, labels):
    vals = []
    for label, field, _ in METHOD_FIELD:
        if label in labels:
            v = (p.get('values') or {}).get(field)
            if v is not None and v not in vals:
                vals.append(v)
    return '/'.join(str(v) for v in vals)


def match_chips(p):
    out = []
    for key, cls, word in (('day', 'd', 'DAY'), ('arena_matches', 'a', 'ARENA'), ('team_matches', 't', 'TEAM')):
        labels = p.get(key) or []
        if labels:
            how = ' · '.join(l[:3].upper() for l in labels)
            out.append(f'<span class="mc {cls}" title="{word} match by {esc(", ".join(labels))}"><b>{word} {esc(_numbers(p, labels))}</b><i>{esc(how)}</i></span>')
    return ''.join(out) or '<span class="mc none">no matches</span>'


# ---------------------------------------------------------------- V5.8 per-team TOP PICK / RUNNER-UP
PICK_LABEL = {1: ('★', 'TOP PICK', 'pk1'), 2: ('☆', 'RUNNER-UP', 'pk2')}


def _pkey(p):
    pid = str(p.get('player_id') or '').strip()
    return ('id', pid) if pid and pid not in ('None', 'nan') else ('name', str(p.get('player') or '').casefold())


def pick_order(p, model_p=None):
    """Deterministic rank key: threat score (raw points), then model P, then name."""
    mp = (model_p or {}).get(str(p.get('player_id'))) if model_p else None
    return (-int(p.get('threat_raw', 0)), -(mp if mp is not None else -1.0), str(p.get('player') or ''), str(p.get('player_id') or ''))


def top_picks_per_team(lists, model_p=None, n=2):
    """Every numerology list shown on the page (iterables of scored player dicts) -> {team: [rank-1, rank-2, ...]}.
    Players are deduped by playerId (name fallback), keeping the highest threat if lists disagree; up to ``n`` per team;
    a team with a single player gets no runner-up."""
    best = {}
    for lst in lists or []:
        for p in lst or []:
            if not p.get('team'):
                continue
            k = _pkey(p)
            if k not in best or pick_order(p, model_p) < pick_order(best[k], model_p):
                best[k] = p
    teams = {}
    for p in best.values():
        teams.setdefault(p['team'], []).append(p)
    return {t: sorted(ps, key=lambda p: pick_order(p, model_p))[:n] for t, ps in sorted(teams.items())}


def pick_ranks(picks):
    """{team: [p1, p2]} -> {player key: 1|2}."""
    return {_pkey(p): i for ps in (picks or {}).values() for i, p in enumerate(ps, 1)}


def pin_board(players, all_players, ranks, pin=True):
    """Keep the board's order but put each team's TOP PICK then RUNNER-UP in that team's first row slots.
    Picks cut off by the 'Players per game' limit are added back. pin=False keeps the order (badge only)."""
    shown = list(players)
    have = {_pkey(p) for p in shown}
    for p in all_players or []:
        if ranks.get(_pkey(p)) and _pkey(p) not in have:
            shown.append(p)
            have.add(_pkey(p))
    if not pin:
        return shown
    out = list(shown)
    for team in dict.fromkeys(p.get('team') for p in shown):
        slots = [i for i, p in enumerate(shown) if p.get('team') == team]
        rows = [shown[i] for i in slots]
        rows.sort(key=lambda p: ranks.get(_pkey(p), 9))   # stable: non-picks keep their order
        for i, p in zip(slots, rows):
            out[i] = p
    return out


def pick_badge(rank):
    if rank not in PICK_LABEL:
        return ''
    icon, text, cls = PICK_LABEL[rank]
    return f'<span class="npk {cls}" title="{text.title()} for this team (threat, then model chance, then name)">{icon} {text}</span>'


def player_row(p, rank=None):
    v = p.get('values') or {}
    roots = ' · '.join(f'{short} {v.get(field, "—")}' for _, field, short in METHOD_FIELD)
    pk = f' {PICK_LABEL[rank][2]}' if rank in PICK_LABEL else ''
    return (f'<li class="npr t-{p["tier"]}{pk}" style="--c:{p["colour"]}"><span class="npr-ring" style="--to:{p["threat"] * 3.6:.0f}deg" title="Threat {p["threat"]}/100">'
            f'<span>{TIER_ICON.get(p["tier"], "")}</span></span>'
            f'<div class="npr-id"><span class="npr-nl"><b class="npr-name">{esc(p["player"])}</b>{pick_badge(rank)}</span><small>{esc(p["team"])} · <span class="tn">{esc(roots)}</span></small></div>'
            f'<div class="npr-m">{match_chips(p)}</div>'
            f'<div class="npr-s"><strong class="tn">{p["threat"]}</strong><small>{TIER_ICON.get(p["tier"], "")} {p["tier"]}'
            + (f' · Eng {int(p["eng_total"])}' if p.get('eng_total') is not None else '') + '</small></div></li>')


def game_board(board, day_num, ranks=None, pin=True):
    g = board['game']
    a, h = g['away'], g['home']
    when = v5.et_time(g.get('start')) if g.get('start') else ''
    arena = esc(vn.clean(g.get('arena')), '')
    root = esc(board.get('arena_root'), '—')
    if not arena:   # V5.8: older snapshots without a venue: no arena chip (never 'None', never a guessed arena)
        arena_html = ''
    elif board['arena_hit']:
        n = len(board['arena_players'])
        arena_html = (f'<span class="nga hit" title="Matches: {esc(", ".join(board["arena_players"]))}">🏟 {arena} <b>= {root}</b>'
                      f'<em>✓ arena match · {n} player{"s" if n != 1 else ""}</em></span>')
    else:
        arena_html = f'<span class="nga">🏟 {arena} <b>= {root}</b><em>no arena match</em></span>'
    ranks = ranks or {}
    players = pin_board(board['players'], board.get('all_players'), ranks, pin) if ranks else board['players']
    rows = ''.join(player_row(p, ranks.get(_pkey(p))) for p in players) or '<li class="npr none">No ranked players.</li>'
    return (f'<section class="sec ngb{" ahit" if board["arena_hit"] else ""}"><header class="ngb-h">{v5.logo(a, "tl")}<h4>{esc(a)} <span>@</span> {esc(h)}</h4>{v5.logo(h, "tl")}'
            f'<span class="ngb-c" title="Players with a threat score above 0">⚑ {board["badge"]} threat{"s" if board["badge"] != 1 else ""}</span></header>'
            f'<div class="ngb-m">{f"<span>🕒 {esc(when)}</span>" if when else ""}<span>Day <b>{esc(day_num)}</b></span>{arena_html}</div>'
            f'<ol class="ngb-l">{rows}</ol></section>')


def boards_html(boards, day_num, model_p=None, pin=True):
    """Legend + every game board. Each team's TOP PICK / RUNNER-UP comes from all lists on the page (every board)."""
    ranks = pick_ranks(top_picks_per_team([b.get('all_players') or b['players'] for b in boards], model_p))
    return legend() + '<div class="nbgrid ngrid">' + ''.join(game_board(b, day_num, ranks, pin) for b in boards) + '</div>'
