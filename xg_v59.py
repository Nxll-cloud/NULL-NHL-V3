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
LEAK_HOURS = 36    # file modified more than this after the slate day's 00:00 UTC could contain later games -> neutral
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


def for_day(data, day, season=None):
    """Gate a fetched structure for one slate day: wrong season, stale (> STALE_DAYS old) or a file newer than the
    day (historical slate -> would include later games) all return a neutral structure with the reason."""
    if not isinstance(data, dict) or not data.get('players'):
        return empty((data or {}).get('error') or 'no data', season or '')
    if season and mp_year(data.get('season')) != mp_year(season):
        return empty('season mismatch', season, data.get('as_of'))
    try:
        d = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
        a = datetime.fromisoformat(str(data.get('as_of')))
        a = a if a.tzinfo else a.replace(tzinfo=timezone.utc)
    except Exception:
        return data   # no comparable dates: trust the season check
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    if a < start - timedelta(days=STALE_DAYS):
        return empty('stale', data.get('season', ''), data.get('as_of'))
    if a > start + timedelta(hours=LEAK_HOURS):
        return empty('file newer than slate day (point-in-time: use aggregate_shots)', data.get('season', ''), data.get('as_of'))
    return data


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


def read_shots(src):
    """Rows of MoneyPuck shots_{yyyy}.zip/.csv (path or bytes) as dicts. Never raises ([] on failure)."""
    try:
        if isinstance(src, (bytes, bytearray)):
            src = io.BytesIO(src)
        if zipfile.is_zipfile(src):
            if hasattr(src, 'seek'):
                src.seek(0)
            with zipfile.ZipFile(src) as z:
                name = next(n for n in z.namelist() if n.endswith('.csv'))
                return list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding='utf-8')))
        with open(src, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
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
    out = {**empty('' if players else 'no shots before date', season, f'{cut}T00:00+00:00'), 'players': players}
    out['league'] = _league(players)
    return out
