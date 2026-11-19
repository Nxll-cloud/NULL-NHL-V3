"""V6.1 Home price-gap scope. Display/selection only: no API calls, no model or scoring changes.

The shared quote comparison (Odds tab, exports) compares every provider event and selection. For the Home
'Price-gap leader' card and the Home price list only, a quote must be:
  * the affirmative (Yes) side of the anytime-goal market with no line;
  * for a game on the selected slate (provider home/away teams + start date, or a CSV team on that slate);
  * for a game that has not started (pre-game prices only; a stale pre-game book vs an in-play book is not a gap).
Scoped discrepancies carry the slate game's team codes so a name can only match a player in THAT game.
"""
from collections import Counter
from datetime import datetime, timezone
import pandas as pd
import edgelab_prices_v60 as elp
from playbook_odds import compare_odds
from v55_ui import game_state

ANYTIME = {elp.name_key(m) for m in elp.MARKETS}
TEAM_ALIASES = {'utahhockeyclub': 'UTA', 'utahhc': 'UTA', 'utah': 'UTA'}   # provider names the NHL table lacks


def _team(value):
    return elp.team(value) or TEAM_ALIASES.get(elp.name_key(value).replace(' ', ''), '')


def _slate_games(games):
    out = []
    for g in games or []:
        if not isinstance(g, dict):
            continue
        away, home = elp.text(g.get('Away') or g.get('away')).upper(), elp.text(g.get('Home') or g.get('home')).upper()
        if away and home:
            out.append({'away': away, 'home': home, 'game': g,
                        'key': elp.ident(g.get('Game ID') or g.get('game_id')) or f'{away}@{home}'})
    return out


def _map(q, slate, day):
    home, away = _team(q.get('home_team')), _team(q.get('away_team'))
    if (elp.text(q.get('home_team')) and not home) or (elp.text(q.get('away_team')) and not away):
        return None, 'unknown event team'
    at = elp.stamp(q.get('commence_time'))
    date = elp.text(q.get('game_date')) or elp.text(q.get('slate_date'))
    if at is not None:
        date = at.tz_convert(elp.ET).date().isoformat()
    if date and date != day:
        return None, 'event not on this slate date'
    if home and away:
        hits = [s for s in slate if (s['home'], s['away']) == (home, away)]
    else:
        code = _team(q.get('team'))
        hits = [s for s in slate if code and code in (s['home'], s['away'])]
    if len(hits) != 1:
        return None, 'event not on this slate'
    return hits[0], None


def scope(quotes, games, day, now=None):
    """-> (clean, discrepancies, report). discrepancies = compare_odds output for in-scope quotes plus
    home_team_code/away_team_code/game_key columns. Never raises on bad provider rows."""
    now = now or datetime.now(timezone.utc)
    report = {'received': len(quotes) if isinstance(quotes, pd.DataFrame) else 0, 'accepted': 0, 'excluded': {}}
    empty = pd.DataFrame()
    if not isinstance(quotes, pd.DataFrame) or quotes.empty:
        return empty, empty, report
    slate = _slate_games(games)
    rejects, keep = Counter(), []
    for q in quotes.to_dict('records'):
        if elp.name_key(q.get('market')) not in ANYTIME or elp.text(q.get('selection')).casefold() != 'yes':
            rejects['not the Yes side of anytime goal'] += 1
            continue
        if elp.ident(q.get('line')):
            rejects['line on anytime Yes contract'] += 1
            continue
        s, reason = _map(q, slate, day)
        if reason:
            rejects[reason] += 1
            continue
        if game_state(s['game'], now) != 'pre':
            rejects['game started or final'] += 1
            continue
        keep.append(dict(q, event_id='nhl:' + s['key'], _home=s['home'], _away=s['away']))
    report['excluded'] = dict(rejects)
    if not keep:
        return empty, empty, report
    try:
        clean, disc = compare_odds(pd.DataFrame(keep))
    except (ValueError, KeyError, TypeError):
        report['excluded']['malformed quote rows'] = len(keep)
        return empty, empty, report
    report['accepted'] = len(clean)
    if not disc.empty:
        teams = {k: (h, a) for k, h, a in zip(clean['event_id'], clean['_home'], clean['_away'])}
        disc = disc.assign(home_team_code=[teams.get(e, ('', ''))[0] for e in disc['event_id']],
                           away_team_code=[teams.get(e, ('', ''))[1] for e in disc['event_id']],
                           game_key=[str(e).removeprefix('nhl:') for e in disc['event_id']])
    return clean.drop(columns=['_home', '_away'], errors='ignore'), disc, report


def empty_reason(source, has_key, live_error, shared_error, quotes, report, discrepancies, has_leader):
    """(title, body) for an empty Price-gap leader card; honest about why nothing is shown."""
    if has_leader:
        return None, None
    if live_error:
        return 'Odds feed unavailable', f'{live_error} No price gap is shown; nothing is invented.'
    if shared_error:
        return 'Odds validation issue', f'{shared_error} No price gap is shown.'
    if not isinstance(quotes, pd.DataFrame) or quotes.empty:
        if source == 'Uploaded CSV':
            return 'No uploaded prices', 'Upload a CSV in Odds to compare books. Nothing is invented.'
        if not has_key:
            return ('Odds key not found',
                    'ODDS_API_KEY was not found in this app\u2019s Streamlit secrets (top level, an odds section, or the environment). '
                    'Check the key name in the app\u2019s Secrets settings, or upload a CSV in Odds. Nothing is invented.')
        return 'No live quotes right now', 'The odds feed returned no anytime-goal quotes (markets may be posted later or suspended).'
    ex = (report or {}).get('excluded') or {}
    detail = '; '.join(f'{k} ({v})' for k, v in sorted(ex.items(), key=lambda kv: -kv[1])[:3])
    if not isinstance(discrepancies, pd.DataFrame) or discrepancies.empty:
        return ('No pre-game price gap tonight',
                'No player on tonight\u2019s unstarted games has a Yes anytime-goal price at 2+ books.' + (f' Excluded: {detail}.' if detail else ''))
    return ('No distinct match for the gap',
            'Price gaps exist, but none maps to a unique player in that game who is not already a leader above.')


def matchup_odds_note(quotes, discrepancies, game):
    """One honest sentence on Odds-badge availability for a Matchup Center game ({'away','home'})."""
    if not isinstance(quotes, pd.DataFrame) or quotes.empty:
        return 'No sportsbook prices loaded, so no Odds badges.'
    teams = {str((game or {}).get('away') or '').upper(), str((game or {}).get('home') or '').upper()} - {''}
    if isinstance(discrepancies, pd.DataFrame) and not discrepancies.empty and 'home_team_code' in discrepancies:
        n = sum(1 for h, a in zip(discrepancies['home_team_code'], discrepancies['away_team_code']) if {h, a} == teams)
        if n:
            return f'{n} comparable pre-game price{"" if n == 1 else "s"} for this game.'
    return 'No pre-game price gap for this game right now, so no Odds badges.'
