"""EdgeLab-only quote scope/identity validation. No API calls or prediction changes."""
from collections import Counter
from html import escape
import re
import unicodedata
from zoneinfo import ZoneInfo
import pandas as pd
from matchup_center_v54 import TEAM_NAMES

ET = ZoneInfo('America/New_York')
MARKETS = {'player_goal_scorer_anytime', 'anytime goal', 'anytime goalscorer', 'anytime goal scorer'}
STATES = {
    'missing_key': 'No provider key: set top-level ODDS_API_KEY in Streamlit secrets (environment-only is not read).',
    'configuration': 'Invalid provider key configuration: top-level ODDS_API_KEY must be a string.',
    'auth': 'Provider rejected credentials or market access (401/403).',
    'quota': 'Provider quota / rate limit reached (429).',
    'timeout': 'Provider request timed out.', 'network': 'Provider network unavailable.',
    'malformed': 'Malformed provider data; no invented prices.', 'unavailable': 'Provider temporarily unavailable.',
    'empty': 'Provider returned no available quotes: markets may be omitted, suspended/live or unavailable.',
    'partial': 'Partial provider feed: some events were skipped.', 'ok': 'Provider returned quotes.'}


def text(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    return '' if value.casefold() in ('nan', 'none', 'null', '<na>', 'unknown', 'unknown player', 'tbd', 'not available', 'n/a') else value


def name_key(value):
    v = unicodedata.normalize('NFKD', text(value)).casefold()
    v = ''.join(c for c in v if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z]+', v))


def ident(value):
    if value is None or isinstance(value, bool):
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        return ''
    return str(value).strip().removesuffix('.0')


def stamp(value):
    try:
        t = pd.to_datetime(value, errors='coerce', utc=True)
        return None if pd.isna(t) else t
    except (ValueError, TypeError):
        return None


def team(value):
    key = name_key(value).replace(' ', '')
    for code, full in TEAM_NAMES.items():
        if key in (name_key(code).replace(' ', ''), name_key(full).replace(' ', '')):
            return code
    return ''


def game_key(slate):
    return ident(slate.get('game_id')) or '|'.join((text(slate.get('away')), text(slate.get('home')), str(stamp(slate.get('start')))))


def aliases(value):
    words = name_key(value).split()
    if not words:
        return set()
    compact = ''.join(words)
    return {compact, ''.join(w[0] for w in words[:-1]) + words[-1]}


def initial_name(value):
    words = name_key(value).split()
    prefix = text(value).rsplit(' ', 1)[0] if len(words)>1 else ''
    letters = ''.join(c for c in prefix if c.isalpha())
    return len(words)>1 and (all(len(w)==1 for w in words[:-1]) or (0<len(letters)<=3 and letters.isupper()))


def alias_match(a, b):
    return (name_key(a).replace(' ','') == name_key(b).replace(' ','')) or (
        (initial_name(a) or initial_name(b)) and bool(aliases(a) & aliases(b)))


class PriceBook(dict):
    """Only verified (current game, model player) keys; never name-only fallback in production."""
    def get_for(self, slate, player):
        return self.get((game_key(slate), ident(player.get('pid'))))


def _scope(q, games, day, origin):
    # Numeric NHL-format event IDs can be imported without confusing opaque sportsbook IDs with NHL IDs.
    gid = ident(q.get('nhl_game_id'))
    if not gid:
        raw = ident(q.get('game_id')) or ident(q.get('event_id'))
        gid = raw if re.fullmatch(r'20\d{8}', raw) else ''
    home, away = team(q.get('home_team')), team(q.get('away_team'))
    if (text(q.get('home_team')) and not home) or (text(q.get('away_team')) and not away):
        return None, 'unknown event team'
    at = stamp(q.get('commence_time'))
    date = text(q.get('game_date')) or text(q.get('slate_date'))
    if at is not None:
        event_day = at.tz_convert(ET).date().isoformat()
        if date and date != event_day:
            return None, 'conflicting event date'
        date = event_day
    if date and date != day:
        return None, 'different slate date'
    if gid:
        matches = [g for g in games if ident(g['slate'].get('game_id')) == gid]
        if len(matches) != 1:
            return None, 'unknown NHL game ID'
        g = matches[0]
        if (home and home != g['slate']['home']) or (away and away != g['slate']['away']):
            return None, 'conflicting game teams'
        return g, None
    if home and away and date:
        matches = [g for g in games if (g['slate']['home'], g['slate']['away']) == (home, away)]
    elif origin == 'csv' and date and team(q.get('team')):
        code = team(q.get('team'))
        matches = [g for g in games if code in (g['slate']['away'], g['slate']['home'])]
    else:
        return None, 'missing event mapping: supply NHL game ID or teams + game date/start'
    return (matches[0], None) if len(matches) == 1 else (None, 'ambiguous or unknown event')


def prepare(quotes, results, day, source='Automatic API'):
    import edgelab_v58 as elv
    report = {'received': len(quotes) if isinstance(quotes, pd.DataFrame) else 0,
              'accepted': 0, 'excluded': {}, 'source': source, 'origins': {}}
    rejects = Counter()
    games = []
    for r in results or []:
        at = stamp(r['slate'].get('start'))
        if at is not None and at.tz_convert(ET).date().isoformat() == day:
            games.append(r)
    grouped = {}
    if not isinstance(quotes, pd.DataFrame) or quotes.empty:
        report['excluded'] = {}
        return PriceBook(), report
    required = {'player', 'market', 'selection', 'american_odds', 'sportsbook', 'updated_at'}
    if required - set(quotes.columns):
        report['excluded'] = {'missing quote columns: ' + ', '.join(sorted(required - set(quotes.columns))): len(quotes)}
        return PriceBook(), report
    for q in quotes.to_dict('records'):
        origin = text(q.get('_quote_origin')) or ('csv' if source == 'Uploaded CSV' else 'provider')
        if q.get('demo') is True or any(tag in text(q.get('source')).casefold() for tag in ('demo','synthetic','simulated')):
            rejects['explicit demo/synthetic price'] += 1
            continue
        if ident(q.get('line')):
            rejects['unsupported line on anytime Yes contract'] += 1
            continue
        if name_key(q.get('market')) not in {name_key(m) for m in MARKETS} or text(q.get('selection')).casefold() != 'yes':
            rejects['unsupported market or non-affirmative selection'] += 1
            continue
        if not name_key(q.get('player')):
            rejects['missing player name'] += 1
            continue
        if not text(q.get('sportsbook')) or stamp(q.get('updated_at')) is None or elv._implied(q.get('american_odds')) is None:
            rejects['invalid book, price or quote timestamp'] += 1
            continue
        g, reason = _scope(q, games, day, origin)
        if reason:
            rejects[reason] += 1
            continue
        possible = [p for p in g['result']['players'] if name_key(p.get('name')) and ident(p.get('pid'))]
        qt = team(q.get('team'))
        if text(q.get('team')) and not qt:
            rejects['unknown quote team'] += 1
            continue
        if qt:
            possible = [p for p in possible if p.get('team') == qt]
        nhl_pid = ident(q.get('nhl_player_id'))
        if not nhl_pid and text(q.get('player_id_namespace')).casefold() == 'nhl':
            nhl_pid = ident(q.get('player_id'))
        if nhl_pid:
            possible = [p for p in possible if ident(p.get('pid')) == nhl_pid]
            if len(possible) == 1 and name_key(q['player']) != name_key(possible[0]['name']) and not alias_match(q['player'],possible[0]['name']):
                possible = []  # conflicting ID/name never guessed
        else:
            exact = [p for p in possible if name_key(p['name']) == name_key(q['player'])]
            possible = exact if exact and not initial_name(q['player']) else [p for p in possible if alias_match(q['player'],p['name'])]
        if len(possible) != 1:
            rejects['ambiguous or unmatched player in this game/team'] += 1
            continue
        p = possible[0]
        row = dict(q, player=p['name'])
        grouped.setdefault((game_key(g['slate']), ident(p['pid'])), []).append(row)
        report['accepted'] += 1
        report['origins'][origin] = report['origins'].get(origin,0) + 1
    book = PriceBook()
    for key, rows in grouped.items():
        price = elv.live_prices(pd.DataFrame(rows)).get(name_key(rows[0]['player']))
        if price:
            origins={text(r.get('_quote_origin')) or ('csv' if source == 'Uploaded CSV' else 'provider') for r in rows}
            price['source']='provider + imported CSV' if len(origins)>1 else 'imported CSV' if 'csv' in origins else 'provider'
            book[key] = price
    report['excluded'] = dict(rejects)
    return book, report


def status_html(report, feed=None):
    feed = feed or {}
    source = report['source']
    lines = []
    if source in ('Automatic API', 'Combine both'):
        lines.append(STATES.get(feed.get('state'), 'Provider status unavailable; no credential inference.'))
        if feed.get('events') is not None:
            lines.append(f"Events returned {int(feed['events'])}; assessed {int(feed.get('attempted_events',0))}; skipped errors {int(feed.get('failed_events',0))}.")
        if feed.get('issues'):
            lines.append('Provider issues: ' + ', '.join(f"{code} ({int(n)})" for code,n in feed['issues'].items() if code in STATES))
        if stamp(feed.get('fetched_at')) is not None:
            lines.append('Provider fetch started ' + str(stamp(feed['fetched_at'])) + '.')
        if feed.get('retry_after_seconds') is not None:
            lines.append(f"{'Cached' if feed.get('cached') else 'Cache policy'} · {int(feed.get('retry_after_seconds',0))}s until eligible refresh; healthy 30m, partial/empty 60s, errors 30–300s. No per-widget retry.")
    else:
        lines.append('Uploaded CSV selected: imported prices, not an automatic live provider feed. An API key alone does not select it.')
    if source in ('Uploaded CSV','Combine both'):
        lines.append('CSV mapping: supply nhl_game_id, or home_team + away_team + commence_time; alternatively team + game_date (YYYY-MM-DD). updated_at alone is not a game date.')
    if source == 'Combine both':
        lines.append('Combined provider + uploaded CSV; imported rows remain user-supplied quotes.')
    lines.append(f"Source: {source}. Received {report['received']} quotes; accepted {report['accepted']} mapped affirmative quotes.")
    if report.get('origins'):
        lines.append('Accepted origin counts: ' + ', '.join(f'{k} {v}' for k,v in report['origins'].items()) + '.')
    if report['excluded']:
        lines.append('Excluded: ' + '; '.join(f'{reason} ({n})' for reason,n in report['excluded'].items()) + '.')
    if not report['accepted']:
        lines.append('No eligible mapped prices. Model rows remain visible without an edge; no synthetic fallback.')
    return ('<style>.v58-el .el-feed{box-sizing:border-box;max-width:100%;min-width:0;overflow-wrap:anywhere;'
            'border-left:2px solid var(--neon,#00e5ff);padding:4px 12px;margin:8px 0;font-size:.82rem;}'
            '.v58-el .el-feed p{margin:6px 0}</style>') + '<section class="el-feed" aria-label="EdgeLab price feed status">' + ''.join('<p>'+escape(v)+'</p>' for v in lines) + '</section>'
