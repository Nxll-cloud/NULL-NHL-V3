"""V6.1 multi-book odds board (Odds tab). Display only: no model, ranking or scoring changes.

Same prop or game line across sportsbooks side by side (one row per line, one column per book), modeled on how
simpleodds.app lays out odds.

Data (no new provider for props):
  * Player props: the app's existing shared quotes (The Odds API anytime-goal fetch, 30-min QuoteCache, and/or the
    uploaded CSV, per the Odds source setting). Default view = the Home price-gap scope (9b53945): tonight's slate,
    pre-game, Yes side of anytime goal, no line, mapped to a unique slate game (home_pricegap_v61).
  * Game lines (moneyline, puck line, total): fetched ONLY when a game-line market is selected, through the same
    QuoteCache (30 min healthy). The Odds API: one bulk /sports/icehockey_nhl/odds call for all events
    (markets=h2h,spreads,totals, region us; documented cost 1 credit per market per region = ~3 credits per refresh,
    cheaper than adding the markets to every per-event call). SportsGameOdds (only with SGO_API_KEY): documented
    /v2/events filtered to the six full-game oddIDs, header x-api-key, cached 30 min. Books from both are merged; when
    the same book appears in both, the most recently updated price wins.
  * A second The Odds API key (ODDS_API_KEY_2 / _BACKUP / ...) is a failover: used only when the primary key is
    rejected (401/403) or out of quota (429). Key values are never shown, logged or cached by value.

Cents: American odds mapped to a continuous scale where +100 and -100 are the same point (even money):
  s(a) = a - 100 for a >= +100,  s(a) = a + 100 for a <= -100.
  cents between two prices = |s(a) - s(b)|.  -110 vs -115 = 5 cents; -110 vs +110 = 20 cents; -105 vs +105 = 10.
  Row spread = max(s) - min(s) over the books quoting that row. Higher American price = better for the bettor
  on both sides of even money, so best = max(s), worst = min(s). Cents are linear in American points, so long-shot
  props (+300 and up) naturally show bigger cent spreads than lines near even money.
  TIGHT = 2+ books and spread < tight threshold (default 5). DISCREPANCY = 2+ books and spread > discrepancy
  threshold (default 20).
"""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import html
import math
import re

import pandas as pd
import requests

import edgelab_prices_v60 as elp
import home_pricegap_v61 as hpg
from odds_api_v45 import BASE, OddsFeedError, _items, _valid_price
from v55_ui import game_state

TIGHT_DEFAULT, DISC_DEFAULT = 5, 20
GAME_MARKETS = 'h2h,spreads,totals'
SGO_BASE = 'https://api.sportsgameodds.com/v2'
SGO_ODD_IDS = ('points-home-game-ml-home', 'points-away-game-ml-away', 'points-home-game-sp-home',
               'points-away-game-sp-away', 'points-all-game-ou-over', 'points-all-game-ou-under')
PREFERRED = ('FanDuel', 'DraftKings', 'BetMGM', 'Caesars', 'Fanatics')
BOOK_NAMES = {'fanduel': 'FanDuel', 'draftkings': 'DraftKings', 'betmgm': 'BetMGM', 'caesars': 'Caesars',
              'williamhillus': 'Caesars', 'williamhill': 'Caesars', 'fanatics': 'Fanatics', 'espnbet': 'ESPN BET',
              'thescorebet': 'ESPN BET', 'betrivers': 'BetRivers', 'bovada': 'Bovada', 'betonlineag': 'BetOnline.ag',
              'betonline': 'BetOnline.ag', 'mybookieag': 'MyBookie.ag', 'lowvig': 'LowVig.ag', 'betus': 'BetUS',
              'ballybet': 'Bally Bet', 'hardrockbet': 'Hard Rock Bet', 'pinnacle': 'Pinnacle', 'circasports': 'Circa Sports',
              'betparx': 'betPARX', 'fliff': 'Fliff', 'pointsbetus': 'PointsBet', 'unibetus': 'Unibet', 'wynnbet': 'WynnBET',
              'superbook': 'SuperBook', 'novig': 'Novig', 'prophetexchange': 'ProphetX', 'betway': 'Betway'}
