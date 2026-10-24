"""V5.6 HTML fragments (rendered through v55_ui.html_block / inline). Pure functions, no Streamlit."""
from __future__ import annotations

import v55_ui as v5
import scorers_tonight_v58 as sctn
import venue_v58 as vn
from v55_ui import esc

ARROWS = {'up': ('▲', 'up'), 'down': ('▼', 'dn'), 'same': ('•', 'eq'), 'new': ('NEW', 'nw')}


def pct(p, dp=1):
    return '—' if p is None else f'{p * 100:.{dp}f}%'


def _arrow(delta):
    if delta is None:
        sym, cls = ARROWS['new']
        return f'<span class="ra {cls}">{sym}</span>'
    if delta > 0:
        return f'<span class="ra up">▲{delta}</span>'
    if delta < 0:
        return f'<span class="ra dn">▼{-delta}</span>'
    return '<span class="ra eq">•</span>'


def _headshot(p, season):
    if p.get('headshot'):
        return f'<img class="ngm" src="{esc(p["headshot"])}" alt="" loading="lazy"/>'
    return v5.mug(season, p.get('team'), p.get('pid'), 'ngm')


def replay_badge(phase, label='', score='', playing=False):
    """V5.9 DEMO replay state: pulses only while autoplay is stepping; paused/scrubbed is a static REPLAY tag; end = 'Final a–h'."""
    sc = f' · {score}' if score else ''
    if phase == 'final':
        txt = (str(label or 'Final') + (f' {score}' if score else '')).strip()
        return f'<span class="live fin rp">{esc(txt)}</span>'
    if phase == 'pregame':
        return '<span class="live pre rp">REPLAY · PREGAME PRIOR</span>'
    if playing:
        return f'<span class="live rp on"><i class="pulse"></i>REPLAYING · {esc(label, "")}{esc(sc)}</span>'
    return f'<span class="live rp">REPLAY · {esc(label, "")}{esc(sc)}</span>'


def state_badge(phase, label='', updated=None, demo=False, replay=None, score=''):
    up = f'<small class="upd">updated {esc(updated)}</small>' if updated else ''
    d = '<span class="chip warn">DEMO</span>' if demo else ''
    if replay:
        return f'{replay_badge(phase, label, score, replay == "playing")}{d}{up}'
    if phase == 'live':
        return f'<span class="live"><i class="pulse"></i>LIVE {esc(label, "")}</span>{d}{up}'
    if phase == 'final':
        txt = str(label or '').upper() if str(label or '').upper().startswith('FINAL') else ('FINAL ' + str(label or '')).strip()
        return f'<span class="live fin">{esc(txt)}</span>{d}{up}'
    if phase == 'shootout':
        return f'<span class="live fin">SHOOTOUT · no next goal</span>{d}{up}'
    return f'<span class="live pre">PREGAME PRIOR</span>{d}{up}'


def team_bar(result):
    g = result['game']
    a, h = g['away'], g['home']
    pa, ph, pn = result['p_team'].get(a, 0), result['p_team'].get(h, 0), result['p_none']
    return (f'<div class="ngbar"><i style="width:{pa * 100:.1f}%;background:{v5.colors(a)[0]}" title="{esc(a)} next goal {pct(pa)}"></i>'
            f'<i style="width:{ph * 100:.1f}%;background:{v5.colors(h)[0]}" title="{esc(h)} next goal {pct(ph)}"></i>'
            f'<i class="none" style="width:{pn * 100:.1f}%" title="No further goal {pct(pn)}"></i></div>'
            f'<div class="ngleg"><span>{esc(a)} {pct(pa)}</span><span>No further goal {pct(pn)}</span><span>{esc(h)} {pct(ph)}</span></div>')


def _st(badge, demo):
    return f'<div class="ngst">{badge}</div>' if demo else badge


