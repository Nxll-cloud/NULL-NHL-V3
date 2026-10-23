"""V5.9 Projected scorers (odds): sportsbook anytime-goal prices -> no-vig implied chance -> ranked per game and slate.

Odds only: this section never mixes in the app's model chance (it is a market view, shown on its own).

Source order (first one with prices wins; the label + timestamps are always shown):
  1. The Odds API (``player_goal_scorer_anytime``, US books incl. FanDuel / DraftKings) - only when ODDS_API_KEY is set
     in Streamlit secrets. It REUSES the quotes app.py already fetches for the Odds tab (``np_live_odds_cached``,
     30-minute cache), so this section makes no extra Odds API calls. Cost on The Odds API: 1 credit per event per
     region per market (events list is free), i.e. ~N games credits per refresh.
  2. ESPN's free public feed (DraftKings 'Anytime Goalscorer' prop prices, one book): scoreboard -> per-game propBets +
     2 team rosters for names. Cached 30 minutes by the app.
  3. Nothing -> an empty state. Never demo data dressed as real (``demo`` is always False here).
OddsJam is a paid, key-gated product: not used and never scraped.

Vig removal: the anytime market is one-sided (only 'Yes' prices are posted), so a per-player two-way devig is
impossible, and a game's scorer list does not sum to a known total (it is the expected number of distinct scorers).
We use a documented FIXED margin: fair = implied x FAIR_FACTOR, FAIR_FACTOR = 0.86, the observed hit-rate / implied
ratio on 4,958 real DraftKings anytime props (2025-26 + Oct 2026, /workspace/edgelab_backtest: 15.0% scored vs 17.5%
average implied). The same factor is applied to every book (an approximation; books' margins differ a little).
Consensus = median no-vig chance across books; also mean, best price (highest payout) + book, and every book's price.
"""
from __future__ import annotations

import html as _html
import math
import re
import statistics
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

FAIR_FACTOR = 0.86
METHOD_NOTE = ('No-vig % = implied chance × 0.86 (fixed margin; the anytime market only posts “Yes” prices, so a '
               'per-player devig is impossible; 0.86 = real scoring rate ÷ implied on 4,958 DraftKings props). '
               'Consensus = median across books.')
SOURCE_API, SOURCE_ESPN = 'The Odds API', 'ESPN (DraftKings)'
MARKET = 'player_goal_scorer_anytime'
BOOK_ORDER = ('FanDuel', 'DraftKings')
BOOK_SHORT = {'FanDuel': 'FD', 'DraftKings': 'DK', 'BetMGM': 'MGM', 'Caesars': 'CZR', 'BetRivers': 'BR', 'ESPN BET': 'ESPN',
              'Fanatics': 'FAN', 'Bovada': 'BOV', 'BetOnline.ag': 'BOL', 'Hard Rock Bet': 'HR'}
ESPN_SB = 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={}'
ESPN_ROSTER = 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/{}/roster'
ESPN_PROPS = ('https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/events/{0}/competitions/{0}/odds/100/'
              'propBets?limit=1000')
ESPN_ABBR = {'TB': 'TBL', 'LA': 'LAK', 'SJ': 'SJS', 'NJ': 'NJD', 'UTAH': 'UTA', 'WAS': 'WSH', 'MON': 'MTL'}


