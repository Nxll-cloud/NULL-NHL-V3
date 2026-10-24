"""V5.9 Prediction Models tab: three systems side by side + a separate, frozen log for the EXPERIMENTAL blend.

Systems (each ranks tonight's skaters; top TOP_N scored like the Home accuracy card, by player ID vs real scorers):
  model  - accuracy_v58.predictions() / parlay_v58.candidates model_rank: P(anytime goal) = 1 - exp(-lambda_game).
  np     - the NP statistical leaderboard: Statistical rank 1..10 (V3.2 Adjusted Index, Form %), accuracy_v58.np_top_ids.
  blend  - EXPERIMENTAL: the model's chance boosted by gematria layer hits. Layer hits = how many of the five
           All-layer criteria a player meets (all_layers_v59.evaluate, the Numbers tab's own code, 0..5):
             day      name English digit = universal day (player_targets_v49 DAY_METHODS, English only)
             position a position label (position_layers_v59.POS_LABELS) hits the day or arena number
             arena    the existing like-for-like arena match (name English digit = arena English digit)
             reverse  at least one hit via Reverse      english  at least one hit via English
           BLEND_KIND 'rate': the goal rate is multiplied by (1 + w * hits), i.e. p' = 1 - (1 - p) ** (1 + w * hits)
           ('logit': logit(p') = logit(p) + w * hits; kept for the weight grid). Ranked by p' (ties: model chance,
           then model rank, then player ID), so a high model chance plus several layer hits outranks a single signal.
           Weights (BLEND_KIND, BLEND_W) were picked by a small grid on the saved / rebuilt nights (top-10 hits, then log
           loss, smallest w among ties); see WEIGHT_NOTE. Gematria layers showed no statistical association with
           scoring in the earlier 801-player check, so the blend is labelled experimental everywhere it is shown.

Blend log: snapshots/accuracy_blend/YYYY-MM-DD.json (one small file per night, ~15 KB). Frozen PRE-GAME by the workflow
right after the accuracy freeze, from that night's frozen model entry (snapshots/accuracy/) + the saved slate snapshot,
with the weights used; content_hash covers the frozen fields. Once the accuracy entry is scored, the same real scorers
score the blend (results added outside the hash). Nights built after the fact carry kind='rebuilt' (never 'frozen').
The accuracy log, its content_hash / verify() and the model / NP numbers are read only, never written here.
CLI: python prediction_models_v59.py update | prune --keep-days 90 | rebuild --snapshot PATH [--source TEXT]
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import accuracy_v58 as acc

HERE = Path(__file__).resolve().parent
SNAP_DIR = HERE / 'snapshots'
ROOT = Path(os.environ.get('PLAYBOOK_BLEND_DIR') or SNAP_DIR / 'accuracy_blend')   # env override: tests / preview only
SCHEMA = 1
METHOD_VERSION = 'blend-v1'
TOP_N = acc.TOP_N
TREND_N = 10
KEEP_DAYS = 90
MAX_BYTES = 95 * 1024
P_EPS = acc.P_EPS
_NAME = re.compile(r'^(\d{4}-\d{2}-\d{2})\.json$')

# Chosen weights. Grid (top-10 hits / pooled log loss) on the 2 clean nights, 2026-10-22 rebuilt + 2026-10-23 saved:
#   rate  w=0    6/20 0.3807 | 0.05 6/20 0.3831 | 0.1 6/20 0.3877 | 0.2 7/20 0.4015 | 0.35 7/20 0.4300 | 0.5 7/20 0.4644
#   logit w=0.05 6/20 0.3831 | 0.1  6/20 0.3883 | 0.2 7/20 0.4079 | 0.35 6/20 0.4646 | 0.5 4/20 0.5586
# Rule: most hits, then log loss, then the smallest w -> rate 0.2 (ties 0.35 / 0.5 / logit 0.2 lose on log loss).
# Sensitivity (report only; 10-14..10-21 are point-in-time reconstructions, not pre-game snapshots): over 10 nights
# rate 0 / 0.05 / 0.1 / 0.2 all hit 31/100 and w=0 has the best log loss, i.e. the blend adds nothing measurable.
BLEND_KIND = 'rate'
BLEND_W = 0.2
WEIGHTS_CHOSEN_THROUGH = '2026-10-23'   # nights up to here were used to pick w (in-sample for the blend)
GRID = [('rate', w) for w in (0.0, 0.05, 0.1, 0.2, 0.35, 0.5)] + [('logit', w) for w in (0.05, 0.1, 0.2, 0.35, 0.5)]
WEIGHT_NOTE = ('Blend = model goal rate × (1 + 0.2 × layer hits), layer hits 0–5 (Day, Position, Arena, Reverse, English); '
               'w = 0.2 won a small grid on the 2 clean nights (Oct 22 rebuilt, Oct 23 saved): 7/20 top-10 hits vs 6/20 for '
               'the plain model (w = 0), a single extra hit on one night. On 10 nights incl. 8 point-in-time reconstructions it '
               'tied w = 0 (31/100) with a worse log loss (0.396 vs 0.374), so treat it as a coin-flip, not an edge.')
EXPERIMENTAL_NOTE = ('Experimental: gematria layers showed no statistical association with scoring in our 801-player check, '
                     'and weights tuned on a few nights may be overfit.')
SYSTEMS = ('model', 'np', 'blend', 'books')
LABEL = {'model': 'Model', 'np': 'NP leaderboard', 'blend': 'Blend (experimental)', 'books': 'Books top picks'}
HASHED_KEYS = ('schema', 'day', 'kind', 'source', 'method', 'weights', 'model_entry_hash', 'frozen_at', 'snapshot_at',
               'first_start', 'day_num', 'top', 'players', 'model_top', 'np_top')


# ------------------------------------------------------------------------------------------------ blend math (pure)
def blend_p(p, hits, w=BLEND_W, kind=BLEND_KIND):
    """Model chance p + layer hit count -> blended chance (a probability in (0, 1))."""
    p = min(max(float(p), P_EPS), 1 - P_EPS)
    n = max(0, int(hits or 0))
    if kind == 'rate':
        return 1.0 - (1.0 - p) ** (1.0 + float(w) * n)
    if kind == 'logit':
        z = math.log(p / (1 - p)) + float(w) * n
        return 1.0 / (1.0 + math.exp(-z))
    raise ValueError(f'unknown blend kind {kind!r}')


def rank_blend(players, hits, w=BLEND_W, kind=BLEND_KIND):
    """players: [[pid, name, team, p, model_rank, ...]] (accuracy entry rows); hits: {pid: n}.
    -> [{'pid','name','team','p','model_rank','hits','pb','rank'}] best first (ties: p, model rank, pid)."""
    out = []
    for row in players or []:
        pid, name, team, p, mr = int(row[0]), row[1], row[2], float(row[3]), row[4]
        n = int((hits or {}).get(pid, (hits or {}).get(str(pid), 0)) or 0)
        out.append({'pid': pid, 'name': name, 'team': team, 'p': p, 'model_rank': mr, 'hits': n,
                    'pb': blend_p(p, n, w, kind)})
    out.sort(key=lambda r: (-r['pb'], -r['p'], r['model_rank'] if isinstance(r['model_rank'], (int, float)) else 1e9, r['pid']))
    for i, r in enumerate(out, 1):
        r['rank'] = i
    return out


def top_hits(top_ids, scorer_ids):
    """Accuracy-card scoring: how many of the top ids scored (player ID match)."""
    s = {int(x) for x in scorer_ids or ()}
    return sum(1 for p in top_ids or () if int(p) in s)


def model_top_ids(players, n=TOP_N):
    """The model's top n by frozen model_rank (exactly the accuracy card's set)."""
    return [p[0] for p in sorted(players or [], key=lambda p: p[4])[:n]]


def log_loss(probs, scorer_ids):
    """Mean log loss over {pid: p} against the scorer set (accuracy_v58.calibration clip)."""
    cal = acc.calibration((p, int(k) in {int(x) for x in scorer_ids}) for k, p in probs.items())
    return cal['log_loss'] if cal else None


def grid_eval(nights, grid=GRID, n=TOP_N):
    """nights: [{'players': [[pid, name, team, p, model_rank]], 'hits': {pid: n}, 'scorers': [pid]}].
    -> [{'kind','w','top_hits','top_n','log_loss'}] (log loss pooled over every priced skater of every night)."""
    out = []
    for kind, w in grid:
        th = tn = 0
        pairs = []
        for nt in nights:
            r = rank_blend(nt['players'], nt['hits'], w, kind)
            sids = {int(x) for x in nt['scorers']}
            th += top_hits([x['pid'] for x in r[:n]], sids)
            tn += min(n, len(r))
            pairs += [(x['pb'], x['pid'] in sids) for x in r]
        cal = acc.calibration(pairs)
        out.append({'kind': kind, 'w': w, 'top_hits': th, 'top_n': tn, 'log_loss': cal['log_loss'] if cal else None})
    return out


def choose(results):
    """Best by top-10 hits, then log loss (4 dp), then the smallest w (limits overfitting)."""
    return min(results, key=lambda r: (-r['top_hits'], round(r['log_loss'] if r['log_loss'] is not None else 9, 4), r['w']))


# ------------------------------------------------------------------------------------------------ gematria layers
def layers_for(snapshot, day=None):
    """Saved slate snapshot -> {pid: {'n': 0..5, 'met': {criterion: bool}, 'hits': [chip], 'pos': code}} using the
    Numbers tab's own functions (numerology_v48.analyze_game, player_targets_v49.slate_targets, pos_tag_v59,
    all_layers_v59.evaluate). Deterministic: names, date and arena only."""
    import pandas as pd
    import all_layers_v59 as al
    import pos_tag_v59 as pt
    import position_layers_v59 as pl
    from home_leaders_v52 import TEAM_NAMES
    from numerology_v48 import analyze_game, universal_day
    from player_targets_v49 import slate_targets
    day = day or snapshot.get('day')
    rows = [r for r in (snapshot or {}).get('rankings') or [] if isinstance(r, dict)]
    if not rows:
        return {}
    ranked = pd.DataFrame(rows)
    games = [g for g in snapshot.get('games') or [] if isinstance(g, dict)]
    analyses = [analyze_game(g, day, dict(TEAM_NAMES)) for g in games]
    pmap = pt.pos_map(ranked)
    day_num = universal_day(day)
    out = {}
    for item in slate_targets(analyses, ranked, day):
        arena_num = pl._root((item.get('game') or {}).get('arena'))
        for side in ('away_targets', 'home_targets'):
            for t in item.get(side) or []:
                try:
                    pid = int(float(t.get('player_id')))
                except (TypeError, ValueError):
                    continue
                if pid in out:
                    continue
                code = pt.lookup(pmap, pid, t.get('team'), t.get('player'))
                ev = al.evaluate(t, code, day_num, arena_num)
                out[pid] = {'n': sum(bool(v) for v in ev['met'].values()), 'met': ev['met'], 'hits': ev['hits'], 'pos': code or ''}
    return out


def met_labels(met):
    import all_layers_v59 as al
    return [al.LABEL[c] for c in al.CRITERIA if (met or {}).get(c)]


# ------------------------------------------------------------------------------------------------ frozen log
def content_hash(rec):
    body = {k: rec.get(k) for k in HASHED_KEYS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def verify(rec):
    return None if not rec.get('content_hash') else content_hash(rec) == rec['content_hash']


def build(entry, snapshot, kind='frozen', source='workflow', now=None, w=BLEND_W, blend_kind=BLEND_KIND):
    """Accuracy entry (frozen model chances) + the same night's slate snapshot -> blend record (pure apart from the
    gematria). kind: 'frozen' (pre-game, workflow) | 'rebuilt' (after the fact)."""
    from numerology_v48 import universal_day
    if kind not in ('frozen', 'rebuilt'):
        raise ValueError(kind)
    day = entry['day']
    lay = layers_for(snapshot, day)
    players = entry.get('players') or []
    ranked = rank_blend(players, {k: v['n'] for k, v in lay.items()}, w, blend_kind)
    now = now or datetime.now(timezone.utc)
    top = [[r['pid'], r['name'], r['team'], (lay.get(r['pid']) or {}).get('pos', ''), round(r['p'], 4), r['model_rank'],
            r['hits'], round(r['pb'], 4), met_labels((lay.get(r['pid']) or {}).get('met'))] for r in ranked[:TOP_N]]
    rec = {'schema': SCHEMA, 'day': day, 'kind': kind, 'source': source, 'method': METHOD_VERSION,
           'weights': {'kind': blend_kind, 'w': w}, 'model_entry_hash': entry.get('content_hash'),
           'frozen_at': now.isoformat(timespec='seconds'), 'snapshot_at': snapshot.get('updated_at') or entry.get('snapshot_at'),
           'first_start': entry.get('first_start'), 'day_num': universal_day(day), 'top': top,
           'players': [[int(p[0]), round(float(p[3]), 4), int((lay.get(int(p[0])) or {}).get('n', 0))] for p in players],
           'model_top': model_top_ids(players), 'np_top': acc.np_top_ids(entry, snapshot),
           'results': None, 'final': False}
    rec['content_hash'] = content_hash(rec)
    return finalize(rec, now)


def finalize(rec, now=None):
    if rec.get('final'):
        return rec
    fs = acc._iso(rec.get('first_start')) if rec.get('first_start') else None
    now = now or datetime.now(timezone.utc)
    if fs is None or now < fs:
        return rec
    return dict(rec, final=True)


def score(rec, scorers, source='accuracy log', model_hits=None, np_hits=None, now=None):
    """Add results (outside content_hash): blend / model / NP top-10 hits vs the same real scorers + log losses."""
    sids = sorted({int(s[0]) if isinstance(s, (list, tuple)) else int(s) for s in scorers or ()})
    pm = {p[0]: p[1] for p in rec.get('players') or []}
    pb = {p[0]: blend_p(p[1], p[2], rec['weights']['w'], rec['weights']['kind']) for p in rec.get('players') or []}
    res = {'scorers': sids, 'n_scorers': len(sids), 'top_n': len(rec.get('top') or []),
           'blend_hits': top_hits([t[0] for t in rec.get('top') or []], sids),
           'model_hits': model_hits if model_hits is not None else top_hits(rec.get('model_top'), sids),
           'np_hits': np_hits if np_hits is not None else (top_hits(rec['np_top'], sids) if rec.get('np_top') else None),
           'log_loss_blend': log_loss(pb, sids) if pb else None, 'log_loss_model': log_loss(pm, sids) if pm else None,
           'source': source, 'scored_at': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds')}
    return dict(rec, results=res)


def _dump(rec):
    return json.dumps(rec, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


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
    body = _dump(rec)
    if len(body.encode('utf-8')) > MAX_BYTES:
        rec = dict(rec, players=[p for p in rec.get('players') or [] if p[2]])   # never happens on a 16-game slate
        body = _dump(rec)
    p = path_for(rec['day'], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(body, encoding='utf-8')
    os.replace(tmp, p)
    return p


def update(now=None, snap_root=SNAP_DIR, root=None, acc_root=None, log=print):
    """Workflow step (after `accuracy_v58.py update`): freeze tonight's blend while pre-game (re-frozen each run
    until first puck drop, like the accuracy entry), catch up nights whose accuracy entry has no blend record
    (kind='rebuilt'), mark final, and score from the accuracy entry's real scorers. Never raises."""
    now = now or datetime.now(timezone.utc)
    today = acc.eastern_today(now).isoformat()
    acc_root = acc_root or acc.LOG_DIR
    done = []
    try:
        ent = acc.load_entry(today, acc_root)
        snap = acc._load_snap(today, snap_root)
        cur = load(today, root)
        fs = acc.first_start(snap) if snap else None
        if (ent and ent.get('players') and not ent.get('results') and not ent.get('final') and snap and fs and now < fs
                and acc.is_pregame(snap) and not (cur and (cur.get('final') or cur.get('results')))):
            new = build(ent, snap, 'frozen', 'workflow', now)
            if not cur or any(cur.get(k) != new.get(k) for k in ('model_entry_hash', 'weights', 'top', 'players', 'np_top', 'method')):
                save(new, root)
                done.append(f'froze {today}')
    except Exception as exc:
        log(f'blend: freeze skipped ({type(exc).__name__}: {exc})')
    for ent in acc.load_all(acc_root):
        day = ent['day']
        try:
            if day >= today or load(day, root) or not ent.get('players') or ent.get('compacted'):
                continue
            snap = acc._load_snap(day, snap_root)
            if snap and snap.get('rankings'):
                save(build(ent, snap, 'rebuilt', 'catch-up from the frozen pre-game model entry', now), root)
                done.append(f'rebuilt {day}')
        except Exception as exc:
            log(f'blend: catch-up {day} skipped ({type(exc).__name__}: {exc})')
    for rec in load_all(root):
        try:
            f = finalize(rec, now)
            if f is not rec:
                save(f, root)
                rec = f
                done.append(f'final {rec["day"]}')
            if rec.get('results') or rec['day'] >= today:
                continue
            ent = acc.load_entry(rec['day'], acc_root)
            if ent and ent.get('results') and ent.get('summary'):
                e2 = acc.attach_np(ent, lambda d: acc._load_snap(d, snap_root))
                save(score(rec, ent['results']['scorers'], 'accuracy log', e2['summary'].get('top_hits'),
                           e2['summary'].get('np_top_hits'), now), root)
                done.append(f'scored {rec["day"]}')
        except Exception as exc:
            log(f'blend: {rec.get("day")} skipped ({type(exc).__name__}: {exc})')
    log('blend: ' + (', '.join(done) or 'nothing to do'))
    return done


