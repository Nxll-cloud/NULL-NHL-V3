"""V6.1 deploy diagnostics: which commit is running, and where (never what) the odds key was found.

* build_stamp(): the checked-out commit read from .git at runtime (no subprocess), else a commit env var, else
  'unknown'. Lets anyone compare the live app with GitHub main.
* find_odds_key(secrets, environ): the documented top-level ODDS_API_KEY wins unchanged (including the existing
  'non-string = configuration error' behaviour). Only when it is absent: case variants / common aliases at top level,
  then an odds-named secrets section ([odds] api_key, [the_odds_api] key, ...), then the ODDS_API_KEY environment
  variable. Returns (value, where); `where` names the location only. Read on every rerun, never at import time.
"""
from collections.abc import Mapping
import os

ALIASES = ('ODDS_API_KEY', 'THE_ODDS_API_KEY', 'THEODDSAPI_KEY', 'ODDSAPI_KEY', 'ODDS_KEY')
SECTION_KEYS = ('ODDS_API_KEY', 'API_KEY', 'KEY', 'APIKEY')
ENV_NAMES = ('ODDS_API_KEY', 'THE_ODDS_API_KEY')
COMMIT_ENVS = ('GIT_COMMIT', 'COMMIT_SHA', 'GITHUB_SHA', 'SOURCE_COMMIT')
CODE_MARK = 'v6.1 price-gap scope'   # bump with user-visible releases; proves the code version even without .git
HERE = os.path.dirname(os.path.abspath(__file__))


def _items(m):
    try:
        return list(m.items())
    except Exception:   # st.secrets raises when no secrets file exists
        return []


def _norm(k):
    return str(k).strip().upper().replace('-', '_').replace(' ', '_')


def find_odds_key(secrets=None, environ=None):
    environ = os.environ if environ is None else environ
    top = _items(secrets) if secrets is not None else []
    for k, v in top:
        if k == 'ODDS_API_KEY':                       # documented location: unchanged semantics
            return (v.strip() if isinstance(v, str) else v), 'secrets: top-level ODDS_API_KEY'
    for k, v in top:
        if _norm(k) in ALIASES and isinstance(v, str) and v.strip():
            return v.strip(), f'secrets: top-level {k}'
    for k, v in top:
        if isinstance(v, Mapping) and 'ODDS' in _norm(k):
            for sk, sv in _items(v):
                if _norm(sk) in SECTION_KEYS + ALIASES and isinstance(sv, str) and sv.strip():
                    return sv.strip(), f'secrets: [{k}] {sk}'
    for k, v in top:                                   # any section holding an ODDS_API_KEY-style name
        if isinstance(v, Mapping):
            for sk, sv in _items(v):
                if _norm(sk) in ALIASES and isinstance(sv, str) and sv.strip():
                    return sv.strip(), f'secrets: [{k}] {sk}'
    for name in ENV_NAMES:
        v = environ.get(name)
        if isinstance(v, str) and v.strip():
            return v.strip(), f'environment: {name}'
    return '', None


def _read(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return fh.read().strip()
    except OSError:
        return ''


def build_stamp(root=HERE, environ=None):
    """{'commit': 12-char sha or 'unknown', 'source': 'git'|'env'|None, 'branch': name or ''}."""
    environ = os.environ if environ is None else environ
    git = os.path.join(root, '.git')
    if os.path.isfile(git):                           # worktree / submodule: 'gitdir: <path>'
        g = _read(git)
        git = os.path.join(root, g[7:].strip()) if g.startswith('gitdir:') else git
    head = _read(os.path.join(git, 'HEAD'))
    sha, branch = '', ''
    if head.startswith('ref:'):
        ref = head[4:].strip()
        branch = ref.rsplit('/', 1)[-1]
        sha = _read(os.path.join(git, *ref.split('/')))
        if not sha:
            for line in _read(os.path.join(git, 'packed-refs')).splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    sha = parts[0]
    elif len(head) >= 7:
        sha = head
    if sha and all(c in '0123456789abcdef' for c in sha.lower()):
        return {'commit': sha[:12], 'source': 'git', 'branch': branch}
    for name in COMMIT_ENVS:
        v = str(environ.get(name) or '').strip()
        if v:
            return {'commit': v[:12], 'source': 'env', 'branch': ''}
    return {'commit': 'unknown', 'source': None, 'branch': ''}


def sidebar_caption(stamp, key_where):
    b = stamp or {}
    build = f"Build {b.get('commit', 'unknown')}" + (f" ({b['branch']})" if b.get('branch') else '') + f' · {CODE_MARK}'
    odds = f'Odds key: found ({key_where})' if key_where else 'Odds key: not found in Streamlit secrets (expected top-level ODDS_API_KEY)'
    return f'{build} · {odds}'
