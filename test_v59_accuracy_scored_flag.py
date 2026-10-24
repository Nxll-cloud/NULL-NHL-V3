"""V5.9: Home 'Model accuracy' card scored marker (user report: Bedard / Lehkonen / Kadri / D'Astous not 'lit').

The card shows YESTERDAY's real scorers (accuracy_v58.view -> eastern_yesterday(now)); every row is a scorer and must carry
its own '✓ nG' marker from the entry's results, independent of tonight's scored-tonight record
(scorers_tonight_v58, keyed on the selected slate np_day, which rolls over at ET midnight)."""
import html as _html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import accuracy_v58 as acc
import scorers_tonight_v58 as sctn

HERE = Path(__file__).resolve().parent
DAY = '2026-10-23'
ENTRY = json.loads((HERE / 'snapshots' / 'accuracy' / f'{DAY}.json').read_text())
BEDARD, LEHKONEN, KADRI, DASTOUS = 8484144, 8477476, 8475172, 8480426
ET = timezone(timedelta(hours=-4))   # EDT on Oct 23/24 2026


def _no_net(*a, **k):
    raise AssertionError('card must render from the saved entry, no network')


def _card(now):
    log = HERE / 'snapshots' / 'accuracy'
    return acc.card_html(acc.view(now, _no_net, log, HERE / 'snapshots'))


def _row_markers(html):
    """{visible short name: goal count} from every card row (top 8 + 'Show all')."""
    out = {}
    for tr in re.findall(r'<tr class="[^"]*">(.*?)</tr>', html.split('<section class="npacc', 1)[1]):
        sn = re.search(r'<span class="sn"[^>]*>(.*?)</span>', tr)
        g = re.search(r'<td class="g"[^>]*>✓<span class="gx"> </span>(\d+)G</td>', tr)
        if sn:
            out[_html.unescape(sn.group(1))] = int(g.group(1)) if g else None
    return out


def _tonight(day, scorers):
    """scorers_tonight record for slate `day` built through the real parser path (from_pbp)."""
    roster = {pid: {'name': n, 'team': t} for pid, n, t, _ in scorers}
    ev = [{'kind': 'goal', 'shooter': pid, 'team': t, 'period': 1, 'secs': 60 * i + k, 'eid': f'{pid}-{k}', 'goalie': 1}
          for i, (pid, n, t, g) in enumerate(scorers) for k in range(g)]
    return sctn.from_pbp({'g': {'game_id': 'g', 'away': 'MTL', 'home': 'CHI', 'roster': roster, 'events': ev}}, day)


def test_entry_is_the_real_oct23_slate():
    sc = {pid: (n, g) for pid, n, t, g in ENTRY['results']['scorers']}
    assert len(sc) == 12 and ENTRY.get('summary')
    assert sc[BEDARD][0] == 'Connor Bedard' and sc[LEHKONEN][0] == 'Artturi Lehkonen' and sc[KADRI][0] == 'Nazem Kadri'
    assert sc[DASTOUS][0] == "Charle-Edouard D'Astous"


def test_every_scorer_gets_marker_with_correct_goal_count_including_show_all():
    html = _card(datetime(2026, 10, 24, 9, 0, tzinfo=ET))
    want = {}
    for pid, n, t, g in ENTRY['results']['scorers']:
        f, l = n.split(' ', 1)
        want[f[0] + '. ' + l] = g
    got = _row_markers(html)
    assert got == want                                   # all 12 rows, 8 visible + 4 under 'Show all'
    assert 'Show all 12 scorers' in html and html.count('>✓<span class="gx"> </span>2G<') == 2   # Guentzel, Evans


def test_bedard_lehkonen_kadri_dastous_marked_and_top10_labelled_separately():
    html = _card(datetime(2026, 10, 24, 9, 0, tzinfo=ET))
    got = _row_markers(html)
    for sn in ('C. Bedard', 'A. Lehkonen', 'N. Kadri', "C. D'Astous"):
        assert got[sn] == 1, sn
    tops = re.findall(r'<tr class="top">.*?<span class="sn"[^>]*>(.*?)</span>', html)
    assert tops == ['N. MacKinnon', 'M. Necas', 'J. Guentzel']          # cyan edge = model top 10 only
    assert 'Cyan edge = model pre-game top 10, not a scored marker.' in html and 'Every row scored on Oct 23 (G = goals).' in html


def test_apostrophe_name_survives_escaping():
    html = _card(datetime(2026, 10, 24, 9, 0, tzinfo=ET))
    assert '>Charle-Edouard&nbsp;D&#x27;Astous<' in html and '>C. D&#x27;Astous<' in html
    assert _row_markers(html)["C. D'Astous"] == 1


def test_midnight_rollover_card_markers_identical_and_independent_of_tonight():
    """np_day rolls 10-23 -> 10-24 at ET midnight (no 10-24 goals yet). The card (yesterday = Oct 23 after midnight) must
    look the same whatever the scored-tonight record says, after the page-wide MarkingStreamlit pass (mark_html)."""
    sc = ENTRY['results']['scorers']
    state = {}
    rec23 = sctn.for_slate(state, '2026-10-23', _tonight('2026-10-23', sc))      # 23:59 ET: tonight = Oct 23, all 12 scored
    assert len(rec23['players']) == 12
    rec24 = sctn.for_slate(state, '2026-10-24', rec23)                           # 00:01 ET: rollover -> empty record
    assert rec24['players'] == {} and sctn.active(state, '2026-10-24') is None
    card = _card(datetime(2026, 10, 24, 0, 1, tzinfo=ET))
    assert card == _card(datetime(2026, 10, 24, 23, 59, tzinfo=ET))           # same yesterday all ET day
    before, after = sctn.mark_html(card, rec23), sctn.mark_html(card, rec24)
    assert before == after == card                                               # no tonight badge ever lands on the card
    assert 'class="npsc' not in before
    assert _row_markers(before) == _row_markers(after) and len(_row_markers(after)) == 12
    assert all(v for v in _row_markers(after).values())


def test_tonight_badge_still_marks_other_home_views():
    """The fix is scoped to the accuracy card: plain name text elsewhere is still badged by the scored-tonight pass."""
    rec = _tonight('2026-10-24', [[BEDARD, 'Connor Bedard', 'CHI', 1]])
    assert 'class="npsc' in sctn.mark_html('<div><b>Connor Bedard</b></div>', rec)
