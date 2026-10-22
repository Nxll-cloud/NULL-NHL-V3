# Null’s Playbook V5.4

V5.4 adds the **Matchup Center** tab, a **Track Record** tab (prediction tracker), a **Goalies: Goals Allowed** section in Research, **probable starting goalies**, a Home **featured intel row** (the same four picks as Research), the brand logo, and **Form %** (0–100 %) everywhere scores are shown. See `V54_NOTES.md` (and `V53_NOTES.md` for the redesign).

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