def nextgoal_panel(result, season, label='', updated=None, demo=False, top=8, title=None, note='', venue=None, scored=None, replay=None):
    """'Live Next Goal' panel: score line, team split, top shooters with headshot, SOG, xG, conv %, next-goal %, rank change."""
    g = result['game']
    a, h = g['away'], g['home']
    sa, sh = g.get('away_score'), g.get('home_score')
    score = f'<b class="sc">{esc(sa, "0")}</b><span>–</span><b class="sc">{esc(sh, "0")}</b>' if result['phase'] != 'pregame' else '<span class="vs">VS</span>'
    rows = []
    for p in result['players'][:top]:
        rows.append(f'<div class="ngr" data-ng="ng-{esc(g.get("game_id"), "")}-{esc(p.get("pid"), "")}" style="--tc:{v5.colors(p["team"])[0]}"><span class="rk">{p.get("rank", "")}</span>{_arrow(p.get("delta"))}'
                    f'{_headshot(p, season)}<div class="ngn"><b>{esc(p["name"])}{sctn.badge_for(scored, p.get("pid"), p.get("name"))}</b><small>{esc(p["team"])} · {esc(p.get("pos"), "")}'
                    f'{" · prior: league" if p.get("prior_source") == "league" else ""}</small></div>'
                    f'<span class="ngs"><em>{p["sog"]}</em><small>SOG</small></span><span class="ngs"><em>{p["xg"]:.2f}</em><small>xG</small></span>'
                    f'<span class="ngs"><em>{p["conv"] * 100:.1f}%</em><small>conv</small></span>'
                    f'<span class="ngp"><em>{pct(p["p_next"])}</em><small>next goal</small><i style="width:{min(100, p["p_next"] * 400):.0f}%"></i></span></div>')
    if not rows:
        rows.append('<div class="ngempty">No skaters available for this game yet.</div>')
    head = title or f'{esc(a)} @ {esc(h)}'
    rsc = f'{sa if sa is not None else 0}–{sh if sh is not None else 0}' if replay else ''
    wrap = 'sec ngp-wrap ngp-demo' if demo else 'sec ngp-wrap'   # V5.9: demo-scoped spacing (assets/v58.css)
    return (f'<section class="{wrap}"><div class="ngh">{v5.logo(a, "tl")}<div class="ngt"><h3>{head}</h3>{vn.tag(venue)}'
            f'{_st(state_badge(result["phase"], label, updated, demo, replay, rsc), demo)}</div>'
            f'<div class="ngsc">{score}</div>{v5.logo(h, "tl")}</div>{team_bar(result)}'
            f'<div class="ngl">{"".join(rows)}</div>'
            f'<p class="ngnote">{esc(note, "")} Horizon {result["remaining"]:.1f} min · pace weight {result["pace_weight"]:.2f} · model estimate, uncalibrated, not betting advice.</p></section>')


def live_strip(items, jump=True):
    """Compact live strip: one chip per game with score/state and the model's current next-goal leader.
    jump=False (V5.9: the strip on the Live Next Goal tab itself) renders it without the tap-to-open-tab affordance."""
    if not items:
        return ''
    cells = []
    for it in items:
        lead = it.get('leader')
        idle = {'final': 'final · no next goal', 'shootout': 'shootout · not modelled', 'pregame': 'pregame prior in tab'}.get(it['phase'], 'model pending')
        who = f'<small>next: {esc(lead["name"].split(" ")[-1])} {pct(lead["p_next"], 0)}</small>' if lead else f'<small>{idle}</small>'
        pulse = '<i class="pulse"></i>' if it['phase'] == 'live' else ''
        cells.append(f'<div class="ls {esc(it["phase"])}">{pulse}{v5.logo(it["away"], "tl")}<b>{esc(it.get("away_score"), "")}</b>'
                     f'<span>{esc(it.get("label"), "")}</span><b>{esc(it.get("home_score"), "")}</b>{v5.logo(it["home"], "tl")}{who}{vn.tag(it.get("venue"))}</div>')
    n = sum(1 for it in items if it['phase'] == 'live')
    tag = f'<span class="live"><i class="pulse"></i>{n} live</span>' if n else '<span class="live pre">No game live</span>'
    # V5.9: the whole strip (heading + chips) is one tap/Enter target that opens the Live Next Goal tab (assets/v55.js data-ngtab).
    # jump=False: plain section (no data-ngtab / ngjump class / role / tabindex), so no click handler, pointer or hover affordance.
    if jump:
        head = '<section class="sec ngjump" data-ngtab="Live Next Goal" role="link" tabindex="0" aria-label="Open the Live Next Goal tab">'
        sub = 'Score endpoint + play-by-play · next-goal leader per game · tap to open the Live Next Goal tab for the full model'
    else:
        head = '<section class="sec">'
        sub = 'Score endpoint + play-by-play · next-goal leader per game'
    return (f'{head}<div class="sh"><h3>Live next goal {tag}</h3><p>{sub}</p></div><div class="lstrip">{"".join(cells)}</div></section>')


