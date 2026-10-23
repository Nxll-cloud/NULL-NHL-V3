"""V5.5 'neon arena' design system for Null's Playbook.

* Pure HTML builders (string in, string out; every dynamic value escaped) ported from the approved V5.5 preview.
* One global stylesheet (local woff2 fonts as @font-face data URIs + assets/v55.css + assets/v55_app.css + the
  chosen theme's overrides for native Streamlit widgets), injected once per run with st.markdown.
* html_block(): renders a fragment with st.html. Streamlit >= 1.52 runs the small motion script
  (unsafe_allow_javascript=True); older versions get the same markup statically (no JS), and versions without
  st.html fall back to st.markdown. Every number is rendered server-side, so the page is complete without JS.
* No fake navigation: tabs are native st.tabs; scoreboard tiles are not clickable.
"""
from __future__ import annotations

import base64
import functools
import html
import inspect
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import position_badge_v59 as pb   # V5.9: Home goalie pill
import goalie_weak_v59 as gw   # V5.9: goalie weak-spot pill (display only)
import winprob_v59 as wp   # V5.9: board favorite pill (model estimate)
import venue_v58 as vn

HERE = Path(__file__).resolve().parent
ASSETS = HERE / 'assets'
FONT_DIR = ASSETS / 'fonts'
ET = ZoneInfo('America/New_York')
CDN_LOGO = 'https://assets.nhle.com/logos/nhl/svg/{t}_light.svg'
CDN_MUG = 'https://assets.nhle.com/mugs/nhl/{season}/{t}/{pid}.png'
_TEAM_RE = re.compile(r'^[A-Z]{2,3}$')
_PID_RE = re.compile(r'^\d{5,9}$')

THEMES = {'Night': 'dark', 'Light': 'light', 'High contrast': 'contrast'}
DEFAULT_THEME = 'dark'
_state = {'theme': DEFAULT_THEME}

TEAM_COLORS = {
    'ANA': ('#F47A38', '#B9975B'), 'BOS': ('#FFB81C', '#000000'), 'BUF': ('#003087', '#FFB81C'),
    'CGY': ('#C8102E', '#F1BE48'), 'CAR': ('#CE1126', '#000000'), 'CHI': ('#CF0A2C', '#000000'),
    'COL': ('#6F263D', '#236192'), 'CBJ': ('#002654', '#CE1126'), 'DAL': ('#006847', '#8F8F8C'),
    'DET': ('#CE1126', '#FFFFFF'), 'EDM': ('#041E42', '#FF4C00'), 'FLA': ('#041E42', '#C8102E'),
    'LAK': ('#111111', '#A2AAAD'), 'MIN': ('#154734', '#A6192E'), 'MTL': ('#AF1E2D', '#192168'),
    'NSH': ('#FFB81C', '#041E42'), 'NJD': ('#CE1126', '#000000'), 'NYI': ('#00539B', '#F47D30'),
    'NYR': ('#0038A8', '#CE1126'), 'OTT': ('#C52032', '#C2912C'), 'PHI': ('#F74902', '#000000'),
    'PIT': ('#FCB514', '#000000'), 'SJS': ('#006D75', '#EA7200'), 'SEA': ('#001628', '#99D9D9'),
    'STL': ('#002F87', '#FCB514'), 'TBL': ('#002868', '#FFFFFF'), 'TOR': ('#00205B', '#FFFFFF'),
    'UTA': ('#6CACE4', '#010101'), 'VAN': ('#00205B', '#00843D'), 'VGK': ('#B4975A', '#333F42'),
    'WSH': ('#041E42', '#C8102E'), 'WPG': ('#041E42', '#004C97'),
}
TEAM_NAMES = {'ANA': 'Anaheim Ducks', 'BOS': 'Boston Bruins', 'BUF': 'Buffalo Sabres', 'CAR': 'Carolina Hurricanes', 'CBJ': 'Columbus Blue Jackets', 'CGY': 'Calgary Flames', 'CHI': 'Chicago Blackhawks', 'COL': 'Colorado Avalanche', 'DAL': 'Dallas Stars', 'DET': 'Detroit Red Wings', 'EDM': 'Edmonton Oilers', 'FLA': 'Florida Panthers', 'LAK': 'Los Angeles Kings', 'MIN': 'Minnesota Wild', 'MTL': 'Montreal Canadiens', 'NJD': 'New Jersey Devils', 'NSH': 'Nashville Predators', 'NYI': 'New York Islanders', 'NYR': 'New York Rangers', 'OTT': 'Ottawa Senators', 'PHI': 'Philadelphia Flyers', 'PIT': 'Pittsburgh Penguins', 'SEA': 'Seattle Kraken', 'SJS': 'San Jose Sharks', 'STL': 'St Louis Blues', 'TBL': 'Tampa Bay Lightning', 'TOR': 'Toronto Maple Leafs', 'UTA': 'Utah Mammoth', 'VAN': 'Vancouver Canucks', 'VGK': 'Vegas Golden Knights', 'WPG': 'Winnipeg Jets', 'WSH': 'Washington Capitals'}
DEFAULT_COLORS = ('#38bdf8', '#8b7bff')
POS = {'L': 'Left wing', 'R': 'Right wing', 'C': 'Centre', 'D': 'Defence', 'G': 'Goalie'}
LIVE_STATUSES = {'LIVE', 'CRIT'}
DONE_STATUSES = {'FINAL', 'OFF', 'OVER'}


# ============================================================== theme + assets

