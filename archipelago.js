/* Archipelago: each public repository is an island; each file that ever existed on its main line is a column.
   Height = commits that changed the file (powers of two). Glyph = the model that last changed it.
   Data: data/archipelago.json, built from git and checked turn by turn against `git log -1 -- <file>`.
   Drawing is pixel-exact: sprites are stamped at whole-pixel positions on a 1x canvas, then scaled by whole
   device pixels. */
(function () {
  'use strict';
  var root = document.getElementById('archipelago');
  if (!root) return;
  var view = root.querySelector('.map-view'), canvas = view.querySelector('canvas'), vctx = canvas.getContext('2d');
  var slider = document.getElementById('map-time'), when = document.getElementById('map-when');
  var cellOut = document.getElementById('map-cell'), legend = document.getElementById('map-glyphs');
  var playLabel = root.querySelector('[data-act="play"] .label');

  fetch(root.getAttribute('data-src')).then(function (r) { return r.json(); }).then(init).catch(function () {
    when.textContent = 'The map data did not load.';
  });

  function init(D) {
    var VH = 4, PAD = 24, TOPPAD = 40, ZMAX = 13, stamp = document.getElementById('map-generated');
    if (stamp) stamp.textContent = D.generated;
    var BAND = [['#FFFF55', '#000000'], ['#55FF55', '#000000'], ['#00AA00', '#000000'], ['#AA5500', '#FFFFFF'],
                ['#555555', '#FFFFFF'], ['#AAAAAA', '#000000'], ['#FFFFFF', '#000000']];
    var band = function (n) { return n === 0 ? 0 : Math.min(6, 32 - Math.clz32(n)); };
    var height = function (b) { return 1 + 2 * b; };

    // --- 16x8 iso tile geometry and pixel sprites -----------------------------------------------
    var HW = [2, 4, 6, 8, 8, 6, 4, 2], YTOP = [], YBOT = [];
    for (var x = 0; x < 16; x++) {
      var t = -1, b = -1;
      for (var r = 0; r < 8; r++) if (x >= 8 - HW[r] && x < 8 + HW[r]) { if (t < 0) t = r; b = r; }
      YTOP[x] = t; YBOT[x] = b;
    }
    var rgba = function (hex) { var n = parseInt(hex.slice(1), 16); return (0xFF000000 | (n & 255) << 16 | (n >> 8 & 255) << 8 | n >> 16) >>> 0; };
    var shade = function (hex, k) {
      return '#' + [1, 3, 5].map(function (i) { return ('0' + Math.round(parseInt(hex.substr(i, 2), 16) * k).toString(16)).slice(-2); }).join('');
    };
    function sprite(w, h, paint) {
      var c = document.createElement('canvas'); c.width = w; c.height = h;
      var g = c.getContext('2d'), im = g.createImageData(w, h), px = new Uint32Array(im.data.buffer);
      paint(function (x, y, col) { px[y * w + x] = col; });
      g.putImageData(im, 0, 0);
      return c;
    }
    function cube(top) {
      var T = rgba(top), L = rgba(shade(top, .55)), R = rgba(shade(top, .78)), LS = rgba(shade(top, .44)), RS = rgba(shade(top, .66));
      return sprite(16, 8 + VH, function (set) {
        for (var x = 0; x < 16; x++) {
          for (var y = YTOP[x]; y <= YBOT[x]; y++) set(x, y, T);
          for (y = YBOT[x] + 1; y <= YBOT[x] + VH; y++) set(x, y, y === YBOT[x] + VH ? (x < 8 ? LS : RS) : (x < 8 ? L : R));
        }
      });
    }
    function flat(col) {
      var C = rgba(col);
      return sprite(16, 8, function (set) { for (var x = 0; x < 16; x++) for (var y = YTOP[x]; y <= YBOT[x]; y++) set(x, y, C); });
    }
    // TempleOS 8x8 system font (from FreeDOS, public domain), CP437 order: low byte = top row, bit 0 = left pixel
    var GLY = D.font.map(function (s) {
      var lo = parseInt(s.slice(8), 16), hi = parseInt(s.slice(0, 8), 16), rows = [];
      for (var i = 0; i < 4; i++) rows.push(lo >>> 8 * i & 255);
      for (i = 0; i < 4; i++) rows.push(hi >>> 8 * i & 255);
      return rows;
    });
    var CP = { 'Ö': 153, '≈': 247, '·': 250 }, gcache = {};
    function code(ch) { return CP[ch] || (ch.charCodeAt(0) < 128 ? ch.charCodeAt(0) : 63); }
    function glyph(ch, col) {
      var k = ch + col;
      return gcache[k] || (gcache[k] = sprite(8, 8, function (set) {
        var g = GLY[code(ch)], C = rgba(col);
        for (var r = 0; r < 8; r++) for (var i = 0; i < 8; i++) if (g[r] >> i & 1) set(i, r, C);
      }));
    }
    var CUBE = BAND.map(function (b) { return cube(b[0]); }), CUBE_SEL = cube('#FF55FF');
    var DEEP = flat('#0000AA'), SHALLOW = flat('#00AAAA');

    // --- history: per repo, a snapshot per turn; one shared date axis --------------------------
    var repos = D.repos.map(function (r) {
      var N = r.paths.length, own = new Int16Array(N).fill(-1), ex = new Uint8Array(N), elev = new Uint16Array(N);
      var snaps = [], cum = [], made = 0, last = '';
      r.turns.forEach(function (t) {
        t[1].forEach(function (p) { ex[p] = 1; });
        t[2].forEach(function (p) { ex[p] = 0; });
        t[3].forEach(function (po) { own[po[0]] = po[1]; });
        t[4].forEach(function (m) { r.commits[m][4].forEach(function (p) { elev[p]++; }); });
        made += t[4].length;
        last = r.commits[t[0]][1] > last ? r.commits[t[0]][1] : last;
        snaps.push({ own: own.slice(), ex: ex.slice(), elev: elev.slice(), commits: made, files: ex.reduce(function (a, v) { return a + v; }, 0) });
        cum.push(last);
      });
      return { name: r.name, url: r.url, paths: r.paths, spare: r.spare, commits: r.commits, snaps: snaps, cum: cum };
    });
    var dates = Array.from(new Set([].concat.apply([], repos.map(function (r) { return r.cum; })))).sort();
    var at = repos.map(function (r) {
      var i = -1;
      return dates.map(function (d) { while (i + 1 < r.cum.length && r.cum[i + 1] <= d) i++; return i; });
    });

    // --- geography -------------------------------------------------------------------------------
    var LAND = new Map(), SHOAL = new Map(), key = function (x, y) { return x * 4096 + y; };
    repos.forEach(function (r, ri) {
      r.cells = [];
      r.paths.forEach(function (p, pi) { LAND.set(key(p[1], p[2]), { r: ri, p: pi }); r.cells.push([p[1], p[2]]); });
      r.spare.forEach(function (c) { LAND.set(key(c[0], c[1]), { r: ri, p: -1 }); r.cells.push(c); });
    });
    D.empty.forEach(function (e) {
      for (var dx = -1; dx <= 1; dx++) for (var dy = 0; dy <= 1; dy++) SHOAL.set(key(e.x + dx, e.y + dy), e);
    });
    var all = [];
    LAND.forEach(function (v, k) { all.push([Math.floor(k / 4096), k % 4096]); });
    SHOAL.forEach(function (v, k) { all.push([Math.floor(k / 4096), k % 4096]); });
    var BX0 = Math.min.apply(null, all.map(function (c) { return c[0]; })) - 3, BX1 = Math.max.apply(null, all.map(function (c) { return c[0]; })) + 3;
    var BY0 = Math.min.apply(null, all.map(function (c) { return c[1]; })) - 3, BY1 = Math.max.apply(null, all.map(function (c) { return c[1]; })) + 3;
    var BW = BX1 - BX0 + 1, BH = BY1 - BY0 + 1;
    var NEAR = new Set();
    LAND.forEach(function (v, k) {
      var x = Math.floor(k / 4096), y = k % 4096;
      for (var dx = -1; dx <= 1; dx++) for (var dy = -1; dy <= 1; dy++) NEAR.add(key(x + dx, y + dy));
    });
    var OW = (BW + BH) * 8 + 2 * PAD, OH = (BW + BH) * 4 + ZMAX * VH + TOPPAD + PAD;
    var off = document.createElement('canvas'); off.width = OW; off.height = OH;
    var g = off.getContext('2d');

    var rot = 0, orders = [];
    function rotate(x, y, r) {
      var u = x - BX0, v = y - BY0;
      return r === 0 ? [u, v] : r === 1 ? [BH - 1 - v, u] : r === 2 ? [BW - 1 - u, BH - 1 - v] : [v, BW - 1 - u];
    }
    function order(r) {
      if (orders[r]) return orders[r];
      var cells = [], RH = r % 2 ? BW : BH;
      for (var x = BX0; x <= BX1; x++) for (var y = BY0; y <= BY1; y++) {
        var XY = rotate(x, y, r);
        cells.push({ x: x, y: y, k: key(x, y), sx: PAD + RH * 8 + (XY[0] - XY[1]) * 8 - 8, base: TOPPAD + ZMAX * VH + (XY[0] + XY[1]) * 4, s: XY[0] + XY[1], X: XY[0] });
      }
      cells.sort(function (a, b) { return a.s - b.s || a.X - b.X; });
      return (orders[r] = cells);
    }

    // --- state -------------------------------------------------------------------------------------
    var k = dates.length - 1, sel = null, hover = null, zoom = 1, panX = 0, panY = 0, timer = null;
    slider.min = 0; slider.max = dates.length - 1; slider.value = k;

    function columnHeight(L) {
      var t = at[L.r][k];
      if (t < 0) return 0;
      if (L.p < 0) return 1;
      var s = repos[L.r].snaps[t];
      return s.ex[L.p] ? height(band(s.elev[L.p])) : 1;
    }

    function text(x, y, s, col, bg) {
      if (bg) { g.fillStyle = bg; g.fillRect(x - 2, y - 2, 8 * s.length + 4, 12); }
      for (var i = 0; i < s.length; i++) g.drawImage(glyph(s[i], col), x + 8 * i, y);
    }

    var bounds;  // pixels covered by islands, shoals and name plaques in the last frame; the default view fits these
    function cover(x0, y0, x1, y1) {
      bounds[0] = Math.min(bounds[0], x0); bounds[1] = Math.min(bounds[1], y0);
      bounds[2] = Math.max(bounds[2], x1); bounds[3] = Math.max(bounds[3], y1);
    }
    function render() {
      g.clearRect(0, 0, OW, OH);
      bounds = [OW, OH, 0, 0];
      var cells = order(rot);
      for (var i = 0; i < cells.length; i++) {
        var c = cells[i], L = LAND.get(c.k);
        if (L || SHOAL.has(c.k)) cover(c.sx, c.base - (L ? columnHeight(L) : 0) * VH, c.sx + 16, c.base + 8);
        if (!L) {
          if (SHOAL.has(c.k)) { g.drawImage(SHALLOW, c.sx, c.base); g.drawImage(glyph('≈', '#55FFFF'), c.sx + 4, c.base); continue; }
          var near = NEAR.has(c.k);
          g.drawImage(near ? SHALLOW : DEEP, c.sx, c.base);
          if (((c.x * 73856093 ^ c.y * 19349663) >>> 0) % 11 === 0) g.drawImage(glyph('~', near ? '#55FFFF' : '#5555FF'), c.sx + 4, c.base);
          continue;
        }
        var t = at[L.r][k];
        if (t < 0) { g.drawImage(SHALLOW, c.sx, c.base); continue; }  // not founded yet: a reef
        var s = repos[L.r].snaps[t], h = 1, spr = CUBE[0], top = null;
        if (L.p >= 0 && s.ex[L.p]) {
          var b = band(s.elev[L.p]), on = sel && sel.r === L.r && sel.p === L.p;
          h = height(b); spr = on ? CUBE_SEL : CUBE[b];
          top = glyph(D.civs[repos[L.r].commits[s.own[L.p]][3]][0], on ? '#000000' : BAND[b][1]);
        }
        for (var z = 0; z < h; z++) g.drawImage(spr, c.sx, c.base - (z + 1) * VH);
        if (top) g.drawImage(top, c.sx + 4, c.base - h * VH);
      }
      plaques(cells);
      blit();
      readTime();
    }

    function plaques(cells) {
      var boxes = [], pos = new Map();
      cells.forEach(function (c) { pos.set(c.k, c); });
      var items = repos.map(function (r, ri) { return { name: r.name, cells: r.cells, ri: ri }; })
        .concat(D.empty.map(function (e) { return { name: e.name + ' (empty)', cells: [[e.x, e.y]], ri: -1 }; }))
        .sort(function (a, b) { return b.cells.length - a.cells.length; });
      items.forEach(function (it) {
        var sx = 0, base = 0, top = 0;
        it.cells.forEach(function (xy) {
          var c = pos.get(key(xy[0], xy[1])); sx += c.sx + 8; base += c.base;
          if (it.ri >= 0) top = Math.max(top, columnHeight(LAND.get(c.k)));
        });
        sx = Math.round(sx / it.cells.length); base = Math.round(base / it.cells.length);
        var ay = base - top * VH, w = 8 * it.name.length, x0 = sx - (w >> 1), y0 = ay - 26;
        var hit = function (b) { return !(x0 + w + 4 < b[0] || b[2] < x0 - 4 || y0 + 12 < b[1] || b[3] < y0 - 2); };
        while (boxes.some(hit)) y0 -= 12;
        boxes.push([x0, y0, x0 + w, y0 + 10]);
        cover(x0 - 2, y0 - 2, x0 + w + 2, y0 + 10);
        var born = it.ri >= 0 && at[it.ri][k] >= 0;
        g.fillStyle = '#AAAAAA'; g.fillRect(sx, y0 + 10, 1, Math.max(0, ay - y0 - 10));
        text(x0, y0, it.name, born ? '#FFFFFF' : '#AAAAAA', '#000000');
      });
    }

    function blit() {
      vctx.imageSmoothingEnabled = false;
      vctx.fillStyle = '#000000'; vctx.fillRect(0, 0, canvas.width, canvas.height);
      vctx.drawImage(off, panX, panY, OW * zoom, OH * zoom);
    }

    function fit(keepView) {
      var dpr = window.devicePixelRatio || 1, w = view.clientWidth, h = view.clientHeight;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      if (!keepView) {
        var bw = bounds[2] - bounds[0] + 16, bh = bounds[3] - bounds[1] + 16;
        zoom = Math.max(1, Math.floor(Math.min(canvas.width / bw, canvas.height / bh)));
        panX = Math.round(canvas.width / 2 - (bounds[0] + bounds[2]) / 2 * zoom);
        panY = Math.round(canvas.height / 2 - (bounds[1] + bounds[3]) / 2 * zoom);
      }
      blit();
    }

    // --- readouts ----------------------------------------------------------------------------------
    function count(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
    function readTime() {
      var born = 0, files = 0, commits = 0;
      repos.forEach(function (r, ri) { var t = at[ri][k]; if (t >= 0) { born++; files += r.snaps[t].files; commits += r.snaps[t].commits; } });
      slider.value = k;
      when.innerHTML = '<b>' + dates[k] + '</b> · ' + born + ' of ' + repos.length + ' repos founded · ' + count(files, 'file') + ' · ' + count(commits, 'commit');
    }
    function esc(s) { return String(s).replace(/[&<>"]/g, function (ch) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]; }); }
    function readCell() {
      var L = hover || sel;
      if (!L) { cellOut.textContent = 'Hover a column to read its file. Click to mark it.'; return; }
      var r = repos[L.r], t = at[L.r][k], link = ' · <a href="' + esc(r.url) + '">' + esc(r.url.replace('https://', '')) + '</a>';
      if (t < 0) { cellOut.innerHTML = '<b>' + esc(r.name) + '</b> · not founded yet' + link; return; }
      var s = r.snaps[t];
      if (L.p < 0) { cellOut.innerHTML = '<b>' + esc(r.name) + '</b> · ' + count(s.files, 'file') + ' · ' + count(s.commits, 'commit') + link; return; }
      var path = r.paths[L.p][0];
      if (!s.ex[L.p]) { cellOut.innerHTML = '<b>' + esc(r.name + '/' + path) + '</b> · not in the repo on this date' + link; return; }
      var c = r.commits[s.own[L.p]], n = s.elev[L.p];
      cellOut.innerHTML = '<b>' + esc(r.name + '/' + path) + '</b> · ' + esc(D.civs[c[3]][0] + ' ' + D.civs[c[3]][1]) + ' · ' +
        count(n, 'commit') + ' · last ' + esc(c[0]) + ' ' + esc(c[2]);
    }
    legend.innerHTML = D.civs.map(function (c) { return '<li><b class="g">' + esc(c[0]) + '</b>' + esc(c[1]) + '</li>'; }).join('');

    // --- input -------------------------------------------------------------------------------------
    function pick(e) {
      var rc = canvas.getBoundingClientRect(), dpr = canvas.width / rc.width;
      var ox = Math.floor(((e.clientX - rc.left) * dpr - panX) / zoom), oy = Math.floor(((e.clientY - rc.top) * dpr - panY) / zoom);
      var cells = order(rot);
      for (var i = cells.length - 1; i >= 0; i--) {
        var c = cells[i], L = LAND.get(c.k);
        if (!L) continue;
        var lx = ox - c.sx;
        if (lx < 0 || lx > 15) continue;
        if (oy >= c.base - columnHeight(L) * VH + YTOP[lx] && oy <= c.base + YBOT[lx]) return L;
      }
      return null;
    }
    function go(n) { k = Math.max(0, Math.min(dates.length - 1, n)); render(); readCell(); }
    function stop() { clearInterval(timer); timer = null; if (playLabel) playLabel.textContent = 'Replay'; cellOut.setAttribute('aria-live', 'polite'); }
    function play() {
      if (timer) { stop(); return; }
      if (k === dates.length - 1) k = -1;
      if (playLabel) playLabel.textContent = 'Pause';
      cellOut.setAttribute('aria-live', 'off');
      timer = setInterval(function () { if (k >= dates.length - 1) stop(); else go(k + 1); }, 180);
    }
    function zoomBy(d) {
      var nz = Math.max(1, Math.min(8, zoom + d)), cx = canvas.width / 2, cy = canvas.height / 2;
      panX = Math.round(cx - (cx - panX) * nz / zoom); panY = Math.round(cy - (cy - panY) * nz / zoom); zoom = nz; blit();
    }
    var ACT = {
      prev: function () { stop(); go(k - 1); }, next: function () { stop(); go(k + 1); }, play: play,
      left: function () { rot = (rot + 3) % 4; render(); fit(false); }, right: function () { rot = (rot + 1) % 4; render(); fit(false); },
      in: function () { zoomBy(1); }, out: function () { zoomBy(-1); }, fit: function () { fit(false); }
    };
    root.querySelectorAll('[data-act]').forEach(function (b) { b.addEventListener('click', function () { ACT[b.getAttribute('data-act')](); }); });
    slider.addEventListener('input', function () { stop(); go(+slider.value); });
    view.addEventListener('keydown', function (e) {
      var m = { ArrowLeft: 'prev', ArrowRight: 'next', ' ': 'play', q: 'left', Q: 'left', e: 'right', E: 'right', '+': 'in', '=': 'in', '-': 'out', '0': 'fit' }[e.key];
      if (m && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); ACT[m](); }
    });
    var drag = null;
    view.addEventListener('pointerdown', function (e) { drag = { x: e.clientX, y: e.clientY, px: panX, py: panY, moved: false }; view.setPointerCapture(e.pointerId); });
    view.addEventListener('pointermove', function (e) {
      if (drag) {
        var dpr = canvas.width / canvas.getBoundingClientRect().width, dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) { drag.moved = true; view.classList.add('dragging'); }
        if (drag.moved) { panX = Math.round(drag.px + dx * dpr); panY = Math.round(drag.py + dy * dpr); blit(); }
        return;
      }
      var L = pick(e);
      if ((L && hover && L.r === hover.r && L.p === hover.p) || L === hover) return;
      hover = L; readCell();
    });
    view.addEventListener('pointerup', function (e) {
      if (drag && !drag.moved) {
        var L = pick(e);
        sel = L && L.p >= 0 ? L : null; hover = L; render(); readCell();
      }
      drag = null; view.classList.remove('dragging');
    });
    view.addEventListener('pointerleave', function () { if (!drag && hover) { hover = null; readCell(); } });
    if (window.ResizeObserver) new ResizeObserver(function () { fit(false); }).observe(view);
    render(); fit(false); readCell();
  }
})();
