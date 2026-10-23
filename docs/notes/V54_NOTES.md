# Null’s Playbook V5.4 — release notes

V5.4 keeps every V5.3 feature, data source and scoring rule. No ranking changes on valid inputs: everything new is either a new view or a display-layer change (Form %), and the one optional ranking change (track record) is OFF by default.

## What’s new
| Area | Summary |
|---|---|
| Brand | `assets/logo.svg` (full lockup), `assets/logo_mark.svg` (mark), PNG exports and favicon. The full lockup is in the Home hero; the mark is in the other tab headers, the sidebar and the page icon. `ui.brand()` falls back to a text wordmark if an asset is missing. |
| Home | No historical coverage on Home (it remains in Research). New elements: a track-record strip, a featured **Player intelligence model** row and Form % everywhere. |
| Matchup Center (new tab) | Four clickable intel cards, a game selector, back buttons, a **Player targets by matchup** view, leakiest goalies and probable starters. |
| Research | New **Goalies: Goals Allowed** section. All tables and CSVs gain a numeric `Form %` column. |
| Track Record (new tab) | Prediction tracker: grading, trends, per-source and per-player records, a manual results form, NHL import and JSON export/import. |
| Live scoring | `live_scoring_future.py` scaffold only (flag OFF, not imported). See README “Future: Live Scoring Ticker”. |

## Home featured intel row = Research picks
Home and Research both call `player_intelligence_v54.intelligence_from_state(st.session_state, day)` → `four_picks()`. The V5.2 Research pipeline was moved into that module unchanged:

build_signals → build_storylines → combined_table → merge_history → merge_multi_history → validate_statistical_ranks → select_storyline_watch → separate_leaders

The four categories are Top statistical goalscorer, Top storyline candidate, Best model + storyline overlap and Statistical sleeper. A category with no lead shows “Insufficient data for this date”.

Tests:
* `test_v54_intel.py` shows the module output is identical to the legacy inline pipeline.
* `test_v54_apptest.py` shows every pick name appears on both Home and Research.

## Goalies: Goals Allowed
* **Source:** NHL official stats API, `https://api-web.nhle.com/v1/club-stats/{TEAM}/{SEASON}/2` (regular season), using the `goalies[]` array: `goalsAgainst`, `gamesPlayed`, `gamesStarted`, `shotsAgainst`, `saves`, `timeOnIce`, `savePercentage`.
* **Calculations:**
  * GAA is recomputed as GA × 3600 / TOI-seconds; None when TOI is 0.
  * SV% = saves / shots; None when shots are 0.
  * The team total sums all goalies who played for that club, so a traded goalie counts for each club with that club’s split.
* **Caching:** `st.cache_data` with a 30-minute TTL; teams are fetched in parallel and a failure never breaks the tab. Errors are listed in an expander.
* **Sorting:** by Goals allowed, GAA or Save % (leakiest first).
* **Tones:** the leakiest third is warm (orange, “Leaky · opportunity”) and the stingiest third is cool (blue, “Stingy”). The rest are “Middle of slate”; teams without data are “No data”. A legend sits above the grid.
* **Scope:** tonight’s slate teams by default, or all teams via a checkbox.

## Matchup Center
* **Overview:** the same four intel cards, each with an **Open matchup** button, plus “Open any game on the slate”.
  * A pick maps to its game by team (and listed opponent when a team is in two games, otherwise the earliest start).
  * A pick whose team is not on the slate shows a warning and a back button.
* **Matchup view:** a matchup bar and a **Player targets by matchup** section, one column per team.
  * Targets are filtered to the two teams, de-duplicated and sorted by Form score, then statistical rank, then numerology matches.
  * The side whose shooters face the leakier opposing goalie (by GAA) comes first and is labelled “▲ FACES THE LEAKIER GOALIE (BY GAA)”.