def rebuild(snapshot, getter=None, source='rebuilt from a saved pre-game slate snapshot', root=None, now=None, save_it=True):
    """Offline: a past night with a clean pre-game snapshot but no accuracy entry. Rebuilds the model exactly like
    accuracy_v58.backfill (predictions + situ_for without starters; nothing is written to snapshots/accuracy/), scores
    model / NP / blend against the NHL feed, labels the record kind='rebuilt'. Returns the record (or None)."""
    import requests
    getter = getter or requests.get
    day = snapshot['day']
    if not (snapshot.get('rankings') and acc.is_pregame(snapshot)):
        return None
    ent = acc.predictions(snapshot, (), 'blend rebuild', now, 'no injury list', acc.situ_for(day, snapshot.get('games'), getter=getter))
    rec = build(ent, snapshot, 'rebuilt', source, now)
    rec = dict(rec, model_entry_hash=None)
    rec['content_hash'] = content_hash(rec)
    res = acc.fetch_results(day, getter)
    if res.get('complete'):
        rec = score(rec, res['scorers'], 'NHL feed (rebuild)', now=now)
    if save_it:
        save(rec, root)
    return rec


def prune(keep_days=KEEP_DAYS, today=None, root=None, dry_run=False):
    r = Path(root or ROOT).resolve()
    if r.parts[-2:] != ('snapshots', 'accuracy_blend'):
        raise ValueError(f'blend prune only runs in snapshots/accuracy_blend/, not {r}')
    cutoff = (today or acc.eastern_today()) - timedelta(days=int(keep_days))
    out = []
    for p in sorted(r.iterdir()) if r.is_dir() else []:
        m = _NAME.match(p.name)
        if m and p.is_file() and date.fromisoformat(m.group(1)) < cutoff:
            out.append(p)
            if not dry_run:
                p.unlink()
    return out


