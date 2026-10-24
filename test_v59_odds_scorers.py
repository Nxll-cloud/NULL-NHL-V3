"""V5.9 Projected scorers (odds): maths, sources, empty state, flag, and placement on the Odds tab + Home."""
import math
import re
from pathlib import Path

import pandas as pd
import pytest

import feature_flags_v58 as flags
import odds_scorers_v59 as o
from v54_testkit import run_app, slate

GAMES = [{'Away': 'MTL', 'Home': 'CHI'}, {'Away': 'TBL', 'Home': 'COL'}]
RANK = [{'Player': 'Cole Caufield', 'Player ID': 8481540, 'Team': 'MTL', 'Position': 'RW'},
        {'Player': 'Nathan MacKinnon', 'Player ID': 8477492, 'Team': 'COL', 'Position': 'C'},
        {'Player': 'Juraj Slafkovský', 'Player ID': 8483515, 'Team': 'MTL', 'Position': 'LW'},
        {'Player': 'Spencer Knight', 'Player ID': 8481519, 'Team': 'CHI', 'Position': 'G'}]


def Q(player, book, american, game='MTL @ CHI', team='MTL', updated='2026-10-23T21:00Z', **kw):
    return {'player': player, 'book': book, 'american': american, 'game': game, 'team': team, 'updated': updated, **kw}


# ---------------------------------------------------------------- price -> probability, vig
@pytest.mark.parametrize('a,p', [(100, .5), ('+300', .25), (-200, 2 / 3), ('EVEN', .5), ('−150', .6)])
def test_american_to_implied(a, p):
    assert o.implied(a) == pytest.approx(p)


@pytest.mark.parametrize('bad', [None, '', 'abc', 50, -99, float('nan'), float('inf'), True])
def test_bad_prices_rejected(bad):
    assert o.implied(bad) is None and o.parse_american(bad) is None


def test_decimal_and_label():
    assert o.decimal(250) == pytest.approx(3.5) and o.decimal(-125) == pytest.approx(1.8)
    assert o.price_label(285) == '+285' and o.price_label('-110') == '-110' and o.price_label(None) == '—'


def test_vig_removal_fixed_documented_margin():
    assert o.FAIR_FACTOR == 0.86 and '0.86' in o.METHOD_NOTE and '4,958' in o.METHOD_NOTE
    assert o.no_vig(o.implied(100)) == pytest.approx(.43)
    assert o.no_vig(0.5) < 0.5 and o.no_vig(None) is None and o.no_vig(2.0) == 1.0


# ---------------------------------------------------------------- aggregation + ranking
def test_aggregate_across_books_median_mean_best():
    rows = o.aggregate([Q('Cole Caufield', 'fanduel', 120), Q('Cole Caufield', 'DraftKings', 110),
                        Q('Cole Caufield', 'BetMGM', 100, updated='2026-10-23T22:00Z')])
    assert len(rows) == 1
    r = rows[0]
    assert list(r['books']) == ['FanDuel', 'DraftKings', 'BetMGM'] and r['n_books'] == 3
    fair = sorted(o.no_vig(o.implied(a)) for a in (120, 110, 100))
    assert r['consensus'] == pytest.approx(fair[1]) and r['mean'] == pytest.approx(sum(fair) / 3)
    assert r['best'] == {'book': 'FanDuel', 'american': 120}
    assert r['updated'] == '2026-10-23T22:00Z'


def test_same_book_duplicate_keeps_better_price_and_drops_bad():
    r, = o.aggregate([Q('A B', 'DraftKings', 200), Q('A B', 'draftkings', 220), Q('A B', 'FanDuel', 'x'), Q('', 'FanDuel', 200)])
    assert r['books'] == {'DraftKings': 220}


def test_rank_consensus_then_books_then_name():
    rows = o.aggregate([Q('Zed', 'FanDuel', 200), Q('Amy', 'FanDuel', 200), Q('Amy', 'DraftKings', 200),
                        Q('Top', 'FanDuel', 105), Q('Low', 'FanDuel', 400, game='TBL @ COL', team='TBL')])
    assert [r['player'] for r in rows] == ['Top', 'Amy', 'Zed', 'Low']
    assert [r['player'] for r in o.rank(rows, 2)] == ['Top', 'Amy']
    g = o.by_game(rows)
    assert list(g) == ['MTL @ CHI', 'TBL @ COL'] and [r['player'] for r in g['TBL @ COL']] == ['Low']


