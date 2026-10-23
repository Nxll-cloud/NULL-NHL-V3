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


# --- calculation line under each row: shown digits come from the same values that decided the match ---
from numerology_v48 import universal_day


def _calc_rows(names, arena, day):
    rows, _ = gmx.match_table(_slate(arena, names), day)
    return rows


def test_calc_line_digits_equal_match_logic_mixed_case_and_accents():
    day = universal_day('2026-10-23')
    assert day == 7   # app's digit-sum method: 2+0+2+6+1+0+2+3 = 16 -> 7
    import itertools, string
    base = ['jJ pEtErKa', 'JJ PETERKA', 'Léon Draisaitl', 'LEON DRAISAITL', 'Tim Stützle', 'Juraj Slafkovský',
            'Nikolaj Ehlers', 'Alexis Lafrenière', 'Jesperi Kotkaniemi', "Ryan O'Reilly", 'Zemgus Girgensons']
    names = base + [a + ' ' + b for a, b in itertools.product(['Ab', 'Cé', 'dQ', 'Xx'], [''.join(t) for t in itertools.product('aEiÖ', repeat=3)])]
    arena = 'Centre Bell'
    an = gmx.arena_number(arena)
    rows = _calc_rows(names, arena, day)
    assert {r['Match type'] for r in rows} == {'date', 'arena'}
    seen_accent = False
    for r in rows:
        v = gematria(r['Player'])
        cells = r['calc']
        assert [c['field'] for c in cells] == [f for f, _ in METHODS]
        assert all(c['digit'] == v[c['field']] for c in cells)          # shown digit == cipher root used in the logic
        line = gmx.calc_line(r)
        for c in cells:
            assert f"{c['short']} {c['digit']}" in line
        hits = [c for c in cells if c['hit']]
        assert hits, r
        if r['Match type'] == 'date':
            assert all(c['digit'] == day for c in hits) and all(c['digit'] != day for c in cells if not c['hit'])
            assert r['Number'] == day and line.endswith(f'→ day {day}')
        else:
            assert [c['target'] for c in cells] == [an[f] for f, _ in METHODS]   # arena digits like-for-like
            assert all(c['digit'] == c['target'] for c in hits) and all(c['digit'] != c['target'] for c in cells if not c['hit'])
            assert r['Number'] == hits[0]['target'] and line.endswith('→ Centre Bell')
            for c in cells:
                assert f"{c['short']} {c['digit']}{'=' if c['hit'] else '≠'}{c['target']}" in line
        assert line.count('✓') == len(hits)
        seen_accent |= any(ch in r['Player'] for ch in 'éüöÖ')
    assert seen_accent
    # case and accents never change the digits: 'jJ pEtErKa' and 'JJ PETERKA' share the same calc
    by = {(r['Player'], r['Match type']): [c['digit'] for c in r['calc']] for r in rows}
    for a, b in (('jJ pEtErKa', 'JJ PETERKA'), ('Léon Draisaitl', 'LEON DRAISAITL')):
        for mt in ('date', 'arena'):
            assert by.get((a, mt)) == by.get((b, mt))
    g1, g2 = gematria('Léon Draisaitl'), gematria('LEON DRAISAITL')
    assert g1 == g2 and gematria('jJ pEtErKa') == gematria('JJ PETERKA')


def test_calc_line_rendered_as_subtitle_not_column():
    day = 7
    rows = _calc_rows(['jJ pEtErKa', 'Léon Draisaitl', 'Tim Stützle', 'Nikolaj Ehlers', 'Alexis Lafrenière'] +
                      [''.join(t) for t in __import__('itertools').product('ABCDE', repeat=3)], 'Rogers Place', day)
    h = gmx.table_html(rows, [], day)
    assert h.count('<th>') == 3 and '<th>Player</th><th>Match type</th><th>Number</th></tr>' in h
    assert h.count('class="gm-c"') == len(rows) and h.count('colspan="3"') == len(rows)
    for r in rows:
        assert html_escape(gmx.calc_line(r)) in h
        raw = gmx.calc_title(r)
        assert all(f"{c['raw']}→{c['digit']}" in raw for c in r['calc'])
    assert 'Rogers Place' in h and '→ day 7' in h


def test_calc_line_example_format():
    r = {'Match type': 'date', 'Number': 7, 'calc': [
        {'field': 'ordinal_root', 'short': 'Eng', 'raw': 96, 'digit': 6, 'target': 7, 'hit': False},
        {'field': 'reduction_root', 'short': 'Red', 'raw': 34, 'digit': 7, 'target': 7, 'hit': True},
        {'field': 'reverse_root', 'short': 'Rev', 'raw': 147, 'digit': 3, 'target': 7, 'hit': False}]}
    assert gmx.calc_line(r) == 'Eng 6 · Red 7 ✓ · Rev 3 → day 7'
    assert gmx.calc_title(r) == 'Eng 96→6 vs day 7 · Red 34→7 vs day 7 ✓ · Rev 147→3 vs day 7'


def html_escape(s):
    import html
    return html.escape(s)


def test_rev_tag_only_on_reverse_only_rows():
    import itertools
    from numerology_v48 import gematria as gm
    assert [gm('Cale Makar')[f] for f, _ in METHODS] == [2, 2, 7]
    names = ['Cale Makar', 'jJ pEtErKa', 'Léon Draisaitl', 'Tim Stützle'] + [''.join(t) for t in itertools.product('ABCDEFG', repeat=3)]
    day = 7
    rows, _ = gmx.match_table(_slate('United Center', names), day)
    makar = [r for r in rows if r['Player'] == 'Cale Makar' and r['Match type'] == 'date']
    assert makar and gmx.rev_only(makar[0])
    h = gmx.table_html(rows, [], day)
    kinds = set()
    for r in rows:
        assert r['Match type'] in ('date', 'arena')
        eng_red_hit = any(c['hit'] for c in r['calc'] if c['field'] in ('ordinal_root', 'reduction_root'))
        rev_hit = next(c['hit'] for c in r['calc'] if c['field'] == 'reverse_root')
        assert gmx.rev_only(r) == (rev_hit and not eng_red_hit)
        kinds.add((r['Match type'], gmx.rev_only(r)))
    # Eng + Rev totals = 27 x letters (a multiple of 9), so equal Reverse roots force equal English roots:
    # an arena row can never be Reverse-only. Date rows can (day 7: Rev 7 means Eng 2).
    assert kinds == {('date', True), ('date', False), ('arena', False)}
    for a in ('United Center', 'Bell Centre', 'Scotiabank Arena', 'Rogers Place'):
        ar, _ = gmx.match_table(_slate(a, names), day)
        assert not any(gmx.rev_only(r) for r in ar if r['Match type'] == 'arena')
    # the tag itself is generic: a constructed arena row with only a Reverse hit is tagged
    fake = {'Player': 'X', 'Match type': 'arena', 'Number': 6, 'arena': 'Test', 'calc': [
        {'field': f, 'short': 'x', 'raw': 1, 'digit': 1, 'target': 1, 'hit': f == 'reverse_root'} for f, _ in METHODS]}
    assert gmx.rev_only(fake) and 'gm-rev' in gmx.table_html([fake], [], day)
    assert h.count('class="gm-rev"') == sum(gmx.rev_only(r) for r in rows)
    assert 'title="Matched through Reverse cipher only"' in h and h.count('<th>') == 3
    # the tag sits in the Player cell, never in the match-type value
    assert '>date<' in h and '>arena<' in h and 'date REV' not in h and 'arena REV' not in h
