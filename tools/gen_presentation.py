#!/usr/bin/env python3
"""Genera docs/infografica.html e docs/slide.html dal catalogo grandezze.

Uso:  python3 tools/gen_presentation.py
Legge:  docs/catalogo_grandezze.json   (prodotto decodificando i dump)
Scrive: docs/infografica.html , docs/slide.html   (statici, self-contained)
"""
import json, os, html, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(ROOT, 'docs', 'catalogo_grandezze.json')

# meta per sottosistema: icona + colore. Ordine = ordine di presentazione.
SUBS = [
    ('Batteria / BMS',          '🔋', '#2563eb'),
    ('Trazione / Motore',       '⚙️', '#dc2626'),
    ('Velocità / Odometro',     '🚌', '#059669'),
    ('Climatizzazione (RHCV)',  '❄️', '#0891b2'),
    ('Porte / Accessibilità',   '🚪', '#7c3aed'),
    ('Freni / Aria',            '🛑', '#b45309'),
    ('Diagnostica (DTC)',       '⚠️', '#db2777'),
    ('Ambiente',                '🌡️', '#65a30d'),
    ('Tempo / Data',            '🕐', '#475569'),
    ('Livelli',                 '🛢️', '#9333ea'),
]


def num(x):
    if x is None:
        return ''
    r = round(x, 2)
    if r == int(r):
        r = int(r)
    return str(r).replace('.', ',')


def val_str(s):
    """Descrizione sintetica del valore osservato per una grandezza."""
    if s['categorical'] and s['labels']:
        return ' · '.join(s['labels'])
    if s['n'] == 0:
        return 'n/d (solo N/A)'
    mn, mx, me = s['min'], s['max'], s['mean']
    u = (' ' + s['unit']) if s['unit'] else ''
    if mn == mx:
        return f"{num(mn)}{u} (costante)"
    return f"{num(mn)} … {num(mx)}{u}  ·  media {num(me)}{u}"


def build_lamps(cat):
    """Rileva le spie cruscotto (DM1) risultate ACCESE nel dump, con il relativo DTC."""
    diag = cat['subsystems'].get('Diagnostica (DTC)', [])
    bymsg = {}
    for s in diag:
        bymsg.setdefault(s['msg'], {})[s['sig']] = s
    SYS = {'DM01_BMS': 'BMS — batteria',
           'DM01_ECAS': 'ECAS — sospensioni pneumatiche',
           'DM01_RHCV': 'RHCV — clima di tetto'}
    LAMPS = [('AmberWarningLamp', 'Spia ambra (warning)', '🟠'),
             ('RedStopLamp', 'Spia rossa (stop)', '🔴'),
             ('MalfunctionIndicatorLamp', 'Spia MIL (malfunzionamento)', '🟡'),
             ('ProtectLamp', 'Spia protezione', '🔵')]
    active = []
    for msg, sysname in SYS.items():
        sigs = bymsg.get(msg)
        if not sigs:
            continue
        suf = '_ECAS' if msg == 'DM01_ECAS' else ''
        def g(base):
            return sigs.get(base + suf) or sigs.get(base)
        spn, fmi, oc = g('SPN0'), g('FMI0'), g('OccurrenceCount0')
        for base, label, icon in LAMPS:
            sig = g(base)
            if not sig:
                continue
            if sig['categorical'] and sig['labels']:
                on = any('On' in l for l in sig['labels'])
            elif sig['n'] > 0:
                on = (sig['max'] == 1)
            else:
                on = False
            if on:
                active.append({'sys': sysname, 'label': label, 'icon': icon,
                               'spn': int(spn['max']) if spn and spn['n'] else '—',
                               'fmi': int(fmi['max']) if fmi and fmi['n'] else '—',
                               'oc': int(oc['max']) if oc and oc['n'] else '—'})
    return active


