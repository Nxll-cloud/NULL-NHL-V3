"""Transparent pre-slate diagnostic checks; never converts missing evidence to a negative claim."""
from datetime import date
import pandas as pd


def diagnostic_summary(combined, metadata=None, history=None, slate_day=None):
    f = pd.DataFrame(combined)
    m = pd.DataFrame(metadata) if metadata is not None else pd.DataFrame()
    h = pd.DataFrame(history) if history is not None else pd.DataFrame()
    if slate_day:
        target = date.fromisoformat(str(slate_day))
    else:
        target = None
    valid_birthdates = 0
    birthdays = 0
    malformed_birthdates = 0
    if 'Birth date' in m.columns:
        for raw in m['Birth date'].fillna(''):
            if not str(raw).strip():
                continue
            try:
                dob = date.fromisoformat(str(raw).strip())
                if target and dob > target:
                    raise ValueError('future birthdate')
                valid_birthdates += 1
                if target and (dob.month, dob.day) == (target.month, target.day):
                    birthdays += 1
            except ValueError:
                malformed_birthdates += 1
    numeric = lambda col: pd.to_numeric(h[col], errors='coerce').fillna(0) if col in h else pd.Series(dtype=float)
    vs = numeric('Vs opponent GP')
    valid = numeric('Log rows valid pre-slate')
    excluded = numeric('Log rows excluded')
    watch = h['Milestone watch (not a flag)'].fillna('').astype(str).str.strip().ne('').sum() if 'Milestone watch (not a flag)' in h else 0
    return {
        'Eligible players':len(f), 'Histories fetched':len(h),
        'Histories with >=1 valid game':int(valid.gt(0).sum()),
        'Histories with >=1 opponent meeting':int(vs.gt(0).sum()),
        'Total prior opponent meetings':int(vs.sum()),
        'Total excluded game-log rows':int(excluded.sum()),
        'Near milestones (2-3 goals away; watch only)':int(watch),
        'Profiles with valid birthdays':valid_birthdates,
        'Profiles with invalid birthdays':malformed_birthdates,
        'Birthdays on slate date':birthdays,
        'Opponent match status':('No prior opponent meetings found in fetched histories' if len(h) and not vs.gt(0).any() else 'See per-player evidence'),
    }
