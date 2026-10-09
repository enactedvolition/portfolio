/* Fills [data-suno-count] from data/suno.json, written daily by
   .github/workflows/suno-count.yml. Suno's API sends no CORS headers, so the
   browser can't ask Suno directly. If the file is missing or bad, the
   element keeps its fallback text. */
(function () {
  var els = document.querySelectorAll('[data-suno-count]');
  if (!els.length || !window.fetch) return;
  fetch(document.currentScript.getAttribute('data-src'), { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw 0; return r.json(); })
    .then(function (d) {
      if (typeof d.tracks !== 'number' || d.tracks <= 0) return;
      var day = (d.fetched_at || '').slice(0, 10);
      els.forEach(function (el) {
        el.textContent = d.tracks + ' tracks on Suno';
        if (day) el.title = 'Public count from suno.com/@' + d.handle + ', checked ' + day;
      });
    })
    .catch(function () {});
})();
