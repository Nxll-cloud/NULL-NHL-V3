"""V5.9: goalie marker for Home ('G' pill). Display only.

Goalie status comes ONLY from real position data: NHL ``positionCode`` (roster / play-by-play / boxscore), the rankings
``Position`` column, or the source category the NHL / ESPN feeds file a player under (club-stats ``goalies`` array, boxscore
``playerByGameStats.*.goalies``, ESPN ``probableStartingGoalie``), which those parsers record as ``position``/``Position`` 'G'.
Never from names. No position data -> no badge.

    goalie_badge(position)        -> '<span class="npg" ...>G</span>' or ''
    position_of(record)           -> the first position field found on a dict (or None)
    is_goalie(position)           -> True only for 'G'
    goalie_row_class(position)    -> ' is-g' (subtle row tint) or ''
"""
import html as _html

POSITION_KEYS = ('position', 'Position', 'positionCode', 'pos')
LABEL = 'Goalie'


def is_goalie(position):
    if isinstance(position, dict):   # ESPN style {'abbreviation': 'G'}
        position = position.get('abbreviation') or position.get('code')
    return isinstance(position, str) and position.strip().upper() == 'G'


def position_of(record):
    if not isinstance(record, dict):
        return None
    for k in POSITION_KEYS:
        v = record.get(k)
        if v not in (None, ''):
            return v
    return None


def goalie_badge(position):
    """Small outlined 'G' pill (styled by .v55 .npg in assets/v58.css). '' for skaters and for missing position data."""
    if not is_goalie(position):
        return ''
    t = _html.escape(LABEL)
    return f'<span class="npg" title="{t}" aria-label="{t}">G</span>'


def goalie_row_class(position):
    return ' is-g' if is_goalie(position) else ''
