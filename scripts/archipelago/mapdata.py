#!/usr/bin/env python3
"""Map data for a git repo, read only from git.

Usage: mapdata.py REPO [ALIAS=CANONICAL ...] > map.json

Turns are the first-parent commits of HEAD, oldest first.
Civilization of a commit: first Co-authored-by name, else the author name (after aliases).
Citizen of a commit: its Claude-Session trailer, else "<civ> (no session)".
Owner of a file at a turn: the commit `git log -1 <turn> -- <file>` returns. Computed down the first-parent line:
a commit that changes the file owns it; a merge passes ownership through the first parent it kept the file from
unchanged, and owns the file itself only if it matches no parent.
Contested at a merge turn: files changed on both sides since the merge base.
Layout: one island per top-level folder in a fixed MAP_W x MAP_H sea. Each island is seeded noise smoothed by a
cellular automaton (the 4-5 rule), then grown or eroded to exactly its file count plus SPARE coast. Inside an island,
subfolders sit together and each subfolder's most-changed files sit nearest the island's center. Seeded by the repo URL,
so a rebuild of the same history draws the same map.
"""
import hashlib, heapq, json, math, random, subprocess, sys

repo, aliases = sys.argv[1], dict(a.split('=', 1) for a in sys.argv[2:])


def git(*args):
    return subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, check=True).stdout


def lines(s):
    return [l for l in s.split('\n') if l]


# --- commits -------------------------------------------------------------
F, R = '\x1f', '\x1e'
fmt = R + F.join(['%H', '%P', '%an', '%ad', '%s',
                  '%(trailers:key=Co-authored-by,valueonly,separator=%x1d)',
                  '%(trailers:key=Claude-Session,valueonly,separator=%x1d)'])
commits, cidx = [], {}
for rec in git('log', '--reverse', '--topo-order', '--date=short', f'--format={fmt}').split(R)[1:]:
    h, parents, author, date, subject, coauth, session = rec.rstrip('\n').split(F)
    author = aliases.get(author, author)
    co = coauth.split('\x1d')[0].split('<')[0].strip() if coauth.strip() else ''
    civ = aliases.get(co, co) if co else author
    sid = session.split('\x1d')[0].strip().rsplit('session_', 1)[-1] if session.strip() else ''
    cidx[h] = len(commits)
    commits.append(dict(h=h[:7], d=date, s=subject, a=author, civ=civ,
                        cit=f'session …{sid[-6:]}' if sid else f'{civ} (no session)',
                        merge=len(parents.split()) > 1))

civs = sorted({c['civ'] for c in commits}, key=lambda v: (-sum(c['civ'] == v for c in commits), v))
citizens = sorted({(c['civ'], c['cit']) for c in commits},
                  key=lambda k: (civs.index(k[0]), -sum((c['civ'], c['cit']) == k for c in commits), k[1]))

# --- turns ---------------------------------------------------------------
turn_hashes = lines(git('rev-list', '--first-parent', '--reverse', 'HEAD'))
paths, pidx = [], {}


def pid(p):
    if p not in pidx:
        pidx[p] = len(paths)
        paths.append(p)
    return pidx[p]


