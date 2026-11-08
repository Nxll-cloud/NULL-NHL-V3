"""The List step 9: independent three-GAME anytime strategy. No network or private money writes.
Uses parlay_v58.choose directly, NEVER build()'s team/small-slate relaxation.
Public freezes hold quotes and strategy evidence only; private bets live in strict_ledger_v60.
"""
from copy import deepcopy
from datetime import datetime, timezone, date
from pathlib import Path
import hashlib
import json
import math

import parlay_v58 as parlay
import parlay_tracker_v59 as tracker
import odds_scorers_v59 as odds
import situational_v58 as sit
import probable_goalies_v54 as pg

ROOT = Path(__file__).resolve().parent / 'snapshots' / 'strict_cards'
INPUT_ROOT = ROOT.parent / 'strict_card_inputs'
DEFAULT_RULE = {'min_gp': 5, 'min_sa': 150, 'min_multiplier': 1.05}
RULE_NOTE = ('Configurable strategy screen, not a validated edge: listed confirmed/probable opposing starter, '
             'at least 5 appearances and 150 shots faced; existing season SV% shrinkage (600 shots toward .896), '
             'goalie scoring multiplier ≥1.05. Unknown starters and team-average fallbacks do not qualify. '
             'This is not the separate H2H weak-spot marker and does not reproduce PropFinder occurrence counting.')
QUOTE_NOTE = ('Quoted suggestions, not placed bets. Leg-product payout is an estimate, including same-book legs; '
              'mixed-book prices are not an executable card quote. No stake or realized P&L is assumed.')


def dt(v):
    return tracker._dt(v)


def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def goalie_evidence(c, ctx, rule=None):
    rule = rule or DEFAULT_RULE
    st = sit.starter_for(ctx, c['team'], c['opp'])
    if not st or (st.get('game_id') and str(st['game_id']) != str(c['game_id'])):
        return None, 'unknown/mismatched starter'
    rows = [g for g in (ctx or {}).get('goalies', []) if g.get('Team') == c['opp']]
    g = pg.match_stats(st, rows)
    if not g or (st.get('goalie_id') and str(st['goalie_id']) != str(g.get('Player ID'))):
        return None, 'starter stats unavailable'
    sa, saves, gp = (num(g.get(k)) for k in ('SA', 'Saves', 'GP'))
    if sa is None or saves is None or gp is None or not 0 <= saves <= sa or sa < rule['min_sa'] or gp < rule['min_gp']:
        return None, 'goalie sample below floor/unknown'
    mult, sv = sit.goalie_mult_from(saves, sa)
    ev = {'goalie_id': str(g['Player ID']), 'name': g['Goalie'], 'status': st['status'], 'source': st.get('source'),
          'fetched_at': st.get('fetched_at'), 'gp': gp, 'sa': sa, 'saves': saves, 'sv': saves / sa,
          'shrunk_sv': sv, 'multiplier': mult}
    return ev, '' if mult >= rule['min_multiplier'] else 'goalie not weak under strategy rule'


def quoted(c, data, now):
    """Only provider prices; ID + team + matchup all agree. Never attach by name alone."""
    if not data or data.get('demo') is not False or data.get('source') not in (odds.SOURCE_API, odds.SOURCE_ESPN):
        return None
    fetched = dt(data.get('fetched_at'))
    start = dt(c.get('start'))
    if not fetched or not start or fetched > now or fetched >= start or (now - fetched).total_seconds() > 7200:
        return None
    matches = [r for r in data.get('rows', []) if str(r.get('pid')) == str(c['pid'])
               and r.get('team') == c['team'] and r.get('game') == (f"{c['opp']} @ {c['team']}" if c.get('home') else f"{c['team']} @ {c['opp']}")]
    if len(matches) != 1:
        return None
    r = matches[0]
    prices = [(b, odds.parse_american(a)) for b, a in (r.get('books') or {}).items() if b and 'demo' not in b.lower()]
    prices = [(b, a) for b, a in prices if a is not None]
    if not prices:
        return None
    b, a = max(prices, key=lambda ba: odds.decimal(ba[1]))
    updated = dt(r.get('updated'))
    if updated and (updated > now or updated >= start):
        return None
    return {'book': b, 'market': odds.MARKET, 'american': a, 'decimal': odds.decimal(a),
            'source': data['source'], 'fetched_at': data['fetched_at'], 'updated_at': r.get('updated') or None}