* **Badges:**

  | Badge | Rule |
  |---|---|
  | Stats | statistical rank ≤ 20 |
  | Numbers | ≥ 2 matches |
  | Overlap | both of the above |
  | Odds +x% | best-price gap on a unique name match |
  | Intel pick | one of the four leaders |
  | Track record | the player’s track badge |

* **Leakiest goalie:** the highest GAA among goalies with GP > 0. Ties go to more GA, then more GP, then name. A goalie with unknown GAA ranks after the known ones.
* **Navigation:** state is kept in `st.session_state['v54_mc_game']` and mirrored to the `?matchup=` query param when supported.

* Each overview pick card sits in the same column as its “Open … vs …” button, so the two stay together when the columns stack on mobile.

## Probable starting goalies
* **Order of sources:**
  1. **NHL first:** `api-web.nhle.com/v1/gamecenter/{id}/boxscore` → `playerByGameStats.{awayTeam,homeTeam}.goalies[].starter`. This is used only for LIVE/OFF/FINAL games; exactly one flagged goalie per team is required.
  2. **ESPN fallback:** `site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates=YYYYMMDD` → `events[].competitions[0].competitors[].probables[]` where `name == "probableStartingGoalie"`. Its `status.type` maps `confirmed` → **Confirmed starter** and `expected`/`probable`/`likely` → **Probable starter**. ESPN team codes are mapped to NHL codes (SJ→SJS, NJ→NJD, LA→LAK, TB→TBL, UTAH→UTA, …).
* **Normalized dict:** `{game_id, team, goalie_id, goalie, status, source, fetched_at}`. The status is confirmed, probable or unknown.
* **Caching:** `st.cache_data` with a 5-minute TTL (`STARTER_TTL_SECONDS = 300`). Failures are cached for the same TTL, which also works as backoff: there is at most one retry per 5 minutes per server process, with an 8 s request timeout.
* **Display:**
  * With a starter, a badge shows the label, source and fetch time, plus the starter’s season line (matched by NHL id, then by unique normalized name, then by initial + last name).
  * With no starter, the label is **“Team goalie stats — starter not yet announced”**.
  * The “leakiest goalie” card is always labelled as team stats (“…not necessarily tonight’s starter”). It is never called the starter unless the feed says so.
* **Real feeds, 2026-10-22, pregame:**
  * ESPN exposed `probableStartingGoalie` for all 12 games: 8 fully confirmed, and 4 with at least one `expected` (NSH; SEA/UTA; VAN/DET).
  * The NHL pregame boxscore (gameState FUT) has **no** `playerByGameStats` or starter info. The `starter` flag appears only once a game is live or final (checked on final game 2026020152).
  * The NHL `matchup.goalieComparison` block lists team goalies but does not mark a starter, so it is not used.
  * Fixtures are in `test_fixtures_v54/`.

## Form % (display layer only)
**Definition:** Form % = clip(V3.2 Adjusted Index, 0, 100).

* The goal-scoring Form index is already a points index whose 100-point benchmark is a player averaging 4 shots/game and 0.5 goals/game. Form % is therefore the share of that benchmark.
* This is **not** per-slate min-max normalization, so a player’s Form % does not change when the slate changes.
* All conversion goes through one helper set in `ui_theme_v53.py`: `form_pct`, `format_form_pct`, `with_form_pct` and `form_pct_config`.

**Formatting and edge cases:**

| Input | Shown |
|---|---|
| 0–100 | rounded whole percent |
| above 100 | “100%+” in text; 100 in numeric columns |
| negative | 0% |
| None, NaN, inf or non-numeric | “—” |

Today’s real slate had a maximum of 156.2, with 8 players above 100.

**Sorting:** tables get a numeric `Form %` column inserted before the raw column, using `NumberColumn` / `ProgressColumn` with format `%d%%`, so sorting is numeric. The raw `V3.2 Adjusted Index` column stays next to it, so no ordering or precision is lost.

**Old → new mapping:**

