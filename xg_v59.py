"""V5.9 shot-quality (xG) weighting for the next-goal model, layered on the V5.8 situational layer.

Source: MoneyPuck.com season skater summary (``moneypuck.com/moneypuck/playerData/seasonSummary/{yyyy}/regular/skaters.csv``),
one of the files MoneyPuck lists on its public data page (moneypuck.com/data.htm). MoneyPuck terms: free for
non-commercial use; "clearly credit MoneyPuck.com" wherever something using the data is shown -> ``CREDIT`` caption.
Only the listed CSV is downloaded (no page scraping), once per ~6h via the app cache.

Per player and situation (EV = MoneyPuck '5on5', PP = '5on4', no split = 'all'):

    q_raw    = xG / SOG                                   (MoneyPuck I_F_xGoals / I_F_shotsOnGoal)
    q        = (xG + K_XG*L) / (SOG + K_XG)               shrunk toward the league xG/SOG L of the same file+situation
    Q        = clamp(q / L, Q_LO, Q_HI)                   relative shot quality (1 = league-average looks)
    F        = clamp((G + K_FIN) / (xG + K_FIN), F_LO, F_HI)   finishing factor, heavily shrunk (K_FIN ghost goals)
    xq       = T * Q * F                                  T = the app's own league sh% for that situation
    sh_new   = W * xq + (1 - W) * sh_situational          sh_situational = the V5.8 shrunk sh% (50 ghost shots)
    mult     = sh_new / sh_situational                    applied to that situation's part of lambda

Using Q *relative* to the same file's league xG/SOG (instead of MoneyPuck's absolute xG) keeps league totals on the
app's existing calibration (shot-weighted mean of Q ~= 1), so goals per team-game do not drift. With no usable xG for
a player (missing, unmatched, zero SOG in that situation, failed/stale fetch, flag off) mult is exactly 1.0, i.e. the
situational model's numbers are reproduced bit for bit.

'other' (MoneyPuck) is not used for EV quality: it mixes empty-net, 3-on-3, 4-on-4 and 6-on-5 shots (league xG/SOG
~0.27), which would inflate players who take empty-net shots.

Point-in-time backtests: ``aggregate_shots`` builds the same structure from MoneyPuck's per-shot file restricted to
games with gameDate < D (dates from the NHL stats ``/game`` endpoint via ``fetch_game_dates``)."""
import csv
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

SOURCE = 'MoneyPuck.com'
CREDIT = 'Shot-quality (xG) data: MoneyPuck.com'
URL = 'https://moneypuck.com/moneypuck/playerData/seasonSummary/{yr}/regular/skaters.csv'
SHOTS_URL = 'https://peter-tanner.com/moneypuck/downloads/shots_{yr}.zip'
GAMES_URL = 'https://api.nhle.com/stats/rest/en/game'
UA = {'User-Agent': "NullsPlaybook/5.9 (+non-commercial hobby app; credits MoneyPuck.com)"}

W = 0.6            # weight on the xG-based expectation (xG/shot stabilises far faster than sh%)
K_XG = 50.0        # ghost shots at league xG/SOG
K_FIN = 25.0       # ghost goals for the finishing factor (heavy shrinkage)
Q_LO, Q_HI = 0.6, 1.6
F_LO, F_HI = 0.85, 1.15
STALE_DAYS = 10    # file older than this vs the slate day -> neutral
ET = ZoneInfo('America/New_York')
# Audit fix (2026-10, replaces LEAK_HOURS = 36): a season file is accepted for a slate only when it was modified BEFORE the
# slate's first puck drop (or, when puck times are unknown, before 00:00 ET on the slate date). The old 36 h-after-00:00 UTC
# window let a file refreshed the next morning (~32-36 h, after the slate's games were final) leak those results in.
# An undated file is trusted only for today's / future slates; for a past slate it is rejected (use ``point_in_time``).
SITS = {'ev': '5on5', 'pp': '5on4', 'all': 'all'}
_COLS = ('playerId', 'season', 'situation', 'I_F_xGoals', 'I_F_shotsOnGoal', 'I_F_goals')


def mp_year(season):
    """App season '20262027' -> MoneyPuck folder/season '2026' (start year)."""
    s = str(season or '').strip()
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else ''


def empty(error='', season='', as_of=None):
    return {'players': {}, 'league': {}, 'season': season, 'as_of': as_of, 'source': SOURCE, 'error': error}


