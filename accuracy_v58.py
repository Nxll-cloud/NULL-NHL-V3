"""V5.8 Home daily accuracy snapshot: yesterday's real goal scorers vs the model's PRE-GAME predictions.

Point-in-time by construction:
  * Predictions are frozen from the precompute workflow's dated slate snapshot (snapshots/YYYY-MM-DD.json) while no
    game of that slate has started (snapshot ``updated_at`` < first puck drop). Rankings in a snapshot are strict
    pre-slate (nhl_data.summarize_games excludes the slate date and later). Once a slate is under way its frozen
    predictions are never rewritten.
  * Model chance = 1 - exp(-lambda_game) from the V5.6 next-goal priors (the same number the Home parlay uses), stored
    at freeze time, so later model changes never rewrite history.
    V5.9: with MODEL_SITUATIONAL on (default) the priors carry the same situational layer as Home / Matchup Center /
    Live Next Goal (situational_v58: PP, goalie, ice time, xG; stats strictly before the slate day). The workflow
    freeze uses the probable starters it can see pre-game; catch-up / backfill / the app's on-the-fly entry have no
    point-in-time starter list, so the goalie part uses each team's goalies weighted by shots against. The entry's
    'model' tag says which model froze it; entries frozen earlier keep their V5.6 numbers.
  * Parlay = rebuilt deterministically from the saved pre-game slate with parlay_v58.build (all games pregame). The
    workflow adds the ESPN 'out' list it can see before puck drop; a git-history backfill has no injury list.
  * Edge Flags need real opening prices. The app only keeps openers in session state and has no odds key, so no flag
    is ever shown (``flags.available`` False, 'n/a (no saved prices)'). If a snapshot ever carries real openers
    (``snapshot['openers'] = {player_id: american_odds}``), flags are recorded with Edge Flags' 3-point rule.
  * Results = real NHL goals (api-web score endpoint, play-by-play fallback), matched to predictions by player ID.
    Shootout goals are excluded (the anytime market ignores them). DEMO data is never read.

Log: one small file per slate in snapshots/accuracy/YYYY-MM-DD.json (well under the 100 KB per-file rule: pending
~20-40 KB on a full slate, compacted to the scorers + top-10 + parlay legs once scored). The workflow writes it
(``python accuracy_v58.py update``); ``backfill`` reads earlier snapshot versions from git history. The app reads the log
and, if a date's log is missing, computes the same entry on the fly from the saved snapshot + live NHL results.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SNAP_DIR = HERE / 'snapshots'
LOG_DIR = Path(os.environ.get('PLAYBOOK_ACCURACY_DIR') or SNAP_DIR / 'accuracy')   # env override: preview/dev only
SCHEMA = 1
TOP_N = 10
TREND_N = 10
ET = ZoneInfo('America/New_York')
NHL = 'https://api-web.nhle.com/v1/'
FINAL = ('OFF', 'FINAL')
MODEL_TAG = 'V5.6 next-goal prior: 1 - exp(-lambda_game)'
MODEL_TAG_SITU = 'V5.9 next-goal prior + situational layer ({parts}): 1 - exp(-lambda_game)'
UA = {'User-Agent': 'NULL-NHL-V5.9 accuracy'}
FLAG_NA = 'flag n/a (no saved prices)'
PARLAY_NOTE = 'parlay rebuilt from the saved pre-game slate'


# ------------------------------------------------------------------------------------------------ dates
def eastern_today(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ET).date()


def eastern_yesterday(now=None):
    return eastern_today(now) - timedelta(days=1)


def _iso(s):
    try:
        d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def first_start(snapshot):
    starts = [_iso(g.get('Start (UTC)')) for g in (snapshot or {}).get('games') or [] if isinstance(g, dict)]
    starts = [s for s in starts if s]
    return min(starts) if starts else None


def is_pregame(snapshot):
    """True when the snapshot was written before the slate's first puck drop."""
    at, fs = _iso((snapshot or {}).get('updated_at')), first_start(snapshot)
    return bool(at and fs and at < fs)


def short_day(day):
    d = date.fromisoformat(day)
    return f'{d:%b} {d.day}'


# ------------------------------------------------------------------------------------------------ predictions
def season_of(day):
    """'2026-10-22' -> '20262027' (NHL seasons start in the autumn)."""
    d = date.fromisoformat(str(day))
    y = d.year if d.month >= 7 else d.year - 1
    return f'{y}{y + 1}'


