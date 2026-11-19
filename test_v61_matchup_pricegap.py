"""V6.1 Matchup Center Odds badges use the Home-filtered prices (Yes side, no line, this slate, unstarted, game-scoped names)."""
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import home_pricegap_v61 as hpg
import matchup_center_v54 as mc
from playbook_odds import compare_odds
from test_v61_home_pricegap import DAY, NOW, GAMES, RANKED, QUOTES, pair, targets


def game(away, home):
    return next(g for g in mc.slate_games(GAMES) if (g['away'], g['home']) == (away, home))


def odds_badges(out):
    return {p['player']: [b[0] for b in p['badges'] if b[1] == 'odds'] for lst in out.values() for p in lst}


def scoped(quotes=QUOTES, now=NOW, games=GAMES):
    return hpg.scope(quotes, games, DAY, now)[1]


def test_unscoped_badges_show_live_and_no_side_gaps_before_fix():
    _, disc = compare_odds(QUOTES)
    assert odds_badges(mc.matchup_targets(targets(), game('LAK', 'TOR'), discrepancies=disc))['Corey Perry'] == ['Odds +128.6%']
    assert odds_badges(mc.matchup_targets(targets(), game('MIN', 'CGY'), discrepancies=disc))['Blake Coleman'] == ['Odds +27.3%']   # the No side


def test_live_game_has_no_odds_badges():
    b = odds_badges(mc.matchup_targets(targets(), game('LAK', 'TOR'), discrepancies=scoped()))
    assert b['Corey Perry'] == [] and not any(b.values())


def test_pregame_badge_uses_yes_side_only():
    b = odds_badges(mc.matchup_targets(targets(), game('MIN', 'CGY'), discrepancies=scoped()))
    assert b['Blake Coleman'] == ['Odds +2.9%']


def test_pregame_badge_and_details():
    out = mc.matchup_targets(targets(), game('VAN', 'SEA'), discrepancies=scoped())
    gem = next(p for p in out['SEA'] if p['player'] == 'Gem Guy')
    assert gem['odds'] == {'gap': 13.33, 'price': 240, 'book': 'BookB'}


def test_before_puck_drop_live_game_badges_show():
    early = datetime(2026, 11, 19, 23, 0, tzinfo=timezone.utc)
    b = odds_badges(mc.matchup_targets(targets(), game('LAK', 'TOR'), discrepancies=scoped(now=early)))
    assert b['Corey Perry'] == ['Odds +128.6%']


def test_other_games_name_never_badges_this_game():
    # Same name in a different game (scoped to MIN@CGY) must not badge the VAN@SEA player.
    quotes = pd.DataFrame(pair('Gem Guy', 'Yes', 200, 300, 'MIN', 'CGY', '2026-11-20T01:00:00Z', 'e2'))
    assert not any(odds_badges(mc.matchup_targets(targets(), game('VAN', 'SEA'), discrepancies=scoped(quotes))).values())


def test_tomorrows_event_never_badges_tonight():
    b = odds_badges(mc.matchup_targets(targets(), game('DAL', 'PHI'), discrepancies=scoped()))
    assert b.get('David Perron') == []


def test_empty_or_missing_prices_give_absent_badges_and_honest_note():
    for disc in (pd.DataFrame(), None):
        assert not any(odds_badges(mc.matchup_targets(targets(), game('VAN', 'SEA'), discrepancies=disc)).values())
    g = game('VAN', 'SEA')
    assert hpg.matchup_odds_note(pd.DataFrame(), pd.DataFrame(), g) == 'No sportsbook prices loaded, so no Odds badges.'
    assert hpg.matchup_odds_note(None, None, g) == 'No sportsbook prices loaded, so no Odds badges.'
    assert hpg.matchup_odds_note(QUOTES, scoped(), g) == '1 comparable pre-game price for this game.'
    assert 'No pre-game price gap for this game' in hpg.matchup_odds_note(QUOTES, scoped(), game('LAK', 'TOR'))


def test_tab_wires_filtered_prices_not_shared_frame():
    src = Path('tabs/matchup.py').read_text()
    assert 'mc.matchup_targets(_home_targets, _game, _mc_ranked, _mc_disc,' in src
    assert 'hpg.scope(_np_shared_quotes,np_games,np_day' in src
    assert '_np_shared_discrepancies' not in src


def test_apptest_game_view_renders_with_filtered_prices(monkeypatch, tmp_path):
    """Offline AppTest: Matchup Center game view with uploaded quotes for a finished (past) slate game renders, shows no
    Odds badges for the started game and says why. The Odds tab's shared comparison still sees the quotes."""
    from v54_testkit import run_app, slate
    g0 = slate()['games'][0]
    key = str(g0['Game ID'])
    csv = pd.DataFrame([{'player': 'Anyone Here', 'team': g0['Home'], 'market': 'player_goal_scorer_anytime', 'selection': 'Yes', 'sportsbook': b,
                         'american_odds': p, 'updated_at': '2026-10-22T20:00:00Z', 'event_id': 'x', 'line': ''} for b, p in (('A', 150), ('B', 400))])
    at = run_app(monkeypatch, tmp_path, session={'v54_mc_game': key, 'v54_mc_select': key, 'v46_source': 'Uploaded CSV', 'playbook_odds_data': csv})
    assert not at.exception
    mcx = ' '.join(c.value for c in at.caption)
    assert 'Odds = pre-game price gap on the Yes side of anytime goal for this game' in mcx
    assert 'No pre-game price gap for this game right now, so no Odds badges.' in mcx
    assert 'Odds +' not in ' '.join(m.value for m in at.markdown)
