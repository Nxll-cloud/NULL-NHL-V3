"""V6.0: The List - static user-supplied method, rendered verbatim with semantic tables."""
from html.parser import HTMLParser
import thelist_v60 as tl
from v54_testkit import HERE

class _P(HTMLParser):
    def __init__(s):
        super().__init__(); s.text=[]; s.tags=[]; s.skip=False; s.tables=[]; s.cur=None; s.row=None
    def handle_starttag(s,t,a):
        s.tags.append(t)
        if t=='style': s.skip=True
        if t=='table': s.cur=[]; s.tables.append(s.cur)
        if t=='tr': s.row=[]; s.cur.append(s.row)
        if t in('td','th'): s.row.append([t,''])
    def handle_endtag(s,t):
        if t=='style': s.skip=False
    def handle_data(s,d):
        if s.skip: return
        s.text.append(d)
        if s.row and s.tags[-1] in('td','th'): s.row[-1][1]+=d

def _parse():
    p=_P(); p.feed(tl.render_html()); return p

EXPECT_LINES = ['THE LIST', 'CREDIT WHERE IT\'S DUE', '"Off the strength of him appearing those multiple times, I probably would have." – Nyah',
    '"Stick with your process." – Nyah', 'Minus odds: chance = odds ÷ (odds + 100) e.g. −125 → 125 ÷ 225 = 56%',
    '# · Player (TEAM) · Price · Chance · Goals this season / last 10 · Goalie he faces + SV%',
    '✅ A clean 3-game card (Kaprizov / Farabee / Kent Johnson) would have paid about +1880.',
    'Player-selection method (occurrence counting, TOI / shots, position and goal → shot rules) by Nyah. Game-environment, goalie, line and list-format layers built on top of it.',
    'All data from PropFinder. Results checked against official NHL box scores.']

def test_every_source_line_rendered_verbatim_in_order():
    p=_parse(); body=''.join(p.text)
    pos=0
    for ln in [l for l in tl.SOURCE.split('\n') if l.strip()]:
        for piece in ln.split(' | '):
            i=body.find(piece,pos); assert i>=0,piece; pos=i+len(piece)
    for e in EXPECT_LINES: assert e in tl.SOURCE and e in body
    assert tl.SOURCE.startswith('THE LIST\n') and tl.SOURCE.endswith('official NHL box scores.')
    for n in range(1,11): assert any(l.startswith(f'{n} ') and l.isupper() for l in tl.SOURCE.split('\n')), n

def test_three_semantic_tables():
    t=_parse().tables
    assert len(t)==3
    grid,views,slate=t
    assert [c[1] for c in grid[0]]==['DEFENSE IT FACES','GOALIE IT FACES','PLAY'] and len(grid)==5
    assert [c[1] for c in views[0]]==['VIEW','WHAT IT TELLS YOU'] and len(views)==6
    assert all(c[0]=='th' for c in slate[0]) and len(slate)==8
    rows=[[c[1] for c in r] for r in slate[1:]]
    assert rows[0]==['1','Kirill Kaprizov MIN','−125','56%','11 in 17 / 7','Askarov .887','✅ 1st']
    assert rows[6]==['7','Kent Johnson CBJ','+260','28%','6 in 14 / 4','Luukkonen .874','✅ 1st']
    assert all(len(r)==7 and all(c[0]=='td' for c in s) for r,s in zip(rows,slate[1:]))
    h=tl.render_html(); assert h.count('class="tl60-wrap"')==3 and 'overflow-x:auto' in h and '<thead>' in h and 'scope="col"' in h

def test_credit_and_static_no_network():
    body=''.join(_parse().text)
    assert 'The heart of this method is Nyah\'s.' in body and 'Steps tagged NYAH are hers.' in body
    src=(HERE/'thelist_v60.py').read_text()
    for bad in ('requests','secrets','urllib','http.client'): assert bad not in src
    assert len(src.encode())<100_000

def test_research_calls_section_always_visible():
    rs=(HERE/'tabs'/'research.py').read_text()
    assert rs.index('tlv.render(st)')>rs.index("st.subheader('🥅 First Goal Intelligence')")
    assert rs.index('tlv.render(st)')<rs.index('    if _rx:\n        st.download_button')