# ------------------------------------------------------------------------------------------------ prices
def parse_american(v):
    """'+285' / 285 / '-120' / 'EVEN' -> int, else None (|price| < 100, NaN, bools rejected)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        s = v.strip().upper().replace('−', '-')
        if s in ('EVEN', 'EV'):
            return 100
        try:
            v = float(s)
        except ValueError:
            return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or -100 < f < 100:
        return None
    return int(round(f))


def implied(american):
    a = parse_american(american)
    if a is None:
        return None
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def decimal(american):
    a = parse_american(american)
    if a is None:
        return None
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / -a


def no_vig(p, factor=FAIR_FACTOR):
    return None if p is None else min(max(p * factor, 0.0), 1.0)


def price_label(a):
    a = parse_american(a)
    return '—' if a is None else (f'+{a}' if a > 0 else str(a))


def book_name(b):
    s = re.sub(r'[^a-z]', '', str(b or '').lower())
    return {'fanduel': 'FanDuel', 'draftkings': 'DraftKings', 'betmgm': 'BetMGM', 'williamhillus': 'Caesars',
            'caesars': 'Caesars', 'betrivers': 'BetRivers', 'espnbet': 'ESPN BET', 'fanatics': 'Fanatics'}.get(s, str(b or '').strip())


def norm_name(n):
    s = unicodedata.normalize('NFKD', str(n or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z ]', '', s.replace('-', ' '))
    return ' '.join(w for w in s.split() if w not in ('jr', 'sr', 'ii', 'iii'))


# ------------------------------------------------------------------------------------------------ aggregation
def aggregate(quotes):
    """quotes [{player, team, game, book, american, updated, pid?, position?}] -> one row per (game, player):
    {player, team, game, pid, position, books {book: american}, implied {book: p}, consensus, mean, raw_consensus,
    best {'book','american'}, n_books, updated}. Same-book duplicates keep the latest/higher price."""
    groups = {}
    for q in quotes or []:
        a = parse_american(q.get('american'))
        name = str(q.get('player') or '').strip()
        if a is None or not name:
            continue
        key = (q.get('game') or '', q.get('pid') or norm_name(name))
        g = groups.setdefault(key, {'player': name, 'team': q.get('team') or '', 'game': q.get('game') or '',
                                    'pid': q.get('pid') or '', 'position': q.get('position') or '', 'books': {}, 'updated': ''})
        b = book_name(q.get('book'))
        if b not in g['books'] or decimal(a) > decimal(g['books'][b]):
            g['books'][b] = a
        g['updated'] = max(g['updated'], str(q.get('updated') or ''))
        for k in ('team', 'pid', 'position'):
            g[k] = g[k] or q.get(k) or ''
    rows = []
    for g in groups.values():
        imp = {b: implied(a) for b, a in g['books'].items()}
        fair = [no_vig(p) for p in imp.values()]
        best_b = max(g['books'], key=lambda b: (decimal(g['books'][b]), b in BOOK_ORDER, b))
        rows.append({**g, 'books': dict(sorted(g['books'].items(), key=lambda kv: _book_rank(kv[0]))), 'implied': imp,
                     'consensus': statistics.median(fair), 'mean': statistics.fmean(fair),
                     'raw_consensus': statistics.median(imp.values()),
                     'best': {'book': best_b, 'american': g['books'][best_b]}, 'n_books': len(g['books'])})
    return rank(rows)


def _book_rank(b):
    return (BOOK_ORDER.index(b) if b in BOOK_ORDER else len(BOOK_ORDER), b)


def rank(rows, n=None):
    out = sorted(rows, key=lambda r: (-r['consensus'], -r['n_books'], -decimal(r['best']['american']), norm_name(r['player'])))
    return out[:n] if n else out


def by_game(rows, n=None):
    games = {}
    for r in rows:
        games.setdefault(r['game'], []).append(r)
    return {g: rank(v, n) for g, v in games.items()}


# ------------------------------------------------------------------------------------------------ slate mapping
def slate_index(games, rankings):
    """Snapshot games + ranking rows -> lookups used to attach team / game / NHL id / position to provider names."""
    from home_leaders_v52 import TEAM_NAMES
    full = {v.lower(): k for k, v in TEAM_NAMES.items()}
    full.update({'utah hockey club': 'UTA', 'st. louis blues': 'STL', 'montréal canadiens': 'MTL'})
    gl = {}
    for g in games or []:
        a, h = str(g.get('Away') or ''), str(g.get('Home') or '')
        if a and h:
            gl[a] = gl[h] = f'{a} @ {h}'
    people = {}
    for r in rankings or []:
        t = str(r.get('Team') or '')
        k = norm_name(r.get('Player'))
        if not k:
            continue
        pid = r.get('Player ID')
        try:
            pid = str(int(float(pid)))
        except (TypeError, ValueError):
            pid = ''
        people.setdefault(k, []).append({'team': t, 'pid': pid, 'position': r.get('Position') or '', 'player': r.get('Player')})
    return {'full': full, 'game_of': gl, 'people': people}


def _attach(q, idx, teams=()):
    """Fill team / pid / position / game from the slate's ranking rows (name match, restricted to the game's teams)."""
    cands = idx['people'].get(norm_name(q['player'])) or []
    if teams:
        cands = [c for c in cands if c['team'] in teams] or ([] if q.get('team') else cands)
    if len(cands) == 1:
        c = cands[0]
        q.update(team=c['team'], pid=c['pid'], position=q.get('position') or c['position'])
    if not q.get('game') and q.get('team'):
        q['game'] = idx['game_of'].get(q['team'], '')
    return q


def quotes_from_odds_api(df, idx):
    """odds_api_v45.fetch_odds frame -> quotes ('Yes' anytime outcomes only)."""
    out = []
    if df is None or getattr(df, 'empty', True):
        return out
    for r in df.to_dict('records'):
        if str(r.get('market') or '') != MARKET or str(r.get('selection') or '').strip().lower() != 'yes':
            continue
        a, h = idx['full'].get(str(r.get('away_team') or '').lower()), idx['full'].get(str(r.get('home_team') or '').lower())
        game = f'{a} @ {h}' if a and h else ''
        if a and h and idx['game_of'] and game not in set(idx['game_of'].values()):
            continue   # an event that is not on this slate (another day)
        out.append(_attach({'player': r.get('player'), 'team': '', 'game': game, 'book': r.get('sportsbook'),
                            'american': r.get('american_odds'), 'updated': r.get('updated_at')}, idx, (a, h) if a else ()))
    return out


def fetch_espn(day, idx, getter=None, timeout=12, workers=6):
    """Free ESPN DraftKings anytime props for ``day`` (YYYY-MM-DD) -> (quotes, warnings). Never raises."""
    import requests
    get = getter or requests.get
    warnings = []

    def j(url):
        try:
            r = get(url, timeout=timeout, headers={'User-Agent': 'NullsPlaybook/5.9'})
            if getattr(r, 'status_code', 200) != 200:
                return None
            return r.json()
        except Exception:   # offline / blocked / malformed: degrade to no data
            return None
    sb = j(ESPN_SB.format(str(day).replace('-', '')))
    events = []
    for e in (sb or {}).get('events') or []:
        try:
            c = e['competitions'][0]
            t = {x['homeAway']: x['team'] for x in c['competitors']}
            ab = {k: ESPN_ABBR.get(v.get('abbreviation'), v.get('abbreviation')) for k, v in t.items()}
            events.append({'id': str(e['id']), 'away': ab['away'], 'home': ab['home'],
                           'team_ids': {str(v['id']): ab[k] for k, v in t.items() if v.get('id')}})
        except (KeyError, IndexError, TypeError, AttributeError):
            continue
    if not events:
        return [], (['ESPN scoreboard unavailable'] if sb is None else [])
    team_ids = {k: v for e in events for k, v in e['team_ids'].items()}
    with ThreadPoolExecutor(workers) as ex:
        props = list(ex.map(lambda e: j(ESPN_PROPS.format(e['id'])), events))
        rosters = dict(zip(team_ids, ex.map(lambda t: j(ESPN_ROSTER.format(t)), team_ids)))
    ath = {}
    for tid, ro in rosters.items():
        for grp in (ro or {}).get('athletes') or []:
            for a in (grp.get('items') if isinstance(grp, dict) else None) or []:
                if isinstance(a, dict) and a.get('id'):
                    ath[str(a['id'])] = {'name': a.get('fullName') or a.get('displayName'), 'team': team_ids[tid],
                                         'position': (a.get('position') or {}).get('abbreviation', '')}
    out = []
    for e, pb in zip(events, props):
        if pb is None:
            warnings.append(f"{e['away']} @ {e['home']}: no props")
            continue
        for it in pb.get('items') or []:
            try:
                if (it.get('type') or {}).get('name') != 'Anytime Goalscorer':
                    continue
                aid = re.search(r'/athletes/(\d+)', it['athlete']['$ref']).group(1)
            except (KeyError, AttributeError, TypeError):
                continue
            a = ath.get(aid)
            if not a or not a.get('name'):
                continue   # athlete not on either listed roster: unidentifiable, skipped
            out.append(_attach({'player': a['name'], 'team': a['team'], 'game': f"{e['away']} @ {e['home']}", 'book': 'DraftKings',
                                'american': ((it.get('odds') or {}).get('american') or {}).get('value'),
                                'updated': it.get('lastUpdated') or '', 'position': a['position']}, idx, (e['away'], e['home'])))
    return out, warnings


def load(day, games, rankings, api_quotes=None, espn_fetch=None, now=None):
    """Source order The Odds API -> ESPN (DraftKings) -> nothing. ``espn_fetch(day, idx)`` returns (quotes, warnings)
    (the app passes a cached wrapper). Returns {source, rows, fetched_at, updated, books, warnings, demo: False}."""
    now = now or datetime.now(timezone.utc)
    idx = slate_index(games, rankings)
    base = {'day': day, 'fetched_at': now.isoformat(timespec='seconds'), 'demo': False, 'warnings': []}
    q = quotes_from_odds_api(api_quotes, idx)
    if q:
        return _done({**base, 'source': SOURCE_API}, q)
    try:
        q, w = (espn_fetch or (lambda d, i: fetch_espn(d, i)))(day, idx)
    except Exception as exc:   # pragma: no cover - fetch_espn never raises; a wrapper might
        q, w = [], [f'ESPN: {type(exc).__name__}']
    base['warnings'] = list(w or [])
    if q:
        return _done({**base, 'source': SOURCE_ESPN}, q)
    return {**base, 'source': None, 'rows': [], 'updated': '', 'books': []}


def _done(d, quotes):
    rows = aggregate(quotes)
    return {**d, 'rows': rows, 'updated': max((r['updated'] for r in rows), default=''),
            'books': sorted({b for r in rows for b in r['books']}, key=_book_rank)}


# ------------------------------------------------------------------------------------------------ HTML (shared by Home + Odds)
def _when(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    except ValueError:
        return ''
    return t.astimezone(timezone.utc).strftime('%b %d · %H:%M UTC')


def _row(i, r):
    import position_badge_v59 as pb
    e = _html.escape
    books = ' '.join(f'<span class="os-b{" best" if b == r["best"]["book"] else ""}" title="{e(b)}: implied {r["implied"][b] * 100:.1f}%">'
                     f'{e(BOOK_SHORT.get(b, b))} {e(price_label(a))}</span>' for b, a in r['books'].items())
    return (f'<li class="os-r"><span class="os-i">{i}</span><div class="os-id"><b>{e(r["player"])}{pb.goalie_badge(r.get("position"))}</b>'
            f'<small>{e(r["team"] or "—")} · {e(r["game"] or "game ?")}</small><div class="os-bk">{books}</div></div>'
            f'<div class="os-p" title="Raw implied (median) {r["raw_consensus"] * 100:.1f}% · mean no-vig {r["mean"] * 100:.1f}%">'
            f'<b>{r["consensus"] * 100:.0f}%</b><small>best {e(price_label(r["best"]["american"]))} {e(BOOK_SHORT.get(r["best"]["book"], r["best"]["book"]))}</small></div></li>')


def section_html(data, limit=10, per_game=True, hint=''):
    """Projected scorers (odds) card. ``limit`` slate-wide rows; ``per_game`` adds tap-to-open per-game lists (Odds tab).
    Home uses limit=5, per_game=False and a hint to the Odds tab. Same columns everywhere."""
    e = _html.escape
    head = ('<div class="sh"><h3>Projected scorers (odds)</h3><p>Anytime-goal prices from sportsbooks → no-vig chance · '
            'market view only, not the model</p></div>')
    rows = (data or {}).get('rows') or []
    if not rows:
        why = 'No sportsbook anytime-goal prices are available right now (no Odds API key configured and the free DraftKings feed returned nothing).'
        if (data or {}).get('source') is None and (data or {}).get('warnings'):
            why += ' ' + e('; '.join(data['warnings'][:2]))
        return f'<section class="sec v59-os empty">{head}<div class="os-empty">{e(why)}</div></section>'
    src = e(data['source']) + (f' · {len(data["books"])} books' if len(data['books']) > 1 else ' · DraftKings only')
    meta = (f'<p class="os-src"><span class="os-tag">{src}</span> prices updated {e(_when(data["updated"]) or "—")} · '
            f'fetched {e(_when(data["fetched_at"]))}</p>')
    top = ''.join(_row(i, r) for i, r in enumerate(rank(rows, limit), 1))
    games = ''
    if per_game:
        for g, rs in by_game(rows).items():
            games += (f'<details class="os-g"><summary>{e(g or "Unmatched game")} <small>{len(rs)} players</small></summary>'
                      f'<ol class="os-l">{"".join(_row(i, r) for i, r in enumerate(rs, 1))}</ol></details>')
    hint_html = f'<p class="os-hint">{e(hint)}</p>' if hint else ''
    return (f'<section class="sec v59-os">{head}{meta}<ol class="os-l">{top}</ol>{games}{hint_html}'
            f'<p class="os-note">{e(METHOD_NOTE)}</p></section>')