def situ_for(day, games=(), getter=None, starters=False, environ=None):
    """V5.9: the app's situational layer for ``day`` without Streamlit (feature_flags_v58 MODEL_SITUATIONAL /
    MODEL_SITUATIONAL_PARTS / MODEL_XG from the environment; off -> None = the V5.6 model exactly). ``getter`` is
    requests.get-like. ``starters`` True -> probable starters for the slate (only meaningful before puck drop).
    Never raises: a failed feed leaves its adjustment neutral."""
    import feature_flags_v58 as ff
    import situational_v58 as sit
    if not ff.model_situational(None, environ):
        return None
    if getter is None:
        import requests
        getter = requests.get

    def js(url, params=None):
        r = getter(url, params=params, timeout=20, headers=UA)
        r.raise_for_status()
        return r.json()
    parts = ff.model_parts(None, environ)
    try:
        ctx = sit.load_context(day, season_of(day), parts, js, lambda url: getter(url, timeout=30, headers=UA))
    except Exception:
        ctx = sit.context(parts=parts)
    st = {}
    if starters and 'goalie' in parts:
        try:
            import matchup_center_v54 as mc
            import probable_goalies_v54 as pgk
            st = pgk.fetch_starters(day, mc.slate_games(games), getter=js)[0]
        except Exception:
            st = {}
    return sit.layer(ctx, st)


def predictions(snapshot, out_ids=(), source='snapshot', now=None, injuries_note=None, situ=None):
    """Saved pre-game slate snapshot -> frozen prediction entry (no network). Every skater the model prices is kept.
    ``situ``: the situational layer (situ_for), the same one the app's surfaces use; None = the V5.6 model."""
    import matchup_center_v54 as mc
    import live_nextgoal_v56 as ng
    import live_state_v56 as lstate
    import parlay_v58 as parlay
    rows = [r for r in snapshot.get('rankings') or [] if isinstance(r, dict)]
    games = mc.slate_games(snapshot.get('games') or [])
    priors = ng.priors_from_rankings(rows)
    pre = [dict(g, status='FUT') for g in games]           # a frozen pre-game view: every game is pregame
    results = lstate.slate_results(pre, priors, {}, {}, {}, situ=situ)   # V5.9: the shared calculation + layer
    cands = parlay.candidates(results, rows)               # model chance + model rank for every priced skater
    pdata = parlay.build(results, rows, set(out_ids or ()), {})
    players = [[c['pid'], c['name'], c['team'], round(c['p'], 4), c['model_rank'],
                int(c['np_rank']) if isinstance(c.get('np_rank'), (int, float)) and not math.isnan(c['np_rank']) else None]
               for c in cands]
    flags = {'available': False, 'note': FLAG_NA, 'flagged': []}
    openers = snapshot.get('openers')
    if isinstance(openers, dict) and openers:               # only real saved opening lines ever count
        import edgelab_v55 as el
        import edgeflags_v56 as ef
        fl = []
        for c in cands:
            o = openers.get(str(c['pid']), openers.get(c['pid']))
            try:
                if o is not None and c['p'] - el.american_to_implied(o) >= ef.MIN_EDGE:
                    fl.append(c['pid'])
            except (TypeError, ValueError):
                continue
        flags = {'available': True, 'note': 'real opening lines saved with the snapshot', 'flagged': fl}
    fs = first_start(snapshot)
    tag = MODEL_TAG_SITU.format(parts=', '.join(situ.ctx.get('parts') or ()) or 'none') if situ is not None else MODEL_TAG
    return {'schema': SCHEMA, 'day': snapshot.get('day'), 'source': source, 'model': tag,
            'frozen_at': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds'),
            'snapshot_at': snapshot.get('updated_at'), 'first_start': fs.isoformat() if fs else None,
            'games': [g['game_id'] for g in games], 'n_players': len(players),
            'mean_p': round(sum(p[3] for p in players) / len(players), 4) if players else None,
            'players': players,
            'parlay': {'legs': [l['pid'] for l in pdata.get('legs') or []], 'per': pdata.get('per'), 'short': bool(pdata.get('short')),
                       'derived': True, 'note': PARLAY_NOTE + (' · ' + injuries_note if injuries_note else '')},
            'flags': flags, 'results': None, 'summary': None}


def out_ids_now(snapshot, injuries):
    """ESPN 'out' list (fetched pre-game by the workflow) -> player IDs, matched like the Home parlay does."""
    import storylines_v58 as slx
    outn = slx.out_players(injuries)
    return {r.get('Player ID') and int(float(r['Player ID'])) for r in snapshot.get('rankings') or []
            if (slx.norm(r.get('Player')), r.get('Team')) in outn and r.get('Player ID') is not None}


