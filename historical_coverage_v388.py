"""Coverage of requested historical seasons for the full ranked slate."""
import pandas as pd

def historical_coverage(combined: pd.DataFrame) -> dict:
    total = len(combined)
    if 'Historical data status' not in combined.columns:
        complete = partial = 0
    else:
        statuses = combined['Historical data status'].fillna('').astype(str).str.strip()
        complete = int(statuses.eq('Complete').sum())
        partial = int((statuses.ne('') & ~statuses.eq('Complete') & ~statuses.eq('Not fetched')).sum())
    not_fetched = total - complete - partial
    return {'total':total,'complete':complete,'partial':partial,'not_fetched':not_fetched,
            'fraction':complete/total if total else 0.0,'percent':100*complete/total if total else 0.0}
