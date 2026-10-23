"""V5.3 design system: one stylesheet plus small, escaped HTML builders.

All builders are pure functions (string in, string out) so they can be unit
tested without Streamlit. Every dynamic value is HTML-escaped; image URLs are
only produced for well-formed NHL team codes and numeric player IDs.
"""
import base64 as _b64
import functools as _ft
import html as _html
import math
import re
from pathlib import Path as _Path

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


# ---------------------------------------------------------------- V5.3.1 brand
ASSET_DIR = _Path(__file__).resolve().parent / 'assets'
BRAND_NAME = 'Null’s Playbook'
# V5.7: the owner's raster logo (resized/cropped/compressed only). Inline data URIs use the small webp files;
# LOGO_HIRES / LOGO_FALLBACKS serve st.logo, README and high-DPI use.
LOGO_FILES = {'full': 'logo_full_360.webp', 'mark': 'logo_mark_128.webp'}
LOGO_HIRES = {'full': 'logo_full.webp', 'mark': 'logo_mark.webp'}
LOGO_FALLBACKS = {'full': 'logo_full.jpg', 'mark': 'logo_mark.png'}
FAVICON_FILE = 'favicon.png'
BRAND_SIZES = ('xs', 'sm', 'md', 'lg', 'xl')


@_ft.lru_cache(maxsize=8)
def _asset_bytes(name, base=None):
    path = _Path(base) / name if base else ASSET_DIR / name
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data or None


def _image_mime(data):
    """MIME type from magic bytes; None for anything that is not a known image."""
    if not data:
        return None
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if b'<svg' in data[:4096]:
        return 'image/svg+xml'
    return None


def logo_data_uri(kind='full', base=None, hires=False):
    """Base64 data URI for a brand image (webp, then png/jpg fallback), or None when missing/corrupt."""
    for table in ((LOGO_HIRES, LOGO_FILES, LOGO_FALLBACKS) if hires else (LOGO_FILES, LOGO_FALLBACKS)):
        name = table.get(kind)
        data = _asset_bytes(name, base) if name else None
        mime = _image_mime(data)
        if mime:
            return f'data:{mime};base64,' + _b64.b64encode(data).decode('ascii')
    return None


def logo_path(kind='full', base=None, fallback=False):
    """Filesystem path of a brand asset as a string, or None when missing.
    kind is 'full'/'mark' (hi-res webp) or a file name; fallback=True picks the png/jpg."""
    name = (LOGO_FALLBACKS if fallback else LOGO_HIRES).get(kind, kind)
    path = _Path(base) / name if base else ASSET_DIR / name
    return str(path) if path.is_file() else None


def page_icon(base=None, fallback='👑'):
    """PIL image of the favicon for st.set_page_config; emoji fallback if unavailable."""
    path = logo_path(FAVICON_FILE, base)
    if not path:
        return fallback
    try:
        from PIL import Image
        img = Image.open(path)
        img.load()
        return img
    except Exception:  # Pillow missing or unreadable file: never block page config
        return fallback


def brand(kind='full', size='md', base=None, extra_class=''):
    """Inline, responsive brand image. Falls back to a styled text wordmark."""
    kind = kind if kind in LOGO_FILES else 'full'
    size = size if size in BRAND_SIZES else 'md'
    cls = f'np-brand np-brand-{kind} np-brand-{size}' + (f' {esc(extra_class)}' if extra_class else '')
    uri = logo_data_uri(kind, base, hires=(size == 'xl'))
    if uri:
        return f'<img class="{cls}" src="{uri}" alt="{esc(BRAND_NAME)}" title="{esc(BRAND_NAME)}"/>'
    text = 'N' if kind == 'mark' else 'NULL’S <em>PLAYBOOK</em>'
    return f'<span class="{cls} np-brand-text" role="img" aria-label="{esc(BRAND_NAME)}">{text}</span>'


def hero(kicker, title, subtitle='', chips=(), tone='stat', brand_kind='mark'):
    """Tab header. brand_kind='full' shows the lockup (Home), 'mark' an inline icon, None nothing."""
    chip_html = ''.join(badge(text, t) for text, t in chips)
    chips_block = f'<div class="np-hero-chips">{chip_html}</div>' if chip_html else ''
    tone = tone if tone in TONES else 'stat'
    if brand_kind == 'full':
        top = f'<div class="np-hero-brand">{brand("full", "lg")}</div><div class="np-kicker">{esc(kicker)}</div>'
    elif brand_kind == 'mark':
        top = f'<div class="np-kicker np-kicker-brand">{brand("mark", "xs")}<span>{esc(kicker)}</span></div>'
    else:
        top = f'<div class="np-kicker">{esc(kicker)}</div>'
    return (f'<header class="np-hero2 np-hero-{tone}">{top}'
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
            f'<em>Form {format_form_pct(form)}</em></div>{method_chips(day, team_m, arena_m)}</div></div>')


