# Null's Playbook V5.9 (integration: Research hide, situational model, scored-tonight badges)

V5.9 is V5.8 (tag `V5.8`, dd0ae1c) plus the branches below, merged with normal merges (no rebase). Desktop layout, theme, logo and data sources are unchanged unless a section says so. Longer write-ups for the two merged features live in `V58_NOTES.md` (sections "Next-goal model: situational layer" and "Research: hidden below Top 10 Statistical Sleepers").

## Merged branches
- `research-hide` (c450759): Research shows everything up to and including **Top 10 Statistical Sleepers**; later sections are behind `SHOW_RESEARCH_EXTRAS` (default off; secrets/env override). Display only.
- `model-situational` (617fd91): next-goal / anytime model gets the situational layer (opponent starting goalie SV%, PP TOI, line context), flag `MODEL_SITUATIONAL` (default on) and `MODEL_PARTS`.
- Conflicts and resolutions (both features kept):
  - `feature_flags_v58.py`: both flag families kept (`SHOW_TRACK_RECORD`, `SHOW_RESEARCH_EXTRAS` and `MODEL_SITUATIONAL`/`MODEL_PARTS`) on one shared `_flag` helper.
  - `tabs/research.py`: research-hide gating kept; the V3.2 rankings caption uses the model branch's wording (starting goalie from the Matchup Center probable-starter source; "Unconfirmed" only when no source lists one). Note: that V3.2 rankings section sits below Top 10, so with `SHOW_RESEARCH_EXTRAS` off the fixed "Starting goalie" label is only visible when extras are switched on.
  - `V58_NOTES.md`: auto-merged.
- Not in V5.9 yet: `home-accuracy` (Home daily accuracy card), merged later.

## Scored-tonight badges (display only)
The 🚨 badge (`scorers_tonight_v58`) now appears in every view that still lists players who scored tonight. Explicit badges are matched by player id (name fallback only when the name is unique on the slate) and sit right after the name; the auto-marker never adds a second one.
- **Storylines**: table rows (`storylines_v58.row_html`).
- **Live Next Goal**: top-shooter rows in each live/final game panel (also Matchup Center's next-goal panel).
- **Edge Flags**: the per-game card's top shooter (settled games) and the "All rows" table (`🚨 Tonight` column). Edge Flags logic is unchanged: players who already scored are still never flagged, the badge only marks them where they are listed.
- **Home**: Top four-leg parlay legs and Top long shot (a locked leg that later scores shows the badge next to "✓ Hit").
- **Research**: every Top 10 list gets a `🚨 Tonight` column (by Player ID; the id column itself is not shown).
- Unchanged from V5.8: Home hero/leaders/rankings, Matchup Center, Numbers, EdgeLab. Odds: none (no scorer list there).
- Tests: `test_v59_badges.py`.

## Mobile: Storylines multiselect tap targets
At 320–430px the Storylines "Groups" multiselect's search box was 28px tall and its Clear-all / Open icons 24px and 22px. `assets/mobile.css` (inside the mobile media query) now gives the combobox input, the clear and dropdown buttons and their row at least 44 x 44px. Desktop untouched.

## Version
README header now says V5.9 (the app itself shows no version string).

## Home goalie marker (V5.9)
Home only: goalies get a small outlined, muted **G** pill (`.v55 .npg`, 12px desktop / 13px mobile, `white-space:nowrap`), plus a faint row tint (`.is-g`) on leader cards, target rows, parlay legs and long-shot cards when the row is a goalie.

- **Shared helper:** `position_badge_v59.py`. Call `goalie_badge(position)` to get the pill HTML, or `''` if the player isn't a goalie. `position_of(record)` reads `position` / `Position` / `positionCode` / `pos`, and `goalie_row_class(position)` returns the tint class. When `home-accuracy` is merged, its accuracy card should call `goalie_badge(position_of(row))`.
- **Source of truth:** position data only, never names. Our feeds already sort players by role, so each source records it explicitly:
  - NHL club-stats `goalies[]` → `Position` (uses `positionCode` when present, otherwise 'G')
  - NHL boxscore `goalies` block → `position`
  - ESPN `probableStartingGoalie` → `position` (uses athlete position abbreviation when present)
  - Rankings / leaders / targets use the roster `Position` column.
  If there's no position, no badge is shown.
- **Where it appears:** Tonight's Board starter names, hero goalie duel, hero lead, Leaders cards, Targets rows, matchup goalie cards, parlay legs and long shot. Today the rankings pool has only skaters and the live pool excludes 'G', so in practice the leaders, long shot and parlay never show a goalie. The wiring is there in case that changes.
- Tonight’s Board tiles: the starter (dot + surname + G) now sits on its own line under the team abbreviation, spanning the full tile width on mobile. Before, the surname shared the row with the abbreviation and was illegible at 320px, and adding the pill clipped it. Very long surnames get an ellipsis; the pill is never clipped. A live score stays on the team row.
- Tests: `test_v59_goalie_badge.py`.
