# Null’s Playbook V4.3 — performance and mobile

- Six concurrent team loads and six concurrent defensive summaries instead of sequential calls.
- Three-season history starts in a background executor, not in the page render path.
- Ten-second status polling while the page is open; no background refresh after app shutdown.
- Historical fetch cache extended to 7 days; manual refresh clears it.
- More compact mobile metrics and suppressed overlapping Streamlit toolbar.
- Matchup start times shown in Eastern Time.
- Visible ranking update timestamp.

**Limitations:** NHL API speed, rate limits and Streamlit Cloud resources may affect actual load time. Historical work may be interrupted by instance restarts. No sportsbook feed is connected.
