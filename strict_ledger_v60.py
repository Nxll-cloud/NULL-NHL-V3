"""Private session-only bet ledger. Never writes disk or calls a bookmaker.
Quoted suggestions ≠ placed bets. Singles and cards are separate exposure.
"""
from copy import deepcopy
import json
import math
from datetime import datetime, timezone
from strict_card_v60 import dt, digest

TERMINAL = ('won', 'lost', 'void', 'push')


def decimal(american):
    a = float(american)
    if not math.isfinite(a) or abs(a) < 100:
        raise ValueError('American odds must be ≥+100 or ≤−100')
    return 1 + a / 100 if a > 0 else 1 + 100 / -a


def card_status(states):
    if not states:
        return 'pending'
    if 'lost' in states:
        return 'lost'
    if any(s not in TERMINAL for s in states):
        return 'pending'
    if all(s in ('void', 'push') for s in states):
        return 'void'
    return 'won'


def financial(status, price, stake):
    if stake is None:
        return {'status': status, 'return': None, 'pnl': None}
    stake = float(stake)
    if not math.isfinite(stake) or stake < 0:
        raise ValueError('Stake must be finite and nonnegative')
    if status not in TERMINAL:
        return {'status': status, 'return': None, 'pnl': None}
    ret = 0 if status == 'lost' else stake if status in ('void', 'push') else stake * price if price else None
    return {'status': status, 'return': round(ret, 2) if ret is not None else None,
            'pnl': round(ret - stake, 2) if ret is not None else None}


def add(ledger, rec, target, stake=None, actual_american=None, book='', placed=False, now=None):
    """Idempotent single entry per quoted card/target. Immutable at-save user entry.
    Defaults to quoted paper tracking. Placed records explicitly require real stake and book.
    A card's actual odds must be an explicit same-book whole-card quote, not leg multiplication.
    """
    now = now or datetime.now(timezone.utc)
    if not rec.get('legs') or rec['id'] != digest(rec):
        raise ValueError('Invalid frozen card')
    if target != 'card' and target not in {str(c['pid']) for c in rec['legs']}:
        raise ValueError('Unknown leg')
    ident = f'{rec["id"]}:{target}'
    if any(e['id'] == ident for e in ledger):
        return deepcopy(ledger)
    if any(not dt(c['start']) or now >= dt(c['start']) for c in rec['legs']):
        raise ValueError('Entry closed at first card puck drop; no retrospective bet logging')
    if stake is not None:
        financial('pending', None, stake)
    actual = decimal(actual_american) if actual_american is not None else None
    if placed and (stake is None or not book.strip() or actual is None):
        raise ValueError('Placed entries require entered stake, actual odds and bookmaker')
    e = {'id': ident, 'card': deepcopy(rec), 'target': target, 'stake': stake,
         'actual_american': actual_american, 'actual_decimal': actual, 'book': book.strip(),
         'placed': bool(placed), 'entered_at': now.isoformat(), 'outcome': None}
    return [*deepcopy(ledger), e]


def evaluate(e, rec=None):
    frozen = e['card']
    # Only accept results for the same immutable selection/quotes.
    rec = rec if rec and rec.get('id') == frozen['id'] else frozen
    confirmation = e.get('book_settlement')
    states = confirmation['states'] if confirmation else (rec.get('results') or {}).get('legs') or {}
    target = e['target']
    if target == 'card':
        ls = [states.get(str(c['pid']), 'pending') for c in frozen['legs']]
        status = card_status(ls)
        voided = any(s in ('void', 'push') for s in ls)
        if confirmation and confirmation.get('post_void_decimal') and status == 'won':
            price, label = confirmation['post_void_decimal'], 'User-reported bookmaker post-void whole-card price'
        elif e.get('actual_decimal') and voided and status == 'won':
            # A whole-card price does not reveal the book's post-void repricing. Never invent it.
            price, label = None, 'Actual card needs bookmaker post-void settlement price'
        elif e.get('actual_decimal'):
            price, label = e['actual_decimal'], 'Entered same-book whole-card quote'
        else:
            price = math.prod(c['quote']['decimal'] for c, s in zip(frozen['legs'], ls) if s not in ('void', 'push'))
            mixed = len({c['quote']['book'] for c in frozen['legs']}) > 1
            label = ('Mixed-book ' if mixed else '') + 'estimated/paper leg-product payout; not executable card odds'
    else:
        c = next(c for c in frozen['legs'] if str(c['pid']) == target)
        status = states.get(target, 'pending')
        price = e.get('actual_decimal') or c['quote']['decimal']
        label = 'Entered actual single odds' if e.get('actual_decimal') else 'Quoted single / paper'
    out = financial(status, price, e.get('stake'))
    return dict(out, payout_basis=label, tracking='placed (user reported)' if e.get('placed') else 'paper/unplaced',
                realized_pnl=out['pnl'] if e.get('placed') and confirmation else None,
                settlement='Bookmaker result (user reported)' if confirmation else 'Calculated strategy result; book settlement unconfirmed')


