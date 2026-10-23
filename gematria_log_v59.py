"""V5.9 gematria history: one dated record per slate night, snapshots/gematria/YYYY-MM-DD.json.

* FROZEN ONCE before the slate's first puck drop from that day's slate snapshot (snapshots/YYYY-MM-DD.json), using the
  same functions as the Numbers page (numerology_v48.analyze_game, player_targets_v49.slate_targets,
  gem_match_v58.match_table), so a record can never disagree with what the page showed. The matches are never rewritten
  after the freeze; the only later write adds the 'results' section. A record written after the first puck drop (the
  workflow missed the window) carries frozen_late=True. Records rebuilt after the fact must carry reconstructed=True
  (there is no backfill: history starts 2026-10-23).
* Header: day, universal day, freeze time, method version + a hash of the cipher code (so a method change never mixes
  silently with older records).
* Results (next run after the slate is final): real scorers from accuracy_v58's NHL score feed (shootout goals excluded,
  play-by-play fallback); postponed / not-OK games are listed and excluded; every matched player gets scored true/false.
* Retention: prune deletes records whose FILENAME date (America/New_York slate date) is more than keep_days (90) old;
  only exact YYYY-MM-DD.json names, and only inside snapshots/gematria/ (hard lock).
CLI (precompute workflow): python gematria_log_v59.py update | prune --keep-days 90 [--dry-run]
Recreational number coincidences, never a scoring signal."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SNAP_DIR = HERE / 'snapshots'
ROOT = Path(os.environ.get('PLAYBOOK_GEMATRIA_DIR') or SNAP_DIR / 'gematria')   # env override: tests / preview only
ET = ZoneInfo('America/New_York')
SCHEMA = 1
METHOD_VERSION = 'gem-v1'   # V5.8 ciphers: English ordinal, full reduction, reverse ordinal; digit roots
KEEP_DAYS = 90
MAX_BYTES = 95 * 1024       # repo rule: every file < 100 KB
KINDS = ('date', 'team', 'arena')
FIELDS = ('ordinal_root', 'reduction_root', 'reverse_root')
_NAME = re.compile(r'^(\d{4}-\d{2}-\d{2})\.json$')


# ------------------------------------------------------------------------------------------------ helpers
def _iso(s):
    try:
        d = datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def eastern_today(now=None):
    now = now or datetime.now(timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.astimezone(ET).date()


def short_day(day):
    d = date.fromisoformat(day)
    return f'{d:%b} {d.day}'


def first_start(snapshot):
    s = [_iso(g.get('Start (UTC)')) for g in (snapshot or {}).get('games') or [] if isinstance(g, dict)]
    s = [x for x in s if x]
    return min(s) if s else None


def team_names():
    from home_leaders_v52 import TEAM_NAMES   # same dict as the Numbers page's _TEAM_NAMES (tabs/research.py)
    return dict(TEAM_NAMES)


def method_hash():
    """12-hex hash of every piece of code that decides a match (ciphers, day number, team names, match rules)."""
    import gem_match_v58 as gm
    import numerology_v48 as nu
    import player_targets_v49 as pt
    parts = [inspect.getsource(f) for f in (nu.digit_root, nu.universal_day, nu.letters, nu.gematria, nu.analyze_game,
                                             pt._first_hit, pt.target_rows, gm.arena_number, gm.player_matches, gm.match_table)]
    parts += [repr(pt.METHODS), repr(pt.DAY_METHODS), repr(pt.NAME_METHODS), repr(gm.MATCH_TYPES), json.dumps(team_names(), sort_keys=True)]
    return hashlib.sha256('\n'.join(parts).encode()).hexdigest()[:12]


def _gid(g):
    try:
        return int(g.get('Game ID') or g.get('game_id'))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ build
def build(snapshot, now=None, source='workflow', reconstructed=False):
    """Slate snapshot -> gematria record (no 'results'). Same code path as the Numbers page."""
    import pandas as pd
    import gem_match_v58 as gm
    from numerology_v48 import analyze_game, gematria, universal_day
    from player_targets_v49 import slate_targets
    now = now or datetime.now(timezone.utc)
    day = snapshot['day']
    uday = universal_day(day)
    fs = first_start(snapshot)
    names = team_names()
    raw_games = [g for g in snapshot.get('games') or [] if isinstance(g, dict)]
    analyses = [analyze_game(g, day, names) for g in raw_games]
    ranked = pd.DataFrame(snapshot.get('rankings') or [])
    targets = slate_targets(analyses, ranked, day) if analyses else []
    rows, missing = gm.match_table(targets, uday)
    games = []
    for g, a in zip(raw_games, analyses):
        an = gm.arena_number(a['arena'])
        ga = gematria(a['arena']) if an is not None else None
        games.append({'gid': _gid(g), 'game': f"{a['away']}@{a['home']}", 'away': a['away'], 'home': a['home'],
                      'start': a.get('start'), 'arena': a['arena'] or '',
                      'arena_eng': [ga['ordinal'], ga['ordinal_root']] if ga else None,
                      'arena_rev': [ga['reverse'], ga['reverse_root']] if ga else None,
                      'arena_red': ga['reduction_root'] if ga else None,
                      'team_matches': a.get('matches') or []})
    by_team = {}
    for gg in games:
        by_team[gg['away']] = by_team[gg['home']] = gg['game']
    table = {}
    for r in rows:   # the Numbers page table: date / arena rows with the ciphers that hit
        table.setdefault(str(r['player_id']) or (r['team'], r['Player']), {})[r['Match type']] = [c['field'] for c in r['calc'] if c['hit']]
    matched, everyone, seen = [], [], set()
    for s in targets:
        for t in list(s.get('away_targets') or []) + list(s.get('home_targets') or []):
            key = str(t.get('player_id') or '') or (t.get('team'), t.get('player'))
            if key in seen:
                continue
            seen.add(key)
            v = t['values']
            pid = int(t['player_id']) if str(t.get('player_id') or '').isdigit() else None
            everyone.append([pid, t['team'], v['ordinal'], v['reverse']])
            hit = dict(table.get(key) or {})
            if t.get('team_matches'):
                hit['team'] = ['ordinal_root']   # target_rows compares team names with English only
            if not hit:
                continue
            matched.append({'pid': pid, 'name': t['player'], 'team': t['team'], 'game': by_team.get(t['team'], ''),
                            'eng': [v['ordinal'], v['ordinal_root']], 'rev': [v['reverse'], v['reverse_root']],
                            'match': {k: hit[k] for k in KINDS if k in hit}})
    rec = {'schema': SCHEMA, 'day': day, 'universal_day': uday, 'method_version': METHOD_VERSION, 'method_hash': method_hash(),
           'frozen_at': now.isoformat(timespec='seconds'), 'snapshot_at': snapshot.get('updated_at'),
           'first_start': fs.isoformat() if fs else None, 'frozen_late': bool(fs and now >= fs),
           'reconstructed': bool(reconstructed), 'source': source, 'no_games': not raw_games,
           'games': games, 'games_without_arena': missing,
           'counts': {k: sum(k in m['match'] for m in matched) for k in KINDS},
           'matched': matched, 'players': everyone, 'players_cols': ['pid', 'team', 'eng_total', 'rev_total']}
    if not raw_games:
        rec['results'] = {'complete': True, 'fetched_at': rec['frozen_at'], 'n_games': 0, 'postponed': [], 'scorers': [], 'scored': {}}
    if len(_dump(rec)) >= MAX_BYTES:   # keep under the repo's 100 KB rule: the all-player list goes first
        rec['players'], rec['players_dropped'] = [], True
    return rec


def _dump(rec):
    return json.dumps(rec, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


# ------------------------------------------------------------------------------------------------ I/O
def path_for(day, root=None):
    date.fromisoformat(day)
    return Path(root or ROOT) / f'{day}.json'


def load(day, root=None):
    try:
        r = json.loads(path_for(day, root).read_text(encoding='utf-8'))
        return r if isinstance(r, dict) and r.get('schema') == SCHEMA and r.get('day') == day else None
    except (OSError, ValueError):
        return None


def save(rec, root=None):
    p = path_for(rec['day'], root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(_dump(rec), encoding='utf-8')
    os.replace(tmp, p)
    return p


def _load_snap(day, snap_root):
    try:
        s = json.loads((Path(snap_root) / f'{day}.json').read_text(encoding='utf-8'))
        return s if isinstance(s, dict) and s.get('day') == day and isinstance(s.get('games'), list) else None
    except (OSError, ValueError):
        return None


def freeze(snapshot, root=None, now=None, source='workflow'):
    """Write the day's record once. An existing record is NEVER rewritten (returns None)."""
    if load(snapshot['day'], root):
        return None
    if snapshot.get('games') and not snapshot.get('rankings'):
        return None   # rankings not loaded yet: wait for the next run
    return save(build(snapshot, now, source), root)


