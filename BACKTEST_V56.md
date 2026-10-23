# V5.6 next-goal backtest (baseline)

Slate: **2026-04-04** (2025-26 regular season, Saturday) — 15 games, 30 of 32 teams, 106 non-shootout goals. Chosen because it is a full 15-game regular-season slate late enough (~75 GP) that season-to-date priors are stable, but a week before the final weekend (when rest/clinching lineups skew). The 2026-10-22 preview slate is excluded on purpose; early-October 2026-27 slates have only 2-6 GP of priors.

Model: `V5.6 next-goal (live_nextgoal_v56)`, code hash `02d66e98cc8e67b7`, backtest `bt-1`. Form multiplier OFF.

## Method (no lookahead)

- Official PBP (`api-web.nhle.com/v1/gamecenter/{id}/play-by-play`) parsed with the same `ng.parse_pbp`; for each goal the model sees `ng.truncate(game, i)` = only shot events before it, the clock at the goal and the goal's own situationCode (manpower / empty net — known before the shot is taken). Score and SOG are recomputed from prior events.
- Priors: each dressed skater's 2025-26 game log (`/v1/player/{id}/game-log/20252026/2`) summed over games dated **before 2026-04-04** (= season stats as of the prior day).
- Ranking = `p_next` (competing risk across both teams). Team-level = rank inside the scoring team. Probabilities are evaluated conditional on a goal occurring next (q = p_next / P(any goal)).
- Leakage that could not be avoided: (1) dressed lineups come from the game's rosterSpots (known at puck drop, not truly pre-game); (2) model constants (league sh% 10%, xG logistic coefficients, pace tau) were set by hand from general NHL knowledge, not fitted to this slate, but that knowledge covers seasons that include this one; (3) the situationCode at the goal is used as the game state (a penalty or goalie pull in progress is legitimately known, but the exact second is the goal's).

## Headline

| metric | model | SOG/G leader | random |
|---|---|---|---|
| game top-1 | 7.5% | 5.7% | 2.8% |
| game top-3 | 19.8% | 22.6% | 8.3% |
| game top-5 | 31.1% | 30.2% | 13.9% |
| team top-1 | 10.4% | 15.1% | 5.6% |
| team top-3 | 29.2% | 33.0% | 16.7% |
| team top-5 | 43.4% | 49.1% | 27.8% |

Multiclass Brier 0.965 (uniform 0.9722); log loss 3.469 (uniform 3.5835, season SOG-share 3.4343).
Pregame top-ranked shooter scored at least once in 40.0% of games (SOG/G leader 40.0%); per team 33.3%. Pregame P(anytime) Brier 0.1328.

**Read:** the model clearly beats random (≈2.7x at game top-1) and is level with the naive season SOG/G leader at game level, but it is *worse* than the SOG/G leader inside the scoring team (top-1 10.4% vs 15.1%) and its log loss is slightly worse than a plain season-SOG share. The in-game pace weight (w = elapsed/(elapsed+30)) lets small in-game shot counts reshuffle teammates too much. Not tuned here: tuning on the same slate would be leakage; test any change against this baseline on a different slate.

App-prior variant (`headline_app_l10_priors` in the baseline): the live app builds SOG priors as Shots/G over the last 10 games x GP (`ng.priors_from_rankings`). Replayed with that prior the model is essentially unchanged: game top-1/3/5 7.5% / 18.9% / 32.1%, team top-1/3/5 10.4% / 28.3% / 43.4%, log loss 3.480, Brier 0.965 (the SOG/G-leader baseline built on L10 shots: game top-1 8.5%, team top-1 13.2%).

## Calibration (conditional next-goal q, all skaters at every goal moment)

| bucket | n | mean pred | observed |
|---|---|---|---|
| 0%-2% | 1911 | 1.0% | 1.7% |
| 2%-5% | 1309 | 3.2% | 3.0% |
| 5%-10% | 518 | 6.7% | 5.6% |
| 10%-15% | 68 | 12.0% | 7.3% |
| 15%-25% | 10 | 16.6% | 10.0% |

