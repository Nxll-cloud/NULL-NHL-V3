"""V6.1 Life Path numbers (t209/t210/t212): birthdate numerology for the Numbers tab. Display/filter only; never scoring.

Method (standard numerology): add every digit of the full birthdate YYYY-MM-DD, then reduce by repeated digit sum,
stopping at one digit or at a master number 11, 22 or 33. Every step is kept, like the daily patterns: 1997-07-26 ->
1+9+9+7+0+7+2+6 = 41 -> 5, chain (41, 5) shown '41/5'; 1989-09-29 -> 47 -> 11 (master, stops), shown '47/11'.
A player matches a day when ANY step of his chain is one of that day's pattern numbers (daily_patterns_v60.entry_for:
saved entry if present, else auto-computed). Missing birthdate = '—' and never matches.

Birthdates: the public NHL roster feed (api-web.nhle.com/v1/roster/{team}/current, 'birthDate', the same feed the app
already uses for jerseys), joined by Player ID; for anyone still missing, the public player landing endpoint
(/v1/player/{id}/landing, 'birthDate'), capped. Every failure leaves the birthdate missing; nothing here raises.
"""
from __future__ import annotations
from datetime import date as _date
import html
import math
import re

COLUMN = 'Birth date'
MASTERS = (11, 22, 33)
ROSTER = 'https://api-web.nhle.com/v1/roster/{team}/current'
LANDING = 'https://api-web.nhle.com/v1/player/{pid}/landing'
LANDING_CAP = 80
CAPTION = ('Life Path = every digit of the player’s birthdate (YYYY-MM-DD) added, then reduced by digit sum until one digit '
           'or a master number 11, 22 or 33 (kept, not reduced). Every step is kept (e.g. 1997-07-26 → 41/5), and a player '
           'matches when any step is one of the day’s pattern numbers. Birthdates from the public NHL roster feed by Player ID; '
           'missing birthdate = — and never matches. Display only: not part of the threat score, rankings or the backtest.')
_ISO = re.compile(r'^(\d{4})-(\d{2})-(\d{2})')


def norm_date(v):
    """'YYYY-MM-DD' for a real calendar date (string/date/datetime), else None."""
    if v is None or isinstance(v, bool):
        return None
    if hasattr(v, 'isoformat') and hasattr(v, 'year'):
        try:
            return _date(v.year, v.month, v.day).isoformat()
        except (TypeError, ValueError):
            return None
    if not isinstance(v, str):
        return None
    m = _ISO.match(v.strip())
    if not m:
        return None
    try:
        return _date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def _dsum(n):
    return sum(int(c) for c in str(int(n)))


def chain(birth):
    """(41, 5) for 1997-07-26; () when the birthdate is missing/invalid. Stops at one digit or 11/22/33."""
    d = norm_date(birth)
    if d is None:
        return ()
    out = [sum(int(c) for c in d if c.isdigit())]
    while out[-1] > 9 and out[-1] not in MASTERS:
        out.append(_dsum(out[-1]))
    return tuple(out)


def number(birth):
    c = chain(birth)
    return c[-1] if c else None


def text(c):
    """'41/5', '11', or '—'."""
    c = tuple(c or ())
    return '/'.join(str(x) for x in c) if c else '—'


def hits(c, numbers):
    """Chain steps that are in the day's numbers (chain order)."""
    nums = set(numbers or ())
    return [x for x in (c or ()) if x in nums]


def label(c, step):
    """'Life Path 11' when the final number matched, else 'Life Path 5 via 41'."""
    c = tuple(c or ())
    return f'Life Path {c[-1]}' if step == c[-1] else f'Life Path {c[-1]} via {step}'


def reason(p, entries):
    """Overlay attribution across selected day entries, e.g. 'Life Path 11 · Nov 22 pattern (2026-11-22)'; None = no match."""
    c = tuple(p.get('life_path') or ())
    out = []
    for e in entries or ():
        hs = hits(c, e.get('numbers'))
        if hs:
            via = [s for s in hs if s != c[-1]]
            lab = f'Life Path {c[-1]}' + (f' via {" & ".join(map(str, via))}' if via and c[-1] not in hs else '')
            out.append(lab + (f' (also {" & ".join(map(str, via))})' if via and c[-1] in hs else '') + f' · {e["label"]} ({e["date"]})')
    return '; '.join(out) or None


def toggle_key(day):
    return f'v61_lifepath_overlay:{day}'


# ---------------------------------------------------------------- birthdate data
def pid_key(v):
    try:
        f = float(v)
        return str(int(f)) if math.isfinite(f) else ''
    except (TypeError, ValueError):
        return str(v or '').strip()


def roster_births(team, getter, timeout=10):
    r = getter(ROSTER.format(team=team), timeout=timeout)
    r.raise_for_status()
    j = r.json() or {}
    return {str(p['id']): d for grp in ('forwards', 'defensemen', 'goalies') for p in j.get(grp) or []
            if p.get('id') is not None and (d := norm_date(p.get('birthDate')))}


