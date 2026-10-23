# Null's Playbook V5.8 (mobile, Home additions, slate fix)

V5.8 is V5.7 tuned for phones, plus the requested Home/Numbers/EdgeLab/Storylines changes. The desktop layout (1024px and wider), the theme, the logo, the data and the models are unchanged unless a section below says so.

## SLATE FAILURE (fixed)
- **What failed:** the GitHub Action "Precompute NHL slate" failed at the step "Repo size check".
- **Why:** the 05:18Z run committed `snapshots/2026-10-23.json`, which is 105.5 KB. `check_repo_size.py` counts every tracked file against the 100 KB code limit, so every run after that failed before it could commit. The snapshot froze at 05:18Z, and the 10-24 slate (~674 KB) was never written.
- **Fix:** `check_repo_size.py` now checks dated slate snapshots (`snapshots/YYYY-MM-DD.json`) against their own cap (`--max-snapshot-kb`, default 5120 KB). Every other file still must be under 100 KB.
- **Also hardened:** on small slates the parlay falls back to 3 or 2 legs, and says so.
- **Affects:** V5.6 (GitHub main 9576b7f) and V5.7, which have the identical file.
- **Repair on main:** replace `check_repo_size.py` with this one, then re-run the workflow.
- **Tests:** `test_v58_slate.py`.

## Mobile
- `assets/mobile.css` holds only `@media` rules and no angle brackets. It is loaded after the theme by `v55_ui.design_css`, as is `assets/v58.css`.
- **Layout:** columns stack; the Featured matchup grid is one column on phones. Tables scroll inside their wrappers, and the tab bar scrolls sideways.
- **Sizes:** body text is at least 13px. Tabs, buttons, inputs, selects, number inputs, segmented controls and expanders are at least 44px tall.
- **Effects:** blur is off on phones, glow is reduced and animations are minimal. `prefers-reduced-motion` is honoured.
- **Sidebar:** the sidebar is min(86vw, 320px) wide, and the logo is capped at 34px.

## Track Record: hidden behind a flag
- The tab and all its UI are hidden by default. The data, tracker DB and logic are untouched.
- **Re-enable:** set `FEATURE_TRACK_RECORD = "true"` in Streamlit secrets, or set the env var `FEATURE_TRACK_RECORD=1`. Accepted values are 1/true/on/yes.
- **Code:** `feature_flags_v58.py`. Tests are in `test_v58_features.py`.

## Home
- **Tonight's board:** sits above the Featured hero.
- **Top four-leg parlay:** sits directly below the hero. It shows no prices, odds or edge.
  - Legs are one per game, falling back to one per team, then to 3 or 2 legs with a note.
  - The combined chance is the product of the leg chances, with a note that it assumes independence.
- **Top long shot candidate:** sits under Leaders & intelligence.
  - Band: model chance of 6–20% and below the slate's top quartile.
  - It needs an upside signal and is never a parlay leg.

## Scorer badges
- Players who already scored tonight get a badge (icon + text, so it is color-blind safe) in Home, Matchup Center, Numbers and EdgeLab.
- Players are matched by id, with a name fallback. Replayed feeds are labelled DEMO.

## Numbers
- The layout is redesigned; values and logic are unchanged.
- Each team gets **★ TOP PICK**: a filled gold badge, accent border and bold name.
- Each team also gets **☆ RUNNER-UP**: an outlined, smaller badge with no glow and a semi-bold name. Teams with a single player get none.
- Both are pinned first in each team, unless a sort control is active (then they are only highlighted).
- Code: `numbers_v58_ui.top_picks_per_team(n=2)`.