# ------------------------------------------------------------------------------------------------ results
def _get(getter, path, timeout=12):
    r = getter(NHL + path, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _name(g):
    fn, ln = (g.get('firstName') or {}).get('default'), (g.get('lastName') or {}).get('default')
    return f'{fn} {ln}'.strip() if fn or ln else (g.get('name') or {}).get('default', '')


def positions_from_boxscore(payload):
    """V5.9: boxscore -> {pid: position} from playerByGameStats (forwards / defense / goalies). Real position data only."""
    out = {}
    for side in ('awayTeam', 'homeTeam'):
        t = ((payload or {}).get('playerByGameStats') or {}).get(side) or {}
        for grp, dflt in (('forwards', None), ('defense', 'D'), ('goalies', 'G')):
            for x in t.get(grp) or []:
                pos = x.get('position') or x.get('positionCode') or dflt
                if x.get('playerId') is not None and pos:
                    out[int(x['playerId'])] = str(pos).strip().upper()
    return out


def positions_from_pbp(payload):
    """V5.9: play-by-play rosterSpots -> {pid: positionCode}."""
    return {int(s['playerId']): str(s['positionCode']).strip().upper() for s in (payload or {}).get('rosterSpots') or []
            if s.get('playerId') is not None and s.get('positionCode')}


def goals_from_pbp(payload):
    """Play-by-play -> [(pid, name, team)] per non-shootout goal."""
    teams = {(payload.get(k) or {}).get('id'): (payload.get(k) or {}).get('abbrev') for k in ('awayTeam', 'homeTeam')}
    names = {s.get('playerId'): f"{(s.get('firstName') or {}).get('default', '')} {(s.get('lastName') or {}).get('default', '')}".strip()
             for s in payload.get('rosterSpots') or []}
    out = []
    for p in payload.get('plays') or []:
        if p.get('typeDescKey') != 'goal' or (p.get('periodDescriptor') or {}).get('periodType') == 'SO':
            continue
        d = p.get('details') or {}
        pid = d.get('scoringPlayerId')
        if pid is not None:
            out.append((int(pid), names.get(pid, str(pid)), teams.get(d.get('eventOwnerTeamId'), '')))
    return out


def results_from_score(payload, pbp_fn=None, box_fn=None):
    """score/{day} payload -> {'complete', 'n_games', 'scorers': [[pid, name, team, goals]]} (final games only).
    A final game whose goal list does not add up to its non-shootout score is re-read from play-by-play (pbp_fn).
    V5.9: 'positions' = {str(pid): position} for scorers, from that game's boxscore (box_fn) or play-by-play rosterSpots.
    The score feed's goals carry no position; a failed lookup simply leaves the scorer without one."""
    games = [g for g in (payload or {}).get('games') or [] if str(g.get('gameScheduleState', 'OK')) == 'OK']
    final = [g for g in games if str(g.get('gameState')) in FINAL]
    tally, pos = {}, {}
    for g in final:
        goals = [x for x in g.get('goals') or [] if (x.get('periodDescriptor') or {}).get('periodType') != 'SO']
        rows = [(int(x['playerId']), _name(x), x.get('teamAbbrev') or '') for x in goals if x.get('playerId') is not None]
        a, h = (g.get('awayTeam') or {}).get('score') or 0, (g.get('homeTeam') or {}).get('score') or 0
        so = 1 if (g.get('periodDescriptor') or {}).get('periodType') == 'SO' or (g.get('gameOutcome') or {}).get('lastPeriodType') == 'SO' else 0
        if len(rows) != a + h - so and pbp_fn is not None:
            try:
                pbp = pbp_fn(g['id'])
                rows = goals_from_pbp(pbp)
                pos.update({k: v for k, v in positions_from_pbp(pbp).items() if k in {r[0] for r in rows}})
            except Exception:
                pass
        if box_fn is not None and any(r[0] not in pos for r in rows):
            try:
                bx = positions_from_boxscore(box_fn(g['id']))
                pos.update({r[0]: bx[r[0]] for r in rows if r[0] in bx})
            except Exception:
                pass
        for pid, name, team in rows:
            t = tally.setdefault(pid, [pid, name, team, 0])
            t[3] += 1
    return {'complete': bool(games) and len(final) == len(games), 'n_games': len(final),
            'scorers': sorted(tally.values(), key=lambda r: (-r[3], r[1])),
            'positions': {str(k): v for k, v in pos.items() if k in tally}}


def fetch_results(day, getter):
    return results_from_score(_get(getter, f'score/{day}'), lambda gid: _get(getter, f'gamecenter/{int(gid)}/play-by-play'),
                              lambda gid: _get(getter, f'gamecenter/{int(gid)}/boxscore'))


# ------------------------------------------------------------------------------------------------ scoring
def score(entry, results, now=None, compact=True):
    """Attach real results + a summary to a frozen prediction entry (pure)."""
    e = dict(entry)
    pred = {p[0]: p for p in e.get('players') or []}
    legs = list((e.get('parlay') or {}).get('legs') or [])
    flagged = set((e.get('flags') or {}).get('flagged') or [])
    scorers = results['scorers']
    sids = {s[0] for s in scorers}
    top = [p[0] for p in sorted(pred.values(), key=lambda p: p[4])[:TOP_N]]
    modeled = [pred[s] for s in sids if s in pred]
    e['results'] = {'fetched_at': (now or datetime.now(timezone.utc)).isoformat(timespec='seconds'),
                    'n_games': results['n_games'], 'scorers': scorers}
    if results.get('positions'):
        e['results']['positions'] = results['positions']   # V5.9: scorer positions by player ID (goalie pill)
    e['summary'] = {'n_scorers': len(scorers), 'n_modeled_scorers': len(modeled),
                    'top_hits': sum(1 for p in top if p in sids), 'top_n': len(top),
                    'parlay_hits': sum(1 for p in legs if p in sids), 'parlay_legs': len(legs),
                    'flag_hits': sum(1 for p in flagged if p in sids) if (e.get('flags') or {}).get('available') else None,
                    'flag_n': len(flagged) if (e.get('flags') or {}).get('available') else None,
                    'avg_p_scorers': round(sum(p[3] for p in modeled) / len(modeled), 4) if modeled else None,
                    'mean_p': e.get('mean_p'), 'n_players': e.get('n_players'),
                    'realized': round(len(modeled) / len(pred), 4) if pred else None}
    if compact:   # rolling compaction: keep only what the card can show
        keep = sids | set(top) | set(legs) | flagged
        e['players'] = [p for p in e.get('players') or [] if p[0] in keep]
        e['compacted'] = True
    return e


def rows(entry, positions=None):
    """Card rows: one per real scorer, best model rank first (unpriced scorers last).
    V5.9: 'position' by player ID from the stored results positions, else `positions` (e.g. the saved slate's roster
    Position column); None when unknown -> no goalie pill."""
    pred = {p[0]: p for p in entry.get('players') or []}
    known = {str(k): v for k, v in (positions or {}).items()}
    known.update((entry.get('results') or {}).get('positions') or {})
    legs = set((entry.get('parlay') or {}).get('legs') or [])
    fl = entry.get('flags') or {}
    out = []
    for pid, name, team, goals in (entry.get('results') or {}).get('scorers') or []:
        p = pred.get(pid)
        out.append({'pid': pid, 'name': name, 'team': team, 'goals': goals, 'p': p[3] if p else None,
                    'rank': p[4] if p else None, 'np_rank': p[5] if p else None, 'parlay': pid in legs,
                    'flag': (pid in set(fl.get('flagged') or [])) if fl.get('available') else None,
                    'position': known.get(str(pid))})
    return sorted(out, key=lambda r: (r['rank'] is None, r['rank'] or 0, r['name']))


def trend(entries, n=TREND_N):
    """Last n scored nights (oldest first) + pooled totals."""
    done = sorted((e for e in entries if e.get('summary')), key=lambda e: e['day'])[-n:]
    nights = [{'day': e['day'], 'top_hits': e['summary']['top_hits'], 'top_n': e['summary']['top_n'],
               'rate': e['summary']['top_hits'] / e['summary']['top_n'] if e['summary']['top_n'] else None,
               'avg_p_scorers': e['summary']['avg_p_scorers'], 'mean_p': e['summary']['mean_p'],
               'realized': e['summary']['realized']} for e in done]
    hits, tot = sum(x['top_hits'] for x in nights), sum(x['top_n'] for x in nights)
    def avg(k):
        v = [x[k] for x in nights if x[k] is not None]
        return sum(v) / len(v) if v else None
    return {'nights': nights, 'top_hits': hits, 'top_n': tot, 'top_rate': hits / tot if tot else None,
            'avg_p_scorers': avg('avg_p_scorers'), 'mean_p': avg('mean_p'), 'realized': avg('realized')}


# ------------------------------------------------------------------------------------------------ log I/O
def log_path(day, root=LOG_DIR):
    date.fromisoformat(day)
    return Path(root) / f'{day}.json'


def load_entry(day, root=LOG_DIR):
    p = log_path(day, root)
    try:
        e = json.loads(p.read_text(encoding='utf-8'))
        return e if isinstance(e, dict) and e.get('schema') == SCHEMA and e.get('day') == day else None
    except (OSError, ValueError):
        return None


def load_all(root=LOG_DIR):
    out = []
    for p in sorted(Path(root).glob('????-??-??.json')) if Path(root).is_dir() else []:
        e = load_entry(p.stem, root)
        if e:
            out.append(e)
    return out


def save_entry(entry, root=LOG_DIR):
    p = log_path(entry['day'], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(entry, separators=(',', ':'), ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(tmp, p)
    return p


def _load_snap(day, snap_root):
    import snapshot_store
    return snapshot_store.load_snapshot(day, snap_root)


# ------------------------------------------------------------------------------------------------ workflow
def update(now=None, getter=None, snap_root=SNAP_DIR, root=LOG_DIR, injuries_fn=None, log=print):
    """Precompute step: freeze today's predictions while pre-game, then score every pending slate that is final.
    Never raises (the snapshot commit must not be blocked by a results-feed hiccup)."""
    import requests
    getter = getter or requests.get
    now = now or datetime.now(timezone.utc)
    today = eastern_today(now).isoformat()
    done = []
    try:
        snap = _load_snap(today, snap_root)
        cur = load_entry(today, root)
        fs = first_start(snap) if snap else None
        if snap and snap.get('rankings') and fs and now < fs and is_pregame(snap) and not (cur and cur.get('results')):
            out, note = set(), None
            try:
                inj = injuries_fn() if injuries_fn else __import__('storylines_v58').espn_fetch('injuries')
                out = out_ids_now(snap, inj)
                note = f'ESPN out list at freeze time ({len(out)} out)'
            except Exception as exc:
                note = f'no injury list ({type(exc).__name__})'
            save_entry(predictions(snap, out, 'workflow', now, note, situ_for(today, snap.get('games'), getter, starters=True)), root)
            done.append(f'froze {today}')
    except Exception as exc:
        log(f'accuracy: freeze skipped ({type(exc).__name__}: {exc})')
    # catch-up: a dated snapshot that is still a clean pre-game record but has no log entry yet
    for p in sorted(Path(snap_root).glob('????-??-??.json')):
        day = p.stem
        if day >= today or load_entry(day, root):
            continue
        snap = _load_snap(day, snap_root)
        if snap and snap.get('rankings') and is_pregame(snap):
            save_entry(predictions(snap, (), 'workflow catch-up', now, situ=situ_for(day, getter=getter)), root)
            done.append(f'caught up {day}')
    for e in load_all(root):
        if e.get('results') or e['day'] >= today:
            continue
        try:
            res = fetch_results(e['day'], getter)
        except Exception as exc:
            log(f'accuracy: results for {e["day"]} unavailable ({type(exc).__name__})')
            continue
        if res['complete']:
            save_entry(score(e, res, now), root)
            done.append(f'scored {e["day"]}')
    log('accuracy: ' + (', '.join(done) or 'nothing to do'))
    return done


def history_versions(repo=HERE):
    """Every committed version of snapshots/YYYY-MM-DD.json in git history -> {day: [(commit, snapshot)]}."""
    out = {}
    try:
        commits = subprocess.run(['git', '-C', str(repo), 'log', '--all', '--format=%H', '--', 'snapshots/'],
                                 capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return out
    for c in commits:
        names = subprocess.run(['git', '-C', str(repo), 'ls-tree', '--name-only', c, 'snapshots/'],
                               capture_output=True, text=True).stdout.split()
        for n in names:
            day = Path(n).stem
            if Path(n).suffix != '.json' or len(day) != 10:
                continue
            try:
                date.fromisoformat(day)
                snap = json.loads(subprocess.run(['git', '-C', str(repo), 'show', f'{c}:{n}'], capture_output=True, text=True, check=True).stdout)
            except (ValueError, subprocess.CalledProcessError):
                continue
            if isinstance(snap, dict) and snap.get('day') == day:
                out.setdefault(day, []).append((c, snap))
    return out


def backfill(repo=HERE, root=LOG_DIR, getter=None, now=None, log=print):
    """Freeze predictions for every past date with a saved pre-game snapshot version in git history (latest version
    stamped before first puck drop), then score the ones whose games are final."""
    import requests
    getter = getter or requests.get
    now = now or datetime.now(timezone.utc)
    report = {}
    for day, versions in sorted(history_versions(repo).items()):
        pre = [(c, s) for c, s in versions if s.get('rankings') and is_pregame(s)]
        if not pre:
            report[day] = f'{len(versions)} version(s), none stamped before puck drop'
            continue
        c, snap = max(pre, key=lambda cs: _iso(cs[1]['updated_at']))
        cur = load_entry(day, root)
        if cur and cur.get('results'):
            report[day] = 'already scored'
            continue
        if not cur:
            cur = predictions(snap, (), f'backfill git {c[:7]}', now, 'no injury list in git history', situ_for(day, getter=getter))
            save_entry(cur, root)
        msg = f'frozen from {c[:7]} (snapshot {snap["updated_at"][:19]}Z, first puck drop {cur["first_start"]})'
        try:
            res = fetch_results(day, getter)
            if res['complete'] and day < eastern_today(now).isoformat():
                save_entry(score(cur, res, now), root)
                msg += f' · scored {res["n_games"]} final games'
            else:
                msg += f' · results pending ({res["n_games"]} final)'
        except Exception as exc:
            msg += f' · results unavailable ({type(exc).__name__})'
        report[day] = msg
    for d, m in report.items():
        log(f'{d}: {m}')
    return report


# ------------------------------------------------------------------------------------------------ app view
_LIVE = {}
_LIVE_TTL = 900


def _live_entry(day, getter, snap_root):
    """On-the-fly entry when the log is missing: saved pre-game snapshot + live NHL results (cached 15 min)."""
    hit = _LIVE.get(day)
    if hit and time.time() - hit[0] < _LIVE_TTL:
        return hit[1]
    val, why = None, None
    snap = _load_snap(day, snap_root)
    if not snap:
        why = 'no_snapshot'
    elif not is_pregame(snap):
        why = 'not_pregame'
    else:
        try:
            res = fetch_results(day, getter)
            ent = predictions(snap, (), 'app on-the-fly', situ=situ_for(day, getter=getter))
            val = score(ent, res) if res['complete'] else ent
            why = None if res['complete'] else 'pending'
        except Exception:
            why = 'results_unavailable'
    _LIVE[day] = (time.time(), (val, why))
    return val, why


def view(now=None, getter=None, root=LOG_DIR, snap_root=SNAP_DIR, lookback=7):
    """Which slate the card shows, and why. Pure apart from the log/snapshot reads and (log missing) NHL results."""
    if getter is None:
        import requests
        getter = requests.get
    now = now or datetime.now(timezone.utc)
    y = eastern_yesterday(now).isoformat()
    entries = {e['day']: e for e in load_all(root)}
    notes = []

    def resolve(day):
        e = entries.get(day)
        if e and e.get('summary'):
            return e, None
        if e:   # frozen, results not stored yet (workflow has not run since the games ended)
            try:
                res = fetch_results(day, getter)
                if res['complete']:
                    return score(e, res), None
            except Exception:
                return None, 'results_unavailable'
            return None, 'pending'
        val, why = _live_entry(day, getter, snap_root)
        return (val, None) if val and val.get('summary') else (None, why)

    shown, why_y = resolve(y)
    if not shown:
        notes.append({'no_snapshot': f'No saved pre-game predictions for {short_day(y)}.',
                      'not_pregame': f'The saved {short_day(y)} snapshot was written after puck drop, so it is not a clean pre-game record.',
                      'pending': f'{short_day(y)} results are not final yet.',
                      'results_unavailable': f'{short_day(y)} results could not be loaded from the NHL feed.'}.get(why_y, f'No {short_day(y)} data.'))
        cands = sorted({d for d in entries if d < y} | {p.stem for p in Path(snap_root).glob('????-??-??.json') if p.stem < y}, reverse=True)
        for d in cands[:lookback]:
            shown, _ = resolve(d)
            if shown:
                notes.append(f'Showing the most recent completed slate: {short_day(d)}.')
                break
    for d, e in entries.items():   # keep scored on-the-fly results in the trend too
        if not e.get('summary') and shown and d == shown['day']:
            entries[d] = shown
    if shown:
        entries[shown['day']] = shown
    pending = [e for d, e in sorted(entries.items()) if not e.get('summary') and d > (shown or {}).get('day', '')]
    return {'yesterday': y, 'shown': shown, 'notes': notes, 'trend': trend(list(entries.values())),
            'pending': pending[-1] if pending else None}


# ------------------------------------------------------------------------------------------------ presentation
CSS = ('<style>.v55 .npacc{margin:14px 0 6px;padding:14px 16px;border-radius:18px;border:1px solid color-mix(in srgb,var(--neon) 30%,transparent);'
       'background:linear-gradient(135deg,rgba(56,225,255,.07),rgba(178,107,255,.08));min-width:0}'
       '.v55 .npacc-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}'
       '.v55 .npacc-h b{color:var(--ink);font:800 .95rem var(--fd);letter-spacing:.08em;text-transform:uppercase}'
       '.v55 .npacc-h span{color:var(--neon);font:700 .86rem var(--fb);font-variant-numeric:tabular-nums}'
       '.v55 .npacc p{margin:6px 0 0;color:var(--mut);font-size:.82rem;line-height:1.45}'
       '.v55 .npacc-tw{margin-top:8px;overflow-x:auto;-webkit-overflow-scrolling:touch}'
       '.v55 .npacc-t{width:100%;border-collapse:collapse;font-size:.82rem;color:var(--ink);font-variant-numeric:tabular-nums}'
       '.v55 .npacc-t th{padding:4px 6px;text-align:left;color:var(--mut);font:700 .76rem var(--fb);letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;border-bottom:1px solid var(--line)}'
       '.v55 .npacc-t td{padding:5px 6px;border-bottom:1px solid var(--line);vertical-align:top}'
       '.v55 .npacc-t td.n{white-space:nowrap;text-align:right}.v55 .npacc-t th.n{text-align:right}'
       '.v55 .npacc-t tr.top td:first-child{box-shadow:inset 2px 0 0 var(--neon)}'
       '.v55 .npacc-t .ok{color:var(--ok);font-weight:800}.v55 .npacc-t .dim{color:var(--dim)}'
       '.v55 .npacc details summary{cursor:pointer;color:var(--neon);font:700 .82rem var(--fb);min-height:44px;display:flex;align-items:center}'
       '.v55 .npacc-tr{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin-top:8px;color:var(--mut);font-size:.82rem}'
       '.v55 .npacc-tr svg{flex:none}.v55 .npacc-tr b{color:var(--ink)}'
       '.v55 .npacc-empty{color:var(--mut);font-size:.86rem;text-align:left}.v55 .npacc-h{justify-content:flex-start;text-align:left}'
       '.v55 .npacc-t td:first-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:0;width:100%}'
       '.v55 .npacc{display:block;width:100%;box-sizing:border-box;text-align:left;align-self:stretch}.v55 .npacc-tw,.v55 .npacc details{width:100%}.v55 .npacc-t td.n,.v55 .npacc-t td:nth-child(2){width:1%}'
       '.v55 .npacc,.v55 .npacc p{text-align:left}.v55 .npacc-tw{max-width:720px}'
       '.v55 .npacc-tr{justify-content:flex-start}.v55 .npacc-t .sn{display:none}@media (max-width:600px){.v55 .npacc{padding:12px}.v55 .npacc-t th{letter-spacing:0;padding:4px 3px}.v55 .npacc-t td{padding:5px 3px}.v55 .npacc-t .fn{display:none}.v55 .npacc-t .sn{display:inline}}</style>')


def _pct(p):
    return '—' if p is None else f'{p * 100:.0f}%'


def spark(nights, w=96, h=22):
    pts = [x['rate'] for x in nights if x['rate'] is not None]
    if len(pts) < 2:
        return ''
    step = w / (len(pts) - 1)
    xy = ' '.join(f'{i * step:.1f},{h - 2 - v * (h - 4):.1f}' for i, v in enumerate(pts))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Top-10 hit rate, last {len(pts)} nights">'
            f'<polyline points="{xy}" fill="none" stroke="var(--neon)" stroke-width="2" stroke-linejoin="round"/></svg>')


def snapshot_positions(day, snap_root=SNAP_DIR):
    """V5.9: {pid: Position} from that day's saved slate rankings (roster data). {} if missing."""
    try:
        snap = _load_snap(day, snap_root) or {}
        return {str(int(float(r['Player ID']))): str(r['Position']).strip().upper() for r in snap.get('rankings') or []
                if isinstance(r, dict) and r.get('Player ID') not in (None, '') and r.get('Position')}
    except Exception:
        return {}


def card_html(v, max_rows=8, snap_root=SNAP_DIR):
    import position_badge_v59 as pb
    import v55_ui as v5
    esc = v5.esc
    shown, tr = v.get('shown'), v.get('trend') or {}
    notes = ' '.join(esc(n) for n in v.get('notes') or [])
    pend = v.get('pending')
    pend_line = (f'<p>{esc(short_day(pend["day"]))} is logged pre-game ({pend.get("n_players", 0)} skaters priced, '
                 f'{len((pend.get("parlay") or {}).get("legs") or [])}-leg parlay); it is scored once its games are final.</p>') if pend else ''
    if not shown:
        return (f'{CSS}<section class="npacc" aria-label="Daily accuracy snapshot"><div class="npacc-h"><b>Model accuracy · yesterday</b></div>'
                f'<p class="npacc-empty">{notes + " " if notes else ""}No completed slate with saved pre-game predictions yet, so there is '
                f'nothing to score. The running trend starts with the first scored night.</p>{pend_line}</section>')
    s = shown['summary']
    flags_on = s.get('flag_n') is not None
    head = (f'{short_day(shown["day"])} · {s["n_scorers"]} scorers · model top-{s["top_n"]} hit {s["top_hits"]}/{s["top_n"]}'
            + (f' · parlay {s["parlay_hits"]}/{s["parlay_legs"]} legs' if s['parlay_legs'] else ''))
    rs = rows(shown, snapshot_positions(shown['day'], snap_root))
    top = {p[0] for p in sorted(shown.get('players') or [], key=lambda p: p[4])[:TOP_N]}

    def tr_(r):
        rank = f'#{r["rank"]}' if r['rank'] else '<span class="dim">—</span>'
        tip = f' title="NP statistical rank #{r["np_rank"]}"' if r.get('np_rank') else ''
        nm = r['name'] or ''
        short = (nm.split(' ', 1)[0][:1] + '. ' + nm.split(' ', 1)[1]) if ' ' in nm else nm
        name = (f'<span class="fn">{esc(nm)}</span><span class="sn" title="{esc(nm)}">{esc(short)}</span>'
                + pb.goalie_badge(pb.position_of(r))) + (f' ×{r["goals"]}' if r['goals'] > 1 else '')
        flag = (f'<td class="n">{"<span class=ok>✓</span>" if r["flag"] else "·"}</td>') if flags_on else ''
        return (f'<tr class="{"top" if r["pid"] in top else ""}"><td>{name}</td><td>{esc(r["team"])}</td><td class="n">{_pct(r["p"])}</td>'
                f'<td class="n"{tip}>{rank}</td><td class="n">{"<span class=ok>✓</span>" if r["parlay"] else "·"}</td>{flag}</tr>')
    th = ('<tr><th>Scorer</th><th>Team</th><th class="n">Model %</th><th class="n">Rank</th>'
          f'<th class="n" title="{esc(PARLAY_NOTE)}">Parlay ✓</th>{"<th class=n>Flag</th>" if flags_on else ""}</tr>')
    body = ''.join(tr_(r) for r in rs[:max_rows])
    more = ''.join(tr_(r) for r in rs[max_rows:])
    table = f'<div class="npacc-tw"><table class="npacc-t"><thead>{th}</thead><tbody>{body}</tbody></table></div>'
    if more:
        table += (f'<details><summary>Show all {len(rs)} scorers</summary><div class="npacc-tw"><table class="npacc-t"><thead>{th}</thead>'
                  f'<tbody>{more}</tbody></table></div></details>')
    n = tr.get('nights') or []
    trend_line = ''
    if n:
        trend_line = (f'<div class="npacc-tr"><span>Last {len(n)} night{"s" if len(n) != 1 else ""}: top-10 hit <b>{tr["top_hits"]}/{tr["top_n"]}</b>'
                      f' ({_pct(tr["top_rate"])})</span>{spark(n)}<span>scorers averaged <b>{_pct(tr["avg_p_scorers"])}</b> model chance vs '
                      f'<b>{_pct(tr["mean_p"])}</b> slate average · <b>{_pct(tr["realized"])}</b> of priced skaters scored</span></div>')
    unpriced = s['n_scorers'] - s['n_modeled_scorers']
    foot = (f'<p class="npacc-f">Pre-game chances frozen from the saved slate ({esc(str(shown.get("snapshot_at", ""))[:16].replace("T", " "))} UTC); '
            f'real NHL goals matched by player ID; marked rows = model top {s["top_n"]}. '
            f'{"Parlay ✓ = " + esc(PARLAY_NOTE) + ". " if s["parlay_legs"] else ""}'
            f'{"" if flags_on else esc(FLAG_NA.capitalize()) + ". "}'
            f'{f"{unpriced} unpriced (under 3 GP / not on slate)." if unpriced else ""}</p>')
    return (f'{CSS}<section class="npacc" aria-label="Daily accuracy snapshot"><div class="npacc-h"><b>Model accuracy</b><span>{esc(head)}</span></div>'
            f'{f"<p>{notes}</p>" if notes else ""}{table}{trend_line}{foot}{pend_line}</section>')


def home_html(now=None, getter=None):
    """Home entry point (never raises)."""
    try:
        return card_html(view(now, getter))
    except Exception as exc:
        return (f'{CSS}<section class="npacc"><div class="npacc-h"><b>Model accuracy</b></div>'
                f'<p class="npacc-empty">Accuracy snapshot unavailable ({type(exc).__name__}).</p></section>')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='V5.8 Home accuracy log')
    ap.add_argument('command', choices=['update', 'backfill', 'show'])
    a = ap.parse_args()
    if a.command == 'update':
        update()
    elif a.command == 'backfill':
        backfill()
    else:
        print(json.dumps({k: v for k, v in view().items() if k != 'shown'}, indent=1, default=str)[:4000])
    sys.exit(0)
