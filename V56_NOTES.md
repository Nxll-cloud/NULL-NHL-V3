# Null’s Playbook V5.6

V5.6 adds a **live next-goal model** with its own tab, Matchup Center goalie threats with real shooter-vs-goalie
history, per-game numerology boards, edge flags against the opening anytime line, and an offline-tested
**backtest with a write-once baseline**. Existing scoring semantics (rankings, Form %, four leaders, numerology
outputs, tracker grading, EdgeLab math) are unchanged; every V5.5 test still passes. Every file is under 100 KB.

## Live next-goal model — `live_nextgoal_v56.py`, `live_feed_v56.py`, `live_state_v56.py`, `tabs/nextgoal.py`
* Source: official NHL play-by-play `api-web.nhle.com/v1/gamecenter/{id}/play-by-play` + `/v1/score/{date}`.
  Polled every 30 s while a game is LIVE/CRIT (exponential backoff with jitter on errors, capped), events deduped by `eventId`.
* Per skater: shot rate = pace blend of in-game SOG/min and the season SOG/GP prior (w = elapsed/(elapsed+30));
  conversion = shrunk sh% (G + 50·10%)/(SOG + 50) blended with in-game xG (logistic on distance + angle, shot type,
  strength); optional bounded Form multiplier (0.9–1.1, off by default — Form is never a probability).
* Team rate × situation multiplier (PP / SH / empty net, OT 3-on-3 pace). Competing risk:
  P(any goal) = 1 − exp(−ΣL·remaining); per-player probabilities sum to ≤ 1, the rest is "no further goal".
* States: LIVE (ranked, arrows vs previous poll), Pregame (prior only), Final (no next goal), Shootout (not modelled).
  DEMO replay of a finished game (MIN@CGY fixture) is labelled DEMO.
* UI: Live Next Goal tab, Matchup Center live panel, Home live strip and board tiles with live scores.
* Not done: the optional Track Record source "Live model" (picks are still graded by the existing tracker).

## (A) Matchup Center goalies — `mc_goalies_v56.py`, `h2h_v56.py`
* Goalies section moved from Research into Matchup Center (Research shows a pointer). Goalie order: PBP goalie in net → starter feed → GS leader.
* Opposing threats ranked by live next-goal % (or the pregame prior / "pregame prior (game over)"); reverse view (shooter vs goalie).
* Real H2H: past meetings of the two clubs from `club-schedule-season`, then each meeting's PBP `goalieInNetId`
  (SOG and goals per shooter–goalie pair; empty-net and shootout excluded). Coverage: since 2024-25, meetings between
  tonight's two clubs only (stated in the UI); cached per game in `data/h2h_cache` (gitignored, size-capped).
* Toggle: sort games with H2H flags first.

## (B) Numbers by game — `numboard_v56.py`
Per-game boards with a documented threat score = round(100·(3D + 2A + T)/18), warm colour tiers, threat rings,
arena highlight and a per-game badge. Built on the unchanged V4.9 signals; entertainment only.

## (C) Edge Flags — `edgeflags_v56.py`, `tabs/edgeflags.py`
Each game's top model shooter vs his opening anytime line: edge = model p − implied, p = 1 − exp(−λ), Form not used.
Opening = earliest quote seen (Odds API current odds or CSV; the API has no historical openers). With no key and no CSV
a synthetic DEMO set is used and labelled DEMO everywhere. Scored / finished games are settled and never flagged.

## Backtest — `backtest_next_goal.py`, `backtests/`, `BACKTEST_V56.md`
Replays a full past slate (2026-04-04, 15 games, 106 goals) through the same model code with no lookahead and
season-to-date priors as of the prior day. Baseline `backtests/baseline_v56.json` is write-once (`--reset-baseline`
to replace). Opening-line comparison is implemented (CSV import, vig removal) but **blocked**: no real historical
opening lines are available. Results and every miss: `BACKTEST_V56.md`.

## Tests
`test_v56_model.py`, `test_v56_features.py`, `test_v56_apptest.py`, `test_v56_backtest.py`; fixtures in
`test_fixtures_v56/` (real PBP from 2026-10-22). No network in tests (`conftest.py` blocks sockets).