def build(day, candidates, ctx, data, now=None, rule=None):
    now = now or datetime.now(timezone.utc)
    rule = dict(rule or DEFAULT_RULE)
    if data and data.get('day') and data['day'] != day:
        data = None
    eligible, reasons, seen, fades = [], {}, set(), []
    def reject(why):
        reasons[why] = reasons.get(why, 0) + 1
    for c in candidates or []:
        gid, pid = str(c.get('game_id') or ''), str(c.get('pid') or '')
        start = dt(c.get('start'))
        if not gid.isdigit() or not pid.isdigit() or not c.get('team') or not c.get('opp'):
            reject('missing NHL player/game ID'); continue
        if not start or now >= start or c.get('phase') != 'pregame':
            reject('started/unknown game time'); continue
        if not isinstance(c.get('name'), str) or not c['name'].strip():
            reject('missing player name'); continue
        if str(c.get('position') or '').upper() in ('G', 'GOALIE'):
            reject('goalie not a skater'); continue
        if not num(c.get('p')) or not 0 < c['p'] < 1 or pid in seen:
            reject('invalid/duplicate candidate'); continue
        seen.add(pid)
        g, why = goalie_evidence(c, ctx, rule)
        if why:
            if g and g['multiplier'] <= .95:
                fades.append(dict(c, goalie=g))
            reject(why); continue
        q = quoted(c, data, now)
        if not q:
            reject('no supported fresh real quote'); continue
        eligible.append(dict(c, game_id=gid, goalie=g, quote=q))
    # Exact existing optimizer, partitioned by NHL ID, not display key or team.
    legs = parlay.choose(eligible, 3, per='game_id')
    games = len({c['game_id'] for c in eligible})
    rec = {'schema': 1, 'day': day, 'frozen_at': now.isoformat(), 'rule': rule, 'legs': legs,
           'eligible_games': games, 'reasons': reasons, 'notes': make_notes(legs, eligible, fades),
           'results': None, 'kind': 'quoted suggestion'}
    if not legs and eligible:
        # Partial card: same strict filters, best one per distinct game, never a full card or payout.
        rec['partial_legs'] = partial_legs(eligible, 3)
        rec['candidate_games'] = len({str(c.get('game_id')) for c in candidates or [] if str(c.get('game_id') or '').isdigit()})
    rec['id'] = digest(rec)
    return rec


def partial_legs(eligible, k=3):
    """Local one-per-game selection (shared parlay.choose stays all-or-nothing)."""
    best = {}
    for c in sorted(eligible, key=lambda c: (-c['p'], c['name'])):
        best.setdefault(c['game_id'], c)
    return sorted(best.values(), key=lambda c: (-c['p'], c['name']))[:k]


def make_notes(legs, eligible, fades=()):
    # Freeze comparator before games, never pick the night's highest total after the fact.
    groups = {}
    for c in sorted(eligible, key=lambda c: (-c['p'], c['name'])):
        groups.setdefault(c['game_id'], {}).setdefault(c['team'], c)
    both = [v for v in groups.values() if len(v) == 2]
    best = max(both, key=lambda v: sum(c['p'] for c in v.values()), default=None)
    fade = min(fades, key=lambda c: (c['goalie']['multiplier'], c['team']), default=None)
    notes = [{'kind': 'environment', 'game_id': next(iter(best.values()))['game_id'] if best else None,
              'teams': list(best) if best else [], 'threshold': 7, 'criterion': 'At least 7 non-shootout goals; pregame heuristic: highest sum of each team’s best eligible model chance among games with two weak starters',
              'reason': None if best else 'No two-sided qualifying game evidence'},
             {'kind': 'fade', 'game_id': fade['game_id'] if fade else None, 'team': fade['team'] if fade else None,
              'teams': [fade['team'], fade['opp']] if fade else [], 'threshold': 2,
              'goalie': fade['goalie'] if fade else None,
              'criterion': 'At most 2 team goals; sampled opposing starter multiplier ≤0.95' if fade else None,
              'reason': None if fade else 'No sampled hot-goalie/team fade evidence; ungraded'}]
    notes += [{'kind': 'starter', 'game_id': c['game_id'], 'team': c['opp'], 'goalie_id': c['goalie']['goalie_id'],
               'name': c['goalie']['name'], 'status': c['goalie']['status'], 'pick': c['name'],
               'criterion': 'Frozen listed goalie ID matches actual NHL starter flag'} for c in legs]
    return notes


def digest(rec):
    public = {k: v for k, v in rec.items() if k not in ('id', 'results')}
    return hashlib.sha256(json.dumps(public, sort_keys=True, allow_nan=False).encode()).hexdigest()[:20]