def _f(x):
    try:
        v = float(x)
        return v if v == v else 0.0
    except (TypeError, ValueError):
        return 0.0


def _league(players):
    out = {}
    for sit in SITS.values():
        xg = sum(p[sit][0] for p in players.values() if sit in p)
        sog = sum(p[sit][1] for p in players.values() if sit in p)
        if sog > 0 and xg > 0:
            out[sit] = xg / sog
    return out


def parse_csv(text, season=''):
    """MoneyPuck skaters.csv -> {'players': {pid: {situation: (xG, SOG, G)}}, 'league': {situation: xG/SOG}}.
    Rows of another season are dropped; a malformed file returns an empty structure with ``error``."""
    try:
        rd = csv.DictReader(io.StringIO(text or ''))
        if not rd.fieldnames or any(c not in rd.fieldnames for c in _COLS):
            return empty('unexpected columns', season)
        yr = mp_year(season)
        players, wrong = {}, 0
        for r in rd:
            if yr and str(r.get('season', '')).strip() != yr:
                wrong += 1
                continue
            sit = r.get('situation')
            if sit not in SITS.values():
                continue
            try:
                pid = int(float(r['playerId']))
            except (TypeError, ValueError):
                continue
            players.setdefault(pid, {})[sit] = (_f(r['I_F_xGoals']), _f(r['I_F_shotsOnGoal']), _f(r['I_F_goals']))
        if not players:
            return empty('season mismatch' if wrong else 'no rows', season)
        return {**empty('', season), 'players': players, 'league': _league(players)}
    except Exception as e:  # never raise
        return empty(f'parse error: {type(e).__name__}', season)


def _default_get(url, params=None):
    import requests
    r = requests.get(url, params=params, timeout=20, headers=UA)
    r.raise_for_status()
    return r


def fetch(season, getter=None):
    """Download + parse the season summary. Never raises; on any failure returns an empty (neutral) structure.
    ``as_of`` = the file's Last-Modified (ISO, UTC) when the server sends it, else the fetch time."""
    yr = mp_year(season)
    if not yr:
        return empty('bad season', season)
    try:
        r = (getter or _default_get)(URL.format(yr=yr))
        text = r.text if hasattr(r, 'text') else str(r)
        lm = (getattr(r, 'headers', None) or {}).get('Last-Modified')
        try:
            as_of = parsedate_to_datetime(lm).astimezone(timezone.utc) if lm else datetime.now(timezone.utc)
        except Exception:
            as_of = datetime.now(timezone.utc)
        out = parse_csv(text, season)
        out['as_of'] = as_of.isoformat(timespec='minutes')
        return out
    except Exception as e:
        return empty(f'fetch failed: {type(e).__name__}', season)