def target_row(rank, player, team, pid, matches, form, day=0, team_m=0, arena_m=0, season=NHL_SEASON_DEFAULT):
    return (f'<div class="np-trow"><span class="np-trow-rank">{int(rank)}</span>{avatar(mug_url(team, pid, season), "sm")}'
            f'<div class="np-trow-info"><b>{esc(player)}</b><small>{int(matches)} matches · Form {format_form_pct(form)}</small></div>'
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
    return f'<div class="np-foot">{brand("mark", "sm")}<span>{esc(text)}</span></div>'


def brand_title(title, caption=''):
    """Compact branded heading used by Research and the sidebar."""
    cap = f'<small>{esc(caption)}</small>' if caption else ''
    return f'<div class="np-brand-title">{brand("mark", "md")}<div><b>{esc(title)}</b>{cap}</div></div>'


CSS = r"""
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


CSS += r"""
.np-brand{display:inline-block;vertical-align:middle;height:auto;max-width:100%;filter:drop-shadow(0 6px 18px rgba(56,189,248,.18))}
.np-brand-mark.np-brand-xs{width:22px;height:22px}.np-brand-mark.np-brand-sm{width:30px;height:30px}
.np-brand-mark.np-brand-md{width:44px;height:44px}.np-brand-mark.np-brand-lg{width:72px;height:72px}.np-brand-mark.np-brand-xl{width:120px;height:120px}
.np-brand-mark:not(.np-brand-text){border-radius:22%}.np-brand-full:not(.np-brand-text){border-radius:14px}  /* V5.7: logo art sits on a black square */
.np-brand-full.np-brand-sm{width:150px}.np-brand-full.np-brand-md{width:220px}.np-brand-full.np-brand-lg{width:clamp(200px,32vw,330px)}.np-brand-full.np-brand-xl{width:clamp(260px,46vw,520px)}
.np-brand-text{font-weight:900;letter-spacing:.04em;color:#fff;font-family:var(--font);white-space:nowrap}
.np-brand-text em{font-style:normal;font-family:var(--mono);color:var(--odds);letter-spacing:.3em;margin-left:.35em;font-size:.7em}
.np-brand-mark.np-brand-text{display:inline-flex;align-items:center;justify-content:center;border-radius:30%;background:linear-gradient(135deg,#38bdf8,#b794ff);color:#0a0f1c}
.np-hero-brand{position:relative;z-index:1;margin:-4px 0 10px}
.np-kicker-brand{display:flex;align-items:center;gap:8px}
.np-brand-title{display:flex;align-items:center;gap:12px;margin:4px 0 10px}.np-brand-title b{display:block;font-size:1.15rem;color:var(--tx)}.np-brand-title small{color:var(--mut);font-size:.78rem}
.np-foot{display:flex;align-items:center;justify-content:center;gap:10px}
[data-testid="stSidebar"] .np-brand-full{width:180px}
@media (max-width:768px){.np-brand-full.np-brand-lg{width:min(260px,78vw)}.np-brand-mark.np-brand-md{width:36px;height:36px}}
/* V5.4 player intelligence row */
.np-intel-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:6px 0 10px}
.np-intel-row.np-intel-solo{grid-template-columns:1fr!important;margin:6px 0 6px}
.np-intel{--tone:var(--stat);position:relative;display:flex;flex-direction:column;gap:9px;padding:16px;border-radius:var(--r2);border:1px solid color-mix(in srgb,var(--tone) 35%,var(--line));background:radial-gradient(120% 90% at 100% 0%,color-mix(in srgb,var(--tone) 16%,transparent),transparent 60%),linear-gradient(165deg,var(--s2),var(--s1));box-shadow:var(--sh);min-width:0;overflow:hidden}
.np-intel:before{content:'';position:absolute;inset:0 auto 0 0;width:3px;background:var(--tone)}
.np-intel-stat{--tone:var(--stat)}.np-intel-gem{--tone:var(--gem)}.np-intel-overlap{--tone:var(--overlap)}.np-intel-odds{--tone:var(--odds)}
.np-intel-label{font-size:.66rem;font-weight:800;letter-spacing:.11em;color:var(--tone)}
.np-intel-person{display:flex;align-items:center;gap:10px;min-width:0}.np-intel-person b{display:block;color:#fff;font-size:1rem;line-height:1.2;overflow-wrap:anywhere}.np-intel-person small{display:block;color:var(--mut);font-size:.74rem;margin-top:3px}
.np-intel-metric strong{display:block;font-family:var(--mono);font-size:1.9rem;line-height:1.05;color:#fff}.np-intel-metric small{color:var(--mut);font-size:.66rem;letter-spacing:.1em}
.np-intel-badges{display:flex;flex-wrap:wrap;gap:5px}.np-intel-reason{color:var(--tx2);font-size:.76rem;line-height:1.35;margin-top:auto}
.np-intel.is-empty{opacity:.75}.np-intel-empty{color:var(--tx2);font-size:.9rem;margin:14px 0 4px}
@media(max-width:1000px){.np-intel-row{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.np-intel-row{grid-template-columns:1fr}.np-intel{padding:13px}.np-intel-metric strong{font-size:1.5rem}}
/* V5.4 goalies */
.np-gk-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:6px 0 10px}
.np-gk{--tone:var(--mut);padding:14px;border-radius:var(--r2);border:1px solid var(--line);background:linear-gradient(165deg,var(--s2),var(--s1));box-shadow:var(--sh);min-width:0}
.np-gk-opportunity{--tone:#fb923c;border-color:rgba(251,146,60,.5);background:radial-gradient(120% 90% at 100% 0%,rgba(251,146,60,.18),transparent 60%),linear-gradient(165deg,var(--s2),var(--s1))}
.np-gk-stingy{--tone:#38bdf8;border-color:rgba(56,189,248,.45);background:radial-gradient(120% 90% at 100% 0%,rgba(56,189,248,.16),transparent 60%),linear-gradient(165deg,var(--s2),var(--s1))}
.np-gk-head{display:flex;align-items:center;gap:10px;margin-bottom:8px}.np-gk-head b{display:block;color:#fff}.np-gk-head small{color:var(--tone);font-size:.72rem;font-weight:700}
.np-gk-pos{font-family:var(--mono);color:var(--mut);font-size:.8rem}
.np-gk-total{margin-left:auto;text-align:right}.np-gk-total strong{display:block;font-family:var(--mono);font-size:1.5rem;color:#fff;line-height:1}.np-gk-total small{color:var(--mut);font-size:.68rem}
.np-gk-line{display:grid;grid-template-columns:minmax(0,1.6fr) auto auto auto auto;gap:8px;align-items:center;padding:6px 0;border-top:1px solid var(--line);font-size:.78rem;color:var(--tx2)}
.np-gk-line b{color:var(--tx);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.np-gk-line em{font-style:normal;font-weight:800;color:var(--tone)}
.np-gk-neutral .np-gk-line em,.np-gk-none .np-gk-line em{color:var(--tx)}
.np-gk-empty{color:var(--mut);font-size:.8rem;padding:6px 0}
.np-gk-legend{display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:.78rem;color:var(--tx2);margin:2px 0 8px}
.np-gk-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px}
@media(max-width:1000px){.np-gk-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.np-gk-grid{grid-template-columns:1fr}.np-gk-line{grid-template-columns:1fr auto auto}.np-gk-line span:nth-of-type(1){display:none}}
/* V5.4 matchup center */
.np-gs{display:flex;gap:10px;align-items:center;padding:12px 14px;border-radius:var(--r2);border:1px solid rgba(251,146,60,.45);background:radial-gradient(120% 120% at 100% 0%,rgba(251,146,60,.14),transparent 60%),var(--s1);margin:6px 0}
.np-gs-starter{border-color:rgba(74,222,128,.45);background:radial-gradient(120% 120% at 100% 0%,rgba(74,222,128,.12),transparent 60%),var(--s1)}
.np-gs b{display:block;color:#fff;font-size:1rem}.np-gs small{color:var(--tx2);font-size:.76rem}.np-gs.is-empty{border-color:var(--line);opacity:.8}
.np-gs-kicker{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.66rem;letter-spacing:.06em;color:var(--mut);text-transform:uppercase;margin-bottom:2px}
.np-mt{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--line)}.np-mt-info b{display:block;color:var(--tx)}.np-mt-info small{display:block;color:var(--mut);font-size:.74rem;margin:2px 0 4px}
.np-mc-side{display:inline-block;font-size:.68rem;font-weight:800;letter-spacing:.08em;color:#fb923c;margin:2px 0 4px}
/* V5.4 track record */
.np-track{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:9px 14px;border-radius:999px;border:1px solid var(--line);background:var(--s1);font-size:.8rem;color:var(--tx2);margin:4px 0 8px}
.np-track b{color:var(--tx)}.np-track strong{font-family:var(--mono);color:#4ade80;font-size:1rem}.np-track em{margin-left:auto;font-style:normal;color:var(--mut);font-size:.74rem}.np-track-pend{color:#f5b942}
.np-slates{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.np-slate{display:flex;flex-direction:column;gap:6px;padding:14px;border-radius:var(--r2);border:1px solid var(--line);background:linear-gradient(165deg,var(--s2),var(--s1))}
.np-slate-head{display:flex;justify-content:space-between;align-items:center}.np-slate small{color:var(--tx2);font-size:.76rem}
@media(max-width:1000px){.np-slates{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.np-slates{grid-template-columns:1fr}.np-track em{margin-left:0}}
"""


# ---------------------------------------------------------------- V5.4 Form %
# The goal-scoring Form Score (rankings.py) is a weighted points index:
#   40*(shots/g L5 / 4) + 25*(shots/g L10 / 4) + 20*(goals/g / .5) + 15*(goals/g L5 / .5)
# so a player exactly at the formula's reference levels (4 shots/g, 0.5 goals/g) scores
# 100 points; the opponent-defense factor (0.85-1.15) then multiplies it. The index is
# unbounded above, so Form % = points / FORM_BENCHMARK, clipped to 0-100 %. Values above
# the benchmark show as "100%+" in text. Display only - rankings use the raw points.
FORM_BENCHMARK = 100.0
FORM_PCT_COL = 'Form %'
FORM_RAW_COLS = ('V3.2 Adjusted Index',)


def form_pct(value, benchmark=FORM_BENCHMARK):
    """Raw form points -> 0..100 float, or None for missing/NaN/non-numeric."""
    try:
        if value is None or isinstance(value, bool):
            return None
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):
        return None
    return max(0.0, min(100.0, v * 100.0 / benchmark))


def form_clipped(value, benchmark=FORM_BENCHMARK):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return v == v and (v > benchmark or v < 0)


def format_form_pct(value, benchmark=FORM_BENCHMARK):
    pct = form_pct(value, benchmark)
    if pct is None:
        return '—'
    try:
        over = float(value) > benchmark
    except (TypeError, ValueError):
        over = False
    return '100%+' if over else f'{int(round(pct))}%'


def with_form_pct(frame, col='V3.2 Adjusted Index'):
    """Display/export copy with a numeric 'Form %' column inserted before the raw index."""
    try:
        import pandas as _pd
    except ImportError:  # pragma: no cover
        return frame
    if not isinstance(frame, _pd.DataFrame) or col not in frame.columns or FORM_PCT_COL in frame.columns:
        return frame
    out = frame.copy()
    vals = [form_pct(v) for v in out[col]]
    out.insert(list(out.columns).index(col), FORM_PCT_COL,
               _pd.to_numeric(_pd.Series([round(v, 1) if v is not None else None for v in vals], index=out.index), errors='coerce'))
    return out


def form_pct_config(st_module=None, progress=False, label=FORM_PCT_COL):
    """Column config mapping for st.dataframe; numeric so sorting stays numeric."""
    if st_module is None:
        import streamlit as st_module
    cc = getattr(st_module, 'column_config', None)
    if cc is None:
        return {}
    if progress and hasattr(cc, 'ProgressColumn'):
        return {FORM_PCT_COL: cc.ProgressColumn(label, format='%d%%', min_value=0, max_value=100)}
    return {FORM_PCT_COL: cc.NumberColumn(label, format='%d%%', min_value=0, max_value=100,
                                          help='Form score as % of the 100-point benchmark (4 shots/g, 0.5 goals/g); clipped at 100%')}


# ---------------------------------------------------------------- V5.4 cards
INTEL_TONES = {'statistical': 'stat', 'storyline': 'gem', 'overlap': 'overlap', 'longshots': 'odds'}


def intel_card(key, label, lead=None, season=NHL_SEASON_DEFAULT, extra_badges=(), note=''):
    """Player-intelligence highlight card shared by Home, Research row and Matchup Center."""
    tone = INTEL_TONES.get(key, 'muted')
    if not lead:
        return (f'<article class="np-intel np-intel-{tone} is-empty"><span class="np-intel-label">{esc(label)}</span>'
                f'<div class="np-intel-empty">Insufficient data for this date</div>'
                f'<small class="np-intel-reason">This pick appears once the slate rankings load.</small></article>')
    team = team_code(lead.get('Team')) or esc(lead.get('Team', ''))
    pid = player_id(lead.get('Player ID'))
    rank = lead.get('Statistical rank')
    try:
        rank_txt = f'#{int(float(rank))}'
    except (TypeError, ValueError):
        rank_txt = '—'
    opp = lead.get('Opponent')
    opp_txt = f' · vs {esc(opp)}' if opp and str(opp) not in ('Unavailable', 'nan') else ''
    try:
        flags = int(float(lead.get('Storyline count') or 0))
    except (TypeError, ValueError):
        flags = 0
    try:
        shots = f"{float(lead.get('Shots/G L5')):.1f} shots/g L5"
    except (TypeError, ValueError):
        shots = 'shots unavailable'
    badges = [badge(f'Stat rank {rank_txt}', 'stat')]
    if flags:
        badges.append(badge(f'{flags} storyline flag' + ('s' if flags != 1 else ''), 'gem'))
    badges += [badge(t, b) for t, b in extra_badges]
    reason = note or {
        'statistical': f'Highest goal-scoring form on the slate · {shots}',
        'storyline': f'Strongest sourced storyline evidence · {shots}',
        'overlap': f'Top-20 form and storyline evidence together · {shots}',
        'longshots': f'Strong form outside the headline names · {shots}',
    }.get(key, shots)
    return (f'<article class="np-intel np-intel-{tone}"><span class="np-intel-label">{esc(label)}</span>'
            f'<div class="np-intel-person">{avatar(mug_url(team, pid, season), "lg")}<div><b>{esc(lead.get("Player", ""))}</b>'
            f'<small>{logo(team, 16)} {esc(team)}{opp_txt}</small></div></div>'
            f'<div class="np-intel-metric"><strong>{format_form_pct(lead.get("V3.2 Adjusted Index"))}</strong><small>FORM %</small></div>'
            f'<div class="np-intel-badges">{"".join(badges)}</div><small class="np-intel-reason">{esc(reason)}</small></article>')


def intel_row(cards, solo=False):
    """Grid of intel cards. solo=True: one card per call (e.g. inside a Streamlit column with its button)."""
    return '<div class="np-intel-row' + (' np-intel-solo' if solo else '') + '">' + ''.join(cards) + '</div>'


def _gk_line(g):
    gaa = fmt_num(g.get('GAA'), 2)
    sv = '—' if g.get('SV%') is None else f"{float(g['SV%']):.3f}".lstrip('0')
    return (f'<div class="np-gk-line"><b>{esc(g.get("Goalie", ""))}</b><span>{int(g.get("GP") or 0)} GP · {int(g.get("GS") or 0)} GS</span>'
            f'<em>{int(g.get("GA") or 0)} GA</em><span>{gaa} GAA</span><span>{sv} SV%</span></div>')


def goalie_card(team, name, summary, goalies, tone='neutral', position=None):
    tone = tone if tone in ('opportunity', 'stingy', 'neutral', 'none') else 'neutral'
    tag = {'opportunity': 'Leaky · opportunity', 'stingy': 'Stingy', 'neutral': 'Middle of slate', 'none': 'No data'}[tone]
    pos = f'<span class="np-gk-pos">#{int(position)}</span>' if position else ''
    rows = ''.join(_gk_line(g) for g in goalies) or '<div class="np-gk-empty">No goalie stats returned for this team yet.</div>'
    return (f'<article class="np-gk np-gk-{tone}"><div class="np-gk-head">{pos}{logo(team, 30)}<div><b>{esc(name or team)}</b>'
            f'<small>{esc(team_code(team) or team)} · {tag}</small></div><div class="np-gk-total"><strong>{int(summary.get("GA") or 0)}</strong>'
            f'<small>GA · {fmt_num(summary.get("GAA"), 2)} GAA</small></div></div>{rows}</article>')


def goalie_spotlight(team, goalie, kind='leaky', starter=None, fetched_at=None, starter_known=False):
    """Matchup goalie card. kind='starter' requires a feed-provided starter; 'leaky' never names a starter."""
    if kind == 'starter' and starter:
        label = {'confirmed': 'Confirmed starter', 'probable': 'Probable starter'}.get(starter.get('status'), 'Starter')
        tone = 'overlap' if starter.get('status') == 'confirmed' else 'odds'
        name = starter.get('goalie') or 'Unknown'
        stats = (f'{int(goalie.get("GA") or 0)} GA · {fmt_num(goalie.get("GAA"), 2)} GAA · '
                 + ('—' if goalie.get('SV%') is None else f"{float(goalie['SV%']):.3f}".lstrip('0')) + ' SV%') if goalie else 'Season stats unavailable for this goalie'
        when = f' · fetched {esc(str(fetched_at)[11:16])} UTC' if fetched_at else ''
        return (f'<div class="np-gs np-gs-starter">{logo(team, 26)}<div><span class="np-gs-kicker">{badge(label, tone)} '
                f'<small>{esc(starter.get("source", ""))}{when}</small></span><b>{esc(name)}</b><small>{stats}</small></div></div>')
    kicker = ('Team goalie stats · not necessarily tonight’s starter' if starter_known
              else 'Team goalie stats — starter not yet announced')
    if not goalie:
        return (f'<div class="np-gs is-empty">{logo(team, 26)}<div><span class="np-gs-kicker">{kicker}</span>'
                f'<b>No goalie data</b><small>Goals allowed unavailable for {esc(team)}</small></div></div>')
    sv = '—' if goalie.get('SV%') is None else f"{float(goalie['SV%']):.3f}".lstrip('0')
    return (f'<div class="np-gs">{logo(team, 26)}<div><span class="np-gs-kicker">{kicker} · leakiest by GAA</span>'
            f'<b>{esc(goalie.get("Goalie", ""))}</b><small>{int(goalie.get("GA") or 0)} GA · {fmt_num(goalie.get("GAA"), 2)} GAA · {sv} SV% · {int(goalie.get("GP") or 0)} GP</small></div></div>')


def target_card(rank, p, team, season=NHL_SEASON_DEFAULT):
    badges = ''.join(badge(t, b) for t, b in p.get('badges', ()))
    srank = f"Stat rank #{p['stat_rank']}" if p.get('stat_rank') else 'Unranked'
    return (f'<div class="np-mt"><span class="np-trow-rank">{int(rank)}</span>{avatar(mug_url(team, p.get("player_id"), season), "sm")}'
            f'<div class="np-mt-info"><b>{esc(p.get("player", ""))}</b><small>Form {format_form_pct(p.get("form"))} · {srank} · {int(p.get("matches") or 0)} matches</small>'
            f'<div class="np-lead-badges">{badges}</div></div></div>')


def track_strip(rate, slates, hits, picks, pending=0):
    if rate is None:
        body = '<b>Track record</b><span>No graded slates yet — results appear after games are final.</span>'
    else:
        body = (f'<b>Last 7 slates</b><strong>{rate * 100:.0f}%</strong><span>{hits}/{picks} picks scored · {slates} graded slate'
                + ('s' if slates != 1 else '') + '</span>')
    pend = f'<span class="np-track-pend">{pending} pending</span>' if pending else ''
    return f'<div class="np-track">{body}{pend}<em>Open 📈 Track Record for details</em></div>'


def slate_card(ev):
    status = ev.get('status')
    rate = ev.get('hit_rate')
    head = {'pending': 'Pending', 'no_picks': 'No picks graded'}.get(status, f'{(rate or 0) * 100:.0f}% hit rate')
    tone = 'muted' if status != 'evaluated' else ('overlap' if (rate or 0) >= 0.3 else 'odds')
    flags = ''.join(badge(t, b) for t, b in ((('Locked', 'stat') if ev.get('locked') else ('Unlocked', 'muted')),)
                    ) + (badge('Retro', 'gem') if ev.get('retro') else '') + (badge('DEMO DATA', 'odds') if ev.get('demo') else '')
    hits = ', '.join(esc(h['player']) for h in ev.get('hits', [])[:6]) or '—'
    near = ', '.join(esc(h['player']) for h in ev.get('near_misses', [])[:4]) or '—'
    return (f'<article class="np-slate"><div class="np-slate-head"><b>{esc(ev.get("day"))}</b>{badge(head, tone)}</div>'
            f'<div class="np-lead-badges">{flags}</div><small>Hits: {hits}</small><small>Near-misses: {near}</small>'
            f'<small>{len(ev.get("hits", []))}/{ev.get("picks", 0)} picks · {len(ev.get("unpredicted", []))} unpredicted scorers · '
            f'{ev.get("final_games", 0)} final games</small></article>')


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
