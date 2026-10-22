# NULL NHL V3

Streamlit NHL slate dashboard using the public NHL API. Displays schedules and player form derived from completed games **strictly before** the selected slate date. No fabricated predictions or odds.

## Deploy

1. Upload `app.py`, `nhl_data.py`, and `requirements.txt` to the repository root.
2. Streamlit Community Cloud: select the repository, `main` branch, and `app.py` as the entry point.
3. In the app, select a slate date and press **Load Player Statistics** for a team.

## Limitations

- The historical roster endpoint returns season roster membership, not guaranteed game-day active lineups. Do not interpret as confirmed lineups.
- Missing player game logs and API failures are reported. A player with no prior games is not a confirmed zero-goal player.
- Date-only cutoff excludes all games on the selected date. The app does not claim point-in-time availability of injury/goalie/odds information.
- No goal-scoring probability model or historical prediction archive is implemented yet.
- GitHub ZIP files are **not** automatically unpacked by GitHub. Unzip on your device and upload the individual files.
