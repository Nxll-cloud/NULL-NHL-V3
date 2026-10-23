<p align="center"><img src="assets/logo_full.webp" alt="Null’s Playbook" width="280"/></p>

# Null’s Playbook V5.7

V5.7 swaps in the owner’s logo (crowned N) for the old shield/Ø mark — favicon, `st.logo`, sidebar, Home hero, tab headers and footers. Nothing else changed. See `V57_NOTES.md`.

## V5.6

V5.6 adds the **⏱ Live Next Goal** model and tab (official NHL play-by-play, competing-risk next-goal %), Matchup Center goalie threats with real shooter-vs-goalie history, per-game numerology boards, **🚩 Edge Flags** against the opening anytime line, and a next-goal **backtest** with a write-once baseline (`python backtest_next_goal.py`, see `BACKTEST_V56.md`). See `V56_NOTES.md`.

## V5.5

V5.5 adds the **🧪 EdgeLab** tab (¼-Kelly edge scanner on demo rows or your own prices + your own probability), **GitHub-upload safety** (`check_repo_size.py`, `.gitignore`, snapshot pruning, per-month Track export, `GITHUB_UPLOAD.md`) and the approved **neon-arena redesign** (designed live Home, Night / Light / High-contrast themes, local fonts). See `V55_NOTES.md`. V5.4 features (Matchup Center, Track Record, goalies, Form %) are unchanged — see `V54_NOTES.md`.

Before pushing to GitHub: `python check_repo_size.py` (see `GITHUB_UPLOAD.md`).

Run: `pip install -r requirements.txt && streamlit run app.py`. Tests: `python -m pytest -q` (offline: `conftest.py` blocks all outbound sockets; fixtures in `test_fixtures_v54/`).

Secrets: `ODDS_API_KEY` (and, in the future, `SGO_API_KEY`) are read only from Streamlit secrets (`.streamlit/secrets.toml` locally, the app's Secrets panel on Streamlit Cloud). Never commit them.

The tracker writes a SQLite file to `data/prediction_tracker_v54.sqlite` (override with `PLAYBOOK_TRACKER_DB`). On Streamlit Community Cloud the filesystem is ephemeral, so use the Track Record tab's **Export JSON** regularly and re-import after a redeploy.

## Future: Live Scoring Ticker

`live_scoring_future.py` is a **scaffold only**. `LIVE_SCORING_ENABLED = False`, and `app.py` does not import or render it. Nothing polls today.

* **Providers** (all `LiveScoreProvider` subclasses whose methods raise `NotImplementedError`):
  1. `NHLOfficialProvider` (primary) — `api-web.nhle.com/v1/score/{day}` for game states and `gamecenter/{id}/landing` → `summary.scoring` for goals. No key.
  2. `ESPNProvider` (fallback) — `site.api.espn.com/.../hockey/nhl/scoreboard` and `summary?event=`. No key. Map ESPN ids to NHL games by teams and start time.
  3. `SportsGameOddsProvider` (optional) — needs `SGO_API_KEY`, read **only** via `st.secrets` (`SportsGameOddsProvider.from_secrets()`); never an env var or a file in the repo.
* **Rate limits / polling lane:** NHL at most every 30 s, ESPN every 45 s, SGO every 60 s (or the plan's limit, whichever is slower). Poll only while a slate game is `LIVE`/`CRIT` (`should_poll`). On 429/5xx use `backoff_delay` (exponential with full jitter, capped at 300 s). One poller per server process, results in `st.cache_data` with a TTL equal to the poll interval, so browser sessions read the cache and never call providers directly.
* **Architecture:** `LivePoller.poll_once(day)` → provider `fetch_slate_states` → for live games `fetch_goal_events` → `dedupe_events` (provider event id, else game/period/time/scorer) → `prediction_tracker_v54.ingest_goal_events(conn, day, events, final=...)`, which also feeds the Track Record grading.
* **UI hooks:** `render_live_ticker(day, leaders)` is meant to sit on Home directly under the hero / stat strip, above the Four Leaders. It should highlight a goal by any of the four leaders (or a tracked pick) with a badge on that leader card. Matchup Center can reuse the same cached state for a per-game score line.
* **Turning it on:** implement the providers, add tests with recorded fixtures (no live calls in tests), then flip the flag and add one guarded `import` in `app.py`.

## Earlier releases

NHL slate analytics with V4.4 scheduled snapshots and mobile dashboard, plus optional sportsbook odds via The Odds API and CSV fallback. See `V44_NOTES.md` and `V45_NOTES.md` for setup.
