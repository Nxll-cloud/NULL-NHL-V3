"""Audit P1.2: a MoneyPuck season file is used for a slate only if modified BEFORE the slate's first puck drop
(00:00 ET on the slate date when puck times are unknown); undated files are not trusted for past slates, and the
point-in-time per-shot rebuild replaces a too-new file on the workflow paths."""
import io
import zipfile
from datetime import datetime, timezone

import situational_v58 as sit
import xg_v59 as xgm

SEASON = '20262027'
DAY = '2026-10-23'
PUCK = '2026-10-23T23:00:00+00:00'          # first puck drop 7 pm ET
NOW_SAME_DAY = datetime(2026, 10, 23, 15, tzinfo=timezone.utc)
NOW_LATER = datetime(2026, 11, 2, 15, tzinfo=timezone.utc)


def data(as_of):
    return {**xgm.empty('', '2026', as_of), 'players': {1: {'5on5': (3.0, 20, 2), 'all': (3.0, 20, 2)}}}


def test_one_minute_before_first_puck_drop_is_accepted_one_minute_after_rejected():
    assert xgm.for_day(data('2026-10-23T22:59:00+00:00'), DAY, SEASON, PUCK)['players']
    out = xgm.for_day(data('2026-10-23T23:01:00+00:00'), DAY, SEASON, PUCK)
    assert out['players'] == {} and 'first puck drop' in out['error']
    assert xgm.for_day(data(PUCK), DAY, SEASON, PUCK)['players'] == {}   # exactly at puck drop -> rejected


def test_next_morning_refresh_that_old_36h_window_allowed_is_now_rejected():
    # 32 h after 00:00 UTC on the slate date = 08:00 UTC next day: the slate's games are final and in the file
    nxt = data('2026-10-24T08:00:00+00:00')
    assert xgm.for_day(nxt, DAY, SEASON)['players'] == {} and xgm.for_day(nxt, DAY, SEASON, PUCK)['players'] == {}
    assert xgm.needs_point_in_time(xgm.for_day(nxt, DAY, SEASON, PUCK))


def test_unknown_puck_times_use_start_of_slate_date_in_eastern_time():
    cut = xgm.slate_cutoff(DAY)
    assert cut == datetime(2026, 10, 23, 4, tzinfo=timezone.utc)        # 00:00 EDT
    assert xgm.slate_cutoff('2026-12-01') == datetime(2026, 12, 1, 5, tzinfo=timezone.utc)   # 00:00 EST
    assert xgm.for_day(data('2026-10-23T03:59:00+00:00'), DAY, SEASON)['players']
    assert xgm.for_day(data('2026-10-23T04:00:00+00:00'), DAY, SEASON)['players'] == {}
    games = [{'Start (UTC)': '2026-10-24T00:00:00Z'}, {'Start (UTC)': PUCK}, {'start': ''}, 'junk']
    assert xgm.slate_cutoff(DAY, games) == datetime(2026, 10, 23, 23, tzinfo=timezone.utc)


def test_undated_file_trusted_for_today_but_not_for_a_past_slate():
    und = data(None)
    assert xgm.for_day(und, DAY, SEASON, PUCK, now=NOW_SAME_DAY)['players']
    out = xgm.for_day(und, DAY, SEASON, PUCK, now=NOW_LATER)
    assert out['players'] == {} and 'undated' in out['error'] and xgm.needs_point_in_time(out)
    assert xgm.for_day(data('garbage'), DAY, SEASON, PUCK, now=NOW_LATER)['players'] == {}


def test_stale_and_season_checks_still_apply_and_are_not_point_in_time():
    st = xgm.for_day(data('2026-10-01T00:00:00+00:00'), DAY, SEASON, PUCK)
    assert st['error'] == 'stale' and not xgm.needs_point_in_time(st)
    assert xgm.for_day(data('2026-10-22T10:00:00+00:00'), DAY, '20252026')['error'] == 'season mismatch'


def shots_zip():
    hdr = list(xgm.SHOT_COLUMNS) + ['extraColumn']
    rows = [['20001', '1', '0.3', '1', '1', '5', '5', '1', '0', '0', '2026', 'x'],
            ['20009', '1', '0.9', '1', '1', '5', '5', '1', '0', '0', '2026', 'x']]   # 20009 is ON the slate -> excluded
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('shots_2026.csv', '\n'.join(','.join(r) for r in [hdr] + rows) + '\n')
    return buf.getvalue()


def getter(url, params=None):
    class R:
        content = shots_zip()
        def json(self):
            return {'data': [{'id': 2026020001, 'gameDate': '2026-10-20'}, {'id': 2026020009, 'gameDate': DAY}]}
    return R()


def test_point_in_time_fallback_replaces_a_too_new_file_and_drops_slate_games():
    xgm._PIT_CACHE.clear()
    ctx = sit.with_xg(sit.context(), data('2026-10-24T08:00:00+00:00'), DAY, SEASON, PUCK, pit_getter=getter)
    assert ctx['xg']['players'][1]['all'][0] == 0.3 and 'point-in-time' in ctx['sources']['xg']
    assert set(next(iter(xgm._PIT_CACHE.values()))[0][0]) == set(xgm.SHOT_COLUMNS)   # trimmed rows
    xgm._PIT_CACHE.clear()
    off = sit.with_xg(sit.context(), data('2026-10-24T08:00:00+00:00'), DAY, SEASON, PUCK)   # no fallback -> neutral
    assert off['xg'] is None and 'first puck drop' in off['sources']['xg']


def test_point_in_time_never_raises():
    def boom(url, params=None):
        raise RuntimeError('down')
    assert xgm.point_in_time(DAY, SEASON, boom, cache={})['players'] == {}
    assert xgm.point_in_time(DAY, 'bogus', boom, cache={})['error'] == 'bad season'


def test_accuracy_situ_for_passes_the_slate_first_puck_drop(monkeypatch):
    import accuracy_v58 as acc
    seen = {}

    def fake(day, season, parts, getter=None, xg_getter=None, cutoff=None, pit_fallback=False):
        seen.update(cutoff=cutoff, pit=pit_fallback)
        return sit.context(parts=parts)
    monkeypatch.setattr(sit, 'load_context', fake)
    acc.situ_for(DAY, [{'Start (UTC)': PUCK}], getter=lambda *a, **k: None, environ={})
    assert seen == {'cutoff': datetime(2026, 10, 23, 23, tzinfo=timezone.utc), 'pit': True}
    acc.situ_for(DAY, (), getter=lambda *a, **k: None, environ={}, pit=False)
    assert seen == {'cutoff': datetime(2026, 10, 23, 4, tzinfo=timezone.utc), 'pit': False}
