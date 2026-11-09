"""V5.8 Numbers (numerology & gematria) presentation: clearer hierarchy, explicit number -> meaning mapping.

Presentation only. Every value comes unchanged from numerology_v48 / player_targets_v49 / numboard_v56 (same matches,
same threat score formula, same tiers and colours, same per-game grouping, sort and limit). Colour is never the only
cue: each tier also has an icon and a word, and each match chip says what it matched (DAY / ARENA / TEAM), which
number, and by which cipher.
"""
import pos_tag_v59 as _pos   # V5.9: position tag after names (display only)
import math
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



def reference_patterns_html():
    """User-supplied reference display only; never an input to any cipher, match or rank."""
    style = """<style>
.num-pattern-ref{min-width:0;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere;border:1px solid rgba(155,92,255,.3);background:linear-gradient(135deg,rgba(155,92,255,.09),rgba(0,229,255,.035))}
.num-pattern-ref .nprf-grid{display:grid;grid-template-columns:1.2fr 1.2fr 1fr;gap:12px;min-width:0}
.num-pattern-ref .nprf-group{min-width:0;padding:10px 12px;border:1px solid rgba(155,92,255,.18);border-radius:10px}
.num-pattern-ref h4{font-size:.78rem;letter-spacing:.07em;text-transform:uppercase;margin:0 0 6px;color:#c9b6ff}
.num-pattern-ref p,.num-pattern-ref ul{margin:0;line-height:1.6}.num-pattern-ref ul{list-style:none;padding:0}
.num-pattern-ref .nprf-additional{grid-column:1/-1}.num-pattern-ref .nprf-primary{border-color:rgba(0,229,255,.3)}.num-pattern-ref .nprf-primary p{font-size:1.12rem;font-weight:700;color:#d9caff}
.num-pattern-ref u{text-decoration-line:underline;text-decoration-thickness:2px;text-underline-offset:.22em}
.num-pattern-ref .nprf-note{font-size:.78rem;margin-top:10px;opacity:.8}
@media(max-width:600px){.num-pattern-ref .nprf-grid{grid-template-columns:1fr;gap:8px}.num-pattern-ref .nprf-group{padding:8px 10px}}
</style>"""
    return (style + '<section class="sec num-pattern-ref" aria-label="Number patterns reference">'
            '<div class="sh"><h3>Number patterns</h3><p>Reference only · underlined numbers mark the key sequence</p></div>'
            '<div class="nprf-grid">'
            '<div class="nprf-group nprf-primary"><h4>Primary pattern</h4><p>9, <u>91</u>, <u>92</u>, <u>93</u>, <u>19</u></p></div>'
            '<div class="nprf-group"><h4>Secondary patterns</h4><ul><li>2-21, 22, 20</li><li>7, 27, 37, 17</li><li>4, 43, 44, 49</li></ul></div>'
            '<div class="nprf-group"><h4>Honorary numbers</h4><p>81, 18, 11, 13</p></div>'
            '<div class="nprf-group nprf-additional"><h4>Additional pattern</h4><p>4, 10, 0, 9, 3, 6</p>'
            '<p class="nprf-note">Possible date mapping: October 9th, 36.</p>'
            '<p class="nprf-note">User-supplied possible mapping; reference only.</p></div></div>'
            '<p class="nprf-note">Display reference only. Existing cipher rules, matches, scores and sorting are unchanged.</p></section>')


