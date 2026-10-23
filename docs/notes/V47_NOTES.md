# Null's Playbook V4.7 — Premium Research + Identity Safeguards

- Premium compact Research cards with player headshots, goal-scoring form score, last-five shots, opponent goals, storyline flags, and collapsible detailed analysis.
- Source URL lists removed from the main Research cards. Source fields remain in underlying data and exports.
- Form Index relabeled Goal-Scoring Form Score in the visual cards; relative score, not a scoring probability.
- Duplicate NHL player names no longer receive an arbitrary model rank when joining sportsbook odds to NHL rankings.
- Name-only odds are explicitly marked unverified because The Odds API player-prop response does not supply a unique player ID in the existing adapter. Ambiguous same-name players are flagged separately.
- Filter by top 25, top 50, top 100, or all statistical ranks; filter flagged collisions; compact sportsbook quote timestamps.
- V4.4 snapshot workflow, 30-minute schedule, 3-season history, and V4.5 API + CSV preserved.
- No verified identity status is claimed until an authoritative cross-provider player mapping is available.
- The provider's terms and any required attribution still apply; technical data remains in source/export for auditing.
