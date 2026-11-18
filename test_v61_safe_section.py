"""V6.1 white-screen hardening: a failing section shows a compact warning, the other tabs still render, and Streamlit
control flow (st.stop / st.rerun) is never swallowed. Offline (v54_testkit fakes every HTTP call)."""
import pytest

import safe_section_v61 as ss
from v54_testkit import run_app

TAB_LABELS = ('🏠 Home', '🎯 Matchup Center', '⚡ Odds', '📊 Research', '🔮 Numbers', '🧪 EdgeLab', '⏱ Live Next Goal',
              '🚩 Edge Flags', '📰 Storylines', '🧠 Prediction Models')


# ---------------------------------------------------------------- unit: safe_section / safe_callback
class _FakeSt:
    def __init__(self):
        self.calls, self.session_state = [], {}

    def warning(self, msg):
        self.calls.append(('warning', msg))

    def caption(self, msg):
        self.calls.append(('caption', msg))

    def toast(self, msg):
        self.calls.append(('toast', msg))

    def expander(self, *a, **k):
        import contextlib
        return contextlib.nullcontext()


def test_exception_becomes_warning_and_is_recorded():
    fake = _FakeSt()
    with ss.safe_section('Odds board', st=fake) as sec:
        raise ValueError('boom')
    assert isinstance(sec.failed, ValueError)
    assert fake.calls[0][0] == 'warning' and 'Odds board' in fake.calls[0][1]
    assert fake.calls[1] == ('caption', 'ValueError: boom')
    assert fake.session_state[ss.STATE_KEY] == [{'section': 'Odds board', 'error': 'ValueError'}]


def test_no_failure_renders_nothing():
    fake = _FakeSt()
    with ss.safe_section('Quiet', st=fake) as sec:
        x = 1 + 1
    assert x == 2 and sec.failed is None and fake.calls == [] and fake.session_state == {}


def test_recorded_errors_are_bounded():
    fake = _FakeSt()
    for i in range(ss.MAX_RECORDED + 15):
        with ss.safe_section(f's{i}', st=fake):
            raise KeyError(i)
    assert len(fake.session_state[ss.STATE_KEY]) == ss.MAX_RECORDED


@pytest.mark.parametrize('make', [
    lambda: __import__('streamlit.runtime.scriptrunner_utils.exceptions', fromlist=['StopException']).StopException(),
    lambda: __import__('streamlit.runtime.scriptrunner_utils.exceptions', fromlist=['RerunException']).RerunException(None),
    lambda: KeyboardInterrupt(),
    lambda: SystemExit(1),
])
def test_control_flow_is_reraised(make):
    exc = make()
    fake = _FakeSt()
    with pytest.raises(type(exc)):
        with ss.safe_section('Never swallow', st=fake):
            raise exc
    assert fake.calls == []
    calls = []

    @ss.safe_callback(st=fake)
    def cb():
        calls.append(1)
        raise exc
    with pytest.raises(type(exc)):
        cb()
    assert calls == [1] and fake.calls == []


def test_fragment_error_already_shown_is_absorbed_quietly():
    from streamlit.errors import FragmentHandledException
    fake = _FakeSt()
    with ss.safe_section('Fragment host', st=fake) as sec:
        raise FragmentHandledException(ValueError('drawn in place'))
    assert isinstance(sec.failed, FragmentHandledException)
    assert fake.calls == []   # no second warning on top of the fragment's own error box
    assert fake.session_state[ss.STATE_KEY][0]['error'] == 'FragmentHandledException'


def test_decorator_form_and_safe_call():
    fake = _FakeSt()

    @ss.safe_section('Decorated', st=fake)
    def broken():
        raise RuntimeError('x')
    assert broken() is None and fake.calls[0][0] == 'warning'
    assert ss.safe_call('ok', lambda a: a * 2, 4, st=fake) == 8
    assert ss.safe_call('bad', lambda: 1 / 0, default='fallback', st=fake) == 'fallback'


