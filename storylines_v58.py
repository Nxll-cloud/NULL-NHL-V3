"""V5.8 Storylines: tonight's narrative facts from real data only (display only - never feeds a model).

Sources (runtime, cached): NHL api-web player landing (birthDate, birthplace, seasonTotals, careerTotals,
last5Games), NHL game logs (meetings, streaks), NHL rosters + standings, ESPN public injuries / transactions /
news feeds, and a bundled GeoNames gazetteer (CC BY 4.0) for hometown distance. Nothing is guessed: a fact that
cannot be computed from those sources is simply not shown (e.g. new dads are not tracked).

Pure functions (offline-tested) come first; ``build`` orchestrates the fetches with injectable fetchers and
``Job`` runs ``build`` in a background thread so the page never blocks while ~500 landings load.
"""
import gzip
import html as _html
import math
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

G_REV = 'REVENGE GAMES'
G_FMR = 'FORMER TEAMS'
G_BIO = 'BIRTHDAYS · FIRST GAMES · HOMETOWNS'
G_VS = 'VS OPP · STREAKS & MILESTONES'
G_NEWS = 'NEWS · LAST 36H'
GROUPS = (G_REV, G_FMR, G_BIO, G_VS, G_NEWS)
LEGEND = 'Revenge = first game vs a former team since leaving; VS = regular season, whole career window shown, games shown'
HOME_KM = 300
NEWS_HOURS = 36
GEO_FILE = Path(__file__).resolve().parent / 'assets' / 'geo_near_arenas.txt.gz'

ARENAS = {'ANA': (33.808, -117.877), 'BOS': (42.366, -71.062), 'BUF': (42.875, -78.876), 'CGY': (51.037, -114.052),
          'CAR': (35.803, -78.722), 'CHI': (41.881, -87.674), 'COL': (39.749, -105.008), 'CBJ': (39.969, -83.006),
          'DAL': (32.790, -96.810), 'DET': (42.341, -83.055), 'EDM': (53.547, -113.498), 'FLA': (26.158, -80.326),
          'LAK': (34.043, -118.267), 'MIN': (44.945, -93.101), 'MTL': (45.496, -73.569), 'NSH': (36.159, -86.778),
          'NJD': (40.734, -74.171), 'NYI': (40.712, -73.726), 'NYR': (40.750, -73.993), 'OTT': (45.297, -75.927),
          'PHI': (39.901, -75.172), 'PIT': (40.439, -79.989), 'SJS': (37.333, -121.901), 'SEA': (47.622, -122.354),
          'STL': (38.627, -90.203), 'TBL': (27.943, -82.452), 'TOR': (43.643, -79.379), 'UTA': (40.768, -111.901),
          'VAN': (49.278, -123.109), 'VGK': (36.103, -115.178), 'WSH': (38.898, -77.021), 'WPG': (49.893, -97.144)}

TEAM_NAMES = {'ANA': 'Anaheim Ducks', 'BOS': 'Boston Bruins', 'BUF': 'Buffalo Sabres', 'CAR': 'Carolina Hurricanes',
              'CBJ': 'Columbus Blue Jackets', 'CGY': 'Calgary Flames', 'CHI': 'Chicago Blackhawks', 'COL': 'Colorado Avalanche',
              'DAL': 'Dallas Stars', 'DET': 'Detroit Red Wings', 'EDM': 'Edmonton Oilers', 'FLA': 'Florida Panthers',
              'LAK': 'Los Angeles Kings', 'MIN': 'Minnesota Wild', 'MTL': 'Montreal Canadiens', 'NJD': 'New Jersey Devils',
              'NSH': 'Nashville Predators', 'NYI': 'New York Islanders', 'NYR': 'New York Rangers', 'OTT': 'Ottawa Senators',
              'PHI': 'Philadelphia Flyers', 'PIT': 'Pittsburgh Penguins', 'SEA': 'Seattle Kraken', 'SJS': 'San Jose Sharks',
              'STL': 'St Louis Blues', 'TBL': 'Tampa Bay Lightning', 'TOR': 'Toronto Maple Leafs', 'UTA': 'Utah Mammoth',
              'VAN': 'Vancouver Canucks', 'VGK': 'Vegas Golden Knights', 'WPG': 'Winnipeg Jets', 'WSH': 'Washington Capitals'}
