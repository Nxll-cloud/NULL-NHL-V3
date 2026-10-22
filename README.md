# NULL NHL V3.1 | Matchup intelligence

Upload all extracted files to the root of your existing GitHub repository and commit to main.

## Added
- Opponent mapping for every ranked player.
- Up to 10 prior *completed* regular-season games for each opponent.
- Defensive goals allowed/game and shots allowed/game, L5 and L10.
- Data coverage/audit table and explicit missing-boxscore warnings.
- Starting goalie explicitly labeled **Unconfirmed**; no goalie adjustment.
- Renames misleading "longshot" watchlist to **statistical sleepers**.

## Method
For each team, retrieve the NHL public API season schedule and select games dated strictly before the chosen slate date with gameState OFF/FINAL. Retrieve each game's boxscore and use the opposing team's goals and shots to calculate allowed rates. Game log availability varies. Failure to retrieve a boxscore is reported, not imputed.

**No betting odds, lineup confirmations, predictive probabilities, or defense-weighted rankings are provided.** The existing descriptive Form Index is unchanged.

## Deployment
Upload the extracted Python files, README, requirements and tests. Streamlit Community Cloud redeploys after the commit. Tap **Rank Entire Slate** and inspect defensive coverage. Large slates may take longer and encounter NHL API rate limits.


## V3.6

Full-slate profile fetch up to 500 ranked players (6 concurrent requests; per-process profile cache (clears on app restart)), date-specific birthday flags, pregame five-game goal-form flags, combined table and filters. Run **Rank Entire Slate**, then **Fetch NHL player biographies and arenas**. Long initial fetches may take time. Download the combined CSV. No automatic claims about injuries, former-team matchups, or milestones; those require verified historical evidence. Numerical overlap is descriptive, not predictive.


See V382_NOTES.md for the V3.8.2 diagnostics update.
