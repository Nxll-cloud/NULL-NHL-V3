# Changelog

Newest first. Model details: [MODEL_CARD.md](MODEL_CARD.md). Older release notes: [docs/notes/](docs/notes/).

## EdgeLab: anytime-goal engine (tonight's patterns) is now the whole tab (2026-11-22)

* EdgeLab now shows only "Anytime goal · tonight's patterns": the estimated chance each skater still in play
  (unstarted or live) scores 1+ goal tonight. The old EdgeLab view is gone from the page (book price status / price
  gaps card, Model-vs-price table, stat strip, settled-results line and captions). Its modules stay because other
  pages use them (edgelab_prices_v60 → home price gap and odds board; edgelab_v58/v55 → edge flags and price helpers).
  The MoneyPuck xG credit caption moved with the tab.
* Prediction Models no longer shows the engine (the Scorer Patterns section added earlier today is removed there).
* Method: L2 logistic fit (lambda 50) over the last 14 scored nights on 12 pre-game traits plus the app Model's logit,
  so overlapping traits (shots, form, forward, top-50) count once and only what each adds on top of the others is
  weighed. Tonight's scorers so far are the live input: a MAP update shrinks the recent fit toward tonight's
  scorers vs non-scorers in started games (time-weighted), prior strength tau 100 (about 4-5% of the weights tonight),
  needs 3+ scorers. Live games are scaled by minutes left. Tonight's scorers are listed separately with their shared
  traits; finished games are skipped. Live chips (assists, shots, leaky goalie) are context only, not in the %.
* Walk-forward check, 19 saved nights (later games of each night, earlier games as "tonight so far"): log loss 0.3530
  vs 0.3552 for the app Model alone, AUC 0.712 vs 0.706, top-10 hits 59/190 vs 55/190 (old pattern-fit list 48/190).
  A heavy tonight weight (tau 3, ~55%) was worse (log loss 0.3623, AUC 0.684), so it is kept modest. Platt
  re-calibration was tested and rejected (worse log loss). Accurate variants still rank stars high (stars do score
  more); the joint fit removes the double counting but does not add star lean versus the old score.
* Overall accuracy label: "Anytime goal · tonight's patterns (EdgeLab)" (not tracked yet). Display only: no change to
  the model, NP ranks, threat weights or logs.

## Prediction Models: Scorer Patterns replaces the experimental Blend (2026-11-22)

* Retired the EXPERIMENTAL Blend column (model chance × gematria layer hits) from every view: the page column, the
  "which system leads" summary, the night-by-night table and the overall accuracy table. Its own docs said it "adds
  nothing measurable"; over the saved history it hit 106/300 vs the plain Model's 108/300. The nightly record writer
  (snapshots/accuracy_blend/) is kept because those records also carry the rebuilt Model / NP top-10s used for nights
  without a saved accuracy entry. The page no longer computes gematria layers at load.
* New `scorer_patterns_v62` section under the overall accuracy table: learns which pre-game traits were over-represented
  among real scorers over the last 14 scored nights (saved slate snapshots + accuracy results, plus the NHL score feed
  for PP goals / points / assists in the prior 7 days), keeps a trait only with enough sample, lift ≥ 1.2 and a 95%
  Wilson lower bound above the base rate, then lists skaters in unfinished games who fit (Fit 0-100, plus live signals
  from tonight's goals: assists, shots, leaky goalie, PP). Tonight's scorers are left out. Pattern fit, not a
  probability; display only (no effect on the model, NP ranks, threat score weights or logs).
* Overall accuracy: the Blend row is replaced by "Scorer Patterns · pattern fit" (not tracked yet); The List / Nyah
  reference-only row was removed (separate commit).

## Numbers: English-only day match re-applied (2026-10-24)

* Re-applied the day-match rule from fbcef82 at the owner's request: a day match counts only when the player's English
  digit (== Reduction) equals the universal day. A Reverse digit equal to the day is a different English digit (9 − d),
  so counting it doubled the day-match odds (2/9 instead of 1/9) and over-filled the hot tier. `DAY_METHODS` = English;
  the date & arena table never ticks Rev for the date (no REV tag); Player Matches view, legend and captions say so.
* The TOP PICK tie-break from 1a9745d is unchanged (score → model chance → form → shot rate → English total → id).
  Arena and team matching are unchanged.
* Tonight (2026-10-23, universal day 7, all 76 players): day matches 21 → 11, hot tier 21 → 11, blaze 0 → 0, date &
  arena table 30 → 20 rows (date 21 → 11, arena 9 → 9). This equals the gematria history record frozen for 2026-10-23
  (date 11, arena 9); saved history files are not rewritten. New records carry method hash c4a53fff43ea.

## Projected scorers from sportsbook odds (2026-10-23)

- New **Projected scorers (odds)** section (`odds_scorers_v59.py`): anytime-goal prices → implied chance → no-vig chance (fixed 0.86 margin, measured on 4,958 real DraftKings props, because the market only posts "Yes" prices) → consensus (median) across books, best price + book, every book's price. Odds only, no model numbers.
- Sources in order: The Odds API (only with `ODDS_API_KEY`; reuses the Odds tab's cached fetch, no extra credits) → free ESPN DraftKings props (cached 30 min) → empty state. Never demo data. OddsJam is paid/key-gated and not used.
- Placement: very top of the ⚡ Odds tab (everything else unchanged below), and on Home directly above Matchup targets (top 5, same renderer and data). Flag `FEATURE_ODDS_SCORERS` (default on).

## Numbers fixes (2026-10-23)
* Numbers TOP PICK tie-break: the model chance now comes from the next-goal model's player records (`pid` + `lam_game`,
  the same ones Home uses) via `numbers_v58_ui.model_p_from_results`. Before, it was built from ranking rows, came out
  empty (`{'None': 0.0}`), and every tie fell to alphabetical order. It is still only a tie-break inside equal points.
* TOP PICK tie-break order inside equal points is now model chance → form index (`V3.2 Adjusted Index`) → shot rate
  (`Shots/G L5`, L10 fallback) → raw English name total → player id (final deterministic key). Never alphabetical; a value
  missing for a player ranks lowest at that stage (`numbers_v58_ui.pick_order`).
* **Reverted** the English-only day match from fbcef82 at the owner's request: a Reverse digit equal to the universal day
  counts as a day match again (`DAY_METHODS` = English, Reverse; Reverse = 9 − English). The date & arena table's Reverse
  hits, REV tag, Player Matches view and captions are back to the old rule. Tonight (2026-10-23, all 76 players): day
  matches 11 → 21, hot tier 11 → 21. The gematria history record frozen for 2026-10-23 under the narrowed rule is left
  as frozen (method hash c1543e197ec2); later records carry the new method hash.

## Audit Phase 1 (2026-10)
* D1 Defencemen's in-game pace counts missed + blocked attempts, capped (`MODEL_D_ATTEMPTS`, ON; 2026-04-04 log loss
  3.4284 → 3.4157). E2 deferred to the Phase 2 multi-night backtest.
