/* chart.js — line chart minimale su <canvas>, con assi, griglia e tooltip.
 * window.FMSChart.draw(canvas, series, opts)
 *   series = [{ name, color, t:[ms...], v:[num...] }, ...]   (t crescente)
 *   opts   = { t0 }  // timestamp di riferimento per l'asse X relativo (secondi)
 * Ritorna un oggetto con dispose() per rimuovere gli handler.
 */
(function () {
  'use strict';

  const PAD = { l: 64, r: 16, t: 16, b: 34 };

  function niceTicks(min, max, n) {
    if (min === max) { min -= 1; max += 1; }
    const span = max - min;
    const step0 = span / n;
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const norm = step0 / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const start = Math.ceil(min / step) * step;
    const ticks = [];
    for (let v = start; v <= max + step * 1e-6; v += step) ticks.push(v);
    return ticks;
  }

  function fmt(v) {
    if (v === 0) return '0';
    const a = Math.abs(v);
    if (a >= 1000 || a < 0.01) return v.toExponential(1);
    return (Math.round(v * 1000) / 1000).toString();
  }

  function draw(canvas, series, opts) {
    opts = opts || {};
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const plotW = W - PAD.l - PAD.r, plotH = H - PAD.t - PAD.b;
    series = series.filter(s => s.t && s.t.length);
    if (!series.length) {
      ctx.fillStyle = '#888'; ctx.font = '13px system-ui';
      ctx.fillText('Nessun campione', PAD.l, PAD.t + 20);
      return { dispose() {} };
    }

    let tMin = Infinity, tMax = -Infinity, vMin = Infinity, vMax = -Infinity;
    for (const s of series) {
      for (let i = 0; i < s.t.length; i++) {
        if (s.t[i] < tMin) tMin = s.t[i];
        if (s.t[i] > tMax) tMax = s.t[i];
      }
      for (let i = 0; i < s.v.length; i++) {
        const v = s.v[i];
        if (v < vMin) vMin = v;
        if (v > vMax) vMax = v;
      }
    }
    const t0 = opts.t0 != null ? opts.t0 : tMin;
    if (vMin === vMax) { vMin -= 1; vMax += 1; }
    const padV = (vMax - vMin) * 0.06;
    vMin -= padV; vMax += padV;

    const X = t => PAD.l + (tMax === tMin ? 0 : (t - tMin) / (tMax - tMin) * plotW);
    const Y = v => PAD.t + plotH - (v - vMin) / (vMax - vMin) * plotH;

    // griglia + assi Y
    ctx.strokeStyle = '#e6e9ef'; ctx.fillStyle = '#5b6472';
    ctx.font = '11px system-ui'; ctx.lineWidth = 1;
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const v of niceTicks(vMin, vMax, 5)) {
      const y = Y(v);
      ctx.beginPath(); ctx.moveTo(PAD.l, y); ctx.lineTo(W - PAD.r, y); ctx.stroke();
      ctx.fillText(fmt(v), PAD.l - 8, y);
    }
    // assi X (secondi relativi a t0)
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const secMin = (tMin - t0) / 1000, secMax = (tMax - t0) / 1000;
    for (const sx of niceTicks(secMin, secMax, 6)) {
      const t = t0 + sx * 1000; if (t < tMin || t > tMax) continue;
      const x = X(t);
      ctx.strokeStyle = '#f0f2f6';
      ctx.beginPath(); ctx.moveTo(x, PAD.t); ctx.lineTo(x, PAD.t + plotH); ctx.stroke();
      ctx.fillStyle = '#5b6472'; ctx.fillText(sx.toFixed(0) + 's', x, PAD.t + plotH + 6);
    }

    // linee (con decimazione per performance)
    for (const s of series) {
      const N = s.t.length;
      const stepDraw = Math.max(1, Math.floor(N / (plotW * 2)));
      ctx.strokeStyle = s.color; ctx.lineWidth = 1.4; ctx.beginPath();
      let started = false;
      for (let i = 0; i < N; i += stepDraw) {
        const x = X(s.t[i]), y = Y(s.v[i]);
        if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // cornice
    ctx.strokeStyle = '#cfd5df'; ctx.lineWidth = 1;
    ctx.strokeRect(PAD.l, PAD.t, plotW, plotH);

    // tooltip
    const tip = document.createElement('div');
    tip.className = 'chart-tip'; tip.style.display = 'none';
    canvas.parentElement.appendChild(tip);
    function onMove(e) {
      const r = canvas.getBoundingClientRect();
      const mx = e.clientX - r.left;
      if (mx < PAD.l || mx > W - PAD.r) { tip.style.display = 'none'; return; }
      const t = tMin + (mx - PAD.l) / plotW * (tMax - tMin);
      let html = '<b>' + ((t - t0) / 1000).toFixed(2) + ' s</b>';
      for (const s of series) {
        // nearest sample
        let lo = 0, hi = s.t.length - 1;
        while (lo < hi) { const m = (lo + hi) >> 1; if (s.t[m] < t) lo = m + 1; else hi = m; }
        const v = s.v[lo];
        html += '<br><span style="color:' + s.color + '">●</span> ' +
                s.name + ': <b>' + fmt(v) + '</b>';
      }
      tip.innerHTML = html;
      tip.style.display = 'block';
      tip.style.left = Math.min(mx + 12, W - 160) + 'px';
      tip.style.top = (PAD.t + 6) + 'px';
    }
    function onLeave() { tip.style.display = 'none'; }
    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mouseleave', onLeave);
    return {
      dispose() {
        canvas.removeEventListener('mousemove', onMove);
        canvas.removeEventListener('mouseleave', onLeave);
        tip.remove();
      }
    };
  }

  window.FMSChart = { draw };
})();
