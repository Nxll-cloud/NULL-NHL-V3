"""FUTURE / NOT WIRED — live game data integration scaffold (Null's Playbook V5.4).

Nothing in this module is imported or rendered by app.py while
``LIVE_SCORING_ENABLED`` is False (the default), so users see no change.
It defines the data model, provider interface, polling design and render hook
for a future live scoring ticker. Provider ``fetch_*`` methods intentionally
raise ``NotImplementedError``; no network calls are made from here.

Only ``GoalEvent`` / ``LiveGameState`` and the pure helpers (``dedupe_events``,
``backoff_delay``, ``should_poll``) are used today — by prediction_tracker_v54,
which converts official boxscore goals into ``GoalEvent`` objects so the
future poller and the tracker share one shape.

Design summary (see README “Future: Live Scoring Ticker”):
* Providers: NHL official API (api-web.nhle.com, no key), ESPN (unofficial,
  no key, may change without notice), SportsGameOdds (requires ``SGO_API_KEY``
  in Streamlit secrets — never in code or the repo).
* Poller: ~30 s base interval, per-provider minimum interval, exponential
  backoff with jitter on HTTP 429/5xx, dedupe by event id, poll only while a
  slate game is live, cache the last good state so a failed poll never blanks
  the UI. Refresh via ``st.fragment(run_every=...)`` when available
  (``hasattr(st, 'fragment')``), else ``streamlit_autorefresh``, with data
  cached by ``st.cache_data(ttl=...)``.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

LIVE_SCORING_ENABLED = False          # feature flag — keep False until providers are implemented
BASE_POLL_SECONDS = 30
MAX_BACKOFF_SECONDS = 300
LIVE_STATES = frozenset({'LIVE', 'CRIT'})   # NHL gameState values while play is in progress


@dataclass(frozen=True)
class GoalEvent:
    game_id: str
    period: int
    time: str                       # MM:SS elapsed in period
    team: str                       # NHL abbreviation, e.g. 'MIN'
    scorer: str
    scorer_id: Optional[str] = None
    assists: tuple = ()             # tuple of (name, player_id or None)
    strength: str = 'ev'            # ev / pp / sh / en / ps
    timestamp: Optional[str] = None # ISO-8601 UTC when known
    event_id: Optional[str] = None  # provider event id used for dedupe
    provider: str = 'nhl'

    @property
    def key(self):
        """Stable dedupe key: provider event id, else game/period/time/scorer."""
        if self.event_id not in (None, ''):
            return (str(self.game_id), 'id', str(self.event_id))
        return (str(self.game_id), int(self.period), str(self.time), str(self.scorer_id or self.scorer).casefold())


@dataclass
class LiveGameState:
    game_id: str
    away: str
    home: str
    state: str = 'FUT'              # FUT / PRE / LIVE / CRIT / FINAL / OFF
    period: int = 0
    clock: str = ''
    away_score: int = 0
    home_score: int = 0
    goals: list = field(default_factory=list)   # list[GoalEvent]
    updated_at: Optional[str] = None

    @property
    def is_live(self):
        return self.state in LIVE_STATES


class LiveScoreProvider(ABC):
    """Provider interface. Implementations must be side-effect free apart from HTTP."""
    name = 'base'
    min_interval_seconds = BASE_POLL_SECONDS
    requires_key = False

    @abstractmethod
    def fetch_slate_states(self, day: str) -> list:
        """Return list[LiveGameState] for every game on ``day`` (YYYY-MM-DD)."""

    @abstractmethod
    def fetch_goal_events(self, game_id: str) -> list:
        """Return list[GoalEvent] scored so far in ``game_id``."""


class NHLOfficialProvider(LiveScoreProvider):
    """api-web.nhle.com — official, no key. TODO: /v1/score/{day} + /v1/gamecenter/{id}/landing."""
    name = 'nhl'
    min_interval_seconds = 30

    def fetch_slate_states(self, day):
        raise NotImplementedError('TODO: GET https://api-web.nhle.com/v1/score/{day} and map games -> LiveGameState')

    def fetch_goal_events(self, game_id):
        raise NotImplementedError('TODO: GET /v1/gamecenter/{game_id}/landing summary.scoring -> GoalEvent '
                                  '(prediction_tracker_v54.parse_landing_goals already parses final boxscores)')


class ESPNProvider(LiveScoreProvider):
    """Unofficial ESPN scoreboard JSON — no key, undocumented, may change without notice."""
    name = 'espn'
    min_interval_seconds = 45

    def fetch_slate_states(self, day):
        raise NotImplementedError('TODO: site.api.espn.com hockey/nhl scoreboard?dates=YYYYMMDD; treat as fallback only')

    def fetch_goal_events(self, game_id):
        raise NotImplementedError('TODO: ESPN summary?event={id} scoring plays; map ESPN ids to NHL ids by teams + start time')


class SportsGameOddsProvider(LiveScoreProvider):
    """SportsGameOdds — commercial, requires SGO_API_KEY in Streamlit secrets; quota-limited."""
    name = 'sportsgameodds'
    min_interval_seconds = 60
    requires_key = True

    def __init__(self, api_key: str = ''):
        self.api_key = api_key or ''

    @classmethod
    def from_secrets(cls, secrets=None):
        """Read SGO_API_KEY from st.secrets (or a mapping in tests). Never log the key."""
        if secrets is None:
            try:
                import streamlit as st
                secrets = st.secrets
            except Exception:
                secrets = {}
        try:
            return cls(secrets.get('SGO_API_KEY', ''))
        except Exception:
            return cls('')

    def fetch_slate_states(self, day):
        raise NotImplementedError('TODO: SportsGameOdds events endpoint (live=true, leagueID=NHL); requires SGO_API_KEY')

    def fetch_goal_events(self, game_id):
        raise NotImplementedError('TODO: SportsGameOdds event results; respect plan rate limits')


# ------------------------------------------------------------------ pure helpers

def dedupe_events(events: Iterable[GoalEvent], seen: Optional[set] = None) -> list:
    """Drop events whose key was already seen (across polls when ``seen`` is reused)."""
    seen = set() if seen is None else seen
    out = []
    for ev in events:
        k = ev.key
        if k in seen:
            continue
        seen.add(k)
        out.append(ev)
    return out


def backoff_delay(attempt: int, status: Optional[int] = None, base: float = BASE_POLL_SECONDS,
                  cap: float = MAX_BACKOFF_SECONDS, rng: Optional[random.Random] = None) -> float:
    """Seconds to wait before the next poll. 429/5xx -> exponential backoff + full jitter."""
    rng = rng or random
    if status is not None and (status == 429 or 500 <= status < 600):
        ceiling = min(cap, base * (2 ** max(0, attempt)))
        return base + rng.uniform(0, ceiling)
    return float(base)


def should_poll(states: Iterable[LiveGameState], now: Optional[datetime] = None) -> bool:
    """Poll only while at least one slate game is live (pre-game/final games are not polled)."""
    return any(s.is_live for s in states)


class LivePoller:
    """Design stub. Intended loop (driven by a Streamlit fragment, not a thread):

    1. if not LIVE_SCORING_ENABLED: return cached state.
    2. pick the first provider whose ``min_interval_seconds`` has elapsed.
    3. states = provider.fetch_slate_states(day); if not should_poll(states): stop.
    4. for live games: events = dedupe_events(provider.fetch_goal_events(id), self.seen).
    5. on 429/5xx: next_at = now + backoff_delay(attempt, status); keep last state.
    6. hand new events to prediction_tracker_v54.ingest_goal_events(day, events).
    """

    def __init__(self, providers=None):
        self.providers = list(providers or [NHLOfficialProvider()])
        self.seen: set = set()
        self.last_state: list = []
        self.attempt = 0

    def poll_once(self, day: str):
        raise NotImplementedError('TODO: implement the loop described in the class docstring')


def render_live_ticker(day: str, leaders: Optional[dict] = None) -> None:
    """Hook (NOT WIRED). Planned Home placement: a slim ticker strip under the header,
    a 'Scored tonight' badge on any leader card whose player has a GoalEvent, the
    leader card highlighted, and live scores on the matchup chips. Must no-op when
    the flag is off so the default UI never changes."""
    if not LIVE_SCORING_ENABLED:
        return None
    raise NotImplementedError('TODO: render ticker with ui_theme_v53 badges once a provider is implemented')