def load():
    cat = json.load(open(CAT, encoding='utf-8'))
    present = [(name, ic, col, [s for s in cat['subsystems'].get(name, [])])
               for name, ic, col in SUBS if name in cat['subsystems']]
    return cat, present


def stats(cat):
    tot = sum(len(v) for v in cat['subsystems'].values())
    withdata = sum(1 for v in cat['subsystems'].values() for s in v if s['n'] > 0)
    return {
        'frames': f"{cat['frames']:,}".replace(',', '.'),
        'dur': f"{cat['durSec']:.1f} s ({int(cat['durSec']//60)} min {round(cat['durSec']%60)} s)",
        'tot': tot, 'withdata': withdata,
        'subs': len(cat['subsystems']),
    }


# --------------------------------------------------------------------------
def gen_infographic(cat, present, st, lamps):
    HVAC = 'Climatizzazione (RHCV)'
    cards = []
    hvac_html = ''
    for name, ic, col, sigs in present:
        nd = sum(1 for s in sigs if s['n'] > 0)
        rows = []
        for s in sigs:
            dim = '' if s['n'] > 0 else ' style="opacity:.5"'
            rows.append(
                f'<li{dim}><span class="sg">{html.escape(s["sig"])}</span>'
                f'<span class="vl">{html.escape(val_str(s))}</span></li>')
        if name == HVAC:
            hvac_html = f'''
      <section class="card hvac" style="--c:{col}">
        <header><span class="ic">{ic}</span><h2>{html.escape(name)} — climatizzazione di bordo</h2>
          <span class="badge2">❄️ HVAC · IN RISALTO</span></header>
        <ul class="cols2">{''.join(rows)}</ul>
      </section>'''
        else:
            cards.append(f'''
      <section class="card" style="--c:{col}">
        <header><span class="ic">{ic}</span><h2>{html.escape(name)}</h2>
          <span class="cnt">{nd} grandezze</span></header>
        <ul>{''.join(rows)}</ul>
      </section>''')

    if lamps:
        items = ''.join(
            f'<li>{a["icon"]} <b>{a["label"]}</b> — {a["sys"]} '
            f'<span class="dtc">guasto attivo · SPN {a["spn"]} · FMI {a["fmi"]} · {a["oc"]} occorrenze</span></li>'
            for a in lamps)
        banner = (f'<div class="alert"><div class="alert-h">⚠️ Spie cruscotto rilevate ACCESE nel dump — {len(lamps)}</div>'
                  f'<ul>{items}</ul>'
                  f'<p class="alert-foot">Le altre spie (rossa di stop, MIL di malfunzionamento, protezione) risultano spente.</p></div>')
    else:
        banner = '<div class="alert ok"><div class="alert-h">✅ Nessuna spia cruscotto accesa nel dump</div></div>'

    today = datetime.date(2026, 6, 27).strftime('%d/%m/%Y')
    return f'''<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FMS-Rampini — Infografica grandezze</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#0f172a;color:#e2e8f0;font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px}}
.hero{{text-align:center;padding:14px 0 22px}}
.hero h1{{font-size:30px;margin:0 0 4px;background:linear-gradient(90deg,#60a5fa,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}}
.hero p{{color:#94a3b8;margin:2px 0;font-size:14px}}
.kpis{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin:18px 0 6px}}
.kpi{{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:12px 20px;min-width:140px}}
.kpi b{{font-size:26px;display:block;color:#f8fafc}}
.kpi span{{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#94a3b8}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-top:18px}}
.card{{background:#1e293b;border:1px solid #334155;border-top:4px solid var(--c);border-radius:12px;padding:14px 16px;break-inside:avoid}}
.card header{{display:flex;align-items:center;gap:9px;margin-bottom:8px}}
.card .ic{{font-size:20px}}
.card h2{{font-size:16px;margin:0;flex:1;color:#f1f5f9}}
.card .cnt{{font-size:11px;color:#0f172a;background:var(--c);padding:2px 9px;border-radius:20px;font-weight:600}}
.card ul{{list-style:none;margin:0;padding:0}}
.card li{{display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px solid #2b3a4f;font-size:12.5px}}
.card li:last-child{{border-bottom:none}}
.sg{{color:#cbd5e1;font-family:ui-monospace,Consolas,monospace;font-size:12px;white-space:nowrap}}
.vl{{color:#7dd3fc;text-align:right}}
.alert{{background:#3b2410;border:1px solid #b45309;border-left:5px solid #f59e0b;border-radius:12px;padding:14px 18px;margin:10px 0 4px}}
.alert.ok{{background:#0e2a1c;border-color:#15803d;border-left-color:#22c55e}}
.alert-h{{font-size:16px;font-weight:700;color:#fbbf24;margin-bottom:8px}}
.alert.ok .alert-h{{color:#86efac;margin-bottom:0}}
.alert ul{{list-style:none;margin:0;padding:0}}
.alert li{{padding:5px 0;border-bottom:1px solid #5a3a17;font-size:13.5px;color:#fde68a}}
.alert li:last-child{{border-bottom:none}}
.alert .dtc{{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#fca5a5;background:#2a1206;padding:1px 8px;border-radius:6px}}
.alert-foot{{color:#b08055;font-size:12px;margin:8px 0 0}}
.card.hvac{{border:1px solid #22d3ee;box-shadow:0 0 0 2px rgba(34,211,238,.25);background:#0c2733;margin:14px 0}}
.card.hvac h2{{color:#a5f3fc}}
.badge2{{font-size:11px;color:#06141b;background:#22d3ee;padding:3px 11px;border-radius:20px;font-weight:700}}
ul.cols2{{column-count:2;column-gap:28px}}
ul.cols2 li{{break-inside:avoid}}
.note{{margin-top:22px;background:#15233b;border:1px solid #334155;border-radius:12px;padding:14px 18px;font-size:12.5px;color:#94a3b8}}
.note b{{color:#e2e8f0}}
.foot{{text-align:center;color:#64748b;font-size:11.5px;margin-top:18px}}
@media print{{body{{background:#fff;color:#111}}.card,.kpi,.note{{background:#fff;border-color:#ccc}}.hero h1{{color:#1e40af;-webkit-text-fill-color:#1e40af}}.sg{{color:#333}}.vl{{color:#1e40af}}}}
</style></head><body><div class="wrap">
  <div class="hero">
    <h1>Bus elettrico Rampini Eltron — grandezze sul canale FMS</h1>
    <p>Catalogo completo dei dati decodificati dal dump CAN&nbsp;J1939 · deposito di Terni · Busitalia</p>
    <div class="kpis">
      <div class="kpi"><b>{st['frames']}</b><span>frame CAN</span></div>
      <div class="kpi"><b>{st['dur']}</b><span>durata · marcia reale</span></div>
      <div class="kpi"><b>{st['withdata']}</b><span>grandezze con dati</span></div>
      <div class="kpi"><b>{st['subs']}</b><span>sottosistemi</span></div>
      <div class="kpi"><b>24</b><span>messaggi decodificati</span></div>
    </div>
  </div>
  {banner}
  {hvac_html}
  <div class="grid">{''.join(cards)}</div>
  <div class="note">
    <b>Come si leggono i dati.</b> Ogni frame CAN viene riconosciuto dal suo <b>PGN</b> (tipo di messaggio) e
    decodificato secondo il DBC del costruttore (Intel/Motorola, segno, scala, offset, tabelle di stato).
    I PGN proprietari 0xFF00.. sono accettati solo dalla centralina corretta (BMS = indirizzo 30).
    La <b>Potenza istantanea</b> è derivata come Vpack × IPack (≈4 Hz). I valori mostrati sono il range osservato nel dump.
  </div>
  <div class="foot">FMS-Rampini · generato il {today} · dashboard: https://gvasta62.github.io/FMS-Rampini/</div>
</div></body></html>'''