def landing_birth(pid, getter, timeout=10):
    r = getter(LANDING.format(pid=pid), timeout=timeout)
    r.raise_for_status()
    return norm_date((r.json() or {}).get('birthDate'))


def fetch_map(teams, getter=None, pids=(), cap=LANDING_CAP):
    """-> ({pid: 'YYYY-MM-DD'}, errors). Rosters for teams, then landing pages for pids still missing (capped). Never raises."""
    try:
        import v55_state
        if getter is None:
            import requests
            getter = requests.get
        maps, errors = v55_state.safe_many(lambda t: roster_births(t, getter), list(teams))
        out = {k: v for m in maps.values() for k, v in (m or {}).items()}
        rest = [p for p in dict.fromkeys(pid_key(x) for x in pids) if p and p not in out][:cap]
        if rest:
            got, e2 = v55_state.safe_many(lambda p: landing_birth(p, getter), rest)
            out.update({k: v for k, v in got.items() if v})
            errors = list(errors) + list(e2)
        return out, list(errors)
    except Exception as exc:
        return {}, [f'Birthdates: {type(exc).__name__}']


def fill_records(records, bmap):
    out = []
    for r in records or []:
        r = dict(r)
        d = norm_date(r.get(COLUMN)) or (bmap or {}).get(pid_key(r.get('Player ID')))
        r[COLUMN] = norm_date(d)
        out.append(r)
    return out


def missing(records):
    recs = [r for r in records or [] if norm_date(r.get(COLUMN)) is None]
    return (sorted({str(r.get('Team') or '').upper() for r in recs if r.get('Team')}),
            [pid_key(r.get('Player ID')) for r in recs if pid_key(r.get('Player ID'))])


def coverage(records):
    recs = list(records or [])
    return sum(norm_date(r.get(COLUMN)) is not None for r in recs), len(recs)


def fill_frame(frame, map_fn):
    """Render-time fallback for snapshots saved before the Birth date column. map_fn(teams, pids) -> {pid: date}.
    Unchanged frame when nothing is missing; never raises (on failure birthdates stay missing)."""
    try:
        import pandas as pd
        recs = frame.to_dict('records')
        teams, pids = missing(recs)
        if COLUMN in frame.columns and not pids:
            return frame
        try:
            bmap = map_fn(tuple(teams), tuple(pids)) if pids else {}
        except Exception:
            bmap = {}
        filled = fill_records(recs, bmap)
        out = frame.copy()
        out[COLUMN] = pd.Series([r[COLUMN] for r in filled], index=frame.index, dtype='object')
        return out
    except Exception:
        return frame


# ---------------------------------------------------------------- display
def tag(p):
    """Compact tag after the jersey: 'LP 41/5', or 'LP —' when missing; '' for legacy rows without the field."""
    if not isinstance(p, dict) or 'life_path' not in p:
        return ''
    c = tuple(p.get('life_path') or ())
    if not c:
        return '<span class="npr-lp none" title="Life Path unavailable (no birthdate)">LP —</span>'
    return f'<span class="npr-lp" title="Life Path (birthdate {html.escape(str(p.get("birth_date") or ""))})">LP {text(c)}</span>'


def day_values(entry):
    """[(label, chain_text, set_of_numbers)] from an entry's breakdown, e.g. ('Universal Day', '30/3', {30, 3})."""
    out = []
    for a, b in (entry or {}).get('breakdown') or ():
        nums = {int(x) for x in re.findall(r'\d+', str(b))}
        out.append((a, b, nums))
    return out


def matched_values(step, entry):
    """'Universal Day 30/3' style labels whose chain contains step; else 'pattern number n'."""
    hit = [f'{a} {b}' for a, b, nums in day_values(entry) if step in nums]
    return hit or [f'pattern number {step}']


def table_rows(slate_targets, entry):
    """Every slate player whose Life Path chain hits the entry's numbers (no top-N). -> (rows, n_players, n_missing)."""
    rows, seen, n, miss = [], set(), 0, 0
    for s in slate_targets or []:
        for t in list(s.get('away_targets') or []) + list(s.get('home_targets') or []):
            key = t.get('player_id') or (t.get('team'), str(t.get('player', '')).casefold())
            if key in seen:
                continue
            seen.add(key)
            n += 1
            c = tuple(t.get('life_path') or ())
            if not c:
                miss += 1
                continue
            hs = hits(c, entry.get('numbers'))
            if hs:
                v = t.get('values') or {}
                rows.append({'player': t.get('player', ''), 'team': t.get('team', ''), 'player_id': t.get('player_id', ''),
                             'jersey': t.get('jersey'), 'life_path': c, 'birth_date': t.get('birth_date'),
                             'steps': hs, 'matched': list(dict.fromkeys(m for s_ in hs for m in matched_values(s_, entry))),
                             'eng': v.get('ordinal'), 'eng_root': v.get('ordinal_root')})
    rows.sort(key=lambda r: (r['life_path'][-1], r['team'], r['player']))
    return rows, n, miss


