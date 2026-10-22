"""Deterministic recreational numerology and gematria; not predictive analytics."""
from datetime import date
import re
import unicodedata


def digit_root(value):
    number = abs(int(value))
    while number >= 10:
        number = sum(int(x) for x in str(number))
    return number


def universal_day(day):
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return digit_root(sum(int(x) for x in d.strftime('%Y%m%d')))


def _clean_text(value):
    """V5.3: None/NaN/'nan' are missing values, never the letters N-A-N."""
    if value is None:
        return ''
    if isinstance(value, float) and value != value:
        return ''
    text = str(value).strip()
    return '' if text.lower() in ('nan', 'none', 'null', '<na>') else text


def letters(text):
    plain = unicodedata.normalize('NFKD', _clean_text(text))
    return re.sub('[^A-Z]', '', ''.join(c for c in plain if not unicodedata.combining(c)).upper())


def gematria(text):
    clean = letters(text)
    ordinal = sum(ord(c) - 64 for c in clean)
    reverse = sum(91 - ord(c) for c in clean)
    return {'ordinal': ordinal, 'ordinal_root': digit_root(ordinal),
            'reduction': sum(digit_root(ord(c) - 64) for c in clean),
            'reduction_root': digit_root(sum(digit_root(ord(c) - 64) for c in clean)),
            'reverse': reverse, 'reverse_root': digit_root(reverse),
            'letters': len(clean)}


def alignment(day_number, *names):
    """Only counts literal digit-root matches, not claimed outcomes."""
    matches = []
    for label, name in names:
        if not name:
            continue
        result = gematria(name)
        for method in ('ordinal_root', 'reduction_root', 'reverse_root'):
            if result[method] == day_number:
                matches.append(f'{label} · {method.replace("_root", "").replace("_", " ")}')
    return matches


def analyze_game(game, day, names):
    away, home = _clean_text(game.get('Away')).upper(), _clean_text(game.get('Home')).upper()
    arena = _clean_text(game.get('Venue'))
    universal = universal_day(day)
    away_name = names.get(away, away)
    home_name = names.get(home, home)
    matches = alignment(universal, ('Away', away_name), ('Home', home_name), ('Arena', arena))
    return {'away': away, 'home': home, 'away_name': away_name, 'home_name': home_name,
            'arena': arena, 'start': game.get('Start (UTC)'), 'universal': universal,
            'away_values': gematria(away_name), 'home_values': gematria(home_name),
            'arena_values': gematria(arena) if arena else None, 'matches': matches}
