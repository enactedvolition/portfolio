# Replays map.json turn by turn and checks every tile against git directly.
import json, subprocess, sys
repo, d = sys.argv[1], json.load(open(sys.argv[2]))
git = lambda *a: subprocess.run(['git', '-C', repo, *a], capture_output=True, text=True, check=True).stdout
fp = git('rev-list', '--first-parent', '--reverse', 'HEAD').split()
assert len(fp) == len(d['turns']), 'turn count'
tree, own, bad, checked = set(), {}, [], 0
for i, (t, h) in enumerate(zip(d['turns'], fp)):
    assert d['commits'][t['c']]['h'] == h[:7], f'turn {i} hash'
    tree |= set(t['add']); tree -= set(t['rm'])
    for p, c in t['own']: own[p] = c
    real = set(git('ls-tree', '-r', '--name-only', h).split('\n')) - {''}
    names = {d['paths'][p]['p'] for p in tree}
    if names != real: bad.append((i, 'tree', len(names ^ real)))
    for p in tree:
        g = git('log', '-1', '--no-renames', '--format=%h', h, '--', d['paths'][p]['p']).strip()
        checked += 1
        if g != d['commits'][own[p]]['h']: bad.append((i, d['paths'][p]['p'], d['commits'][own[p]]['h'], g))
cells = [(p['x'], p['y']) for p in d['paths']] + [(s[0], s[1]) for s in d.get('spare', [])]
gw, gh = d.get('grid', (10**9, 10**9))
assert all(0 <= x < gw and 0 <= y < gh for x, y in cells), 'cell outside the map grid'
print('tiles checked', checked, 'mismatches', len(bad), 'duplicate cells', len(cells) - len(set(cells)))
for b in bad[:20]: print(b)
