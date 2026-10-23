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

## GitHub status
- V5.8 (with arena names and the date & arena match table) is on GitHub main, and the `V5.8` tag points to that commit. The earlier V5.8 commit was 0f91d5f.
- Odds keys stay in Streamlit secrets.
