"""V5.5 EdgeLab: a research prototype that compares a *model probability* with a sportsbook price.

Pure functions (tested in test_edgelab_v55.py).

Data honesty
------------
* V5.8: no DEMO prices, no manual probability entry, no bankroll / Kelly sizing. What remains here is the pure
  price math (american_to_implied, validation, formatting) and the stamp / SQLite helpers (kept so stored stamps
  survive). The EdgeLab tab itself is edgelab_v58 (next-goal model p vs live prices, read-only).
* Nothing here derives a probability from Form %: Form % is a relative form index, not a probability.
* Research only. Not betting advice.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
EPS = 1e-9
DISCLAIMER = 'Mobile research prototype. Not betting advice.'
RESEARCH_NOTE = 'Research only, not betting advice. Edge = model probability − sportsbook implied probability.'

# --- session / widget namespacing ---------------------------------------------------------------------------
K_STAMPED = 'edgelab_stamped'
K_PERSIST = 'edgelab_persist'


class EdgeLabError(ValueError):
    """Invalid odds or probability."""


# ============================================================================== pure functions

def round_half_up(x, dp=2):
    """Consistent rounding for money and percentages (half away from zero, no float artefacts)."""
    q = Decimal(1).scaleb(-dp)
    d = Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP)
    return float(d)


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def validate_odds(odds):
    """American odds must be finite numbers with |odds| >= 100. (-100, 100), including 0, is not a price."""
    if not _is_number(odds):
        raise EdgeLabError(f'odds must be a finite number, got {odds!r}')
    if -100 < float(odds) < 100:
        raise EdgeLabError(f'American odds must be ≤ -100 or ≥ +100, got {odds!r}')
    return float(odds)


def validate_probability(p):
    """Model probability must be a finite number strictly between 0 and 1."""
    if not _is_number(p):
        raise EdgeLabError(f'model probability must be a finite number, got {p!r}')
    if not 0 < float(p) < 1:
        raise EdgeLabError(f'model probability must be strictly between 0 and 1, got {p!r}')
    return float(p)


def american_to_implied(odds):
    """Sportsbook implied probability (0-1) of American odds. Same formula as the prototype, plus validation."""
    odds = validate_odds(odds)
    return 100 / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)


def net_payout(odds):
    """b: profit per 1 unit staked."""
    odds = validate_odds(odds)
    return odds / 100 if odds > 0 else 100 / abs(odds)


def edge_pct(p, odds):
    """Edge in percentage points (signed)."""
    return (validate_probability(p) - american_to_implied(odds)) * 100


def all_edges(rows):
    """Signed edge for every valid row (used for the 'closest to the threshold' empty state)."""
    out = []
    for row in rows or []:
        try:
            out.append({**row, 'edge': round_half_up(edge_pct(row.get('model_p'), row.get('odds')), 2)})
        except EdgeLabError:
            continue
    return sorted(out, key=lambda r: -r['edge'])


# --- formatting --------------------------------------------------------------------------------------------

def fmt_edge(edge):
    return f'{edge:+.2f}%'


def fmt_odds(odds):
    o = int(round(float(odds)))
    return f'+{o}' if o > 0 else str(o)


def fmt_money(x):
    return f'${x:,.2f}'


def caption(bet):
    """'book · odds · model %' exactly as the prototype, with a correctly signed price."""
    return f"{bet['book']} · {fmt_odds(bet['odds'])} · model {bet['model_pct']:.1f}%"


# --- keys & stamps -----------------------------------------------------------------------------------------

def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-') or 'x'


def bet_key(kind, bet):
    """Stable, unique key: kind | game-or-player | pick | book (odds/probability excluded so edits keep the key)."""
    who = bet.get('game') or bet.get('player') or ''
    return '_'.join(_slug(x) for x in (kind, who, bet.get('pick', ''), bet.get('book', '')))


def bet_name(bet):
    who = bet.get('player') or bet.get('game') or ''
    return f"{who} · {bet.get('pick', '')}".strip(' ·')


def now_et(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ET)


def make_stamp(kind, bet, bankroll, now=None, source='demo'):
    t = now_et(now)
    return {'key': bet_key(kind, bet), 'kind': kind, 'name': bet_name(bet), 'pick': bet.get('pick'),
            'book': bet.get('book'), 'odds': float(bet['odds']), 'model_p': float(bet['model_p']),
            'edge': bet['edge'], 'stake': bet['stake'], 'bankroll': float(bankroll), 'source': source,
            'stamped_at': t.isoformat(timespec='seconds'), 'stamped_label': t.strftime('%b %-d, %-I:%M %p ET')}


def add_stamp(stamps, stamp):
    """Append unless the same bet key is already stamped. Returns (new_list, added)."""
    stamps = list(stamps or [])
    if any(s.get('key') == stamp['key'] for s in stamps):
        return stamps, False
    return stamps + [stamp], True


def remove_stamp(stamps, key):
    return [s for s in (stamps or []) if s.get('key') != key]


def is_stamped(stamps, key):
    return any(s.get('key') == key for s in (stamps or []))


def scorecard_rows(stamps):
    """Newest first, like the prototype."""
    return list(reversed(list(stamps or [])))


def scorecard_totals(stamps):
    stamps = list(stamps or [])
    staked = round_half_up(sum(float(s.get('stake') or 0) for s in stamps), 2)
    avg = round_half_up(sum(float(s.get('edge') or 0) for s in stamps) / len(stamps), 2) if stamps else None
    return {'count': len(stamps), 'staked': staked, 'avg_edge': avg}


STAMP_FIELDS = ['stamped_at', 'kind', 'name', 'pick', 'book', 'odds', 'model_p', 'edge', 'stake', 'bankroll', 'source', 'key']


def stamps_csv(stamps):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=STAMP_FIELDS, extrasaction='ignore')
    w.writeheader()
    for s in stamps or []:
        w.writerow(s)
    return buf.getvalue()


# --- optional SQLite persistence (tracker DB) --------------------------------------------------------------
_DDL = '''CREATE TABLE IF NOT EXISTS edgelab_stamps(
 key TEXT PRIMARY KEY, stamped_at TEXT NOT NULL, payload TEXT NOT NULL)'''


def db_init(conn):
    conn.execute(_DDL)
    conn.commit()


def db_save(conn, stamp):
    db_init(conn)
    conn.execute('INSERT OR IGNORE INTO edgelab_stamps(key, stamped_at, payload) VALUES (?,?,?)',
                 (stamp['key'], stamp['stamped_at'], json.dumps(stamp, sort_keys=True)))
    conn.commit()


def db_load(conn):
    db_init(conn)
    return [json.loads(r[0]) for r in conn.execute('SELECT payload FROM edgelab_stamps ORDER BY stamped_at, key')]


def db_delete(conn, key):
    db_init(conn)
    conn.execute('DELETE FROM edgelab_stamps WHERE key=?', (key,))
    conn.commit()


def db_clear(conn):
    db_init(conn)
    conn.execute('DELETE FROM edgelab_stamps')
    conn.commit()


def merge_stamps(session, stored):
    out = list(session or [])
    for s in stored or []:
        out, _ = add_stamp(out, s)
    return sorted(out, key=lambda s: s.get('stamped_at') or '')


# --- real prices (user supplies the probability) -----------------------------------------------------------

def quote_options(quotes):
    """Valid loaded price rows -> list of bet dicts without a probability. Invalid prices are skipped."""
    if quotes is None or getattr(quotes, 'empty', True):
        return []
    out, seen = [], set()
    for r in quotes.to_dict('records'):
        try:
            odds = validate_odds(float(r.get('american_odds')))
        except (EdgeLabError, TypeError, ValueError):
            continue
        pick = ' '.join(str(x) for x in (r.get('selection') or 'Yes', r.get('market') or '') if x).strip()
        bet = {'player': str(r.get('player') or ''), 'pick': pick, 'odds': odds, 'book': str(r.get('sportsbook') or ''),
               'team': str(r.get('team') or '')}
        k = bet_key('real', bet)
        if k in seen or not bet['player'] or not bet['book']:
            continue
        seen.add(k)
        out.append(bet)
    return out


def teams_of(bet):
    t = bet.get('team')
    g = bet.get('game') or ''
    m = re.match(r'\s*([A-Z]{2,3})\s*@\s*([A-Z]{2,3})', g)
    if m:
        return m.group(1), m.group(2)
    return (t, t) if t else (None, None)


# ============================================================================== Streamlit view
# V5.8: the V5.5 view (bankroll input, Min Edge slider, DEMO Games/Props, manual "your probability", Stamp buttons and
# the Scorecard sub-tab) was removed. EdgeLab is now the read-only edgelab_v58 view (model p vs live prices).
# The stamp helpers and the edgelab_stamps SQLite functions above are kept unchanged so stored stamps are not lost.
