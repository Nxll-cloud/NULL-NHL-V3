# V4.4 — scheduled snapshots and fast opening

- `.github/workflows/precompute.yml` runs every 30 minutes (GitHub Actions schedule is best-effort, not exact) and can be triggered manually with a selected date.
- `precompute_slate.py` computes all players and 3 previous regular seasons, saves `snapshots/YYYY-MM-DD.json` atomically.
- Home and Research read the same validated daily snapshot; live fallback remains for dates without snapshots.
- Streamlit does **not** need write access to the repo; GitHub Actions commits snapshots.
- GitHub Actions **Settings → Actions → General → Workflow permissions** must allow **Read and write permissions** for commits. Branch protections may block commits.
- Run the workflow manually once after deployment to generate today's snapshot. GitHub schedule can be delayed or skipped; use the timestamp to detect stale data.
- Saved snapshots are not pregame snapshots for backtesting unless generated before the games. Avoid historical look-ahead.
- No actual latency benchmark or production deployment has been completed.