def _utc(x):
    if x is None or x == '':
        return None
    try:
        d = x if isinstance(x, datetime) else datetime.fromisoformat(str(x).replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def slate_cutoff(day, games=None):
    """Point-in-time cutoff for a slate: its first puck drop (UTC) from ``games`` rows ('Start (UTC)' / 'start' /
    'startTimeUTC'), else 00:00 America/New_York on the slate date. ``day`` = date or 'YYYY-MM-DD'."""
    starts = [_utc((g or {}).get('Start (UTC)') or (g or {}).get('start') or (g or {}).get('startTimeUTC'))
              for g in (games or ()) if isinstance(g, dict)]
    starts = [x for x in starts if x]
    if starts:
        return min(starts)
    d = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    return datetime(d.year, d.month, d.day, tzinfo=ET).astimezone(timezone.utc)


PIT_ERRORS = ('file not before first puck drop', 'undated file for a past slate')


def for_day(data, day, season=None, cutoff=None, now=None):
    """Gate a fetched structure for one slate day. Neutral structure (with the reason) when: wrong season; stale
    (> STALE_DAYS before the cutoff); modified at/after the slate's first puck drop (``cutoff``; default = 00:00 ET on
    the slate date), which could contain that slate's results; or undated while the slate is already in the past
    (``now``'s ET date > slate date). Undated files are trusted for today's / future slates (the fetch is current)."""
    if not isinstance(data, dict) or not data.get('players'):
        return empty((data or {}).get('error') or 'no data', season or '')
    if season and mp_year(data.get('season')) != mp_year(season):
        return empty('season mismatch', season, data.get('as_of'))
    try:
        d = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    except (TypeError, ValueError):
        return empty('bad slate day', data.get('season', ''), data.get('as_of'))
    cut = _utc(cutoff) or slate_cutoff(d)
    a = _utc(data.get('as_of'))
    if a is None:
        today = (now or datetime.now(timezone.utc)).astimezone(ET).date()
        if d < today:
            return empty(PIT_ERRORS[1] + ' (point-in-time: use aggregate_shots)', data.get('season', ''), data.get('as_of'))
        return data
    if a < cut - timedelta(days=STALE_DAYS):
        return empty('stale', data.get('season', ''), data.get('as_of'))
    if a >= cut:
        return empty(PIT_ERRORS[0] + ' (point-in-time: use aggregate_shots)', data.get('season', ''), data.get('as_of'))
    return data


def needs_point_in_time(gated):
    """True when ``for_day`` rejected a file only because of its date (a point-in-time rebuild can replace it)."""
    return bool(gated) and not gated.get('players') and any(e in str(gated.get('error') or '') for e in PIT_ERRORS)


_PIT_CACHE = {}


def point_in_time(day, season, getter=None, cache=_PIT_CACHE):
    """Season-summary-shaped xG built ONLY from games dated before ``day`` (MoneyPuck per-shot file + NHL game dates).
    Used when the season file is too new for a past slate. Never raises (neutral structure on failure). The parsed
    per-shot rows are cached per season in-process (the zip is large)."""
    yr = mp_year(season)
    if not yr:
        return empty('bad season', season)
    try:
        if season not in cache:
            dates = fetch_game_dates(season, getter)
            r = (getter or _default_get)(SHOTS_URL.format(yr=yr))
            raw = getattr(r, 'content', r)
            rows = read_shots(raw, SHOT_COLUMNS) if isinstance(raw, (bytes, bytearray)) else []
            if not dates or not rows:
                return empty('point-in-time data unavailable', season)
            cache[season] = (rows, dates)
        rows, dates = cache[season]
        out = aggregate_shots(rows, str(day)[:10], dates, season)
        out['source'] = SOURCE + ' (point-in-time, per-shot file)'
        return out
    except Exception as e:
        return empty(f'point-in-time failed: {type(e).__name__}', season)


def quality(data, pid, key):
    """Shrunk relative shot quality for one player/situation key ('ev'|'pp'|'all'). None = no usable data."""
    if not data or not data.get('players'):
        return None
    sit = SITS[key]
    L = (data.get('league') or {}).get(sit)
    row = (data['players'].get(pid) or data['players'].get(_int(pid)) or {}).get(sit)
    if not L or not row or row[1] <= 0:
        return None
    xg, sog, g = row
    q = (xg + K_XG * L) / (sog + K_XG)
    Q = min(Q_HI, max(Q_LO, q / L))
    F = min(F_HI, max(F_LO, (g + K_FIN) / (xg + K_FIN)))
    return {'sit': sit, 'sog': sog, 'xg': round(xg, 3), 'goals': g, 'xg_per_shot_raw': round(xg / sog, 4),
            'xg_per_shot_shrunk': round(q, 4), 'league_xg_per_shot': round(L, 4), 'quality': round(Q, 4),
            'finishing': round(F, 4)}


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def blend(sh, target, qinfo, w=W):
    """(multiplier, info) for one situation. Exactly (1.0, None) without xG info or a usable sh%."""
    if not qinfo or not sh or sh <= 0 or not target:
        return 1.0, None
    xq = target * qinfo['quality'] * qinfo['finishing']
    new = w * xq + (1 - w) * sh
    m = new / sh
    return m, {**qinfo, 'sh_before': round(sh, 4), 'xq': round(xq, 4), 'sh_after': round(new, 4), 'mult': round(m, 4)}


def why_bit(xg):
    """Short EdgeLab tooltip fragment, e.g. 'xG ×1.08 EV / ×0.95 PP'."""
    if not xg:
        return ''
    parts = [f"×{xg[k]['mult']:.2f} {lbl}" for k, lbl in (('ev', 'EV'), ('pp', 'PP'), ('all', 'all')) if xg.get(k)]
    return ('xG ' + ' / '.join(parts)) if parts else ''


def attribution(results=None, data=None):
    """Credit caption when any shown chance used MoneyPuck xG (or when the loaded data is usable)."""
    used = any((p.get('situ') or {}).get('xg') for r in (results or []) for p in ((r or {}).get('result', r) or {}).get('players', []) or [])
    return CREDIT if used or (data and data.get('players')) else ''


# ------------------------------------------------------------------ point-in-time helpers (backtests)
def fetch_game_dates(season, getter=None):
    """{NHL game id: 'YYYY-MM-DD'} for the regular season from the NHL stats API. Never raises ({} on failure)."""
    try:
        r = (getter or _default_get)(GAMES_URL, params={'cayenneExp': f'season={season} and gameType=2'})
        js = r.json() if hasattr(r, 'json') else r
        return {int(g['id']): str(g['gameDate'])[:10] for g in js.get('data', []) if g.get('id') and g.get('gameDate')}
    except Exception:
        return {}


SHOT_COLUMNS = ('game_id', 'shooterPlayerId', 'xGoal', 'goal', 'shotWasOnGoal', 'homeSkatersOnIce', 'awaySkatersOnIce',
                'isHomeTeam', 'shotOnEmptyNet', 'isPlayoffGame', 'season')   # all aggregate_shots reads


def _trim(rows, columns):
    return [{k: r.get(k) for k in columns} for r in rows] if columns else list(rows)


def read_shots(src, columns=None):
    """Rows of MoneyPuck shots_{yyyy}.zip/.csv (path or bytes) as dicts (only ``columns`` when given, to keep a
    full-season file small in memory). Never raises ([] on failure)."""
    try:
        if isinstance(src, (bytes, bytearray)):
            src = io.BytesIO(src)
        if zipfile.is_zipfile(src):
            if hasattr(src, 'seek'):
                src.seek(0)
            with zipfile.ZipFile(src) as z:
                name = next(n for n in z.namelist() if n.endswith('.csv'))
                return _trim(csv.DictReader(io.TextIOWrapper(z.open(name), encoding='utf-8')), columns)
        with open(src, encoding='utf-8') as fh:
            return _trim(csv.DictReader(fh), columns)
    except Exception:
        return []


def aggregate_shots(rows, before, game_dates, season=''):
    """Season-summary-shaped structure from per-shot rows of regular-season games with gameDate < ``before``.
    Situations: 5on5 / 5on4 by skaters on ice (shooting team first); 'all' = every situation. As in MoneyPuck's summary,
    xG sums every unblocked attempt and SOG counts shots on goal (goals included). Empty-net shots are excluded from every situation. MoneyPuck game_id 20001 -> NHL id {start year}020001."""
    yr = mp_year(season) or ''
    cut = str(before)[:10]
    pl = {}
    for r in rows or []:
        try:
            if str(r.get('isPlayoffGame', '0')) not in ('0', '0.0') or _f(r.get('shotOnEmptyNet')):
                continue
            gid = int(float(r['game_id']))
            nhl = int(f"{yr or str(r.get('season', ''))[:4]}{gid:06d}") if gid < 1_000_000 else gid
            gd = game_dates.get(nhl)
            if not gd or gd >= cut:
                continue
            pid = int(float(r['shooterPlayerId']))
            home = _f(r.get('isHomeTeam')) == 1
            us, them = (r.get('homeSkatersOnIce'), r.get('awaySkatersOnIce')) if home else (r.get('awaySkatersOnIce'), r.get('homeSkatersOnIce'))
            us, them = int(_f(us)), int(_f(them))
        except (TypeError, ValueError, KeyError):
            continue
        # MoneyPuck convention: xG over every unblocked attempt, divided by shots on goal
        xg, g, on = _f(r.get('xGoal')), _f(r.get('goal')), 1.0 if (_f(r.get('shotWasOnGoal')) or _f(r.get('goal'))) else 0.0
        sits = ['all'] + (['5on5'] if (us, them) == (5, 5) else ['5on4'] if (us, them) == (5, 4) else [])
        for s in sits:
            a = pl.setdefault(pid, {}).setdefault(s, [0.0, 0.0, 0.0])
            a[0] += xg
            a[1] += on
            a[2] += g
    players = {p: {s: tuple(v) for s, v in d.items()} for p, d in pl.items()}
    # as_of = 00:00 UTC on the cutoff date: strictly before any NHL puck drop that day, so for_day accepts it
    out = {**empty('' if players else 'no shots before date', season, f'{cut}T00:00+00:00'), 'players': players}
    out['league'] = _league(players)
    return out
