#!/usr/bin/env python3
"""Data for the interactive archipelago: every path that ever existed on each repo's main line, laid out with the same
cellular-automaton island generator as archipelago.py, plus the per-turn history the page replays.

Usage: web_export.py config.json font.json out.json
config: {"date", "repos": [{"name", "dir", "map", "url"}], "empty": [{"name", "url"}]}
Each map is mapdata.py output, already checked turn by turn against git by verify_git.py.
"""
import collections, hashlib, heapq, json, math, random, sys

cfg, font, out = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
GW, GH, SPARE = 82, 52, 0.35

repos = []
for r in cfg['repos']:
    d = json.load(open(r['map']))
    repos.append(dict(r, d=d, n=len(d['paths'])))
civ_commits = collections.Counter(r['d']['civs'][c['civ']] for r in repos for c in r['d']['commits'])
civs = sorted(civ_commits, key=lambda c: (-civ_commits[c], c))
GLYPH = {'Claude Opus 5.5': 'Ö', 'Claude Opus 5': 'O', 'Claude Opus 4.8': 'o', 'Claude Fable 5': 'F', 'Claude': '?'}
top_human = max((c for c in civs if not c.startswith('Claude') and '[bot]' not in c), key=lambda c: civ_commits[c])
glyph = lambda c: GLYPH.get(c) or ('@' if c == top_human else c[7] if c.startswith('Claude ') else c[0].upper())
label = lambda c: 'Claude, no version' if c == 'Claude' else c.replace('Claude ', '').replace('[bot]', ' bot')


# --- island generator (same as archipelago.py / mapdata.py) -----------------------------------------
def jitter(key, cell): return int(hashlib.sha1(f'{key}:{cell[0]},{cell[1]}'.encode()).hexdigest()[:8], 16) / 2**32
def nbrs(c): return [(c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)]
def moore(c): return [(c[0] + dx, c[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
def inside(c): return 1 <= c[0] < GW - 1 and 1 <= c[1] < GH - 1


def component(cells, start):
    seen, todo = {start}, [start]
    while todo:
        for n in nbrs(todo.pop()):
            if n in cells and n not in seen:
                seen.add(n); todo.append(n)
    return seen


def ca_island(name, seed, radius, target, blocked):
    allowed = lambda c: inside(c) and c not in blocked
    grid = [(x, y) for y in range(GH) for x in range(GW)]
    best = None
    for s in [0.8 + 0.1 * i for i in range(11)]:
        rng = random.Random(f'archipelago:{name}')
        land = {c for c in grid if rng.random() < (0.95 if math.dist(c, seed) / (s * radius) < 0.6 else
                max(0.0, 0.95 * (1.5 - math.dist(c, seed) / (s * radius)) / 0.9)) and allowed(c)}
        for _ in range(4):
            land = {c for c in grid if allowed(c) and (sum(n in land for n in moore(c)) >= (4 if c in land else 5))}
        if land:
            comp = component(land, min(land, key=lambda c: math.dist(c, seed)))
            if best is None or abs(len(comp) - target) < abs(len(best) - target):
                best = comp
    cells = best or {min(filter(allowed, grid), key=lambda c: math.dist(c, seed))}
    while len(cells) < target:
        cands = {n for c in cells for n in nbrs(c) if allowed(n) and n not in cells}
        assert cands, f'no room to grow {name}'
        cells.add(min(cands, key=lambda c: math.dist(c, seed) + 1.5 * jitter(name, c)))
    while len(cells) > target:
        coast = sorted((c for c in cells if any(n not in cells for n in nbrs(c))),
                       key=lambda c: -(math.dist(c, seed) + 1.5 * jitter(name, c)))
        cells.discard(next(c for c in coast if len(component(cells - {c}, next(iter(cells - {c})))) == len(cells) - 1))
    return cells


repos.sort(key=lambda r: (-r['n'], r['name']))
rng, mid, land = random.Random('archipelago:seeds'), ((GW - 1) / 2, (GH - 1) / 2), set()
for r in repos:
    d, n = r['d'], r['n']
    r['target'] = n + (round(n * SPARE) if n > 2 else 1)
    r['radius'] = math.sqrt(r['target'] / math.pi)
    cands = [c for c in ((rng.uniform(r['radius'] + 2, GW - 3 - r['radius']), rng.uniform(r['radius'] + 3, GH - 4 - r['radius']))
                         for _ in range(4000)) if all(math.dist(c, o['seed']) >= r['radius'] + o['radius'] + 5 for o in repos if 'seed' in o)]
    assert cands, f"sea too small for {r['name']}"
    r['seed'] = min(cands, key=lambda c: math.dist(c, mid))
    cells = ca_island(r['name'], r['seed'], r['radius'], r['target'], land | {m for c in land for m in moore(c)})
    land |= cells
    churn = collections.Counter(p for c in d['commits'] for p in c['f'])
    free, placed, at = set(cells), set(), {}
    mean = (sum(c[0] for c in free) / len(free), sum(c[1] for c in free) / len(free))
    center = min(free, key=lambda c: (math.dist(c, mean), c))
    top = lambda i: d['paths'][i]['r']
    for g in sorted({top(i) for i in range(n)}, key=lambda g: (-sum(top(i) == g for i in range(n)), g)):
        fs = sorted((i for i in range(n) if top(i) == g), key=lambda i: (-churn[i], d['paths'][i]['p']))
        near = {m for c in placed for m in nbrs(c) if m in free}
        seed = min(near, key=lambda c: (math.dist(c, center), jitter(g, c))) if near else center
        heap, seen, order = [(0.0, seed)], {seed}, []
        while len(order) < len(fs):
            if not heap:
                c0 = min((c for c in free if c not in seen), key=lambda c: math.dist(c, seed)); seen.add(c0); heap.append((0.0, c0))
            _, c = heapq.heappop(heap); order.append(c)
            for m in nbrs(c):
                if m in free and m not in seen:
                    seen.add(m); heapq.heappush(heap, (math.dist(m, seed) + 0.75 * jitter(g, m), m))
        for i, c in zip(fs, order):
            at[i] = c; free.discard(c); placed.add(c)
    r['at'], r['spare'] = at, sorted(free)

empty = []
for e in cfg.get('empty', []):
    spot = min(((x, y) for y in range(4, GH - 4) for x in range(4, GW - 4)
                if all(math.dist((x, y), c) > 5 for c in land) and all(math.dist((x, y), (o['x'], o['y'])) > 8 for o in empty)),
               key=lambda c: math.dist(c, mid))
    empty.append(dict(name=e['name'], url=e['url'], x=spot[0], y=spot[1]))

ci = {c: i for i, c in enumerate(civs)}
data = dict(
    generated=cfg['date'], sources=cfg.get('sources'), grid=[GW, GH], font=font,
    civs=[[glyph(c), label(c)] for c in civs],
    repos=[dict(name=r['name'], url=r['url'],
                paths=[[r['d']['paths'][i]['p'], *r['at'][i]] for i in range(r['n'])],
                spare=r['spare'],
                commits=[[c['h'], c['d'], c['s'], ci[r['d']['civs'][c['civ']]], c['f']] for c in r['d']['commits']],
                turns=[[t['c'], t['add'], t['rm'], t['own'], t['moves']] for t in r['d']['turns']]) for r in repos],
    empty=empty)
json.dump(data, open(out, 'w'), separators=(',', ':'), ensure_ascii=False)
print(out, f"{sum(r['n'] for r in repos)} paths in {len(repos)} islands, {len(empty)} shoal(s), "
      f"{sum(len(r['d']['commits']) for r in repos)} commits")
