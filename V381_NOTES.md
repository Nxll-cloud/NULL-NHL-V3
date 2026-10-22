# V3.8.1 data integrity patch
- Preserves previously fetched biography and history batches for the selected slate within Streamlit session state, merging by Player ID.
- Adds full-player export separate from the top-10 shortlist.
- Adds audit metrics and CSV for eligible players, fetched profiles/history, populated fields, and storyline flags.
- Streamlit session state is not permanent storage and can reset after server restart.
- No new predictive claims; no independently verified lineup, news, or former-team inference.
- Re-run Rank Entire Slate and fetch profiles/history after deployment.
