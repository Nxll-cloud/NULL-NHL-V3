"""Daily number-pattern registry for the Numbers tab (display/filter only; never scoring input).

Add a day = append ONE JSON object to patterns/daily_number_patterns.json, e.g.
{"date": "2026-11-10", "label": "Nov 10 pattern", "numbers": [2, 20, 11], "note": "optional literal text",
 "breakdown": [["Universal Day", "30/3"], ["Month", "11"]]}
Saved numbers are kept literally (0 explicit, no digit transforms); saved note/breakdown are user text.
Dates with no saved entry get an auto-computed pattern (see compute() below); a saved entry overrides it.
Bad entries are skipped with a warning; the rest still load.
"""
from datetime import date as _date
from pathlib import Path
import json
import math
import re

REGISTRY = Path(__file__).resolve().parent / 'patterns' / 'daily_number_patterns.json'
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
RULE = ('A row matches a selected pattern when the player’s English root (values.ordinal_root, 1–9) OR full '
        'unreduced English ordinal total (values.ordinal) exactly equals one of its numbers. No Reverse, '
        'digit transforms or date mapping; 10, 11, 21, 30 are kept literally. 0 matches only an explicit stored 0; '
        'missing/unknown values never match.')
NOT_TESTED = ('Display/filter only, not a forecast. These daily patterns are not backtested; the saved historical '
              'audit covers only the original reference groups.')


def validate(raw):
    """-> (entries, warnings). Never raises on bad entries."""
    entries, warnings, seen = [], [], set()
    if not isinstance(raw, list):
        return [], ['Daily pattern registry must be a JSON list; no daily patterns loaded.']
    for i, e in enumerate(raw, 1):
        where = f'Daily pattern entry #{i}'
        if not isinstance(e, dict):
            warnings.append(f'{where} skipped: not an object.'); continue
        d = e.get('date')
        try:
            ok = isinstance(d, str) and bool(_DATE.match(d)) and _date.fromisoformat(d).isoformat() == d
        except ValueError:
            ok = False
        if not ok:
            warnings.append(f'{where} skipped: date must be YYYY-MM-DD.'); continue
        if d in seen:
            warnings.append(f'{where} skipped: duplicate date {d}.'); continue
        label = e.get('label')
        if not isinstance(label, str) or not label.strip():
            warnings.append(f'{where} ({d}) skipped: label must be non-empty text.'); continue
        nums = e.get('numbers')
        if not isinstance(nums, list) or not nums or any(isinstance(n, bool) or not isinstance(n, int) for n in nums):
            warnings.append(f'{where} ({d}) skipped: numbers must be a non-empty list of whole numbers.'); continue
        if len(set(nums)) != len(nums):
            warnings.append(f'{where} ({d}) skipped: repeated number in list.'); continue
        note = e.get('note')
        if note is not None and (not isinstance(note, str) or not note.strip()):
            warnings.append(f'{where} ({d}) skipped: note must be text when present.'); continue
        bd = e.get('breakdown')
        if bd is not None and (not isinstance(bd, list) or any(not isinstance(x, list) or len(x) != 2
                               or not all(isinstance(s, str) and s.strip() for s in x) for x in bd)):
            warnings.append(f'{where} ({d}) skipped: breakdown must be [["Label", "value"], ...] text pairs.'); continue
        unknown = set(e) - {'date', 'label', 'numbers', 'note', 'breakdown'}
        if unknown:
            warnings.append(f'{where} ({d}): ignored unknown field(s) {", ".join(sorted(unknown))}.')
        seen.add(d)
        entries.append({'date': d, 'label': label.strip(), 'numbers': tuple(nums), 'note': note,
                        'breakdown': tuple((a, b) for a, b in bd) if bd else ()})
    entries.sort(key=lambda x: x['date'])
    return entries, warnings


