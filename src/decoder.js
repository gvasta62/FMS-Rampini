/* decoder.js — parsing dei dump candump CSV e decodifica J1939 secondo il DBC.
 * Espone window.FMSDecoder con:
 *   buildIndex()                      -> prepara le strutture dal DB segnali (window.FMS_DB)
 *   parseCsv(text)                    -> [{pgn,source,ts,bytes}]  (frame grezzi)
 *   decodeFrame(frame)               -> [{msg, sig, raw, phys, na, label}]  (segnali decodificati)
 */
(function () {
  'use strict';

  const PROP = new Set((window.FMS_DB && window.FMS_DB.proprietaryPgns) || [65280, 65281, 65282]);

  // pgn -> [messaggi]    e    pgn+sa -> messaggio
  let byPgn = new Map();

  function buildIndex() {
    byPgn = new Map();
    for (const msg of window.FMS_DB.messages) {
      if (!byPgn.has(msg.pgn)) byPgn.set(msg.pgn, []);
      byPgn.get(msg.pgn).push(msg);
    }
    return byPgn;
  }

  /* ---- parsing CSV ---------------------------------------------------- */
  function hexToBytes(hex) {
    const n = (hex.length / 2) | 0;
    const out = new Uint8Array(n);
    for (let i = 0; i < n; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
    return out;
  }

  function parseCsv(text) {
    const frames = [];
    let i = 0;
    // salta header
    let nl = text.indexOf('\n');
    if (nl === -1) return frames;
    i = nl + 1;
    const len = text.length;
    while (i < len) {
      let end = text.indexOf('\n', i);
      if (end === -1) end = len;
      const line = text.charCodeAt(end - 1) === 13 ? text.slice(i, end - 1) : text.slice(i, end);
      i = end + 1;
      if (!line) continue;
      // colonne: hexCanId,canId,pgn,source,timestamp,iface,value,willBeFiltered
      const c = line.split(',');
      if (c.length < 7) continue;
      const pgn = +c[2], source = +c[3], ts = +c[4], value = c[6];
      if (!Number.isFinite(pgn) || !Number.isFinite(ts) || !value) continue;
      frames.push({ pgn, source, ts, bytes: hexToBytes(value) });
    }
    return frames;
  }

  /* ---- decodifica di un singolo segnale ------------------------------ */
  function rawIntel(bytes, start, length) {
    // little-endian: byte0 = LSB. BigInt per sicurezza fino a 32+ bit.
    let val = 0n;
    const nb = bytes.length;
    for (let b = nb - 1; b >= 0; b--) val = (val << 8n) | BigInt(bytes[b]);
    const mask = (1n << BigInt(length)) - 1n;
    return (val >> BigInt(start)) & mask;
  }

  function rawMotorola(bytes, start, length) {
    // big-endian (sawtooth). Estrae bit per bit partendo dal MSB indicato da `start`.
    let bit = start, val = 0n;
    for (let k = 0; k < length; k++) {
      const byteIdx = bit >> 3;
      const bitInByte = bit & 7;
      const b = byteIdx < bytes.length ? bytes[byteIdx] : 0;
      val = (val << 1n) | BigInt((b >> bitInByte) & 1);
      // avanza al bit successivo nella numerazione Motorola
      if (bitInByte === 0) bit += 15; else bit -= 1;
    }
    return val;
  }

  function decodeSignal(bytes, sg) {
    let raw = sg.order === 1 ? rawIntel(bytes, sg.start, sg.len)
                             : rawMotorola(bytes, sg.start, sg.len);
    // N/A: tutti 1 sui bit del segnale (tipico 0xFF..)
    const allOnes = raw === (1n << BigInt(sg.len)) - 1n;
    if (sg.signed) {
      const half = 1n << BigInt(sg.len - 1);
      if (raw >= half) raw -= 1n << BigInt(sg.len);
    }
    const rawNum = Number(raw);
    let label = null, na = false;
    if (sg.vt && Object.prototype.hasOwnProperty.call(sg.vt, String(rawNum))) {
      label = sg.vt[String(rawNum)];
      if (/n\.?\/?a/i.test(label)) na = true;
    }
    if (allOnes && sg.len >= 8) na = true; // 0xFF / 0xFFFF... = non disponibile
    const phys = rawNum * sg.scale + sg.offset;
    return { raw: rawNum, phys, na, label };
  }

  /* ---- scelta della definizione messaggio + decodifica frame --------- */
  function pickMsg(pgn, source) {
    const defs = byPgn.get(pgn);
    if (!defs) return null;
    // PGN proprietari condivisi documentati (0xFF00/01/02): valido SOLO source 30 (BMS),
    // gli altri source (HVAC/DCDC/PCU) vanno ignorati anche se definiti nel DBC.
    if (PROP.has(pgn)) {
      if (source !== 30) return null;
      return defs.find(d => d.sa === 30) || null;
    }
    // match esatto (pgn, source): sempre preferito e affidabile.
    const exact = defs.find(d => d.sa === source);
    if (exact) return exact;
    // Altri PGN proprietari (>= 0xFF00 = 65280): zona di collisione indirizzi J1939.
    // Niente fallback per-solo-PGN: un source non riconosciuto è spurio -> scarta.
    // (esclude p.es. BMS_STAT2/BMS_DIAG da source 208/39/40 senza perdere nessun
    //  messaggio legittimo, il cui source DBC coincide già con quello reale).
    if (pgn >= 0xFF00) return null;
    // PGN standard a definizione unica: recupero per solo-PGN (il source del DBC
    // poteva essere ereditato da un template diesel e non coincidere con la realtà).
    if (defs.length === 1) return defs[0];
    // PGN standard con più definizioni e nessun match di source: ambiguo -> scarta.
    return null;
  }

  function decodeFrame(frame) {
    const msg = pickMsg(frame.pgn, frame.source);
    if (!msg || !msg.signals.length) return null;
    const bytes = frame.bytes;
    // multiplexing: trova selettore
    let muxVal = null;
    const sel = msg.signals.find(s => s.mux === 'M');
    if (sel) muxVal = Number(sel.order === 1 ? rawIntel(bytes, sel.start, sel.len)
                                             : rawMotorola(bytes, sel.start, sel.len));
    const out = [];
    for (const sg of msg.signals) {
      if (sg.mux === 'M') continue;
      if (sg.mux !== null && sg.mux !== undefined && sg.mux !== muxVal) continue;
      // byte insufficienti per il segnale -> salta
      if ((sg.start + sg.len) > bytes.length * 8) continue;
      const d = decodeSignal(bytes, sg);
      out.push({ msg: msg.name, sig: sg.name, unit: sg.unit, desc: sg.desc || '',
                 raw: d.raw, phys: d.phys, na: d.na, label: d.label });
    }
    return { msg, signals: out };
  }

  window.FMSDecoder = { buildIndex, parseCsv, decodeFrame, PROP };
})();
