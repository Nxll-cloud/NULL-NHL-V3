"""Prediction Models only: scoped mobile table and private per-session ledger UI."""
from datetime import datetime, timezone
from html import escape
import json

import parlay_v58 as parlay
import parlay_tracker_v59 as tracker
import strict_card_v60 as strategy
import strict_ledger_v60 as ledger

CSS = '''<style>
.sc60{box-sizing:border-box;min-width:0;max-width:100%;padding:14px;border:1px solid #00e5ff66;border-radius:14px;
background:linear-gradient(130deg,#00e5ff0d,#9b5cff12);margin:14px 0;overflow-wrap:anywhere}
.sc60 h3{color:#00e5ff}.sc60 p{font-size:.88rem}.sc60 .sc60-scroll{width:100%;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
.sc60 table{width:100%;min-width:760px;border-collapse:collapse;font-size:.85rem}.sc60 th{color:#c9b6ff;text-align:left}
.sc60 td,.sc60 th{padding:8px;border-bottom:1px solid #9b5cff33;vertical-align:top}.sc60 td{white-space:normal}
@media(max-width:420px){.sc60{padding:10px}.sc60 td,.sc60 th{padding:6px}}
</style>'''


def games_from_pbp(pbps):
    games = {}
    for gid, g in (pbps or {}).items():
        goals = [e for e in g.get('events', []) if e.get('kind') == 'goal' and e.get('ptype') != 'SO']
        final = g.get('state') in ('OFF', 'FINAL')
        a, h = g.get('away_score'), g.get('home_score')
        so = 1 if g.get('ptype') == 'SO' else 0
        verified = (final and a is not None and h is not None and len(goals) == a + h - so
                    and all(e.get('shooter') and e.get('team') in (g.get('away'), g.get('home')) for e in goals))
        tally = {t: sum(e.get('team') == t for e in goals) for t in (g.get('away'), g.get('home'))}
        games[str(gid)] = {'final': final, 'verified': verified, 'scorers': [e['shooter'] for e in goals if e.get('shooter')],
                           'team_goals': tally, 'total': len(goals) if verified else None, 'starters': {}}
    return games


def resolve(store, day, results, rows, ctx, quotes, now=None, demo=False):
    now = now or datetime.now(timezone.utc)
    key = 'sc60_quote:' + day
    public = strategy.load(day)
    rec = store.get(key)
    if rec:
        # A later workflow freeze must not replace an earlier session's at-pick quote/selection.
        return public if public and public['id'] == rec['id'] and public.get('results') else rec
    if public:
        store[key] = public
        return public
    if demo:
        return {'legs': [], 'reasons': {'demo replay is not a real pregame quote': 1}}
    starts = [strategy.dt(r['slate'].get('start')) for r in results or []]
    if tracker.started(results) or any(s and now >= s for s in starts):
        return {'legs': [], 'reasons': {'slate started; no frozen pregame strategy card': 1}}
    cands = parlay.candidates(results, rows, exclude_started=True)
    rec = strategy.build(day, cands, ctx, quotes, now)
    if rec['legs']:
        store[key] = rec
    return rec


def section_html(rec):
    e = lambda v: escape(str(v))
    body = '<h3>the list</h3><p>' + e(strategy.RULE_NOTE) + '</p>'
    legs = rec.get('legs') or []
    partial = [] if legs else (rec.get('partial_legs') or [])
    why = '; '.join(f'{k} ({v})' for k, v in (rec.get('reasons') or {}).items())
    if not legs and not partial:
        body += '<b>No qualifying 3-game card</b><p>' + e(why or 'Fewer than three distinct eligible NHL games with supported prices.') + '</p>'
    else:
        shown = legs or partial
        states = (rec.get('results') or {}).get('legs') or {}
        if legs:
            body += '<p>Frozen at ' + e(rec['frozen_at']) + ' · three distinct NHL game IDs · independent of Home’s four-leg card.</p>'
        else:
            n, total = len(partial), rec.get('candidate_games')
            body += (f'<b class="sc60-partial">Partial card · {n} of 3 legs</b><p>Only {n} distinct NHL game{"s" if n != 1 else ""}'
                     + (f' of {e(total)}' if total else '') + ' had a qualifying player. Other games failed the strict screen: '
                     + e(why or 'no qualifying player') + '. Not a full 3-game card; no combined price shown.</p>')
        body += '<div class="sc60-scroll" tabindex="0" role="region" aria-label="the list table"><table><thead><tr>'
        body += ''.join('<th scope="col">' + h + '</th>' for h in ('Player', 'Game ID / matchup', 'Model %', 'Opposing goalie', 'Book / offered odds', 'Quote source / time', 'Result'))
        body += '</tr></thead><tbody>'
        for c in shown:
            q, g = c['quote'], c['goalie']
            cells = [f"{c['name']} ({c['team']})", f"{c['game_id']} · {c['team']} vs {c['opp']}", f"{100*c['p']:.1f}%",
                     f"{g['name']} · {g['status']} · SV {g['sv']:.3f} (shrunk {g['shrunk_sv']:.3f}, ×{g['multiplier']:.2f}) · {g['gp']:g} GP / {g['sa']:g} SA",
                     f"{q['book']} · {q['american']:+g} / {q['decimal']:.3f}", f"{q['source']} · {q['market']} · fetched {q['fetched_at']}",
                     states.get(str(c['pid']), 'pending')]
            body += '<tr>' + ''.join('<td>' + e(v) + '</td>' for v in cells) + '</tr>'
        body += '</tbody></table></div>'
        if legs:
            import math
            combined = math.prod(c['quote']['decimal'] for c in legs)
            body += f'<p>Estimated independent-leg combined decimal price: {combined:.3f} · paper estimate, not an offered whole-card quote.</p>'
        body += '<p>Anytime grading includes overtime, excludes shootout attempts; settles only on verified final games. DNP/void rules vary by book: verify settlement yourself.</p>'
    body += '<p>' + e(strategy.QUOTE_NOTE) + '</p>'
    return CSS + '<section class="sc60" aria-label="the list">' + body + '</section>'


