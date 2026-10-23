"""V5.8 'Scored tonight' - one shared source of truth for every model view (display only).

Goal events come from the play-by-play the app already polls for the selected slate (live_feed_v56 /
live_nextgoal_v56.Poller: backoff, eventId dedupe, stops when final). Nothing here changes a probability, a
ranking or a pick: it only decorates player entries with a goal-light badge.

* ``from_pbp(pbp, day)`` -> {'day', 'demo', 'players': {pid: rec}, 'names': {name: pid}}
* Matching is by NHL playerId; a displayed name is used only when it maps to exactly one slate roster player.
* The record lives in session_state keyed by slate date, so a new slate date starts empty (rollover reset).
* ``MarkingStreamlit`` wraps the ``st`` module: st.markdown / st.html get badges after matching player names,
  st.dataframe gets a leading '🚨 Tonight' column. With no scorers every call passes through unchanged.
"""
import html as _html
import re
import unicodedata

STATE_KEY = 'v58_scorers'
COL = '🚨 Tonight'
ID_COLS = ('Player ID', 'player_id', 'playerId', 'Shooter ID', 'pid')
NAME_COLS = ('Player', 'player', 'Shooter', 'Name', 'name')
_STR = {'PP': 'PPG', 'SH': 'SHG', 'EN': 'ENG'}