# ------------------------------------------------------------------------------------------------ tab view (pure)
def nights(blend_recs, acc_entries, today, n=TREND_N, books_recs=()):
    """Last n scored nights before `today`, oldest first: {'day','kind','model','np','blend','books'} hit counts
    (/top_n). Model / NP come from the saved accuracy entry when it is scored (the card's own numbers), else from the
    blend record's rebuild. Books come from snapshots/accuracy_books (frozen pre-game only, never rebuilt). Nights
    with neither a scored blend nor a scored books record are skipped."""
    accd = {e['day']: e for e in acc_entries or []}
    bl = {r['day']: r for r in blend_recs or [] if r.get('results')}
    bk = {r['day']: r for r in books_recs or () if r.get('results')}
    out = []
    for day in sorted(set(bl) | set(bk)):
        if day >= today:
            continue
        res = (bl.get(day) or {}).get('results') or {}
        e = accd.get(day)
        es = (e or {}).get('summary') if (e or {}).get('results') else None
        if not res and not es:
            continue
        kr = (bk.get(day) or {}).get('results')
        out.append({'day': day, 'kind': (bl.get(day) or {}).get('kind'), 'top_n': res.get('top_n') or TOP_N,
                    'n_scorers': res.get('n_scorers') or (kr or {}).get('n_scorers'),
                    'model': es['top_hits'] if es else res.get('model_hits'),
                    'np': (es.get('np_top_hits') if es and es.get('np_top_n') else res.get('np_hits')),
                    'blend': res.get('blend_hits'), 'books': kr['books_hits'] if kr else None,
                    'books_n': kr['top_n'] if kr else None, 'saved': bool(es)})
    return out[-n:]