# ------------------------------------------------------------------------------------------------ results
def join_results(rec, payload, results):
    """Attach the results section. payload = NHL score/{day}; results = accuracy_v58.results_from_score(payload)."""
    by_gid = {int(g['id']): g for g in (payload or {}).get('games') or [] if g.get('id') is not None}
    postponed = []
    for gg in rec.get('games') or []:
        g = by_gid.get(gg.get('gid'))
        if g is None or str(g.get('gameScheduleState', 'OK')) != 'OK':
            postponed.append(gg['game'])
    sc = {int(s[0]): s for s in results.get('scorers') or []}
    live_games = {gg['game'] for gg in rec.get('games') or []} - set(postponed)
    scored = {}
    for m in rec.get('matched') or []:
        s = sc.get(m['pid']) if m.get('pid') is not None else None
        # scored in the game the record matched him to (a scorer whose team is not in that game does not count)
        ok = bool(s and m['game'] in live_games and s[2] in m['game'].split('@'))
        scored[str(m['pid'])] = int(s[3]) if ok else 0
    out = dict(rec)
    out['results'] = {'complete': True, 'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      'n_games': results.get('n_games', 0), 'postponed': postponed,
                      'scorers': [list(s[:4]) for s in results.get('scorers') or []], 'scored': scored}
    return out


