# Null’s Playbook V4.2 — Mobile + automatic full slate

- One date picker shared across Home and Research; date changes trigger a new full-slate ranking.
- Automatically loads every scheduled team and ranks eligible players; no Rank Entire Slate button needed.
- Runs three previous seasons of opponent history for all ranked players automatically, with retrieval errors and coverage visible.
- Refreshes the open app every 30 minutes via streamlit-autorefresh; team/schedule/defense caches expire after 30 minutes. Historical API results cache for 6 hours and are re-used rather than re-downloaded unnecessarily.
- Manual Refresh now button clears caches and retries.
- Mobile polish: smaller hero and metrics, compact portrait cards with team logos, horizontally scrolling matchup cards, sticky tabs, collapsed sidebar.
- Rankings remain descriptive form indexes, not calibrated goal probabilities. No background job is created when app is closed.
- Historical date analysis is not guaranteed to reproduce exact as-of-date rosters or archived odds. Never treat a newly generated snapshot as an original pregame prediction.