def totals(ns):
    t = {}
    for s in SYSTEMS:
        got = [x for x in ns if x.get(s) is not None]
        t[s] = {'hits': sum(x[s] for x in got), 'n': sum(_n(x, s) for x in got), 'nights': len(got)}
    return t


def _n(x, s):
    return (x.get('books_n') or x['top_n']) if s == 'books' else x['top_n']


def leader(tot):
    """Systems with the best hit rate (ties all listed); [] when nothing is scored."""
    rate = {s: v['hits'] / v['n'] for s, v in tot.items() if v['n']}
    if not rate:
        return []
    best = max(rate.values())
    return [s for s in SYSTEMS if s in rate and abs(rate[s] - best) < 1e-12]


def np_top(rankings, n=TOP_N):
    """NP leaderboard top n rows (Statistical rank 1..n) from snapshot / session rankings rows."""
    got = {}
    for row in rankings or []:
        try:
            r, pid = int(float(row.get('Statistical rank'))), int(float(row.get('Player ID')))
        except (TypeError, ValueError, AttributeError):
            continue
        if 1 <= r <= n:
            got.setdefault(r, dict(row, _pid=pid, _rank=r))
    return [got[r] for r in sorted(got)]


CSS = ('<style>.v55 .pm{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:10px 0}'
       '@media (max-width:1180px){.v55 .pm{grid-template-columns:repeat(2,minmax(0,1fr))}}'
       '@media (max-width:700px){.v55 .pm{grid-template-columns:minmax(0,1fr)}}'
       '.v55 .pmc{min-width:0;padding:12px 14px;border-radius:18px;border:1px solid color-mix(in srgb,var(--pc,var(--neon)) 32%,transparent);'
       'background:linear-gradient(135deg,rgba(56,225,255,.06),rgba(178,107,255,.07))}'
       '.v55 .pmc h3{margin:0;color:var(--ink);font:800 .9rem var(--fd);letter-spacing:.08em;text-transform:uppercase}'
       '.v55 .pmc .pmk{margin:2px 0 8px;color:var(--mut);font-size:.76rem;line-height:1.4}'
       '.v55 .pmr{display:grid;grid-template-columns:2.1em minmax(0,1fr) auto;align-items:center;gap:6px;padding:6px 0;border-top:1px solid var(--line);font-size:.84rem;color:var(--ink)}'
       '.v55 .pmr .rk{color:var(--mut);font-weight:800;font-variant-numeric:tabular-nums}'
       '.v55 .pmr .nm{min-width:0;display:flex;align-items:center;gap:5px}.v55 .pmr .nm b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:700}'
       '.v55 .pmr .nm small{color:var(--dim);font-size:.72rem;flex:none}'
       '.v55 .pmr .st{text-align:right;white-space:nowrap;font-weight:800;color:var(--pc,var(--neon));font-variant-numeric:tabular-nums}'
       '.v55 .pmr .ly{grid-column:2/4;margin-top:-2px;color:var(--mut);font-size:.72rem;overflow-wrap:anywhere}'
       '.v55 .pmr.sc .nm b{color:var(--ok)}'
       '.v55 .pmr .nm .npsc{flex:none;margin-left:0}'
       '.v55 .pmacc{margin-top:8px;padding-top:6px;border-top:1px solid var(--line);color:var(--mut);font-size:.78rem;line-height:1.5;overflow-wrap:anywhere}'
       '.v55 .pmacc b{color:var(--ink)}'
       '.v55 .pms{margin:8px 0;padding:12px 14px;border-radius:18px;border:1px solid color-mix(in srgb,var(--neon) 30%,transparent);'
       'background:linear-gradient(135deg,rgba(56,225,255,.07),rgba(178,107,255,.08))}'
       '.v55 .pms p{margin:4px 0 0;color:var(--mut);font-size:.8rem;line-height:1.45}.v55 .pms b{color:var(--ink)}'
       '.v55 .pms .pmh{color:var(--ink);font:800 .95rem var(--fd);letter-spacing:.04em}'
       '.v55 .pmt{width:100%;border-collapse:collapse;margin-top:8px;font-size:.8rem;color:var(--ink);font-variant-numeric:tabular-nums}'
       '.v55 .pmt th{padding:4px 5px;text-align:right;color:var(--mut);font:700 .72rem var(--fb);letter-spacing:.05em;text-transform:uppercase;border-bottom:1px solid var(--line)}'
       '.v55 .pmt td{padding:4px 5px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}'
       '.v55 .pmt th:first-child,.v55 .pmt td:first-child{text-align:left}.v55 .pmt .kd{color:var(--dim);font-size:.7rem}'
       '.v55 .pmf{margin:8px 0 0;color:var(--dim);font-size:.74rem;line-height:1.45}'
       '.v55 .pmx{color:var(--warn,#ffb347);font-weight:800;letter-spacing:.06em;font-size:.66rem;border:1px solid currentColor;border-radius:999px;padding:1px 6px;margin-left:6px;vertical-align:middle}'
       '@media (max-width:360px){.v55 .pmc{padding:10px}.v55 .pmt th,.v55 .pmt td{padding:4px 2px}}</style>')