turns, prev_tree, prev_owner, prev = [], set(), {}, None
for t in turn_hashes:
    tree = set(lines(git('ls-tree', '-r', '--name-only', t)))
    ps = git('log', '-1', '--format=%P', t).split()
    differs = [set(lines(git('diff-tree', '-r', '--no-renames', '--name-only', q, t))) for q in ps]
    owner = {}
    for p in tree:  # same history simplification as `git log -1 -- p`: follow the first parent the file is unchanged from
        k = next((i for i, d in enumerate(differs) if p not in d), None)
        owner[p] = cidx[t] if k is None else prev_owner[p] if k == 0 else \
            cidx[git('log', '-1', '--format=%H', ps[k], '--', p).strip()]
    moves = lines(git('rev-list', '--reverse', '--topo-order', t, *([f'^{prev}'] if prev else [])))
    contested = []
    if len(ps) == 2:
        base = git('merge-base', ps[0], ps[1]).strip()
        both = set(lines(git('diff', '--no-renames', '--name-only', base, ps[0]))) & \
               set(lines(git('diff', '--no-renames', '--name-only', base, ps[1])))
        for p in sorted(both):
            contested.append(dict(p=pid(p),
                                  main=[cidx[h] for h in lines(git('rev-list', f'{base}..{ps[0]}', '--', p))],
                                  branch=[cidx[h] for h in lines(git('rev-list', f'{base}..{ps[1]}', '--', p))]))
    turns.append(dict(c=cidx[t],
                      add=[pid(p) for p in sorted(tree - prev_tree)],
                      rm=[pid(p) for p in sorted(prev_tree - tree)],
                      own=[[pid(p), owner[p]] for p in sorted(tree) if owner.get(p) != prev_owner.get(p)],
                      moves=[cidx[h] for h in moves],
                      contested=contested))
    prev_tree, prev_owner, prev = tree, owner, t

# files each commit touched (mapped paths only), same rule as ownership
touched, cur = {}, None
for l in git('log', '--no-renames', '--cc', '--format=@%H', '--name-only', 'HEAD').split('\n'):
    if l.startswith('@'):
        cur = touched.setdefault(cidx[l[1:]], [])
    elif l in pidx:
        cur.append(pidx[l])


# --- layout --------------------------------------------------------------
def jitter(key, cell):
    return int(hashlib.sha1(f'{key}:{cell[0]},{cell[1]}'.encode()).hexdigest()[:8], 16) / 2**32


def nbrs(c):
    return [(c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)]


def region(p):
    return p.split('/')[0] if '/' in p else '(root)'


def group(p):
    parts = p.split('/')
    return '/'.join(parts[:2]) if len(parts) > 2 else region(p)


MAP_W, MAP_H, SPARE = 42, 30, 0.35
origin = git('remote', 'get-url', 'origin').strip()
churn = {}
for fs in touched.values():
    for p in fs:
        churn[p] = churn.get(p, 0) + 1


