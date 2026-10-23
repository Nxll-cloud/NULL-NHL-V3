"""Audit P1.7: official basics (model card, changelog, notes location, ...)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _links(md):
    return [l for l in re.findall(r'\]\(([^)#]+)\)', md) if not l.startswith('http')]


def test_single_model_card_and_changelog_with_working_links():
    for name in ('MODEL_CARD.md', 'CHANGELOG.md'):
        assert (ROOT / name).is_file()
        for l in _links((ROOT / name).read_text()):
            assert (ROOT / l).exists(), (name, l)
    card = (ROOT / 'MODEL_CARD.md').read_text()
    for must in ('Power-play double count fixed', 'MODEL_PP_COHERENT', 'Shots-share baseline', 'MODEL_WINPROB_V2',
                 'Not betting advice', '1-800-GAMBLER', 'MoneyPuck', 'not** model output'):
        assert must in card, must


def test_release_notes_live_in_docs_notes_and_readme_points_there():
    assert not list(ROOT.glob('V*_NOTES.md')), 'release notes belong in docs/notes/'
    notes = {p.name for p in (ROOT / 'docs' / 'notes').glob('*.md')}
    assert {'V54_NOTES.md', 'V58_NOTES.md', 'V59_NOTES.md', 'V59_XG_NOTES.md'} <= notes
    readme = (ROOT / 'README.md').read_text()
    assert '(MODEL_CARD.md)' in readme and '(CHANGELOG.md)' in readme
    for ref in re.findall(r'`([^`]*_NOTES\.md)`', readme):
        assert ref.startswith('docs/notes/') and (ROOT / ref).is_file(), ref
    for py in ROOT.glob('*.py'):
        for ref in re.findall(r'(\S*V\d+(?:_XG)?_NOTES\.md)', py.read_text(errors='ignore')):
            assert ref.startswith('docs/notes/') or 'NOTES.md' not in ref or py.name.startswith('test_'), (py.name, ref)
