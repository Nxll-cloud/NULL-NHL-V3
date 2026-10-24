"""V5.9: the Model accuracy card's collapsed 'Model top 10 (pre-game)' list (card now on the Prediction Models tab)."""
import html as _html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import accuracy_v58 as acc
import scorers_tonight_v58 as sctn

HERE = Path(__file__).resolve().parent
DAY = '2026-10-23'
ENTRY = json.loads((HERE / 'snapshots' / 'accuracy' / f'{DAY}.json').read_text())


def _no_net(*a, **k):
    raise AssertionError('no network')


def _card():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    return acc.card_html(acc.view(now, _no_net, HERE / 'snapshots' / 'accuracy', HERE / 'snapshots'))


def test_top10_list_is_the_frozen_model_ranks_with_scored_checks():
    h = acc.top10_html(ENTRY)
    top = sorted(ENTRY['players'], key=lambda p: p[4])[:10]
    goals = {s[0] for s in ENTRY['results']['scorers']}
    assert h.startswith('<details class="npacc-top"><summary>Model top 10 (pre-game)') and '<details open' not in h
    rows = re.findall(r'<tr><td class="n">#(\d+)</td>.*?<span class="sn" title="([^"]*)">.*?</td><td>([A-Z]{3})</td>'
                      r'<td class="n">(\d+%)</td><td class="n">(.*?)</td></tr>', h)
    assert [int(r[0]) for r in rows] == [p[4] for p in top] == list(range(1, 11))
    assert [_html.unescape(r[1]) for r in rows] == [p[1] for p in top] and [r[2] for r in rows] == [p[2] for p in top]
    assert [r[3] for r in rows] == [acc._pct(p[3]) for p in top]
    checks = ['✓' in r[4] for r in rows]
    assert checks == [p[0] in goals for p in top]
    assert sum(checks) == ENTRY['summary']['top_hits'] and f'· {sum(checks)} scored</summary>' in h   # same count as the header


def test_card_keeps_its_header_table_trend_and_adds_the_list():
    h = _card()
    s = ENTRY['summary']
    assert f'model top-10 hit {s["top_hits"]}/10' in h and 'NP leaderboard top-10 hit' in h and 'Last ' in h
    assert 'title="NP statistical rank #' in h and 'Cyan edge = model pre-game top 10' in h
    assert h.count('<details class="npacc-top">') == 1 and h.index('Every row scored on') < h.index('<details class="npacc-top">') < h.index('<div class="npacc-tr">')
    rec = {'day': '2026-10-24', 'players': {str(p[0]): {'name': p[1], 'team': p[2]} for p in ENTRY['players'][:40]},
           'names': {sctn.norm(p[1]) for p in ENTRY['players'][:40]}}
    assert 'npsc' in sctn.mark_html('<b>' + ENTRY['players'][0][1] + '</b>', rec)   # the pass is live for plain names
    marked = sctn.mark_html(h, rec)
    assert 'npsc' not in marked.split('<details class="npacc-top">', 1)[1].split('</details>', 1)[0]   # never badged by tonight's pass


def test_list_empty_without_players_and_fits_narrow_css():
    assert acc.top10_html({'players': []}) == ''
    assert '.v55 .npacc-top .npacc-t td:nth-child(2){white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:0' in acc.CSS