MARKET_FILTERS = ('Anytime goal (Yes)', 'All player props', 'Moneyline', 'Puck line', 'Total', 'All game lines', 'Everything')
LINE_FILTERS = {'Moneyline': ('Moneyline',), 'Puck line': ('Puck line',), 'Total': ('Total',),
                'All game lines': ('Moneyline', 'Puck line', 'Total'), 'Everything': ('Moneyline', 'Puck line', 'Total')}
FLAG_FILTERS = ('All', 'Tight', 'Discrepancy')
LINE_LABELS = {'h2h': 'Moneyline', 'spreads': 'Puck line', 'totals': 'Total'}
CAPTION = ('Cents: American odds on one continuous scale where +100 = -100 (even money); -110 vs -115 = 5¢, -110 vs +110 = 20¢. '
           'Spread = best minus worst price in cents across the books on that row. TIGHT = 2+ books under the tight threshold; '
           'DISCREPANCY = 2+ books above the discrepancy threshold. Best = highest payout for the bettor. Display only: not a '
           'model signal, not expected value; prices can be stale between 30-minute refreshes.')


# ------------------------------------------------------------------ cents math

def american(value):
    """int American price or None (rejects bools, NaN, inf, strings that are not numbers, and (-100, 100))."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(str(value).strip().replace('\u2212', '-')) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or not (n >= 100 or n <= -100):
        return None
    return int(round(n))


def cents_scale(price):
    """Continuous cents scale: +100 and -100 both map to 0. -110 -> -10, +110 -> +10."""
    a = american(price)
    if a is None:
        return None
    return a - 100 if a >= 100 else a + 100


def cents_gap(a, b):
    sa, sb = cents_scale(a), cents_scale(b)
    return None if sa is None or sb is None else abs(sa - sb)


def spread_cents(prices):
    vals = [s for s in (cents_scale(p) for p in prices) if s is not None]
    return (max(vals) - min(vals)) if len(vals) >= 2 else None


def flag(spread, n_books, tight=TIGHT_DEFAULT, disc=DISC_DEFAULT):
    """'tight' | 'disc' | '' (needs 2+ books)."""
    if spread is None or n_books < 2:
        return ''
    if spread < tight:
        return 'tight'
    if spread > disc:
        return 'disc'
    return ''


def best_worst(prices):
    """{book: price} -> (best books, worst books); empty sets when fewer than 2 books or all prices equal."""
    sc = {b: cents_scale(p) for b, p in prices.items()}
    sc = {b: s for b, s in sc.items() if s is not None}
    if len(sc) < 2 or max(sc.values()) == min(sc.values()):
        return set(), set()
    hi, lo = max(sc.values()), min(sc.values())
    return {b for b, s in sc.items() if s == hi}, {b for b, s in sc.items() if s == lo}


def book_name(value):
    k = re.sub(r'[^a-z0-9]', '', str(value or '').casefold())
    return BOOK_NAMES.get(k) or str(value or '').strip()


# ------------------------------------------------------------------ fetchers (game lines)

def _get(session, url, params, headers, timeout, provider):
    try:
        r = session.get(url, params=params, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise OddsFeedError(f'{provider} request timed out.', code='timeout') from None
    except requests.RequestException:
        raise OddsFeedError(f'Could not reach {provider}.', code='network') from None
    if r.status_code in (401, 403):
        raise OddsFeedError(f'{provider} rejected credentials or market access (401/403).', code='auth')
    if r.status_code == 429:
        raise OddsFeedError(f'{provider} rate limit or quota reached (429).', code='quota')
    if r.status_code != 200:
        raise OddsFeedError(f'{provider} returned HTTP {r.status_code}.', code='unavailable')
    try:
        return r.json()
    except ValueError:
        raise OddsFeedError(f'{provider} returned malformed JSON.', code='malformed') from None


COLUMNS = ['event_id', 'player', 'team', 'market', 'selection', 'line', 'sportsbook', 'american_odds', 'updated_at',
           'home_team', 'away_team', 'commence_time', 'source']


def _frame(rows, status):
    f = pd.DataFrame(rows, columns=COLUMNS)
    f.attrs['feed_status'] = status
    return f


def fetch_game_lines(api_key, *, regions='us', markets=GAME_MARKETS, timeout=12, session=None, event_cache=None, keep_event=None):
    """The Odds API bulk NHL odds (h2h / spreads / totals) in the shared quote schema (player = '').
    One request for all events. Signature matches fetch_odds so QuoteCache.get can cache it."""
    if api_key is not None and not isinstance(api_key, str):
        raise OddsFeedError('ODDS_API_KEY must be a string in top-level Streamlit secrets.', code='configuration')
    if not api_key or not api_key.strip():
        raise OddsFeedError('No API key configured. Add ODDS_API_KEY to Streamlit secrets or upload CSV.', code='missing_key')
    if any(m not in LINE_LABELS for m in str(markets).split(',')):
        raise OddsFeedError('Invalid markets configuration')
    s = session or requests.Session()
    data = _get(s, BASE + '/sports/icehockey_nhl/odds', {'regions': regions, 'markets': markets, 'oddsFormat': 'american',
                                                          'dateFormat': 'iso', 'apiKey': api_key}, None, timeout, 'The Odds API')
    if not isinstance(data, list):
        raise OddsFeedError('Invalid event list from provider', code='malformed')
    rows, fetched = [], datetime.now(timezone.utc).isoformat()
    for ev in _items(data):
        eid = str(ev.get('id') or '').strip()
        if not eid or (keep_event is not None and not keep_event(ev)):
            continue
        home, away = str(ev.get('home_team') or ''), str(ev.get('away_team') or '')
        for book in _items(ev.get('bookmakers')):
            for m in _items(book.get('markets')):
                key = str(m.get('key') or '')
                if key not in LINE_LABELS:
                    continue
                for o in _items(m.get('outcomes')):
                    name, price, point = str(o.get('name') or '').strip(), o.get('price'), o.get('point')
                    updated = m.get('last_update') or book.get('last_update')
                    if not name or not _valid_price(price) or not updated or (key != 'h2h' and point is None):
                        continue
                    rows.append({'event_id': eid, 'player': '', 'team': name if key != 'totals' else '', 'market': key,
                                 'selection': name, 'line': '' if point is None else str(point),
                                 'sportsbook': str(book.get('title') or book.get('key') or ''), 'american_odds': int(price),
                                 'updated_at': updated, 'home_team': home, 'away_team': away,
                                 'commence_time': str(ev.get('commence_time') or ''), 'source': 'The Odds API'})
    return _frame(rows, {'state': 'ok' if rows else 'empty', 'provider': 'The Odds API', 'events': len(data),
                         'event_requests': 1, 'issues': {}, 'quotes': len(rows), 'fetched_at': fetched}), []


def fetch_sgo_lines(api_key, *, timeout=12, session=None, max_pages=3):
    """SportsGameOdds (documented v2 /events) NHL full-game moneyline / spread / total per bookmaker, unstarted
    events only, in the shared quote schema. Header auth (x-api-key), so the key never appears in a URL."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise OddsFeedError('No SGO_API_KEY configured.', code='missing_key')
    s = session or requests.Session()
    params = {'leagueID': 'NHL', 'started': 'false', 'oddsAvailable': 'true', 'oddID': ','.join(SGO_ODD_IDS), 'limit': 50}
    rows, events, pages, cursor = [], 0, 0, None
    while pages < max_pages:
        data = _get(s, SGO_BASE + '/events', dict(params, **({'cursor': cursor} if cursor else {})),
                    {'x-api-key': api_key.strip()}, timeout, 'SportsGameOdds')
        pages += 1
        if not isinstance(data, dict) or not isinstance(data.get('data'), list):
            raise OddsFeedError('SportsGameOdds returned an invalid event list.', code='malformed')
        for ev in _items(data['data']):
            events += 1
            rows.extend(_sgo_rows(ev))
        cursor = data.get('nextCursor')
        if not cursor or not data['data']:
            break
    return _frame(rows, {'state': 'ok' if rows else 'empty', 'provider': 'SportsGameOdds', 'events': events,
                         'event_requests': pages, 'issues': {}, 'quotes': len(rows),
                         'fetched_at': datetime.now(timezone.utc).isoformat()})