def fetch_and_join(rec, getter):
    import accuracy_v58 as acc
    payload = acc._get(getter, f"score/{rec['day']}")
    res = acc.results_from_score(payload, lambda gid: acc._get(getter, f'gamecenter/{int(gid)}/play-by-play'),
                                 lambda gid: acc._get(getter, f'gamecenter/{int(gid)}/boxscore'))
    games = [g for g in payload.get('games') or [] if str(g.get('gameScheduleState', 'OK')) == 'OK']
    if games and not res['complete']:
        return None   # some games still in progress: try again next run
    return join_results(rec, payload, res)


def update(now=None, getter=None, snap_root=SNAP_DIR, root=None, log=print, environ=None):
    """Workflow step: freeze today's record pre-game (or late, flagged), catch up missed snapshot days, then add
    results to finished nights. Never raises."""
    import feature_flags_v58 as flags
    if not flags.show_gem_history(None, environ):
        log('gematria: flag off, skipped')
        return []
    import requests
    getter = getter or requests.get
    now = now or datetime.now(timezone.utc)
    today = eastern_today(now).isoformat()
    done = []
    for p in sorted(Path(snap_root).glob('????-??-??.json')):
        day = p.stem
        if day > today or load(day, root):
            continue
        try:
            snap = _load_snap(day, snap_root)
            if snap and freeze(snap, root, now, 'workflow' if day == today else 'workflow catch-up'):
                done.append(f'froze {day}' + (' (late)' if load(day, root).get('frozen_late') else ''))
        except Exception as exc:
            log(f'gematria: freeze {day} skipped ({type(exc).__name__}: {exc})')
    for p in sorted(Path(root or ROOT).glob('????-??-??.json')) if Path(root or ROOT).is_dir() else []:
        rec = load(p.stem, root)
        if not rec or rec.get('results') or rec['day'] >= today:
            continue
        try:
            out = fetch_and_join(rec, getter)
            if out:
                save(out, root)
                done.append(f'results {rec["day"]}')
        except Exception as exc:
            log(f'gematria: results {rec["day"]} unavailable ({type(exc).__name__})')
    log('gematria: ' + (', '.join(done) or 'nothing to do'))
    return done


# ------------------------------------------------------------------------------------------------ prune
def _locked(root):
    r = Path(root or ROOT).resolve()
    if r.parts[-2:] != ('snapshots', 'gematria'):
        raise ValueError(f'gematria prune only runs in snapshots/gematria/, not {r}')
    return r


def prune(keep_days=KEEP_DAYS, today=None, root=None, dry_run=False):
    """Delete records whose filename date is more than keep_days before today (America/New_York slate date).
    keep_days=90: day 90 is kept, day 91 deleted. Exact YYYY-MM-DD.json names only; file mtimes are ignored."""
    if int(keep_days) < 1:
        raise ValueError('keep_days must be >= 1')
    r = _locked(root)
    today = today or eastern_today()
    cutoff = today - timedelta(days=int(keep_days))
    out = []
    for p in sorted(r.iterdir()) if r.is_dir() else []:
        m = _NAME.match(p.name)
        if not m or not p.is_file():
            continue
        try:
            d = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if d < cutoff:
            out.append(p)
            if not dry_run:
                p.unlink()
    return out