def grade_note(n, games):
    g = games.get(str(n.get('game_id')), {})
    if not g.get('final') or not g.get('verified'):
        return 'unknown'
    if n['kind'] == 'environment' and n.get('game_id') and g.get('total') is not None:
        return 'won' if g['total'] >= n['threshold'] else 'lost'
    if n['kind'] == 'fade' and n.get('team') and n.get('threshold') is not None:
        actual = g.get('team_goals', {}).get(n['team'])
        return 'unknown' if actual is None else ('won' if actual <= n['threshold'] else 'lost')
    if n['kind'] == 'starter':
        actual = g.get('starters', {}).get(n.get('team'))
        return 'unknown' if actual is None else ('matched' if str(actual) == n['goalie_id'] else 'changed')
    return 'unknown'


def settle(rec, games, now=None):
    """Only reliable FINAL evidence. OT counts, shootout attempts never count. No DNP assumptions."""
    out = deepcopy(rec)
    old = out.get('results') or {}
    statuses = dict(old.get('legs') or {})
    for c in out['legs']:
        pid = str(c['pid'])
        if statuses.get(pid) in ('won', 'lost', 'void', 'push'):
            continue
        g = games.get(c['game_id'], {})
        statuses[pid] = ('won' if pid in {str(p) for p in g.get('scorers', [])} else 'lost') if g.get('final') and g.get('verified') else 'pending'
    from strict_ledger_v60 import card_status
    notes = [grade_note(n, games) for n in out['notes']]
    prev = old.get('notes') or []
    notes = [prev[i] if i < len(prev) and prev[i] != 'unknown' else v for i, v in enumerate(notes)]
    out['results'] = {'legs': statuses, 'card': card_status(list(statuses.values())), 'notes': notes,
                      'graded_at': old.get('graded_at') or (now or datetime.now(timezone.utc)).isoformat()}
    return out


def load(day, root=None):
    date.fromisoformat(day)
    try:
        rec = json.loads((Path(root or ROOT) / f'{day}.json').read_text())
        return rec if rec.get('id') == digest(rec) and rec.get('schema') == 1 else None
    except (OSError, ValueError, TypeError):
        return None


def save(rec, root=None):
    """Public quote record ONLY. Immutable selection, quote, notes; settled results only advance."""
    allowed = {'schema', 'day', 'frozen_at', 'rule', 'legs', 'eligible_games', 'reasons', 'notes', 'results', 'kind', 'id'}
    if set(rec) - allowed or rec.get('id') != digest(rec):
        raise ValueError('Invalid public strategy record')
    # Prevent private user data accidentally entering a public workflow directory.
    if any(k in json.dumps(rec).lower() for k in ('"stake"', '"actual_odds"', '"placed"', '"profit"')):
        raise ValueError('Private bet data cannot be saved publicly')
    root = Path(root or ROOT)
    old = load(rec['day'], root)
    if old:
        if old['id'] != rec['id']:
            return old
        prior = (old.get('results') or {}).get('legs', {})
        for pid, state in prior.items():
            if state != 'pending' and (rec.get('results') or {}).get('legs', {}).get(pid) != state:
                raise ValueError('Settled record is immutable')
        for i, state in enumerate((old.get('results') or {}).get('notes', [])):
            new_notes = (rec.get('results') or {}).get('notes', [])
            if state != 'unknown' and (i >= len(new_notes) or new_notes[i] != state):
                raise ValueError('Settled notes are immutable')
    if len(json.dumps(rec).encode()) >= 99000:
        raise ValueError('strategy record too large')
    root.mkdir(parents=True, exist_ok=True)
    p = root / f'{rec["day"]}.json'
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(rec, ensure_ascii=False, allow_nan=False))
    tmp.replace(p)
    return rec


