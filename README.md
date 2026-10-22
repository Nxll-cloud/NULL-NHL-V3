# NULL NHL V3 | Data-validation upgrade

This package replaces `app.py` and `nhl_data.py` and preserves the existing schedule and player explorer.

## New validation
- Reject malformed game dates, game IDs, negative goals/shots and goals exceeding shots.
- Deduplicate games by game ID.
- Exclude games on or after the selected date.
- Display per-player data-quality flags and coverage counts.
- Clearly disclose that current rosters are **not** historical rosters.
- No goal-scoring probability or backtest accuracy claims.

## Install
Upload the four extracted files into the **root** of your existing GitHub repository,
overwriting matching files, then commit. Streamlit Community Cloud should redeploy.

## Limitations
This is a data-quality improvement, not an independent proof of completion
or historical roster membership. NHL endpoints and field names may change.
A reliable backtest needs historical roster/lineup snapshots and pregame data archives.