def _sgo_rows(ev):
    st = ev.get('status') if isinstance(ev.get('status'), dict) else {}
    if st.get('started') or st.get('ended') or st.get('cancelled') or st.get('live'):
        return []
    teams = ev.get('teams') if isinstance(ev.get('teams'), dict) else {}
    nm = lambda side: ((teams.get(side) or {}).get('names') or {}) if isinstance(teams.get(side), dict) else {}
    home, away = nm('home').get('long') or nm('home').get('short') or '', nm('away').get('long') or nm('away').get('short') or ''
    out = []
    odds = ev.get('odds') if isinstance(ev.get('odds'), dict) else {}
    for oid in SGO_ODD_IDS:
        o = odds.get(oid)
        if not isinstance(o, dict) or o.get('started') or o.get('ended') or o.get('cancelled'):
            continue
        stat, ent, period, bet, side = oid.split('-')
        market = {'ml': 'h2h', 'sp': 'spreads', 'ou': 'totals'}[bet]
        for bk, q in (o.get('byBookmaker') or {}).items() if isinstance(o.get('byBookmaker'), dict) else ():
            if not isinstance(q, dict) or q.get('available') is False:
                continue
            price = american(q.get('odds'))
            line = q.get('spread') if bet == 'sp' else q.get('overUnder') if bet == 'ou' else None
            if price is None or (bet != 'ml' and american_line(line) is None):
                continue
            sel = (home if side == 'home' else away) if bet != 'ou' else side.title()
            out.append({'event_id': 'sgo:' + str(ev.get('eventID') or ''), 'player': '', 'team': sel if bet != 'ou' else '',
                        'market': market, 'selection': sel, 'line': '' if line is None else str(american_line(line)),
                        'sportsbook': book_name(bk), 'american_odds': price,
                        'updated_at': q.get('lastUpdatedAt') or st.get('startsAt') or '', 'home_team': home, 'away_team': away,
                        'commence_time': str(st.get('startsAt') or ''), 'source': 'SportsGameOdds'})
    return out


