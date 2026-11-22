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


BACKUP_NAMES = ('ODDS_API_KEY_2', 'ODDS_API_KEY2', 'ODDS_API_KEY_BACKUP', 'ODDS_API_KEY_SECONDARY', 'ODDS_API_KEY_ALT',
                'ODDS_API_KEY_FALLBACK', 'BACKUP_ODDS_API_KEY', 'SECONDARY_ODDS_API_KEY', 'THE_ODDS_API_KEY_2',
                'ODDS_API_BACKUP_KEY', 'ODDS_KEY_2')
BACKUP_SECTION_KEYS = ('API_KEY_2', 'KEY_2', 'BACKUP', 'BACKUP_KEY', 'BACKUP_API_KEY', 'SECONDARY', 'SECONDARY_KEY',
                       'SECONDARY_API_KEY', 'FALLBACK_KEY', 'ALT_KEY') + BACKUP_NAMES
SGO_NAMES = ('SGO_API_KEY', 'SPORTSGAMEODDS_API_KEY', 'SPORTS_GAME_ODDS_API_KEY', 'SGO_KEY', 'SPORTSGAMEODDS_KEY')


def find_extra_keys(secrets=None, environ=None, primary=''):
    """Second odds credentials, by location only (values are returned for use, never shown):
    {'backup': (value, where) | None   # a second The Odds API key: failover on 401/403/429
     'sgo': (value, where) | None      # SportsGameOdds key (SGO_API_KEY): merged game-line books
     'other': [names]}                 # other odds-named secrets this app has no documented adapter for (not used)"""
    environ = os.environ if environ is None else environ
    top = _items(secrets) if secrets is not None else []
    out, used = {'backup': None, 'sgo': None, 'other': []}, set()
    primary = primary.strip() if isinstance(primary, str) else ''

    def ok(v):
        return isinstance(v, str) and v.strip() and v.strip() != primary

    for k, v in top:
        n = _norm(k)
        if out['backup'] is None and n in BACKUP_NAMES and ok(v):
            out['backup'] = (v.strip(), f'secrets: top-level {k}'); used.add(k)
        elif out['sgo'] is None and n in SGO_NAMES and isinstance(v, str) and v.strip():
            out['sgo'] = (v.strip(), f'secrets: top-level {k}'); used.add(k)
    for k, v in top:
        if not isinstance(v, Mapping):
            continue
        n = _norm(k)
        for sk, sv in _items(v):
            sn = _norm(sk)
            if out['sgo'] is None and (('SGO' in n or 'SPORTSGAMEODDS' in n.replace('_', '')) and sn in SECTION_KEYS
                                       or sn in SGO_NAMES) and isinstance(sv, str) and sv.strip():
                out['sgo'] = (sv.strip(), f'secrets: [{k}] {sk}')
            elif out['backup'] is None and ('ODDS' in n and sn in BACKUP_SECTION_KEYS or sn in BACKUP_NAMES) and ok(sv):
                out['backup'] = (sv.strip(), f'secrets: [{k}] {sk}')
    if out['backup'] is None:   # a second alias at top level holding a DIFFERENT value than the primary key
        for k, v in top:
            if k != 'ODDS_API_KEY' and _norm(k) in ALIASES and ok(v) and primary:
                out['backup'] = (v.strip(), f'secrets: top-level {k}'); used.add(k)
                break
    for name in BACKUP_NAMES:
        if out['backup'] is None and ok(environ.get(name)):
            out['backup'] = (environ[name].strip(), f'environment: {name}')
    for name in SGO_NAMES:
        if out['sgo'] is None and isinstance(environ.get(name), str) and environ[name].strip():
            out['sgo'] = (environ[name].strip(), f'environment: {name}')
    known = set(ALIASES) | set(BACKUP_NAMES) | set(SGO_NAMES)
    out['other'] = sorted(k for k, v in top if isinstance(v, str) and _norm(k) not in known
                          and any(t in _norm(k) for t in ('ODDS', 'JAM', 'BOOK', 'ESPN', 'DRAFTKINGS', 'FANDUEL')))
    return out


def extra_caption(extra):
    """Sidebar stamp addition, same style as the primary 'Odds key: found (...)': locations only."""
    x = extra or {}
    parts = []
    parts.append(f"Backup Odds API key: found ({x['backup'][1]}; failover on 401/403/429)" if x.get('backup')
                 else 'Backup Odds API key: not found')
    parts.append(f"SportsGameOdds key: found ({x['sgo'][1]}; game-line books)" if x.get('sgo') else 'SportsGameOdds key: not found')
    if x.get('other'):
        parts.append('Other odds-named secrets (no adapter, not used): ' + ', '.join(x['other']))
    return ' · '.join(parts)


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


def sidebar_caption(stamp, key_where, extra=None):
    b = stamp or {}
    build = f"Build {b.get('commit', 'unknown')}" + (f" ({b['branch']})" if b.get('branch') else '') + f' · {CODE_MARK}'
    odds = f'Odds key: found ({key_where})' if key_where else 'Odds key: not found in Streamlit secrets (expected top-level ODDS_API_KEY)'
    return f'{build} · {odds}' + (f' · {extra_caption(extra)}' if extra is not None else '')