# ---------------------------------------------------------------- sources
def _api_df():
    base = {'market': 'player_goal_scorer_anytime', 'away_team': 'Montréal Canadiens', 'home_team': 'Chicago Blackhawks',
            'updated_at': '2026-10-23T20:00Z'}
    return pd.DataFrame([{**base, 'player': 'Cole Caufield', 'selection': 'Yes', 'sportsbook': 'FanDuel', 'american_odds': 115},
                         {**base, 'player': 'Cole Caufield', 'selection': 'Yes', 'sportsbook': 'DraftKings', 'american_odds': 110},
                         {**base, 'player': 'Cole Caufield', 'selection': 'No', 'sportsbook': 'DraftKings', 'american_odds': -150},
                         {**base, 'player': 'Juraj Slafkovsky', 'selection': 'Yes', 'sportsbook': 'FanDuel', 'american_odds': 190},
                         {**base, 'player': 'Other', 'selection': 'Yes', 'sportsbook': 'FanDuel', 'american_odds': 300,
                          'away_team': 'Boston Bruins', 'home_team': 'Buffalo Sabres'}])


def test_odds_api_first_and_espn_not_called():
    calls = []
    d = o.load('2026-10-23', GAMES, RANK, _api_df(), lambda day, idx: calls.append(day) or ([], []))
    assert d['source'] == o.SOURCE_API and calls == [] and d['demo'] is False
    top = d['rows'][0]
    assert top['player'] == 'Cole Caufield' and top['books'] == {'FanDuel': 115, 'DraftKings': 110}
    assert top['game'] == 'MTL @ CHI' and top['team'] == 'MTL' and top['pid'] == '8481540'
    slaf = next(r for r in d['rows'] if 'Slafkov' in r['player'])
    assert slaf['team'] == 'MTL' and slaf['pid'] == '8483515'      # accent-insensitive slate match
    assert not any(r['player'] == 'Other' for r in d['rows'])      # off-slate event dropped
    assert d['books'] == ['FanDuel', 'DraftKings']


def test_no_key_path_falls_back_to_espn():
    d = o.load('2026-10-23', GAMES, RANK, None, lambda day, idx: ([Q('Cole Caufield', 'DraftKings', 110)], []))
    assert d['source'] == o.SOURCE_ESPN and d['rows'][0]['books'] == {'DraftKings': 110}
    d2 = o.load('2026-10-23', GAMES, RANK, pd.DataFrame(), lambda day, idx: ([Q('X', 'DraftKings', 110)], []))
    assert d2['source'] == o.SOURCE_ESPN   # key set but no anytime prices -> still ESPN


def test_no_source_gives_empty_never_demo():
    d = o.load('2026-10-23', GAMES, RANK, None, lambda day, idx: ([], ['ESPN scoreboard unavailable']))
    assert d['source'] is None and d['rows'] == [] and d['demo'] is False
    h = o.section_html(d)
    assert 'os-empty' in h and 'No sportsbook anytime-goal prices' in h and 'DEMO' not in h and 'os-r' not in h


class _R:
    def __init__(self, js, status=200):
        self.js, self.status_code = js, status

    def json(self):
        return self.js


def _espn_getter(fail_props=False):
    sb = {'events': [{'id': '1', 'competitions': [{'competitors': [
        {'homeAway': 'home', 'team': {'id': '17', 'abbreviation': 'COL'}},
        {'homeAway': 'away', 'team': {'id': '20', 'abbreviation': 'TB'}}]}]}]}
    ros = {'17': {'athletes': [{'items': [{'id': '9', 'fullName': 'Nathan MacKinnon', 'position': {'abbreviation': 'C'}},
                                          {'id': '8', 'fullName': 'Mackenzie Blackwood', 'position': {'abbreviation': 'G'}}]}]},
           '20': {'athletes': [{'items': [{'id': '7', 'fullName': 'Nikita Kucherov', 'position': {'abbreviation': 'RW'}}]}]}}
    item = lambda aid, v, kind='Anytime Goalscorer': {'type': {'name': kind}, 'odds': {'american': {'value': v}},
                                                      'lastUpdated': '2026-10-23T21:44Z',
                                                      'athlete': {'$ref': f'http://x/athletes/{aid}?lang=en'}}
    props = {'items': [item('9', '+115'), item('7', '+160'), item('8', '+5000'), item('7', '+900', 'Total Points'), item('99', '+200')]}

    def get(url, timeout=None, headers=None):
        if 'scoreboard' in url:
            return _R(sb)
        if 'roster' in url:
            return _R(ros[url.split('/teams/')[1].split('/')[0]])
        if 'propBets' in url:
            if fail_props:
                raise ConnectionError('offline')
            return _R(props)
        return _R({}, 404)
    return get