def h2h_text(h):
    if not h:
        return '<small class="h2h none">no H2H shots</small>'
    cls = 'hit' if h['goals'] else ''
    return f'<small class="h2h {cls}">H2H {h["goals"]} G / {h["sog"]} SOG · {h["games"]} gp</small>'


def goalie_threats(goalie, team, threats, season, coverage, top=5):
    rows = ''.join(f'<div class="gtr"><span class="rk">{t.get("rank", i)}</span>{_headshot(t, season)}<b>{esc(t["name"])}</b>'
                   f'<span class="ngp mini"><em>{pct(t.get("p_next"))}</em></span>{h2h_text(t.get("h2h"))}</div>'
                   for i, t in enumerate(threats[:top], 1))
    status = esc(goalie.get('status') or 'season stats')
    return (f'<div class="gtc" style="--tc:{v5.colors(team)[0]}"><div class="gth">{v5.logo(team, "tl")}<div><b>{esc(goalie.get("name"))}</b>'
            f'<small>{esc(team)} goalie · {status} · SV% {esc(goalie.get("sv"), "—")} · GAA {esc(goalie.get("gaa"), "—")}</small></div></div>'
            f'<p class="gtk">Opposing threats by V5.6 next-goal %</p>{rows or "<p>No opposing skaters.</p>"}'
            f'<p class="gtf">H2H {esc(coverage)}</p></div>')


def reverse_view(rows, season):
    """Each shooter -> his hardest goalie to beat (H2H when >= 3 SOG, else the opponent's best season SV%)."""
    out = []
    for r in rows:
        g = r.get('goalie') or {}
        basis = r.get('basis') or '—'
        h = g.get('h2h')
        detail = (f'{h["goals"]} G on {h["sog"]} SOG' if h else f'SV% {esc(g.get("sv"), "—")}') if g else 'no goalie data'
        out.append(f'<div class="rvr">{_headshot(r, season)}<b>{esc(r["name"])}</b><small>{esc(r["team"])}</small><span class="arrow">→</span>'
                   f'<b>{esc(g.get("name"), "—")}</b><small>{detail} · basis: {esc(basis)}</small></div>')
    return f'<div class="rvw">{"".join(out)}</div>'


def h2h_flag(flags, game_label):
    if not flags:
        return ''
    items = ''.join(f'<span class="flag">🚩 #{f.get("rank")} {esc(f["shooter"])} has {f["goals"]} G on {f["sog"]} SOG vs {esc(f["goalie"])}'
                    f' ({esc(f.get("goalie_status") or "probable")})</span>' for f in flags)
    return f'<div class="h2hf"><b>{esc(game_label)}</b>{items}</div>'


def threat_ring(p):
    return (f'<span class="tring" style="--c:{p["colour"]};--to:{p["threat"] * 3.6:.0f}deg" title="Threat {p["threat"]}/100">'
            f'<span class="tri">{p["number"]}</span></span>')


