"""V5.8 EdgeLab: a read-only view of the next-goal model against CURRENT live anytime-goal prices.

* Model p is the same computation the Edge Flags tab uses: ``edgeflags_v56.player_lambda`` (pregame per-game lambda;
  live = the player's rate x remaining minutes; both include the V5.8 situational layer when it is on) then ``live_nextgoal_v56.p_anytime`` (1 - e^-lambda), on the shared
  ``_v56_results``. Form % is never used as a probability.
* Implied = ``edgelab_v55.american_to_implied`` of the LIVE price. That differs from Edge Flags, which uses the opener
  (earliest quote seen). Live price = each book's latest anytime-goal quote for the player, averaged over the books;
  ``updated`` = the newest of those timestamps. ``books`` = how many books went into the average.
* edge = model p - implied. Priced rows sort biggest edge first; rows without a live price follow (model p only,
  no edge number).
* Exclusions (as Edge Flags): players who already scored are settled and left out; final / shootout games are left out;
  no moneylines (the model has no win probability). No DEMO prices, no manual probability or odds entry, and no
  bankroll / stake / Kelly / threshold.
"""
from __future__ import annotations

import pandas as pd

import edgelab_v55 as el
import edgeflags_v56 as eflags
import live_nextgoal_v56 as lm
import situational_v58 as sit

LIVE_LABEL = 'Live price'
NO_PRICE = 'No live price'
NO_PRICES_TITLE = 'No live prices loaded — add ODDS_API_KEY in Streamlit secrets'
OVER = ('final', 'shootout')


def live_prices(quotes):
    """Quotes frame (player, market, american_odds, sportsbook, updated_at) -> {player_casefold: price dict}.
    Per player: each book's LATEST anytime-goal quote, averaged across books (implied probability)."""
    if not isinstance(quotes, pd.DataFrame) or quotes.empty or not {'player', 'american_odds'}.issubset(quotes.columns):
        return {}
    q = quotes.copy()
    if 'market' in q.columns:
        m = q['market'].astype(str).str.lower()
        q = q[m.apply(lambda s: any(k in s for k in eflags.ANYTIME_MARKETS))]
    if q.empty:
        return {}
    q['_t'] = pd.to_datetime(q['updated_at'] if 'updated_at' in q.columns else None, errors='coerce', utc=True)
    q['_b'] = q['sportsbook'].astype(str) if 'sportsbook' in q.columns else ''
    q['_imp'] = q['american_odds'].map(_implied)
    q = q[q['_imp'].notna()]
    out = {}
    for player, grp in q.groupby(q['player'].map(eflags._norm)):
        if not player:
            continue
        latest = []
        for _, g in grp.groupby('_b'):
            g = g.sort_values('_t', na_position='first', kind='stable')
            latest.append(g.iloc[-1])
        imp = sum(r['_imp'] for r in latest) / len(latest)
        ts = [r['_t'] for r in latest if not pd.isna(r['_t'])]
        t = max(ts) if ts else None
        out[player] = {'implied': imp, 'american': eflags.implied_to_american(imp), 'books': len(latest),
                       'book_names': sorted({str(r['_b']) for r in latest if str(r['_b'])}),
                       'at': None if t is None else t.isoformat(), 'source': 'live'}
    return out


def _implied(o):
    try:
        return el.american_to_implied(float(o))
    except (el.EdgeLabError, TypeError, ValueError):
        return None


def model_rows(results, prices, scored_ids=()):
    """Shared model results -> (priced rows sorted by edge desc, unpriced rows sorted by model p desc).
    Final/shootout games and players who already scored are omitted."""
    priced, unpriced = [], []
    scored = set(scored_ids or ())
    for r in results or []:
        res, slate = r['result'], r['slate']
        ph, rem = res['phase'], res['remaining']
        if ph in OVER:
            continue
        game = f"{slate['away']} @ {slate['home']}"
        for rec in res['players']:
            if rec.get('goals', 0) > 0 or rec.get('pid') in scored:  # settled: the anytime prop has already won
                continue
            lam = eflags.player_lambda(rec, ph, rem)
            if lam is None:
                continue
            p = lm.p_anytime(lam)
            line = prices.get(eflags._norm(rec['name']))
            row = {'pid': rec.get('pid'), 'name': rec['name'], 'team': rec['team'], 'game': game, 'phase': ph,
                   'start': slate.get('start'), 'rank': rec.get('rank'), 'lambda': lam, 'model_p': p,
                   'implied': None, 'american': None, 'books': 0, 'at': None, 'edge': None,
                   'why': sit.why(rec.get('situ')) if rec.get('situ') else ''}
            if line:
                row.update(implied=line['implied'], american=line['american'], books=line['books'], at=line['at'],
                           edge=p - line['implied'])
                priced.append(row)
            else:
                unpriced.append(row)
    priced.sort(key=lambda x: (-x['edge'], -x['model_p'], x['name']))
    unpriced.sort(key=lambda x: (-x['model_p'], x['name']))
    return priced, unpriced


def fmt_pct(p):
    return '—' if p is None else f'{p * 100:.1f}%'


def fmt_edge(e):
    return f'{e * 100:+.1f} pts'


def fmt_time(iso, tz='America/New_York'):
    if not iso:
        return '—'
    t = pd.Timestamp(iso)
    t = t.tz_localize('UTC') if t.tzinfo is None else t
    return t.tz_convert(tz).strftime('%-I:%M %p ET')


def table_html(priced, unpriced, logo=None, limit_unpriced=None):
    """Read-only table. ``logo`` (team -> html) is optional. Player names in <b> get scorer badges via the proxy."""
    import html as h
    lg = logo or (lambda t: '')

    def tr(r, priced_row):
        tone = 'pos' if priced_row and r['edge'] > 0 else 'neg' if priced_row else 'na'
        edge = f'<td class="el-e {tone}">{fmt_edge(r["edge"])}</td>' if priced_row else f'<td class="el-e na">{NO_PRICE}</td>'
        price = (f'<td class="el-n">{el.fmt_odds(r["american"])}<small>{fmt_pct(r["implied"])} · {r["books"]} book{"s" if r["books"] != 1 else ""}'
                 f' · {fmt_time(r["at"])}</small></td>') if priced_row else '<td class="el-n na">—</td>'
        live = ' <i class="el-live">LIVE</i>' if r['phase'] == 'live' else ''
        why = f' title="{h.escape(r["why"])}"' if r.get('why') else ''  # V5.8: situational breakdown on hover
        return (f'<tr class="{tone}"><td class="el-p">{lg(r["team"])}<span><b>{h.escape(r["name"])}</b><small>{h.escape(r["team"])} · {h.escape(r["game"])}{live}</small></span></td>'
                f'<td class="el-n"{why}>{fmt_pct(r["model_p"])}<small>λ {r["lambda"]:.2f}</small></td>{price}{edge}</tr>')

    up = unpriced if limit_unpriced is None else unpriced[:limit_unpriced]
    body = ''.join(tr(r, True) for r in priced)
    if up:
        body += f'<tr class="el-g"><th colspan="4">{NO_PRICE} · model chance only ({len(unpriced)})</th></tr>' + ''.join(tr(r, False) for r in up)
    head = f'<thead><tr><th>Player</th><th>Model p</th><th>{LIVE_LABEL}</th><th>Edge</th></tr></thead>'
    return f'<div class="el-wrap"><table class="el-t">{head}<tbody>{body}</tbody></table></div>'
