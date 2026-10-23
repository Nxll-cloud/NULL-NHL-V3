#!/usr/bin/env python3
"""V5.6 repo-size guard for GitHub uploads (V5.5 + per-file limit).

GitHub warns on files over 50 MB and rejects files over 100 MB. This script walks the repo (respecting
.gitignore: `git ls-files` when inside a git checkout, otherwise a small built-in .gitignore matcher),
lists the largest files, and exits non-zero when any file is over the fail limit.

    python check_repo_size.py                 # warn > 50 MB, fail > 95 MB, top 15
    python check_repo_size.py --top 25 --fail-mb 90 path/to/repo
    python check_repo_size.py --max-file-kb 100   # this repo's rule: every file < 100 KB (default)
    python check_repo_size.py --max-file-kb 0     # disable the per-file KB rule

Exit codes: 0 ok (warnings allowed), 1 a file is over the fail limit or the per-file KB limit.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from pathlib import Path

MB = 1024 * 1024
WARN_MB, FAIL_MB, TOP = 50, 95, 15
MAX_FILE_KB = 100   # V5.6: this repo keeps every file under 100 KB (configurable; 0 disables)
ALWAYS_SKIP = {'.git'}


def _patterns(root: Path):
    f = root / '.gitignore'
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        neg = line.startswith('!')
        pat = line[1:] if neg else line
        out.append((neg, pat))
    return out


def _match(rel: str, is_dir: bool, pat: str) -> bool:
    dir_only = pat.endswith('/')
    pat = pat.rstrip('/')
    if dir_only and not is_dir:
        return False
    anchored = '/' in pat.lstrip('/') or pat.startswith('/')
    pat = pat.lstrip('/')
    if anchored:
        return fnmatch.fnmatchcase(rel, pat)
    return fnmatch.fnmatchcase(rel.rsplit('/', 1)[-1], pat)


def ignored(rel: str, is_dir: bool, patterns) -> bool:
    """Minimal .gitignore semantics: last matching rule wins; '!' re-includes; 'dir/' matches directories."""
    hit = False
    for neg, pat in patterns:
        if _match(rel, is_dir, pat):
            hit = not neg
    return hit


def _git_files(root: Path):
    try:
        r = subprocess.run(['git', '-C', str(root), 'ls-files', '-co', '--exclude-standard', '-z'],
                           capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    top = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != root.resolve():
        return None  # only trust git when root is the repo top level
    return [root / p for p in r.stdout.decode('utf-8', 'replace').split('\0') if p]


def walk(root, use_gitignore=True):
    """Files that would be uploaded: [(relative path, size bytes)]."""
    root = Path(root)
    files = _git_files(root) if use_gitignore else None
    if files is None:
        pats = _patterns(root) if use_gitignore else []
        files = []
        for d, dirs, names in os.walk(root):
            rd = Path(d).relative_to(root).as_posix()
            rd = '' if rd == '.' else rd + '/'
            dirs[:] = [x for x in dirs if x not in ALWAYS_SKIP and not ignored(rd + x, True, pats)]
            files += [Path(d) / n for n in names if not ignored(rd + n, False, pats)]
    out = []
    for p in files:
        try:
            if p.is_file() and not p.is_symlink():
                out.append((p.relative_to(root).as_posix(), p.stat().st_size))
        except OSError:
            continue
    return sorted(out, key=lambda x: (-x[1], x[0]))


def human(n):
    return f'{n / MB:.2f} MB' if n >= MB else f'{n / 1024:.1f} KB'


def check(root='.', warn_mb=WARN_MB, fail_mb=FAIL_MB, top=TOP, use_gitignore=True, max_file_kb=None):
    """max_file_kb: per-file limit in KB (files must be strictly smaller); None/0 disables it."""
    files = walk(root, use_gitignore)
    warn = [(p, s) for p, s in files if s > warn_mb * MB]
    fail = [(p, s) for p, s in files if s > fail_mb * MB]
    over_kb = [(p, s) for p, s in files if max_file_kb and s >= max_file_kb * 1024]
    return {'files': files, 'total': sum(s for _, s in files), 'top': files[:top], 'warn': warn, 'fail': fail,
            'over_kb': over_kb, 'max_file_kb': max_file_kb or 0, 'ok': not fail and not over_kb}


def report(res, warn_mb=WARN_MB, fail_mb=FAIL_MB):
    lines = [f"{len(res['files'])} files · {human(res['total'])} total · largest: "
             + (f"{res['top'][0][0]} ({human(res['top'][0][1])})" if res['top'] else 'none'),
             f"Top {len(res['top'])} files:"]
    lines += [f'  {human(s):>10}  {p}' for p, s in res['top']]
    for p, s in res['warn']:
        if (p, s) not in res['fail']:
            lines.append(f'WARNING: {p} is {human(s)} (> {warn_mb} MB; GitHub warns above 50 MB)')
    for p, s in res['fail']:
        lines.append(f'FAIL: {p} is {human(s)} (> {fail_mb} MB; GitHub rejects files over 100 MB)')
    for p, s in res.get('over_kb', []):
        lines.append(f"FAIL: {p} is {human(s)} (per-file limit: every file must be < {res['max_file_kb']:g} KB)")
    if res.get('max_file_kb') and not res.get('over_kb'):
        lines.append(f"OK: every file is < {res['max_file_kb']:g} KB.")
    lines.append('OK: no file over the fail limit.' if res['ok'] else 'FAILED: remove or shrink the files above (see GITHUB_UPLOAD.md).')
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('root', nargs='?', default='.')
    ap.add_argument('--warn-mb', type=float, default=WARN_MB)
    ap.add_argument('--fail-mb', type=float, default=FAIL_MB)
    ap.add_argument('--top', type=int, default=TOP)
    ap.add_argument('--max-file-kb', type=float, default=MAX_FILE_KB, help='per-file limit in KB (0 disables; default %(default)s)')
    ap.add_argument('--no-gitignore', action='store_true', help='count ignored files too')
    a = ap.parse_args(argv)
    res = check(a.root, a.warn_mb, a.fail_mb, a.top, not a.no_gitignore, a.max_file_kb)
    print(report(res, a.warn_mb, a.fail_mb))
    return 0 if res['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