def norm(name):
    s = unicodedata.normalize('NFKD', str(name or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z]+', ' ', s).strip()


def _pid(v):
    try:
        if v is None or isinstance(v, bool):
            return None
        f = float(v)
        if f != f:
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def clock(period, ptype, secs):
    p = 'OT' if ptype == 'OT' else f'P{period}'
    secs = int(secs or 0)
    return f'{p} {secs // 60:02d}:{secs % 60:02d}'


def from_pbp(pbp, day, demo=False):
    """{game_id: parsed live_nextgoal_v56.parse_pbp game} -> scorer record. Shootout goals never count."""
    players, roster_names = {}, {}
    for gid, game in (pbp or {}).items():
        if not isinstance(game, dict):
            continue
        roster = game.get('roster') or {}
        for rpid, r in roster.items():
            p = _pid(rpid)
            if p is not None:
                roster_names.setdefault(norm(r.get('name')), set()).add(p)
        label = f"{game.get('away', '')} @ {game.get('home', '')}".strip()
        for e in game.get('events') or []:
            if e.get('kind') != 'goal' or e.get('ptype') == 'SO':
                continue
            p = _pid(e.get('shooter'))
            if p is None:
                continue
            info = roster.get(p) or roster.get(str(p)) or {}
            rec = players.setdefault(p, {'player_id': p, 'name': info.get('name') or str(p), 'team': e.get('team') or info.get('team', ''),
                                         'game': label, 'game_id': str(game.get('game_id') or gid), 'goals': 0, 'events': []})
            strength = e.get('strength') or 'EV'
            rec['events'].append({'eid': e.get('eid'), 'period': e.get('period'), 'ptype': e.get('ptype'), 'secs': e.get('secs'),
                                  'time': clock(e.get('period'), e.get('ptype'), e.get('secs')), 'strength': strength,
                                  'ppg': strength == 'PP', 'eng': strength == 'EN' or e.get('goalie') in (None, ''),
                                  'shg': strength == 'SH'})
    for rec in players.values():   # dedupe by eventId (a game may be merged twice) and count
        seen, ev = set(), []
        for e in sorted(rec['events'], key=lambda e: ((e.get('period') or 0), (e.get('secs') or 0))):
            k = e.get('eid') if e.get('eid') is not None else (e['time'], e['strength'])
            if k in seen:
                continue
            seen.add(k)
            ev.append(e)
        rec['events'], rec['goals'] = ev, len(ev)
    names = {}
    for p, rec in players.items():
        n = norm(rec['name'])
        if n and roster_names.get(n, {p}) == {p}:   # unique on the slate rosters -> safe for name-only views
            names[n] = p
    return {'day': str(day), 'demo': bool(demo), 'players': players, 'names': names}


def empty(day):
    return {'day': str(day), 'demo': False, 'players': {}, 'names': {}}


def for_slate(state, day, record):
    """Store the record under the slate date; a record for another date is replaced by an empty one (rollover reset)."""
    if record is None or str(record.get('day')) != str(day):
        record = empty(day)
    state[STATE_KEY] = record
    return record


def active(state, day=None):
    rec = state.get(STATE_KEY) if state is not None else None
    if not rec or (day is not None and rec.get('day') != str(day)):
        return None
    return rec if rec.get('players') else None


def lookup(record, pid=None, name=None):
    if not record:
        return None
    p = _pid(pid)
    if p is not None:
        return record['players'].get(p)
    if name:
        q = record['names'].get(norm(name))
        return record['players'].get(q) if q is not None else None
    return None


def short(rec):
    if not rec:
        return ''
    g = rec.get('goals', 0)
    return '🚨 G' if g == 1 else f'🚨 {g}G'


def tooltip(rec, demo=False):
    if not rec:
        return ''
    parts = [e['time'] + (f" {_STR[e['strength']]}" if e.get('strength') in _STR else '') for e in rec.get('events', [])]
    pre = 'DEMO replay · ' if demo else ''
    return f"{pre}Scored tonight ({rec.get('game', '')}): " + ' · '.join(parts)


def badge(rec, demo=False):
    if not rec:
        return ''
    cls = 'npsc multi' if rec.get('goals', 0) > 1 else 'npsc'
    if demo:
        cls += ' demo'
    return f'<span class="{cls}" title="{_html.escape(tooltip(rec, demo))}" role="img" aria-label="{_html.escape(tooltip(rec, demo))}">{short(rec)}</span>'


def ticker(record):
    """Header chip: who has scored tonight (empty string when nobody has)."""
    if not record or not record.get('players'):
        return ''
    recs = sorted(record['players'].values(), key=lambda r: (-r['goals'], r['name']))
    items = ''.join(f'<span class="npst-i">{_html.escape(r["name"])} <b>{"" if r["goals"] == 1 else str(r["goals"])}G</b></span>' for r in recs[:14])
    more = f'<span class="npst-i">+{len(recs) - 14} more</span>' if len(recs) > 14 else ''
    demo = '<span class="npst-demo">DEMO replay</span>' if record.get('demo') else ''
    n = sum(r['goals'] for r in recs)
    return (f'<div class="npst" role="status"><span class="npst-h">🚨 Scored tonight · {len(recs)} players · {n} goals</span>{demo}'
            f'<div class="npst-l">{items}{more}</div></div>')


def _name_regex(record):
    names = []
    for p, rec in record['players'].items():
        if norm(rec['name']) in record['names']:
            names.append((_html.escape(rec['name'], quote=False), rec))
    if not names:
        return None, {}
    names.sort(key=lambda x: -len(x[0]))
    rx = re.compile(r'(?<=>)(\s*)(' + '|'.join(re.escape(n) for n, _ in names) + r')(?=\s*(?:<|·|,|\(|\||&nbsp;))(?!\s*<span class="npsc)')
    return rx, {n: r for n, r in names}


def mark_html(text, record):
    """Insert a badge after every displayed text node that starts with a scorer's unique name."""
    if not record or not record.get('players') or not isinstance(text, str) or '>' not in text:
        return text
    rx, by = _name_regex(record)
    if rx is None:
        return text
    demo = record.get('demo')
    return rx.sub(lambda m: m.group(1) + m.group(2) + badge(by[m.group(2)], demo), text)


def mark_frame(frame, record):
    """DataFrame copy with a leading '🚨 Tonight' column ('' when the player has not scored). Same object if no match."""
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover
        return frame
    if not record or not record.get('players') or not isinstance(frame, pd.DataFrame) or frame.empty or COL in frame.columns:
        return frame
    idc = next((c for c in ID_COLS if c in frame.columns), None)
    nmc = next((c for c in NAME_COLS if c in frame.columns), None)
    if idc is None and nmc is None:
        return frame
    vals = []
    for _, r in frame.iterrows():
        rec = lookup(record, r.get(idc)) if idc is not None and _pid(r.get(idc)) is not None else (lookup(record, name=r.get(nmc)) if nmc else None)
        vals.append(short(rec) + (' DEMO' if rec and record.get('demo') else ''))
    if not any(vals):
        return frame
    out = frame.copy()
    out.insert(0, COL, vals)
    return out


class MarkingStreamlit:
    """Transparent proxy for the streamlit module used by app.py and the tab bodies (display only)."""

    def __init__(self, module):
        object.__setattr__(self, '_st', module)
        import inspect
        for name in ('markdown', 'html', 'dataframe'):       # keep the real signatures (v55_ui.html_mode inspects st.html)
            real, mine = getattr(module, name, None), getattr(type(self), name)
            if real is None:
                continue
            def bound(*a, _m=mine, **k):
                return _m(self, *a, **k)
            try:
                bound.__signature__ = inspect.signature(real)
            except (TypeError, ValueError):
                pass
            bound.__doc__, bound.__name__ = getattr(real, '__doc__', None), name
            object.__setattr__(self, name, bound)

    def __getattr__(self, name):
        return getattr(self._st, name)

    def __setattr__(self, name, value):
        setattr(self._st, name, value)

    def _rec(self):
        try:
            state = self._st.session_state
            rec = state.get(STATE_KEY)
        except Exception:
            return None
        return rec if rec and rec.get('players') else None

    def markdown(self, body, *a, **k):
        rec = self._rec()
        if rec and k.get('unsafe_allow_html'):
            body = mark_html(body, rec)
        return self._st.markdown(body, *a, **k)

    def html(self, body, *a, **k):
        rec = self._rec()
        if rec:
            body = mark_html(body, rec)
        return self._st.html(body, *a, **k)

    def dataframe(self, data=None, *a, **k):
        rec = self._rec()
        if rec:
            new = mark_frame(data, rec)
            if new is not data:
                order = k.get('column_order')
                if order:
                    k['column_order'] = [COL] + [c for c in order if c != COL]
                data = new
        return self._st.dataframe(data, *a, **k)
