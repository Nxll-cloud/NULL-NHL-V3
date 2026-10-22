"""V5.3 design system: one stylesheet plus small, escaped HTML builders.

All builders are pure functions (string in, string out) so they can be unit
tested without Streamlit. Every dynamic value is HTML-escaped; image URLs are
only produced for well-formed NHL team codes and numeric player IDs.
"""
import html as _html
import math
import re

NHL_SEASON_DEFAULT = '20262027'
_TEAM_RE = re.compile(r'^[A-Z]{2,3}$')

# Signal tones are used consistently across Home, Numbers and Odds.
TONES = ('stat', 'gem', 'odds', 'overlap', 'warn', 'ok', 'muted', 'day', 'team', 'arena')


def esc(value, fallback=''):
    """Escape for HTML; None/NaN become the fallback, never the text 'nan'."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return _html.escape(fallback)
    text = str(value)
    if text.strip().lower() in ('nan', 'none', '<na>'):
        return _html.escape(fallback)
    return _html.escape(text)


def team_code(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ''
    code = str(value).strip().upper()
    if code in ('NAN', 'NA', 'NONE'):
        return ''
    return code if _TEAM_RE.match(code) else ''


def player_id(value):
    """Normalise 8478402, 8478402.0 and '8478402' to '8478402'; anything else to ''."""
    if value is None or isinstance(value, bool):
        return ''
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ''
    if not math.isfinite(number) or number <= 0 or number != int(number):
        return ''
    return str(int(number))


def logo_url(team):
    code = team_code(team)
    return f'https://assets.nhle.com/logos/nhl/svg/{code}_light.svg' if code else ''


def mug_url(team, pid, season=NHL_SEASON_DEFAULT):
    code, ident = team_code(team), player_id(pid)
    season = str(season) if re.fullmatch(r'\d{8}', str(season)) else NHL_SEASON_DEFAULT
    return f'https://assets.nhle.com/mugs/nhl/{season}/{code}/{ident}.png' if code and ident else ''


def fmt_num(value, digits=1, fallback='—'):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return f'{number:.{digits}f}'


def badge(text, tone='muted', title=None):
    tone = tone if tone in TONES else 'muted'
    tip = f' title="{esc(title)}"' if title else ''
    return f'<span class="npb npb-{tone}"{tip}>{esc(text)}</span>'


def avatar(url, size='md', fallback='🏒'):
    size = size if size in ('sm', 'md', 'lg') else 'md'
    if url:
        return (f'<span class="npa npa-{size}"><img src="{esc(url)}" alt="" loading="lazy" '
                f'referrerpolicy="no-referrer"/></span>')
    return f'<span class="npa npa-{size} npa-empty">{esc(fallback)}</span>'


def logo(team, size=28):
    url = logo_url(team)
    size = int(size) if isinstance(size, int) and 8 <= size <= 96 else 28
    if not url:
        return f'<span class="np-logo-empty" style="width:{size}px;height:{size}px"></span>'
    return f'<img class="np-logo" src="{url}" alt="{esc(team_code(team))}" loading="lazy" style="width:{size}px;height:{size}px"/>'


def section(title, subtitle='', icon='', tone='muted'):
    tone = tone if tone in TONES else 'muted'
    sub = f'<p>{esc(subtitle)}</p>' if subtitle else ''
    ico = f'<span class="np-sec-icon npt-{tone}">{esc(icon)}</span>' if icon else ''
    return f'<div class="np-sec">{ico}<div><h3>{esc(title)}</h3>{sub}</div></div>'


def hero(kicker, title, subtitle='', chips=(), tone='stat'):
    chip_html = ''.join(badge(text, t) for text, t in chips)
    chips_block = f'<div class="np-hero-chips">{chip_html}</div>' if chip_html else ''
    tone = tone if tone in TONES else 'stat'
    return (f'<header class="np-hero2 np-hero-{tone}"><div class="np-kicker">{esc(kicker)}</div>'
            f'<h1 class="np-hero-title">{esc(title)}</h1>'
            f'<p class="np-hero-sub">{esc(subtitle)}</p>{chips_block}</header>')


def stat_strip(items):
    """items: iterable of (label, value, tone). Responsive KPI strip (2 columns on phones)."""
    cells = []
    for label, value, tone in items:
        tone = tone if tone in TONES else 'muted'
        cells.append(f'<div class="np-kpi npt-{tone}"><span>{esc(label)}</span><strong>{esc(value, "—")}</strong></div>')
    return '<div class="np-kpis">' + ''.join(cells) + '</div>'


def day_banner(day, number, note='Recreational numeric context · not a scoring probability'):
    return (f'<div class="np-day"><div class="np-day-orb">{esc(number)}</div><div><span>UNIVERSAL DAY</span>'
            f'<b>{esc(day)}</b><small>{esc(note)}</small></div></div>')


def method_chips(day=0, team=0, arena=0):
    return ('<span class="np-chips">' + badge(f'D {int(day)}', 'day', 'Universal-day method matches')
            + badge(f'T {int(team)}', 'team', 'Team-name method matches')
            + badge(f'A {int(arena)}', 'arena', 'Arena-name method matches') + '</span>')


def leader_card(tone, label, player=None, team='', opponent='', pid='', metric='', caption='',
                badges=(), season=NHL_SEASON_DEFAULT, empty_text='No eligible player available'):
    tone = tone if tone in TONES else 'muted'
    if not player:
        return (f'<article class="np-lead np-lead-{tone} is-empty"><span class="np-lead-label">{esc(label)}</span>'
                f'<div class="np-lead-empty">{esc(empty_text)}</div>'
                f'<small class="np-lead-cap">Waiting for relevant verified data</small></article>')
    extras = ''.join(badge(t, b) for t, b in badges)
    opp = f' · vs {esc(opponent)}' if opponent else ''
    return (f'<article class="np-lead np-lead-{tone}"><span class="np-lead-label">{esc(label)}</span>'
            f'<div class="np-lead-person">{avatar(mug_url(team, pid, season), "lg")}<div><b>{esc(player)}</b>'
            f'<small>{logo(team, 16)} {esc(team_code(team) or team)}{opp}</small></div></div>'
            f'<div class="np-lead-metric"><strong>{esc(metric, "—")}</strong><small>{esc(caption)}</small></div>'
            f'<div class="np-lead-badges">{extras}</div></article>')


def gem_card(rank, player, team, pid, matches, form, day=0, team_m=0, arena_m=0, season=NHL_SEASON_DEFAULT):
    return (f'<div class="np-gem">{avatar(mug_url(team, pid, season), "md")}<div class="np-gem-info">'
            f'<span class="np-gem-rank">#{int(rank)} · {esc(team_code(team) or team)}</span><b>{esc(player)}</b>'
            f'<div class="np-gem-score"><strong>{int(matches)}</strong><small>symbolic matches</small>'
            f'<em>Form {fmt_num(form)}</em></div>{method_chips(day, team_m, arena_m)}</div></div>')


def target_row(rank, player, team, pid, matches, form, day=0, team_m=0, arena_m=0, season=NHL_SEASON_DEFAULT):
    return (f'<div class="np-trow"><span class="np-trow-rank">{int(rank)}</span>{avatar(mug_url(team, pid, season), "sm")}'
            f'<div class="np-trow-info"><b>{esc(player)}</b><small>{int(matches)} matches · Form {fmt_num(form)}</small></div>'
            f'{method_chips(day, team_m, arena_m)}</div>')


def team_head(team, name, note=''):
    small = f'<small>{esc(note)}</small>' if note else ''
    return f'<div class="np-thead">{logo(team, 30)}<div><b>{esc(name)}</b>{small}</div></div>'


def matchup_chip(away, home, when):
    return (f'<div class="np-match2"><div class="np-match2-logos">{logo(away, 40)}<span>@</span>{logo(home, 40)}</div>'
            f'<b>{esc(away)} <i>at</i> {esc(home)}</b><small>{esc(when)}</small></div>')


def matchup_bar(away, home, when, venue):
    return (f'<div class="np-mbar"><span class="np-mbar-meta">{esc(when)}</span><div class="np-mbar-teams">'
            f'{logo(away, 30)}<b>{esc(away)}</b><em>VS</em><b>{esc(home)}</b>{logo(home, 30)}</div>'
            f'<span class="np-mbar-meta">{esc(venue, "Venue unavailable")}</span></div>')


def gap_meter(pct, cap=100.0):
    """Width of the payout-gap bar; clamps negatives, NaN and huge gaps."""
    try:
        value = float(pct)
    except (TypeError, ValueError):
        value = 0.0
    if not math.isfinite(value) or value < 0:
        value = 0.0
    width = 100.0 * min(value, cap) / cap if cap > 0 else 0.0
    return f'<div class="np-meter"><span style="width:{width:.0f}%"></span></div>'


def odds_card(player, team, pid, best_price, best_book, low_price, low_book, gap_pct, books,
              rank_text, identity, season=NHL_SEASON_DEFAULT):
    ambiguous = 'Ambiguous' in str(identity)
    ident = badge('Name collision' if ambiguous else 'Unverified identity', 'warn' if ambiguous else 'muted', identity)
    return (f'<div class="np-oc"><div class="np-oc-head">{avatar(mug_url(team, pid, season), "md")}'
            f'<div class="np-oc-player"><b>{esc(player)}</b><small>{logo(team, 14) if team_code(team) else ""} '
            f'{esc(team_code(team) or "Team unmatched")} · {esc(rank_text)}</small>'
            f'<div class="np-oc-badges">{badge(f"{int(books)} books", "odds")}{ident}</div></div>'
            f'<div class="np-oc-best"><span>BEST</span><strong>{esc(best_price)}</strong><small>{esc(best_book)}</small></div></div>'
            f'<div class="np-oc-foot"><span>Low {esc(low_price)} · {esc(low_book)}</span>'
            f'<strong>+{fmt_num(gap_pct)}% payout gap</strong></div>{gap_meter(gap_pct)}</div>')


def num_value_row(name, values, tone='team'):
    if not values:
        return f'<div class="np-nrow"><b>{esc(name or None, "Unavailable")}</b><span class="np-nrow-na">Unavailable</span></div>'
    cells = ''.join(
        f'<span class="np-nv"><small>{lab}</small><strong>{esc(values.get(root))}</strong><em>{esc(values.get(raw))}</em></span>'
        for lab, raw, root in (('ENG', 'ordinal', 'ordinal_root'), ('RED', 'reduction', 'reduction_root'), ('REV', 'reverse', 'reverse_root')))
    tone = tone if tone in TONES else 'team'
    return f'<div class="np-nrow npt-{tone}"><b>{esc(name)}</b><div class="np-nvs">{cells}</div></div>'


def footer(text):
    return f'<div class="np-foot">{esc(text)}</div>'


CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
:root{color-scheme:dark;
 --bg:#0a0f1c;--s1:#111a2c;--s2:#162238;--s3:#1c2b45;--line:#24344f;--line2:#2f4566;
 --tx:#e6edf7;--tx2:#b4c3d9;--mut:#8ea2bf;
 --stat:#f5c451;--gem:#b794ff;--odds:#38bdf8;--overlap:#34d399;--warn:#fbbf24;--ok:#34d399;
 --day:#c4a1ff;--team:#60c8ff;--arena:#5eead4;
 --r1:10px;--r2:14px;--r3:20px;--sh:0 10px 30px rgba(0,0,0,.35);
 --font:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;--mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
html,body,.stApp,[data-testid="stMarkdownContainer"],button,input,select,textarea{font-family:var(--font)!important}
.stApp{background:radial-gradient(1200px 500px at 15% -10%,#13284a 0%,transparent 60%),radial-gradient(900px 400px at 100% 0%,#1d1540 0%,transparent 55%),var(--bg);color:var(--tx)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background:#0c1424;border-right:1px solid var(--line)}
.block-container{max-width:1240px;padding-top:2.2rem!important;padding-bottom:4rem!important}
h1,h2,h3,h4{color:#f3f7fd!important;letter-spacing:-.02em;font-weight:750!important}
h4{font-size:1.05rem!important;margin-top:1.1rem!important}
p,li{line-height:1.55}
[data-testid="stCaptionContainer"],.stCaption{color:var(--mut)!important}
a{color:var(--odds)}
/* Native widgets */
[data-testid="stMetric"]{background:linear-gradient(160deg,var(--s2),var(--s1));border:1px solid var(--line);border-radius:var(--r2);padding:14px 16px}
[data-testid="stMetricLabel"]{color:var(--mut)!important;text-transform:uppercase;letter-spacing:.06em;font-size:.72rem!important}
[data-testid="stMetricValue"]{color:#fff;font-family:var(--mono)!important;font-weight:700}
[data-testid="stExpander"]{border:1px solid var(--line)!important;border-radius:var(--r2)!important;background:rgba(17,26,44,.55)}
[data-testid="stExpander"] summary:hover{color:var(--odds)}
[data-testid="stDataFrame"],[data-testid="stTable"]{border:1px solid var(--line);border-radius:var(--r2);overflow:hidden}
div.stButton>button,div.stDownloadButton>button{border-radius:var(--r1);border:1px solid var(--line2);background:var(--s2);color:var(--tx);font-weight:600;transition:all .15s}
div.stButton>button:hover,div.stDownloadButton>button:hover{border-color:var(--odds);color:#fff;background:var(--s3)}
div.stButton>button[kind="primary"]{background:linear-gradient(135deg,#0ea5e9,#2563eb);border:0;color:#fff}
[data-testid="stAlert"]{border-radius:var(--r2)!important}
.stTabs [data-baseweb="tab-list"]{gap:4px;background:rgba(17,26,44,.85);border:1px solid var(--line);border-radius:999px;padding:4px;width:fit-content;max-width:100%;overflow-x:auto;backdrop-filter:blur(8px)}
.stTabs [data-baseweb="tab"]{border-radius:999px;padding:8px 18px;font-weight:650;color:var(--tx2);height:auto}
.stTabs [aria-selected="true"]{background:var(--s3);color:#fff}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none}
[data-testid="stToolbar"]{opacity:.6}
/* Badges */
.npb{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:999px;font-size:.68rem;font-weight:700;letter-spacing:.02em;border:1px solid;white-space:nowrap;line-height:1.35}
.npb-stat{color:var(--stat);border-color:rgba(245,196,81,.45);background:rgba(245,196,81,.10)}
.npb-gem{color:var(--gem);border-color:rgba(183,148,255,.45);background:rgba(183,148,255,.10)}
.npb-odds{color:var(--odds);border-color:rgba(56,189,248,.45);background:rgba(56,189,248,.10)}
.npb-overlap,.npb-ok{color:var(--overlap);border-color:rgba(52,211,153,.45);background:rgba(52,211,153,.10)}
.npb-warn{color:var(--warn);border-color:rgba(251,191,36,.5);background:rgba(251,191,36,.10)}
.npb-muted{color:var(--tx2);border-color:var(--line2);background:rgba(255,255,255,.03)}
.npb-day{color:var(--day);border-color:rgba(196,161,255,.4);background:rgba(196,161,255,.08)}
.npb-team{color:var(--team);border-color:rgba(96,200,255,.4);background:rgba(96,200,255,.08)}
.npb-arena{color:var(--arena);border-color:rgba(94,234,212,.4);background:rgba(94,234,212,.08)}
.np-chips{display:inline-flex;gap:4px;flex-wrap:wrap}
.npt-stat{--tone:var(--stat)}.npt-gem{--tone:var(--gem)}.npt-odds{--tone:var(--odds)}.npt-overlap,.npt-ok{--tone:var(--overlap)}.npt-warn{--tone:var(--warn)}.npt-muted{--tone:var(--tx2)}.npt-day{--tone:var(--day)}.npt-team{--tone:var(--team)}.npt-arena{--tone:var(--arena)}
/* Avatars & logos */
.npa{display:inline-grid;place-items:center;flex-shrink:0;border-radius:50%;overflow:hidden;background:radial-gradient(circle at 50% 30%,#2a3d5e,#141f33);border:1px solid var(--line2)}
.npa img{width:100%;height:100%;object-fit:cover;object-position:top}
.npa-sm{width:36px;height:36px;font-size:.9rem}.npa-md{width:52px;height:52px;font-size:1.2rem}.npa-lg{width:64px;height:64px;font-size:1.5rem}
.np-logo{object-fit:contain;vertical-align:middle;filter:drop-shadow(0 2px 4px rgba(0,0,0,.4))}.np-logo-empty{display:inline-block}
/* Hero, sections, KPIs */
.np-hero2{position:relative;overflow:hidden;border:1px solid var(--line2);border-radius:var(--r3);padding:26px 28px;margin:4px 0 16px;background:linear-gradient(120deg,#122845 0%,#0e1b30 55%,#120f2a 100%);box-shadow:var(--sh)}
.np-hero2:after{content:'';position:absolute;right:-60px;top:-60px;width:220px;height:220px;border-radius:50%;background:radial-gradient(circle,var(--hero-glow,rgba(56,189,248,.25)),transparent 70%)}
.np-hero-gem{--hero-glow:rgba(183,148,255,.3)}.np-hero-odds{--hero-glow:rgba(56,189,248,.3)}.np-hero-stat{--hero-glow:rgba(245,196,81,.22)}
.np-kicker{font-size:.7rem;letter-spacing:.2em;font-weight:800;color:var(--odds);text-transform:uppercase}
.np-hero-title{font-size:clamp(1.8rem,4.2vw,2.9rem)!important;line-height:1.08!important;margin:8px 0 6px!important;padding:0!important;font-weight:800!important;letter-spacing:-.035em}
.np-hero-sub{color:var(--tx2);font-size:.95rem;margin:0;max-width:760px}
.np-hero-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.np-sec{display:flex;align-items:center;gap:12px;margin:26px 0 10px}
.np-sec h3{font-size:1.2rem!important;margin:0!important;padding:0!important}
.np-sec p{margin:2px 0 0;color:var(--mut);font-size:.82rem}
.np-sec-icon{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:color-mix(in srgb,var(--tone) 14%,transparent);border:1px solid color-mix(in srgb,var(--tone) 40%,transparent);font-size:1.05rem}
.np-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:8px 0 6px}
.np-kpi{background:linear-gradient(160deg,var(--s2),var(--s1));border:1px solid var(--line);border-left:3px solid var(--tone);border-radius:var(--r2);padding:12px 14px}
.np-kpi span{display:block;color:var(--mut);font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;font-weight:700}
.np-kpi strong{display:block;font-family:var(--mono);font-size:1.55rem;color:#fff;margin-top:3px}
.np-day{display:flex;align-items:center;gap:14px;border:1px solid rgba(183,148,255,.35);background:linear-gradient(110deg,rgba(60,34,110,.55),rgba(17,26,44,.6));border-radius:var(--r2);padding:12px 16px;margin:10px 0}
.np-day-orb{display:grid;place-items:center;width:54px;height:54px;border-radius:50%;font-family:var(--mono);font-size:1.7rem;font-weight:700;color:#f3e8ff;background:radial-gradient(circle,#6d3fc0,#2a1858);box-shadow:0 0 24px rgba(183,148,255,.45);flex-shrink:0}
.np-day span{display:block;font-size:.68rem;font-weight:800;letter-spacing:.14em;color:var(--gem)}.np-day b{color:#fff;font-size:1rem}.np-day small{display:block;color:var(--mut);font-size:.72rem}
/* Four leaders */
.np-leads{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:6px 0 8px}
.np-lead{--tone:var(--odds);position:relative;display:flex;flex-direction:column;gap:10px;padding:16px;border-radius:var(--r2);border:1px solid var(--line);background:linear-gradient(165deg,var(--s2),var(--s1));box-shadow:var(--sh);min-width:0;overflow:hidden}
.np-lead:before{content:'';position:absolute;inset:0 0 auto 0;height:3px;background:var(--tone)}
.np-lead-stat{--tone:var(--stat)}.np-lead-gem{--tone:var(--gem)}.np-lead-odds{--tone:var(--odds)}.np-lead-overlap{--tone:var(--overlap)}
.np-lead-label{font-size:.68rem;font-weight:800;letter-spacing:.1em;color:var(--tone);text-transform:uppercase}
.np-lead-person{display:flex;align-items:center;gap:10px;min-width:0}.np-lead-person .npa{border-color:color-mix(in srgb,var(--tone) 55%,transparent)}
.np-lead-person b{display:block;color:#fff;font-size:1rem;line-height:1.2;overflow-wrap:anywhere}.np-lead-person small{display:block;color:var(--mut);font-size:.74rem;margin-top:3px}
.np-lead-metric strong{display:block;font-family:var(--mono);font-size:1.75rem;line-height:1.1;color:#fff}.np-lead-metric small,.np-lead-cap{display:block;color:var(--mut);font-size:.72rem}
.np-lead-badges{display:flex;flex-wrap:wrap;gap:5px;margin-top:auto}
.np-lead.is-empty{opacity:.78}.np-lead-empty{color:var(--tx2);font-size:.88rem;margin:18px 0 6px}
/* Gematria cards */
.np-hscroll{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 14px;scroll-snap-type:x mandatory;scrollbar-width:thin}
.np-gem{flex:0 0 240px;scroll-snap-align:start;display:flex;gap:11px;padding:13px;border-radius:var(--r2);border:1px solid rgba(183,148,255,.3);background:linear-gradient(160deg,#1d1838,#111a2c);min-width:0}
.np-gem-info{min-width:0;flex:1}.np-gem-rank{display:block;font-size:.68rem;color:var(--gem);font-weight:700;letter-spacing:.05em}
.np-gem-info b{display:block;color:#fff;font-size:.92rem;line-height:1.2;margin:3px 0 6px;overflow-wrap:anywhere}
.np-gem-score{display:flex;align-items:baseline;gap:6px;margin-bottom:7px}.np-gem-score strong{font-family:var(--mono);font-size:1.4rem;color:#f3e8ff}.np-gem-score small{color:var(--mut);font-size:.68rem}.np-gem-score em{margin-left:auto;font-style:normal;font-size:.7rem;color:var(--stat)}
/* Matchup chips/bars and target rows */
.np-match2{flex:0 0 160px;scroll-snap-align:start;display:flex;flex-direction:column;align-items:center;gap:7px;padding:13px 10px;border-radius:var(--r2);border:1px solid var(--line);background:linear-gradient(160deg,var(--s2),var(--s1));text-align:center}
.np-match2-logos{display:flex;align-items:center;gap:10px}.np-match2-logos span{color:var(--mut);font-size:.75rem;font-weight:700}
.np-match2 b{color:#fff;font-size:.86rem}.np-match2 b i{color:var(--mut);font-style:normal;font-weight:500}.np-match2 small{color:var(--odds);font-size:.74rem;font-family:var(--mono)}
.np-mbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:11px 14px;margin:18px 0 6px;border-radius:var(--r2);border:1px solid var(--line2);background:linear-gradient(110deg,#15294a,#101a2e)}
.np-mbar-teams{display:flex;align-items:center;gap:9px}.np-mbar-teams b{color:#fff;font-size:1rem}.np-mbar-teams em{font-style:normal;font-size:.66rem;font-weight:800;color:var(--odds);letter-spacing:.1em}
.np-mbar-meta{color:var(--mut);font-size:.74rem}
.np-thead{display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid var(--line);margin-bottom:4px}.np-thead b{display:block;color:#fff;font-size:.9rem}.np-thead small{display:block;color:var(--mut);font-size:.7rem}
.np-trow{display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid rgba(36,52,79,.6);min-width:0}
.np-trow-rank{display:grid;place-items:center;width:22px;height:22px;border-radius:7px;background:var(--s3);color:var(--tx2);font-size:.7rem;font-weight:800;flex-shrink:0}
.np-trow-info{flex:1;min-width:0}.np-trow-info b{display:block;color:#fff;font-size:.86rem;line-height:1.2;overflow-wrap:anywhere}.np-trow-info small{display:block;color:var(--mut);font-size:.7rem}
/* Odds cards */
.np-oc{border:1px solid var(--line);border-radius:var(--r2);background:linear-gradient(160deg,var(--s2),var(--s1));padding:14px 16px 12px;margin:12px 0 4px;box-shadow:var(--sh)}
.np-oc-head{display:flex;align-items:center;gap:12px}.np-oc-player{flex:1;min-width:0}
.np-oc-player b{display:block;color:#fff;font-size:1.02rem;overflow-wrap:anywhere}.np-oc-player small{display:block;color:var(--mut);font-size:.74rem;margin-top:2px}
.np-oc-badges{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}
.np-oc-best{text-align:right;flex-shrink:0;padding:8px 12px;border-radius:var(--r1);background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.35)}
.np-oc-best span{display:block;font-size:.6rem;letter-spacing:.14em;font-weight:800;color:var(--overlap)}
.np-oc-best strong{display:block;font-family:var(--mono);font-size:1.5rem;color:#d1fae5;line-height:1.15}.np-oc-best small{display:block;color:var(--tx2);font-size:.7rem}
.np-oc-foot{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-top:11px;padding-top:9px;border-top:1px solid var(--line);font-size:.76rem;color:var(--mut)}.np-oc-foot strong{color:var(--odds);font-family:var(--mono)}
.np-meter{height:4px;border-radius:4px;background:var(--s3);margin-top:8px;overflow:hidden}.np-meter span{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,var(--odds),var(--overlap))}
.np-orow{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 14px;border:1px solid var(--line);border-radius:var(--r1);background:var(--s1);margin:6px 0}
.np-orow b{color:#fff}.np-orow small{color:var(--mut)}.np-orow strong{font-family:var(--mono);color:#d1fae5}
/* Numbers */
.np-nrow{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 14px;margin:7px 0;border-radius:var(--r1);border:1px solid var(--line);border-left:3px solid var(--tone,var(--team));background:var(--s1)}
.np-nrow b{color:#fff;font-size:.9rem}.np-nrow-na{color:var(--mut);font-size:.8rem}
.np-nvs{display:flex;gap:6px}.np-nv{display:flex;flex-direction:column;align-items:center;min-width:56px;padding:5px 8px;border-radius:9px;background:var(--s3)}
.np-nv small{font-size:.58rem;color:var(--mut);letter-spacing:.1em;font-weight:700}.np-nv strong{font-family:var(--mono);font-size:1.1rem;color:#fff}.np-nv em{font-style:normal;font-size:.6rem;color:var(--mut);font-family:var(--mono)}
.np-num-match{border:1px solid var(--line);border-radius:var(--r2);background:linear-gradient(160deg,var(--s2),var(--s1));padding:14px;margin:14px 0 4px;box-shadow:var(--sh)}
.np-num-top{display:flex;justify-content:space-between;gap:8px;color:var(--mut);font-size:.74rem;border-bottom:1px solid var(--line);padding-bottom:9px}
.np-num-versus{display:grid;grid-template-columns:minmax(0,1fr) 88px minmax(0,1fr);gap:8px;text-align:center;padding:12px 0}
.np-num-versus>div{display:flex;flex-direction:column;align-items:center;gap:6px;min-width:0}.np-num-versus img{height:52px;width:52px;object-fit:contain}
.np-num-versus b{color:#fff}.np-num-versus small{font-size:.66rem;color:var(--tx2);font-family:var(--mono)}
.np-num-center{justify-content:center}.np-num-center strong{font-family:var(--mono);font-size:1.5rem;color:var(--gem);line-height:1}.np-num-center .np-num-green{color:var(--arena)}.np-num-center small{font-size:.58rem!important;letter-spacing:.12em;color:var(--mut)!important}.np-num-center span{font-size:.66rem;color:var(--mut);font-weight:800}
.np-num-foot{border-top:1px solid var(--line);padding-top:9px;display:flex;flex-wrap:wrap;gap:5px}
/* Legacy V4-V5 classes kept for Research and Player Targets, restyled to tokens */
.np-feature-scroll,.np-match-scroll{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;padding:4px 2px 14px;scrollbar-width:thin}
.np-feature{flex:0 0 200px;scroll-snap-align:start;border:1px solid var(--line);border-radius:var(--r2);padding:13px;background:linear-gradient(160deg,var(--s2),var(--s1));display:flex;flex-direction:column;gap:6px}
.np-feature-top{display:flex;justify-content:space-between;align-items:flex-start}.np-rank{color:var(--stat);font-weight:800;font-family:var(--mono)}
.np-feature b{font-size:.95rem;color:#fff}.np-feature small{color:var(--mut);font-size:.74rem}
.np-feature-score{color:#fff;font-size:1.5rem;font-weight:700;font-family:var(--mono)}.np-feature-score span{font-size:.6rem;color:var(--stat);font-weight:700;letter-spacing:.1em;font-family:var(--font)}
.np-player{border:1px solid var(--line);border-radius:var(--r2);background:linear-gradient(160deg,var(--s2),var(--s1));padding:13px;margin:7px 0}
.np-muted{font-size:.78rem;color:var(--mut)}
.np-research-card{background:linear-gradient(160deg,var(--s2),var(--s1));border:1px solid var(--line);border-top:3px solid var(--stat);border-radius:var(--r2);padding:16px;margin:13px 0 4px;box-shadow:var(--sh)}
.np-research-eyebrow{color:var(--stat);font-weight:800;font-size:.68rem;letter-spacing:.12em;margin-bottom:9px}
.np-research-row{display:flex;align-items:center;gap:13px}.np-research-photo,.np-research-placeholder{height:80px;width:80px;border-radius:50%;object-fit:cover;object-position:top;flex-shrink:0;background:var(--s3);border:1px solid var(--line2)}.np-research-placeholder{display:grid;place-items:center}
.np-research-person{flex:1;min-width:0}.np-research-name{color:#fff;font-size:1.12rem;font-weight:750}.np-research-team{color:var(--mut);font-size:.76rem;margin-top:3px}
.np-research-form{color:#fff;font-family:var(--mono);font-size:1.55rem;font-weight:700;margin-top:6px}.np-research-form small{display:block;color:var(--stat);font-size:.58rem;letter-spacing:.08em;font-weight:700;font-family:var(--font)}
.np-research-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:12px}.np-research-stats>div{background:var(--s3);border-radius:var(--r1);padding:9px}.np-research-stats b{display:block;font-size:1.05rem;color:#fff;font-family:var(--mono)}.np-research-stats small{display:block;font-size:.66rem;color:var(--mut)}
.np-research-note{color:var(--tx2);font-size:.78rem;line-height:1.5;margin-top:12px}
.np-v50-heading{margin:10px 0 14px}.np-v50-heading span{font-size:.7rem;letter-spacing:.16em;font-weight:800;color:var(--gem)}.np-v50-heading h3{font-size:1.45rem;margin:6px 0!important}.np-v50-heading p{font-size:.82rem;color:var(--mut)}
.np-foot{text-align:center;color:var(--mut);font-size:.72rem;letter-spacing:.05em;padding:26px 0 8px}
/* Responsive */
@media(max-width:1000px){.np-leads{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:768px){
 .block-container{padding:1rem .75rem 5rem!important}
 .np-hero2{padding:18px 16px;border-radius:16px}.np-hero-sub{font-size:.84rem}
 .np-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.np-kpi strong{font-size:1.25rem}
 .stTabs [data-baseweb="tab-list"]{position:sticky;top:0;z-index:30;width:100%;justify-content:space-between}
 .stTabs [data-baseweb="tab"]{padding:7px 10px;font-size:.82rem}
 [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:8px!important}
 [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"])>[data-testid="stColumn"]{width:auto!important;min-width:0!important;flex:none!important}
 .np-lead{padding:12px}.np-lead-metric strong{font-size:1.4rem}.npa-lg{width:50px;height:50px}
 .np-gem{flex-basis:220px}.np-oc-best strong{font-size:1.25rem}
 .np-nrow{flex-direction:column;align-items:flex-start}.np-num-versus{grid-template-columns:minmax(0,1fr) 70px minmax(0,1fr)}.np-num-versus img{height:42px;width:42px}
}
@media(max-width:420px){.np-leads{grid-template-columns:1fr}.np-oc-head{flex-wrap:wrap}.np-oc-best{width:100%;text-align:left}}
"""


def stylesheet():
    return '<style>' + CSS + '</style>'


def eastern_today(now=None):
    """NHL slate date in America/New_York. `now` must be timezone-aware (UTC assumed if naive)."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ZoneInfo('America/New_York')).date()