def test_fetch_espn_parses_draftkings_props():
    idx = o.slate_index(GAMES, RANK)
    q, w = o.fetch_espn('2026-10-23', idx, _espn_getter())
    assert w == []
    by = {x['player']: x for x in q}
    assert set(by) == {'Nathan MacKinnon', 'Nikita Kucherov', 'Mackenzie Blackwood'}   # other markets / unknown ids skipped
    assert by['Nathan MacKinnon']['team'] == 'COL' and by['Nathan MacKinnon']['game'] == 'TBL @ COL'
    assert by['Nathan MacKinnon']['pid'] == '8477492' and by['Nikita Kucherov']['team'] == 'TBL'   # TB -> TBL
    assert all(x['book'] == 'DraftKings' for x in q)
    rows = o.aggregate(q)
    assert rows[0]['player'] == 'Nathan MacKinnon' and rows[0]['consensus'] == pytest.approx(o.no_vig(100 / 215))


def test_fetch_espn_offline_degrades():
    idx = o.slate_index(GAMES, RANK)
    q, w = o.fetch_espn('2026-10-23', idx, _espn_getter(fail_props=True))
    assert q == [] and w == ['TBL @ COL: no props']

    def dead(*a, **k):
        raise ConnectionError('offline')
    assert o.fetch_espn('2026-10-23', idx, dead) == ([], ['ESPN scoreboard unavailable'])


# ---------------------------------------------------------------- HTML (odds only)
def _data():
    return o.load('2026-10-23', GAMES, RANK, None, lambda d, i: ([Q('Cole Caufield', 'FanDuel', 115), Q('Cole Caufield', 'DraftKings', 110),
                                                                   Q('Spencer Knight', 'DraftKings', 5000, team='CHI', position='G'),
                                                                   Q('Nathan MacKinnon', 'DraftKings', 115, game='TBL @ COL', team='COL')], []))


def test_section_html_odds_only_columns():
    h = o.section_html(_data(), limit=10, per_game=True)
    assert 'Projected scorers (odds)' in h and 'ESPN (DraftKings)' in h and 'prices updated' in h and 'fetched' in h
    assert 'Cole Caufield' in h and 'FD +115' in h and 'DK +110' in h and 'best +115 FD' in h and 'MTL · MTL @ CHI' in h
    assert 'class="npg"' in h and ">G</span>" in h                     # shared goalie badge
    assert h.count('<details class="os-g">') == 2
    low = h.lower()
    for banned in ('model', 'gap', 'edge'):
        assert banned not in re.sub(r'market view only, not the model', '', low)
    assert 'DEMO' not in h


def test_compact_home_variant_same_columns():
    h = o.section_html(_data(), limit=1, per_game=False, hint='Full list: ⚡ Odds tab')
    assert h.count('class="os-r"') == 1 and '<details' not in h and 'Full list: ⚡ Odds tab' in h
    assert 'FD +115' in h and 'best +115 FD' in h and '%</b>' in h


def test_html_escapes_and_css_sanitizer_safe():
    d = o.load('d', [], [], None, lambda *_: ([Q('<script>x', 'DraftKings', 200)], []))
    assert '<script>' not in o.section_html(d)
    css = open('assets/v58.css', encoding='utf-8').read()
    block = css[css.index('V5.9 Projected scorers'):]
    assert '.v59-os' in block and not re.search(r'<[a-zA-Z/!]', block)


def test_flag_default_on_and_off():
    assert flags.SHOW_ODDS_SCORERS is True and flags.show_odds_scorers(secrets={}, environ={}) is True
    assert flags.show_odds_scorers(secrets={'FEATURE_ODDS_SCORERS': 'false'}, environ={}) is False
    assert flags.show_odds_scorers(secrets={}, environ={'FEATURE_ODDS_SCORERS': '0'}) is False


# ---------------------------------------------------------------- AppTest placement
def _flat(node):
    out = []
    for c in getattr(node, 'children', {}).values():
        if getattr(c, 'children', None) and c.type not in ('markdown',):
            out.extend(_flat(c))
        else:
            out.append((c.type, str(getattr(c, 'value', getattr(c, 'label', '')))))
    return out


def _tab(at, label):
    return next(t for t in at.tabs if t.label == label)


@pytest.fixture
def fake_espn():
    """Canned ESPN propBets + rosters for the testkit's scoreboard fixture (the app's real fetch path, offline)."""
    from v54_testkit import load
    sb = load('espn_scoreboard_20261022.json')   # trimmed fixture: give each team an id, as the live feed does
    snap, routes, rows, aid = slate(), {'scoreboard?dates': sb}, [], 1000
    for n, ev in enumerate(sb['events']):
        items = []
        for k, c in enumerate(ev['competitions'][0]['competitors']):
            c['team']['id'] = str(100 + 2 * n + k)
            ab = o.ESPN_ABBR.get(c['team']['abbreviation'], c['team']['abbreviation'])
            roster = []
            for r in [r for r in snap['rankings'] if r['Team'] == ab][:3]:
                aid += 1
                roster.append({'id': str(aid), 'fullName': r['Player'], 'position': {'abbreviation': r.get('Position') or 'C'}})
                price = 110 + 15 * (aid % 13)
                items.append({'type': {'name': 'Anytime Goalscorer'}, 'odds': {'american': {'value': f'+{price}'}},
                              'lastUpdated': '2026-10-23T21:44Z', 'athlete': {'$ref': f'http://x/athletes/{aid}?lang=en'}})
                rows.append({'player': r['Player'], 'american': price})
            routes[f"/teams/{c['team']['id']}/roster"] = {'athletes': [{'items': roster}]}
        routes[f"/events/{ev['id']}/competitions"] = {'items': items}
    rows.sort(key=lambda x: (x['american'], o.norm_name(x['player'])))
    return routes, rows


