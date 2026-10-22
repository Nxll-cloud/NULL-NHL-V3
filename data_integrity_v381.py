"""Coverage checks and cumulative metadata merges for V3.8.1."""
import pandas as pd

def normalize_id(series):
    return series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

def merge_profile_batches(existing, incoming):
    frames = [pd.DataFrame(x).copy() for x in (existing, incoming) if x is not None and not pd.DataFrame(x).empty]
    if not frames:
        return pd.DataFrame()
    for f in frames:
        if 'Player ID' not in f.columns:
            raise ValueError('Player ID missing in fetched metadata')
        f['Player ID'] = normalize_id(f['Player ID'])
    return pd.concat(frames, ignore_index=True).drop_duplicates('Player ID', keep='last').reset_index(drop=True)

def coverage_audit(combined, profiles=None, history=None):
    frame = pd.DataFrame(combined)
    p = pd.DataFrame(profiles) if profiles is not None else pd.DataFrame()
    h = pd.DataFrame(history) if history is not None else pd.DataFrame()
    count = lambda col: int(pd.to_numeric(frame.get(col, pd.Series(dtype=float)), errors='coerce').fillna(0).gt(0).sum())
    populated = lambda col: int(frame[col].fillna('').astype(str).str.strip().replace({'None':'', 'nan':''}).ne('').sum()) if col in frame else 0
    return {'Eligible players':len(frame), 'Profiles fetched':len(p), 'Histories fetched':len(h),
            'Players with jersey':populated('Jersey'), 'Players with life path':populated('Life path'),
            'Players with arena':populated('Arena'), 'Players with V3.8 flags':count('V3.8 flag count'),
            'Total V3.8 flags':int(pd.to_numeric(frame.get('V3.8 flag count', pd.Series(dtype=float)), errors='coerce').fillna(0).sum()),
            'Players with any storyline':count('Storyline count')}