Overconfident at the top (10-25% calls hit 7-10%), underconfident at the bottom (0-2% calls hit 1.7%, mostly defencemen and depth players).

Pregame P(anytime) = 1 − exp(−λ):

| bucket | n | mean pred | observed |
|---|---|---|---|
| 0%-10% | 169 | 7.3% | 8.3% |
| 10%-20% | 230 | 14.7% | 15.7% |
| 20%-30% | 99 | 24.3% | 25.2% |
| 30%-40% | 38 | 33.8% | 36.8% |
| 40%-100% | 4 | 43.2% | 50.0% |

Anytime probabilities are well calibrated (slightly low across buckets — the slate averaged 7.1 goals/game).

## Miss patterns (98 of 106 goals were not the game top-1)

| situation | goals | top-1 | top-3 | team top-1 | median rank | share of misses |
|---|---|---|---|---|---|---|
| blowout (lead>=3 before goal) | 17 | 11.8% | 23.5% | 11.8% | 18 | 15.3% |
| late (P3 last 5 min / OT) | 14 | 14.3% | 35.7% | 28.6% | 6 | 12.2% |
| empty net | 7 | 28.6% | 42.9% | 28.6% | 5 | 5.1% |
| power play | 17 | 11.8% | 29.4% | 23.5% | 5 | 15.3% |
| shorthanded | 5 | 20.0% | 20.0% | 20.0% | 16 | 4.1% |
| early (<10 game SOG) | 12 | 0.0% | 8.3% | 0.0% | 16 | 12.2% |
| defenceman scorer | 16 | 0.0% | 0.0% | 0.0% | 22 | 16.3% |
| rebound (<=3 s) | 10 | 10.0% | 20.0% | 10.0% | 16 | 9.2% |
| even strength | 77 | 3.9% | 15.6% | 5.2% | 14 | 75.5% |

Highlights: defenceman scorers (16 goals) were never in the top 3 (median rank 22); early-game goals (<10 combined SOG) went 0/12 at top-1 and median rank 16 — the prior is flat there; blowout goals (median rank 18) are depth/fourth-line goals the model can't see because it has no TOI or line deployment; empty-net and PP goals are the best case (median rank 5); rebounds (median rank 16) go to net-front players with low prior shot rates.

## Opening-line comparison: BLOCKED

No real historical opening anytime-goal lines were available: no ODDS_API_KEY in env/secrets (and the Odds API historical endpoint is paid), no user CSV for 2026-04-04 (`demo_odds.csv` is a labelled DEMO set for 2026-10-22). Free sources checked: The Odds Gap free sample covers only Sep 15-21 2026 game lines; PuckAPI / OddsPapi need an account key. Nothing was fabricated. The comparison is implemented: `--lines file.csv` (columns in `backtests/opening_lines_template.csv`: date, game_id, player, player_id, team, book, side yes/no, american_odds, timestamp; earliest timestamp per book/side = opener; two-sided pairs are vig-removed, one-sided flagged) reports model P(anytime) vs market, Brier both ways, and the hit rate of positive-edge calls.

## Baseline store

`backtests/baseline_v56.json` (write-once). `python backtest_next_goal.py --date 2026-04-04` prints deltas and never touches it; only `--reset-baseline` replaces it. `--baseline-only` prints the stored headline. Verified: after the app-L10 variant was added, a plain run reported `same_code: False` and left the file byte-identical; it was then replaced once, deliberately, with `--reset-baseline` so the stored code hash matches the shipped code. Raw downloads cache to `data/backtest_cache/` (gitignored, not in the zip). Tests: `test_v56_backtest.py` (offline).

## Every miss