TABLE_STYLE = ('<style>.num-lp{min-width:0;max-width:100%;box-sizing:border-box;overflow-wrap:anywhere;'
               'border:1px solid rgba(155,92,255,.3);background:linear-gradient(135deg,rgba(155,92,255,.09),rgba(0,229,255,.035))}'
               '.num-lp .lp-w{max-height:560px;overflow-y:auto;overflow-x:hidden}'
               '.num-lp table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:.85rem}'
               '.num-lp th{text-align:left;font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;color:#c9b6ff;padding:6px 6px;'
               'position:sticky;top:0;background:#141b2e}'
               '.num-lp td{padding:6px;border-top:1px solid rgba(155,92,255,.14);vertical-align:top;overflow-wrap:anywhere}'
               '.num-lp .lp-c{font-weight:700;color:#d9caff;font-variant-numeric:tabular-nums}'
               '.num-lp .lp-m{color:#c9b6ff;font-size:.8rem}.num-lp .lp-g{opacity:.85;font-size:.78rem;font-variant-numeric:tabular-nums}'
               '.num-lp .lp-note{font-size:.78rem;margin:8px 0 0;opacity:.8}.num-lp .lp-empty{padding:10px 0;opacity:.9}'
               '.num-lp th.lp-wp{width:30%}.num-lp th.lp-wt{width:12%}.num-lp th.lp-wl{width:16%}.num-lp th.lp-hg{width:16%}'
               '.num-lp .lp-sub{display:none;opacity:.8;font-size:.74rem}'
               '@media(max-width:600px){.num-lp th{letter-spacing:.02em;font-size:.66rem}.num-lp th.lp-wp{width:36%}.num-lp th.lp-wt{width:15%}.num-lp th.lp-wl{width:20%}.num-lp th.lp-hg,.num-lp td.lp-hg{display:none}.num-lp .lp-sub{display:block}'
               '.num-lp table{font-size:.8rem}}</style>')


def table_html(rows, entry, n_players, n_missing, loaded=True):
    e = lambda x: html.escape(str(x))
    nums = ', '.join(str(x) for x in entry.get('numbers') or ())
    head = (f'<div class="sh"><h3>Life Path matches · {e(entry.get("label", ""))}</h3><p>Every player on this slate whose Life Path '
            f'chain has a step in {e(entry.get("date", ""))}’s numbers ({e(nums)}) · read-only, not scoring</p></div>')
    if not loaded:
        body = '<p class="lp-empty">Life Path matches appear once this slate’s rankings are loaded.</p>'
    elif n_players and n_missing == n_players:
        body = '<p class="lp-empty">No birthdates are available for this slate yet, so no Life Path can match. Nothing is guessed.</p>'
    elif not rows:
        body = '<p class="lp-empty">No player’s Life Path matches today’s numbers.</p>'
    else:
        import jersey_v61 as _jy
        trs = ''.join(
            f'<tr><td><b>{e(r["player"])}</b>{_jy.tag(r)}<span class="lp-sub">Eng {e(r["eng"] if r["eng"] is not None else "—")} → '
            f'{e(r["eng_root"] if r["eng_root"] is not None else "—")}</span></td><td>{e(r["team"])}</td>'
            f'<td class="lp-c" title="Birthdate {e(r["birth_date"] or "")}">{e(text(r["life_path"]))}</td>'
            f'<td class="lp-m">{e("; ".join(r["matched"]))}<br><small>chain step{"s" if len(r["steps"]) != 1 else ""} hit: {e(" · ".join(str(s) for s in r["steps"]))}</small></td>'
            f'<td class="lp-g lp-hg">Eng {e(r["eng"] if r["eng"] is not None else "—")} → {e(r["eng_root"] if r["eng_root"] is not None else "—")}</td></tr>'
            for r in rows)
        body = ('<div class="lp-w"><table>'
                '<thead><tr><th class="lp-wp">Player</th><th class="lp-wt">Team</th><th class="lp-wl">Life Path</th><th>Matched day value</th><th class="lp-hg">Gematria</th></tr></thead>'
                f'<tbody>{trs}</tbody></table></div>')
    note = (f'{len(rows)} match{"es" if len(rows) != 1 else ""} · {n_players - n_missing} of {n_players} players have a birthdate'
            + (f' · {n_missing} without a birthdate (never match)' if n_missing else '')) if loaded else ''
    return (TABLE_STYLE + '<section class="sec num-lp" aria-label="Life Path matches">' + head + body
            + (f'<p class="lp-note">{e(note)}</p>' if note else '') + f'<p class="lp-note">{e(CAPTION)}</p></section>')