TONE = {'model': 'var(--neon)', 'np': 'var(--vio,#b26bff)', 'blend': '#ff5fd2', 'books': 'var(--ok,#3dffa8)'}


def _e(x):
    return html.escape(str(x if x is not None else ''))


def summary_html(ns, n=TREND_N):
    tot = totals(ns)
    lead = leader(tot)
    if not ns:
        return (f'{CSS}<section class="pms" aria-label="Prediction systems summary"><div class="pmh">Which system is hitting best</div>'
                f'<p>No scored night yet. Each system’s top-{TOP_N} hit count appears here once a slate is final.</p>'
                f'<p>{_e(EXPERIMENTAL_NOTE)}</p></section>')
    parts = ' · '.join(f'{LABEL[s]} <b>{tot[s]["hits"]}/{tot[s]["n"]}</b>' + (f' ({tot[s]["nights"]} nights)' if tot[s]['nights'] != len(ns) else '')
                       for s in SYSTEMS)
    if len(lead) == len([s for s in SYSTEMS if tot[s]['n']]):
        verdict = 'All systems are level'
    else:
        verdict = ' and '.join(LABEL[s] for s in lead) + (' lead' if len(lead) > 1 else ' leads')
    rebuilt = sum(1 for x in ns if not x.get('saved'))
    bn = tot['books']['nights']
    books = (' Books has only the nights frozen since its log started (no odds were saved before), so compare it on '
             'those nights only.' if bn < len(ns) else '')
    ins = sum(1 for x in ns if x['day'] <= WEIGHTS_CHOSEN_THROUGH)
    insample = (f' The blend’s weight was picked on {ins} of these nights, so its record there is in-sample.' if ins else '')
    return (f'{CSS}<section class="pms" aria-label="Prediction systems summary"><div class="pmh">{_e(verdict)} over the last '
            f'{len(ns)} scored night{"s" if len(ns) != 1 else ""}</div><p>Top-{TOP_N} hits: {parts}.</p>'
            f'<p>Small sample: {len(ns)} night{"s" if len(ns) != 1 else ""} ({rebuilt} rebuilt) of ~{TOP_N} picks each, so a gap of a '
            f'few hits is noise.{insample}{books} {_e(EXPERIMENTAL_NOTE)}</p></section>')


