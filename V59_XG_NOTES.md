# V5.9 – xG shot-quality weighting (next-goal model)

Layer `xg` on top of the V5.8 situational model (`xg_v59.py`, hooks in `situational_v58.py`; flag `MODEL_XG`).

## Source
- **MoneyPuck.com** season skater summary, `moneypuck.com/moneypuck/playerData/seasonSummary/{yyyy}/regular/skaters.csv`
  (listed on moneypuck.com/data.htm; updated nightly; one ~2.5 MB download per 6 h through `st.cache_data`).
- Terms (data.htm): free for **non-commercial** use; "clearly credit MoneyPuck.com" wherever something using the data is
  shown; non-approved scraping of the site is blocked. We only download the listed CSV, and a credit caption
  (`xg_v59.CREDIT`) shows on Home, Edge Flags, EdgeLab and Live Next Goal whenever a shown chance used xG.
  Commercial use needs MoneyPuck's approval.
- Natural Stat Trick was not used: automated access is only allowed on data.naturalstattrick.com with an approved
  per-user key (rate-limited, HTML tables); the public site is for human use.
- Matching: MoneyPuck `playerId` = NHL playerId (2026-10-23 slate: 76/76 ranked skaters matched; 76 with 5on5 SOG,
  35 with 5on4 SOG).

## Formula (per player, per situation)
EV quality from MoneyPuck `5on5`, PP from `5on4`; without the NHL PP split, `all` scales the whole base.
```
q   = (xG + 50·L) / (SOG + 50)          L = league xG/SOG in the same file + situation
Q   = clamp(q / L, 0.6, 1.6)
F   = clamp((G + 25) / (xG + 25), 0.85, 1.15)      finishing, heavily shrunk
xq  = T · Q · F                          T = app league sh% (EV 0.0917, PP 0.148, all 0.10)
sh' = 0.6 · xq + 0.4 · sh_situational    sh_situational = V5.8 shrunk sh% (50 ghost shots, 10% anchor)
```
The situational EV / PP parts (or the base) are multiplied by sh'/sh; then line, goalie and the [0.5, 2.0] ratio cap
apply as before. Q is relative to the file's own league average, so league totals stay on the app's calibration.
`rec['situ']['xg']` logs, per situation: xg_per_shot_raw / _shrunk, league, quality, finishing, sh_before / after,
mult, plus weight, source and as_of.

## Fallbacks (exactly the situational numbers)
No data, failed fetch, wrong season, file older than 10 days, file newer than slate day +36 h (historical slates
would see later games), unmatched player or 0 SOG in that situation -> multiplier 1.0 for that part. `MODEL_XG=0`
(env) / `MODEL_XG = "false"` (secrets) drops the part.

## Gaps
- `5on5` is not all of EV (4v4 / 3v3 are in MoneyPuck `other`, mixed with empty-net and 6v5); `other` is not used.
- MoneyPuck xG is computed on unblocked attempts; xG/SOG follows MoneyPuck's own convention.
- Early season (≈12 GP): xG/SOG is shrunk heavily; finishing factor ≈ 1 for nearly everyone.
- No live xG feed: in-game, the existing play-by-play xG proxy in live_nextgoal_v56 stays; the pregame xG ratio scales it.
- Point-in-time backtests: `xg_v59.aggregate_shots(read_shots(shots_{yyyy}.zip), D, fetch_game_dates(season))`
  (per-shot file has no dates; NHL stats `/game` gives them). Matches the summary's league xG/SOG; per-player 5on5 SOG
  agree exactly for ~75% of players (strength classification by skaters on ice differs slightly).
