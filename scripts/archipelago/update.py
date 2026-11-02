#!/usr/bin/env python3
"""Rebuild data/archipelago.json from the owner's public, non-fork repositories.

Usage: update.py OWNER OUT

1. List the owner's public repositories (GitHub API through `gh`; forks left out).
2. Clone each with full history. Note each one's latest commit; for this site's own repository, skip the commits
   this job makes, so the map never chases its own updates. If none moved since the last build, stop here.
3. Extract each repository with mapdata.py and check every file at every turn against git with verify_git.py.
   Any mismatch stops the run.
4. Lay out the islands with web_export.py and replace OUT.
On any failure OUT is left as it was and the script exits non-zero.
"""
import json, os, re, subprocess, sys, tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OWNER, OUT = sys.argv[1], sys.argv[2]
SELF = os.environ.get('GITHUB_REPOSITORY', f'{OWNER}/portfolio').split('/', 1)[1]
UPDATE_SUBJECT = 'Update archipelago map'  # the workflow's commit message
ALIASES = ['enactedvolition=EV Campbell', 'BobGnarly420=EV Campbell']  # one GitHub account, three names


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


names = sorted(run('gh', 'api', '--paginate', f'users/{OWNER}/repos?type=owner&per_page=100',
                   '--jq', '.[] | select(.private | not) | select(.fork | not) | .name').split())
work = tempfile.mkdtemp()
sources, built, empty = {}, [], []
for name in names:
    d = os.path.join(work, name)
    run('git', 'clone', '--quiet', f'https://github.com/{OWNER}/{name}', d)
    if subprocess.run(['git', '-C', d, 'rev-parse', '--verify', '-q', 'HEAD'], capture_output=True).returncode:
        sources[name] = None
        empty.append(name)
        continue
    grep = ['--invert-grep', f'--grep=^{UPDATE_SUBJECT}$'] if name == SELF else []
    sources[name] = run('git', '-C', d, 'log', '-1', '--format=%H', *grep).strip()
    built.append(name)

try:
    previous = json.load(open(OUT)).get('sources')
except (OSError, ValueError):
    previous = None
if previous == sources:
    print(f'unchanged: {len(built)} repos, {len(empty)} empty')
    sys.exit(0)

checked = 0
for name in built:
    d, m = os.path.join(work, name), os.path.join(work, name + '.json')
    with open(m, 'w') as f:
        subprocess.run([sys.executable, os.path.join(HERE, 'mapdata.py'), d, *ALIASES], stdout=f, check=True)
    res = run(sys.executable, os.path.join(HERE, 'verify_git.py'), d, m)
    n, bad, dup = map(int, re.search(r'tiles checked (\d+) mismatches (\d+) duplicate cells (\d+)', res).groups())
    if bad or dup:
        sys.exit(f'::error::{name}: {bad} owner mismatches, {dup} duplicate cells against git\n{res}')
    checked += n

cfg = os.path.join(work, 'config.json')
json.dump(dict(date=datetime.now(timezone.utc).strftime('%Y-%m-%d'), sources=sources,
               repos=[dict(name=n, dir=os.path.join(work, n), map=os.path.join(work, n + '.json'),
                           url=f'https://github.com/{OWNER}/{n}') for n in built],
               empty=[dict(name=n, url=f'https://github.com/{OWNER}/{n}') for n in empty]), open(cfg, 'w'))
run(sys.executable, os.path.join(HERE, 'web_export.py'), cfg, os.path.join(HERE, 'templeos-font.json'), OUT + '.tmp')
os.replace(OUT + '.tmp', OUT)
print(f'rebuilt: {len(built)} repos, {len(empty)} empty, {checked} file states checked against git')
