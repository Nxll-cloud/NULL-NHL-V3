# Changelog

Newest first. Model details: [MODEL_CARD.md](MODEL_CARD.md). Older release notes: [docs/notes/](docs/notes/).

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
