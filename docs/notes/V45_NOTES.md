# Null’s Playbook V4.5 — Odds API + CSV

Preserves V4.4 GitHub Actions NHL slate precomputation, three-season history, and Streamlit mobile layout. Adds an optional **The Odds API v4** adapter for event-specific NHL player props and a source switch for API, CSV, or combined odds.

## Setup
1. Obtain your own The Odds API key and confirm NHL player-prop market coverage for your plan and region.
2. Streamlit Cloud → App settings → Secrets: `ODDS_API_KEY = "your_key_here"`. Do not commit keys to GitHub.
3. Open the Odds tab. Select region and provider market keys; default `player_goal_scorer_anytime` is subject to actual provider support. Compare API quotes or upload CSV.
4. Provider calls are cached for 30 minutes per API key/region/market configuration while the page is open. They are **not** scheduled by GitHub Actions. Scheduled NHL statistical snapshots remain independent.

## Important
- Coverage is limited to sportsbooks/markets actually supplied by the provider; no promise of all books, Circa, or all goal-scorer markets.
- CSV remains available without an API key.
- Same event ID, player, market, selection, and line are required for comparison. Unknown event IDs use team as a fallback, so include real event IDs in CSV.
- Odds timestamps and source must be checked; odds may change before placing a bet. A price discrepancy is not an EV guarantee.
- Initial API fetch may take time because event-level props require multiple calls; provider quotas apply.