def capture_inputs(snapshot, entry, situ, root=None, out_ids=()):
    """Called by existing accuracy freeze, sharing its fetched context. No new calls, no backfill."""
    import matchup_center_v54 as mc
    frozen, first = dt(entry['frozen_at']), dt(entry.get('first_start'))
    if not frozen or not first or frozen >= first or situ is None:
        return
    games = mc.slate_games(snapshot.get('games') or [])
    by_team = {t: g for g in games for t in (g['away'], g['home'])}
    out = []
    for p in entry.get('players') or []:
        g = by_team.get(p[2])
        if not g or p[0] in set(out_ids):
            continue
        out.append({'pid': p[0], 'name': p[1], 'team': p[2], 'opp': g['home'] if p[2] == g['away'] else g['away'],
                    'game_id': str(g['game_id']), 'game': g['key'], 'home': p[2] == g['home'], 'start': g['start'],
                    'p': p[3], 'phase': 'pregame'})
    # JSON cannot encode tuple context keys: keep just per-candidate evidence, not the entire stats payload.
    evidence = {}
    for c in out:
        key = c['game_id'] + ':' + c['opp']
        if key not in evidence:
            evidence[key] = goalie_evidence(c, situ.ctx)[0]
    p = Path(root or INPUT_ROOT) / f'{entry["day"]}.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    # Inputs may refresh pregame; once an actual strategy card exists its quote and pick never refresh.
    columns = ['pid', 'name', 'team', 'opp', 'game_id', 'game', 'home', 'start', 'p', 'phase']
    payload = {'day': entry['day'], 'frozen_at': entry['frozen_at'], 'first_start': entry['first_start'],
               'columns': columns, 'candidates': [[c[k] for k in columns] for c in out], 'goalies': evidence}
    if len(json.dumps(payload).encode()) < 99000:
        tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(payload)); tmp.replace(p)


def from_inputs(inputs, book, now):
    """Workflow consumes ONLY already-fetched books and model evidence."""
    if (not inputs or not book or book.get('demo') is not False
            or book.get('day') != inputs.get('day')):
        return None
    fz, fs = dt(inputs.get('frozen_at')), dt(inputs.get('first_start'))
    if not fz or not fs or not fz <= now < fs:
        return None
    rows = []
    pool = [dict(zip(inputs['columns'], c)) for c in inputs['candidates']] if inputs.get('columns') else inputs['candidates']
    ctx = sit.context()
    for c in pool:
        g = inputs.get('goalies', {}).get(c['game_id'] + ':' + c['opp'])
        if not g:
            continue
        ctx['goalies'].append({'Team': c['opp'], 'Player ID': g['goalie_id'], 'Goalie': g['name'], 'SA': g['sa'], 'Saves': g['saves'], 'GP': g['gp']})
        ctx['starters'].setdefault(tuple(sorted((c['team'], c['opp']))), {})[c['opp']] = {
            'team': c['opp'], 'goalie': g['name'], 'goalie_id': g['goalie_id'], 'status': g['status'], 'source': g['source'], 'fetched_at': g['fetched_at']}
    # Deduplicate goalie rows; pg.match_stats safely matches by NHL ID/team.
    ctx['goalies'] = list({(g['Team'], g['Player ID']): g for g in ctx['goalies']}.values())
    cs = {str(c['pid']): c for c in pool}
    for t in book.get('top') or []:
        c = cs.get(str(t[0]))
        if c:
            rows.append({'pid': t[0], 'team': t[2], 'game': f"{c['opp']} @ {c['team']}" if c['home'] else f"{c['team']} @ {c['opp']}", 'books': t[8], 'updated': book.get('odds_updated')})
    data = {'demo': False, 'source': book['source'], 'fetched_at': book['frozen_at'], 'rows': rows}
    return build(inputs['day'], pool, ctx, data, now)


def update(now=None, root=None, input_root=None, books_root=None, acc_root=None):
    """Workflow: freeze once before first slate start; settle from existing complete accuracy results, no API calls."""
    import accuracy_v58 as acc
    import books_picks_v59 as bp
    now = now or datetime.now(timezone.utc)
    day = acc.eastern_today(now).isoformat()
    root = Path(root or ROOT)
    if not load(day, root):
        try:
            inp = json.loads((Path(input_root or INPUT_ROOT) / f'{day}.json').read_text())
            rec = from_inputs(inp, bp.load(day, books_root), now)
            if rec and rec['legs']:
                save(rec, root)
        except (OSError, ValueError, KeyError):
            pass
    for p in root.glob('????-??-??.json') if root.is_dir() else []:
        rec = load(p.stem, root)
        ent = acc.load_entry(p.stem, acc_root or acc.LOG_DIR)
        # Existing accuracy results are only persisted by update after the full slate is final.
        if not rec or not ent or not ent.get('results') or not ent.get('final'):
            continue
        if (ent['results'].get('n_games') != len(ent.get('games') or [])
                or not {c['game_id'] for c in rec['legs']}.issubset({str(g) for g in ent.get('games') or []})):
            continue
        games = ent['results'].get('strict_games') or {}
        save(settle(rec, games, now), root)


if __name__ == '__main__':
    update()