_EXTRA_NAMES = {'Utah Hockey Club': 'UTA', 'Utah HC': 'UTA', 'Arizona Coyotes': 'ARI', 'Phoenix Coyotes': 'ARI',
                'Atlanta Thrashers': 'ATL', 'Mighty Ducks of Anaheim': 'ANA'}
ESPN_ABBR = {'TB': 'TBL', 'NJ': 'NJD', 'SJ': 'SJS', 'LA': 'LAK', 'UTAH': 'UTA', 'WAS': 'WSH', 'VEG': 'VGK', 'MON': 'MTL'}
COUNTRY = {'CAN': 'CA', 'USA': 'US'}


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


_NAME_TO_ABBR = {norm(v): k for k, v in TEAM_NAMES.items()}
_NAME_TO_ABBR.update({norm(k): v for k, v in _EXTRA_NAMES.items()})


def team_abbr(name):
    """NHL landing teamName ('Montréal Canadiens', 'St. Louis Blues', 'Utah Hockey Club') -> abbreviation or ''."""
    n = norm(name)
    if not n:
        return ''
    if n in _NAME_TO_ABBR:
        return _NAME_TO_ABBR[n]
    return _NAME_TO_ABBR.get(n.replace('saint ', 'st '), '')


def fmt_season(season):
    s = str(season)
    return f'{s[:4]}-{s[6:8]}' if len(s) == 8 else s


def season_of(day):
    d = date.fromisoformat(str(day))
    y = d.year if d.month >= 7 else d.year - 1
    return int(f'{y}{y + 1}')


def seasons_between(first, last):
    """[20182019, ..., 20262027] inclusive (season ids as ints)."""
    a, b = int(str(first)[:4]), int(str(last)[:4])
    return [int(f'{y}{y + 1}') for y in range(a, b + 1)]


# ------------------------------------------------------------------------------------------------- landing facts
def nhl_stints(season_totals):
    """NHL regular-season totals per team: {abbr: {gp, g, a, p, first, last, name}}."""
    out = {}
    for s in season_totals or []:
        if s.get('leagueAbbrev') != 'NHL' or s.get('gameTypeId') != 2:
            continue
        name = (s.get('teamName') or {}).get('default') if isinstance(s.get('teamName'), dict) else s.get('teamName')
        ab = team_abbr(name)
        if not ab:
            continue
        r = out.setdefault(ab, {'gp': 0, 'g': 0, 'a': 0, 'p': 0, 'first': s.get('season'), 'last': s.get('season'), 'name': name})
        r['gp'] += int(s.get('gamesPlayed') or 0)
        r['g'] += int(s.get('goals') or 0)
        r['a'] += int(s.get('assists') or 0)
        r['p'] += int(s.get('points') or 0)
        r['first'] = min(r['first'], s.get('season'))
        r['last'] = max(r['last'], s.get('season'))
    return out


def nhl_seasons(season_totals):
    return sorted({int(s['season']) for s in season_totals or [] if s.get('leagueAbbrev') == 'NHL' and s.get('gameTypeId') == 2 and s.get('season')})


def birthday_age(birth_date, day):
    """Age turned on the slate day, or None."""
    try:
        b, d = date.fromisoformat(str(birth_date)), date.fromisoformat(str(day))
    except ValueError:
        return None
    return d.year - b.year if (b.month, b.day) == (d.month, d.day) else None


def games_on_or_after(last5, day):
    return sum(1 for g in last5 or [] if str(g.get('gameDate', '')) >= str(day) and g.get('gameTypeId', 2) == 2)


def gp_before(landing, day):
    """Current-season NHL regular-season GP strictly before the slate day (landing totals minus later games)."""
    cur = season_of(day)
    gp = sum(int(s.get('gamesPlayed') or 0) for s in landing.get('seasonTotals') or []
             if s.get('season') == cur and s.get('leagueAbbrev') == 'NHL' and s.get('gameTypeId') == 2)
    return max(0, gp - games_on_or_after(landing.get('last5Games'), day))


def career_before(landing, day):
    rs = ((landing.get('careerTotals') or {}).get('regularSeason') or {})
    later = [g for g in landing.get('last5Games') or [] if str(g.get('gameDate', '')) >= str(day) and g.get('gameTypeId', 2) == 2]
    return (int(rs.get('goals') or 0) - sum(int(g.get('goals') or 0) for g in later),
            int(rs.get('points') or 0) - sum(int(g.get('points') or 0) for g in later))