def _row(rank, name, team, pos_html, stat, layers='', scored=False, badge=''):
    """One top-10 row. ``badge`` (V6.0) is the scored-tonight pill html (scorers_tonight_v58.badge), placed right after
    the name; '' when he has not scored."""
    ly = f'<span class="ly">{_e(layers)}</span>' if layers else ''
    return (f'<div class="pmr{" sc" if scored else ""}"><span class="rk">{rank}</span><span class="nm"><b title="{_e(name)}">{_e(name)}</b>'
            f'{badge}{pos_html}<small>{_e(team)}</small></span><span class="st">{_e(stat)}</span>{ly}</div>')


def rebuilt_for(x, sys_):
    """Is this system's number on this night a rebuild (not a pre-game freeze)?"""
    if sys_ == 'books':
        return False   # books nights are always frozen pre-game
    return x['kind'] == 'rebuilt' if sys_ == 'blend' else not x.get('saved')


def acc_line(ns, sys_):
    got = [x for x in ns if x.get(sys_) is not None]
    if not got:
        return ('<div class="pmacc">Accuracy: no scored night yet'
                + (' (log started tonight; no odds were saved before it).' if sys_ == 'books' else '.') + '</div>')
    per = ' · '.join(f'{acc.short_day(x["day"])} <b>{x[sys_]}/{_n(x, sys_)}</b>{" (rebuilt)" if rebuilt_for(x, sys_) else ""}' for x in got)
    h, t = sum(x[sys_] for x in got), sum(_n(x, sys_) for x in got)
    return f'<div class="pmacc">Top-{TOP_N} hit, last {len(got)} night{"s" if len(got) != 1 else ""}: <b>{h}/{t}</b> ({100 * h / t:.0f}%) · {per}</div>'