| game | per | time | score (A-H) | str | model top (q) | scorer | rank | q |
|---|---|---|---|---|---|---|---|---|
| DET@NYR | 1 | 13:19 | 0-0 | EV | J.T. Miller (10.7%) | Jaroslav Chmelar | 26 | 1.5% |
| DET@NYR | 2 | 15:59 | 0-1 | EV | J.T. Miller (10.3%) | Gabe Perreault | 9 | 4.0% |
| DET@NYR | 3 | 19:27 | 0-4 | EV | Dylan Larkin (12.1%) | David Perron | 3 | 7.0% |
| MIN@OTT | 1 | 09:45 | 0-0 | EV | Kirill Kaprizov (9.3%) | Jonas Brodin (D) | 32 | 0.9% |
| MIN@OTT | 1 | 15:35 | 1-0 | EV | Brady Tkachuk (9.8%) | Ryan Hartman | 8 | 4.6% |
| MIN@OTT | 2 | 15:31 | 2-0 | EV | Brady Tkachuk (9.8%) | Ryan Hartman | 7 | 5.4% |
| MIN@OTT | 3 | 12:46 | 3-0 | EV | Brady Tkachuk (9.1%) | Jake Middleton (D) | 36 | 0.3% |
| MIN@OTT | 3 | 16:43 | 4-0 | EV | Brady Tkachuk (8.6%) | Drake Batherson | 18 | 2.1% |
| COL@DAL | 3 | 10:39 | 0-0 | EV | Wyatt Johnston (9.7%) | Martin Necas | 4 | 6.5% |
| COL@DAL | 3 | 19:02 | 1-0 | EN | Martin Necas (9.9%) | Nathan MacKinnon | 5 | 6.1% |
| BOS@TBL | 2 | 06:47 | 0-0 | EV | Viktor Arvidsson (7.8%) | Casey Mittelstadt | 22 | 1.7% |
| BOS@TBL | 3 | 02:13 | 1-0 | EV | Fraser Minten (9.8%) | Charle-Edouard D'Astous (D) | 17 | 2.7% |
| BOS@TBL | 3 | 14:29 | 1-1 | EV | Fraser Minten (9.1%) | Darren Raddysh (D) | 21 | 1.8% |
| BOS@TBL | 3 | 18:27 | 1-2 | EN | Nick Paul (8.2%) | Nikita Kucherov | 3 | 6.6% |
| FLA@PIT | 1 | 00:20 | 0-0 | EV | Carter Verhaeghe (7.5%) | Noel Acciari | 4 | 5.5% |
| FLA@PIT | 1 | 05:06 | 0-1 | PP | Noel Acciari (12.1%) | Erik Karlsson (D) | 10 | 3.7% |
| FLA@PIT | 1 | 07:10 | 0-2 | EV | Noel Acciari (8.1%) | A.J. Greer | 16 | 2.3% |
| FLA@PIT | 1 | 14:31 | 1-2 | EV | Noel Acciari (7.3%) | Seth Jones (D) | 22 | 1.6% |
| FLA@PIT | 2 | 01:51 | 2-2 | EV | Tommy Novak (8.9%) | Anthony Mantha | 14 | 3.3% |
| FLA@PIT | 2 | 05:51 | 2-3 | PP | Rickard Rakell (20.0%) | Evgeni Malkin | 8 | 4.7% |
| FLA@PIT | 2 | 08:27 | 2-4 | EV | Rickard Rakell (15.4%) | Evgeni Malkin | 3 | 6.3% |
| FLA@PIT | 2 | 09:53 | 2-5 | EV | Rickard Rakell (14.7%) | Elmer Soderblom | 28 | 0.8% |
| FLA@PIT | 2 | 18:07 | 2-7 | EV | Rickard Rakell (16.8%) | Ryan Shea (D) | 31 | 0.5% |
| FLA@PIT | 3 | 03:30 | 2-8 | EV | Rickard Rakell (15.8%) | Evgeni Malkin | 2 | 12.8% |
| FLA@PIT | 3 | 08:02 | 2-9 | EV | Rickard Rakell (15.0%) | Noah Gregor | 22 | 1.8% |
| FLA@PIT | 3 | 10:46 | 3-9 | EV | Rickard Rakell (14.6%) | Mackie Samoskevich | 12 | 3.2% |
| MTL@NJD | 1 | 15:58 | 0-0 | EV | Cole Caufield (10.1%) | Jayden Struble (D) | 35 | 0.4% |
| MTL@NJD | 2 | 08:12 | 1-0 | PP | Cole Caufield (12.2%) | Ivan Demidov | 4 | 7.1% |
| MTL@NJD | 2 | 09:28 | 2-0 | EV | Timo Meier (11.5%) | Lane Hutson (D) | 25 | 1.0% |
| MTL@NJD | 2 | 13:08 | 3-0 | EV | Timo Meier (11.2%) | Dawson Mercer | 20 | 1.5% |
| MTL@NJD | 2 | 17:40 | 3-1 | SH | Cole Caufield (12.7%) | Jack Hughes | 10 | 3.3% |
| MTL@NJD | 3 | 17:45 | 3-2 | PP | Cole Caufield (8.5%) | Timo Meier | 2 | 7.2% |
| BUF@WSH | 1 | 03:15 | 0-0 | EV | Alex Ovechkin (11.5%) | Jakob Chychrun (D) | 7 | 3.9% |
| BUF@WSH | 1 | 03:35 | 0-1 | EV | Alex Ovechkin (11.2%) | Dylan Strome | 13 | 2.7% |
| BUF@WSH | 1 | 05:52 | 0-2 | EV | Alex Ovechkin (10.2%) | Connor McMichael | 22 | 1.7% |
| BUF@WSH | 1 | 06:30 | 0-3 | EV | Alex Ovechkin (9.8%) | Rasmus Dahlin (D) | 14 | 2.5% |
| BUF@WSH | 1 | 12:15 | 1-3 | EV | Alex Ovechkin (8.5%) | Beck Malenstyn | 29 | 0.8% |
| BUF@WSH | 2 | 06:06 | 2-3 | EV | Jack Quinn (10.8%) | Aliaksei Protas | 3 | 6.0% |
| BUF@WSH | 3 | 06:26 | 2-4 | EV | Connor McMichael (9.6%) | Ryan Leonard | 15 | 2.2% |
| BUF@WSH | 3 | 08:55 | 2-5 | SH | Jack Quinn (13.5%) | Tom Wilson | 24 | 1.0% |
| NYI@CAR | 1 | 05:17 | 0-0 | EV | Sebastian Aho (15.2%) | Marc Gatcomb | 31 | 1.0% |
| NYI@CAR | 1 | 11:07 | 1-0 | EV | Sebastian Aho (13.5%) | Seth Jarvis | 2 | 7.0% |
| NYI@CAR | 2 | 02:15 | 1-1 | EV | Sebastian Aho (13.8%) | Max Shabanov | 29 | 1.1% |
| NYI@CAR | 2 | 11:15 | 2-1 | EV | Sebastian Aho (15.9%) | Jackson Blake | 17 | 2.1% |
| NYI@CAR | 3 | 00:24 | 2-3 | EV | Sebastian Aho (15.5%) | Seth Jarvis | 2 | 11.4% |
| NYI@CAR | 3 | 18:23 | 2-4 | PP | Sebastian Aho (13.5%) | Anders Lee | 6 | 4.7% |
| WPG@CBJ | 1 | 01:17 | 0-0 | EV | Kyle Connor (7.1%) | Ivan Provorov (D) | 22 | 2.1% |
| WPG@CBJ | 2 | 18:14 | 0-1 | EV | Gabriel Vilardi (13.7%) | Kyle Connor | 7 | 3.9% |
| WPG@CBJ | 3 | 10:58 | 1-1 | EV | Gabriel Vilardi (11.3%) | Kyle Connor | 4 | 5.5% |
| UTA@VAN | 1 | 02:28 | 0-0 | EV | Dylan Guenther (6.7%) | Linus Karlsson | 18 | 2.5% |
| UTA@VAN | 1 | 13:34 | 0-1 | EV | Nick Schmaltz (7.6%) | Kailer Yamamoto | 24 | 1.8% |
| UTA@VAN | 1 | 18:30 | 1-1 | EV | Nick Schmaltz (7.0%) | Clayton Keller | 13 | 3.1% |
| UTA@VAN | 2 | 02:05 | 2-1 | EV | Nick Schmaltz (6.7%) | Linus Karlsson | 8 | 4.2% |
| UTA@VAN | 2 | 07:04 | 2-2 | PP | Nick Schmaltz (12.1%) | Clayton Keller | 6 | 6.1% |
| UTA@VAN | 2 | 11:55 | 3-2 | EV | Kailer Yamamoto (8.0%) | Dylan Guenther | 4 | 6.3% |
| UTA@VAN | 3 | 00:20 | 4-2 | PP | Linus Karlsson (10.6%) | Jake DeBrusk | 4 | 6.9% |
| UTA@VAN | 3 | 01:32 | 4-3 | EV | Jake DeBrusk (7.8%) | Lawson Crouse | 11 | 3.9% |
| UTA@VAN | 3 | 04:40 | 5-3 | PP | Jake DeBrusk (11.8%) | Marco Rossi | 6 | 4.3% |
| UTA@VAN | 3 | 11:45 | 5-4 | EV | Jake DeBrusk (7.3%) | Liam O'Brien | 31 | 0.6% |
| UTA@VAN | 3 | 19:07 | 6-4 | EN | Jake DeBrusk (8.6%) | Clayton Keller | 5 | 6.2% |
| TOR@LAK | 1 | 04:19 | 0-0 | EV | William Nylander (9.9%) | Matthew Knies | 6 | 4.2% |
| TOR@LAK | 1 | 13:42 | 1-0 | SH | Adrian Kempe (11.0%) | Steven Lorentz | 33 | 0.6% |
| TOR@LAK | 2 | 01:11 | 2-0 | EV | Alex Laferriere (11.9%) | Quinton Byfield | 15 | 2.5% |
| TOR@LAK | 2 | 03:55 | 2-1 | EV | Alex Laferriere (11.2%) | Adrian Kempe | 5 | 5.6% |
| TOR@LAK | 2 | 09:18 | 2-2 | PP | William Nylander (11.5%) | John Tavares | 6 | 4.9% |
| TOR@LAK | 2 | 14:53 | 3-2 | EV | Adrian Kempe (8.8%) | Artemi Panarin | 9 | 4.1% |
| TOR@LAK | 2 | 19:47 | 3-3 | PP | William Nylander (9.0%) | Easton Cowan | 5 | 5.5% |
| TOR@LAK | 3 | 05:46 | 4-3 | EV | Alex Laferriere (13.5%) | Adrian Kempe | 3 | 7.2% |
| TOR@LAK | 3 | 06:14 | 4-4 | EV | Alex Laferriere (13.4%) | Samuel Helenius | 18 | 1.6% |
| TOR@LAK | 3 | 09:37 | 4-6 | EV | Alex Laferriere (14.5%) | Nick Robertson | 13 | 2.8% |
| TOR@LAK | 3 | 13:29 | 5-6 | EV | Alex Laferriere (14.2%) | Matthew Knies | 13 | 2.7% |
| TOR@LAK | OT | 02:33 | 6-6 | EV | Alex Laferriere (13.2%) | Quinton Byfield | 7 | 4.8% |
| VGK@EDM | 1 | 11:43 | 0-0 | EV | Mark Stone (9.4%) | Brett Howden | 19 | 1.9% |
| VGK@EDM | 2 | 05:44 | 1-0 | EV | Mark Stone (11.5%) | Colton Sissons | 28 | 0.9% |
| VGK@EDM | 2 | 08:05 | 2-0 | EV | Mark Stone (10.8%) | Jeremy Lauzon (D) | 27 | 1.0% |
| VGK@EDM | 2 | 19:26 | 3-0 | EV | Mark Stone (9.3%) | Evan Bouchard (D) | 7 | 5.0% |
| VGK@EDM | 3 | 04:04 | 3-1 | EV | Connor McDavid (11.5%) | Mark Stone | 2 | 8.8% |
| VGK@EDM | 3 | 16:13 | 4-1 | PP | Mark Stone (13.8%) | Rasmus Andersson (D) | 21 | 1.6% |
| CGY@ANA | 1 | 10:11 | 0-0 | EV | Troy Terry (8.8%) | Beckett Sennecke | 3 | 7.2% |
| CGY@ANA | 1 | 13:24 | 0-1 | EV | Beckett Sennecke (10.9%) | Joel Farabee | 18 | 2.2% |
| CGY@ANA | 2 | 01:20 | 1-1 | EV | Beckett Sennecke (9.5%) | Ryan Strome | 26 | 1.3% |
| CGY@ANA | 2 | 07:49 | 2-1 | EV | Beckett Sennecke (10.9%) | Matvei Gridin | 14 | 3.1% |
| CGY@ANA | 2 | 18:44 | 3-1 | EV | Beckett Sennecke (9.7%) | Morgan Frost | 4 | 6.0% |
| CGY@ANA | 3 | 07:49 | 4-1 | EV | Morgan Frost (9.4%) | Leo Carlsson | 10 | 3.9% |
| CGY@ANA | 3 | 09:51 | 4-2 | PP | Beckett Sennecke (12.3%) | Mason McTavish | 16 | 1.7% |
| NSH@SJS | 1 | 08:38 | 0-0 | PP | Erik Haula (9.0%) | Filip Forsberg | 3 | 8.6% |
| NSH@SJS | 1 | 16:55 | 2-0 | PP | Filip Forsberg (17.8%) | Steven Stamkos | 4 | 7.0% |
| NSH@SJS | 2 | 15:49 | 3-0 | EV | Filip Forsberg (8.5%) | Nick Leddy (D) | 22 | 1.5% |
| NSH@SJS | 3 | 01:06 | 3-2 | EV | Macklin Celebrini (12.3%) | Alexander Wennberg | 21 | 1.4% |
| NSH@SJS | 3 | 08:28 | 3-3 | EV | Macklin Celebrini (11.0%) | Ryan O'Reilly | 19 | 1.8% |
| NSH@SJS | 3 | 17:26 | 4-3 | SH | Macklin Celebrini (14.6%) | Erik Haula | 16 | 2.2% |
| NSH@SJS | 3 | 18:45 | 5-3 | EN | Macklin Celebrini (8.5%) | Tyson Jost | 17 | 2.0% |
| CHI@SEA | 2 | 09:15 | 0-0 | PP | Ryan Donato (14.9%) | Teuvo Teravainen | 2 | 8.6% |
| CHI@SEA | 2 | 19:37 | 1-0 | EV | Ryan Donato (12.8%) | Tyler Bertuzzi | 6 | 4.4% |
| CHI@SEA | 3 | 10:48 | 2-0 | EV | Ryan Donato (10.5%) | Jaden Schwartz | 25 | 1.2% |
| CHI@SEA | 3 | 13:08 | 2-1 | EV | Ryan Donato (10.2%) | Sacha Boisvert | 16 | 2.4% |
| CHI@SEA | 3 | 14:18 | 3-1 | EV | Ryan Donato (9.9%) | Kaapo Kakko | 27 | 1.0% |
| CHI@SEA | 3 | 18:48 | 3-2 | EN | Ryan Donato (10.8%) | Ilya Mikheyev | 12 | 2.6% |