def test_callback_failure_is_a_toast_not_a_crash():
    fake = _FakeSt()

    @ss.safe_callback(st=fake)
    def cb(a, b=0):
        return a / b
    assert cb(1, b=2) == 0.5
    assert cb(1) is None
    assert fake.calls == [('toast', '⚠️ That control could not be applied. Please try again.')]
    assert fake.session_state[ss.STATE_KEY][0]['error'] == 'ZeroDivisionError'


def test_secrets_are_redacted_from_messages():
    msg = ss.redact("HTTPSConnectionPool: /v4/sports?apiKey=abc123SECRET&regions=us token=xyz password=hunter2")
    assert 'abc123SECRET' not in msg and 'xyz' not in msg and 'hunter2' not in msg and 'regions=us' in msg
    assert len(ss.redact('a' * 1000)) == 300


def test_every_callback_in_tabs_is_guarded():
    import re
    from pathlib import Path
    for f in ('matchup', 'numbers', 'nextgoal'):
        src = (Path(__file__).resolve().parent / 'tabs' / f'{f}.py').read_text(encoding='utf-8')
        names = set(re.findall(r'on_(?:click|change)=(\w+)', src))
        assert names, f
        for n in names:
            assert re.search(r'@safe_callback[^\n]*\n\s*def ' + n + r'\b', src), (f, n)


# ---------------------------------------------------------------- AppTest: one failing tab, the rest still render
def _tab(at, label):
    return next(t for t in at.tabs if t.label == label)


def _content(block):
    return len(block.markdown) + len(block.get('html')) + len(block.dataframe) + len(block.caption)


def _failing_run_tab(monkeypatch, fail, how='raise'):
    import tabs
    real = tabs.run_tab

    def run_tab(name, ns):
        if name == fail:
            if how == 'stop':
                ns['st'].stop()
            raise RuntimeError(f'injected failure in {name}')
        return real(name, ns)
    monkeypatch.setattr(tabs, 'run_tab', run_tab)


@pytest.mark.parametrize('fail', ['numbers', 'research', 'home'])
def test_failing_tab_shows_fallback_and_other_tabs_render(monkeypatch, tmp_path, fail):
    _failing_run_tab(monkeypatch, fail)
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception, [e.value for e in at.exception]
    label = {'numbers': '🔮 Numbers', 'research': '📊 Research', 'home': '🏠 Home'}[fail]
    warn = [w.value for w in _tab(at, label).warning]
    assert any('could not load right now' in w for w in warn), warn
    others = [lbl for lbl in TAB_LABELS if lbl != label]
    for lbl in others:
        t = _tab(at, lbl)
        assert _content(t) > 0, lbl
        assert not any('tab could not load' in w.value for w in t.warning), (lbl, [w.value for w in t.warning])
    if fail == 'research':   # Numbers reads _TEAM_NAMES, which tabs/research.py defines last
        assert any('Universal day' in m.value or 'NUMBERS' in m.value for m in _tab(at, '🔮 Numbers').markdown)


def test_failing_live_state_keeps_every_tab_up(monkeypatch, tmp_path):
    _failing_run_tab(monkeypatch, 'live')
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception, [e.value for e in at.exception]
    assert any('Live scores and next-goal data' in w.value for w in at.warning)
    for lbl in TAB_LABELS:
        assert _content(_tab(at, lbl)) > 0, lbl


def test_st_stop_is_not_swallowed(monkeypatch, tmp_path):
    _failing_run_tab(monkeypatch, 'odds', how='stop')
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    assert not any('could not load' in w.value for w in at.warning)   # stop is not reported as a failure
    assert _content(_tab(at, '🏠 Home')) > 0                         # Home ran before Odds
    assert _content(_tab(at, '📊 Research')) == 0                     # the script really stopped at Odds


def test_no_failure_means_no_fallback(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    assert not any('could not load right now' in w.value for w in at.warning)
    assert ss.STATE_KEY not in at.session_state
