"""Auditable pregame facts; no news or injury assertions."""
from datetime import date
import pandas as pd
from signals import reduce_number, pythagorean, ordinal


def build_storylines(ranked, metadata, day):
    """Only use source-linked profiles and pre-slate stats already in rankings."""
    if not isinstance(ranked, pd.DataFrame): ranked = pd.DataFrame(ranked)
    if not isinstance(metadata, pd.DataFrame): metadata = pd.DataFrame(metadata)
    profiles = {}
    for _, r in metadata.iterrows():
        key = str(r.get('Player ID', '')).removesuffix('.0')
        if key: profiles[key] = r
    slate = date.fromisoformat(str(day))
    output = []
    for _, r in ranked.iterrows():
        pid = str(r.get('Player ID', '')).removesuffix('.0')
        p = profiles.get(pid)
        facts, sources = [], []
        if p is not None:
            url = str(p.get('Source URL', ''))
            dob = str(p.get('Birth date', ''))
            try:
                born = date.fromisoformat(dob)
                if born <= slate and (born.month, born.day) == (slate.month, slate.day):
                    facts.append('Birthday on slate date')
                    sources.append(url)
            except ValueError: pass
        try:
            recent_goals = float(r.get('Goals/G L5', 0))
            prior_games = int(r.get('Prior GP', 0))
            if prior_games >= 5 and recent_goals >= .6:
                facts.append('Recent goal form: >=0.6 goals/game over last five')
                sources.append('https://api-web.nhle.com/v1/player/{}/game-log/20262027/2'.format(pid))
        except (ValueError, TypeError): pass
        output.append({'Player ID': pid, 'Storyline count': len(facts),
                       'Verified data flags': ' | '.join(facts) or 'None',
                       'Evidence URLs': ' | '.join(sources) or '',
                       'Former-team matchup': 'Not verified',
                       'Milestone watch': 'Not verified',
                       'Injury/news': 'Not verified'})
    return pd.DataFrame(output)


def combined_table(ranked, signals, storylines):
    """Join without treating experimental patterns as probabilities."""
    base = pd.DataFrame(ranked).copy()
    base['Player ID'] = base['Player ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    sig = signals.copy()
    sig['Player ID'] = sig['Player ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    story = storylines.copy()
    for frame in (sig, story):
        if frame['Player ID'].duplicated().any(): raise ValueError('Duplicate player IDs')
    cols = ['Player ID','Pattern overlaps','Matching patterns','Jersey','Life path','Birthday','Arena', 'Name Pythagorean','Name ordinal']
    result = base.merge(sig[[c for c in cols if c in sig]], on='Player ID', how='left', validate='one_to_one')
    result = result.merge(story, on='Player ID', how='left', validate='one_to_one')
    result['Pattern overlaps'] = result['Pattern overlaps'].fillna(0).astype(int)
    result['Storyline count'] = result['Storyline count'].fillna(0).astype(int)
    for col in ('Name Pythagorean','Name ordinal'):
        if col in result: result[col+' reduced'] = result[col].apply(lambda v: reduce_number(int(v)) if pd.notna(v) else None)
    result['Exploratory overlap count'] = result['Pattern overlaps'] + result['Storyline count']
    return result