def moore(c):
    return [(c[0] + dx, c[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def inside(c):
    return 1 <= c[0] < MAP_W - 1 and 1 <= c[1] < MAP_H - 1


def component(cells, start):
    seen, todo = {start}, [start]
    while todo:
        for n in nbrs(todo.pop()):
            if n in cells and n not in seen:
                seen.add(n)
                todo.append(n)
    return seen


def ca_island(name, seed, radius, target, blocked):
    allowed = lambda c: inside(c) and c not in blocked
    grid = [(x, y) for y in range(MAP_H) for x in range(MAP_W)]
    best = None
    for s in [0.8 + 0.1 * i for i in range(11)]:  # pick the noise scale whose smoothed island is closest to target
        rng = random.Random(f'{origin}:{name}')
        land = set()
        for c in grid:
            d = math.dist(c, seed) / (s * radius)
            if rng.random() < (0.95 if d < 0.6 else max(0.0, 0.95 * (1.5 - d) / 0.9)) and allowed(c):
                land.add(c)
        for _ in range(4):  # 4-5 rule: land with >=5 land neighbours, or land staying land with >=4
            land = {c for c in grid if allowed(c) and (sum(n in land for n in moore(c)) >= (4 if c in land else 5))}
        if land:
            comp = component(land, min(land, key=lambda c: math.dist(c, seed)))
            if best is None or abs(len(comp) - target) < abs(len(best) - target):
                best = comp
    cells = best or {min(filter(allowed, grid), key=lambda c: math.dist(c, seed))}
    while len(cells) < target:  # grow along the coast nearest the seed
        cands = {n for c in cells for n in nbrs(c) if allowed(n) and n not in cells}
        assert cands, f'no room to grow {name}'
        cells.add(min(cands, key=lambda c: math.dist(c, seed) + 1.5 * jitter(name, c)))
    while len(cells) > target:  # erode the farthest coast that keeps the island in one piece
        coast = sorted((c for c in cells if any(n not in cells for n in nbrs(c))),
                       key=lambda c: -(math.dist(c, seed) + 1.5 * jitter(name, c)))
        cells.discard(next(c for c in coast if len(component(cells - {c}, next(iter(cells - {c})))) == len(cells) - 1))
    return cells


regions = sorted({region(p) for p in paths}, key=lambda r: (-sum(region(p) == r for p in paths), r))
need = {r: sum(region(p) == r for p in paths) for r in regions}
target = {r: need[r] + (round(need[r] * SPARE) if need[r] > 2 else 1) for r in regions}
radius = {r: math.sqrt(target[r] / math.pi) for r in regions}
rng, mid = random.Random(f'{origin}:seeds'), ((MAP_W - 1) / 2, (MAP_H - 1) / 2)
seeds, island, land = {}, {}, set()
for r in regions:  # largest first, each as near the middle as spacing allows
    cands = [c for c in ((rng.uniform(radius[r] + 1.5, MAP_W - 2.5 - radius[r]),
                          rng.uniform(radius[r] + 1.5, MAP_H - 2.5 - radius[r])) for _ in range(3000))
             if all(math.dist(c, seeds[o]) >= radius[r] + radius[o] + 2.5 for o in seeds)]
    assert cands, f'map too small for {r}'
    seeds[r] = min(cands, key=lambda c: math.dist(c, mid))
    island[r] = ca_island(r, seeds[r], radius[r], target[r], land | {n for c in land for n in moore(c)})
    land |= island[r]

cell_of, spare = {}, []
for r in regions:
    free, placed = set(island[r]), set()
    mean = (sum(c[0] for c in free) / len(free), sum(c[1] for c in free) / len(free))
    center = min(free, key=lambda c: (math.dist(c, mean), c))
    groups = sorted({group(p) for p in paths if region(p) == r},
                    key=lambda g: (-sum(group(p) == g for p in paths), g))
    for g in groups:
        files = sorted((p for p in paths if group(p) == g), key=lambda p: (-churn.get(pidx[p], 0), p))
        cands = {n for c in placed for n in nbrs(c) if n in free}
        seed = min(cands, key=lambda c: (math.dist(c, center), jitter(g, c))) if cands else center
        heap, seen, order = [(0.0, seed)], {seed}, []
        while len(order) < len(files):
            if not heap:  # this subfolder's pocket filled; continue in the nearest free cell
                c0 = min((c for c in free if c not in seen), key=lambda c: math.dist(c, seed))
                seen.add(c0)
                heap.append((0.0, c0))
            _, c = heapq.heappop(heap)
            order.append(c)
            for n in nbrs(c):
                if n in free and n not in seen:
                    seen.add(n)
                    heapq.heappush(heap, (math.dist(n, seed) + 0.75 * jitter(g, n), n))
        for f, c in zip(files, order):
            cell_of[f] = c
            free.discard(c)
            placed.add(c)
    spare += [[c[0], c[1], r] for c in sorted(free)]

json.dump(dict(repo=origin, head=turn_hashes[-1][:7], grid=[MAP_W, MAP_H], spare=spare,
               civs=civs, citizens=[list(k) for k in citizens],
               commits=[dict(h=c['h'], d=c['d'], s=c['s'], a=c['a'], civ=civs.index(c['civ']),
                             cit=citizens.index((c['civ'], c['cit'])), merge=c['merge'],
                             f=sorted(touched.get(i, []))) for i, c in enumerate(commits)],
               paths=[dict(p=p, x=cell_of[p][0], y=cell_of[p][1], r=region(p), g=group(p)) for p in paths],
               turns=turns), sys.stdout, separators=(',', ':'))
