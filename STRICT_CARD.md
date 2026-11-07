# Strict three-game strategy (Prediction Models)

Separate from Home's four-leg card and Model/NP/Blend/Books rankings. This is **not** a full automated Nyah/PropFinder model.

## Selection and quotes

`strict_card_v60.build(day, candidates, ctx, data, now=None, rule=None)` accepts an externally supplied player pool (not hardwired to a leaderboard/top 10). Candidate dictionaries use the existing `parlay_v58.candidates` shape: NHL `pid`, `game_id`, `team`, `opp`, `home`, UTC `start`, `phase='pregame'`, `name`, model `p` in (0,1). It reuses `parlay_v58.choose(..., 3, per='game_id')`; it never calls the legacy relaxing `build`. No three games = no card. Research can supply its own filtered candidate list to this same guard.

`ctx` is the app's existing `situational_v58` context. An eligible listed opposing starter must be confirmed or probable, matched by team/ID (or the existing unique team/name match), with **GP ≥5, SA ≥150**, and `goalie_mult_from(Saves, SA)[0] ≥1.05`. Existing formula shrinks SV% with 600 shots toward .896 and bounds the multiplier. `rule` can configure the floors/cutoff for a separate experiment; defaults and rule are saved. This **operational strategy rule is not validated performance**. The separate H2H weak-spot marker needs different data; it is not silently replicated or fetched here. Unknown starters, missing samples and team averages cannot qualify.

`data` is already-loaded `odds_scorers_v59.load` output. Only non-demo The Odds API/ESPN provider prices, matching player ID + team + matchup, fetched within two hours and before start, qualify. Offered American/decimal price, market, book, source, provider update time if available, and retrieval time are frozen. Consensus/no-vig values are **not** used as prices. Quote suggestions are not wagers.

The session locks its first qualifying pregame card. Late sessions use a saved public freeze or show no qualifying card; there is no results-based rebuild. A new workflow freeze never overwrites an earlier session's quote. Public records also reject re-selection/refreeze.

## Private money logging

Open **Private odds, stakes & profit/loss ledger**. Select whole card OR an individual single. Leave stake blank for unknown, enter zero if appropriate, or enter your actual stake. Actual odds can differ from the quote. Marking a record placed requires entered stake, American odds and book. Saving a card does not create singles or double-count their exposure; separately tracked singles need separate entries. Entries lock once and cannot be overwritten.

Without an entered whole-card quote, combined payout is only a leg-product **paper estimate**, especially when books differ. Neither same-book nor mixed-book multiplication is advertised as executable card odds. Missing stake = unknown P&L. Won/lost/pending/void/push are distinct; void/push legs are removed from estimated products, all void = refund. An actual whole-card quote with voided legs needs the bookmaker's repriced quote, not invented repricing.

Calculated strategy P&L is not called realized. After verified final results, use **Confirm bookmaker settlement** to record each leg's actual disposition (including DNP voids/pushes), add a note and optionally the bookmaker's post-void card price. Confirmation locks once; the original calculation and quote are retained. Realized P&L is shown only for user-reported placed entries with an explicit bookmaker confirmation. No betting action occurs.

There is **no suitable private persistent backend in this app**. Financial entries stay only in `st.session_state`, never public workflow files, another session or GitHub. Download your private JSON and restore it on a later session. Restart/reload/session loss can lose undownloaded entries. Imported data/settlements are user-reported, not independently authenticated. `private_ledgers/` and downloaded private-ledger names are ignored by git.

## Public tracking and grading

The existing accuracy freeze passes its already-fetched context/candidates to `capture_inputs`; after the existing books freeze, the workflow calls `strict_card_v60.update`. No extra HTTP/API/paid-quota calls. Public workflow pricing is limited to the existing books snapshot's top-10 quoted pool; the live board can use its larger already-loaded quote pool. Different frozen source/timing may produce different card IDs. No stakes/actual bets are saved publicly.

Public data: `snapshots/strict_card_inputs/DAY.json` (pregame inputs, compact/shared evidence), `snapshots/strict_cards/DAY.json` (immutable suggestion + eventual results). Results use existing score/PBP/boxscore fetches only: `strict_games` adds validated final per-game evidence without changing accuracy math. Game goal counts must reconcile with non-shootout score, including OT. Live goals never settle a leg. The new strategy counts OT goals, unlike Home's existing regulation-only card. A final no-goal strategy result is not proof of a bookmaker's participation/DNP rules.

Environment note: pregame heuristic selects the highest sum of each team's best eligible model chance among games with two qualifying weak starters; grade ≥7 non-shootout goals. Not a PropFinder L5/L10 environment model. Fade: strongest sampled goalie (multiplier ≤.95), team ≤2 goals. Starter dependency: compare frozen goalie NHL ID with actual NHL starter flag when already-fetched boxscore contains it. Missing criteria, unavailable/inconsistent final evidence or absent starter flags stay **unknown**, not a manufactured hit. Results and graded notes never rewrite the frozen selection/quotes.
