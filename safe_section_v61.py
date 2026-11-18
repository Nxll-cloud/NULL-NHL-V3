"""V6.1 white-screen hardening: one failing section shows a compact warning instead of killing the whole page.

``safe_section(name)``  context manager (or ``@safe_section(name)`` decorator) around a tab body / major section.
``safe_callback(fn)``   wraps a widget ``on_click`` / ``on_change`` callback (callbacks run BEFORE the script, so an
                        uncaught error there replaces the entire page with a traceback).

Only ``Exception`` subclasses are handled. Streamlit control flow (st.stop / st.rerun / st.switch_page raise
StopException / RerunException, both ``BaseException`` subclasses) is always re-raised, as are KeyboardInterrupt /
SystemExit. FragmentHandledException means a fragment already drew its own error box in place; left alone it would end
the WHOLE script run (every later tab blank), so a section absorbs it quietly (logged, no second warning). The traceback goes to the server log (Streamlit Cloud "Manage app" logs);
the page shows only the section name, the exception type and a short message with any key/token query values
redacted. When nothing fails, nothing is rendered: output is identical to the unwrapped code.
"""
import contextlib
import functools
import logging
import re
import traceback

LOG = logging.getLogger('nulls_playbook.safe_section')
STATE_KEY = '_np_section_errors'   # bounded list of recent failures in st.session_state (diagnostics only)
MAX_RECORDED = 20
_SECRET_RE = re.compile(r'(?i)((?:api[_-]?key|apikey|key|token|secret|password|auth)=)[^&\s\'"]+')


def _control_types():
    found = []
    for mod, names in (('streamlit.runtime.scriptrunner_utils.exceptions', ('ScriptControlException', 'StopException', 'RerunException')),
                       ('streamlit.runtime.scriptrunner', ('StopException', 'RerunException'))):
        try:
            m = __import__(mod, fromlist=list(names))
        except Exception:   # older/newer Streamlit layout: the isinstance(Exception) test below still protects control flow
            continue
        found.extend(t for t in (getattr(m, n, None) for n in names) if isinstance(t, type))
    return tuple(dict.fromkeys(found))


CONTROL_FLOW = _control_types()
try:
    from streamlit.errors import FragmentHandledException as _Handled
    ALREADY_SHOWN = (_Handled,)
except Exception:   # pragma: no cover - Streamlit without fragments
    ALREADY_SHOWN = ()


def is_control_flow(exc):
    """True for anything that must propagate: Streamlit stop/rerun control and every non-Exception."""
    return isinstance(exc, CONTROL_FLOW) or not isinstance(exc, Exception)


def redact(text, limit=300):
    text = _SECRET_RE.sub(r'\1[redacted]', str(text or ''))
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _streamlit():
    import streamlit
    return streamlit


def _record(st, name, exc):
    try:
        errs = st.session_state.setdefault(STATE_KEY, [])
        errs.append({'section': name, 'error': type(exc).__name__})
        del errs[:-MAX_RECORDED]
    except Exception:   # no session (bare mode) or state unavailable: logging already happened
        pass


def report(name, exc, st=None, fallback=None):
    """Log ``exc`` with its traceback and show the compact fallback. Never raises (except control flow)."""
    LOG.error('Section %r failed: %s', name, redact(f'{type(exc).__name__}: {exc}', 2000))
    LOG.error('%s', redact(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)), 20000))
    st = st or _streamlit()
    _record(st, name, exc)
    try:
        st.warning(fallback or f'⚠️ {name} could not load right now. The rest of the page still works; '
                               'reload the page or try again in a minute.')
        with st.expander('Technical details', expanded=False):
            st.caption(f'{type(exc).__name__}: {redact(exc)}')
    except BaseException as render_exc:   # pragma: no cover - fallback itself failed (e.g. no script context)
        if is_control_flow(render_exc):
            raise
        LOG.error('Fallback for %r could not render: %r', name, render_exc)


class safe_section(contextlib.ContextDecorator):
    """``with safe_section('Home tab'): ...`` or ``@safe_section('Odds board')``. Exceptions -> warning + log."""

    def __init__(self, name, st=None, fallback=None):
        self.name, self.st, self.fallback = name, st, fallback
        self.failed = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None or is_control_flow(exc):
            return False
        self.failed = exc
        if isinstance(exc, ALREADY_SHOWN):   # the fragment's own error box is already on the page
            LOG.error('Section %r: fragment error already shown in place: %s', self.name, redact(repr(exc.__cause__ or exc), 2000))
            _record(self.st or _streamlit(), self.name, exc)
            return True
        report(self.name, exc, self.st, self.fallback)
        return True


def safe_callback(fn=None, *, name=None, st=None):
    """Decorator for widget callbacks: a failure becomes a toast/warning + log, and the script still runs."""
    if fn is None:
        return lambda f: safe_callback(f, name=name, st=st)
    label = name or getattr(fn, '__name__', 'callback')

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if is_control_flow(exc):
                raise
            LOG.error('Callback %r failed:\n%s', label,
                      redact(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)), 20000))
            s = st or _streamlit()
            _record(s, f'callback {label}', exc)
            try:
                s.toast('⚠️ That control could not be applied. Please try again.')
            except Exception:
                pass
            return None
    return wrapper


def safe_call(name, fn, *args, default=None, st=None, **kwargs):
    """Function form: ``value = safe_call('Odds feed', fetch, ...)`` -> ``default`` (and the fallback) on failure."""
    with safe_section(name, st):
        return fn(*args, **kwargs)
    return default   # reached only when the call failed (the fallback has been shown)
