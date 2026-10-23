# NULL NHL V3.7 — featured storyline watch

## New
- Featured storyline candidate displayed at the top of the dashboard after rankings load.
- Top 10 supported storyline watchlist and statistical sleeper watchlist.
- Links to NHL player profile/game log evidence where available.
- Existing V3.6 numerology, gematria, explorer, and V3.3 backtesting preserved.

## Selection method
Only V3.6's supported storyline flags (birthday on slate date, or >=0.6 goals/game in the last five based on pre-slate game logs) count. Most supported flags wins; V3.2 adjusted form index breaks ties. Numerology does not influence this ranking. A storyline flag is a documented fact, **not** evidence of a scoring edge. The game-log source URL is constructed from the player's NHL ID; current data retrieval is not independent news verification.

## Limitations
Automated former-team/revenge, milestone, injuries, confirmed lineups and opponent-history narratives are **not yet implemented**. The profile endpoint can reflect current rather than historical metadata. Model scores are descriptive, not calibrated goal probabilities. Test suite is local and does not validate live NHL API connectivity or prediction accuracy.

## Installation
Unzip and upload the contents (not the parent folder) to the root of `Nxll-cloud/NULL-NHL-V3` on GitHub `main`. Commit and wait for Streamlit deployment. Rank Entire Slate, then Fetch NHL player biographies and arenas to add birthday flags. The featured card appears at the top of the page; scroll up after fetching.