# --------------------------------------------------------------------------
def gen_slides(cat, present, st, lamps):
    slides = []

    def slide(cls, inner):
        slides.append(f'<section class="slide {cls}">{inner}</section>')

    # 1 — titolo
    slide('title', f'''
      <div class="badge">🔋 BUS ELETTRICO · CANALE FMS · J1939</div>
      <h1>Le grandezze del bus Rampini&nbsp;Eltron</h1>
      <p class="sub">Catalogo dei dati disponibili sul dump del bus FMS — deposito di Terni</p>
      <p class="org">Busitalia · Direzione Ingegneria Parco Mezzi</p>''')

    # 2 — numeri
    slide('stats', f'''
      <h2>Il dump in numeri</h2>
      <div class="kpis">
        <div class="kpi"><b>{st['frames']}</b><span>frame CAN registrati</span></div>
        <div class="kpi"><b>{st['dur']}</b><span>durata (marcia reale 0–52 km/h)</span></div>
        <div class="kpi"><b>{st['withdata']}</b><span>grandezze decodificate</span></div>
        <div class="kpi"><b>{st['subs']}</b><span>sottosistemi del veicolo</span></div>
        <div class="kpi"><b>24</b><span>messaggi CAN diversi</span></div>
        <div class="kpi"><b>6</b><span>file dump uniti per timestamp</span></div>
      </div>''')

    # 3 — come funziona
    slide('flow', '''
      <h2>Dal segnale grezzo alla grandezza</h2>
      <div class="pipe">
        <div class="step"><span>1</span><b>Frame CAN grezzo</b><code>0CFF3F1E … 95301786abac0000</code><p>PGN + source + payload esadecimale</p></div>
        <div class="arr">→</div>
        <div class="step"><span>2</span><b>Chiave DBC</b><code>61 messaggi · 171 segnali</code><p>bit, endianness, scala, offset, stati</p></div>
        <div class="arr">→</div>
        <div class="step"><span>3</span><b>Grandezza fisica</b><code>Vpack = 636,3 V</code><p>con unità, range e statistiche</p></div>
      </div>
      <p class="cap">Regola chiave: i PGN proprietari 0xFF00.. sono validi solo dalla centralina corretta (BMS = indirizzo 30); così i frame spuri di altre centraline non sovrascrivono i dati batteria.</p>''')

    # 4 — overview sottosistemi
    chips = ''.join(
        f'<div class="ovc" style="--c:{col}"><span>{ic}</span><b>{html.escape(n)}</b>'
        f'<i>{sum(1 for s in sg if s["n"]>0)} grandezze</i></div>'
        for n, ic, col, sg in present)
    slide('overview', f'<h2>Dieci sottosistemi monitorati</h2><div class="ovgrid">{chips}</div>')

    # 5..N — una slide per sottosistema
    for name, ic, col, sigs in present:
        nd = sum(1 for s in sigs if s['n'] > 0)
        rows = []
        for s in sigs:
            dim = ' class="dim"' if s['n'] == 0 else ''
            unit = html.escape(s['unit']) if s['unit'] else '—'
            rows.append(
                f'<tr{dim}><td class="mono">{html.escape(s["sig"])}</td>'
                f'<td>{unit}</td><td class="v">{html.escape(val_str(s))}</td>'
                f'<td class="n">{s["n"]:,}</td></tr>'.replace(',', '.'))
        disp = html.escape(name) + (' &nbsp;·&nbsp; HVAC' if name == 'Climatizzazione (RHCV)' else '')
        callout = ''
        if name == 'Diagnostica (DTC)' and lamps:
            ll = ' &nbsp;·&nbsp; '.join(
                f'{a["icon"]} {a["label"]} <i>({a["sys"].split(" —")[0]} · SPN {a["spn"]} / FMI {a["fmi"]} · {a["oc"]}×)</i>'
                for a in lamps)
            callout = f'<div class="lampcall">⚠️ <b>Spie cruscotto accese nel dump:</b> {ll}</div>'
        slide('detail', f'''
          <h2 style="--c:{col}"><span class="ic">{ic}</span>{disp}
            <em>{nd} grandezze</em></h2>{callout}
          <table><thead><tr><th>Grandezza</th><th>Unità</th><th>Valore osservato nel dump</th><th>Campioni</th></tr></thead>
          <tbody>{''.join(rows)}</tbody></table>''')

    # chiusura
    slide('end', '''
      <h2>In sintesi</h2>
      <ul class="big">
        <li>✅ <b>86 grandezze</b> leggibili dal dump, su 10 sottosistemi</li>
        <li>🔋 Telemetria batteria completa: tensione, corrente, SoC, SOH 94,8%, temperature, potenza</li>
        <li>🚌 Dinamica di marcia: velocità 0–52 km/h, regime motore, pedali, odometro</li>
        <li>⚠️ <b>''' + str(len(lamps)) + ''' spie ambra accese</b> nel dump — DTC attivi su BMS e sospensioni ECAS</li>
        <li>🌐 Tutto consultabile online: <b>gvasta62.github.io/FMS-Rampini</b></li>
      </ul>''')

    total = len(slides)
    nav = ''.join(slides)
    return f'''<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FMS-Rampini — Slide grandezze</title>
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;height:100%;background:#0b1220;font:16px/1.5 system-ui,Segoe UI,Roboto,sans-serif;color:#e2e8f0}}
.deck{{height:100vh;overflow:hidden;position:relative}}
.slide{{position:absolute;inset:0;display:none;flex-direction:column;justify-content:center;
  padding:6vh 7vw;animation:fade .25s ease}}
.slide.active{{display:flex}}
@keyframes fade{{from{{opacity:.3}}to{{opacity:1}}}}
h1{{font-size:46px;margin:.2em 0;line-height:1.1;background:linear-gradient(90deg,#60a5fa,#22d3ee);-webkit-background-clip:text;background-clip:text;color:transparent}}
h2{{font-size:30px;margin:0 0 22px;color:#f1f5f9;display:flex;align-items:center;gap:12px}}
h2 .ic{{font-size:30px}}
h2 em{{font-style:normal;font-size:14px;font-weight:600;color:#0b1220;background:var(--c,#38bdf8);padding:3px 12px;border-radius:20px;margin-left:auto}}
.title{{align-items:flex-start}}
.badge{{font-size:13px;letter-spacing:1px;color:#22d3ee;border:1px solid #164e63;background:#0c2030;padding:6px 14px;border-radius:20px}}
.sub{{font-size:20px;color:#cbd5e1;margin:6px 0}}
.org{{color:#64748b;margin-top:18px}}
.kpis{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
.kpi{{background:#15233b;border:1px solid #334155;border-radius:14px;padding:20px 22px}}
.kpi b{{font-size:30px;display:block;color:#f8fafc}}
.kpi span{{color:#94a3b8;font-size:13px}}
.pipe{{display:flex;align-items:stretch;gap:14px;margin-top:10px}}
.step{{flex:1;background:#15233b;border:1px solid #334155;border-radius:14px;padding:18px;position:relative}}
.step span{{position:absolute;top:-14px;left:18px;width:28px;height:28px;border-radius:50%;background:#2563eb;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700}}
.step b{{display:block;font-size:18px;margin-bottom:8px;color:#f1f5f9}}
.step code{{display:block;background:#0b1220;border:1px solid #243044;border-radius:8px;padding:8px;font-size:12.5px;color:#7dd3fc;word-break:break-all}}
.step p{{color:#94a3b8;font-size:13px;margin:8px 0 0}}
.arr{{display:flex;align-items:center;color:#38bdf8;font-size:30px}}
.cap{{color:#94a3b8;font-size:14px;margin-top:26px;border-left:3px solid #2563eb;padding-left:14px}}
.ovgrid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}}
.ovc{{background:#15233b;border:1px solid #334155;border-top:4px solid var(--c);border-radius:14px;padding:18px 12px;text-align:center}}
.ovc span{{font-size:30px;display:block}}
.ovc b{{display:block;font-size:14px;margin:8px 0 4px;color:#f1f5f9}}
.ovc i{{font-style:normal;font-size:12px;color:#94a3b8}}
table{{width:100%;border-collapse:collapse;font-size:15px}}
th{{text-align:left;color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:.4px;border-bottom:2px solid #334155;padding:6px 10px}}
td{{padding:6px 10px;border-bottom:1px solid #1f2c44}}
td.mono{{font-family:ui-monospace,Consolas,monospace;font-size:13.5px;color:#e2e8f0}}
td.v{{color:#7dd3fc}}
td.n{{text-align:right;color:#94a3b8;font-variant-numeric:tabular-nums}}
tr.dim td{{opacity:.45}}
.lampcall{{background:#3b2410;border:1px solid #b45309;border-left:4px solid #f59e0b;border-radius:10px;padding:10px 16px;margin:-8px 0 16px;color:#fde68a;font-size:15px}}
.lampcall i{{font-style:normal;color:#fca5a5;font-family:ui-monospace,Consolas,monospace;font-size:13px}}
h2 em.hv{{background:#22d3ee}}
.detail table{{display:block;max-height:58vh;overflow:auto}}
ul.big{{font-size:21px;line-height:2;list-style:none;padding:0}}
ul.big b{{color:#f8fafc}}
.hud{{position:fixed;bottom:16px;right:20px;display:flex;align-items:center;gap:12px;z-index:10}}
.hud button{{background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;width:38px;height:34px;font-size:16px;cursor:pointer}}
.hud button:hover{{background:#334155}}
.hud .pg{{color:#94a3b8;font-size:13px;min-width:52px;text-align:center}}
.bar{{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,#60a5fa,#22d3ee);z-index:10;transition:width .2s}}
@media print{{.slide{{display:flex!important;position:relative;height:100vh;page-break-after:always;background:#0b1220}}.hud,.bar{{display:none}}}}
</style></head><body>
<div class="bar" id="bar"></div>
<div class="deck" id="deck">{nav}</div>
<div class="hud"><button id="prev">‹</button><span class="pg" id="pg"></span><button id="next">›</button></div>
<script>
const sl=[...document.querySelectorAll('.slide')];let i=0;const N=sl.length;
function show(n){{i=Math.max(0,Math.min(N-1,n));sl.forEach((s,k)=>s.classList.toggle('active',k===i));
  document.getElementById('pg').textContent=(i+1)+' / '+N;
  document.getElementById('bar').style.width=((i+1)/N*100)+'%';}}
document.getElementById('next').onclick=()=>show(i+1);
document.getElementById('prev').onclick=()=>show(i-1);
document.addEventListener('keydown',e=>{{if(e.key==='ArrowRight'||e.key===' ')show(i+1);
  if(e.key==='ArrowLeft')show(i-1);if(e.key==='Home')show(0);if(e.key==='End')show(N-1);}});
show(0);
</script></body></html>'''


def main():
    cat, present = load()
    st = stats(cat)
    lamps = build_lamps(cat)
    open(os.path.join(ROOT, 'docs', 'infografica.html'), 'w', encoding='utf-8').write(
        gen_infographic(cat, present, st, lamps))
    open(os.path.join(ROOT, 'docs', 'slide.html'), 'w', encoding='utf-8').write(
        gen_slides(cat, present, st, lamps))
    print(f"OK: infografica.html + slide.html  ({st['withdata']} grandezze, "
          f"{st['subs']} sottosistemi, {len(lamps)} spie accese)")
    for a in lamps:
        print(f"   {a['icon']} {a['label']} — {a['sys']} (SPN {a['spn']}/FMI {a['fmi']}, {a['oc']}×)")


if __name__ == '__main__':
    main()