def set_theme(theme):
    _state['theme'] = theme if theme in THEMES.values() else DEFAULT_THEME
    return _state['theme']


def theme():
    return _state['theme']


def theme_from_label(label):
    return THEMES.get(label, DEFAULT_THEME)


_FONTS = [('Barlow Condensed', 600, 'normal', 'barlow-condensed-600.woff2'), ('Barlow Condensed', 700, 'normal', 'barlow-condensed-700.woff2'),
          ('Barlow Condensed', 800, 'normal', 'barlow-condensed-800.woff2'), ('Barlow Condensed', 800, 'italic', 'barlow-condensed-800i.woff2'),
          ('Inter', '400 700', 'normal', 'inter-var.woff2')]


@functools.lru_cache(maxsize=1)
def fonts_css():
    """@font-face rules with the bundled woff2 subsets as data URIs (no third-party font requests)."""
    out = []
    for fam, weight, style, name in _FONTS:
        path = FONT_DIR / name
        if not path.is_file():
            continue
        b64 = base64.b64encode(path.read_bytes()).decode()
        out.append(f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};font-display:swap;"
                   f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return ''.join(out)


@functools.lru_cache(maxsize=16)   # V5.8: more stylesheets (v58.css, mobile.css)
def _asset_text(name):
    try:
        return (ASSETS / name).read_text(encoding='utf-8')
    except OSError:
        return ''


def check_sanitizer_safe(name, src):
    """DOMPurify (st.html) silently drops a <style>/<script> whose text contains '<' followed by a letter, '/' or '!'."""
    if re.search(r'<[/\w!]', src):
        raise ValueError(f'v55 {name} contains a "<" sequence that st.html would strip')
    return src


def design_css(theme_name=None):
    t = theme_name or theme()
    css = fonts_css() + _asset_text('v55.css') + _asset_text('v55_app.css') + _asset_text('v56.css')
    css += _asset_text(f'v55_app_{t}.css') if t != 'dark' else ''
    css += _asset_text('v58.css') + _asset_text('mobile.css')   # V5.8: components + mobile layer (media queries only)
    return check_sanitizer_safe('css', css)


def page_style(theme_name=None):
    """The one global <style> block (st.markdown(..., unsafe_allow_html=True))."""
    t = theme_name or theme()
    return f'<style>{design_css(t)}</style><div class="v55-theme-flag" data-theme="{t}" hidden></div>'


def js():
    return check_sanitizer_safe('js', _asset_text('v55.js'))


# ============================================================== st.html guard

def html_mode(st_module):
    """'js' when st.html supports unsafe_allow_javascript (Streamlit >= 1.52), 'static' for older st.html,
    'markdown' when st.html is missing (Streamlit < 1.33)."""
    fn = getattr(st_module, 'html', None)
    if fn is None:
        return 'markdown'
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return 'static'
    return 'js' if 'unsafe_allow_javascript' in params else 'static'


def wrap(fragment, theme_name=None, extra_class='', script=False):
    t = theme_name or theme()
    tail = f'<script>{js()}</script>' if script else ''
    return f'<div class="v55 v55-app {extra_class}" data-theme="{esc(t)}">{fragment}{tail}</div>'


def html_block(st_module, fragment, theme_name=None, extra_class=''):
    """Render a V5.5 fragment. Returns the mode used ('js' | 'static' | 'markdown')."""
    mode = html_mode(st_module)
    if mode == 'js':
        st_module.html(wrap(fragment, theme_name, extra_class, script=True), unsafe_allow_javascript=True)
    elif mode == 'static':
        st_module.html(wrap(fragment, theme_name, extra_class))
    else:
        st_module.markdown(wrap(fragment, theme_name, extra_class), unsafe_allow_html=True)
    return mode


def inline(fragment, extra_class=''):
    """Small static V5.5 snippet for st.markdown (cards, chips, empty states)."""
    return wrap(fragment, None, 'v55i ' + extra_class)


# ============================================================== primitives

def esc(v, default='—'):
    if v is None or (isinstance(v, float) and v != v) or v == '':
        return html.escape(default)
    s = str(v)
    if s.strip().lower() in ('nan', 'none', '<na>'):
        return html.escape(default)
    return html.escape(s)


def team_code(t):
    t = str(t or '').strip().upper()
    return t if _TEAM_RE.match(t) else ''


def pid_str(pid):
    try:
        s = str(int(float(pid)))
    except (TypeError, ValueError):
        return ''
    return s if _PID_RE.match(s) else ''


def _lum(hex_):
    h = hex_.lstrip('#'); r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def colors(t):
    return TEAM_COLORS.get(team_code(t), DEFAULT_COLORS)


def team_vars(t):
    """CSS custom props: --p primary, --s secondary, --a accent (the brighter non-white/black colour)."""
    p, s = colors(t)
    cands = [c for c in (p, s) if 0.08 < _lum(c) < 0.92] or [p]
    a = max(cands, key=_lum) if _lum(p) < 0.12 else p
    return f'--p:{p};--s:{s};--a:{a}'


def _accent(t):
    return dict(x.split(':') for x in team_vars(t).replace('--', '').split(';'))['a']


def logo(t, cls='lg'):
    t = team_code(t)
    if not t:
        return f'<span class="{cls} lg-ph"></span>'
    return f'<img class="{cls}" src="{CDN_LOGO.format(t=t)}" alt="{t} logo" loading="lazy"/>'


