"""V5.8 Numbers date & arena match table: arena-number calc, matching, the {'date','arena'}-only rule, empty states."""
import gem_match_v58 as gmx
from numerology_v48 import gematria
from player_targets_v49 import METHODS


def _slate(arena, players, away='MTL', home='CHI'):
    return [{'game': {'away': away, 'home': home, 'arena': arena},
             'away_targets': [{'player': n, 'player_id': str(i), 'team': away} for i, n in enumerate(players)], 'home_targets': []}]


def test_arena_number_uses_page_ciphers_and_real_venue_only():
    g = gematria('United Center')
    assert gmx.arena_number('United Center') == {f: g[f] for f, _ in METHODS}
    assert set(gmx.arena_number('Bell Centre')) == {'ordinal_root', 'reduction_root', 'reverse_root'}
    for missing in (None, '', 'None', float('nan'), '123'):
        assert gmx.arena_number(missing) is None


def _name_with(field, value, avoid=None):
    """Find a simple synthetic name whose cipher root equals value (deterministic search)."""
    import itertools, string
    for n in range(2, 5):
        for t in itertools.product(string.ascii_uppercase, repeat=n):
            v = gematria(''.join(t))
            if v[field] == value and (avoid is None or avoid(v)):
                return ''.join(t)
    raise AssertionError


def test_matching_date_and_arena_rows():
    day = 6   # United Center: English/Reduction root 3, Reverse root 6
    an = gmx.arena_number('United Center')
    target = an['ordinal_root']
    both = _name_with('ordinal_root', target, lambda v: day in (v['reduction_root'], v['reverse_root']) and target != day)
    rows = gmx.player_rows(both, day, an)
    assert ('date', 6) in rows and ('arena', target) in rows
    neither = _name_with('ordinal_root', 1, lambda v: all(v[f] not in (day, an[f]) for f, _ in METHODS))
    assert gmx.player_rows(neither, day, an) == []
    table, missing = gmx.match_table(_slate('United Center', [both, neither]), day)
    assert missing == [] and [(r['Player'], r['Match type']) for r in table] == [(both, 'date'), (both, 'arena')]
    assert all(r['Number'] == 6 for r in table if r['Match type'] == 'date')


def test_only_date_and_arena_ever_appear():
    import itertools, string
    names = [''.join(t) for t in itertools.product('ABCDEFGHIJ', repeat=3)]
    for day in range(1, 10):
        rows, _ = gmx.match_table(_slate('Scotiabank Arena', names) + _slate(None, names[:50], 'BOS', 'TOR'), day)
        assert rows and {r['Match type'] for r in rows} <= {'date', 'arena'}
        assert set(gmx.COLUMNS) == {'Player', 'Match type', 'Number'}
    h = gmx.table_html(rows, [], 5)
    assert '<th>Player</th><th>Match type</th><th>Number</th></tr>' in h and h.count('<th>') == 3
    assert 'Team' not in h and 'English' not in h


def test_missing_venue_skips_arena_and_says_so():
    day = 5
    rows, missing = gmx.match_table(_slate(None, ['ABC', 'DEFG', 'HIJKL']), day)
    assert missing == ['MTL @ CHI'] and all(r['Match type'] == 'date' for r in rows)
    h = gmx.table_html(rows, missing, day)
    assert 'no arena number for MTL @ CHI' in h and 'None' not in h


def test_empty_states():
    assert 'No player matches' in gmx.table_html([], [], 5)
    assert 'once this slate' in gmx.table_html([], [], 5, loaded=False)
    assert gmx.match_table(None, 5) == ([], [])
