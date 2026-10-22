"""V5.3 regression tests: malformed inputs, NaN/inf, empty data and UI escaping."""
from datetime import datetime, timezone
import math
import tempfile
import json
from pathlib import Path

import pandas as pd
import pytest

from odds_api_v45 import fetch_odds, OddsFeedError, _valid_price
from playbook_odds import compare_odds, CSV_TEMPLATE, REQUIRED
from odds_intelligence_v46 import price_label
from numerology_v48 import analyze_game, letters, gematria
from player_targets_v49 import target_rows
from home_leaders_v52 import choose_leaders, all_targets
from snapshot_store import load_snapshot, save_snapshot
import ui_theme_v53 as ui


class Resp:
    def __init__(self, body=None, status=200, bad_json=False):
        self.body, self.status_code, self.bad_json = body, status, bad_json
    def json(self):
        if self.bad_json:
            raise ValueError('Expecting value')
        return self.body


class Session:
    def __init__(self, events, odds):
        self.events, self.odds = events, odds
    def get(self, url, params, timeout):
        return self.events if url.endswith('/events') else self.odds


def _book(title, price, desc='Player X'):
    return {'title': title, 'markets': [{'key': 'player_goal_scorer_anytime', 'last_update': '2026-10-22T18:00:00Z',
            'outcomes': [{'description': desc, 'name': 'Yes', 'price': price}]}]}


# ---- odds_api_v45
def test_malformed_events_json_is_feed_error():
    with pytest.raises(OddsFeedError, match='malformed JSON'):
        fetch_odds('k', session=Session(Resp(bad_json=True), Resp({})))

def test_malformed_event_odds_json_becomes_warning():
    frame, warnings = fetch_odds('k', session=Session(Resp([{'id': 'e1'}]), Resp(bad_json=True)))
    assert frame.empty and len(warnings) == 1 and 'malformed' in warnings[0]

def test_non_dict_events_and_payloads_skipped():
    frame, warnings = fetch_odds('k', session=Session(Resp(['junk', None, {'id': 'e1'}]), Resp(['not a dict'])))
    assert frame.empty and warnings == ['Event e1: invalid odds payload']

def test_null_lists_and_junk_entries_do_not_crash():
    body = {'bookmakers': [None, {'title': 'A', 'markets': None}, {'title': 'B', 'markets': ['x', {'outcomes': None}]}, _book('C', 250)]}
    frame, _ = fetch_odds('k', session=Session(Resp([{'id': 'e1'}]), Resp(body)))
    assert list(frame['sportsbook']) == ['C']

@pytest.mark.parametrize('price,ok', [(True, False), (float('nan'), False), (float('inf'), False), ('250', False),
                                      (50, False), (-99, False), (100, True), (-110, True), (250.0, True)])
def test_valid_price(price, ok):
    assert _valid_price(price) is ok

def test_bool_and_nan_prices_not_ingested():
    body = {'bookmakers': [_book('A', True), _book('B', float('nan')), _book('C', 300), _book('D', 320)]}
    frame, _ = fetch_odds('k', session=Session(Resp([{'id': 'e1'}]), Resp(body)))
    assert sorted(frame['sportsbook']) == ['C', 'D']


# ---- playbook_odds
def _quote(book, odds, player='Player X'):
    return {'player': player, 'team': 'BOS', 'market': 'goal', 'selection': 'Yes', 'sportsbook': book,
            'american_odds': odds, 'updated_at': '2026-10-22T18:00:00Z', 'event_id': 'e1', 'line': ''}

def test_compare_odds_drops_infinite_prices():
    clean, gaps = compare_odds(pd.DataFrame([_quote('A', float('inf')), _quote('B', 200), _quote('C', 240)]))
    assert set(clean['sportsbook']) == {'B', 'C'}
    assert math.isfinite(gaps.iloc[0]['decimal_price_improvement_pct'])

def test_compare_odds_empty_after_cleaning():
    clean, gaps = compare_odds(pd.DataFrame([_quote('A', 'n/a'), _quote('B', 0)]))
    assert clean.empty and gaps.empty

def test_csv_template_is_real_header():
    assert CSV_TEMPLATE.endswith('\n') and '\\n' not in CSV_TEMPLATE
    header = CSV_TEMPLATE.strip().split(',')
    assert REQUIRED.issubset(header)


# ---- odds_intelligence_v46
@pytest.mark.parametrize('value,label', [(float('inf'), '—'), (float('nan'), '—'), (True, '—'), (None, '—'),
                                         (250.0, '+250'), ('-110', '-110')])
def test_price_label_edge_cases(value, label):
    assert price_label(value) == label


# ---- numerology_v48
def test_nan_venue_and_names_are_unavailable_not_nan_text():
    result = analyze_game({'Away': 'bos', 'Home': 'MIN', 'Venue': float('nan'), 'Start (UTC)': None}, '2026-10-22', {'BOS': 'Boston Bruins'})
    assert result['arena'] == '' and result['arena_values'] is None
    assert result['away'] == 'BOS' and result['away_name'] == 'Boston Bruins'
    assert letters(float('nan')) == '' and gematria(None)['ordinal'] == 0