def load(path=None):
    try:
        raw = json.loads(Path(path or REGISTRY).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return [], [f'Daily pattern registry unreadable ({type(exc).__name__}); no daily patterns loaded.']
    return validate(raw)


def _whole(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if math.isfinite(f) and f.is_integer() else None


def fields(p):
    v = p.get('values') or {}
    total = v.get('ordinal') if v.get('ordinal') is not None else p.get('eng_total')
    return _whole(v.get('ordinal_root')), _whole(total)


def matches(p, entries):
    """-> list of (entry, 'English root = n' | 'English total = n') for every selected entry hit."""
    root, total = fields(p)
    out = []
    for e in entries:
        why = [f'English root = {root}'] if root is not None and root in e['numbers'] else []
        if total is not None and total in e['numbers']:
            why.append(f'English total = {total}')
        if why:
            out.append((e, ' & '.join(why)))
    return out


def reason(p, entries):
    hits = matches(p, entries)
    return '; '.join(f'{why} · {e["label"]} ({e["date"]})' for e, why in hits) or None


def toggle_key(day, entry_date):
    return f'v60_number_overlay:{day}:{entry_date}'


# ---- Auto-computed daily patterns (t198): every date gets a pattern; explicit registry entries override. ----
# Formula derived from the user's Nov 9 2026 breakdown (reproduces 1, 3, 9, 10, 11, 21, 30 exactly):
#   yearSum = digit sum of YYYY (2026 -> 10)
#   Universal Year  = yearSum              shown with its reduction chain, e.g. '10/1'
#   Universal Month = M + yearSum          e.g. Nov 2026 -> '21/3'
#   Universal Day   = M + D + yearSum      e.g. Nov 9 -> '30/3'; Nov 17 -> '38/11/2'
#   Calendar Day    = D                    '9', or '17/8' when D > 9
#   Month           = M as written         '11' (NOT reduced: the user's Nov 9 list has 11 but not 2)
# Numbers = sorted unique set of every value in the UD, UM, UY and Calendar Day chains, plus M.
# Chains reduce by digit sum until one digit and keep EVERY step (38 -> 11 -> 2 contributes 38, 11 and 2).
AUTO_NOTE = 'auto-computed from date formula'
FORMULA = ('Auto days: yearSum = digits of the year added (2026 → 10). Universal Year = yearSum; Universal Month = month + yearSum; '
           'Universal Day = month + day + yearSum; Calendar Day = day; Month = month as written. Each value is shown with every '
           'digit-sum step to one digit (38/11/2), and all of those steps plus the month are the numbers to look for. '
           'Reproduces your Nov 9 list exactly. A saved entry for a date replaces the formula for that date.')
_WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _dsum(n):
    return sum(int(c) for c in str(abs(int(n))))


def chain(n):
    """Every digit-sum step down to one digit: 38 -> (38, 11, 2); 30 -> (30, 3); 9 -> (9,)."""
    out = [int(n)]
    while out[-1] > 9:
        out.append(_dsum(out[-1]))
    return tuple(out)


def _fmt(c):
    return '/'.join(str(x) for x in c)


def compute(d):
    """Formula entry for a datetime.date (or ISO string). Same shape as registry entries plus source='auto'."""
    if isinstance(d, str):
        d = _date.fromisoformat(d)
    y, m, day = _dsum(d.year), d.month, d.day
    uy, um, ud, cd = chain(y), chain(m + y), chain(m + day + y), chain(day)
    nums = tuple(sorted(set(ud) | set(um) | set(uy) | set(cd) | {m}))
    return {'date': d.isoformat(), 'label': f'{_MONTHS[m - 1]} {day} pattern', 'numbers': nums, 'note': AUTO_NOTE,
            'breakdown': (('Universal Day', _fmt(ud)), ('Universal Month', _fmt(um)), ('Calendar Day', _fmt(cd)),
                          ('Universal Year', _fmt(uy)), ('Month', str(m))), 'source': 'auto'}


def entry_for(d, explicit=()):
    """Explicit registry entry for that date if one exists (overrides), else the auto-computed one."""
    iso = d if isinstance(d, str) else d.isoformat()
    for e in explicit:
        if e['date'] == iso:
            return dict(e, source='saved')
    return compute(iso)


def today_et():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('America/New_York')).date()


def week_of(d):
    """Mon..Sun dates of the week containing d."""
    from datetime import timedelta
    mon = d - timedelta(days=d.weekday())
    return [mon + timedelta(days=i) for i in range(7)]


def day_label(d):
    return f'{_WEEKDAYS[d.weekday()]} {d.day}'


def picker_key(day, kind):
    return f'v60_daily_pick:{day}:{kind}'


def applied_key(day):
    """Per-slate set of applied pattern dates (union filter)."""
    return f'v60_daily_applied:{day}'