# ------------------------------------------------------------------------------------------------ query
def last_n_days(n, kind='arena', end=None, root=None):
    """The n slate nights before `end` (a YYYY-MM-DD slate date; default today, ET), oldest first:
    [{'day','label','status': ok|pending|missing|no_games,'count','of','who','reconstructed','frozen_late'}].
    count = players with a `kind` match who scored in the game they were matched to (postponed games excluded)."""
    if kind not in KINDS:
        raise ValueError(kind)
    end = date.fromisoformat(end) if end else eastern_today()
    out = []
    for i in range(int(n), 0, -1):
        day = (end - timedelta(days=i)).isoformat()
        rec = load(day, root)
        row = {'day': day, 'label': short_day(day), 'status': 'missing', 'count': None, 'of': None, 'who': [],
               'reconstructed': False, 'frozen_late': False}
        if rec:
            res = rec.get('results') or {}
            post = set(res.get('postponed') or [])
            pool = [m for m in rec.get('matched') or [] if kind in m.get('match', {}) and m.get('game') not in post]
            row.update(reconstructed=bool(rec.get('reconstructed')), frozen_late=bool(rec.get('frozen_late')), of=len(pool))
            if rec.get('no_games') or not rec.get('games'):
                row['status'] = 'no_games'
            elif not res.get('complete'):
                row['status'] = 'pending'
            else:
                hits = [m for m in pool if (res.get('scored') or {}).get(str(m['pid']))]
                row.update(status='ok', count=len(hits),
                           who=[(m['name'], m['team'], int(res['scored'][str(m['pid'])])) for m in hits])
        out.append(row)
    return out


def average(nights):
    ok = [x['count'] for x in nights if x['status'] == 'ok']
    return (sum(ok) / len(ok), len(ok)) if ok else (None, 0)


# ------------------------------------------------------------------------------------------------ Numbers strip
EST_NOTE = 'est. = rebuilt after the fact from NHL feeds, not frozen before puck drop.'


def strip_html(nights, kind_label='Arena-match scorers'):
    """One slim row for the Numbers page: last-N-night chips (tap a chip for who) + average over nights with results."""
    import html as h
    e = h.escape
    if not any(x['status'] != 'missing' for x in nights):
        return (f'<section class="sec v59-gh empty"><div class="gh-row"><span class="gh-k">{e(kind_label)}</span>'
                '<span class="gh-start">History starts tonight</span></div></section>')
    chips = []
    for x in nights:
        est = '<em class="gh-est" title="Reconstructed record">est.</em>' if x.get('reconstructed') else ''
        lab = f'<small>{e(x["label"])}{est}</small>'
        if x['status'] == 'ok':
            who = (' · '.join(f'{e(n)} <span>{e(t)}</span>' + (f' ×{g}' if g > 1 else '') for n, t, g in x['who'])
                   or 'No arena-match player scored')
            chips.append(f'<details class="gh-c ok" name="gh"><summary title="{e(x["day"])}: {x["count"]} of {x["of"]} arena-match players scored">'
                         f'{lab}<b>{x["count"]}</b><i>of {x["of"]}</i></summary><div class="gh-who"><strong>{e(x["label"])}</strong> {who}</div></details>')
        else:
            word = {'pending': 'pending', 'no_games': 'no games'}.get(x['status'], 'no saved data')
            big = '…' if x['status'] == 'pending' else '–'
            chips.append(f'<div class="gh-c {e(x["status"])}" title="{e(x["day"])}: {word}">{lab}<b>{big}</b><i>{word}</i></div>')
    avg, k = average(nights)
    av = (f'<span class="gh-avg"><small>{k}-night avg</small><b>{avg:.1f}</b></span>' if k
          else '<span class="gh-avg"><small>avg</small><b>–</b></span>')
    note = f'<p class="gh-note">{e(EST_NOTE)}</p>' if any(x.get('reconstructed') for x in nights) else ''
    return (f'<section class="sec v59-gh"><div class="gh-row"><span class="gh-k">{e(kind_label)}</span>'
            f'<div class="gh-cs">{"".join(chips)}</div>{av}</div>{note}</section>')


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='V5.9 gematria history log')
    ap.add_argument('command', choices=['update', 'prune'])
    ap.add_argument('--keep-days', type=int, default=KEEP_DAYS)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if a.command == 'update':
        update()
    else:
        gone = prune(a.keep_days, dry_run=a.dry_run)
        print(('Would prune ' if a.dry_run else 'Pruned ') + f'{len(gone)} gematria record(s) older than {a.keep_days} days'
              + ''.join(f'\n  {p.name}' for p in gone))
