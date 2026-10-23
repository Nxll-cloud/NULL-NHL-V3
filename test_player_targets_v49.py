import pandas as pd
from player_targets_v49 import target_rows,slate_targets
from numerology_v48 import analyze_game

def test_team_scoping_and_deterministic():
    rows=pd.DataFrame([{'Player':'Alpha','Team':'BOS','Player ID':1,'V3.2 Adjusted Index':4}, {'Player':'Beta','Team':'NSH','Player ID':2,'V3.2 Adjusted Index':8}])
    result=target_rows(rows,'BOS','Boston Bruins','TD Garden','2026-10-22')
    assert len(result)==1 and result[0]['player']=='Alpha'
    assert result==target_rows(rows,'BOS','Boston Bruins','TD Garden','2026-10-22')

def test_duplicate_id_not_repeated():
    rows=pd.DataFrame([{'Player':'Same','Team':'BOS','Player ID':1},{'Player':'Same','Team':'BOS','Player ID':1}])
    assert len(target_rows(rows,'BOS','Boston Bruins','TD Garden','2026-10-22'))==1

def test_arena_missing_graceful():
    rows=pd.DataFrame([{'Player':'Alpha','Team':'BOS','Player ID':1}])
    assert target_rows(rows,'BOS','Boston Bruins','', '2026-10-22')[0]['arena_matches']==[]

def test_all_games_and_teams():
    g=analyze_game({'Away':'BOS','Home':'NSH','Venue':'TD Garden'},'2026-10-22',{'BOS':'Boston Bruins','NSH':'Nashville Predators'})
    rows=pd.DataFrame([{'Player':'Alpha','Team':'BOS','Player ID':1},{'Player':'Beta','Team':'NSH','Player ID':2}])
    out=slate_targets([g],rows,'2026-10-22')
    assert len(out)==1 and len(out[0]['away_targets'])==1 and len(out[0]['home_targets'])==1


def _row(name, team='MTL', pid=1, form=0):
    return {'Player': name, 'Team': team, 'Player ID': pid, 'V3.2 Adjusted Index': form}

def test_each_target_counts_once_and_raw_totals_carried():
    # 2026-10-23: universal day 7. 'Alex Newhook' = English 133 -> 7 (Reduction 7 too); 'Lane Hutson' = 129 -> 3 = United Center.
    rows = pd.DataFrame([_row('Alex Newhook', pid=1), _row('Lane Hutson', pid=2), _row('Frank Nazar', 'CHI', 3)])
    mtl = {t['player']: t for t in target_rows(rows, 'MTL', 'Montreal Canadiens', 'United Center', '2026-10-23')}
    assert mtl['Alex Newhook']['day'] == ['English'] and mtl['Alex Newhook']['matches'] == 1   # not English + Reduction
    assert mtl['Lane Hutson']['arena_matches'] == ['English'] and mtl['Lane Hutson']['day'] == []   # Reverse mirror not recounted
    assert (mtl['Alex Newhook']['eng_total'], mtl['Alex Newhook']['rev_total'], mtl['Alex Newhook']['letters']) == (133, 164, 11)
    chi = target_rows(rows, 'CHI', 'Chicago Blackhawks', 'United Center', '2026-10-23')[0]
    assert chi['day'] == ['Reverse'] and chi['team_matches'] == ['English'] and chi['matches'] == 2   # English 2 -> Reverse 7 = day
    for t in list(mtl.values()) + [chi]:
        assert all(len(t[k]) <= 1 for k in ('day', 'team_matches', 'arena_matches'))

def test_board_ties_sort_by_raw_english_and_row_shows_it():
    import numboard_v56 as nb, numbers_v58_ui as nu
    a = {'player': 'A', 'team': 'MTL', 'player_id': '1', 'day': ['English'], 'team_matches': [], 'arena_matches': [], 'matches': 1, 'form': 0.0, 'values': {}, 'eng_total': 88}
    b = dict(a, player='B', player_id='2', eng_total=142)
    board = nb.game_board({'arena_values': None}, [a, b], [])
    assert [p['player'] for p in board['players']] == ['B', 'A']   # same score: higher raw English total first
    assert board['players'][0]['threat'] == 50 and board['players'][0]['tier'] == 'hot'
    assert '· Eng 142' in nu.player_row(board['players'][0])
