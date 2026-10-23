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

## Not pushed
Nothing was pushed to GitHub. Odds keys stay in Streamlit secrets.
