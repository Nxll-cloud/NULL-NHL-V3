"""V5.4 single source of truth for the Research “Player Intelligence” model.

Both the Research tab and the Home featured row call ``intelligence_from_state``
(or the pure ``build_intelligence``) with the same session inputs, so the four
picks — Top statistical goal scorer, Top storyline candidate, Best model +
storyline overlap, Statistical sleeper — are identical on both pages.
The pipeline is exactly the V5.2 Research pipeline, moved here unchanged:
build_signals -> build_storylines -> combined_table -> merge_history ->
merge_multi_history -> validate_statistical_ranks -> select_storyline_watch ->
separate_leaders.
"""
import pandas as pd

from signals import build_signals
from storylines_v36 import build_storylines, combined_table
from storyline_v38 import merge_history
from history_v386 import merge_multi_history
from ranking_integrity_v3871 import validate_statistical_ranks
from storyline_v37 import select_storyline_watch
from storyline_v387 import separate_leaders

LEADER_LABELS = [('statistical', 'TOP STATISTICAL GOALSCORER'), ('storyline', 'TOP STORYLINE CANDIDATE'),
                 ('overlap', 'BEST MODEL + STORYLINE OVERLAP'), ('longshots', 'STATISTICAL SLEEPER')]


def read_uploaded_metadata(uploaded):
    """Parse the optional Research metadata CSV. Returns (frame or None, warning or None)."""
    if uploaded is None:
        return None, None
    try:
        if hasattr(uploaded, 'seek'):
            uploaded.seek(0)
        metadata = pd.read_csv(uploaded, dtype=str).fillna('')
    except (ValueError, pd.errors.ParserError, UnicodeError) as exc:
        return None, f'Metadata could not be loaded: {exc}'
    if 'Player ID' not in metadata.columns:
        return None, 'Metadata needs a Player ID column; metadata ignored.'
    return metadata, None


def merge_metadata(uploaded_frame, automatic):
    """V3.5 rule: uploaded rows win over automatic profiles for the same Player ID."""
    if automatic is None:
        return uploaded_frame
    if uploaded_frame is None:
        return automatic
    return pd.concat([uploaded_frame, automatic], ignore_index=True).drop_duplicates(subset=['Player ID'], keep='first')


def build_intelligence(ranked, day, metadata=None, history_v38=None, history_v386=None):
    """Pure pipeline. Returns dict(signals, storylines, combined, top_stories,
    storyline_sleepers, featured, v387) or None when there is no ranked slate."""
    if not isinstance(ranked, pd.DataFrame) or ranked.empty:
        return None
    signals = build_signals(ranked, day, metadata)
    storylines = build_storylines(ranked, metadata if metadata is not None else pd.DataFrame(), day)
    combined = combined_table(ranked, signals, storylines)
    combined = merge_history(combined, history_v38)
    combined = merge_multi_history(combined, history_v386)
    validate_statistical_ranks(combined)
    top_stories, storyline_sleepers, featured = select_storyline_watch(combined)
    v387 = separate_leaders(combined)
    return {'signals': signals, 'storylines': storylines, 'combined': combined, 'top_stories': top_stories,
            'storyline_sleepers': storyline_sleepers, 'featured': featured, 'v387': v387}


def inputs_from_state(state, day):
    """Exactly the session lookups the V5.2 Research tab used. Returns (kwargs or None, warnings)."""
    warnings = []
    uploaded_frame, warn = read_uploaded_metadata(state.get('signal_meta'))
    if warn:
        warnings.append(warn)
    automatic = state.get('auto_signal_metadata') if state.get('auto_signal_day') == day and 'auto_signal_metadata' in state else None
    metadata = merge_metadata(uploaded_frame, automatic)
    if 'signals_ranked' not in state or state.get('signals_day') != day:
        return None, warnings
    return {'ranked': state['signals_ranked'], 'day': day, 'metadata': metadata,
            'history_v38': state.get('history_v38') if state.get('history_v38_day') == day else None,
            'history_v386': state.get('history_v386') if state.get('history_v386_day') == day else None}, warnings


def intelligence_from_state(state, day):
    """Shared entry point for Home and Research. Returns (result or None, warnings)."""
    kwargs, warnings = inputs_from_state(state, day)
    if kwargs is None:
        return None, warnings
    return build_intelligence(**kwargs), warnings


def four_picks(result):
    """{key: leader row dict or None} in LEADER_LABELS order."""
    leaders = (result or {}).get('v387', {}).get('leaders', {}) if result else {}
    out = {}
    for key, _ in LEADER_LABELS:
        lead = leaders.get(key)
        out[key] = None if lead is None else (lead.to_dict() if hasattr(lead, 'to_dict') else dict(lead))
    return out


def pick_identity(picks):
    """Comparable identity tuple per category: (Player ID, Player) or None."""
    return {k: (None if v is None else (str(v.get('Player ID', '')), str(v.get('Player', '')))) for k, v in picks.items()}
