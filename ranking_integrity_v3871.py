"""Stable statistical ranks from adjusted form, independent of storyline joins."""
import pandas as pd


def assign_statistical_ranks(ranked):
    """Sort by the actual V3.2 ordering and attach unique 1-based ranks."""
    frame = pd.DataFrame(ranked).copy()
    if frame.empty:
        frame['Statistical rank'] = pd.Series(dtype='int64')
        return frame
    if frame['Player ID'].isna().any() or frame['Player ID'].astype(str).duplicated().any():
        raise ValueError('Statistical ranking requires unique non-null Player IDs')
    frame['V3.2 Adjusted Index'] = pd.to_numeric(frame['V3.2 Adjusted Index'], errors='coerce')
    frame['Shots/G L5'] = pd.to_numeric(frame['Shots/G L5'], errors='coerce')
    if frame['V3.2 Adjusted Index'].isna().any():
        raise ValueError('Cannot rank players with missing adjusted form index')
    frame = frame.sort_values(['V3.2 Adjusted Index', 'Shots/G L5', 'Player'],
                              ascending=[False,False,True], kind='stable').reset_index(drop=True)
    frame['Statistical rank'] = range(1,len(frame)+1)
    return frame


def validate_statistical_ranks(frame):
    f = pd.DataFrame(frame)
    if f.empty: return True
    if 'Statistical rank' not in f or 'Player ID' not in f:
        raise ValueError('Statistical rank or Player ID missing')
    ranks = pd.to_numeric(f['Statistical rank'],errors='coerce')
    if ranks.isna().any() or sorted(ranks.astype(int).tolist()) != list(range(1,len(f)+1)):
        raise ValueError('Statistical ranks must be unique and span 1 through player count')
    if f['Player ID'].astype(str).duplicated().any():
        raise ValueError('Duplicate player IDs after evidence merge')
    return True
