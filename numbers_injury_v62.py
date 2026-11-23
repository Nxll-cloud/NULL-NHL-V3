"""Numbers tab: silently drop currently injured players before ranking, filters and overlays.

Source: the same public ESPN injuries feed already used on Home / parlays
(storylines_v58.espn_fetch('injuries')). Historical gematria logs are never rewritten.
If the feed cannot be loaded, results stay unfiltered and the failure is logged
server-side only (no UI note, no crash).
"""
import logging

import pandas as pd

import storylines_v58 as slx

LOG = logging.getLogger('nulls.numbers')


def drop_from_ranked(ranked, injured):
    """Return a copy of the rankings frame without rows in ``injured`` {(norm name, team)}.

    ``injured`` empty or None leaves the frame unchanged (same object). Missing
    Player/Team columns are also left unchanged.
    """
    if ranked is None or injured is None or not injured:
        return ranked
    if not isinstance(ranked, pd.DataFrame) or ranked.empty:
        return ranked
    if not {'Player', 'Team'}.issubset(ranked.columns):
        return ranked
    keep = [
        (slx.norm(name), str(team or '').upper()) not in injured
        for name, team in zip(ranked['Player'], ranked['Team'])
    ]
    return ranked.loc[keep].copy()


def apply(ranked, fetch=None, log=LOG):
    """Load the ESPN injury list and drop those players from ``ranked``.

    ``fetch`` defaults to ``storylines_v58.espn_fetch('injuries')`` (injectable in tests).
    Any exception — network, bad payload, unexpected shape after a raise in fetch —
    is logged and ``ranked`` is returned unchanged.
    """
    if ranked is None:
        return ranked
    try:
        payload = fetch() if fetch is not None else slx.espn_fetch('injuries')
        injured = slx.injured_players(payload)
    except Exception:
        log.exception('Numbers injury filter unavailable; leaving results unfiltered')
        return ranked
    return drop_from_ranked(ranked, injured)