def num_game_board(board, day_num):
    g = board['game']
    arena = esc(g.get('arena') or 'Arena unavailable')
    arena_html = (f'<span class="arena hit" title="Matches: {esc(", ".join(board["arena_players"]))}">🏟 {arena} · {board["arena_root"]}</span>'
                  if board['arena_hit'] else f'<span class="arena">🏟 {arena} · {esc(board["arena_root"], "—")}</span>')
    rows = []
    for p in board['players']:
        sig = ''.join([f'<i class="sg d">D×{len(p["day"])}</i>' if p['day'] else '', f'<i class="sg a">A×{len(p["arena_matches"])}</i>' if p['arena_matches'] else '',
                       f'<i class="sg t">T×{len(p["team_matches"])}</i>' if p['team_matches'] else ''])
        rows.append(f'<div class="nbr t-{p["tier"]}" style="--c:{p["colour"]}">{threat_ring(p)}<div class="nbn"><b>{esc(p["player"])}</b>'
                    f'<small>{esc(p["team"])} · ENG {p["values"]["ordinal_root"]} · RED {p["values"]["reduction_root"]} · REV {p["values"]["reverse_root"]}</small></div>'
                    f'<span class="nbs">{sig}</span><span class="nbt">{p["threat"]}</span></div>')
    return (f'<section class="sec nbg"><div class="nbh">{v5.logo(g["away"], "tl")}<b>{esc(g["away"])} @ {esc(g["home"])}</b>{v5.logo(g["home"], "tl")}'
            f'<span class="nbb" title="Players with a threat score above 0">{board["badge"]} threats</span></div>'
            f'<div class="nbm"><span>Day {day_num}</span>{arena_html}</div><div class="nbl">{"".join(rows) or "<p>No ranked players.</p>"}</div></section>')


def _am(v):
    return '—' if v is None else f'{int(v):+d}'


def edge_card(game, flag, rows, season, label, scored=None):
    top = flag['top']
    a, h = game['away'], game['home']
    if top is None:
        body = '<p>No model rows yet.</p>'
    else:
        e = top['edge']
        tone = 'pos' if e is not None and e >= 0 else 'neg'
        if top['settled']:
            etxt = 'settled ✓ (already scored)' if top.get('outcome') and top['model_p'] is not None else ('game over · scored ✓' if top.get('outcome') else 'game over · no goal')
            tone = 'pos' if top.get('outcome') else 'neg'
        else:
            etxt = 'no line' if e is None else f'{e * 100:+.1f} pts'
        body = (f'<div class="efr top">{_headshot(top, season)}<div><b>{esc(top["name"])}{sctn.badge_for(scored, top.get("pid"), top.get("name"))}</b><small>#{top.get("rank")} next-goal · {esc(top["team"])}</small></div>'
                f'<span class="ngs"><em>{pct(top["model_p"])}</em><small>model p</small></span>'
                f'<span class="ngs"><em>{_am(top["american"])}</em><small>open line</small></span>'
                f'<span class="ngs"><em>{pct(top["implied"])}</em><small>implied</small></span>'
                f'<span class="edge {tone}">{etxt}</span></div>')
        more = ''.join(f'<span class="chip ok">{esc(r["name"])} {r["edge"] * 100:+.1f}</span>' for r in flag['other_flags'][:4])
        if more:
            body += f'<div class="efm">Other flagged: {more}</div>'
    fl = '<span class="flagb on">🚩 EDGE</span>' if flag['flagged'] else '<span class="flagb">no edge</span>'
    return (f'<div class="efc{" on" if flag["flagged"] else ""}"><div class="efh">{v5.logo(a, "tl")}<b>{esc(a)} @ {esc(h)}</b>{v5.logo(h, "tl")}{fl}'
            f'<small>{esc(label)}</small>{vn.tag(game.get("venue"))}</div>{body}</div>')