def american_line(value):
    try:
        v = float(str(value).replace('\u2212', '-'))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def key_id(value):
    """Short non-reversible id for cache identities (never the key itself)."""
    return sha256(str(value or '').encode()).hexdigest()[:16]


def with_failover(get, keys, *args):
    """get(key, *args) with [(key, where), ...]; the next key is tried only on auth/quota errors.
    -> (result, where_used). Re-raises the last error when every key fails."""
    last = None
    for i, (key, where) in enumerate([k for k in keys if k and k[0]]):
        try:
            return get(key, *args), where
        except OddsFeedError as exc:
            last = exc
            if exc.code not in ('auth', 'quota'):
                raise
    if last is not None:
        raise last
    raise OddsFeedError('No API key configured.', code='missing_key')


# ------------------------------------------------------------------ normalize + rows

def _fmt_line(v, signed):
    f = american_line(v)
    if f is None:
        return ''
    s = f'{f:g}'
    return ('+' + s if f > 0 else s) if signed else s


def normalize(quotes, games, day, now=None, market_filter=MARKET_FILTERS[0]):
    """Shared-schema quotes -> canonical rows for the board, scoped to the slate date, unstarted games.
    -> (list of dicts, report)."""
    now = now or datetime.now(timezone.utc)
    report = {'received': len(quotes) if isinstance(quotes, pd.DataFrame) else 0, 'excluded': Counter()}
    out = []
    if not isinstance(quotes, pd.DataFrame) or quotes.empty:
        return out, report
    slate = hpg._slate_games(games)
    want_lines = LINE_FILTERS.get(market_filter, ())
    want_props = market_filter in ('Anytime goal (Yes)', 'All player props', 'Everything')
    for q in quotes.to_dict('records'):
        mk = elp.text(q.get('market'))
        is_line = mk in LINE_LABELS and not elp.text(q.get('player'))
        if is_line and LINE_LABELS[mk] not in want_lines:
            continue
        if not is_line and not want_props:
            continue
        price = american(q.get('american_odds'))
        book = book_name(q.get('sportsbook'))
        if price is None or not book:
            report['excluded']['invalid price or book'] += 1
            continue
        anytime = elp.name_key(mk) in hpg.ANYTIME
        sel = elp.text(q.get('selection'))
        if not is_line:
            if market_filter == 'Anytime goal (Yes)' and not anytime:
                continue
            if anytime and (sel.casefold() != 'yes' or elp.ident(q.get('line'))):
                report['excluded']['not the Yes side of anytime goal'] += 1
                continue
            if not elp.text(q.get('player')):
                report['excluded']['no player name'] += 1
                continue
        s, reason = hpg._map(q, slate, day)
        if reason:
            report['excluded'][reason] += 1
            continue
        if game_state(s['game'], now) != 'pre':
            report['excluded']['game started or final'] += 1
            continue
        if is_line:
            market = LINE_LABELS[mk]
            if mk == 'totals':
                label, order = f'{sel.title()} {_fmt_line(q.get("line"), False)}', (2, sel.casefold() != 'over', american_line(q.get('line')) or 0)
            else:
                code = hpg._team(sel) or sel.upper()
                if code not in (s['away'], s['home']):
                    report['excluded']['line team not in this game'] += 1
                    continue
                side = 0 if code == s['away'] else 1
                label = f'{code} ML' if mk == 'h2h' else f'{code} {_fmt_line(q.get("line"), True)}'
                order = (0 if mk == 'h2h' else 1, side, american_line(q.get('line')) or 0)
            line = elp.text(q.get('line'))
        else:
            mname = 'Anytime goal' if anytime else (elp.text(mk).replace('player_', '').replace('_', ' ').title())
            market = mname
            ln = elp.text(q.get('line'))
            label = elp.text(q.get('player')) + ('' if anytime else f' · {sel}{" " + ln if ln else ""}')
            order = (3, mname, elp.name_key(q.get('player')), sel.casefold(), american_line(ln) or 0)
            line = ln
        out.append({'game_key': s['key'], 'away': s['away'], 'home': s['home'], 'start': s['game'].get('start') or s['game'].get('Start (UTC)'),
                    'kind': 'line' if is_line else 'prop', 'market': market, 'label': label, 'order': order,
                    'ident': (s['key'], market, label.casefold(), line), 'book': book, 'price': price,
                    'updated': elp.text(q.get('updated_at')), 'source': elp.text(q.get('source')) or 'CSV'})
    report['excluded'] = dict(report['excluded'])
    return out, report


