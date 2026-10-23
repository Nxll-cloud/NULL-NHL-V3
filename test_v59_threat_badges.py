"""V5.9 top-threat mini badges (threat_badges_v59): one badge per game, the model's #1 per game, link target = the
Live Next Goal row, missing-number fallback. Offline: real PBP fixture + the real slate_results/model path."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import feature_flags_v58 as flags
import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import threat_badges_v59 as th
import v55_ui as v5
import v56_ui as v56

HERE = Path(__file__).resolve().parent
NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


def _row(pid, name, team, pos='C', gp=10, g_pg=0.4, s_pg=3.0):
    return {'Player ID': pid, 'Player': name, 'Team': team, 'Position': pos, 'Prior GP': gp, 'Goals/G Prior': g_pg, 'Shots/G L10': s_pg}


PRIORS = ng.priors_from_rankings([
    _row(1, 'Nathan MacKinnon', 'COL', g_pg=0.6, s_pg=4.5), _row(2, 'Cale Makar', 'COL', 'D', g_pg=0.3, s_pg=3.0),
    _row(3, 'Nikita Kucherov', 'TBL', 'R', g_pg=0.45, s_pg=3.2), _row(9, 'Andrei Vasilevskiy', 'TBL', 'G', g_pg=0, s_pg=0),
    _row(4, 'Cole Caufield', 'MTL', 'R', g_pg=0.55, s_pg=3.8), _row(5, 'Connor Bedard', 'CHI', g_pg=0.4, s_pg=4.0)])
SLATE = [{'key': 'MTL@CHI', 'game_id': '2026020166', 'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T00:30:00Z', 'status': 'FUT'},
         {'key': 'TBL@COL', 'game_id': '2026020167', 'away': 'TBL', 'home': 'COL', 'start': '2026-10-24T02:00:00Z', 'status': 'FUT'}]


def _results(slate=SLATE, pbp=None):
    return lstate.slate_results(slate, PRIORS, {}, pbp or {}, {})


def test_one_badge_per_game_in_slate_order():
    res = _results()
    res = res + [res[1]]   # a repeated game never yields a second badge
    t = th.top_threats(res, {'1': 29, '4': 13})
    assert [x['game_id'] for x in t] == ['2026020166', '2026020167']
    html = th.section_html(t)
    assert html.count('class="thb"') == 2 and html.index('MTL @ CHI') < html.index('TBL @ COL')
    assert th.section_html([]) == '' and th.top_threats([]) == []
    # a game with no ranked skater shows no badge (nothing invented)
    assert th.top_threats([{'slate': SLATE[0], 'result': {'players': [], 'phase': 'pregame'}}]) == []


def test_badge_is_the_models_top_player_per_game():
    t = {x['game_id']: x for x in th.top_threats(_results())}
    assert t['2026020167']['name'] == 'Nathan MacKinnon' and t['2026020167']['team'] == 'COL' and t['2026020167']['opp'] == 'TBL'
    assert t['2026020166']['name'] == 'Cole Caufield' and t['2026020166']['opp'] == 'CHI'
    for r in _results():   # identical to the ranking's own #1 (max next-goal %), goalies never picked
        best = max(r['result']['players'], key=lambda p: p['p_next'])
        assert t[r['slate']['game_id']]['pid'] == r['result']['players'][0]['pid'] == best['pid']
        assert all(str(p['pos']).upper() != 'G' for p in r['result']['players'])


def test_real_pbp_top_player_and_feed_number():
    raw = json.loads((HERE / 'test_fixtures_v56' / 'pbp_2026020162.json').read_text())
    game = ng.parse_pbp(raw)
    slate = [{'key': f'{game["away"]}@{game["home"]}', 'game_id': str(game['game_id']), 'away': game['away'], 'home': game['home'], 'status': 'OFF'}]
    res = _results(slate, {str(game['game_id']): game})
    top = th.top_threats(res)[0]
    first = res[0]['result']['players'][0]
    assert top['pid'] == first['pid'] and top['number'] == game['roster'][first['pid']]['number'] is not None
    assert f'<b class="thn">{top["number"]}</b>' in th.badge(top)


def test_link_target_matches_live_next_goal_row():
    res = _results()
    t = th.top_threats(res)
    html = th.section_html(t)
    panel = v56.nextgoal_panel(res[1]['result'], 20262027, res[1]['label'])
    hook = th.anchor('2026020167', t[1]['pid'])
    assert f'data-ng="{hook}"' in html and f'href="#{hook}"' in html and f'data-ng="{hook}"' in panel
    assert 'data-tab="Live Next Goal"' in html
    app = (HERE / 'app.py').read_text()
    assert "'⏱ Live Next Goal'" in app   # the tab the JS clicks exists
    js = v5.js()   # sanitizer-safe and carries the tab-switch + scroll hook
    assert "a[data-ng]" in js and '[role=tab]' in js and 'scrollIntoView' in js


def test_missing_number_shows_team_abbrev_only():
    t = th.top_threats(_results(), {'4': 'N/A'})   # no PBP number, roster says N/A, COL leader has no entry
    for x in t:
        assert x['number'] is None
        b = th.badge(x)
        assert f'<b class="tha">{x["team"]}</b>' in b and 'class="thn"' not in b and '#None' not in b
    assert th.jersey_number(13) == 13 and th.jersey_number('8') == 8 and th.jersey_number(120) is None and th.jersey_number(7.5) is None
    filled = {x['team']: x for x in th.top_threats(_results(), {'1': 29})}
    assert filled['COL']['number'] == 29 and '<b class="thn">29</b><small>COL</small>' in th.badge(filled['COL'])


def test_home_places_row_under_hero_and_flag():
    data = {'day': '2026-10-23', 'season': 20262027, 'games': [], 'featured': None, 'threat_html': '<nav class="sec thr">X</nav>', 'parlay_html': '<i id="pl"></i>'}
    html = v5.render_home(data, NOW)
    assert html.index('class="hero') < html.index('class="sec thr"') < html.index('id="pl"')
    assert flags.show_threat_badges(secrets={}, environ={}) is True
    assert flags.show_threat_badges(secrets={'FEATURE_THREAT_BADGES': 'false'}, environ={}) is False
    css = (HERE / 'assets' / 'v58.css').read_text()
    assert re.search(r'a\.thb\{[^}]*min-height:44px', css) and 'overflow-x:auto' in css.split('.v55 .throw{')[1].split('}')[0]