* P1.7 Official basics: this changelog and the model card; release notes moved to `docs/notes/`; prediction hashes and
  model version on frozen entries; Python 3.11 pin + `requirements.lock`; shared footer (21+ / 1-800-GAMBLER, data
  sources, not affiliated with the NHL, not betting advice, model card link); streamlit >= 1.50.
* P1.6 Gematria / Numbers picks separate from model picks (Long Shot: two labelled options; tracker: model-only rates).
* P1.5 Win % V2 behind `MODEL_WINPROB_V2` (default OFF: 2026-04-04 regression 0.6499 → 0.6645).
* P1.4 Shots-share baseline beside every accuracy number.
* P1.3 Power-play double count fixed (`MODEL_PP_COHERENT`, ON; 2026-04-04 log loss 3.4593 → 3.4284).
* P1.2 xG point-in-time gate. P1.1 Full accuracy log with Brier / log loss / reliability.
* Fix: startup crash after in-place Cloud update (stale project modules), 996c99e.

## Earlier releases
| Version | Notes |
|---|---|
| V5.9 (+ xG) | [V59_NOTES](docs/notes/V59_NOTES.md), [V59_XG_NOTES](docs/notes/V59_XG_NOTES.md) |
| V5.8 | [V58_NOTES](docs/notes/V58_NOTES.md) |
| V5.7 | [V57_NOTES](docs/notes/V57_NOTES.md) |
| V5.6 | [V56_NOTES](docs/notes/V56_NOTES.md), [BACKTEST_V56](BACKTEST_V56.md) |
| V5.5 | [V55_NOTES](docs/notes/V55_NOTES.md) |
| V5.4 | [V54_NOTES](docs/notes/V54_NOTES.md) |
| V5.0–V5.3 | [V50](docs/notes/V50_NOTES.md) · [V51](docs/notes/V51_NOTES.md) · [V52](docs/notes/V52_NOTES.md) · [V53](docs/notes/V53_NOTES.md) |
| V4.x | [V4](docs/notes/V4_NOTES.md) · [V41](docs/notes/V41_NOTES.md) · [V42](docs/notes/V42_NOTES.md) · [V421](docs/notes/V421_NOTES.md) · [V43](docs/notes/V43_NOTES.md) · [V44](docs/notes/V44_NOTES.md) · [V45](docs/notes/V45_NOTES.md) · [V46](docs/notes/V46_NOTES.md) · [V47](docs/notes/V47_NOTES.md) · [V48](docs/notes/V48_NOTES.md) · [V49](docs/notes/V49_NOTES.md) |
| V3.x | [V35](docs/notes/V35_NOTES.md) · [V37](docs/notes/V37_NOTES.md) · [V38](docs/notes/V38_NOTES.md) · [V381](docs/notes/V381_NOTES.md) · [V382](docs/notes/V382_NOTES.md) · [V383](docs/notes/V383_NOTES.md) · [V384](docs/notes/V384_NOTES.md) · [V385](docs/notes/V385_NOTES.md) · [V386](docs/notes/V386_NOTES.md) · [V387](docs/notes/V387_NOTES.md) · [V3871](docs/notes/V3871_NOTES.md) · [V388](docs/notes/V388_NOTES.md) |
