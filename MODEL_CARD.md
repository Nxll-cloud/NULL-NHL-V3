# Model card: Null's Playbook next-goal model (V5.9 + audit Phase 1)

Single reference for what the app's probabilities are, what feeds them, how they are checked, and their limits.
Version history: [CHANGELOG.md](CHANGELOG.md). Older per-release write-ups: [docs/notes/](docs/notes/).

**Not betting advice.** Every percentage is a model estimate for entertainment and research. 21+. Gambling problem?
Call 1-800-GAMBLER. Not affiliated with or endorsed by the NHL.

## What it predicts
* **Next goal (live):** for each skater in a game, P(he scores the next goal); the remainder is "no further goal".
* **Anytime goal (pregame):** p = 1 - exp(-λ) with λ the skater's per-game goal rate.
* **Win % (Tonight's Board favourite pill):** display only, derived from the same skater rates (see below).
Gematria / Numbers picks are **not** model output (see "Separate lenses").

## Model (live_nextgoal_v56.py + situational_v58.py + xg_v59.py)
* Shot rate: recent shots/game prior shrunk to a positional mean, blended toward tonight's pace as the game runs.
* Conversion: season shooting % shrunk to league 10% (K = 50 shots), blended with in-game shot xG.
* Team rate × situation multiplier (PP / SH / empty net / 3-on-3 OT); competing-risk next goal over remaining time.
* Situational layer (`MODEL_SITUATIONAL`, default ON): opposing goalie SV%, PP time-on-ice split, TOI deployment,
  MoneyPuck shot quality (`MODEL_XG`, ON; point-in-time gated, see below). Each part is bounded.
* Constants are documented priors, not fitted. Probabilities are not separately calibrated.

## Audit Phase 1 fixes
| Item | Change | Flag / default | Evidence |
|---|---|---|---|
| P1.1 | Accuracy log keeps every priced skater; Brier, log loss and a reliability table | always on | tests |
| P1.2 | xG point-in-time gate: a MoneyPuck file is used for a slate only if modified before first puck drop | always on | boundary tests |
| P1.3 | **Power-play double count fixed**: before, a live PP was priced twice (the player's PP split *and* the team PP multiplier) and PP shots also got PP xG. Now the player PP split applies pregame only, live uses one team-neutral PP share, and PP shots are valued at EV xG | `MODEL_PP_COHERENT` ON | 2026-04-04 next-goal log loss 3.4593 → 3.4284 (shots-share 3.4343); `backtests/audit_pp_2026-04-04.json` |
| P1.4 | **Shots-share baseline**: a naive "share of team shots" model is shown next to every accuracy number. Pass rule: model log loss ≤ baseline log loss (tracker: Stats hit rate ≥ baseline top-N by shots/game). Comparison line only, never a pick | always on | Home accuracy card, Track Record |
| P1.5 | **Win % V2** (`MODEL_WINPROB_V2`): 18 dressed skaters (roster/lineup, else top 12 F + 6 D by TOI), 50/50 blend with shrunk team GF/GA (NHL team/summary), home ice ×1.037, real regulation-tie rate 22.05% and OT/SO home 52.5% (NHL 2023-24..2025-26, 3,936 games), range in the tooltip | **OFF** | 2026-04-04 log loss 0.6499 → 0.6645 (regression ⇒ OFF by rule); 8 slates 0.6955 → 0.6755; `backtests/audit_winprob_*.json` |
| P1.6 | Gematria / Numbers kept apart from model picks (two labelled long-shot options; tracker model-only vs Numbers rates) | always on | tests |

## Separate lenses (not the model)
Gematria / numerology and storylines are a "Numbers" lens. They never change a model probability, never enter a model
hit rate, the learning prior, the leaderboard or badges. Long Shot shows a **Model pick** and a separately labelled
**Gematria / Numbers pick**. The Track Record reports **Model (Stats + Odds)** and **Numbers (Numbers + Overlap)** apart.

## Evaluation
* `python backtest_next_goal.py --date YYYY-MM-DD [--situ --pp-coherent on|off]`: replays official play-by-play.
  `backtests/baseline_v56.json` is write-once (never overwritten); audit runs are written alongside it.
* `python backtest_winprob.py --date ...`: win % log loss / Brier / accuracy, V5.9 vs V2.
* Daily accuracy card (accuracy_v58.py): yesterday's frozen pregame probabilities vs real scorers, with the baseline.
* Known limits: single-slate decisions are noisy (one 15-game night); multi-night backtesting and weight fitting are
  Phase 2. No injury/line-change feed beyond ESPN injuries; live data can lag.

## Data sources
NHL API (api-web.nhle.com, api.nhle.com stats: schedule, play-by-play, rosters, game logs, team summary) · ESPN
(probable goalies, injuries) · MoneyPuck.com skater season summary (free for non-commercial use with credit to
MoneyPuck.com; commercial use needs their approval) · The Odds API (optional prices, user key).