def skipped_days(ns, today, n=TREND_N):
    """Calendar nights in the n before `today` with no scored record (no clean pre-game snapshot)."""
    have = {x['day'] for x in ns}
    d0 = date.fromisoformat(today)
    return [d for d in ((d0 - timedelta(days=i)).isoformat() for i in range(n, 0, -1)) if d not in have]


def column_html(sys_, rows_html, ns, sub, extra=''):
    x = '<span class="pmx">EXPERIMENTAL</span>' if sys_ == 'blend' else ''
    return (f'<div class="pmc" style="--pc:{TONE[sys_]}"><h3>{_e(LABEL[sys_].replace(" (experimental)", ""))}{x}</h3><p class="pmk">{_e(sub)}</p>'
            f'{rows_html or "<p class=pmk>No ranking for this slate yet.</p>"}{acc_line(ns, sys_)}{extra}</div>')


def night_label(x):
    if x.get('saved'):
        return 'saved' + (' · blend rebuilt' if x['kind'] == 'rebuilt' else '')
    return 'rebuilt'


def nights_table(ns):
    if not ns:
        return ''
    body = ''.join(f'<tr><td>{_e(acc.short_day(x["day"]))} <span class="kd">{_e(night_label(x))}</span></td>'
                   + ''.join(f'<td>{"—" if x.get(s) is None else str(x[s]) + "/" + str(_n(x, s))}</td>' for s in SYSTEMS) + '</tr>'
                   for x in reversed(ns))
    return (f'<table class="pmt"><thead><tr><th>Night</th><th>Model</th><th>NP</th><th>Blend</th><th>Books</th></tr></thead>'
            f'<tbody>{body}</tbody></table>')


def _pct(p):
    return '—' if p is None else f'{100 * float(p):.1f}%'