def build_rows(canon, tight=TIGHT_DEFAULT, disc=DISC_DEFAULT):
    """Canonical rows -> board rows (one per identical line), newest price per book wins."""
    groups = {}
    for c in canon:
        g = groups.setdefault(c['ident'], {'c': c, 'prices': {}, 'when': {}, 'src': {}})
        w = pd.to_datetime(c['updated'], utc=True, errors='coerce')
        w = None if pd.isna(w) else w
        old = g['when'].get(c['book'], 'missing')
        if old == 'missing' or (w is not None and (old is None or w > old)):
            g['prices'][c['book']], g['when'][c['book']], g['src'][c['book']] = c['price'], w, c['source']
    rows = []
    for g in groups.values():
        c, prices = g['c'], g['prices']
        sp = spread_cents(prices.values())
        best, worst = best_worst(prices)
        rows.append({'game_key': c['game_key'], 'away': c['away'], 'home': c['home'], 'start': c['start'], 'kind': c['kind'],
                     'market': c['market'], 'label': c['label'], 'order': c['order'], 'prices': prices, 'sources': g['src'],
                     'n': len(prices), 'spread': sp, 'flag': flag(sp, len(prices), tight, disc), 'best': best, 'worst': worst})
    rows.sort(key=lambda r: (str(r['start'] or ''), r['game_key'], r['order'], r['label']))
    return rows