def milestone(goals, points):
    """Closest round-number milestone within reach tonight: ('points', 500, 2) / ('goals', 200, 1) / None."""
    out = []
    if points >= 97:
        nxt = (points // 100 + 1) * 100
        if nxt - points <= 3:
            out.append(('points', nxt, nxt - points))
    if goals >= 48:
        nxt = (goals // 50 + 1) * 50
        if nxt - goals <= 2:
            out.append(('goals', nxt, nxt - goals))
    return min(out, key=lambda m: m[2]) if out else None


# ------------------------------------------------------------------------------------------------- geography
def haversine_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def parse_gazetteer(text):
    """'#CC.adm|Name' admin lines + 'name|CC.adm|lat|lon' rows -> ({(norm name, 'CC.adm'): (lat, lon)}, {(CC, norm admin name): 'CC.adm'})."""
    places, admins = {}, {}
    for line in text.splitlines():
        if not line or line.startswith('# '):
            continue
        if line.startswith('#'):
            code, _, name = line[1:].partition('|')
            admins[(code.split('.')[0], norm(name))] = code
            admins[(code.split('.')[0], norm(code.split('.')[-1]))] = code    # postal-style 'MN', 'ON' also accepted
            continue
        parts = line.split('|')
        if len(parts) != 4:
            continue
        try:
            places.setdefault((norm(parts[0]), parts[1]), (float(parts[2]), float(parts[3])))
        except ValueError:
            continue
    return places, admins


_CA_POSTAL = {'AB': '01', 'BC': '02', 'MB': '03', 'NB': '04', 'NL': '05', 'NS': '07', 'ON': '08', 'PE': '09', 'QC': '10', 'SK': '11',
              'YT': '12', 'NT': '13', 'NU': '14'}


@lru_cache(maxsize=1)
def gazetteer():
    try:
        with gzip.open(GEO_FILE, 'rt', encoding='utf-8') as fh:
            places, admins = parse_gazetteer(fh.read())
    except OSError:
        return {}, {}
    for k, v in _CA_POSTAL.items():
        admins.setdefault(('CA', norm(k)), f'CA.{v}')
    return places, admins


def locate(city, province, country, geo=None):
    places, admins = geo or gazetteer()
    cc = COUNTRY.get(str(country or '').upper(), str(country or '').upper()[:2])
    if cc not in ('CA', 'US') or not city:
        return None
    adm = admins.get((cc, norm(province))) if province else None
    if adm:
        return places.get((norm(city), adm))
    hits = [v for (n, a), v in places.items() if n == norm(city) and a.startswith(cc + '.')]
    return hits[0] if len(hits) == 1 else None


def hometown(landing, arena_team, geo=None, limit_km=HOME_KM):
    """('Richmond Hill, Ontario', 31) when the birthplace is within limit_km of the arena, else None."""
    city = (landing.get('birthCity') or {}).get('default') if isinstance(landing.get('birthCity'), dict) else landing.get('birthCity')
    prov = (landing.get('birthStateProvince') or {}).get('default') if isinstance(landing.get('birthStateProvince'), dict) else landing.get('birthStateProvince')
    arena = ARENAS.get(arena_team)
    where = locate(city, prov, landing.get('birthCountry'), geo)
    if not (where and arena):
        return None
    km = haversine_km(where, arena)
    return (', '.join(x for x in (city, prov) if x), int(round(km))) if km <= limit_km else None


# ------------------------------------------------------------------------------------------------- game-log facts
def _before(logs, day):
    return sorted((g for g in logs or [] if str(g.get('gameDate', '')) < str(day)), key=lambda g: g.get('gameDate', ''), reverse=True)


def streak(games, key='points'):
    """Consecutive games (newest first) with key > 0."""
    n = 0
    for g in games:
        if int(g.get(key) or 0) > 0:
            n += 1
        else:
            break
    return n


def left_date(logs, team):
    dates = [g.get('gameDate', '') for g in logs or [] if g.get('teamAbbrev') == team]
    return max(dates) if dates else None


def former_status(team_logs_since, opp, left, day):
    """Meetings vs the former team (as an opponent) after leaving and before the slate -> (n, games)."""
    games = [g for g in team_logs_since if g.get('opponentAbbrev') == opp and g.get('teamAbbrev') != opp
             and (left is None or str(g.get('gameDate', '')) > str(left)) and str(g.get('gameDate', '')) < str(day)]
    return len(games), games


def vs_summary(logs, opp, day):
    allg = _before(logs, day)
    vs = [g for g in allg if g.get('opponentAbbrev') == opp]
    gp, gpa = len(vs), len(allg)
    tot = lambda gs, k: sum(int(g.get(k) or 0) for g in gs)
    return {'gp': gp, 'g': tot(vs, 'goals'), 'a': tot(vs, 'assists'), 'p': tot(vs, 'points'),
            'ppg': (tot(vs, 'points') / gp) if gp else None, 'ppg_all': (tot(allg, 'points') / gpa) if gpa else None,
            'gp_all': gpa, 'pstreak': streak(vs, 'points'), 'gstreak': streak(vs, 'goals'),
            'first': min((g.get('gameDate', '') for g in vs), default=None)}


def vs_story(s, opp):
    """(tag, story) for a notable vs-opponent record, else None."""
    if not s or not s['gp']:
        return None
    if s['gstreak'] >= 3:
        return 'VS TEAM', f'Goals in {s["gstreak"]} straight vs {opp}'
    if s['pstreak'] >= 4:
        return 'VS TEAM', f'Points in {s["pstreak"]} straight vs {opp}'
    if s['gp'] >= 5 and s['p'] >= 4 and s['ppg_all'] is not None and s['ppg'] >= max(s['ppg_all'] * 1.35, s['ppg_all'] + 0.25):
        return 'VS TEAM', f'{s["p"]} P in {s["gp"]} GP vs {opp}'
    return None


def hot_story(current_logs, day):
    g = _before(current_logs, day)
    ps, gs = streak(g, 'points'), streak(g, 'goals')
    if gs >= 3:
        run = g[:gs]
        return 'HOT STREAK', f'Goals in {gs} straight', run
    if ps >= 5:
        return 'HOT STREAK', f'Points in {ps} straight', g[:ps]
    return None


# ------------------------------------------------------------------------------------------------- news
def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except ValueError:
        return None


def age_label(ts, now):
    h = (now - ts).total_seconds() / 3600
    return f'{max(0, int(round(h * 60)))}m ago' if h < 1 else f'{int(h)}h ago'


def espn_team(abbr):
    a = str(abbr or '').upper()
    return ESPN_ABBR.get(a, a)


def news_rows(injuries, transactions, articles, players_by_name, slate_teams, now, hours=NEWS_HOURS):
    """ESPN feeds -> NEWS rows for slate players/teams within `hours`. Unknown shapes are ignored, never guessed."""
    rows, lo = [], now - timedelta(hours=hours)

    def player_for(name, team=None):
        hits = players_by_name.get(norm(name)) or []
        if team:
            hits = [p for p in hits if p['team'] == team] or hits
        return hits[0] if len(hits) == 1 else None

    for t in (injuries or {}).get('injuries', []) if isinstance(injuries, dict) else []:
        for i in t.get('injuries') or []:
            ts = _ts(i.get('date'))
            ath = i.get('athlete') or {}
            team = espn_team((ath.get('team') or {}).get('abbreviation'))
            if not ts or not (lo <= ts <= now) or team not in slate_teams:
                continue
            p = player_for(ath.get('displayName'), team)
            typ = ((i.get('details') or {}).get('type') or (i.get('type') or {}).get('description') or '').strip()
            ret = (i.get('details') or {}).get('returnDate')
            story = f"{i.get('status') or 'Injury'}{' · ' + typ if typ else ''}"
            detail = f"ESPN injury report · {age_label(ts, now)}" + (f' · return est. {ret}' if ret else '')
            if i.get('longComment') and len(i['longComment']) > 4:
                detail += ' · ' + i['longComment'][:160]
            rows.append({'tag': 'INJURY', 'name': ath.get('displayName'), 'team': team, 'player': p, 'story': story,
                         'detail': detail, 'link': '', 'ts': ts})
    for tr in (transactions or {}).get('transactions', []) if isinstance(transactions, dict) else []:
        ts = _ts(tr.get('date'))
        team = espn_team((tr.get('team') or {}).get('abbreviation'))
        desc = str(tr.get('description') or '')
        if not ts or not (lo <= ts <= now) or team not in slate_teams or not desc:
            continue
        p = next((pp for n, lst in players_by_name.items() for pp in lst if pp['team'] == team and n and n in norm(desc)), None)
        call = re.search(r'\b(recalled|called up|activated|assigned)\b', desc, re.I)
        rows.append({'tag': 'CALL-UP' if call and re.search(r'recall|called up', desc, re.I) else 'ROSTER', 'name': p['name'] if p else '',
                     'team': team, 'player': p, 'story': desc[:120], 'detail': f'ESPN transactions · {ts:%b %d} (date only)', 'link': '', 'ts': ts})
    for a in (articles or {}).get('articles', []) if isinstance(articles, dict) else []:
        ts = _ts(a.get('published'))
        if not ts or not (lo <= ts <= now) or a.get('type') == 'Media':
            continue
        names = [c.get('description') for c in a.get('categories') or [] if c.get('type') == 'athlete']
        for nm in names:
            p = player_for(nm)
            if p and p['team'] in slate_teams:
                link = ((a.get('links') or {}).get('web') or {}).get('href', '')
                rows.append({'tag': 'NEWS', 'name': p['name'], 'team': p['team'], 'player': p, 'story': str(a.get('headline') or '')[:140],
                             'detail': f'ESPN {a.get("type") or "story"} · {age_label(ts, now)}', 'link': link, 'ts': ts})
                break
    rows.sort(key=lambda r: r['ts'], reverse=True)
    seen, out = set(), []
    for r in rows:
        k = (r['tag'], r['name'], r['story'])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


# ------------------------------------------------------------------------------------------------- rows + grouping
def row(group, tag, p, story, detail, link='', source='NHL'):
    return {'group': group, 'tag': tag, 'pid': p.get('pid'), 'player': p.get('name', ''), 'team': p.get('team', ''),
            'opp': p.get('opp', ''), 'score': p.get('score'), 'rank': p.get('rank'), 'story': story, 'detail': detail,
            'link': link, 'source': source}


def grouped(rows):
    """[(group, rows sorted by model score desc, then name)] in GROUPS order; empty groups kept (rendered as empty)."""
    out = []
    for g in GROUPS:
        rs = [r for r in rows if r['group'] == g]
        if g != G_NEWS:
            rs.sort(key=lambda r: (-(r['score'] if isinstance(r.get('score'), (int, float)) else -1), r['player']))
        out.append((g, rs))
    return out


def counters(rows):
    c = lambda pred: sum(1 for r in rows if pred(r))
    return {'Revenge games': c(lambda r: r['group'] == G_REV), 'Former teams': c(lambda r: r['group'] == G_FMR),
            'Birthdays / first games / hometowns': c(lambda r: r['group'] == G_BIO), 'News stories': c(lambda r: r['group'] == G_NEWS)}


def landing_rows(p, landing, day, geo=None):
    """Bio rows (birthday, first game, hometown, milestone) for one player with game context p."""
    out = []
    age = birthday_age(landing.get('birthDate'), day)
    if age:
        out.append(row(G_BIO, 'BDAY', p, f'Turns {age} tonight', f'Born {landing.get("birthDate")}'))
    ht = hometown(landing, p.get('arena'), geo)
    if ht:
        out.append(row(G_BIO, 'HOMETOWN', p, f'Near home: born in {ht[0]}', f'~{ht[1]} km from the {p.get("arena")} arena', source='NHL + GeoNames'))
    if p.get('team_gp') and gp_before(landing, day) == 0:
        prev = [s for s in landing.get('seasonTotals') or [] if s.get('season') == season_of(day) - 10001 and s.get('leagueAbbrev') == 'NHL' and s.get('gameTypeId') == 2]
        pd_ = f" · {fmt_season(season_of(day) - 10001)}: {sum(int(s.get('goals') or 0) for s in prev)} G, {sum(int(s.get('points') or 0) for s in prev)} P in {sum(int(s.get('gamesPlayed') or 0) for s in prev)} GP" if prev else ''
        out.append(row(G_BIO, '1ST GAME', p, f'First game of {fmt_season(season_of(day))} if he dresses',
                       f'{p.get("team")} has played {p["team_gp"]} without him{pd_}'))
    g, pts = career_before(landing, day)
    m = milestone(g, pts)
    if m:
        out.append(row(G_VS, 'MILESTONE', p, f'{m[2]} {m[0][:-1] if m[2] == 1 else m[0]} from {m[1]}', f'Career NHL regular season: {g} G, {pts} P'))
    return out


def former_row(p, stint, n_since, partial=False):
    span = f'{fmt_season(stint["first"])} to {fmt_season(stint["last"])}' if stint['first'] != stint['last'] else fmt_season(stint['first'])
    base = f'{stint["g"]} G, {stint["p"]} P in {stint["gp"]} GP with the {stint.get("name") or p.get("opp")} ({span})'
    if n_since == 0 and not partial:
        return row(G_REV, 'REVENGE', p, f'First game vs {p["opp"]} since leaving', base)
    since = f'{n_since}+ games' if partial else f'{n_since} game{"s" if n_since != 1 else ""}'
    return row(G_FMR, 'FORMER', p, f'Faces former team {p["opp"]}', f'{base} · {since} vs them since')


# ------------------------------------------------------------------------------------------------- orchestration
def build(day, games, ranked, fetch, log_fn, espn_get=None, now=None, vs_top=40, workers=12, progress=None, max_seasons_since=8):
    """Everything for one slate. fetch(path) -> NHL JSON; log_fn(pid, season_str) -> gameLog list; espn_get(name) -> JSON.

    Returns {'rows', 'errors', 'sources', 'built_at', 'n_players'}. Any single failure only drops that fact."""
    now = now or datetime.now(timezone.utc)
    errors, sources = [], {}
    ctx = {}
    for g in games or []:
        a, h = g.get('away'), g.get('home')
        if a and h:
            ctx[a] = {'opp': h, 'arena': h}
            ctx[h] = {'opp': a, 'arena': h}
    players = {}
    for r in ranked or []:
        try:
            pid = int(float(r.get('Player ID')))
        except (TypeError, ValueError):
            continue
        t = r.get('Team')
        if t in ctx:
            players[pid] = {'pid': pid, 'name': r.get('Player', ''), 'team': t, 'score': r.get('V3.2 Adjusted Index'),
                            'rank': r.get('Statistical rank'), **ctx[t]}
    cur = season_of(day)

    def safe(fn, *a):
        try:
            return fn(*a), None
        except Exception as exc:  # network / HTTP / JSON: drop just this fact
            return None, f'{type(exc).__name__}'

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rosters = dict(zip(ctx, pool.map(lambda t: safe(fetch, f'roster/{t}/{cur}'), ctx)))
        for t, (data, err) in rosters.items():
            if err:
                errors.append(f'roster {t}: {err}')
                continue
            for grp in ('forwards', 'defensemen'):
                for sp in (data or {}).get(grp) or []:
                    pid = sp.get('id')
                    if pid and pid not in players:
                        nm = ((sp.get('firstName') or {}).get('default', '') + ' ' + (sp.get('lastName') or {}).get('default', '')).strip()
                        players[pid] = {'pid': pid, 'name': nm, 'team': t, 'score': None, 'rank': None, **ctx[t]}
        prev_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
        stand, err = safe(fetch, f'standings/{prev_day}')
        team_gp = {}
        if err:
            errors.append(f'standings: {err}')
        else:
            for s in (stand or {}).get('standings') or []:
                ab = (s.get('teamAbbrev') or {}).get('default') if isinstance(s.get('teamAbbrev'), dict) else s.get('teamAbbrev')
                if season_of(prev_day) == cur:
                    team_gp[ab] = int(s.get('gamesPlayed') or 0)
        for p in players.values():
            p['team_gp'] = team_gp.get(p['team'], 0)
        pids = list(players)
        total = len(pids)
        done = [0]

        def land(pid):
            out = safe(fetch, f'player/{pid}/landing')
            done[0] += 1
            if progress:
                progress(done[0], total)
            return out
        landings = dict(zip(pids, pool.map(land, pids)))
        sources['NHL player landing'] = f'{sum(1 for v in landings.values() if v[0])}/{total}'
        geo = gazetteer()
        rows, former_jobs = [], []
        for pid, (ld, err) in landings.items():
            if not ld:
                continue
            p = players[pid]
            p['name'] = p['name'] or f"{(ld.get('firstName') or {}).get('default', '')} {(ld.get('lastName') or {}).get('default', '')}".strip()
            rows += landing_rows(p, ld, day, geo)
            st_ = nhl_stints(ld.get('seasonTotals'))
            if p['opp'] in st_ and p['opp'] != p['team']:
                former_jobs.append((p, st_[p['opp']]))
            p['_seasons'] = nhl_seasons(ld.get('seasonTotals'))

        def former(job):
            p, stint = job
            seasons = [s for s in seasons_between(stint['last'], cur)]
            partial = len(seasons) > max_seasons_since
            seasons = seasons[-max_seasons_since:] if partial else seasons
            logs = []
            for s in seasons:
                lg, e = safe(log_fn, p['pid'], str(s))
                if e:
                    return row(G_FMR, 'FORMER', p, f'Faces former team {p["opp"]}', 'Game log unavailable - meetings since leaving not checked')
                logs += lg or []
            left = left_date(logs, p['opp']) if not partial else None
            n, _ = former_status(logs, p['opp'], left, day)
            return former_row(p, stint, n, partial)
        rows += [r for r in pool.map(former, former_jobs) if r]

        ranked_ps = sorted((p for p in players.values() if isinstance(p.get('rank'), (int, float))), key=lambda p: p['rank'])[:vs_top]

        def vs(p):
            seasons = [s for s in (p.get('_seasons') or []) if s <= cur][-5:]
            if cur not in seasons:
                seasons.append(cur)
            logs, cur_log = [], []
            for s in seasons:
                lg, e = safe(log_fn, p['pid'], str(s))
                if e:
                    continue
                logs += lg or []
                if s == cur:
                    cur_log = lg or []
            out = []
            s = vs_summary(logs, p['opp'], day)
            vsx = vs_story(s, p['opp'])
            if vsx:
                since = fmt_season(season_of(s['first'])) if s['first'] else '—'
                ratio = f'{s["ppg"]:.2f} P/GP vs {p["opp"]} vs {s["ppg_all"]:.2f} overall' if s['ppg_all'] is not None else ''
                out.append(row(G_VS, vsx[0], p, vsx[1], f'{s["g"]} G, {s["p"]} P in {s["gp"]} GP vs {p["opp"]} since {since} · {ratio}'))
            hot = hot_story(cur_log, day)
            if hot:
                run = hot[2]
                out.append(row(G_VS, hot[0], p, hot[1], f'{sum(int(g.get("goals") or 0) for g in run)} G, {sum(int(g.get("points") or 0) for g in run)} P over the run ({fmt_season(cur)})'))
            return out
        for rs in pool.map(vs, ranked_ps):
            rows += rs
        sources['NHL game logs (vs opp / streaks)'] = f'top {len(ranked_ps)} by NP rank'

        by_name = {}
        for p in players.values():
            by_name.setdefault(norm(p['name']), []).append(p)
        feeds = {}
        if espn_get is not None:
            for k in ('injuries', 'transactions', 'news'):
                feeds[k], e = safe(espn_get, k)
                if e:
                    errors.append(f'ESPN {k}: {e}')
        sources['ESPN injuries / transactions / news'] = 'ok' if feeds and all(v is not None for v in feeds.values()) else ('partial' if any(v is not None for v in feeds.values()) else 'unavailable')
        for n in news_rows(feeds.get('injuries'), feeds.get('transactions'), feeds.get('news'), by_name, set(ctx), now):
            p = n['player'] or {'pid': None, 'name': n['name'] or '—', 'team': n['team'], 'opp': (ctx.get(n['team']) or {}).get('opp', ''),
                                'score': None, 'rank': None}
            rows.append(row(G_NEWS, n['tag'], p, n['story'], n['detail'], n['link'], 'ESPN'))
    return {'rows': rows, 'errors': errors, 'sources': sources, 'built_at': now.isoformat(), 'n_players': len(players),
            'feeds_ok': bool(feeds) and any(v is not None for v in feeds.values())}


class Job:
    """Background build for one slate key; the tab polls status without blocking the page."""

    def __init__(self, key, fn):
        self.key, self.done, self.total, self.result, self.error = key, 0, 0, None, None
        self.started = time.time()
        self.finished = None
        self._t = threading.Thread(target=self._run, args=(fn,), daemon=True, name='storylines-v58')
        self._t.start()

    def progress(self, done, total):
        self.done, self.total = done, total

    def _run(self, fn):
        try:
            self.result = fn(self.progress)
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'
        self.finished = time.time()

    @property
    def running(self):
        return self.finished is None


_JOBS, _LOCK = {}, threading.Lock()
RESULT_TTL = 3 * 3600


def job_for(key, fn, force=False):
    """Shared per-process job per slate key; a finished result is reused for RESULT_TTL seconds."""
    with _LOCK:
        j = _JOBS.get(key)
        stale = j is not None and j.finished is not None and (time.time() - j.finished > RESULT_TTL or j.error)
        if j is None or force or stale:
            j = _JOBS[key] = Job(key, fn)
        for k in [k for k, v in _JOBS.items() if k != key and v.finished and time.time() - v.finished > RESULT_TTL]:
            _JOBS.pop(k, None)
        return j


# ------------------------------------------------------------------------------------------------- runtime fetchers (TTL)
_TTL = {'landing': 12 * 3600, 'roster': 6 * 3600, 'standings': 3600, 'log': 3600, 'espn': 900}
_CACHE, _CLOCK = {}, threading.Lock()
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/'


def _cached(kind, key, fn):
    """Thread-safe TTL cache (the build runs in a worker thread, outside Streamlit's script context)."""
    now = time.time()
    with _CLOCK:
        hit = _CACHE.get((kind, key))
        if hit and now - hit[0] < _TTL[kind]:
            return hit[1]
    val = fn()
    with _CLOCK:
        _CACHE[(kind, key)] = (now, val)
        if len(_CACHE) > 6000:
            for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:2000]:
                _CACHE.pop(k, None)
    return val


def nhl_fetch(path):
    import nhl_data
    kind = 'landing' if path.endswith('/landing') else 'roster' if path.startswith('roster/') else 'standings'
    return _cached(kind, path, lambda: nhl_data.fetch_json(path))


def nhl_log(pid, season, current=None):
    """Past seasons reuse history_v386.season_log (process lru); the current season gets a 1h TTL."""
    import history_v386
    import nhl_data
    if current is not None and str(season) != str(current):
        return history_v386.season_log(int(pid), str(season))
    return _cached('log', (int(pid), str(season)), lambda: nhl_data.get_game_log(int(pid), str(season)))


def espn_fetch(kind):
    import requests
    url = ESPN + {'injuries': 'injuries', 'transactions': 'transactions', 'news': 'news?limit=50'}[kind]

    def go():
        r = requests.get(url, timeout=12, headers={'User-Agent': 'NullsPlaybook/5.8'})
        r.raise_for_status()
        return r.json()
    return _cached('espn', kind, go)


OUT_STATUSES = ('out', 'injured reserve', 'long term injured reserve', 'suspended', 'suspension')


def out_players(injuries):
    """ESPN injuries JSON -> {(norm name, team)} for players listed as out (Day-To-Day is NOT treated as out)."""
    out = set()
    for t in (injuries or {}).get('injuries', []) if isinstance(injuries, dict) else []:
        for i in t.get('injuries') or []:
            ath = i.get('athlete') or {}
            if norm(i.get('status')) in OUT_STATUSES:
                out.add((norm(ath.get('displayName')), espn_team((ath.get('team') or {}).get('abbreviation'))))
    return out


def stories_for_day(day):
    """{pid: [tags]} from a finished Storylines build for this slate (empty when the tab has not been built)."""
    out = {}
    with _LOCK:
        jobs = [j for k, j in _JOBS.items() if k and k[0] == day and j.result]
    for j in jobs[-1:]:
        for r in j.result['rows']:
            if r.get('pid') and r['group'] != G_NEWS:
                out.setdefault(r['pid'], []).append(r['tag'])
    return out


def row_html(r, stars=(), score='—', badge=''):
    """One Storylines table row (V5.9: moved out of the tab so the scored-tonight badge is testable). ``badge`` is
    scorers_tonight_v58.badge_for(...) html, placed right after the name text; display only."""
    e = _html.escape
    star = ''.join(f'<span class="sl-star" title="{e(x)}">★ {e(x)}</span>' for x in stars)
    story = e(r['story'])
    if r.get('link'):
        story = f'<a href="{e(r["link"])}" target="_blank" rel="noopener">{story}</a>'
    return (f'<tr><td><span class="sl-tag t-{norm(r["tag"]).replace(" ", "-")}">{e(r["tag"])}</span></td>'
            f'<td class="sl-p"><b>{e(r["player"] or "—")}{badge}</b>{star}</td><td>{e(r["team"] or "—")}</td>'
            f'<td>{e(r["opp"] or "—")}</td><td class="sl-n">{score}</td><td class="sl-s">{story}</td>'
            f'<td class="sl-d">{e(r["detail"])} <small>· {e(r["source"])}</small></td></tr>')
