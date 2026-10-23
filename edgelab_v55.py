"""V5.5 EdgeLab: a research prototype that compares a *model probability* with a sportsbook price.

Pure functions first (tested in test_edgelab_v55.py), then the Streamlit view (render_edgelab).

Data honesty
------------
* The Games and Props lists are DEMO DATA (hard-coded prices and probabilities from the original
  standalone prototype). They are badged "DEMO DATA — not live prices" everywhere they appear.
* When real prices are loaded (Odds API via Streamlit secrets, or the CSV upload on the Odds tab) the user may
  pick one, but the model probability must be typed in by the user. Nothing here derives a probability from
  Form %: Form % is a relative form index, not a probability.
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
KELLY_FRACTION = 0.25
BANKROLL_MIN, BANKROLL_MAX, BANKROLL_DEFAULT, BANKROLL_STEP = 500, 50000, 2500, 100
EDGE_MIN, EDGE_MAX, EDGE_DEFAULT, EDGE_STEP = 1.0, 12.0, 4.0, 0.5
EPS = 1e-9
DEMO_BADGE = 'DEMO DATA — not live prices'
REAL_BADGE = 'REAL PRICE · your probability'
DISCLAIMER = 'Mobile research prototype. Not betting advice.'
RESEARCH_NOTE = 'Research only, not betting advice. Edge = model probability − sportsbook implied probability; stake = ¼-Kelly.'

# --- demo data: unchanged from the pasted prototype (team codes added only for colours) ---------------------
DEMO_GAMES = [
    {'game': 'EDM @ CGY', 'pick': 'EDM ML', 'odds': -140, 'model_p': 0.61, 'book': 'DraftKings', 'team': 'EDM'},
    {'game': 'EDM @ CGY', 'pick': 'Over 6.5', 'odds': -115, 'model_p': 0.56, 'book': 'FanDuel', 'team': 'CGY'},
    {'game': 'TOR @ BOS', 'pick': 'BOS ML', 'odds': -155, 'model_p': 0.64, 'book': 'BetMGM', 'team': 'BOS'},
    {'game': 'COL @ DAL', 'pick': 'COL -1.5', 'odds': 145, 'model_p': 0.42, 'book': 'Caesars', 'team': 'COL'},
]
DEMO_PROPS = [
    {'player': 'C. McDavid', 'pick': 'Over 1.5 Points', 'odds': -130, 'model_p': 0.62, 'book': 'DraftKings', 'team': 'EDM'},
    {'player': 'A. Matthews', 'pick': 'Over 0.5 Goals', 'odds': 100, 'model_p': 0.51, 'book': 'FanDuel', 'team': 'TOR'},
    {'player': 'N. MacKinnon', 'pick': 'Over 3.5 Shots', 'odds': -105, 'model_p': 0.58, 'book': 'BetMGM', 'team': 'COL'},
]

# --- session / widget namespacing ---------------------------------------------------------------------------
K_STAMPED = 'edgelab_stamped'
K_BANKROLL = 'edgelab_bankroll'
K_MIN_EDGE = 'edgelab_min_edge'
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


def kelly(p, odds, bankroll, fraction=KELLY_FRACTION):
    """Fractional-Kelly stake. Never negative, never above the bankroll, rounded to cents."""
    p = validate_probability(p)
    b = net_payout(odds)
    if not _is_number(bankroll) or bankroll < 0:
        raise EdgeLabError(f'bankroll must be a non-negative number, got {bankroll!r}')
    if not _is_number(fraction) or not 0 <= fraction <= 1:
        raise EdgeLabError(f'Kelly fraction must be in [0, 1], got {fraction!r}')
    k = (b * p - (1 - p)) / b
    stake = k * fraction * float(bankroll)
    return round_half_up(min(max(0.0, stake), float(bankroll)), 2)


def edge_pct(p, odds):
    """Edge in percentage points (signed)."""
    return (validate_probability(p) - american_to_implied(odds)) * 100


def process(rows, bankroll=BANKROLL_DEFAULT, min_edge=EDGE_DEFAULT, fraction=KELLY_FRACTION):
    """Score bets. Returns (kept, skipped).

    kept: rows with edge ≥ min_edge, enriched with edge (2 dp, signed), stake, model % and implied % (1 dp),
    sorted by edge descending (stable). skipped: [(row, reason)] for invalid odds / probabilities."""
    kept, skipped = [], []
    for row in rows or []:
        try:
            p = validate_probability(row.get('model_p'))
            imp = american_to_implied(row.get('odds'))
        except EdgeLabError as exc:
            skipped.append((row, str(exc)))
            continue
        raw = (p - imp) * 100
        if raw + EPS < float(min_edge):
            continue
        kept.append({**row, 'edge': round_half_up(raw, 2), 'stake': kelly(p, row['odds'], bankroll, fraction),
                     'model_pct': round_half_up(p * 100, 1), 'implied_pct': round_half_up(imp * 100, 1)})
    kept.sort(key=lambda r: -r['edge'])
    return kept, skipped


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


def score_real(bet, prob_pct, bankroll):
    """User-entered probability (in %, 0-100 exclusive) applied to a real price. Raises EdgeLabError."""
    if prob_pct is None:
        raise EdgeLabError('enter your own probability for this price')
    p = validate_probability(float(prob_pct) / 100)
    imp = american_to_implied(bet['odds'])
    return {**bet, 'model_p': p, 'edge': round_half_up((p - imp) * 100, 2), 'stake': kelly(p, bet['odds'], bankroll),
            'model_pct': round_half_up(p * 100, 1), 'implied_pct': round_half_up(imp * 100, 1)}


def teams_of(bet):
    t = bet.get('team')
    g = bet.get('game') or ''
    m = re.match(r'\s*([A-Z]{2,3})\s*@\s*([A-Z]{2,3})', g)
    if m:
        return m.group(1), m.group(2)
    return (t, t) if t else (None, None)


# ============================================================================== Streamlit view

def _factory(st):
    return st.session_state.get('_edgelab_conn_factory')


def _with_conn(st, fn, *args):
    """Open a fresh connection per operation (Streamlit reruns may run on another thread)."""
    conn = _factory(st)()
    try:
        return fn(conn, *args)
    finally:
        conn.close()


def _on_stamp(kind, bet, source, now_fn):
    import streamlit as st
    bankroll = st.session_state.get(K_BANKROLL, BANKROLL_DEFAULT)
    stamp = make_stamp(kind, bet, bankroll, now=now_fn(), source=source)
    st.session_state[K_STAMPED], added = add_stamp(st.session_state.get(K_STAMPED, []), stamp)
    if added and st.session_state.get(K_PERSIST) and _factory(st) is not None:
        try:
            _with_conn(st, db_save, stamp)
        except Exception as exc:  # persistence is optional; session stamps still work
            st.session_state['edgelab_persist_error'] = f'{type(exc).__name__}: {exc}'


def _on_remove(key):
    import streamlit as st
    st.session_state[K_STAMPED] = remove_stamp(st.session_state.get(K_STAMPED, []), key)
    if st.session_state.get(K_PERSIST) and _factory(st) is not None:
        try:
            _with_conn(st, db_delete, key)
        except Exception:
            pass


def _on_clear():
    import streamlit as st
    st.session_state[K_STAMPED] = []
    if st.session_state.get(K_PERSIST) and _factory(st) is not None:
        try:
            _with_conn(st, db_clear)
        except Exception:
            pass


def _on_persist():
    """Turning persistence on mid-session: merge stored stamps and save the session's existing ones."""
    import streamlit as st
    if not st.session_state.get(K_PERSIST) or _factory(st) is None:
        return
    try:
        merged = merge_stamps(st.session_state.get(K_STAMPED, []), _with_conn(st, db_load))
        for s in merged:
            _with_conn(st, db_save, s)
        st.session_state[K_STAMPED] = merged
        st.session_state['_edgelab_loaded'] = True
        st.session_state.pop('edgelab_persist_error', None)
    except Exception as exc:
        st.session_state['edgelab_persist_error'] = f'{type(exc).__name__}: {exc}'


