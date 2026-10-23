"""Null's Playbook V5.9 · top-threat mini badges under Home's "Tonight's top target" card.

One circular jersey badge per slate game: the #1 skater of that game in the SAME next-goal ranking every surface uses
(``_v56_results`` = live_state_v56.slate_results with the situational/xG layer; Live Next Goal shows the same list).
Number = NHL feed data only: the play-by-play roster spot's sweaterNumber, else the NHL roster feed (v55 jersey map);
when neither has it the badge shows the team abbrev alone (never an invented number). Team colours = v55 TEAM_COLORS.
Tapping a badge opens the Live Next Goal tab and scrolls to that player's row (assets/v55.js, ``data-ng`` hook).
Display only: nothing here feeds the model."""
from html import escape

import v55_ui as v5
import position_badge_v59 as pb

NG_TAB = 'Live Next Goal'   # tab label text the JS looks for (app.py: '⏱ Live Next Goal')


def _esc(x):
    return escape('' if x is None else str(x), quote=True)


def jersey_number(value):
    """NHL sweater numbers are 0..99 integers; anything else (None, '', 'N/A', 120) -> None."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    n = int(f)
    return n if f == n and 0 <= n <= 99 else None


def anchor(game_id, pid):
    """Row hook shared by the badge and the Live Next Goal row (v56_ui.nextgoal_panel ``data-ng``)."""
    return f'ng-{str(game_id or "").strip()}-{str(pid or "").strip()}'


def top_threats(results, jersey=None):
    """[{game_id, key, away, home, pid, name, team, opp, pos, number, p_next, phase}] in slate order, one per game that
    has a ranked skater. ``results``: _v56_results rows; ``jersey``: {str(pid): number} from the NHL roster feed."""
    jersey = jersey or {}
    out, seen = [], set()
    for r in results or []:
        res = (r or {}).get('result') or {}
        sl = (r or {}).get('slate') or {}
        g = res.get('game') or {}
        gid = str(sl.get('game_id') or g.get('game_id') or '')
        players = [p for p in res.get('players') or [] if str(p.get('pos', '')).upper() != 'G']
        if not gid or gid in seen or not players:
            continue
        seen.add(gid)
        p = players[0]   # the model's own order (live_nextgoal_v56.model sorts by next-goal %, then SOG)
        num = jersey_number(p.get('number'))
        if num is None:
            num = jersey_number(jersey.get(str(p.get('pid'))))
        away, home = sl.get('away') or g.get('away', ''), sl.get('home') or g.get('home', '')
        team = p.get('team', '')
        out.append({'game_id': gid, 'key': sl.get('key'), 'away': away, 'home': home, 'pid': p.get('pid'), 'name': p.get('name', ''),
                    'team': team, 'opp': home if team == away else away, 'pos': p.get('pos', ''), 'number': num,
                    'p_next': p.get('p_next') or 0.0, 'phase': res.get('phase', 'pregame')})
    return out


def _last(name):
    parts = str(name or '').split()
    return parts[-1] if parts else ''


def badge(t):
    team = v5.team_code(t['team']) or str(t['team'] or '')
    num = t.get('number')
    face = (f'<b class="thn">{num}</b><small>{_esc(team)}</small>' if num is not None else f'<b class="tha">{_esc(team)}</b>')
    basis = ('final, shot leader' if t['phase'] == 'final' else f'next-goal model {t["p_next"] * 100:.1f}%')
    tip = (f'Top threat {t["away"]} @ {t["home"]}: {t["name"]} ({team}{f" #{num}" if num is not None else ""}) · {basis}. '
           f'Tap for his row in {NG_TAB}.')
    return (f'<a class="thb" href="#{_esc(anchor(t["game_id"], t["pid"]))}" data-ng="{_esc(anchor(t["game_id"], t["pid"]))}" '
            f'data-tab="{_esc(NG_TAB)}" style="{v5.team_vars(team)}" title="{_esc(tip)}" aria-label="{_esc(tip)}">'
            f'<span class="thc">{face}</span><span class="thl">{_esc(_last(t["name"]))}{pb.goalie_badge(t.get("pos"))}</span>'
            f'<span class="thg">vs {_esc(t["opp"])}</span></a>')


def section_html(threats):
    """The badge row ('' when no game has a ranked skater, so Home shows nothing rather than an empty strip)."""
    if not threats:
        return ''
    return (f'<nav class="sec thr" aria-label="Top threat per game"><div class="thh"><span class="kicker">Top threat · every game</span>'
            f'<small>#1 in the next-goal model (xG + situational) · tap to open {NG_TAB}</small></div>'
            f'<div class="throw">{"".join(badge(t) for t in threats)}</div></nav>')