def books(rows):
    """Preferred books first (FanDuel, DraftKings, BetMGM, Caesars, Fanatics) when quoted, then others by row count."""
    cnt = Counter(b for r in rows for b in r['prices'])
    return [b for b in PREFERRED if b in cnt] + sorted((b for b in cnt if b not in PREFERRED), key=lambda b: (-cnt[b], b))


def filter_rows(rows, flag_filter='All', search=''):
    want = {'Tight': 'tight', 'Discrepancy': 'disc'}.get(flag_filter)
    q = str(search or '').strip().casefold()
    out = []
    for r in rows:
        if want and r['flag'] != want:
            continue
        if q:
            names = ' '.join([r['away'], r['home'], f"{r['away']}@{r['home']}", f"{r['away']} @ {r['home']}", r['label'],
                              elp.TEAM_NAMES.get(r['away'], ''), elp.TEAM_NAMES.get(r['home'], '')]).casefold()
            if q not in names:
                continue
        out.append(r)
    return out


# ------------------------------------------------------------------ empty states

def empty_reason(market_filter, source, has_key, live_error, shared_error, quotes, report, games, now=None, lines_error=None,
                 n_rows_unfiltered=0):
    """(title, body) when the board has no rows; reuses the Home price-gap reasons for the prop feed."""
    now = now or datetime.now(timezone.utc)
    slate = [g for g in (games or []) if isinstance(g, dict)]
    if not slate:
        return 'No games on this slate', 'There are no NHL games on the selected date, so there is nothing to compare.'
    if all(game_state(g, now) != 'pre' for g in slate):
        return 'Every game has started', 'All of tonight’s games have started or finished; the board compares pre-game prices only.'
    if n_rows_unfiltered:
        return 'No lines match these filters', 'Try All, a lower tight threshold or a higher discrepancy threshold, or clear the search.'
    lines = market_filter in LINE_FILTERS
    if lines and lines_error:
        return 'Game lines unavailable', f'{lines_error} No prices are shown; nothing is invented.'
    if lines and not has_key:
        return hpg.empty_reason('Automatic API', False, None, None, pd.DataFrame(), {}, pd.DataFrame(), False)
    if not lines:
        t, b = hpg.empty_reason(source, has_key, live_error, shared_error, quotes, report, None, False)
        if t == 'No pre-game price gap tonight':
            return ('No comparable prices', 'No line on tonight’s unstarted games has a price at a sportsbook yet.'
                    + (b.split('books.', 1)[1] if 'books.' in b else ''))
        if t:
            return t, b
    ex = (report or {}).get('excluded') or {}
    detail = '; '.join(f'{k} ({v})' for k, v in sorted(ex.items(), key=lambda kv: -kv[1])[:3])
    return 'No comparable prices', 'The feed has no prices for this market on tonight’s unstarted games.' + (f' Excluded: {detail}.' if detail else '')


# ------------------------------------------------------------------ html

def _p(a):
    return f'+{a}' if a > 0 else str(a)


def _time(iso):
    t = elp.stamp(iso)
    if t is None:
        return ''
    t = t.tz_convert(elp.ET)
    return t.strftime('%-I:%M %p ET')