## Home: daily accuracy snapshot
- **What:** a compact card under the Top long shot (above Leaders/Matchups; nothing above Tonight's Board, Featured or the parlay moved). It shows yesterday's (Eastern) real goal scorers next to what the model said for them *before* the games: model chance (V5.6 prior, 1 - exp(-lambda_game)), slate rank, and Parlay ✓. The summary line reads e.g. `Oct 22 · 22 scorers · model top-10 hit 4/10 · parlay 2/4 legs`. A mini trend row covers the last 10 scored nights: pooled top-10 hit rate, a sparkline, and the scorers' average model chance vs the slate average and the realised scorer rate.
- **Point-in-time only:** predictions come only from a saved slate snapshot stamped *before the first puck drop* (`updated_at < first start`). Nothing is recomputed after the fact. The precompute workflow keeps rewriting the day's snapshot after puck drop, so the frozen copy lives in `snapshots/accuracy/YYYY-MM-DD.json` and is never rewritten once the slate has started. The parlay is rebuilt with `parlay_v58` from that pre-game slate and is labelled "parlay rebuilt from the saved pre-game slate".
- **Results:** come from the real NHL API (`/v1/score/DATE`, with play-by-play as a fallback when the goal list is short) and are matched by player ID. Shootout goals are excluded. A slate is scored only when every game is OFF/FINAL. No demo data is used.
- **Fallbacks:** if yesterday has no saved pre-game snapshot, the card says "No saved pre-game predictions for <date>." and shows the most recent completed slate (within 7 days), labelled as such. If the log file is missing, the card computes on the fly from a pre-game snapshot plus the NHL feed (15-minute cache).
- **Edge Flags:** no opening prices are saved, so the Flag column is hidden and the card says "flag n/a (no saved prices)". If a future snapshot carries `openers` ({player_id: American price}), flags are recorded at freeze time (model minus implied >= edgeflags MIN_EDGE) and the column appears.
- **Accumulation:** `.github/workflows/precompute.yml` runs `python accuracy_v58.py update` after the slate calc and before the size check. It is non-blocking, and the existing `git add -f -A snapshots/` commits it. Each night is about 4 KB (compacted after scoring), well under the 100 KB per-file limit. `python accuracy_v58.py backfill` replays every dated snapshot in git history; `show` prints the current view.
- **Status at build (Oct 23):** the only saved slate snapshot is 2026-10-23 (frozen pre-game from 082374e, 08:59Z, 76 skaters, 4-leg parlay; pending until final). There is no Oct 22 snapshot in the repo or its history, so the card currently reads "No saved pre-game predictions for Oct 22." The first scored night appears on Oct 24.
- **Files:** `accuracy_v58.py`; a one-line hook in `tabs/home.py`; `precompute.yml`; `snapshots/accuracy/`; `test_v58_accuracy.py`; `test_fixtures_v58/score_20261022_trimmed.json` (real Oct 22 finals for the 3 games in the trimmed Oct 22 fixture).

## EdgeLab (read-only)
- **Kept:** a read-only table comparing the same next-goal model the Edge Flags tab uses against the current live anytime-goal prices (averaged across books). It shows the model chance, the implied chance, the edge, the book count, the update time and live/settled state; it also shows scorer badges.
- **Removed:**
  - DEMO prices
  - manual probability or odds entry
  - bankroll, stake, Kelly and threshold controls
  - moneylines
- Players who already scored, and final or shootout games, are left out.
- Code: `edgelab_v58.py`.

## Storylines tab
- Real NHL/ESPN data, covering revenge games, former teams, birthdays, first games, hometowns, VS opponent, streaks/milestones and news (last 36h).
- Nothing is fabricated. Topics with no data source (e.g. new dads) are not shown.

## Arena names on slate displays
- Each game shows its arena as a small muted 📍 line next to the matchup. The name comes from the real NHL API `venue.default` (schedule and score endpoints) and is carried through the slate rows and the saved snapshots (`Venue`).
- Where it appears:
  - Home: Tonight's Board tiles, the Featured matchup banner, the Matchup targets heading, the live next-goal strip, the Top four-leg parlay legs, the Top long shot, and the "Player targets by matchup" expanders.
  - Numbers: the game board headers (arena chip with its number) and the Games and Player Targets views.
  - Matchup Center: the game picker, the header banner, the per-game "Goalies vs tonight's threats" headings and the Live Next Goal panel.
  - Live Next Goal panels, Edge Flags game cards (display only, the logic is unchanged) and the Research slate cards.
- If a game has no venue (e.g. an older snapshot), the score endpoint's real arena is used. If neither has one, the line is hidden. It never shows "None" and the app never guesses an arena. The DEMO replay panel shows no arena.
- Mobile (320–430px): the line stays on one line, cuts off with an ellipsis (the full name is in the tooltip) and uses 13px text. On desktop the layout is unchanged.
- Code: `venue_v58.py` (`clean`, `of`, `fill`, `label`, `tag`). Tests: `test_v58_venue.py`.

## Numbers: date & arena match table
- Near the top of the Numbers page there is a compact table with exactly three columns: **Player | Match type | Number**.
- Match type is only ever `date` (the player's name number equals tonight's universal day number) or `arena` (it equals the arena number of the player's game). The code filters and asserts this.
- A player who matches both gets two rows. Number is the matched value: the day number for `date`, and the arena's root in the first matching cipher (English, then Reduction, then Reverse) for `arena`.
- It uses the same three ciphers as the rest of the page. The arena number comes only from the real NHL venue name. Games without a venue get no arena rows, and a small note under the table lists them.
- Empty states: "No player matches tonight's date or arena numbers", or a note that the table appears once the slate rankings are loaded.
- The table scrolls vertically (max 420px) and never horizontally. Text is 13px on phones. Scored-tonight badges still appear next to player names.
- Entertainment only, not a scoring signal. Code: `gem_match_v58.py`. Tests: `test_v58_gem_match.py`.
- Calculation line: under every row a muted subtitle line shows the player's reduced digit for each cipher and the target, e.g. `Eng 2 · Red 2 · Rev 7 ✓ → day 7` for a date row, or `Eng 3=3 ✓ · Red 3=3 ✓ · Rev 6=6 ✓ → United Center` for an arena row (compared like for like). ✓ marks the cipher(s) that hit. Hovering the line on desktop shows the raw totals before reduction (e.g. `Eng 96→6`). The line is built from the same per-cipher values that decide the match (`player_matches`), so it can't disagree with the table. It's never a column: there are still exactly three, and match type stays `date`/`arena`.
- REV tag: a small outlined violet `REV` pill next to the player name marks rows that matched only through the Reverse cipher (tooltip "Matched through Reverse cipher only"). Note: English and Reduction roots are always equal, and English + Reverse totals are a multiple of 9, so an arena row can never be Reverse-only. In practice only date rows get the tag.

## Next-goal model: situational layer (V5.8)
- Code: `situational_v58.py`, hooked into `live_nextgoal_v56.model(..., situ=...)`. Tests: `test_v58_situational.py`.
- Baseline is unchanged: prior shots/game (5 ghost games) × shrunk sh% `(G + 50×0.10)/(SOG + 50)` = base λ.
- Layers on top (each bounded, logged per player in `rec['situ']`, switchable):
  - **PP**: base λ is split into EV + PP. EV = (prior SOG/g − season PP SOG/g, floor 25%) × EV sh% shrunk 50 shots to 9.17%. PP = PP shots per PP minute (shrunk with 20 ghost minutes at the league 10.42/60) × PP TOI/game × tonight's PP-opportunity factor (team PP opps × opponent times shorthanded vs league, 10 ghost games, clamp 0.75–1.30) × PP sh% shrunk 50 shots to 14.8%. EV and PP targets are anchored so the league mix still converts at 10%.
  - **Goalie**: opponent goalie SV% shrunk 600 shots to .896; mult = (1 − SV)/(1 − .896), clamp 0.85–1.15. Order: live in-net goalie (PBP) → confirmed/probable starter (same `starters_cached` source as Matchup Center) → SA-weighted team average → neutral.
  - **Line/TOI**: EV TOI per game last 14 days vs season (3 ghost games), elasticity 0.5, clamp 0.90–1.10. A deployment proxy, not linemate identity.
  - final = (EV + PP + (line − 1)×EV) × goalie; ratio final/base clamped 0.5–2.0. Live rate is scaled by the same ratio.
- No data → ratio exactly 1.0 → the V5.6 numbers exactly. Flag `MODEL_SITUATIONAL` (env > secrets, default on) turns it off; `MODEL_SITUATIONAL_PARTS` picks layers (`pp,goalie,line`).
- Data: NHL stats API (skater summary/powerplay/timeonice, team powerplay/penaltykill, goalie summary), games before the slate date, cached 3 h; a failed report leaves its layer neutral.
- Downstream (all read `_v56_results`): Edge Flags (model input only), EdgeLab (model-p cell has a "why" tooltip), four-leg parlay, long shot, scored-tonight. Scored players stay settled/excluded. DEMO replay, MC goalie panel and the backtest stay on the V5.6 model.
- Rankings "Starting goalie" now reads the same starter source (e.g. `Spencer Knight (Probable)`; `Unconfirmed` only when no source lists one), and "Goalie adjustment" shows the model's actual SV% step for that row (`sit.goalie_columns`). Form % itself still has no goalie adjustment.
- Gaps: no linemate/line-combo feed (TOI proxy only); live per-player strength is not redistributed (team-level PP/SH multiplier as before); backtest not yet rerun on the new model.

## GitHub status
- V5.8 (with arena names and the date & arena match table) is on GitHub main, and the `V5.8` tag points to that commit. The earlier V5.8 commit was 0f91d5f.
- Odds keys stay in Streamlit secrets.

## Research: hidden below Top 10 Statistical Sleepers
- **Display only:** Research now ends at "Top 10 Statistical Sleepers" (and its CSV button). Everything rendered after it is hidden: Full NHL Slate/Matchup cards, Player Statistics Explorer, V3.2 Goal-Scorer Rankings, V3.3 Historical Backtesting, V3.5 Auto Storyline, Numerology & Gematria, V3.8 Opponent History, the V3.8.2/3.8.4/3.8.5/3.8.6 audits and the V3.8.2 Combined Explorer, plus their captions, buttons, downloads and dividers.
- **Still runs:** the live ranking pipeline (Home's source when no snapshot exists) with its default settings (3 prior games, defense adjustment on), the shared intelligence pipeline and the three-season history job. Nothing was deleted.
- **Re-enable:** set `FEATURE_RESEARCH_EXTRAS = "true"` in Streamlit secrets, or the env var `FEATURE_RESEARCH_EXTRAS=1` (env wins), same as Track Record. Code: `feature_flags_v58.py`; tests: `test_v58_research.py`.