def mug(season, t, pid, cls='mug'):
    t, pid = team_code(t), pid_str(pid)
    if not (t and pid):
        return f'<div class="{cls} mug-ph">🏒</div>'
    return f'<img class="{cls}" src="{CDN_MUG.format(season=esc(season, ""), t=t, pid=pid)}" alt="" loading="lazy"/>'


def parse_iso(iso):
    try:
        d = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def et_time(iso):
    d = parse_iso(iso)
    return d.astimezone(ET).strftime('%-I:%M %p ET') if d else 'Time TBD'


def game_state(game_or_iso, now):
    """'live' | 'done' | 'pre'. The game's own Status (NHL gameState) wins; the start time is the fallback."""
    status, iso = '', game_or_iso
    if isinstance(game_or_iso, dict):
        status = str(game_or_iso.get('status') or game_or_iso.get('Status') or '').upper()
        iso = game_or_iso.get('start') or game_or_iso.get('Start (UTC)')
    if status in LIVE_STATUSES:
        return 'live'
    if status in DONE_STATUSES:
        return 'done'
    start = parse_iso(iso)
    if start is None:
        return 'pre'
    if status in ('FUT', 'PRE') and now < start + timedelta(hours=3, minutes=15):
        return 'pre' if now < start else 'starting'
    if now >= start + timedelta(hours=3, minutes=15):
        return 'done'
    return 'live' if now >= start else 'pre'