def legend():
    items = ''.join(f'<li class="t-{n}" style="--c:{c}"><span class="ti">{TIER_ICON[n]}</span><b>{n.title()}</b><small>{TIER_RANGE[n]}</small></li>' for _, n, c in TIERS)
    return (f'<section class="nlg nleg-v58"><div class="nlg-h"><b>How to read a row</b><span>Score 0–100 = ({W_DAY}·DAY + {W_ARENA}·ARENA + {W_TEAM}·TEAM) ÷ {RAW_MAX} × 100 · '
            f'each counts once (0 or 1) when the player’s name number equals that target · ring fill = score · '
            f'Eng = the full name’s English total before reducing to one digit</span></div>'
            '<p class="nlg-k">The three ciphers are not independent: Reduction always gives the same digit as English, and '
            'Reverse mirrors English (the two digits always add up to 9, e.g. 7 and 2). So each name has one number, and it is counted once; '
            'the day match uses the English digit only (a Reverse digit equal to the day is a different English number).</p>'
            f'<ul class="nlg-t" aria-label="Threat tiers, warm = higher">{items}</ul>'
            '<p class="nlg-k"><span class="mc d">DAY</span> matches the universal day · <span class="mc a">ARENA</span> matches the game’s arena name · '
            '<span class="mc t">TEAM</span> matches his own team name · warm colours = higher score; every tier also has its icon and word</p>'
            '<p class="nlg-k"><span class="npk pk1">★ TOP PICK</span> each team’s highest score on the slate · <span class="npk pk2">☆ RUNNER-UP</span> its second · '
            'ties: score, then model chance, form, shot rate, English name total</p></section>')


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


def _norm_pid(pid):
    """8483493 / '8483493' / 8483493.0 -> '8483493' (the model_p_from_results key); anything else -> str()."""
    try:
        return str(int(float(pid)))
    except (TypeError, ValueError):
        return str(pid)


