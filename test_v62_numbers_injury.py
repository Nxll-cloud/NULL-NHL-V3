"""Numbers tab: silently omit currently injured players (ESPN injuries feed). No injury UI."""
import logging
from pathlib import Path

import pandas as pd
import pytest

import numbers_injury_v62 as ninj
import storylines_v58 as slx
from player_targets_v49 import slate_targets


def _inj(name, team, status, team_in_athlete=True):
    ath = {'displayName': name}
    if team_in_athlete:
        ath['team'] = {'abbreviation': team}
    return {'athlete': ath, 'status': status}


def _payload(*rows):
    # ESPN groups by team; grouping does not affect parsing (team comes from athlete).
    return {'injuries': [{'displayName': 'X', 'injuries': list(rows)}]}


DTD = _inj('Connor McDavid', 'EDM', 'Day-To-Day')
OUT = _inj('Nathan MacKinnon', 'COL', 'Out')
IR = _inj('Leo Carlsson', 'ANA', 'Injured Reserve')
LTIR = _inj('Jack Eichel', 'VGK', 'Long-Term Injured Reserve')
SUSP = _inj('Wyatt Kaiser', 'CHI', 'Suspension')
# ESPN uses LA / TB / NJ; ranked frames use NHL abbreviations.
ESPN_LA = _inj('Trevor Moore', 'LA', 'Day-To-Day')


def test_injured_players_includes_dtd_out_ir_ltir_not_suspension():
    got = slx.injured_players(_payload(DTD, OUT, IR, LTIR, SUSP, ESPN_LA))
    assert got == {
        ('connor mcdavid', 'EDM'),
        ('nathan mackinnon', 'COL'),
        ('leo carlsson', 'ANA'),
        ('jack eichel', 'VGK'),
        ('trevor moore', 'LAK'),  # espn_team maps LA -> LAK
    }
    # out_players still treats Day-To-Day as available; Numbers does not.
    out = slx.out_players(_payload(DTD, OUT, IR, LTIR, SUSP, ESPN_LA))
    assert ('connor mcdavid', 'EDM') not in out
    assert ('trevor moore', 'LAK') not in out
    assert ('nathan mackinnon', 'COL') in out and ('wyatt kaiser', 'CHI') in out


def test_injured_players_is_resilient_to_bad_payloads():
    assert slx.injured_players(None) == set()
    assert slx.injured_players({}) == set()
    assert slx.injured_players({'injuries': None}) == set()
    assert slx.injured_players({'injuries': [None, {'injuries': [None, {}]}]}) == set()
    assert slx.injured_players([1, 2]) == set()


def _frame(*rows):
    return pd.DataFrame(rows, columns=['Player', 'Team', 'Player ID', 'V3.2 Adjusted Index'])


RANKED = _frame(
    ('Connor McDavid', 'EDM', 8478402, 10),
    ('Leon Draisaitl', 'EDM', 8477934, 9),
    ('Trevor Moore', 'LAK', 8479369, 5),
    ('Wyatt Kaiser', 'CHI', 8482082, 4),
    ('Cale Makar', 'COL', 8480069, 8),
)


def test_drop_from_ranked_removes_injured_keeps_suspension_and_healthy():
    injured = slx.injured_players(_payload(DTD, ESPN_LA, SUSP, OUT))
    out = ninj.drop_from_ranked(RANKED, injured)
    assert list(out['Player']) == ['Leon Draisaitl', 'Wyatt Kaiser', 'Cale Makar']
    assert list(RANKED['Player']) == ['Connor McDavid', 'Leon Draisaitl', 'Trevor Moore', 'Wyatt Kaiser', 'Cale Makar']
    assert ninj.drop_from_ranked(RANKED, set()) is RANKED
    assert ninj.drop_from_ranked(RANKED, None) is RANKED
    assert ninj.drop_from_ranked(None, injured) is None


def test_apply_drops_injured_using_injected_fetch():
    out = ninj.apply(RANKED, fetch=lambda: _payload(DTD, ESPN_LA, SUSP))
    assert list(out['Player']) == ['Leon Draisaitl', 'Wyatt Kaiser', 'Cale Makar']


def test_apply_leaves_frame_and_logs_when_source_unavailable(caplog):
    def boom():
        raise ConnectionError('espn down')
    with caplog.at_level(logging.ERROR, logger='nulls.numbers'):
        out = ninj.apply(RANKED, fetch=boom)
    assert out is RANKED
    assert 'injury filter unavailable' in caplog.text.lower()
    assert 'espn down' in caplog.text


def test_apply_does_not_rewrite_gematria_logs(tmp_path):
    log = tmp_path / '2026-11-22.json'
    log.write_text('{"untouched": true}', encoding='utf-8')
    before = log.read_bytes()
    ninj.apply(RANKED, fetch=lambda: _payload(DTD))
    ninj.apply(RANKED, fetch=lambda: (_ for _ in ()).throw(RuntimeError('nope')))
    assert log.read_bytes() == before


def test_slate_targets_omit_injured_after_apply():
    ranked = ninj.apply(RANKED, fetch=lambda: _payload(DTD, ESPN_LA))
    games = [{'away': 'EDM', 'home': 'LAK', 'away_name': 'Edmonton Oilers', 'home_name': 'Los Angeles Kings',
              'arena': 'Crypto.com Arena', 'start': '2026-11-23T00:00:00Z'}]
    item = slate_targets(games, ranked, '2026-11-23')[0]
    away = {t['player'] for t in item['away_targets']}
    home = {t['player'] for t in item['home_targets']}
    assert 'Connor McDavid' not in away and 'Leon Draisaitl' in away
    assert 'Trevor Moore' not in home


def test_numbers_tab_applies_filter_once_upstream_with_no_injury_ui():
    src = Path('tabs/numbers.py').read_text()
    assert src.index('import numbers_injury_v62') < src.index('_gm_targets=num_slate_targets')
    assert src.count('_num_inj.apply(_nb_ranked)') == 1
    assert '_nb_ranked=_num_inj.apply(_nb_ranked)' in src
    # local frame only; do not mutate the shared rankings used by other tabs
    assert "st.session_state['signals_ranked']=_num_inj" not in src
    hook = src[src.index('import numbers_injury_v62'):src.index('_gm_targets=num_slate_targets')]
    assert 'st.' not in hook and 'warning' not in hook.lower() and 'caption' not in hook.lower()
    assert 'injury report' not in src.lower()


def test_other_tabs_do_not_gain_the_numbers_injury_filter():
    for path in Path('tabs').glob('*.py'):
        if path.name == 'numbers.py':
            continue
        text = path.read_text()
        assert 'numbers_injury_v62' not in text, path
