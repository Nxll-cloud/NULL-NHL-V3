# NULL NHL V3.8.3 — Opponent-code diagnostics

Updates `storyline_v38.py` with opponent abbreviation normalization and raw-opponent diagnostics. `app.py` includes the new fields in the downloadable opponent-history diagnostics CSV. It does **not** assert that zero opponent matches is a bug: a team may simply not have played the upcoming opponent yet this season. NHL aliases (e.g. ARI/UTA) require special historical care.

## Validate
Run `python -m pytest -q` locally, deploy all files to main, rerun Rank Entire Slate and Fetch opponent history, then download the opponent-history diagnostics CSV. Inspect `Raw opponent samples`, `Opponent normalized`, and `Rows missing opponent code` before drawing conclusions.