def _bet_card(st, ui5, kind, bet, stamps, source, now_fn, badge_text):
    key = bet_key(kind, bet)
    a, h = teams_of(bet)
    with st.container(border=True):
        st.markdown(ui5.bet_head(bet_name(bet), badge_text, a, h, bet['edge']), unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.metric('Edge', fmt_edge(bet['edge']))
        c2.metric('Stake', fmt_money(bet['stake']))
        st.caption(f"{caption(bet)} · implied {bet['implied_pct']:.1f}%")
        done = is_stamped(stamps, key)
        st.button('✓ Stamped' if done else 'Stamp', key=f'edgelab_stamp_{key}', disabled=done,
                  on_click=_on_stamp, args=(kind, bet, source, now_fn), use_container_width=True)


def _bet_list(st, ui5, kind, rows, bankroll, min_edge, stamps, now_fn):
    kept, skipped = process(rows, bankroll, min_edge)
    st.markdown(ui5.chip_row([(DEMO_BADGE, 'demo'), (f'{len(kept)} of {len(rows)} clear {min_edge:.1f}%', 'neon')]), unsafe_allow_html=True)
    if not kept:
        near = all_edges(rows)[:3]
        st.markdown(ui5.empty_state('No edge clears the threshold',
                                    f'Nothing reaches {min_edge:.1f}% at these prices. Closest: ' +
                                    (', '.join(f"{bet_name(r)} {fmt_edge(r['edge'])}" for r in near) or 'none') +
                                    '. Lower Min Edge % to inspect them.', '◎'), unsafe_allow_html=True)
    for bet in kept:
        _bet_card(st, ui5, kind, bet, stamps, 'demo', now_fn, DEMO_BADGE)
    for row, why in skipped:
        st.caption(f'Skipped {bet_name(row)}: {why}')


def render_edgelab(quotes=None, now_fn=None, conn_factory=None):
    """Render the EdgeLab tab. quotes: validated price rows (the app's shared odds frame) or None.
    now_fn: clock (tests); conn_factory: () -> sqlite3 connection for optional persistence."""
    import streamlit as st
    import v55_ui as ui5
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    st.session_state.setdefault(K_STAMPED, [])

    st.markdown(ui5.tab_head('EdgeLab · research prototype', 'EdgeLab',
                             'Model probability vs sportsbook price · ¼-Kelly sizing · stamp ideas to a scorecard',
                             [(DEMO_BADGE, 'demo'), ('Research only · not betting advice', 'warn')], logo=True), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    bankroll = c1.number_input('Bankroll ($)', min_value=BANKROLL_MIN, max_value=BANKROLL_MAX, value=BANKROLL_DEFAULT,
                               step=BANKROLL_STEP, key=K_BANKROLL)
    min_edge = c2.slider('Min Edge %', min_value=EDGE_MIN, max_value=EDGE_MAX, value=EDGE_DEFAULT, step=EDGE_STEP, key=K_MIN_EDGE)

    # optional persistence: merge stored stamps once per session when switched on
    st.session_state['_edgelab_conn_factory'] = conn_factory
    if st.session_state.get(K_PERSIST) and conn_factory is not None:
        try:
            if not st.session_state.get('_edgelab_loaded'):
                st.session_state[K_STAMPED] = merge_stamps(st.session_state[K_STAMPED], _with_conn(st, db_load))
                st.session_state['_edgelab_loaded'] = True
        except Exception as exc:
            st.session_state['edgelab_persist_error'] = f'{type(exc).__name__}: {exc}'
    stamps = st.session_state[K_STAMPED]

    g_tab, p_tab, s_tab = st.tabs(['Games', 'Props', f'Scorecard ({len(stamps)})'])
    with g_tab:
        _bet_list(st, ui5, 'game', DEMO_GAMES, bankroll, min_edge, stamps, now_fn)
    with p_tab:
        _bet_list(st, ui5, 'prop', DEMO_PROPS, bankroll, min_edge, stamps, now_fn)
        opts = quote_options(quotes)
        st.markdown(ui5.sec_head('Your price, your probability', 'Pick a loaded sportsbook price and type your own probability. Form % is never used as a probability.'), unsafe_allow_html=True)
        if not opts:
            st.markdown(ui5.empty_state('No real prices loaded', 'Add ODDS_API_KEY to Streamlit secrets or upload a CSV on the Odds tab. Demo bets above stay demo.', '$'), unsafe_allow_html=True)
        else:
            labels = [f"{o['player']} · {o['pick']} · {o['book']} {fmt_odds(o['odds'])}" for o in opts]
            ix = st.selectbox('Loaded price', range(len(opts)), format_func=lambda i: labels[i], key='edgelab_real_pick')
            prob = st.number_input('Your probability (%)', min_value=0.1, max_value=99.9, value=None, step=0.5,
                                   key='edgelab_real_prob', placeholder='Type your own estimate')
            if prob is None:
                st.info('Enter your own probability to score this price. EdgeLab does not invent one.')
            else:
                try:
                    bet = score_real(opts[ix], prob, bankroll)
                except EdgeLabError as exc:
                    st.warning(str(exc))
                else:
                    _bet_card(st, ui5, 'real', bet, stamps, 'real price · user probability', now_fn, REAL_BADGE)
    with s_tab:
        tot = scorecard_totals(stamps)
        st.markdown(ui5.kpi_strip([('Stamped', str(tot['count']), 'neon'), ('Total stake', fmt_money(tot['staked']), 'ok'),
                                   ('Average edge', fmt_edge(tot['avg_edge']) if tot['avg_edge'] is not None else '—', 'stat')]), unsafe_allow_html=True)
        if not stamps:
            st.markdown(ui5.empty_state('No stamps yet', 'Tap Stamp on a Games or Props card to log it here with the time you stamped it.', '✎'), unsafe_allow_html=True)
        for s in scorecard_rows(stamps):
            with st.container(border=True):
                cA, cB = st.columns([5, 1])
                cA.markdown(ui5.stamp_row(s, fmt_edge(s['edge']), fmt_money(s['stake']), fmt_odds(s['odds'])), unsafe_allow_html=True)
                cB.button('Remove', key=f"edgelab_rm_{s['key']}", on_click=_on_remove, args=(s['key'],), use_container_width=True)
        if stamps:
            d1, d2 = st.columns(2)
            d1.download_button('Export CSV', stamps_csv(stamps), file_name='edgelab_scorecard.csv', mime='text/csv',
                               key='edgelab_export', use_container_width=True)
            d2.button('Clear all', key='edgelab_clear', on_click=_on_clear, use_container_width=True)
        tog = st.toggle if hasattr(st, 'toggle') else st.checkbox
        tog('Save stamps to the local tracker database', key=K_PERSIST, on_change=_on_persist,
            help='Off by default: stamps live in this browser session only. On: also stored in the tracker SQLite (edgelab_stamps table).')
        if st.session_state.get('edgelab_persist_error'):
            st.caption('Persistence unavailable: ' + st.session_state['edgelab_persist_error'] + ' — session stamps still work.')
    st.caption(RESEARCH_NOTE)
    st.markdown(ui5.foot(DISCLAIMER), unsafe_allow_html=True)