def table_html(rows, book_cols, tight=TIGHT_DEFAULT, disc=DISC_DEFAULT, empty=None, note=''):
    e = lambda x: html.escape(str(x))
    legend = ('<div class="obd-leg"><span class="obd-k best">Best price</span><span class="obd-k worst">Worst price</span>'
              f'<span class="obd-f tight">TIGHT &lt; {e(tight)}¢</span><span class="obd-f disc">DISCREPANCY &gt; {e(disc)}¢</span>'
              '<span class="obd-k na">— no price</span></div>')
    head = ('<div class="sh"><h3>Multi-book odds board</h3><p>Same line, every book, side by side · '
            'pre-game, tonight’s slate · display only</p></div>')
    if empty:
        body = f'<div class="obd-empty"><b>{e(empty[0])}</b><p>{e(empty[1])}</p></div>'
    else:
        ncol = len(book_cols) + 2
        th = ''.join(f'<th class="obd-b">{e(b)}</th>' for b in book_cols)
        trs, last = [], None
        for r in rows:
            if r['game_key'] != last:
                last = r['game_key']
                trs.append(f'<tr class="obd-g"><th class="obd-s" scope="rowgroup">{e(r["away"])} @ {e(r["home"])}'
                           f'<small>{e(_time(r["start"]))}</small></th><td colspan="{ncol - 1}"></td></tr>')
            cells = []
            for b in book_cols:
                if b not in r['prices']:
                    cells.append('<td class="obd-na">—</td>')
                    continue
                cls = 'best' if b in r['best'] else 'worst' if b in r['worst'] else ''
                cells.append(f'<td class="{cls}" title="{e(b)} · {e(r["sources"].get(b, ""))}">{e(_p(r["prices"][b]))}</td>')
            fl = {'tight': '<span class="obd-f tight">TIGHT</span>', 'disc': '<span class="obd-f disc">DISCREPANCY</span>'}.get(r['flag'], '')
            sp = '—' if r['spread'] is None else f'{r["spread"]}¢'
            trs.append(f'<tr class="obd-r {e(r["flag"])}"><th class="obd-s" scope="row"><span class="obd-l">{e(r["label"])}</span>'
                       f'<small>{e(r["market"])} · {r["n"]} book{"s" if r["n"] != 1 else ""}</small></th>{"".join(cells)}'
                       f'<td class="obd-sp">{e(sp)}{fl}</td></tr>')
        body = (f'<div class="obd-w"><table class="obd-t"><thead><tr><th class="obd-s">Line</th>{th}<th class="obd-sp">Spread</th></tr></thead>'
                f'<tbody>{"".join(trs)}</tbody></table></div>')
    return (f'<section class="sec v61-obd" aria-label="Multi-book odds board">{head}{legend}{body}'
            + (f'<p class="obd-note">{e(note)}</p>' if note else '') + f'<p class="obd-note">{e(CAPTION)}</p></section>')


def sgo_for_cache(api_key, regions=None, markets=None, event_cache=None, keep_event=None):
    """fetch_sgo_lines with the fetch_odds signature, so the shared QuoteCache (30 min healthy, short error cooldowns)
    can hold it under its own identity (regions='sgo')."""
    return fetch_sgo_lines(api_key), []


def load_lines(cache_get, primary, extra):
    """Game-line quotes from every configured source. cache_get(fetch, key, regions, markets) -> (frame, warnings).
    -> (frame, notes, error). The Odds API: primary key, backup on auth/quota. SportsGameOdds: merged when keyed."""
    frames, notes, errors = [], [], []
    keys = [(primary, 'primary ODDS_API_KEY')] + ([(extra['backup'][0], 'backup Odds API key')] if (extra or {}).get('backup') else [])
    if any(k for k, _ in keys):
        try:
            (f, _w), used = with_failover(lambda k: cache_get(fetch_game_lines, k, 'us', GAME_MARKETS), keys)
            frames.append(f)
            notes.append(f'The Odds API ({used}): {len(f)} quotes')
        except OddsFeedError as exc:
            errors.append(f'The Odds API: {exc.safe_message}')
    if (extra or {}).get('sgo'):
        try:
            f, _w = cache_get(sgo_for_cache, extra['sgo'][0], 'sgo', 'lines')
            frames.append(f)
            notes.append(f'SportsGameOdds: {len(f)} quotes')
        except OddsFeedError as exc:
            errors.append(f'SportsGameOdds: {exc.safe_message}')
    frames = [f for f in frames if isinstance(f, pd.DataFrame) and not f.empty]
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    return frame, notes, ('; '.join(errors) if errors and frame.empty else None)
