/* app.js — orchestrazione dashboard FMS-Rampini. */
(function () {
  'use strict';

  const DEC = window.FMSDecoder;
  const PALETTE = ['#2563eb', '#dc2626', '#059669', '#d97706', '#7c3aed', '#0891b2', '#db2777', '#65a30d'];

  // stato globale
  const state = {
    files: [],            // {name, frames}
    tMin: Infinity, tMax: -Infinity,
    totalFrames: 0,
    msgStats: new Map(),  // msgName -> {pgn, comment, count, firstTs, lastTs, sources:Set}
    signals: new Map(),   // key "MSG.SIG" -> {msg,sig,unit,desc,count,na,min,max,sum,first,last,t:[],v:[]}
    derived: new Map(),
  };

  const $ = sel => document.querySelector(sel);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

  /* ---------- ingest ---------- */
  function ingest(name, text) {
    const frames = DEC.parseCsv(text);
    state.files.push({ name, count: frames.length });
    for (const f of frames) {
      state.totalFrames++;
      if (f.ts < state.tMin) state.tMin = f.ts;
      if (f.ts > state.tMax) state.tMax = f.ts;
      const dec = DEC.decodeFrame(f);
      if (!dec) continue;
      const mn = dec.msg.name;
      let ms = state.msgStats.get(mn);
      if (!ms) { ms = { pgn: dec.msg.pgn, comment: dec.msg.comment, count: 0, firstTs: f.ts, lastTs: f.ts, sources: new Set() }; state.msgStats.set(mn, ms); }
      ms.count++; ms.lastTs = f.ts; ms.sources.add(f.source);
      for (const s of dec.signals) {
        const key = mn + '.' + s.sig;
        let sig = state.signals.get(key);
        if (!sig) { sig = { msg: mn, sig: s.sig, unit: s.unit, desc: s.desc, label: s.label, pgn: dec.msg.pgn,
          count: 0, na: 0, min: Infinity, max: -Infinity, sum: 0, first: null, last: null, lastLabel: null, t: [], v: [] }; state.signals.set(key, sig); }
        if (s.na) { sig.na++; continue; }
        sig.count++;
        if (s.phys < sig.min) sig.min = s.phys;
        if (s.phys > sig.max) sig.max = s.phys;
        sig.sum += s.phys;
        if (sig.first === null) sig.first = s.phys;
        sig.last = s.phys; sig.lastLabel = s.label;
        sig.t.push(f.ts); sig.v.push(s.phys);
      }
    }
  }

  /* ---------- segnali derivati ---------- */
  function buildDerived() {
    // Potenza istantanea P = Vpack * IPack / 1000  (kW) da BMS_STAT1 (~4 Hz)
    const vp = state.signals.get('BMS_STAT1.Vpack');
    const ip = state.signals.get('BMS_STAT1.IPack');
    if (vp && ip && vp.t.length && ip.t.length) {
      // i due segnali arrivano dallo stesso messaggio -> stessi timestamp
      const n = Math.min(vp.t.length, ip.t.length);
      const sig = { msg: 'DERIVATO', sig: 'PotenzaIstantanea (V×I)', unit: 'kW', desc: 'Vpack × IPack da BMS_STAT1', pgn: '-',
        count: 0, na: 0, min: Infinity, max: -Infinity, sum: 0, first: null, last: null, lastLabel: null, t: [], v: [], derived: true };
      for (let i = 0; i < n; i++) {
        const p = vp.v[i] * ip.v[i] / 1000;
        sig.t.push(vp.t[i]); sig.v.push(p); sig.count++; sig.sum += p;
        if (p < sig.min) sig.min = p; if (p > sig.max) sig.max = p;
        if (sig.first === null) sig.first = p; sig.last = p;
      }
      state.signals.set('DERIVATO.PotenzaIstantanea', sig);
    }
  }

  /* ---------- rendering ---------- */
  function durationStr() {
    if (!isFinite(state.tMin)) return '—';
    const s = (state.tMax - state.tMin) / 1000;
    const m = Math.floor(s / 60);
    return `${s.toFixed(1)} s (${m} min ${Math.round(s % 60)} s)`;
  }

  function renderSummary() {
    const decodedSigs = [...state.signals.values()].filter(s => s.count > 0).length;
    $('#summary').innerHTML = '';
    const chips = [
      liveMode ? ['Sorgente', '● LIVE'] : ['File caricati', state.files.length],
      ['Frame totali', state.totalFrames.toLocaleString('it-IT')],
      ['Durata', durationStr()],
      ['Messaggi decodificati', state.msgStats.size],
      ['Grandezze rilevate', decodedSigs],
    ];
    for (const [k, v] of chips) {
      const c = el('div', 'chip');
      c.appendChild(el('div', 'chip-val', String(v)));
      c.appendChild(el('div', 'chip-key', k));
      $('#summary').appendChild(c);
    }
    const start = isFinite(state.tMin) ? new Date(state.tMin).toLocaleString('it-IT') : '';
    $('#timespan').textContent = start ? `Registrazione: ${start}  →  ${new Date(state.tMax).toLocaleString('it-IT')}` : '';
  }

  function renderMessages() {
    const rows = [...state.msgStats.entries()].sort((a, b) => b[1].count - a[1].count);
    const dur = (state.tMax - state.tMin) / 1000 || 1;
    let html = `<table class="tbl"><thead><tr><th>Messaggio</th><th>PGN</th><th>Descrizione</th>
      <th class="num">Frame</th><th class="num">Freq (Hz)</th><th>Source</th></tr></thead><tbody>`;
    for (const [name, m] of rows) {
      html += `<tr><td class="mono">${name}</td><td class="mono">${m.pgn} <span class="dim">0x${m.pgn.toString(16).toUpperCase()}</span></td>
        <td class="dim">${m.comment || ''}</td><td class="num">${m.count.toLocaleString('it-IT')}</td>
        <td class="num">${(m.count / dur).toFixed(2)}</td><td class="mono dim">${[...m.sources].join(', ')}</td></tr>`;
    }
    // messaggi del DBC mai visti
    const seen = new Set(state.msgStats.keys());
    const missing = window.FMS_DB.messages.filter(m => !seen.has(m.name));
    html += `</tbody></table>`;
    if (missing.length) {
      html += `<p class="note">Messaggi definiti nel DBC ma <b>non rilevati</b> in questi dump (${missing.length}): `
        + `<span class="dim mono">${missing.map(m => m.name).join(', ')}</span></p>`;
    }
    $('#tab-messages').innerHTML = html;
  }

  function fmtNum(v) {
    if (v == null || !isFinite(v)) return '—';
    const a = Math.abs(v);
    if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(2);
    return (Math.round(v * 1000) / 1000).toLocaleString('it-IT');
  }

  function renderSignals(filter) {
    filter = (filter || '').toLowerCase();
    const list = [...state.signals.values()]
      .filter(s => s.count > 0 || s.na > 0)
      .filter(s => !filter || (s.msg + '.' + s.sig + ' ' + (s.desc || '') + ' ' + s.unit).toLowerCase().includes(filter))
      .sort((a, b) => a.msg === b.msg ? a.sig.localeCompare(b.sig) : a.msg.localeCompare(b.msg));

    let html = `<table class="tbl"><thead><tr><th>Messaggio</th><th>Grandezza</th><th>Unità</th>
      <th class="num">Ultimo</th><th class="num">Min</th><th class="num">Media</th><th class="num">Max</th>
      <th class="num">Campioni</th><th></th></tr></thead><tbody>`;
    for (const s of list) {
      const mean = s.count ? s.sum / s.count : null;
      const last = s.lastLabel ? `${fmtNum(s.last)} <span class="dim">(${s.lastLabel})</span>` : fmtNum(s.last);
      const naTag = s.na ? ` <span class="na" title="campioni N/A">N/A×${s.na}</span>` : '';
      const key = s.msg + '.' + s.sig;
      html += `<tr data-key="${key}"><td class="mono ${s.derived ? 'der' : ''}">${s.msg}</td>
        <td class="mono" title="${s.desc || ''}">${s.sig}${naTag}</td><td class="dim">${s.unit || ''}</td>
        <td class="num">${s.count ? last : '—'}</td><td class="num">${fmtNum(s.min)}</td>
        <td class="num">${fmtNum(mean)}</td><td class="num">${fmtNum(s.max)}</td>
        <td class="num">${s.count.toLocaleString('it-IT')}</td>
        <td class="num"><button class="mini" data-plot="${key}">grafico</button></td></tr>`;
    }
    html += `</tbody></table>`;
    $('#signals-host').innerHTML = html;
    $('#signals-host').querySelectorAll('[data-plot]').forEach(b =>
      b.addEventListener('click', () => openChart([b.getAttribute('data-plot')])));
  }

  /* ---------- selettore grafico multi-segnale ---------- */
  function renderPlotPicker() {
    const sel = $('#plot-select');
    sel.innerHTML = '';
    const list = [...state.signals.values()].filter(s => s.count > 0)
      .sort((a, b) => a.msg === b.msg ? a.sig.localeCompare(b.sig) : a.msg.localeCompare(b.msg));
    for (const s of list) {
      const o = el('option'); o.value = s.msg + '.' + s.sig;
      o.textContent = `${s.msg}.${s.sig}${s.unit ? ' [' + s.unit + ']' : ''}`;
      sel.appendChild(o);
    }
  }

  let activeChart = null;
  function drawInto(canvas, keys, container) {
    if (activeChart && activeChart.dispose) activeChart.dispose();
    const series = keys.map((k, i) => {
      const s = state.signals.get(k);
      return s ? { name: k, color: PALETTE[i % PALETTE.length], t: s.t, v: s.v } : null;
    }).filter(Boolean);
    activeChart = window.FMSChart.draw(canvas, series, { t0: state.tMin });
    if (container) {
      container.innerHTML = series.map((s, i) =>
        `<span class="leg"><span style="background:${s.color}"></span>${s.name}</span>`).join('');
    }
  }

  function openChart(keys) {
    document.querySelector('[data-tab="plot"]').click();
    const sel = $('#plot-select');
    [...sel.options].forEach(o => o.selected = keys.includes(o.value));
    drawInto($('#plot-canvas'), keys, $('#plot-legend'));
  }

  /* ---------- tabs ---------- */
  function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        $('#tab-' + btn.getAttribute('data-tab')).classList.add('active');
      });
    });
  }

  /* ---------- caricamento file ---------- */
  function resetState() {
    state.files = []; state.tMin = Infinity; state.tMax = -Infinity; state.totalFrames = 0;
    state.msgStats = new Map(); state.signals = new Map();
  }

  function readFiles(fileList) {
    const files = [...fileList].filter(f => /\.csv$/i.test(f.name));
    if (!files.length) { alert('Seleziona file .csv (candump).'); return; }
    resetState();
    $('#status').textContent = 'Lettura in corso…';
    let done = 0;
    files.forEach(file => {
      const r = new FileReader();
      r.onload = () => {
        ingest(file.name, r.result);
        if (++done === files.length) finish();
      };
      r.readAsText(file);
    });
  }

  async function autoLoad() {
    // modalità server: legge l'elenco da ../data/manifest.json e carica i dump.
    resetState();
    $('#status').textContent = 'Caricamento dalla cartella data/ …';
    let names = [];
    try {
      const man = await fetch('../data/manifest.json');
      if (man.ok) names = await man.json();
    } catch (e) { /* nessun manifest */ }
    let any = false;
    for (const name of names) {
      try {
        const res = await fetch('../data/' + name);
        if (!res.ok) continue;
        ingest(name, await res.text()); any = true;
      } catch (e) { /* ignora */ }
    }
    if (!any) { $('#status').textContent = 'Auto-caricamento non riuscito: apri via web server (vedi README) o usa «Carica file CSV».'; return; }
    finish();
  }

  function finish() {
    buildDerived();
    renderSummary();
    renderMessages();
    renderSignals('');
    renderPlotPicker();
    $('#status').textContent = `Pronto — ${state.totalFrames.toLocaleString('it-IT')} frame, ${state.signals.size} grandezze.`;
    $('#app').classList.add('loaded');
    // grafico iniziale: velocità o SoC se presenti
    const pref = ['CCVS.WheelBasedSpeed', 'BMS_MSGS.SoC', 'BMS_STAT1.Vpack'];
    const k = pref.find(x => state.signals.has(x) && state.signals.get(x).count);
    if (k) { renderPlotPicker(); }
  }

  /* ---------- LIVE (WebSocket) ---------- */
  let ws = null, liveTimer = null, reconnectT = null;
  let liveMode = false;
  let liveRec = [];                       // registrazione GREZZA completa (per salvare il dump)
  let recCapped = false;
  const LIVE_WINDOW_MS = 5 * 60 * 1000;   // finestra scorrevole grafici: ultimi 5 minuti
  const REC_MAX = 3000000;                // tetto di sicurezza memoria (~3M frame)

  function setLiveDot(cls) { $('#live-dot').className = 'live-dot ' + cls; }

  function connectLive(url) {
    disconnectLive(true);
    resetState();
    liveRec = []; recCapped = false;
    liveMode = true;
    $('#app').classList.add('loaded', 'live');
    $('#btn-live').textContent = 'Disconnetti';
    setLiveDot('connecting');
    $('#status').textContent = 'Connessione live a ' + url + ' …';
    try { ws = new WebSocket(url); }
    catch (e) { $('#status').textContent = 'URL non valido: ' + e.message; setLiveDot('off'); liveMode = false; return; }

    ws.onopen = () => {
      setLiveDot('on');
      $('#status').textContent = '● LIVE — in ricezione…';
      document.querySelector('[data-tab="signals"]').click();
      if (liveTimer) clearInterval(liveTimer);
      liveTimer = setInterval(liveTick, 1000);
    };
    ws.onmessage = ev => { try { liveIngest(JSON.parse(ev.data)); } catch (e) { /* frame ignorato */ } };
    ws.onerror = () => setLiveDot('off');
    ws.onclose = () => {
      setLiveDot('off');
      if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
      if (liveMode) {
        $('#status').textContent = 'Live disconnesso — nuovo tentativo tra 3 s…';
        reconnectT = setTimeout(() => { if (liveMode) connectLive(url); }, 3000);
      }
    };
  }

  function disconnectLive(silent) {
    liveMode = false;
    if (reconnectT) { clearTimeout(reconnectT); reconnectT = null; }
    if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
    if (ws) { try { ws.onclose = null; ws.close(); } catch (e) {} ws = null; }
    setLiveDot('off');
    $('#btn-live').textContent = 'Connetti live';
    $('#app').classList.remove('live');
    if (!silent) $('#status').textContent = 'Live disconnesso.';
  }

  function liveIngest(f) {
    // f = { pgn, source, ts, d:"hex" }  -> riusa il decoder già esistente
    const ts = f.ts || Date.now();
    // registrazione grezza completa per il salvataggio del dump
    if (liveRec.length < REC_MAX) liveRec.push({ ts, id: f.id || '', pgn: f.pgn, source: f.source, d: f.d });
    else if (!recCapped) { recCapped = true; $('#status').textContent = 'Registrazione al limite di memoria: salva e riconnetti per continuare.'; }
    const bytes = DEC.hexToBytes(f.d);
    state.totalFrames++;
    if (ts < state.tMin) state.tMin = ts;
    if (ts > state.tMax) state.tMax = ts;
    const dec = DEC.decodeFrame({ pgn: f.pgn, source: f.source, ts, bytes });
    if (!dec) return;
    const mn = dec.msg.name;
    let ms = state.msgStats.get(mn);
    if (!ms) { ms = { pgn: dec.msg.pgn, comment: dec.msg.comment, count: 0, firstTs: ts, lastTs: ts, sources: new Set() }; state.msgStats.set(mn, ms); }
    ms.count++; ms.lastTs = ts; ms.sources.add(f.source);
    for (const s of dec.signals) {
      const key = mn + '.' + s.sig;
      let sig = state.signals.get(key);
      if (!sig) {
        sig = { msg: mn, sig: s.sig, unit: s.unit, desc: s.desc, label: s.label, pgn: dec.msg.pgn,
          count: 0, na: 0, min: Infinity, max: -Infinity, sum: 0, first: null, last: null, lastLabel: null, t: [], v: [] };
        state.signals.set(key, sig); state._dirtyPicker = true;
      }
      if (s.na) { sig.na++; continue; }
      sig.t.push(ts); sig.v.push(s.phys); sig.last = s.phys; sig.lastLabel = s.label;
    }
  }

  function liveTick() {
    const now = state.tMax || Date.now();
    const start = now - LIVE_WINDOW_MS;
    for (const sig of state.signals.values()) {
      if (sig.derived) continue;
      const t = sig.t;
      if (t.length && t[0] < start) {           // taglia la finestra scorrevole
        let lo = 0, hi = t.length;
        while (lo < hi) { const m = (lo + hi) >> 1; if (t[m] < start) lo = m + 1; else hi = m; }
        sig.t = t.slice(lo); sig.v = sig.v.slice(lo);
      }
      const vv = sig.v; let mn = Infinity, mx = -Infinity, sum = 0;
      for (let i = 0; i < vv.length; i++) { const x = vv[i]; if (x < mn) mn = x; if (x > mx) mx = x; sum += x; }
      sig.count = vv.length; sig.min = mn; sig.max = mx; sig.sum = sum;
      sig.first = vv.length ? vv[0] : null;
      if (vv.length) sig.last = vv[vv.length - 1];
    }
    buildDerived();
    renderSummary();
    if (!recCapped) $('#status').textContent = `● LIVE — ${state.totalFrames.toLocaleString('it-IT')} frame ricevuti · `
      + `${[...state.signals.values()].filter(s => s.count).length} grandezze · finestra ${Math.round(LIVE_WINDOW_MS / 60000)} min`;
    const mb = (liveRec.length * 40 / 1048576);
    $('#rec-info').textContent = liveRec.length
      ? `registrati ${liveRec.length.toLocaleString('it-IT')} frame (~${mb.toFixed(1)} MB)` : 'registrazione…';
    const tab = document.querySelector('.tab-btn.active').getAttribute('data-tab');
    if (tab === 'signals') renderSignals($('#sig-filter').value);
    else if (tab === 'messages') renderMessages();
    else if (tab === 'plot') {
      const keys = [...$('#plot-select').selectedOptions].map(o => o.value);
      if (keys.length) drawInto($('#plot-canvas'), keys, $('#plot-legend'));
    }
    if (state._dirtyPicker) { renderPlotPicker(); state._dirtyPicker = false; }
  }

  function saveDump() {
    if (!liveRec.length) { alert('Nessun frame registrato da salvare.'); return; }
    let name = ($('#dump-name').value || 'cattura_live').trim().replace(/[^\w.\-]+/g, '_');
    if (!/\.csv$/i.test(name)) name += '.csv';
    const lines = new Array(liveRec.length);
    for (let i = 0; i < liveRec.length; i++) {
      const r = liveRec[i];
      const canid = r.id ? parseInt(r.id, 16) : '';
      lines[i] = `${r.id},${canid},${r.pgn},${r.source},${r.ts},live,${r.d},false`;
    }
    const csv = 'hexCanId,canId,pgn,source,timestamp,iface,value,willBeFiltered\n' + lines.join('\n') + '\n';
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = el('a'); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    $('#status').textContent = `Dump salvato: ${name} — ${liveRec.length.toLocaleString('it-IT')} frame.`;
  }

  /* ---------- init ---------- */
  function init() {
    DEC.buildIndex();
    setupTabs();
    $('#file-input').addEventListener('change', e => { disconnectLive(true); readFiles(e.target.files); });
    $('#btn-auto').addEventListener('click', () => { disconnectLive(true); autoLoad(); });
    $('#btn-live').addEventListener('click', () => {
      if (liveMode) disconnectLive();
      else connectLive($('#ws-url').value.trim());
    });
    $('#btn-save').addEventListener('click', saveDump);
    $('#sig-filter').addEventListener('input', e => renderSignals(e.target.value));
    $('#plot-select').addEventListener('change', e => {
      const keys = [...e.target.selectedOptions].map(o => o.value).slice(0, 8);
      drawInto($('#plot-canvas'), keys, $('#plot-legend'));
    });
    const dz = $('#dropzone');
    ['dragover', 'dragenter'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('hover'); }));
    ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('hover'); }));
    dz.addEventListener('drop', e => readFiles(e.dataTransfer.files));
    window.addEventListener('resize', () => {
      if (activeChart) {
        const sel = $('#plot-select');
        const keys = [...sel.selectedOptions].map(o => o.value);
        if (keys.length) drawInto($('#plot-canvas'), keys, $('#plot-legend'));
      }
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