def render(st, day, results, rows, ctx, quotes, pbps=None, demo=False):
    import v55_ui as v5
    now = datetime.now(timezone.utc)
    rec = resolve(st.session_state, day, results, rows, ctx, quotes, now, demo)
    games = games_from_pbp(pbps)
    if rec.get('legs'):
        rec = strategy.settle(rec, games, now)
        st.session_state['sc60_quote:' + day] = rec
    v5.html_block(getattr(st, '_st', st), section_html(rec))
    if rec.get('legs'):
        with st.expander('Frozen explanatory notes / grading'):
            grades = (rec.get('results') or {}).get('notes') or []
            for i, n in enumerate(rec['notes']):
                st.write(f"{n['kind'].title()}: {n.get('pick') or n.get('game_id') or ''} · {n.get('criterion') or n.get('reason')} · {grades[i] if i < len(grades) else 'unknown'}")
            st.caption('Starter comparisons remain unknown without a reliable actual NHL starter flag; a live goalie-in-net observation is not proof of the starter. No retrospective best-game or fade claims.')
    with st.expander('Private odds, stakes & profit/loss ledger'):
        st.caption('Session-only: private entries are not written to GitHub or shared with other sessions. Download to retain them; reload/restart/session loss can erase them. Import only your own saved file. No bet is placed here.')
        key = 'sc60_private_ledger'
        entries = st.session_state.get(key, [])
        if rec.get('legs'):
            names = {'card': 'Whole 3-leg card (separate stake)'}
            names.update({str(c['pid']): f"Single: {c['name']}" for c in rec['legs']})
            with st.form('sc60_log_form'):
                target = st.selectbox('Track card OR single', list(names), format_func=names.get)
                placed = st.checkbox('I actually placed this bet (self-reported)', value=False)
                stake_text = st.text_input('Stake (blank = unknown; zero is valid)', value='')
                actual_text = st.text_input('Actual American odds (optional for paper; whole-card quote for card)', value='')
                book = st.text_input('Actual sportsbook (required for placed record)', value='')
                st.caption('Saving a card does not create singles. Enter singles only if separately tracked/wagered. Save once pregame; saved entries cannot be overwritten.')
                submitted = st.form_submit_button('Log privately — no bet placed')
            if submitted:
                try:
                    entries = ledger.add(entries, rec, target, float(stake_text) if stake_text.strip() else None,
                                         float(actual_text) if actual_text.strip() else None, book, placed, now)
                    st.success('Private record saved (duplicate save is a no-op).')
                except (ValueError, TypeError) as exc:
                    st.error(str(exc))
        up = st.file_uploader('Import private ledger JSON', type=['json'], key='sc60_import')
        if st.button('Restore imported ledger', key='sc60_restore') and up is not None:
            try:
                entries = ledger.restore(up.getvalue().decode('utf-8'))
                st.success('Private ledger restored in this session only.')
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                st.error('Invalid private ledger: ' + str(exc))
        records = {rec['id']: rec} if rec.get('id') else {}
        for entry in entries:
            frozen = entry['card']
            public = strategy.load(frozen['day'])
            if public and public['id'] == frozen['id']:
                records[frozen['id']] = public
            elif frozen['id'] not in records:
                records[frozen['id']] = strategy.settle(frozen, games, now)
        entries = ledger.grade(entries, records)
        # A final no-goal strategy result is not proof of book DNP/void settlement.
        if entries:
            entry_id = st.selectbox('Confirm bookmaker settlement for saved entry', [e['id'] for e in entries])
            chosen = next(e for e in entries if e['id'] == entry_id)
            required = chosen['card']['legs'] if chosen['target'] == 'card' else [c for c in chosen['card']['legs'] if str(c['pid']) == chosen['target']]
            with st.form('sc60_book_settlement'):
                dispositions = {str(c['pid']): st.selectbox('Book result: ' + c['name'], ['won', 'lost', 'void', 'push'],
                                                         key='sc60_result_' + str(c['pid'])) for c in required}
                settlement_note = st.text_input('Book settlement evidence / note (self-reported; required)', key='sc60_settlement_note')
                post_void = st.text_input('Book post-void whole-card American price, if repriced (optional)', key='sc60_postvoid')
                confirmed = st.form_submit_button('Confirm settlement privately — lock once')
            if confirmed:
                try:
                    entries = ledger.confirm_settlement(entries, entry_id, dispositions, settlement_note,
                                                        records.get(chosen['card']['id'], chosen['card']),
                                                        float(post_void) if post_void.strip() else None, now)
                    st.success('Self-reported settlement locked; original strategy calculation retained.')
                except (ValueError, TypeError) as exc:
                    st.error(str(exc))
        st.session_state[key] = entries
        display = []
        for entry in entries:
            out = entry['outcome']
            display.append({'Day': entry['card']['day'], 'Target': entry['target'], 'Tracking': out['tracking'], 'Stake': entry.get('stake'),
                            'Actual American odds': entry.get('actual_american'), 'Status': out['status'], 'Return': out['return'],
                            'P&L (paper if unplaced)': out['pnl'], 'Realized P&L (placed + book confirmed)': out['realized_pnl'], 'Settlement': out['settlement'], 'Payout basis': out['payout_basis']})
        if display:
            st.dataframe(display, hide_index=True, use_container_width=True)
        st.download_button('Download private ledger JSON', ledger.export(entries), file_name='playbook-private-ledger.json', mime='application/json', key='sc60_export')
