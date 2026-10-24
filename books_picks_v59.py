"""V5.9 Books top picks: the fourth system on the Prediction Models tab, plus its frozen pre-game log.

No new pick method. The ranking is odds_scorers_v59 ("Projected scorers (odds)", the Home / Odds section) unchanged:
  * odds_scorers_v59.aggregate: every book's anytime-goal "Yes" price -> implied -> no-vig (x FAIR_FACTOR 0.86);
    consensus = MEDIAN no-vig chance across the books quoting the player (a median is the consistency-across-books
    step: one outlier book cannot move it), plus best price + book and every book's price.
  * odds_scorers_v59.rank: consensus desc, then number of books (more books agreeing first), then best price.
Top 10 here = that order, keeping only players matched to an NHL id (the accuracy card scores by player id).
The cross-book outlier view (playbook_odds.compare_odds, best vs worst price) is shown as context only, as on the
Odds tab; it does not re-rank.

Books actually covered (see odds_scorers_v59 + app.py np_live_odds_cached(..., 'us', ...)):
  * The Odds API, region 'us' only and only when ODDS_API_KEY is in Streamlit secrets (DraftKings, FanDuel, BetMGM,
    Caesars*, Fanatics* (*paid plan), BetRivers, ...). Hard Rock Bet is region 'us2' and Novig 'us_ex' - not requested
    by the app. Circa is not offered by The Odds API at all.
  * Otherwise ESPN's free public feed = DraftKings only (one book: "consensus" is then DraftKings' no-vig price).
The workflow has no odds key, so frozen nights use the ESPN (DraftKings) source; the record says which.

Log: snapshots/accuracy_books/<day>.json, frozen pre-game by the nightly workflow (`books_picks_v59.py update`, the
step right after the accuracy and blend freezes in precompute.yml), re-frozen at most every REFREEZE_MIN minutes until first puck drop,
then scored against the accuracy entry's real scorers (player-id match, like the accuracy card). Past nights are never
rebuilt: no odds were saved in git before this log (snapshots hold slate + rankings only), so books nights start here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import accuracy_v58 as acc
import odds_scorers_v59 as oddsc

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('PLAYBOOK_BOOKS_DIR') or HERE / 'snapshots' / 'accuracy_books')   # env override: tests only
SCHEMA = 1
METHOD = f'odds_scorers_v59 median no-vig consensus (x{oddsc.FAIR_FACTOR}), rank: consensus, n_books, best price'
TOP_N = acc.TOP_N
KEEP_DAYS = 90
MAX_BYTES = 95 * 1024
REFREEZE_MIN = 120       # workflow runs every 30 min; refetch ESPN at most every 2 h before first puck drop
REQUESTED = ('Hard Rock Bet', 'DraftKings', 'Fanatics', 'Circa', 'Novig')
COVERAGE_NOTE = ('Books covered: DraftKings (free ESPN feed, used by the nightly freeze). With an Odds API key the app '
                 'adds region “us” books (FanDuel, BetMGM, Fanatics on paid plans …). Not covered: Hard Rock Bet '
                 '(Odds API region us2, not requested), Novig (us_ex, not requested), Circa (not on The Odds API).')
HASHED_KEYS = ('schema', 'day', 'kind', 'source', 'method', 'books', 'odds_updated', 'frozen_at', 'first_start', 'top', 'rows')
_NAME = re.compile(r'^(\d{4}-\d{2}-\d{2})\.json$')


def _pid(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def picks(rows, n=TOP_N):
    """odds_scorers rows (already in odds_scorers_v59.rank order) -> top n with an NHL id."""
    return [r for r in oddsc.rank(list(rows or [])) if _pid(r.get('pid'))][:n]


def gap(r):
    """Cross-book outlier context (as playbook_odds.compare_odds): best vs worst price, or None for one book."""
    b = r.get('books') or {}
    if len(b) < 2:
        return None
    lo = min(b, key=lambda k: oddsc.decimal(b[k]))
    return {'best': r['best'], 'worst': {'book': lo, 'american': b[lo]}}


def content_hash(rec):
    body = {k: rec.get(k) for k in HASHED_KEYS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def verify(rec):
    return None if not rec.get('content_hash') else content_hash(rec) == rec['content_hash']


def build(data, day, first_start=None, now=None, kind='frozen'):
    """odds_scorers_v59.load(...) output -> books record. top rows: [pid, name, team, pos, consensus, n_books,
    best_book, best_american, {book: american}]; rows: every id-matched player [pid, consensus, n_books]."""
    now = now or datetime.now(timezone.utc)
    ranked = [r for r in oddsc.rank(list(data.get('rows') or [])) if _pid(r.get('pid'))]
    top = [[_pid(r['pid']), r['player'], r.get('team') or '', r.get('position') or '', round(r['consensus'], 5), r['n_books'],
            r['best']['book'], r['best']['american'], r['books']] for r in ranked[:TOP_N]]
    rec = {'schema': SCHEMA, 'day': day, 'kind': kind, 'source': data.get('source'), 'method': METHOD,
           'books': list(data.get('books') or []), 'odds_updated': data.get('updated') or '',
           'frozen_at': now.isoformat(timespec='seconds'), 'first_start': first_start, 'demo': False,
           'top': top, 'rows': [[_pid(r['pid']), round(r['consensus'], 5), r['n_books']] for r in ranked],
           'unmatched': sum(1 for r in data.get('rows') or [] if not _pid(r.get('pid'))), 'results': None, 'final': False}
    rec['content_hash'] = content_hash(rec)
    return rec


def score(rec, scorers, source='accuracy log', now=None):
    sids = sorted({int(s[0]) if isinstance(s, (list, tuple)) else int(s) for s in scorers or ()})
    hits = len({t[0] for t in rec.get('top') or []} & set(sids))
    return dict(rec, final=True, results={'scorers': sids, 'n_scorers': len(sids), 'top_n': len(rec.get('top') or []),
                                         'books_hits': hits, 'source': source,
                                         'scored_at': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds')})


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
        rec = dict(rec, rows=rec['rows'][:200])
        rec['content_hash'] = content_hash(rec)
    p = path_for(rec['day'], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(rec, separators=(',', ':'), ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(tmp, p)
    return p


def update(now=None, snap_root=None, root=None, acc_root=None, fetch=None, log=print):
    """Freeze tonight pre-game (ESPN DraftKings via odds_scorers_v59.load; api_quotes=None, so never an Odds API
    credit), then score past frozen nights from the accuracy entry. ``fetch(day, idx)`` = odds_scorers espn_fetch
    (tests inject one). Never raises."""
    now = now or datetime.now(timezone.utc)
    snap_root = snap_root or acc.SNAP_DIR
    acc_root = acc_root or acc.LOG_DIR
    today = acc.eastern_today(now).isoformat()
    done = []
    try:
        snap = acc._load_snap(today, snap_root)
        fs = acc.first_start(snap) if snap else None
        cur = load(today, root)
        fresh = cur and acc._iso(cur['frozen_at']) and now - acc._iso(cur['frozen_at']) < timedelta(minutes=REFREEZE_MIN)
        if snap and fs and now < fs and acc.is_pregame(snap) and snap.get('rankings') and not fresh:
            data = oddsc.load(today, snap.get('games') or [], snap['rankings'], None, fetch, now)
            if data.get('rows'):
                new = build(data, today, fs.isoformat(timespec='seconds'), now)
                if not cur or [t[:6] for t in cur['top']] != [t[:6] for t in new['top']] or cur['source'] != new['source']:
                    save(new, root)
                    done.append(f'froze {today} ({new["source"]})')
                else:
                    done.append(f'{today} unchanged')
            else:
                done.append(f'{today}: no book prices ({"; ".join(data.get("warnings") or [])[:120]})')
    except Exception as exc:
        log(f'books: freeze skipped ({type(exc).__name__}: {exc})')
    for rec in load_all(root):
        try:
            if rec.get('results') or rec['day'] >= today:
                continue
            ent = acc.load_entry(rec['day'], acc_root)
            if ent and ent.get('results'):
                save(score(rec, ent['results']['scorers'], 'accuracy log', now), root)
                done.append(f'scored {rec["day"]}')
        except Exception as exc:
            log(f'books: {rec.get("day")} skipped ({type(exc).__name__}: {exc})')
    log('books: ' + (', '.join(done) or 'nothing to do'))
    return done


def prune(keep_days=KEEP_DAYS, today=None, root=None, dry_run=False):
    r = Path(root or ROOT).resolve()
    if r.parts[-2:] != ('snapshots', 'accuracy_books'):
        raise ValueError(f'books prune only runs in snapshots/accuracy_books/, not {r}')
    cutoff = (today or acc.eastern_today()) - timedelta(days=int(keep_days))
    out = []
    for p in sorted(r.iterdir()) if r.is_dir() else []:
        m = _NAME.match(p.name)
        if m and p.is_file() and date.fromisoformat(m.group(1)) < cutoff:
            out.append(p)
            if not dry_run:
                p.unlink()
    return out


def tonight_rows(day, rec=None, live=None):
    """-> {'source', 'rows': [{'rank','pid','name','team','pos','stat','layers'}]}: the frozen record for `day`, else
    the app's already-loaded _np_odds_scorers (no extra fetch), else empty."""
    if rec and rec.get('day') == day and rec.get('top'):
        src, items = f'frozen pre-game · {rec.get("source")}', [
            {'pid': t[0], 'player': t[1], 'team': t[2], 'position': t[3], 'consensus': t[4], 'n_books': t[5],
             'best': {'book': t[6], 'american': t[7]}, 'books': t[8]} for t in rec['top']]
    elif live and live.get('day') == day and live.get('rows'):
        src, items = f'live · {live.get("source")}', picks(live['rows'])
    else:
        return {'source': 'no book prices loaded', 'rows': []}
    out = []
    for i, r in enumerate(items, 1):
        sh = ' · '.join(f'{oddsc.BOOK_SHORT.get(b, b)} {oddsc.price_label(a)}' for b, a in (r.get('books') or {}).items())
        g = gap(r)
        extra = f' · range {oddsc.price_label(g["worst"]["american"])} to {oddsc.price_label(g["best"]["american"])}' if g else ''
        out.append({'rank': i, 'pid': _pid(r['pid']), 'name': r['player'], 'team': r.get('team'), 'pos': r.get('position') or '',
                    'stat': f'{100 * r["consensus"]:.1f}%',
                    'layers': f'{r["n_books"]} book{"s" if r["n_books"] != 1 else ""}: {sh}{extra}'})
    return {'source': src, 'rows': out}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='V5.9 books top-picks log')
    ap.add_argument('command', choices=['update', 'prune'])
    ap.add_argument('--keep-days', type=int, default=KEEP_DAYS)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.command == 'update':
        update()
    else:
        print(f'books prune: {len(prune(a.keep_days, dry_run=a.dry_run))} file(s)')
