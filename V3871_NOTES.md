# V3.8.7.1 — Ranking integrity fix

- Assign unique 1-based statistical ranks immediately after adjusted form sorting.
- Preserve ranks through biography, storyline, current-season, and multi-season joins.
- Reject missing or duplicated ranks instead of silently labeling everyone rank N.
- Rerun Streamlit after multi-season fetch to refresh the four cards above the fetch button.
- Distinguish missing or insufficient historical evidence from zero observed goals.
- Existing statistical weights and experimental numerology remain unchanged.

**Workflow:** Rank Entire Slate → Fetch multi-season opponent history → review four cards. The 500-player option covers up to the full eligible slate; NHL API requests can take time.