def _odds_scorers_block(at):
    """The Odds tab's Projected scorers block (V5.9 t141u: second, directly under the Odds Intelligence banner)."""
    return next(v for _, v in _flat(_tab(at, '⚡ Odds')) if 'v59-os' in v)


def test_odds_tab_renders_banner_then_projected_scorers_and_rest_unchanged(monkeypatch, tmp_path, fake_espn):
    routes, rows = fake_espn
    at = run_app(monkeypatch, tmp_path, routes=routes)
    on = _flat(_tab(at, '⚡ Odds'))
    assert 'ODDS INTELLIGENCE' in on[0][1] and 'Odds Intelligence' in on[0][1]          # the banner is first
    assert 'Projected scorers (odds)' in on[1][1] and 'ESPN (DraftKings)' in on[1][1]   # projected scorers directly under it
    assert rows[0]['player'] in on[1][1] and f"DK +{rows[0]['american']}" in on[1][1]
    assert sum('Projected scorers (odds)' in v for _, v in on) == 1
    monkeypatch.setenv('FEATURE_ODDS_SCORERS', '0')
    off = _flat(_tab(run_app(monkeypatch, tmp_path, routes=routes), '⚡ Odds'))
    assert not any('Projected scorers' in v for _, v in off) and 'ODDS INTELLIGENCE' in off[0][1]
    ts = re.compile(r'\d{1,2}:\d{2}(:\d{2})?|\d{4}-\d{2}-\d{2}T[\d:.+Z-]+')
    assert [(t, ts.sub('', v)) for t, v in on[:1] + on[2:]] == [(t, ts.sub('', v)) for t, v in off]   # everything else, same order


def test_odds_tab_banner_before_projected_scorers_source_order():
    """t141u: layout-only move - the banner call precedes the projected-scorers call in tabs/odds.py, each exactly once."""
    src = (Path(__file__).resolve().parent / 'tabs' / 'odds.py').read_text()
    ban = "st.markdown(v5.tab_head('NULL’S PLAYBOOK · ODDS INTELLIGENCE'"
    sc = "v5.html_block(st,oddsc.section_html(_np_odds_scorers,limit=10,per_game=True),extra_class='v59-osw')"
    assert src.count(ban) == 1 and src.count(sc) == 1 and src.index(ban) < src.index(sc)
    assert src.index(sc) < src.index('api_df=_np_live_quotes')   # still above the rest of the tab


def test_home_section_directly_above_matchup_targets(monkeypatch, tmp_path, fake_espn):
    at = run_app(monkeypatch, tmp_path, routes=fake_espn[0])
    home = ' '.join(v for _, v in _flat(_tab(at, '🏠 Home')))
    i, j = home.index('v59-os'), home.index('Matchup targets')
    between = home[i:j]
    assert between.count('<section') == 1          # nothing else sits between it and Matchup targets
    assert between.count('class="os-r"') == 5 and '⚡ Odds tab' in between and '<details' not in between
    for above in ('Leaders', 'parlay'):
        assert above.lower() in home[:i].lower()  # the rest of Home stays above, unmoved
    odds = _odds_scorers_block(at)
    first = re.search(r'<li class="os-r">.*?</li>', between).group(0)
    assert first in odds                            # same renderer + same data as the Odds tab


def test_home_and_odds_without_source_show_empty_state_not_demo(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path)   # testkit: no key, ESPN props unreachable
    home = ' '.join(v for _, v in _flat(_tab(at, '🏠 Home')))
    odds = _odds_scorers_block(at)
    for h in (home, odds):
        assert 'No sportsbook anytime-goal prices' in h and 'os-r' not in h.split('v59-os')[1].split('</section>')[0]
    assert home.index('v59-os') < home.index('Matchup targets')


def test_flag_off_hides_home_section(monkeypatch, tmp_path, fake_espn):
    monkeypatch.setenv('FEATURE_ODDS_SCORERS', '0')
    at = run_app(monkeypatch, tmp_path, routes=fake_espn[0])
    assert 'v59-os' not in ' '.join(v for _, v in _flat(_tab(at, '🏠 Home')))
    assert 'Matchup targets' in ' '.join(v for _, v in _flat(_tab(at, '🏠 Home')))
