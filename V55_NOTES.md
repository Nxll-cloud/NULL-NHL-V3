# Null’s Playbook V5.5

One release combining three pieces of work (the interim "V5.4.1" naming is dropped):
**(A) EdgeLab**, **(B) GitHub-upload safety**, **(C) the approved neon-arena redesign**.
Scoring semantics are unchanged: rankings, Form %, the four leaders, goalie stats, tracker grading and odds
logic produce exactly what V5.4 produced. All 220 V5.4 tests still pass unmodified (two text helpers were
extended to also read `st.html` output).

## (A) EdgeLab tab — `edgelab_v55.py`
Seventh top-level tab `🧪 EdgeLab`, ported from the pasted standalone Streamlit prototype.
* Controls: Bankroll (500–50,000, default 2,500, step 100), Min Edge % (1.0–12.0, default 4.0, step 0.5).
* Sub-tabs **Games / Props / Scorecard (n)**. Cards show Edge and Stake metrics plus the
  `book · odds · model %` caption and a **Stamp** button; the scorecard lists stamps newest first.
* Demo games/props are the prototype’s rows, badged **“DEMO DATA — not live prices”**.
* Math (pure functions, tested against a verbatim reference of the prototype):
  implied = 100/(o+100) for o>0, |o|/(|o|+100) otherwise · b = o/100 or 100/|o| ·
  Kelly k = (b·p − (1−p))/b · stake = ¼·k·bankroll clipped to [0, bankroll], rounded half-up to cents ·
  edge = (p − implied)·100, kept when edge ≥ Min Edge, sorted descending.
* **Real prices:** on Props you can pick any validated price already loaded on the Odds tab (API or CSV) and
  type *your own* probability. EdgeLab never invents a probability, and Form % is never used as one.
* Optional persistence: toggle *Save stamps to the local tracker database* (SQLite `data/edgelab.sqlite`,
  table `edgelab_stamps`, next to the tracker DB; a fresh connection per operation). Turning it on
  mid-session also saves the stamps you already made. **Export CSV** and **Clear all** on the scorecard.
* Footer: “Mobile research prototype. Not betting advice.” No `set_page_config`, no global CSS of its own;
  every session key starts with `edgelab_`.

### Bugs fixed vs the pasted prototype (each has a test in `test_edgelab_v55.py`)
| Prototype | V5.5 |
|---|---|
| Odds in (−100, 100), 0, NaN accepted (division by zero / nonsense implied %) | rejected with a clear message; row listed as skipped |
| p ≤ 0, p ≥ 1, NaN accepted | rejected |
| `stamped_at` server-local (UTC on Streamlit Cloud) | Eastern Time ISO + “Oct 22, 9:30 PM ET” label |
| Same bet could be stamped repeatedly | one stamp per bet key; button shows “✓ Stamped”; Remove + Clear all |
| Widget keys from list index (collide/shift when the filter changes) | stable keys from kind + game/player + pick + book |
| Edge sign could be lost in formatting | signed edge everywhere (`+3.79%` / `−2.10%`) |
| Stake could exceed bankroll / go negative with odd inputs | clipped to [0, bankroll] |
| Mixed `round()` (banker’s) and f-strings | one half-up rounding helper |

### Differences from the pasted code (intentional)
* Runs inside the Playbook (no `set_page_config`, no page CSS); styled with V5.5 components.
* Odds display shows `+145` instead of `145`; captions add the implied %.
* Adds: real-price scoring with user probability, CSV export, optional SQLite, Clear all, skipped-row notes,
  “closest bets” empty state when nothing clears the threshold.
* Demo rows unchanged (team codes added only for colours).

## (B) GitHub-upload safety
* Zip has files at the top level, no wrapper folder, no nested zips, no data/sqlite/videos/caches/secrets.
* `check_repo_size.py`: walks the repo respecting `.gitignore`, prints the top 15 files, warns > 50 MB, exits 1
  on any file > 95 MB. Runs in the workflow before the snapshot commit; `tools/pre-commit.sample` for local use.
* `.gitignore`: venv/.venv/env, `__pycache__`, `.pytest_cache`, `*.zip`, `data/`, `*.sqlite*`,
  `snapshots/*.json` (+ `!snapshots/.gitkeep`), `.streamlit/secrets.toml`, logs, `*.mp4`, `*.gif`, `playbook_screens/`.
  The workflow now uses `git add -f -A snapshots/`.
* `snapshot_store.prune_snapshots(keep_days=60)` + `python snapshot_store.py prune [--keep-days N] [--dry-run]`:
  only `YYYY-MM-DD.json` files older than N days are deleted; documented, run by the workflow.
* Track Record: per-month JSON export (`trk.export_month_json`, *Month to export*); importable with the
  existing Import. Nothing is deleted.
* App works with no snapshots and no data directory (AppTest with every request failing).
* `GITHUB_UPLOAD.md`: unzip → git / GitHub Desktop, what not to commit, size checks, `du` / `git rev-list`,
  `git filter-repo`, LFS only for intentional datasets.

## (C) Redesign — `v55_ui.py`, `v55_state.py`, `assets/v55*.css`, `assets/v55.js`, `assets/fonts/`
* **Home** is one designed fragment, `st.html(render_home(state), unsafe_allow_javascript=True)`, bound to live
  data built by `v55_state.build_state`: hero for the statistical leader’s game (real start-time countdown,
  live/final from the NHL status), goalie duel (confirmed/probable only when the feeds say so), tonight’s board
  with starter dots, the four leaders + Player Intelligence row (`np-intel-row`), Track Record rings from the
  real store (empty rings + “No graded slates yet” when there is nothing graded), featured matchup targets with
  last-10 sparklines (data-URI `<img>`; “Game log unavailable” when the feed fails).
* **Matchup Center** uses the same scoreboard and a versus hero; its native flow, buttons and keys are unchanged.
* Odds, Research, Numbers, Track Record and EdgeLab get the same tab hero; native widgets (tabs, buttons,
  metrics, inputs, sliders, expanders, alerts, dataframes) are reskinned by CSS only.
* Fonts: Barlow Condensed + Inter as local woff2 (OFL licences included); the Google Fonts `@import` was removed.
* Themes: **Night / Light / High contrast** via a native control next to the date.
* Motion: count-ups, ring fill, reveal (with a 1.5 s fallback so nothing stays hidden), 30 s countdown tick,
  live pulse. No fake HTML tabs and no clickable fake tiles — navigation is native `st.tabs` only.
* Version guard: `v55_ui.html_mode()` → `js` (Streamlit ≥ 1.52, `st.html(..., unsafe_allow_javascript=True)`),
  `static` (older `st.html`, no script) or `markdown` (no `st.html`). Tested for every path.

### Known limitations
* The global design CSS is ~184 KB per rerun because fonts are inlined as data URIs (no external requests).
* `.streamlit/config.toml` stays dark-based, so dataframes and charts remain dark in the Light theme.
* `st.html` sanitises markup: no inline `<svg>` (sparklines are images, rings are CSS conic gradients).

### Differences from the approved preview
* Preview tabs / theme button / clickable tiles were HTML; V5.5 uses native tabs and a native theme control,
  and tiles are not clickable (open a game from Matchup Center).
* Preview numbers were a frozen data extract; V5.5 binds to the live slate, store and feeds, with designed
  empty states (no odds leader → “No validated price yet”, no graded slates → empty rings, missing logs).
* No “PREVIEW” chip; DEMO chips appear only when demo rows exist in the tracker.
* The preview mp4/gif are not shipped.