def _num(v):
    """Finite float or None (missing / blank / NaN -> None, which ranks lowest)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def pick_order(p, model_p=None):
    """Deterministic rank key (lower sorts first): threat score (raw points), then model chance, then form index
    ('form' = V3.2 Adjusted Index), then shot rate ('shot_rate' = Shots/G L5, L10 fallback), then the raw English name
    total ('eng_total'), and only then the player id as a final deterministic key. Never alphabetical. Any value missing
    for a player ranks lowest at that stage. Model chance etc. only break ties inside equal points."""
    mp = (model_p or {}).get(_norm_pid(p.get('player_id'))) if model_p else None
    low = float('-inf')

    def stage(v):
        v = _num(v)
        return -(v if v is not None else low)
    form = p.get('form') if p.get('form_known', True) else None
    return (-int(p.get('threat_raw', 0)), stage(mp), stage(form), stage(p.get('shot_rate')), stage(p.get('eng_total')),
            _norm_pid(p.get('player_id') or ''))


def model_p_from_results(results):
    """{str(pid): pregame model chance} for the TOP PICK tie-break, from the next-goal model's player records
    (``lstate.slate_results`` -> result['players'], the same records Home's parlay / Long Shot use: ``pid`` + ``lam_game``).
    Only ever a tie-break inside equal gematria points; never part of any Numbers score or hit rate.
    (Ranking rows have 'Player ID' and no 'lam_game', so building this from them gave {'None': 0.0} and every tie
    fell to alphabetical order.)"""
    from live_nextgoal_v56 import p_anytime
    out = {}
    for r in results or []:
        res = (r or {}).get('result') or {}
        for rec in res.get('players') or []:
            pid, lam = rec.get('pid'), rec.get('lam_game')
            if pid in (None, '') or lam is None:
                continue
            try:
                key, p = _norm_pid(pid), p_anytime(lam)
            except (TypeError, ValueError):
                continue
            if key not in out or p > out[key]:
                out[key] = p
    return out


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
    return f'<span class="npk {cls}" title="{text.title()} for this team (threat, then model chance, form, shot rate, English total)">{icon} {text}</span>'



# Optional exact-match DISPLAY overlay. These literal values never feed scoring or ciphers.
FOLLOW_PATTERN = (4, 10, 0, 9, 3, 6)
OVERLAY_RULE = ('Exact match of the player’s already-computed English root (values.ordinal_root) to '
                '4, 10, 0, 9, 3, 6. No Reverse matches, digit transforms or date mapping. '
                '10 is kept literally, not reduced to 1; a normal name root is 1–9. '
                'An explicit 0 can match; missing/unknown values cannot.')
OVERLAY_STYLE = ('<style>.v58-num .npr-overlay{display:block;margin-top:4px;color:#c9b6ff;'
                 'font-size:.76rem;overflow-wrap:anywhere}.v58-num .npr-overlay-summary{'
                 'font-size:.85rem;color:#c9b6ff;margin:6px 0}</style>')


def overlay_key(day):
    return 'v60_number_overlay:' + str(day)


def overlay_match(p):
    """English-only equality on the existing computed field; never coerce unknown to zero."""
    value = (p.get('values') or {}).get('ordinal_root')
    if value is None or isinstance(value, bool):
        return None
    number = _num(value)
    if number is None or not number.is_integer() or number not in FOLLOW_PATTERN:
        return None
    return f'English root = {int(number)}'


def _board_ranks(boards, model_p=None):
    return pick_ranks(top_picks_per_team([b.get('all_players') or b['players'] for b in boards], model_p))


def _shown_players(board, ranks, pin=True):
    return pin_board(board['players'], board.get('all_players'), ranks, pin) if ranks else board['players']


def _overlay_reason(p, overlay):
    """overlay True = original root-only 4,10,0,9,3,6 API; a list of registry entries = daily union (root OR total)."""
    if overlay is True:
        return overlay_match(p)
    import daily_patterns_v60 as _dp
    return _dp.reason(p, overlay)


def overlay_counts(boards, model_p=None, pin=True, patterns=None):
    """Count the SAME already-selected displayed rows (after limits/pinning), not a fresh candidate pool."""
    ranks = _board_ranks(boards, model_p)
    rows = [p for b in boards for p in _shown_players(b, ranks, pin)]
    if patterns is not None:
        return len(rows), (sum(_overlay_reason(p, list(patterns)) is not None for p in rows) if patterns else 0)
    return len(rows), sum(overlay_match(p) is not None for p in rows)


def player_row(p, rank=None, pos_tag='', overlay_reason=None):
    v = p.get('values') or {}
    roots = ' · '.join(f'{short} {v.get(field, "—")}' for _, field, short in METHOD_FIELD)
    pk = f' {PICK_LABEL[rank][2]}' if rank in PICK_LABEL else ''
    return (f'<li class="npr t-{p["tier"]}{pk}" style="--c:{p["colour"]}"><span class="npr-ring" style="--to:{p["threat"] * 3.6:.0f}deg" title="Threat {p["threat"]}/100">'
            f'<span>{TIER_ICON.get(p["tier"], "")}</span></span>'
            f'<div class="npr-id"><span class="npr-nl"><b class="npr-name">{esc(p["player"])}</b>{pos_tag}{pick_badge(rank)}</span><small>{esc(p["team"])} · <span class="tn">{esc(roots)}</span></small>'
            + (f'<small class="npr-overlay">Overlay match · {esc(overlay_reason)}</small>' if overlay_reason else '') + '</div>'
            f'<div class="npr-m">{match_chips(p)}</div>'
            f'<div class="npr-s"><strong class="tn">{p["threat"]}</strong><small>{TIER_ICON.get(p["tier"], "")} {p["tier"]}'
            + (f' · Eng {int(p["eng_total"])}' if p.get('eng_total') is not None else '') + '</small></div></li>')


def game_board(board, day_num, ranks=None, pin=True, pmap=None, overlay=False):
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
    players = _shown_players(board, ranks, pin)
    baseline_count = len(players)
    if overlay:
        players = [p for p in players if _overlay_reason(p, overlay) is not None]
    rows = ''.join(player_row(p, ranks.get(_pkey(p)), _pos.tag_for(pmap, p.get('player_id'), p.get('team'), p.get('player'), p) if pmap is not None else '',
                              _overlay_reason(p, overlay) if overlay else None) for p in players)
    rows = rows or ('<li class="npr none">0 overlay matches in the current selection.</li>' if overlay else '<li class="npr none">No ranked players.</li>')
    effect = (f'<p class="npr-overlay-summary">Overlay ON · {len(players)} of {baseline_count} current selections shown</p>' if overlay else '')
    return (f'<section class="sec ngb{" ahit" if board["arena_hit"] else ""}"><header class="ngb-h">{v5.logo(a, "tl")}<h4>{esc(a)} <span>@</span> {esc(h)}</h4>{v5.logo(h, "tl")}'
            f'<span class="ngb-c" title="Players with a threat score above 0">⚑ {board["badge"]} threat{"s" if board["badge"] != 1 else ""}</span></header>'
            f'<div class="ngb-m">{f"<span>🕒 {esc(when)}</span>" if when else ""}<span>Day <b>{esc(day_num)}</b></span>{arena_html}</div>'
            f'{effect}<ol class="ngb-l">{rows}</ol></section>')


def boards_html(boards, day_num, model_p=None, pin=True, pmap=None, overlay=False):
    """Legend + every game board. Each team's TOP PICK / RUNNER-UP comes from all lists on the page (every board).
    overlay: False/[] = baseline; True = original 4,10,0,9,3,6 root rule; list of daily registry entries = union filter."""
    if isinstance(overlay, tuple):
        overlay = list(overlay)
    ranks = _board_ranks(boards, model_p)
    return (OVERLAY_STYLE if overlay else '') + legend() + '<div class="nbgrid ngrid">' + ''.join(game_board(b, day_num, ranks, pin, pmap, overlay) for b in boards) + '</div>'


DAILY_STYLE = ('<style>.num-daily{min-width:0;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere;'
               'border:1px solid rgba(155,92,255,.3);background:linear-gradient(135deg,rgba(155,92,255,.09),rgba(0,229,255,.035))}'
               '.num-daily .ndp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px;min-width:0}'
               '.num-daily .ndp-item{min-width:0;padding:10px 12px;border:1px solid rgba(155,92,255,.18);border-radius:10px}'
               '.num-daily h4{font-size:.78rem;letter-spacing:.07em;text-transform:uppercase;margin:0 0 6px;color:#c9b6ff}'
               '.num-daily .ndp-nums{font-size:1.05rem;font-weight:700;color:#d9caff;margin:0}'
               '.num-daily dl{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:8px 0 0;font-size:.82rem}'
               '.num-daily dt{opacity:.8}.num-daily dd{margin:0;font-weight:600}'
               '.num-daily .ndp-note{font-size:.78rem;margin:8px 0 0;opacity:.8}</style>')


def daily_patterns_html(entries, warnings=()):
    """Visible registry list (date, literal numbers, optional literal note / breakdown). Display only."""
    import daily_patterns_v60 as _dp
    items = []
    for e in entries:
        nums = ', '.join(str(n) for n in e['numbers'])
        rootable = [n for n in e['numbers'] if 1 <= n <= 9]
        other = [n for n in e['numbers'] if not 1 <= n <= 9]
        bd = ''.join(f'<dt>{esc(a)}</dt><dd>{esc(b)}</dd>' for a, b in e['breakdown'])
        items.append(f'<div class="ndp-item"><h4>{esc(e["label"])} · {esc(e["date"])}</h4><p class="ndp-nums">{esc(nums)}</p>'
                     + (f'<dl aria-label="Date breakdown (user-supplied)">{bd}</dl>' if bd else '')
                     + (f'<p class="ndp-note">{esc(e["note"])}</p>' if e.get('note') else '')
                     + f'<p class="ndp-note">Can match a 1–9 English root: {esc(", ".join(map(str, rootable)) or "none")}'
                     + (f' · full-total only: {esc(", ".join(map(str, other)))}' if other else '') + '</p></div>')
    body = ''.join(items) or '<p>No daily patterns registered.</p>'
    warn = ''.join(f'<p class="ndp-note">⚠ {esc(w)}</p>' for w in warnings)
    return (DAILY_STYLE + '<section class="sec num-daily" aria-label="Daily number patterns">'
            '<div class="sh"><h3>Daily patterns</h3><p>One user-supplied pattern per day · each can be applied as a By Game filter</p></div>'
            f'<div class="ndp-grid">{body}</div>{warn}<p class="ndp-note">{esc(_dp.NOT_TESTED)}</p></section>')