def until(iso, now):
    start = parse_iso(iso)
    if start is None:
        return '—'
    mins = int((start - now).total_seconds() // 60)
    return f'{mins // 60}h {mins % 60:02d}m' if mins >= 60 else f'{max(mins, 0)}m'


def count(value, suffix='', decimals=0, cls='num'):
    """Number that counts up client-side; the server renders the final value (no-JS safe)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f'<span class="{cls}">—</span>'
    if v != v:
        return f'<span class="{cls}">—</span>'
    shown = f'{v:.{decimals}f}{suffix}'
    return f'<span class="{cls}" data-count="{v}" data-dec="{decimals}" data-suffix="{esc(suffix, "")}">{esc(shown)}</span>'


def form_count(pct, label, cls='num'):
    """Form % keeps V5.4 semantics: clip(index, 0, 100); '100%+' when the raw index exceeds the benchmark."""
    if pct is None:
        return f'<span class="{cls}">—</span>'
    return count(round(pct), '%+' if label == '100%+' else '%', 0, cls)


def _mix(c1, c2, k):
    a = [int(c1.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]; b = [int(c2.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    return '#' + ''.join(f'{round(x * (1 - k) + y * k):02x}' for x, y in zip(a, b))


def _spark_svg(vals, goals, w, h, line, fill, dot):
    top = max(max(vals), 4); n = len(vals); step = w / max(n - 1, 1)
    pts = [(i * step, h - 4 - (v / top) * (h - 10)) for i, v in enumerate(vals)]
    ln = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
    dots = ''.join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{2.6 + 1.1 * min(g, 3)}" fill="#fff" stroke="{dot}" stroke-width="2.4"/>' for (x, y), g in zip(pts, goals) if g)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {w + 8} {h + 8}" width="{w + 8}" height="{h + 8}">'
            f'<defs><linearGradient id="f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{fill}" stop-opacity=".45"/><stop offset="1" stop-color="{fill}" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="0,{h} {ln} {w},{h}" fill="url(#f)"/><polyline points="{ln}" fill="none" stroke="{line}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>{dots}</svg>')


def _int(x):
    try:
        return int(x or 0)
    except (TypeError, ValueError):
        return 0


def sparkline(log, w=150, h=40, team=None, key='shots'):
    """Last-10 shots line with goal games as dots, as data-URI images (st.html strips inline <svg>).
    Two colour variants (dark/light); CSS shows the right one."""
    if not log:
        return '<div class="spark-empty">Game log unavailable</div>'
    vals = [_int(g.get(key)) for g in log]; goals = [_int(g.get('goals')) for g in log]
    a = _accent(team) if team else '#38e1ff'
    title = html.escape('Shots per game, last %d: %s; goals: %s' % (len(vals), ' '.join(map(str, vals)), ' '.join(map(str, goals))))
    out = ''
    for cls, line, fill, dot in (('sd', _mix(a, '#ffffff', .45), a, '#ff3d7f'), ('sl', _mix(a, '#000000', .15), a, '#d6145a')):
        b64 = base64.b64encode(_spark_svg(vals, goals, w, h, line, fill, dot).encode()).decode()
        out += f'<img class="spark {cls}" src="data:image/svg+xml;base64,{b64}" alt="{title}" title="{title}"/>'
    return f'<div class="sparkw">{out}</div>'


def heat_strip(log, big=False):
    """One cell per game (last 10): heat = shots, number = goals."""
    if not log:
        return ''
    cells = []
    for g in log:
        s, gl = _int(g.get('shots')), _int(g.get('goals'))
        cells.append(f'<i class="hc{" goal" if gl else ""}" style="--h:{min(s / 6, 1):.2f}" title="{esc(g.get("date"))} vs {esc(g.get("opp"))}: {s} SOG, {gl} G">'
                     f'{"<b>" + str(gl) + "</b>" if gl else ""}</i>')
    return f'<div class="heat{" big" if big else ""}">{"".join(cells)}</div>'


def ring(rate, label, sub, size=150, cls=''):
    """Hit-rate ring as a CSS conic-gradient (no inline SVG); empty ('—') when there is no graded data."""
    pct = None if rate is None else rate * 100
    return (f'<div class="ring {cls}{" none" if pct is None else ""}"><div class="rgw" style="--sz:{size}px"><div class="rg" style="--to:{0 if pct is None else pct * 3.6:.1f}deg"></div>'
            f'<div class="rc">{count(None if pct is None else round(pct), "%", 0, "rnum")}<small>{esc(label)}</small></div></div><p>{esc(sub)}</p></div>')


def chip(text, tone=''):
    return f'<span class="chip {esc(tone, "")}">{esc(text)}</span>'


def chips(items):
    return ''.join(chip(t, tone) for t, tone in items)


def chip_row(items):
    return inline(f'<div class="cats crow">{chips(items)}</div>')


_chips_html = chips  # alias: tab_head's `chips` parameter shadows the function


def logo_mark():
    import ui_theme_v53 as ui
    uri = ui.logo_data_uri('mark')
    return f'<img class="v55-mark" src="{uri}" alt="{esc(ui.BRAND_NAME)}"/>' if uri else ''


# ============================================================== generic tab pieces (st.markdown)

TONE_MAP = {'muted': '', 'stat': 'stat', 'gem': 'gem', 'odds': 'odds', 'overlap': 'overlap', 'ok': 'ok', 'warn': 'warn', 'day': 'gem', 'team': 'neon', 'arena': 'overlap'}
TAB_TONES = {'stat': ('#ffd24a', '#ff8a3d'), 'odds': ('#38e1ff', '#4f7bff'), 'gem': ('#c08bff', '#ff3d7f'), 'overlap': ('#35f0c0', '#38e1ff'), 'neon': ('#38e1ff', '#b26bff')}


def tab_head(kicker, title, sub='', chips=(), tone='neon', logo=True, team=None):
    """Tab hero in the V5.5 style; drop-in for ui_theme_v53.hero(kicker, title, subtitle, chips, tone)."""
    chip_items = [(t, TONE_MAP.get(c, c)) for t, c in chips]
    a, b = colors(team) if team else TAB_TONES.get(tone, TAB_TONES['neon'])
    return inline(f'''<header class="th" style="--pa:{a};--pb:{b}"><i class="th-beam"></i>
<div class="th-top">{logo_mark() if logo else ''}<span class="kicker">{esc(kicker)}</span></div>
<h2 class="th-title">{esc(title)}</h2>{f'<p class="th-sub">{esc(sub)}</p>' if sub else ''}
<div class="cats">{_chips_html(chip_items)}</div></header>''')


def sec_head(title, sub=''):
    return inline(f'<div class="sh mini"><h3>{esc(title)}</h3>{f"<p>{esc(sub)}</p>" if sub else ""}</div>')


def empty_state(title, body, glyph='—'):
    return inline(f'<div class="empty-st glass"><span class="ghost">{esc(glyph)}</span><div><b>{esc(title)}</b><p>{esc(body)}</p></div></div>')


def kpi_strip(items):
    cells = ''.join(f'<div class="kp {esc(tone, "")}"><span class="lbl">{esc(label)}</span><strong>{esc(value)}</strong></div>' for label, value, tone in items)
    return inline(f'<div class="kps">{cells}</div>')


def foot(text):
    return inline(f'<footer class="foot">{logo_mark()}<span>{esc(text)}</span></footer>')


def bet_head(name, badge_text, away, home, edge):
    tone = 'pos' if edge > 0 else 'neg'
    return inline(f'''<div class="bh" style="--pa:{colors(away)[0]};--ph:{colors(home)[0]}">{logo(away, "bl")}{logo(home, "bl") if home and home != away else ""}
<div class="bht"><b>{esc(name)}</b><span class="chip demo">{esc(badge_text)}</span></div><span class="edge {tone}">{'▲' if edge > 0 else '▼'}</span></div>''')


def stamp_row(s, edge_txt, stake_txt, odds_txt):
    return inline(f'''<div class="sr"><b>{esc(s.get("name"))}</b>
<div class="cats">{chip("Edge " + edge_txt, "neon")}{chip("Stake " + stake_txt, "ok")}{chip(f"{s.get('book')} {odds_txt}", "")}{chip(s.get("source") or "demo", "demo")}</div>
<small>Stamped {esc(s.get("stamped_label") or s.get("stamped_at"))}</small></div>''')


# ============================================================== Home / Matchup sections (st.html)

def _goalie_line(s):
    sv = s.get('SV%') if s else None
    try:
        sv = ('%.3f' % float(sv)).lstrip('0')
    except (TypeError, ValueError):
        sv = '—'
    return sv


def hero(data, now):
    fg = data.get('featured')
    if not fg:
        return f'''<section class="hero empty"><div class="hero-top"><span class="hero-brand">{logo_mark()}<span class="kicker">Featured matchup · {esc(data.get("day"))}</span></span></div>
<div class="ebody"><h2>No NHL games on this slate</h2><p>Pick another date above. Nothing is invented when the schedule is empty.</p></div></section>'''
    a, h = fg['away'], fg['home']; season = data.get('season')
    lead = (data.get('leaders') or {}).get('statistical')
    state = game_state(fg, now)
    if state == 'live':
        when = '<span class="live"><i class="pulse"></i>Live now · NHL game state</span>'
    elif state == 'done':
        when = '<span class="when done">Final</span>'
    elif state == 'starting':
        when = '<span class="when"><i class="pulse"></i>Puck drop due · awaiting NHL live state</span>'
    else:
        when = f'<span class="when" data-start="{esc(fg.get("start"), "")}"><i class="pulse"></i>Puck drop in <b class="cd">{until(fg.get("start"), now)}</b></span>'

    def duel(t):
        g = (data.get('goalies') or {}).get(t) or {}
        s = g.get('starter_stats') or {}
        lab = g.get('starter_label') or 'Team goalie stats — starter not yet announced'
        tone = 'ok' if 'Confirmed' in lab else ('warn' if 'Probable' in lab else '')
        name = s.get('Goalie') or (g.get('starter') or {}).get('goalie') or 'Starter TBD'
        gb = pb.goalie_badge(pb.position_of(s) or pb.position_of(g.get('starter')))   # V5.9: 'G' pill from feed position data
        return f'''<div class="duel-g" style="{team_vars(t)}">{mug(season, t, s.get("Player ID"), "gmug")}
<div><span class="chip {tone}">{esc(lab)}</span><b>{esc(name)}{gb}</b>
<div class="gl"><span>{count(s.get("GAA"), "", 2, "gnum")}<small>GAA</small></span><span><em class="gnum">{_goalie_line(s)}</em><small>SV%</small></span><span>{count(s.get("GP"), "", 0, "gnum")}<small>GP</small></span></div></div></div>'''

    if lead:
        cats = [p['label'].title() for p in (data.get('picks') or {}).values() if p and pid_str(p.get('player_id')) == pid_str(lead.get('player_id'))]
        opp = lead.get('opponent') or (h if lead.get('team') == a else a)
        feature = f'''<div class="feature glass" style="{team_vars(lead["team"])}">
<div class="fmug">{mug(season, lead["team"], lead.get("player_id"), "bigmug")}<span class="jersey">{esc(lead.get("jersey"), "")}</span></div>
<div class="fbody"><span class="kicker">Tonight’s top target</span>
<h1>{f'<small>#{esc(lead.get("jersey"))}</small>' if lead.get("jersey") else ''}{esc(lead.get("player"))}{pb.goalie_badge(lead.get("position"))}</h1>
<p class="fmeta">{logo(lead["team"], "mini")}<span>{esc(lead["team"])} vs {esc(opp)}</span><span>{esc(POS.get(lead.get("position"), lead.get("position")))}</span></p>
<div class="cats lead">{chip("Top statistical", "neon")}{"".join(chip(c, "neon") for c in cats)}</div><span class="leads">Stat rank #{esc(lead.get("stat_rank"))} · leads {len(cats) + 1} of 8 categories</span></div>
<div class="fnum"><span class="lbl">Goal-scoring Form %</span>{form_count(lead.get("form_pct"), lead.get("form_label"), "mega")}
<span class="sub">{esc(_fmt(lead.get("shots_l5")))} shots/g · {esc(_fmt(lead.get("goals_l5"), 2))} goals/g (last 5)</span></div>
<div class="ftrend"><span class="lbl">Last {len(lead.get("log") or [])} · shots &amp; goals</span>{sparkline(lead.get("log"), 300, 70, lead["team"])}{heat_strip(lead.get("log"), True)}</div></div>'''
    else:
        feature = '''<div class="feature glass empty"><div class="ebody"><b>Rankings are still loading</b><p>The top target appears when this slate’s rankings are available — nothing is shown until then.</p></div></div>'''
    src = ((data.get('goalies') or {}).get(a) or {}).get('starter') or {}
    return f'''<section class="hero" style="--pa:{colors(a)[0]};--pa2:{colors(a)[1]};--ph:{colors(h)[0]};--ph2:{colors(h)[1]}">
<div class="hero-bg"><i class="beam b1"></i><i class="beam b2"></i><i class="ice"></i>{logo(a, "wm wm-a")}{logo(h, "wm wm-h")}</div>
<div class="hero-top"><span class="hero-brand">{logo_mark()}<span class="kicker">Featured matchup · {esc(data.get("day"))}</span></span>{when}</div>
<div class="versus"><div class="side" style="{team_vars(a)}">{logo(a, "hlogo")}<div><small>Away</small><h2>{esc(TEAM_NAMES.get(a, a))}</h2></div></div>
<div class="vs"><b>VS</b><span>{et_time(fg.get("start"))}</span>{_vs_arena(fg)}</div>
<div class="side home" style="{team_vars(h)}"><div><small>Home</small><h2>{esc(TEAM_NAMES.get(h, h))}</h2></div>{logo(h, "hlogo")}</div></div>
{vn.tag(fg.get("venue"), "vn hvn")}{feature}
<div class="duel"><span class="lbl">Goalie duel · {esc(src.get("source"), "no starter feed yet")}</span>{duel(a)}<b class="dvs">vs</b>{duel(h)}</div></section>'''


def _fmt(v, dp=1):
    try:
        return f'{float(v):.{dp}f}'
    except (TypeError, ValueError):
        return None


def scoreboard(data, now):
    games = data.get('games') or []
    if not games:
        return ''
    fk = (data.get('featured') or {}).get('key')
    tiles = []
    for g in games:
        a, h = g['away'], g['home']; s = game_state(g, now)
        sts = (data.get('starters') or {}).get(g['key'], {}) or {}

        def gl(t):
            x = sts.get(t) or {}; stt = x.get('status', 'unknown')
            mark = {'confirmed': '<i class="dot ok"></i>', 'probable': '<i class="dot warn"></i>'}.get(stt, '<i class="dot"></i>')
            gb = pb.goalie_badge(pb.position_of(x)) if x.get("goalie") else ''   # V5.9: surname truncates, pill never clips
            return f'<span class="sg"><span class="sgn">{mark}{esc((x.get("goalie") or "TBD").split(" ")[-1])}</span>{gb}</span>'
        sc = (data.get('scores') or {}).get(g['key'])  # V5.6: live/final score from the score endpoint or PBP
        clk = f'<span class="clk">{esc(sc.get("label"), "")}</span>' if sc and s == 'live' else ''
        badge = (f'<span class="st live"><i class="pulse"></i>Live{clk}</span>' if s == 'live' else
                 f'<span class="st">{esc(sc.get("label"), "Final") if sc else "Final"}</span>' if s == 'done' else f'<span class="st">{et_time(g.get("start"))}</span>')
        sa = f'<span class="scr">{esc(sc.get("away"), "")}</span>' if sc else ''
        sh = f'<span class="scr">{esc(sc.get("home"), "")}</span>' if sc else ''
        tiles.append(f'''<div class="tile{" feat" if g["key"] == fk else ""}" style="--pa:{colors(a)[0]};--ph:{colors(h)[0]}">
{badge}<div class="row">{logo(a, "tl")}<b>{esc(a)}</b>{gl(a)}{sa}</div><div class="row">{logo(h, "tl")}<b>{esc(h)}</b>{gl(h)}{sh}</div>{wp.pill((data.get("winprob") or {}).get(g["key"]))}{vn.tag(g.get("venue"), "vn tvn")}</div>''')
    live = sum(1 for g in games if game_state(g, now) == 'live')
    status = f'<span class="live"><i class="pulse"></i>{live} live</span>' if live else ''
    return f'''<section class="sec"><div class="sh"><h3>Tonight’s board {status}</h3><p>{len(games)} games · goalie dots: <i class="dot ok"></i>confirmed <i class="dot warn"></i>expected <i class="dot"></i>not announced · open any game in Matchup Center{wp.legend(data.get('winprob'))}</p></div>
<div class="board">{"".join(tiles)}</div></section>'''


def player_card(season, kind, tone, p, metric_html, caption, chip_html, big=False, empty_title=None, empty_body=None):
    if p is None:
        return f'''<article class="pc empty {tone}"><span class="kind">{esc(kind)}</span><span class="ghost">{"$" if tone == "odds" else "—"}</span><div class="ebody"><b>{esc(empty_title or "Load sportsbook odds to unlock")}</b><p>{esc(empty_body or "No eligible player — this category stays empty until real prices are imported. Nothing is invented.")}</p></div></article>'''
    return f'''<article class="pc {tone}{" big" if big else ""}{pb.goalie_row_class(p.get("position"))}" style="{team_vars(p.get("team"))}">
<span class="kind">{esc(kind)}</span><span class="jbg">{esc(p.get("jersey"), "")}</span>
{mug(season, p.get("team"), p.get("player_id"), "pmug")}
<div class="pcb"><h4>{esc(p.get("player"))}{pb.goalie_badge(p.get("position"))}</h4><p>{logo(p.get("team"), "mini")} {esc(p.get("team"))} · vs {esc(p.get("opponent"))}{" · #" + esc(p.get("jersey")) if p.get("jersey") else ""}</p>
<div class="pm">{metric_html}<small>{esc(caption, "")}</small></div>
{sparkline(p.get("log"), 220, 34, p.get("team"))}{heat_strip(p.get("log"))}
<div class="cats">{chip_html}</div></div></article>'''


def leaders_row(data):
    L, P, season = data.get('leaders') or {}, data.get('picks') or {}, data.get('season')
    lead = L.get('statistical')
    lead_id = pid_str((lead or {}).get('player_id'))
    cards = []
    g = L.get('gematria')
    cards.append(player_card(season, 'Gematria leader', 'gem', g, count(g.get('matches'), '', 0, 'pnum') if g else '', 'symbolic matches',
                             chips([(f'Day {g["day_n"]}', 'gem'), (f'Team {g["team_n"]}', 'gem'), (f'Arena {g["arena_n"]}', 'gem'), (f'Form {g["form_label"]}', '')]) if g else '',
                             empty_title='No gematria leader yet', empty_body='Appears when this slate’s rosters are ranked.'))
    o = L.get('overlap')
    cards.append(player_card(season, 'Stats + Numbers', 'overlap', o,
                             (count(o.get('matches'), '', 0, 'pnum') + f'<em class="sep">·</em>{form_count(o.get("form_pct"), o.get("form_label"), "pnum")}') if o else '',
                             'matches · Form %', chips([('Stats', 'stat'), ('Numbers', 'gem')]) if o else '',
                             empty_title='No overlap player', empty_body='No player is both a top-form and a ≥2-match numbers pick on this slate.'))
    for k, p in P.items():
        if p and pid_str(p.get('player_id')) != lead_id:
            flags = p.get('flags') or 0
            cards.append(player_card(season, str(p.get('label', '')).title(), 'stat', p, form_count(p.get('form_pct'), p.get('form_label'), 'pnum'), 'Form %',
                                     chips([(f'Stat rank #{esc(p.get("stat_rank"))}', 'stat'), (f'{flags} storyline flag' + ('' if flags == 1 else 's'), 'gem')])))
    od = L.get('odds')
    if od:
        cards.append(player_card(season, 'Price-gap leader', 'odds', od, f'<span class="pnum">{esc(od.get("best_odds_label"))}</span>',
                                 f'best at {esc(od.get("best_sportsbook"), "sportsbook")}', chips([(f'+{_fmt(od.get("gap_pct"))}% gap', 'odds'), ('Unverified identity', '')])))
    else:
        cards.append(player_card(season, 'Price-gap leader', 'odds', None, '', '', ''))
    n = 1 + sum(1 for p in P.values() if p and pid_str(p.get('player_id')) == lead_id) if lead else 0
    lede = (f'<b>{esc(lead.get("player"))}</b> leads {n} of 8 categories and is featured above; the rest are tonight’s other distinct names.'
            if lead else 'Leaders appear when this slate’s rankings load. Empty categories stay empty.')
    return f'''<section class="sec"><div class="sh"><h3>Leaders &amp; intelligence</h3><p>Four Leaders + Player Intelligence, merged by player. {lede}</p></div>
<div class="prow np-intel-row">{"".join(cards)}</div></section>'''


def track_section(track, title='Track record'):
    """Real tracker data only. track = {'r7','r30','all' (trk.rolling dicts), 'trend': [...], 'demo': bool, 'pending': int}."""
    track = track or {}
    r7, r30, ra = (track.get(k) or {'rate': None, 'hits': 0, 'picks': 0, 'slates': 0} for k in ('r7', 'r30', 'all'))
    demo = '<span class="chip demo">DEMO DATA in store</span>' if track.get('demo') else ''
    graded = ra.get('slates') or 0
    if not graded:
        lede = f'No graded slates yet — rings fill in after results are entered or imported below. {track.get("pending", 0)} slate(s) pending.'
    else:
        lede = (f'{graded} graded slate(s) · {ra.get("hits", 0)}/{ra.get("picks", 0)} picks hit · {track.get("pending", 0)} pending slate(s) excluded. '
                'Form % is a relative index, not a probability.')
    trend = track.get('trend') or []
    bars = ''.join(f'<i style="--v:{(e.get("rate") or 0):.2f}" title="{esc(e.get("day"))}: {e.get("hits", 0)}/{e.get("picks", 0)}"></i>' for e in trend)
    bars_html = f'<div class="bars">{bars}</div>' if bars else '<div class="bars none"><span>No graded slates yet</span></div>'
    return f'''<section class="sec track"><div class="sh"><h3>{esc(title)} {demo}</h3><p>{esc(lede)}</p></div>
<div class="trk glass">{ring(r7.get("rate"), "last 7", f'{r7.get("hits", 0)}/{r7.get("picks", 0)} picks hit', 170, "main")}{ring(r30.get("rate"), "last 30", f'{r30.get("hits", 0)}/{r30.get("picks", 0)}', 120)}{ring(ra.get("rate"), "all time", f'{graded} slates', 120)}
<div class="tbars"><span class="lbl">Hit rate by slate</span>{bars_html}</div></div></section>'''


def goalie_card(season, team, g, kind):
    g = g or {}
    if kind == 'starter':
        s = g.get('starter_stats'); lab = g.get('starter_label')
        if not s:
            return '<div class="gc unknown"><span class="chip">Team goalie stats — starter not yet announced</span></div>'
        st_ = g.get('starter') or {}
        at = str(st_.get('fetched_at') or '')[11:16]
        tone = 'ok' if 'Confirmed' in (lab or '') else 'warn'
        head = f'<span class="chip {tone}">{esc(lab)}</span><small>{esc(st_.get("source"), "feed")} · fetched {esc(at)} UTC</small>'
    else:
        s = g.get('leakiest')
        if not s:
            return '<div class="gc unknown"><span class="chip">No team goalie stats</span></div>'
        head = '<span class="chip leak">Team stats · leakiest by GAA</span><small>not necessarily tonight’s starter</small>'
    return f'''<div class="gc {kind}" style="{team_vars(team)}">{mug(season, team, s.get("Player ID"), "gcm")}<div class="gcb">{head}<b>{esc(s.get("Goalie"))}{pb.goalie_badge(pb.position_of(s))}</b>
<div class="gl"><span>{count(s.get("GA"), "", 0, "gnum")}<small>GA</small></span><span>{count(s.get("GAA"), "", 2, "gnum")}<small>GAA</small></span><span><em class="gnum">{_goalie_line(s)}</em><small>SV%</small></span><span>{count(s.get("GP"), "", 0, "gnum")}<small>GP</small></span></div></div></div>'''


BADGE_TONES = {'Stats': 'stat', 'Numbers': 'gem', 'Overlap': 'overlap', 'Intel pick': 'neon'}


def target_row(season, i, p):
    bar = p.get('form_pct') or 0
    badges = ''.join(chip(b, BADGE_TONES.get(b, 'odds' if str(b).startswith('Odds') else '')) for b in p.get('badges', []))
    matches = f" · {p['matches']} number matches" if p.get('matches') else ''
    return f'''<li class="tr{pb.goalie_row_class(p.get("position"))}" style="{team_vars(p.get("team"))}"><span class="rk">{i}</span>{mug(season, p.get("team"), p.get("player_id"), "tm")}
<div class="tn"><b>{esc(p.get("player"))}{pb.goalie_badge(p.get("position"))}</b><small>#{esc(p.get("jersey"), "?")} · Stat rank #{esc(p.get("stat_rank"))}{esc(matches, "")}</small>
<div class="cats">{badges}</div></div>
<div class="tf">{form_count(p.get("form_pct"), p.get("form_label"), "tnum")}<div class="fbar"><i style="--w:{min(bar, 100):.0f}%"></i></div></div>
<div class="tt">{sparkline(p.get("log"), 120, 30, p.get("team"))}{heat_strip(p.get("log"))}</div>{gw.row_cell(p.get("goalie_weak"))}</li>'''


def matchup_section(data, title=None, limit=5):
    fg = data.get('featured')
    if not fg:
        return ''
    season = data.get('season'); weak = data.get('weak_side')
    order = [weak] + [t for t in (fg['away'], fg['home']) if t != weak] if weak else [fg['away'], fg['home']]
    cols = []
    for t in order:
        opp = fg['home'] if t == fg['away'] else fg['away']
        og = (data.get('goalies') or {}).get(opp) or {}
        lst = (data.get('targets') or {}).get(t, [])[:limit]
        rows = ''.join(target_row(season, i, p) for i, p in enumerate(lst, 1)) or \
            '<li class="tr none"><span>Player targets appear once this slate’s rankings load.</span></li>'
        cols.append(f'''<div class="mcol" style="{team_vars(t)}"><div class="mhead">{logo(t, "ml")}<div><h4>{esc(TEAM_NAMES.get(t, t))} shooters</h4><p>vs {esc(opp)} goaltending</p></div>
{'<span class="chip leak">▲ Faces the leakier goalie (by GAA)</span>' if t == weak else ''}{gw.team_chip(og.get('weak_team'))}</div>
<div class="gcs">{goalie_card(season, opp, og, "starter")}{goalie_card(season, opp, og, "leaky")}</div><ol class="tl">{rows}</ol></div>''')
    head = title or f'Matchup targets · {esc(fg["away"])} @ {esc(fg["home"])}{vn.tag(fg.get("venue"))}'
    gw_note = gw.legend(data)   # V5.9: one-line basis for the 'vs G' pills, only when one is shown
    return f'''<section class="sec mc"><div class="sh"><h3>{head}</h3><p>Both rosters ranked by Form % · bars are Form % (0–100) · strips are the last 10 games (heat = shots, number = goals) · none of this is a probability{gw_note}</p></div>
<div class="mgrid">{"".join(cols)}</div></section>'''


def _vs_arena(g):
    """Desktop arena under the VS (mobile shows the .hvn line under the teams instead). '' when the arena is unknown."""
    a = vn.clean((g or {}).get('venue'))
    return f'<em title="{esc(a)}">{vn.PIN} {esc(a)}</em>' if a else ''


def versus_bar(game, now):
    a, h = game['away'], game['home']
    s = game_state(game, now)
    when = ('<span class="live"><i class="pulse"></i>Live</span>' if s == 'live' else '<span class="when done">Final</span>' if s == 'done'
            else f'<span class="when" data-start="{esc(game.get("start"), "")}"><i class="pulse"></i>Puck drop in <b class="cd">{until(game.get("start"), now)}</b></span>')
    return f'''<section class="hero vbar" style="--pa:{colors(a)[0]};--pa2:{colors(a)[1]};--ph:{colors(h)[0]};--ph2:{colors(h)[1]}">
<div class="hero-bg"><i class="beam b1"></i><i class="beam b2"></i><i class="ice"></i>{logo(a, "wm wm-a")}{logo(h, "wm wm-h")}</div>
<div class="hero-top"><span class="kicker">Matchup Center</span>{when}</div>
<div class="versus"><div class="side" style="{team_vars(a)}">{logo(a, "hlogo")}<div><small>Away</small><h2>{esc(TEAM_NAMES.get(a, a))}</h2></div></div>
<div class="vs"><b>VS</b><span>{et_time(game.get("start"))}</span>{_vs_arena(game)}</div>
<div class="side home" style="{team_vars(h)}"><div><small>Home</small><h2>{esc(TEAM_NAMES.get(h, h))}</h2></div>{logo(h, "hlogo")}</div></div>{vn.tag(game.get("venue"), "vn hvn")}</section>'''


def footer(data):
    snap = data.get('snapshot_at')
    snap_txt = f'NHL snapshot {esc(str(snap)[:16].replace("T", " "))} UTC' if snap else 'Live NHL fallback (no saved snapshot)'
    st_at = str(data.get('starters_fetched_at') or '')[11:16]
    return (f'<footer class="foot">{logo_mark()}<span>Data: {snap_txt} · {data.get("n_ranked", 0)} ranked players · NHL club-stats goalies · '
            f'ESPN probables{" fetched " + esc(st_at) + " UTC" if st_at else ""} · NHL game logs &amp; rosters. '
            f'Form % = clip(V3.2 index, 0, 100); not a probability. Research only, not betting advice.</span></footer>')


def render_home(data, now=None):
    """Home fragment: scoreboard + hero + leaders + featured matchup + footer (V5.8: board above hero; no track record)."""
    now = now or datetime.now(timezone.utc)
    # V5.8: the track-record rings live only in the Track Record tab (track_section is rendered there).
    # V5.8: Tonight's board sits directly above the Featured matchup hero (single swap; everything else in V5.7 order).
    # V5.8: the Top four-leg parlay (data['parlay_html'], price-free) sits directly below the Featured matchup hero.
    return (scoreboard(data, now) + hero(data, now) + (data.get('threat_html') or '')  # V5.9: top-threat badges under the hero
            + (data.get('parlay_html') or '') + leaders_row(data)
            + (data.get('longshot_html') or '')  # V5.8: Top long shot candidate, directly under Leaders & intelligence
            + (data.get('odds_scorers_html') or '')  # V5.9: Projected scorers (odds), directly above Matchup targets
            + matchup_section(data) + footer(data))
