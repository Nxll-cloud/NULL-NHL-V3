"""V6.0 First Goal Intelligence: a SEPARATE market board + frozen log, shown on Prediction Models and Research.

Adapted from the user's standalone "First Goal Intelligence Module v1.0" (Streamlit app). Same intent, Playbook patterns:
  * Market player_goal_scorer_first from The Odds API (regions us,us2), fetched through odds_api_v45.fetch_odds
    (same validation / error handling as the anytime feed), only for events on tonight's slate. Needs ODDS_API_KEY
    and a plan that includes this market; every fetch costs credits (1 per region per event, so ~2 per game).
  * aggregate(): latest quote per (game, player, book); MEDIAN implied % across books = a MARKET REFERENCE, not a
    calibrated first-goal prediction; best book / odds, price gap vs median (pp), fair american from the median.
    Sorted by number of books, then price gap (as v1.0).
  * No standalone app, no pandas: lists of dicts. Never feeds Model / NP / Blend / Books or the accuracy card.
Log: snapshots/accuracy_firstgoal/<day>.json, frozen pre-game by the nightly workflow (only when the workflow has an
ODDS_API_KEY secret; otherwise it skips and costs nothing), scored by the FIRST (non-shootout) goal of each game from
the NHL play-by-play: a game is a hit when the market favourite for that game scored first.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import accuracy_v58 as acc
import odds_scorers_v59 as oddsc

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('PLAYBOOK_FIRSTGOAL_DIR') or HERE / 'snapshots' / 'accuracy_firstgoal')   # env override: tests only
SCHEMA = 1
MARKET = 'player_goal_scorer_first'
REGIONS = 'us,us2'
METHOD = 'first-goal v1.0: median implied % across books (market reference), rank: books, price gap; hit = game favourite scored first'
KEEP_DAYS = 90
MAX_BYTES = 95 * 1024
REFREEZE_MIN = 180       # workflow runs every 30 min; refetch at most every 3 h before first puck drop (credits)
TOP_N = 10
LONGSHOT = 2000
HASHED_KEYS = ('schema', 'day', 'kind', 'source', 'method', 'books', 'odds_updated', 'frozen_at', 'first_start', 'top', 'favs')
CAVEAT = ('Market-implied probabilities are not model-calibrated first-goal predictions. Bookmaker margin and correlated '
          'quotes can distort comparisons. A positive price gap means a better price than the median book, not proven value.')
COVERAGE_NOTE = ('Source: The Odds API market player_goal_scorer_first, regions us + us2 (adds Hard Rock Bet). Needs '
                 'ODDS_API_KEY with first-goal market access; ~2 credits per game per refresh. Circa / Novig not covered.')
_NAME = re.compile(r'^(\d{4}-\d{2}-\d{2})\.json$')


def american_to_prob(odds):
    odds = float(odds)
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)


def fair_american(p):
    return round(100 * (1 - p) / p) if p < .5 else round(-100 * p / (1 - p))


def _pid(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ quotes + board
def quotes_from_records(records, idx=None):
    """odds_api_v45.fetch_odds records (list of dicts) -> [{game, player, book, price, updated, pid, team}] for MARKET."""
    out = []
    for r in records or []:
        if str(r.get('market') or '') != MARKET:
            continue
        price = oddsc.parse_american(r.get('american_odds'))
        name = str(r.get('player') or '').strip()
        if price is None or not name:
            continue
        a, h = str(r.get('away_team') or ''), str(r.get('home_team') or '')
        game, teams = f'{a} @ {h}', ()
        if idx:
            aa, hh = idx['full'].get(a.lower()), idx['full'].get(h.lower())
            if aa and hh:
                game, teams = f'{aa} @ {hh}', (aa, hh)
                if idx['game_of'] and game not in set(idx['game_of'].values()):
                    continue   # not on this slate
        q = {'player': name, 'team': '', 'game': game, 'book': oddsc.book_name(r.get('sportsbook')), 'price': int(price),
             'updated': str(r.get('updated_at') or ''), 'pid': ''}
        if idx:
            oddsc._attach(q, idx, teams)
        out.append(q)
    return out


def aggregate(quotes):
    """v1.0 aggregate, pure python. -> rows sorted by (Books, Price gap) desc."""
    latest = {}
    for q in sorted(quotes or [], key=lambda q: q.get('updated') or ''):
        latest[(q['game'], oddsc.norm_name(q['player']), q['book'])] = q
    groups = {}
    for q in latest.values():
        groups.setdefault((q['game'], oddsc.norm_name(q['player'])), []).append(q)
    out = []
    for (game, _), g in groups.items():
        best = max(g, key=lambda q: (q['price'], q['book']))
        ref = statistics.median(american_to_prob(q['price']) for q in g)
        bp = american_to_prob(best['price'])
        out.append({'game': game, 'player': g[0]['player'], 'pid': _pid(next((q['pid'] for q in g if q.get('pid')), None)),
                    'team': next((q['team'] for q in g if q.get('team')), ''), 'books': len({q['book'] for q in g}),
                    'best_book': best['book'], 'best_odds': int(best['price']), 'median_pct': round(ref * 100, 2),
                    'best_pct': round(bp * 100, 2), 'gap_pp': round((ref - bp) * 100, 2), 'fair': fair_american(ref),
                    'updated': max(q['updated'] for q in g),
                    'prices': {q['book']: q['price'] for q in sorted(g, key=lambda q: q['book'])}})
    return sorted(out, key=lambda r: (r['books'], r['gap_pp']), reverse=True)


def filter_board(board, min_books=1, longshots=False):
    return [r for r in board or [] if r['books'] >= min_books and (not longshots or r['best_odds'] >= LONGSHOT)]


def by_median(board):
    return sorted(board or [], key=lambda r: (-r['median_pct'], -r['books'], r['player']))


def favourites(board):
    """Per game: the player with the highest median implied % (more books, then name, break ties)."""
    fav = {}
    for r in by_median(board):
        fav.setdefault(r['game'], r)
    return fav


def _event_on(day):
    """Keep only events whose start falls on the Eastern `day` (tonight's slate), so no credits on other days."""
    def keep(ev):
        t = acc._iso(ev.get('commence_time'))
        return bool(t) and t.astimezone(acc.ET).date().isoformat() == day
    return keep


def fetch_board(api_key, day, games=(), rankings=(), session=None):
    """-> {'day','source','quotes','board','warnings'}; raises odds_api_v45.OddsFeedError (no key, 401/403, 429 ...)."""
    import odds_api_v45 as oapi
    df, warn = oapi.fetch_odds(api_key, regions=REGIONS, markets=MARKET, session=session, keep_event=_event_on(day))
    recs = df.to_dict('records') if hasattr(df, 'to_dict') else list(df or [])
    idx = oddsc.slate_index(games, rankings) if (games or rankings) else None
    quotes = quotes_from_records(recs, idx)
    return {'day': day, 'source': 'The Odds API · player_goal_scorer_first · us,us2', 'quotes': quotes,
            'board': aggregate(quotes), 'warnings': list(warn or [])}


# ------------------------------------------------------------------------------------------------ frozen log
def content_hash(rec):
    body = {k: rec.get(k) for k in HASHED_KEYS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def verify(rec):
    return None if not rec.get('content_hash') else content_hash(rec) == rec['content_hash']


def _compact(r):
    return [r['pid'], r['player'], r['team'], r['game'], r['median_pct'], r['books'], r['best_book'], r['best_odds'], r['gap_pp']]


def build(data, day, first_start=None, now=None, kind='frozen'):
    now = now or datetime.now(timezone.utc)
    board = data.get('board') or []
    rec = {'schema': SCHEMA, 'day': day, 'kind': kind, 'source': data.get('source'), 'method': METHOD,
           'books': sorted({b for r in board for b in r['prices']}), 'odds_updated': max((r['updated'] for r in board), default=''),
           'frozen_at': now.isoformat(timespec='seconds'), 'first_start': first_start, 'demo': False,
           'top': [_compact(r) for r in by_median(board)[:TOP_N]],
           'favs': {g: _compact(r) for g, r in sorted(favourites(board).items())}, 'results': None, 'final': False}
    rec['content_hash'] = content_hash(rec)
    return rec


def first_scorers_from_pbp(payload):
    """Official PBP JSON -> (state, first non-shootout goal scorer id or None)."""
    import live_nextgoal_v56 as ng
    g = ng.parse_pbp(payload)
    goals = [e for e in g['events'] if e['kind'] == 'goal']
    return g.get('state', ''), (goals[0]['shooter'] if goals else None)


def fetch_first_scorers(games, getter):
    """{game 'AWY @ HOM': first scorer id (None = no regulation/OT goal)} for FINISHED games only."""
    out = {}
    for g in games or []:
        gid = g.get('Game ID')
        if not gid:
            continue
        state, pid = first_scorers_from_pbp(acc._get(getter, f'gamecenter/{int(gid)}/play-by-play'))
        if state in acc.FINAL:
            out[f'{g.get("Away")} @ {g.get("Home")}'] = pid
    return out


def score(rec, firsts, source='NHL play-by-play', now=None):
    """firsts {game: first scorer id}. Hit per game = that game's frozen favourite scored first. top_hits = how many
    games' first scorers were in the frozen top 10. Frozen fields (hash) unchanged."""
    games = {g: (rec['favs'][g][0], pid) for g, pid in firsts.items() if g in (rec.get('favs') or {})}
    hits = sum(1 for fav, pid in games.values() if fav and pid and fav == pid)
    top_ids = {t[0] for t in rec.get('top') or [] if t[0]}
    return dict(rec, final=True, results={'firsts': {g: pid for g, pid in sorted(firsts.items())}, 'games': len(games),
                                         'fav_hits': hits, 'top_hits': len(top_ids & {p for p in firsts.values() if p}),
                                         'source': source, 'scored_at': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds')})


def path_for(day, root=None):
    date.fromisoformat(day)
    return Path(root or ROOT) / f'{day}.json'


def load(day, root=None):
    try:
        r = json.loads(path_for(day, root).read_text(encoding='utf-8'))
        return r if isinstance(r, dict) and r.get('schema') == SCHEMA and r.get('day') == day else None
    except (OSError, ValueError):
        return None


def load_all(root=None):
    r = Path(root or ROOT)
    return [x for x in (load(p.stem, root) for p in sorted(r.glob('????-??-??.json'))) if x] if r.is_dir() else []


def save(rec, root=None):
    if len(json.dumps(rec, separators=(',', ':')).encode()) > MAX_BYTES:
        raise ValueError('first-goal record too large')
    p = path_for(rec['day'], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(rec, separators=(',', ':'), ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(tmp, p)
    return p


def update(now=None, snap_root=None, root=None, api_key=None, fetch=None, getter=None, log=print):
    """Freeze tonight pre-game (only with ODDS_API_KEY in the environment; else skipped, zero credits), then score past
    frozen nights from the NHL play-by-play once every game is final. Never raises."""
    now = now or datetime.now(timezone.utc)
    snap_root = snap_root or acc.SNAP_DIR
    today = acc.eastern_today(now).isoformat()
    key = api_key if api_key is not None else os.environ.get('ODDS_API_KEY', '')
    done = []
    try:
        snap = acc._load_snap(today, snap_root)
        fs = acc.first_start(snap) if snap else None
        cur = load(today, root)
        fresh = cur and acc._iso(cur['frozen_at']) and now - acc._iso(cur['frozen_at']) < timedelta(minutes=REFREEZE_MIN)
        if not key and not fetch:
            done.append('no ODDS_API_KEY in the workflow: freeze skipped')
        elif snap and fs and now < fs and acc.is_pregame(snap) and not fresh:
            data = (fetch or fetch_board)(key, today, snap.get('games') or [], snap.get('rankings') or [])
            if data.get('board'):
                new = build(data, today, fs.isoformat(timespec='seconds'), now)
                if not cur or cur['top'] != new['top'] or cur['favs'] != new['favs']:
                    save(new, root)
                    done.append(f'froze {today}')
                else:
                    done.append(f'{today} unchanged')
            else:
                done.append(f'{today}: no first-goal prices (market not offered / not entitled)')
    except Exception as exc:
        log(f'firstgoal: freeze skipped ({type(exc).__name__}: {exc})')
    if getter is None:
        import requests
        getter = lambda url, timeout=12: requests.get(url, timeout=timeout, headers=acc.UA)   # noqa: E731
    for rec in load_all(root):
        try:
            if rec.get('results') or rec['day'] >= today:
                continue
            snap = acc._load_snap(rec['day'], snap_root)
            games = [g for g in (snap or {}).get('games') or [] if f'{g.get("Away")} @ {g.get("Home")}' in rec['favs']]
            firsts = fetch_first_scorers(games, getter)
            if games and len(firsts) == len(games):
                save(score(rec, firsts, now=now), root)
                done.append(f'scored {rec["day"]}')
        except Exception as exc:
            log(f'firstgoal: {rec.get("day")} skipped ({type(exc).__name__}: {exc})')
    log('firstgoal: ' + (', '.join(done) or 'nothing to do'))
    return done


def prune(keep_days=KEEP_DAYS, today=None, root=None, dry_run=False):
    r = Path(root or ROOT).resolve()
    if r.parts[-2:] != ('snapshots', 'accuracy_firstgoal'):
        raise ValueError(f'first-goal prune only runs in snapshots/accuracy_firstgoal/, not {r}')
    cutoff = (today or acc.eastern_today()) - timedelta(days=int(keep_days))
    out = []
    for p in sorted(r.iterdir()) if r.is_dir() else []:
        m = _NAME.match(p.name)
        if m and p.is_file() and date.fromisoformat(m.group(1)) < cutoff:
            out.append(p)
            if not dry_run:
                p.unlink()
    return out


# ------------------------------------------------------------------------------------------------ display (read only)
def record_totals(recs):
    sc = [r['results'] for r in recs or [] if r.get('results')]
    return {'nights': len(sc), 'games': sum(x['games'] for x in sc), 'hits': sum(x['fav_hits'] for x in sc)}


def accuracy_line(recs):
    t = record_totals(recs)
    if not t['games']:
        return 'Record: no scored night yet (the log starts with the first pre-game freeze).'
    return (f'Record: game favourite scored first in {t["hits"]}/{t["games"]} games '
            f'({100 * t["hits"] / t["games"]:.0f}%) over {t["nights"]} night{"s" if t["nights"] != 1 else ""}.')


def tonight_board(day, rec=None, live=None):
    """-> (source, rows): live board for `day` when loaded (no extra fetch here), else the frozen record, else empty."""
    if live and live.get('day') == day and live.get('board'):
        return f'live · {live.get("source")}', by_median(live['board'])
    if rec and rec.get('day') == day and rec.get('top'):
        keys = ('pid', 'player', 'team', 'game', 'median_pct', 'books', 'best_book', 'best_odds', 'gap_pp')
        rows = [dict(zip(keys, t)) for t in rec['top']]
        for r in rows:   # derived display fields (not stored, so the frozen hash is unchanged)
            r.update(best_pct=round(american_to_prob(r['best_odds']) * 100, 2), fair=fair_american(r['median_pct'] / 100),
                     updated=rec.get('odds_updated') or '')
        return f'frozen pre-game · {rec.get("source")}', rows
    return '', []


def _e(x):
    import html
    return html.escape(str(x if x is not None else ''))


CSS = ('<style>.v55 .fg{border:1px solid rgba(255,196,0,.35);border-radius:14px;padding:12px;margin:10px 0;'
       'background:rgba(255,196,0,.05);min-width:0}.v55 .fg h4{margin:0 0 4px;color:#ffc400}.v55 .fg ol{margin:6px 0;padding-left:1.4em}'
       '.v55 .fg li{margin:3px 0;overflow-wrap:anywhere}.v55 .fg .fgs{opacity:.75;font-size:.85em}'
       '.v55 .fg .fgw{color:#ffb020;font-size:.85em;margin:6px 0}.v55 .fg .fgx{font-size:.85em}</style>')


def section_html(source, rows, recs=(), scored=(), status='', n=TOP_N):
    """First Goal card (shared by Prediction Models and Research)."""
    scored = {int(s) for s in scored or ()}
    body = ''.join(f'<li><b>{_e(r["player"])}</b>{" 🚨" if r.get("pid") in scored else ""} <span class="fgs">{_e(r.get("game"))}</span>'
                   f' · {r["median_pct"]:.1f}% · best {_e(oddsc.price_label(r["best_odds"]))} {_e(r["best_book"])}'
                   f' · {r["books"]} book{"s" if r["books"] != 1 else ""}</li>' for r in rows[:n])
    if not body:
        body = f'<p class="fgx">{_e(status or "No first-goal prices loaded for tonight.")}</p>'
    else:
        body = f'<ol>{body}</ol>'
    return (CSS + '<section class="fg" aria-label="First goal intelligence"><h4>🥅 First Goal · market board</h4>'
            f'<div class="fgs">{_e(source or "no source")} · ranked by median implied % across books</div>{body}'
            f'<div class="fgx">{_e(accuracy_line(recs))}</div><p class="fgw">⚠️ {_e(CAVEAT)}</p>'
            f'<div class="fgs">{_e(COVERAGE_NOTE)}</div></section>')


def table_rows(rows):
    """Board rows -> display dicts with the v1.0 column names (Research tables)."""
    return [{'Game': r['game'], 'Player': r['player'], 'Books': r['books'], 'Best book': r['best_book'], 'Best odds': r['best_odds'],
             'Median market implied %': r['median_pct'], 'Best price implied %': r.get('best_pct'), 'Price gap (pp)': r['gap_pp'],
             'Reference fair odds': r.get('fair'), 'Last update': r.get('updated')} for r in rows]


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='V6.0 first-goal market log')
    ap.add_argument('command', choices=['update', 'prune'])
    ap.add_argument('--keep-days', type=int, default=KEEP_DAYS)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.command == 'update':
        update()
    else:
        print(f'firstgoal prune: {len(prune(a.keep_days, dry_run=a.dry_run))} file(s)')
