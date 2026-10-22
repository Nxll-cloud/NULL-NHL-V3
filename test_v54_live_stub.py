import random
from datetime import datetime, timezone
from pathlib import Path

import pytest

import live_scoring_future as live

HERE = Path(__file__).resolve().parent


def test_flag_off_and_not_imported_by_app():
    assert live.LIVE_SCORING_ENABLED is False
    src = (HERE / 'app.py').read_text(encoding='utf-8')
    assert 'live_scoring_future' not in src


def test_provider_stubs_raise_not_implemented():
    for prov in (live.NHLOfficialProvider(), live.ESPNProvider(), live.SportsGameOddsProvider('')):
        with pytest.raises(NotImplementedError):
            prov.fetch_slate_states('2026-10-22')
        with pytest.raises(NotImplementedError):
            prov.fetch_goal_events('2026020154')
    with pytest.raises(NotImplementedError):
        live.LivePoller().poll_once('2026-10-22')


def test_sgo_key_only_from_secrets():
    assert live.SportsGameOddsProvider.from_secrets({'SGO_API_KEY': 'k'}).api_key == 'k'
    assert live.SportsGameOddsProvider.from_secrets({}).api_key == ''
    src = (HERE / 'live_scoring_future.py').read_text(encoding='utf-8')
    assert 'os.environ' not in src


def test_dedupe_by_event_id_and_fallback_key():
    a = live.GoalEvent('1', 1, '01:00', 'BOS', 'A', event_id='9')
    b = live.GoalEvent('1', 2, '05:00', 'BOS', 'B', event_id='9')
    c = live.GoalEvent('1', 1, '02:00', 'BOS', 'Anne Smith')
    d = live.GoalEvent('1', 1, '02:00', 'BOS', 'anne smith')
    seen = set()
    assert len(live.dedupe_events([a, b, c, d], seen)) == 2
    assert live.dedupe_events([a, c], seen) == []


def test_backoff_and_should_poll():
    assert live.backoff_delay(3) == live.BASE_POLL_SECONDS
    d = live.backoff_delay(10, status=429, rng=random.Random(1))
    assert live.BASE_POLL_SECONDS <= d <= live.BASE_POLL_SECONDS + live.MAX_BACKOFF_SECONDS
    assert live.should_poll([]) is False


def test_render_ticker_is_noop_when_disabled():
    assert live.render_live_ticker('2026-10-22') is None
