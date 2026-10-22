# NULL NHL V3 | Stage 1 full-slate rankings

Replace the files in the **root** of your existing GitHub repository with the extracted files in this ZIP. Commit to `main`; Streamlit Community Cloud should rebuild.

## New capability
Tap **Rank Entire Slate** to fetch current-season player game logs for every scheduled team and rank eligible skaters by a transparent **descriptive form index**:
- 40 × (last-5 shots/game ÷ 4)
- 25 × (last-10 shots/game ÷ 4)
- 20 × (prior-season-to-date goals/game ÷ 0.5)
- 15 × (last-5 goals/game ÷ 0.5)

Weights and scaling are **arbitrary illustrative choices**, not trained or calibrated. Values may exceed 100. This is **not** a probability or evidence of predictive advantage.

Includes minimum-prior-games filter, CSV download, request-failure warnings, and an exploratory longshot watchlist based on shot volume outside the top 20.

## Known limitations
Current-season roster endpoint may not represent the historical lineup on a past date. Game-log cutoff uses prior game dates but does not independently verify completed-game status. The index excludes opponent defense, starting goalies, injuries, lines, power-play deployment and betting odds. Rankings cannot be used for reliable historical backtests until historical lineup snapshots and pregame data are archived.

Streamlit may take time to load a large slate and API rate limits may apply. No background scheduler is included.