def tonight(day, rankings, games, entry=None, rec=None, cands=None, layers=None, books_rec=None, books_live=None):
    """Tonight's three top-N lists -> {sys: {'rows': [{'rank','name','team','pos','stat','layers','pid'}], 'source': str}}.
    Model: the frozen pre-game accuracy entry for `day` (else parlay_v58.candidates rows, live). NP: Statistical rank
    1..N, Form %. Blend: the frozen blend record for `day` (else computed now from the same model rows + layers)."""
    import pandas as pd
    import pos_tag_v59 as pt
    import ui_theme_v53 as ui
    pmap = pt.pos_map(pd.DataFrame(rankings or []))
    out = {}
    if entry and entry.get('day') == day and entry.get('players'):
        players, msrc = entry['players'], 'frozen pre-game model'
    else:
        players = [[c['pid'], c['name'], c['team'], c['p'], c['model_rank']] for c in cands or [] if c.get('model_rank') is not None]
        msrc = 'live model'
    mrows = sorted(players, key=lambda p: p[4])[:TOP_N]
    out['model'] = {'source': msrc, 'rows': [{'rank': p[4], 'pid': p[0], 'name': p[1], 'team': p[2], 'pos': pt.lookup(pmap, p[0], p[2], p[1]) or '',
                                              'stat': _pct(p[3]), 'layers': ''} for p in mrows]}
    out['np'] = {'source': 'NP statistical leaderboard', 'rows': [
        {'rank': r['_rank'], 'pid': r['_pid'], 'name': r.get('Player'), 'team': r.get('Team'),
         'pos': pt.lookup(pmap, r['_pid'], r.get('Team'), r.get('Player'), r) or '',
         'stat': 'Form ' + ui.format_form_pct(r.get('V3.2 Adjusted Index')), 'layers': ''} for r in np_top(rankings)]}
    if rec and rec.get('day') == day and rec.get('top'):
        brows = [{'rank': i, 'pid': t[0], 'name': t[1], 'team': t[2], 'pos': t[3], 'stat': _pct(t[7]),
                  'layers': f'{t[6]} layer{"s" if t[6] != 1 else ""}' + (' · ' + ' · '.join(t[8]) if t[8] else '') + f' · model {_pct(t[4])}'}
                 for i, t in enumerate(rec['top'], 1)]
        bsrc = f'frozen pre-game · w = {rec["weights"]["w"]} ({rec["weights"]["kind"]})'
    else:
        lay = layers if layers is not None else (layers_for({'day': day, 'rankings': rankings, 'games': games}, day) if rankings else {})
        brows = [{'rank': r['rank'], 'pid': r['pid'], 'name': r['name'], 'team': r['team'],
                  'pos': (lay.get(r['pid']) or {}).get('pos') or pt.lookup(pmap, r['pid'], r['team'], r['name']) or '',
                  'stat': _pct(r['pb']),
                  'layers': f'{r["hits"]} layer{"s" if r["hits"] != 1 else ""}'
                            + (' · ' + ' · '.join(met_labels((lay.get(r['pid']) or {}).get('met'))) if r['hits'] else '') + f' · model {_pct(r["p"])}'}
                 for r in rank_blend(players, {k: v['n'] for k, v in lay.items()})[:TOP_N]]
        bsrc = f'computed now · w = {BLEND_W} ({BLEND_KIND})'
    out['blend'] = {'source': bsrc, 'rows': brows}
    import books_picks_v59 as bp
    bt = bp.tonight_rows(day, books_rec, books_live)
    for r in bt['rows']:
        r['pos'] = pt.lookup(pmap, r['pid'], r['team'], r['name']) or r['pos']
    out['books'] = bt
    return out


SUBS = {'model': 'Ranked by goal chance, 1 − e^(−λ) for tonight’s game',
        'np': 'Statistical rank · V3.2 Adjusted Index as Form %',
        'blend': 'Model chance boosted per gematria layer hit',
        'books': 'Median no-vig anytime-goal chance across books (odds only)'}


def scored_badge(record, pid):
    """V6.0: the shared scored-tonight pill (scorers_tonight_v58) for one listed player, matched by NHL player ID only
    (never by name); '' when there is no record or he has not scored. Display only."""
    import scorers_tonight_v58 as sctn
    rec = sctn.lookup(record, pid=pid) if record and sctn._pid(pid) is not None else None
    return sctn.badge(rec, bool(record.get('demo'))) if rec else ''


def page_html(t, ns, scored=(), record=None):
    """The four columns (2 x 2 under 1180 px, stacked under 700 px). ``record`` (V6.0) is tonight's scorer record
    (scorers_tonight_v58, from the live play-by-play): rows whose player ID scored get the shared 🚨 pill (🚨 nG for 2+)."""
    import pos_tag_v59 as pt
    sc = {int(x) for x in scored or ()} | {int(p) for p in ((record or {}).get('players') or {})}
    cols = []
    for s in SYSTEMS:
        rows = ''.join(_row(r['rank'], r['name'], r['team'], pt.tag(r['pos']) if r.get('pos') else '', r['stat'], r.get('layers'),
                            int(r['pid']) in sc, scored_badge(record, r['pid'])) for r in t[s]['rows'])
        extra = f'<p class="pmf">{_e(__import__("books_picks_v59").COVERAGE_NOTE)}</p>' if s == 'books' else ''
        cols.append(column_html(s, rows, ns, f'{SUBS[s]} · {t[s]["source"]}', extra))
    return f'{CSS}<div class="pm">{"".join(cols)}</div>'


if __name__ == '__main__':
    import argparse
    import sys
    ap = argparse.ArgumentParser(description='V5.9 blend log (experimental prediction system)')
    ap.add_argument('command', choices=['update', 'prune', 'rebuild'])
    ap.add_argument('--keep-days', type=int, default=KEEP_DAYS)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--snapshot')
    ap.add_argument('--source', default='rebuilt from a saved pre-game slate snapshot')
    a = ap.parse_args()
    if a.command == 'update':
        update()
    elif a.command == 'prune':
        gone = prune(a.keep_days, dry_run=a.dry_run)
        print(f'blend prune: {len(gone)} file(s){" (dry run)" if a.dry_run else ""}')
    else:
        r = rebuild(json.loads(Path(a.snapshot).read_text(encoding='utf-8')), source=a.source)
        print('rebuilt' if r else 'not a clean pre-game snapshot: skipped')
    sys.exit(0)
