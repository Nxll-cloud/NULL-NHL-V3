"""Null's Playbook V5.9 · Position gematria (Numbers tab curiosity layer).

Presentation only: runs each NHL position label through numerology_v48.gematria (same English / Reduced / Reverse
ciphers as the rest of the Numbers page) at render time. Not imported by any scoring, ranking, tier, TOP PICK or
match-table module, and it adds no day or arena matching.
"""
import html

from numerology_v48 import gematria

CURIOSITY_NOTE = 'Curiosity layer — not used in any score, rank, tier, TOP PICK or match table.'

# (display label, text fed to the cipher) in display order. Both spellings of defenceman are separate rows.
LABELS = (
    ('Center', 'Center'),
    ('Left Wing', 'Left Wing'),
    ('Right Wing', 'Right Wing'),
    ('Defenseman (US)', 'Defenseman'),
    ('Defenceman (Canadian)', 'Defenceman'),
    ('Defense', 'Defense'),
    ('Forward', 'Forward'),
    ('Goalie', 'Goalie'),
    ('Goaltender', 'Goaltender'),
    ('C', 'C'),
    ('L', 'L'),
    ('R', 'R'),
    ('D', 'D'),
    ('G', 'G'),
    ('LW', 'LW'),
    ('RW', 'RW'),
)


def rows():
    """One dict per label: label, text, and the gematria totals/roots computed now (never hardcoded)."""
    out = []
    for label, text in LABELS:
        v = gematria(text)
        out.append({'label': label, 'text': text,
                    'english': (v['ordinal'], v['ordinal_root']),
                    'reduced': (v['reduction'], v['reduction_root']),
                    'reverse': (v['reverse'], v['reverse_root'])})
    return out


def table_html(data=None):
    """Four-column table (Position | English | Reduced | Reverse), each cell 'total → root'. Reuses the .v58-gm table styles."""
    e = html.escape
    data = rows() if data is None else data
    cell = lambda pair: f'{int(pair[0])} → {int(pair[1])}'
    def name(label):   # '(US)' / '(Canadian)' tag sits on its own line so narrow screens never split a word
        base, _, tag = label.partition(' (')
        return f'<b>{e(base)}</b>' + (f'<small class="pg-sp">({e(tag)}</small>' if tag else '')
    trs = ''.join(f'<tr class="gm-r"><td class="gm-p">{name(r["label"])}</td>'
                  f'<td class="gm-n">{cell(r["english"])}</td><td class="gm-n">{cell(r["reduced"])}</td>'
                  f'<td class="gm-n">{cell(r["reverse"])}</td></tr>' for r in data)
    head = ('<div class="sh"><h3>Position gematria</h3><p>Each NHL position label run through the same three ciphers as '
            'the rest of this page · total → digit root · NHL codes (C, L, R, D, G, LW, RW) included</p></div>')
    table = ('<div class="gm-w"><table class="gm"><thead><tr><th>Position</th><th>English</th><th>Reduced</th>'
             f'<th>Reverse</th></tr></thead><tbody>{trs}</tbody></table></div>')
    return f'<section class="sec v58-gm v59-pg">{head}{table}<p class="gm-note">{e(CURIOSITY_NOTE)}</p></section>'
