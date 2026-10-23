"""Audit P1.7d: one shared footer, rendered at the bottom of every tab (app.py calls render() after each run_tab).

Responsible-gambling line, data sources (with MoneyPuck's terms), the no-affiliation statement, the
'not betting advice' statement and a link to the model card. Plain markdown only (no HTML/JS), so it renders
identically on every Streamlit version >= 1.50 and in AppTest.
"""

REPO_URL = 'https://github.com/Nxll-cloud/NULL-NHL-V3'
MODEL_CARD_URL = f'{REPO_URL}/blob/main/MODEL_CARD.md'

RESPONSIBLE = '21+ only. Gambling problem? Call **1-800-GAMBLER**.'
SOURCES = (
    ('NHL API', 'https://api-web.nhle.com'),
    ('ESPN', 'https://www.espn.com/nhl/'),
    ('MoneyPuck', 'https://moneypuck.com/data.htm'),
    ('The Odds API', 'https://the-odds-api.com'),
)
MONEYPUCK_TERMS = 'MoneyPuck data used under its terms: non-commercial use, with credit to MoneyPuck.com'
NOT_AFFILIATED = 'Not affiliated with or endorsed by the NHL'
NOT_ADVICE = 'Model estimates for research and entertainment; not betting advice.'


def footer_md():
    sources = ', '.join(f'[{n}]({u})' for n, u in SOURCES)
    return (f'{RESPONSIBLE} · Data: {sources}. {MONEYPUCK_TERMS}. '
            f'{NOT_AFFILIATED}. {NOT_ADVICE} [Model card]({MODEL_CARD_URL})')


def render(st):
    """Draw the footer with the given streamlit module (or app.py's MarkingStreamlit proxy).

    One caption, no divider: Research deliberately ends on Sleepers with no dividers (test_v58_research)."""
    st.caption(footer_md())
