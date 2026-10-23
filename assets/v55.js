(function(){
  var cs = document.currentScript, root = cs && cs.closest ? cs.closest('.v55') : null;
  if (!root) { var all = document.querySelectorAll('.v55:not(.js)'); root = all.length ? all[all.length - 1] : null; }
  if (!root || root.classList.contains('js')) return;
  root.classList.add('js');
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function countUp(el){
    if (el.dataset.done) return; el.dataset.done = 1;
    var to = parseFloat(el.dataset.count), dec = +el.dataset.dec || 0, suf = el.dataset.suffix || '', t0 = null, dur = 1300, fin = el.textContent;
    if (reduce || isNaN(to)) return;
    function step(ts){ t0 = t0 || ts; var k = Math.min((ts - t0) / dur, 1), e = 1 - Math.pow(1 - k, 4);
      el.textContent = k >= 1 ? fin : (to * e).toFixed(dec) + (suf === '%+' ? '%' : suf); if (k < 1) requestAnimationFrame(step); }
    requestAnimationFrame(step);
  }
  function ringIn(c){ var to = parseFloat(c.style.getPropertyValue('--to')) || 0, t0 = null; c.classList.add('go');
    if (reduce) return; c.style.setProperty('--deg', '0deg');
    function st(ts){ t0 = t0 || ts; var k = Math.min((ts - t0) / 1500, 1), e = 1 - Math.pow(1 - k, 4); c.style.setProperty('--deg', (to * e).toFixed(1) + 'deg'); if (k < 1) requestAnimationFrame(st); }
    requestAnimationFrame(st); }
  function show(el){ if (el.matches('[data-count]')) countUp(el); else if (el.matches('div.rg')) ringIn(el); else el.classList.add('seen'); }
  var els = root.querySelectorAll('[data-count], div.rg, .sec');
  var io = (!reduce && 'IntersectionObserver' in window) ? new IntersectionObserver(function(es){ es.forEach(function(e){ if (e.isIntersecting) { show(e.target); io.unobserve(e.target); } }); }, {threshold: .15}) : null;
  els.forEach(function(el){ if (el.matches('.sec') && io) el.classList.add('rv-in'); if (io) io.observe(el); else show(el); });
  // safety net: never leave a section hidden (print, full-page capture, observers that never fire)
  setTimeout(function(){ els.forEach(function(el){ if (io) io.unobserve(el); show(el); }); }, 1500);
  // countdown from the game's real start time (server already rendered the current value)
  function tick(){
    if (!root.isConnected) { clearInterval(timer); return; }
    root.querySelectorAll('[data-start]').forEach(function(w){
      var t = Date.parse(w.dataset.start), b = w.querySelector('.cd'); if (isNaN(t) || !b) return;
      var m = Math.floor((t - Date.now()) / 60000);
      b.textContent = m >= 60 ? Math.floor(m / 60) + 'h ' + ('0' + (m % 60)).slice(-2) + 'm' : Math.max(m, 0) + 'm';
    });
  }
  var timer = setInterval(tick, 30000);
  // V5.9: top-threat badges -> open the Live Next Goal tab (native st.tabs button) and scroll to that player's row.
  root.addEventListener('click', function(ev){
    var a = ev.target && ev.target.closest ? ev.target.closest('a[data-ng]') : null; if (!a) return;
    var want = a.dataset.ng, tabTxt = a.dataset.tab || 'Live Next Goal', tab = null;
    document.querySelectorAll('[data-testid=stTabs] [role=tab]').forEach(function(b){ if (!tab && b.textContent.indexOf(tabTxt) !== -1) tab = b; });
    if (!tab) return;   // no tab bar: leave the plain #hash link alone
    ev.preventDefault(); tab.click();
    var tries = 0;
    (function seek(){
      var hit = null;
      document.querySelectorAll('[data-ng="' + want + '"]').forEach(function(el){ if (!hit && el.getClientRects().length && !el.closest('a')) hit = el; });
      if (hit) { hit.scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'center'}); hit.classList.add('ng-hit');
        setTimeout(function(){ hit.classList.remove('ng-hit'); }, 2600); return; }
      if (++tries !== 25) setTimeout(seek, 120); else tab.scrollIntoView({block: 'start'});
    })();
  });
})();