def grade(ledger, records):
    out = deepcopy(ledger)
    for e in out:
        old = e.get('outcome')
        if e.get('book_settlement'):
            e['outcome'] = evaluate(e, records.get(e['card']['id']))
            continue
        if old and old['status'] in TERMINAL:
            continue
        e['outcome'] = evaluate(e, records.get(e['card']['id']))
    return out


def confirm_settlement(entries, entry_id, states, note, rec, post_void_american=None, now=None):
    """User-reported bookmaker disposition, once only, after every relevant game final.
    Original calculated outcome and frozen quotes remain retained; this never places/changes a bet.
    """
    out = deepcopy(entries)
    e = next((e for e in out if e['id'] == entry_id), None)
    if not e or e.get('book_settlement'):
        raise ValueError('Entry missing or bookmaker settlement already locked')
    if rec.get('id') != e['card']['id']:
        raise ValueError('Settlement must match the frozen card')
    required = {str(c['pid']) for c in e['card']['legs']} if e['target'] == 'card' else {e['target']}
    strategy_states = (rec.get('results') or {}).get('legs') or {}
    if not all(strategy_states.get(p) in TERMINAL for p in required):
        raise ValueError('Wait for verified final results before confirming book settlement')
    if set(states) != required or any(s not in TERMINAL for s in states.values()) or not note.strip():
        raise ValueError('Supply each leg disposition and a bookmaker settlement note')
    e['calculated_outcome'] = deepcopy(e.get('outcome'))
    e['book_settlement'] = {'states': dict(states), 'note': note.strip(),
        'confirmed_at': (now or datetime.now(timezone.utc)).isoformat(),
        'post_void_decimal': decimal(post_void_american) if post_void_american is not None else None,
        'post_void_american': post_void_american}
    e['outcome'] = evaluate(e, rec)
    return out


def export(ledger):
    return json.dumps({'schema': 1, 'entries': ledger}, ensure_ascii=False, allow_nan=False, indent=2)


def restore(text):
    if len(text.encode()) > 2_000_000:
        raise ValueError('Ledger import too large')
    obj = json.loads(text)
    if obj.get('schema') != 1 or not isinstance(obj.get('entries'), list) or len(obj['entries']) > 1000:
        raise ValueError('Invalid ledger schema')
    ids = set()
    for e in obj['entries']:
        rec = e['card']
        if rec['id'] != digest(rec) or len(rec.get('legs', [])) != 3 or len({c['game_id'] for c in rec['legs']}) != 3:
            raise ValueError('Invalid frozen card')
        if e['id'] != f'{rec["id"]}:{e["target"]}' or e['id'] in ids:
            raise ValueError('Invalid or duplicate ledger entry')
        if e['target'] != 'card' and e['target'] not in {str(c['pid']) for c in rec['legs']}:
            raise ValueError('Invalid target')
        if not dt(e['entered_at']) or any(dt(e['entered_at']) >= dt(c['start']) for c in rec['legs']):
            raise ValueError('Entry is not pregame')
        financial('pending', None, e.get('stake'))
        if e.get('actual_american') is not None and decimal(e['actual_american']) != e.get('actual_decimal'):
            raise ValueError('Actual odds inconsistent')
        if e.get('placed') and (e.get('stake') is None or not e.get('book') or not e.get('actual_decimal')):
            raise ValueError('Placed entry missing evidence')
        ids.add(e['id'])
    return obj['entries']