| Old | New |
|---|---|
| “Form score”, “Form Score”, “FORM” (cards, captions, Numbers lines, Matchup targets) | “Form %” / “FORM %” with `format_form_pct` |
| Raw score text, e.g. `64.6` | `65%`; `156.2` → `100%+` |
| Leaderboard ProgressColumn, max = slate leader’s score | “Form %” ProgressColumn, fixed 0–100 |
| Research / Numbers tables, raw index only | `Form %` (numeric) + raw `V3.2 Adjusted Index` |
| CSV exports (ranked, scored, frame, top stories, combined, filtered, signals) | gain a `Form %` column; all raw columns unchanged |
| Threshold `form > 0` (overlap eligibility) | identical to `Form % > 0`; logic still uses the raw value |
| Pre-game snapshot CSV (backtest re-upload) | **unchanged, raw**, because backtesting re-reads it |

## Track Record (prediction_tracker_v54.py)
* **Storage:** SQLite at `data/prediction_tracker_v54.sqlite`, or `PLAYBOOK_TRACKER_DB`. `data/` and `*.sqlite` are gitignored. Each write is one transaction.
* **Ephemeral filesystem:** Streamlit Cloud’s filesystem does not persist, so export JSON regularly. Import merges the file, never touches locked slates, and only accepts whitelisted columns.
* **Saving:** Home auto-saves the slate’s predictions, idempotently, when the slate is today or later. Saving locks automatically at the first puck drop, and a locked slate is never modified. A manual **Lock** button exists; locking a past slate marks it *retro*.
* **What is saved:** the four leaders (Stats / Numbers / Odds / Overlap), statistical top 10 (`PICK_CUTOFF`) plus watch band 11–15, and gematria top 5.
* **Definitions** (module docstring):
  * hit / miss over unique picks in final games;
  * unpredicted scorers;
  * near-misses: a watch-band player who scored, or a pick with an assist but no goal;
  * a pending slate is excluded from all rates.
* **Learning:** p0 = pooled hit rate (0.25 until 20 graded picks); shrunk = (k + 10·p0)/(n + 10); adj = clamp(0.5·(shrunk − p0)/p0, ±0.05), and 0 when n < 3.
  * Toggle **“Use track record to adjust rankings”** (default OFF): when OFF, the ranking object is returned untouched. When ON, the leaderboard is ordered by raw index × (1 + adj); the four leaders are unchanged.
  * Badges: “Hot when predicted” / “Keeps missing”.
* **Results:** a manual form (final checkbox; names resolved against the slate roster; unmatched names saved by name with a warning) and an NHL import (`gamecenter/{id}/landing` → `summary.scoring`). `ingest_goal_events` is the hook for the future live ticker.

## Tests
* `conftest.py` blocks every outbound socket, so tests cannot reach the network.
* New: `test_v54_{form_pct,goalies,matchup,probable_goalies,tracker,intel,logo,live_stub,apptest}.py`. The AppTests run the full app on a trimmed real slate (`test_fixtures_v54/slate_trimmed_20261022.json`) with every HTTP call faked from fixtures. They cover:
  * Home with no historical coverage;
  * Home picks == Research picks;
  * the Research goalie section;
  * the Track Record tab;
  * the Matchup Center overview, a card click and back;
  * a game that is not on the slate;
  * starters both confirmed/probable and unknown.

Full suite: 220 tests, all passing offline (a conftest.py guard blocks non-local sockets).

## Unverified / limitations
* ESPN `probables` is an undocumented public feed; field names could change, and the result then degrades to “starter not yet announced”.
* NHL starter flags are only verified for one final game. Live-game behaviour was not observed.
* Track Record learning has no real graded history yet; the screenshots use a labelled demo database (not shipped).
* Streamlit Cloud persistence was not tested: the tracker file is ephemeral there by design.
* The `?matchup=` deep link depends on `st.query_params` support in the deployed Streamlit version.