# ---- player_targets_v49
def test_nan_form_becomes_zero():
    ranked = pd.DataFrame([{'Player': 'A Player', 'Player ID': 1.0, 'Team': 'BOS', 'V3.2 Adjusted Index': float('nan')}])
    rows = target_rows(ranked, 'BOS', 'Boston Bruins', 'TD Garden', '2026-10-22')
    assert rows[0]['form'] == 0.0 and rows[0]['player_id'] == '1'


# ---- home_leaders_v52
def _slate():
    games = [{'Away': 'MTL', 'Home': 'BOS', 'Venue': 'TD Garden', 'Start (UTC)': '2026-10-22T23:00:00Z'}]
    ranked = pd.DataFrame([{'Player': n, 'Player ID': i, 'Team': t, 'V3.2 Adjusted Index': f} for n, i, t, f in
                           [('Juraj Slafkovský', 1, 'MTL', 60), ('Nick Suzuki', 2, 'MTL', 70), ('David Pastrnak', 3, 'BOS', 90)]])
    return ranked, all_targets(games, ranked, '2026-10-22')

def test_odds_leader_matches_accent_insensitive_names():
    ranked, targets = _slate()
    taken = {p['player_id'] for p in choose_leaders(ranked, targets).values() if p}
    free = ranked[~ranked['Player ID'].astype(str).isin(taken)].iloc[0]
    # Provider spelling differs only by case, accents and punctuation (e.g. "Slafkovsky" vs "Slafkovský").
    provider = free['Player'].upper().replace('Ý', 'Y') + '.'
    odds = pd.DataFrame([{'player': provider, 'best_odds': 260, 'best_sportsbook': 'A', 'decimal_price_improvement_pct': 25.0}])
    leaders = choose_leaders(ranked, targets, odds)
    assert leaders['odds'] is not None and leaders['odds']['player_id'] == str(free['Player ID'])

def test_odds_leader_skips_nan_gap_and_missing_column():
    ranked, targets = _slate()
    nan_gap = pd.DataFrame([{'player': 'Nick Suzuki', 'best_odds': 200, 'best_sportsbook': 'A', 'decimal_price_improvement_pct': float('nan')}])
    assert choose_leaders(ranked, targets, nan_gap)['odds'] is None
    no_col = pd.DataFrame([{'player': 'Nick Suzuki', 'best_odds': 200}])
    assert choose_leaders(ranked, targets, no_col)['odds'] is None

def test_empty_slate_has_no_leaders():
    leaders = choose_leaders(None, all_targets([], None, '2026-10-22'))
    assert leaders == {} or all(v is None for v in leaders.values())


# ---- snapshot_store
def test_snapshot_list_json_and_bad_timestamp_rejected():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / '2026-10-22.json'
        p.write_text('[1, 2]')
        assert load_snapshot('2026-10-22', root=Path(d)) is None
        save_snapshot('2026-10-22', [], [], root=Path(d))
        data = json.loads(p.read_text()); data['updated_at'] = 12345; p.write_text(json.dumps(data))
        assert load_snapshot('2026-10-22', root=Path(d)) is None


# ---- ui_theme_v53
def test_esc_blocks_markup_and_hides_nan():
    assert ui.esc('<script>x</script>') == '&lt;script&gt;x&lt;/script&gt;'
    assert ui.esc(float('nan'), '—') == '—' and ui.esc(None) == '' and ui.esc('nan', 'x') == 'x'

def test_image_urls_only_for_valid_codes():
    assert ui.logo_url('bos') == 'https://assets.nhle.com/logos/nhl/svg/BOS_light.svg'
    assert ui.logo_url('"><img onerror=1>') == '' and ui.logo_url(None) == ''
    assert ui.mug_url('BOS', 8478402.0, '20262027').endswith('/20262027/BOS/8478402.png')
    assert ui.mug_url('BOS', float('nan')) == '' and ui.mug_url('BOS', 'abc') == '' and ui.mug_url('BOS', True) == ''
    assert '/20262027/' in ui.mug_url('BOS', 1, season='bad')

def test_cards_escape_player_names_and_handle_missing():
    html = ui.leader_card('stat', 'Label', '<b>Evil</b>', 'BOS', 'MTL', 1, '9.0', 'cap')
    assert '<b>Evil</b>' not in html and '&lt;b&gt;Evil' in html
    assert 'No eligible player' in ui.leader_card('gem', 'Label')
    card = ui.odds_card('X', float('nan'), '', '+250', 'A', '+200', 'B', float('nan'), 2, 'Model rank unavailable', 'Ambiguous: two players')
    assert 'Team unmatched' in card and 'Name collision' in card and '+—%' in card
    assert ui.num_value_row('', None).count('Unavailable') == 2

@pytest.mark.parametrize('pct,width', [(50, '50%'), (-5, '0%'), (float('nan'), '0%'), (1e9, '100%'), ('x', '0%')])
def test_gap_meter_clamps(pct, width):
    assert f'width:{width}' in ui.gap_meter(pct)

def test_eastern_today_uses_new_york_calendar():
    # 02:30 UTC on Oct 23 is still the evening of Oct 22 in New York.
    assert ui.eastern_today(datetime(2026, 10, 23, 2, 30, tzinfo=timezone.utc)).isoformat() == '2026-10-22'
    assert ui.eastern_today(datetime(2026, 10, 23, 2, 30)).isoformat() == '2026-10-22'
