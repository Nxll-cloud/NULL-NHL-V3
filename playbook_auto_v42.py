"""Automatic full-slate orchestration; does not claim predictive probabilities."""
from datetime import datetime, timezone, timedelta
import pandas as pd


def needs_refresh(state, day, now, minutes=15):
    if state.get('np_v42_day') != day:
        attempted = state.get('np_v42_attempt_at')
        return attempted is None or (now - attempted).total_seconds() >= 60
    previous = state.get('np_v42_last_run')
    return previous is None or (now - previous).total_seconds() >= minutes * 60


def coverage_summary(ranked, history):
    if ranked is None or pd.DataFrame(ranked).empty:
        return 0, 0, 0
    frame = pd.DataFrame(ranked)
    count = len(frame)
    if history is None or pd.DataFrame(history).empty:
        return 0, 0, count
    h = pd.DataFrame(history)
    if 'Player ID' not in h or 'Historical data status' not in h:
        return 0, 0, count
    statuses = dict(zip(h['Player ID'].astype(str).str.replace(r'\.0$', '', regex=True), h['Historical data status']))
    ids = frame['Player ID'].astype(str).str.replace(r'\.0$', '', regex=True)
    complete = sum(statuses.get(i) == 'Complete' for i in ids)
    partial = sum(i in statuses and statuses[i] != 'Complete' for i in ids)
    return complete, partial, count - complete - partial


def auto_full_slate(day, schedule_fetch, team_fetch, defense_fetch, history_fetch,
                    rank_fn, attach_fn, assign_fn, min_games=3, use_defense=True,
                    max_history_players=500, history_years=3):
    games = schedule_fetch(day)
    if not games:
        return {'games': [], 'ranked': pd.DataFrame(), 'history': pd.DataFrame(), 'errors': []}
    teams = sorted({g[k] for g in games for k in ('Home', 'Away') if g.get(k)})
    all_rows, errors, defense = [], [], {}
    for team in teams:
        try:
            rows, errs = team_fetch(team, day)
            all_rows.extend(rows)
            errors.extend(f'{team}: {e}' for e in errs)
        except Exception as exc:
            errors.append(f'{team} player data: {type(exc).__name__}: {exc}')
    if not all_rows:
        return {'games': games, 'ranked': pd.DataFrame(), 'history': pd.DataFrame(), 'errors': errors}
    for team in teams:
        try:
            defense[team] = defense_fetch(team, day)
        except Exception as exc:
            errors.append(f'{team} defense: {type(exc).__name__}: {exc}')
    ranked = pd.DataFrame(assign_fn(attach_fn(rank_fn(all_rows, min_games), games, defense, adjust=use_defense)))
    if ranked.empty:
        return {'games': games, 'ranked': ranked, 'history': pd.DataFrame(), 'errors': errors}
    history, history_errors = history_fetch(ranked.to_dict('records'), games, day,
                                           max_players=max_history_players, years=history_years)
    errors.extend(history_errors)
    return {'games': games, 'ranked': ranked, 'history': history, 'errors': errors}
