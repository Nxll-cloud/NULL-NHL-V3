"""Exploratory, non-predictive date and name patterns. No automatic claims of causality."""
from datetime import date
import re
import pandas as pd


def reduce_number(value, keep_masters=False):
    value = abs(int(value))
    while value > 9 and (not keep_masters or value not in (11, 22, 33)):
        value = sum(int(c) for c in str(value))
    return value


def universal_day(day):
    d = date.fromisoformat(str(day))
    return reduce_number(sum(int(x) for x in d.strftime('%Y%m%d')))


def pythagorean(text):
    """A=1..I=9, J=1..R=9, S=1..Z=8; ASCII letters only."""
    return sum((ord(c) - 65) % 9 + 1 for c in str(text).upper() if 'A' <= c <= 'Z')


def ordinal(text):
    return sum(ord(c) - 64 for c in str(text).upper() if 'A' <= c <= 'Z')


def build_signals(players, day, metadata=None):
    """Do not infer DOB, jersey, arena or storylines from names. Metadata is optional."""
    ud = universal_day(day)
    extra = {}
    if metadata is not None and not metadata.empty:
        for _, m in metadata.iterrows():
            pid = str(m.get('Player ID', '')).strip()
            if pid and pid not in extra:
                extra[pid] = m
    out = []
    for _, r in players.iterrows():
        name = str(r.get('Player', '')).strip()
        if not name or name.lower() == 'nan':
            continue
        pid = str(r.get('Player ID', '')).strip()
        if pid.endswith('.0'):
            pid = pid[:-2]
        m = extra.get(pid, {})
        pyth = pythagorean(name)
        ordv = ordinal(name)
        jersey = None
        raw_jersey = str(m.get('Jersey', '')).strip()
        if re.fullmatch(r'\d{1,2}', raw_jersey):
            jersey = int(raw_jersey)
        dob = str(m.get('Birth date', '')).strip()
        life_path = None
        birthday = False
        if dob and dob.lower() != 'nan':
            try:
                birth = date.fromisoformat(dob)
                if birth <= date.fromisoformat(day):
                    life_path = reduce_number(sum(int(c) for c in birth.isoformat() if c.isdigit()))
                    birthday = (birth.month, birth.day) == (date.fromisoformat(day).month, date.fromisoformat(day).day)
            except ValueError:
                pass
        arena = str(m.get('Arena', '')).strip()
        if arena.lower() == 'nan':
            arena = ''
        story = str(m.get('Verified storyline', '')).strip()
        source = str(m.get('Source URL', '')).strip()
        if story.lower() == 'nan': story = ''
        if source.lower() == 'nan': source = ''
        if story and not source:
            story = ''  # Do not display unsupported storyline claims.
        matches = []
        if reduce_number(pyth) == ud: matches.append('Name Pythagorean')
        if reduce_number(ordv) == ud: matches.append('Name ordinal')
        if jersey is not None and reduce_number(jersey) == ud: matches.append('Jersey')
        if life_path is not None and life_path == ud: matches.append('Life path')
        if arena and reduce_number(pythagorean(arena)) == ud: matches.append('Arena Pythagorean')
        out.append({'Player': name, 'Team': r.get('Team'), 'Player ID': pid,
                    'Universal day': ud, 'Name Pythagorean': pyth,
                    'Name ordinal': ordv, 'Jersey': jersey, 'Life path': life_path,
                    'Birthday': birthday if life_path is not None else None,
                    'Arena': arena or None, 'Pattern overlaps': len(matches),
                    'Matching patterns': ', '.join(matches) or 'None',
                    'Verified storyline': story or None,
                    'Storyline source': source or None})
    return pd.DataFrame(out).sort_values(['Pattern overlaps', 'Player'], ascending=[False, True])
