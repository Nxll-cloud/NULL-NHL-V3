from datetime import date
from numerology_v48 import universal_day, gematria, digit_root, analyze_game

def test_universal_day_2026_10_22():
    assert universal_day('2026-10-22') == 6
    assert universal_day(date(2026,10,22)) == 6

def test_gematria_abc():
    assert gematria('ABC')['ordinal'] == 6
    assert gematria('ABC')['reverse'] == 75
    assert gematria('ABC')['reduction'] == 6

def test_diacritics_and_empty():
    assert gematria('Montréal')['ordinal'] == gematria('Montreal')['ordinal']
    assert gematria('')['letters'] == 0
    assert digit_root(0) == 0

def test_venue_missing_not_fabricated():
    r = analyze_game({'Away':'MIN','Home':'CGY','Venue':None},'2026-10-22',{'MIN':'Minnesota Wild','CGY':'Calgary Flames'})
    assert r['arena_values'] is None and r['arena'] == ''
    assert r['universal'] == 6


def test_ciphers_are_one_digit():
    """Reduction always equals English and Reverse mirrors English (digits sum to 9), so a name carries one digit."""
    for name in ('Alex Newhook', 'Cale Makar', "Charle-Edouard D'Astous", 'Juraj Slafkovský', 'Blaze', 'ABC', 'Z'):
        g = gematria(name)
        assert g['reduction_root'] == g['ordinal_root']
        assert (g['ordinal_root'] + g['reverse_root']) % 9 == 0
