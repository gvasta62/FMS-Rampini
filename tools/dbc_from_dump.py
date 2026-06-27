#!/usr/bin/env python3
"""Banco di lavoro DBC — dal dump di un mezzo verso il suo file DBC.

Quattro modalità:
  inventory  Inventario dei messaggi presenti nel dump + analisi byte/bit.
  skeleton   Genera uno scheletro DBC: usa il SEED J1939 standard per i PGN noti,
             e crea segnali placeholder (per byte attivo) per i PGN proprietari.
  remap      Adatta un DBC esistente al mezzo: rimappa i source address in base a
             ciò che il dump trasmette davvero (match esatto, rimappa, assente).
  makeseed   Crea un seed DBC standard estraendo i PGN < 0xFF00 da un DBC dato.

ESEMPI
  python3 tools/dbc_from_dump.py inventory --data data --out docs/dump_inventory.md
  python3 tools/dbc_from_dump.py skeleton  --data data --out nuovo_mezzo.dbc
  python3 tools/dbc_from_dump.py remap --dbc data/RAMPINI_ELTRON_TERNI_corretto.dbc --data data --out rimappato.dbc
  python3 tools/dbc_from_dump.py makeseed --dbc data/RAMPINI_ELTRON_TERNI_corretto.dbc --out data/fms_standard_seed.dbc
"""
import argparse, glob, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_DEFAULT = os.path.join(ROOT, 'data', 'fms_standard_seed.dbc')


# ---------------------------------------------------------------- J1939
def pgn_source(cid29):
    pf = (cid29 >> 16) & 0xFF
    ps = (cid29 >> 8) & 0xFF
    dp = (cid29 >> 24) & 1
    edp = (cid29 >> 25) & 1
    pgn = (edp << 17) | (dp << 16) | (pf << 8) | (ps if pf >= 240 else 0)
    return pgn, cid29 & 0xFF


def boid_of(cid29):
    """ID per la definizione BO_ del DBC (frame esteso)."""
    return 0x80000000 | (cid29 & 0x1FFFFFFF)


# ---------------------------------------------------------------- lettura dump
def load_frames(files):
    """Ritorna lista di (canId29, pgn, source, value_hex). Ordinata per timestamp."""
    rows = []
    for f in files:
        with open(f) as fh:
            next(fh, None)
            for line in fh:
                c = line.rstrip('\n').split(',')
                if len(c) > 6 and c[1].lstrip('-').isdigit() and c[2].isdigit() and c[3].isdigit() and c[4].isdigit():
                    rows.append((int(c[4]), int(c[1]) & 0x1FFFFFFF, int(c[2]), int(c[3]), c[6]))
    rows.sort(key=lambda r: r[0])
    return rows


def analyze(rows):
    """Inventario per (pgn,source) con statistiche per byte."""
    msgs = {}
    g_tmin = rows[0][0] if rows else 0
    g_tmax = rows[-1][0] if rows else 0
    for ts, cid, pgn, src, val in rows:
        key = (pgn, src)
        m = msgs.get(key)
        if not m:
            m = {'cid': cid, 'pgn': pgn, 'src': src, 'dlc': 0, 'n': 0,
                 'first': ts, 'last': ts, 'bytes': [None] * 8}
            msgs[key] = m
        m['n'] += 1; m['last'] = ts
        data = bytes.fromhex(val) if len(val) % 2 == 0 else b''
        m['dlc'] = max(m['dlc'], len(data))
        for i, b in enumerate(data[:8]):
            bs = m['bytes'][i]
            if bs is None:
                bs = m['bytes'][i] = {'min': b, 'max': b, 'distinct': set(), 'inc': 0, 'dec': 0,
                                      'prev': None, 'nff': 0, 'allff': True}
            bs['min'] = min(bs['min'], b); bs['max'] = max(bs['max'], b)
            if len(bs['distinct']) < 64:
                bs['distinct'].add(b)
            if b != 0xFF:
                bs['allff'] = False; bs['nff'] += 1
            if bs['prev'] is not None:
                if b > bs['prev']: bs['inc'] += 1
                elif b < bs['prev']: bs['dec'] += 1
            bs['prev'] = b
    return msgs, (g_tmax - g_tmin) / 1000.0 or 1.0


def classify_byte(bs):
    if bs is None:
        return '—', 'assente'
    nd = len(bs['distinct'])
    if bs['allff']:
        return 'unused', 'sempre 0xFF (non usato / N/A)'
    if nd == 1:
        return 'const', f"costante 0x{bs['min']:02X}"
    if bs['inc'] > 0 and bs['dec'] <= max(1, bs['inc'] // 50) and nd > 3:
        return 'counter', f"contatore ↑ ({nd}+ valori, {bs['min']}..{bs['max']})"
    if nd <= 16:
        return 'enum', f"enum/flag ({nd} valori)"
    return 'analog', f"analogico ({nd}{'+' if nd>=64 else ''} val, {bs['min']}..{bs['max']})"


# ---------------------------------------------------------------- parsing DBC
def parse_dbc(text):
    """Ritorna (messages, cm_by_boid, val_by_boid)."""
    messages = []
    cm_by = {}
    val_by = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r'\s*BO_ (\d+) (\w+)\s*:\s*(\d+)', line)
        if m:
            boid = int(m.group(1)); pgn, sa = pgn_source(boid & 0x1FFFFFFF)
            cur = {'boid': boid, 'name': m.group(2), 'dlc': int(m.group(3)),
                   'pgn': pgn, 'sa': sa, 'sgs': []}
            messages.append(cur); continue
        if re.match(r'\s*SG_ ', line) and cur is not None:
            cur['sgs'].append(line); continue
        mc = re.match(r'\s*CM_ (?:SG_|BO_) (\d+) ', line)
        if mc:
            cm_by.setdefault(int(mc.group(1)), []).append(line); continue
        mv = re.match(r'\s*VAL_ (\d+) ', line)
        if mv:
            val_by.setdefault(int(mv.group(1)), []).append(line)
    return messages, cm_by, val_by


# ---------------------------------------------------------------- MODE: inventory
def mode_inventory(rows, out):
    msgs, dur = analyze(rows)
    seed = load_seed_pgns()
    order = sorted(msgs.values(), key=lambda m: -m['n'])
    L = ['# Inventario dump — messaggi e analisi byte', '',
         f"Frame totali: **{len(rows):,}** · durata **{dur:.1f} s** · "
         f"messaggi distinti **{len(msgs)}**".replace(',', '.'), '',
         '| PGN | hex | src | nome (seed std) | DLC | frame | Hz | byte attivi |',
         '|---|---|---|---|---:|---:|---:|---|']
    for m in order:
        name = seed.get(m['pgn'], {}).get('name', '—')
        active = sum(1 for i in range(m['dlc']) if (c := classify_byte(m['bytes'][i]))[0] not in ('unused', 'const', '—'))
        hz = m['n'] / ((m['last'] - m['first']) / 1000.0 or dur)
        L.append(f"| {m['pgn']} | 0x{m['pgn']:04X} | {m['src']} | {name} | {m['dlc']} | "
                 f"{m['n']:,} | {hz:.2f} | {active}/{m['dlc']} |".replace(',', '.'))
    L += ['', '## Dettaglio byte per messaggio proprietario / non-seed', '']
    for m in order:
        if m['pgn'] in seed:
            continue
        L.append(f"### PGN {m['pgn']} (0x{m['pgn']:04X}) · source {m['src']} · DLC {m['dlc']} · {m['n']:,} frame".replace(',', '.'))
        L.append('| byte | tipo | nota |')
        L.append('|---|---|---|')
        for i in range(m['dlc']):
            cls, note = classify_byte(m['bytes'][i])
            L.append(f"| b{i} | {cls} | {note} |")
        L.append('')
    write(out, '\n'.join(L))
    print(f"[inventory] {len(msgs)} messaggi · {len(rows):,} frame -> {out}".replace(',', '.'))


# ---------------------------------------------------------------- MODE: skeleton
def load_seed_pgns(seed_path=None):
    seed_path = seed_path or SEED_DEFAULT
    if not os.path.exists(seed_path):
        return {}
    messages, cm_by, val_by = parse_dbc(open(seed_path, encoding='utf-8').read())
    seed = {}
    for msg in messages:
        seed[msg['pgn']] = {'name': msg['name'], 'dlc': msg['dlc'], 'sgs': msg['sgs'],
                            'cm': cm_by.get(msg['boid'], []), 'val': val_by.get(msg['boid'], []),
                            'oldboid': msg['boid']}
    return seed


def renumber(lines, old, new):
    pat = re.compile(r'(?<!\d)' + str(old) + r'(?!\d)')
    return [pat.sub(str(new), ln) for ln in lines]


def mode_skeleton(rows, out, seed_path):
    msgs, dur = analyze(rows)
    seed = load_seed_pgns(seed_path)
    head = ['VERSION ""', '', 'NS_ :', 'BS_:', '', 'BU_: Vector__XXX', '']
    body, cms, vals = [], [], []
    seeded = skel = 0
    for m in sorted(msgs.values(), key=lambda x: x['pgn']):
        newboid = boid_of(m['cid'])
        s = seed.get(m['pgn'])
        if s:                                   # PGN standard noto -> usa il seed
            seeded += 1
            body.append(f"BO_ {newboid} {s['name']}: {s['dlc']} Vector__XXX")
            body += s['sgs']; body.append('')
            cms += renumber(s['cm'], s['oldboid'], newboid)
            vals += renumber(s['val'], s['oldboid'], newboid)
        else:                                   # proprietario / non noto -> scheletro
            skel += 1
            nm = f"PGN{m['pgn']}_SA{m['src']}"
            body.append(f"BO_ {newboid} {nm}: {m['dlc']} Vector__XXX")
            notes = []
            for i in range(m['dlc']):
                cls, note = classify_byte(m['bytes'][i])
                if cls in ('unused',):
                    notes.append(f"b{i}:{note}"); continue
                body.append(f' SG_ {nm}_b{i} : {i*8}|8@1+ (1,0) [0|255] "" Vector__XXX')
                cms.append(f'CM_ SG_ {newboid} {nm}_b{i} "{note}";')
            body.append('')
            cms.append(f'CM_ BO_ {newboid} "AUTO scheletro · {m["n"]} frame · '
                       f'{"; ".join(notes) if notes else "tutti i byte attivi"}";')
    out_txt = '\n'.join(head + body + [''] + cms + [''] + vals + [''])
    write(out, out_txt)
    print(f"[skeleton] {seeded} messaggi da seed standard + {skel} scheletri proprietari -> {out}")
    print("  Rifinisci a mano i segnali proprietari, poi valida con:  python3 tools/gen_signals.py")


# ---------------------------------------------------------------- MODE: remap
def mode_remap(rows, dbc_path, out):
    msgs, _ = analyze(rows)
    present = {}                                  # pgn -> set(source)
    for (pgn, src) in msgs:
        present.setdefault(pgn, set()).add(src)
    text = open(dbc_path, encoding='utf-8').read()
    messages, _, _ = parse_dbc(text)
    dbc_per_pgn = {}                              # quante definizioni DBC per PGN
    for msg in messages:
        dbc_per_pgn[msg['pgn']] = dbc_per_pgn.get(msg['pgn'], 0) + 1
    report = ['# Rimappatura DBC sul dump', '',
              '| messaggio | PGN | source DBC | esito | source reale |',
              '|---|---|---|---|---|']
    repl = []          # (old_boid, new_boid)
    n_ok = n_remap = n_amb = n_abs = 0
    for msg in messages:
        pgn, sa = msg['pgn'], msg['sa']
        srcs = present.get(pgn)
        if srcs is None:
            esito, real = 'PGN assente', '—'; n_abs += 1
        elif sa in srcs:
            esito, real = 'OK (coincide)', str(sa); n_ok += 1
        elif len(srcs) == 1 and dbc_per_pgn[pgn] == 1:
            # sicuro: un solo source reale e una sola definizione DBC su questo PGN
            new_sa = next(iter(srcs))
            new_boid = (msg['boid'] & ~0xFF) | new_sa
            repl.append((msg['boid'], new_boid))
            esito, real = 'RIMAPPATO', str(new_sa); n_remap += 1
        else:
            # PGN condiviso da più definizioni, o più source reali -> verifica manuale
            esito, real = 'AMBIGUO (verifica)', ', '.join(map(str, sorted(srcs))); n_amb += 1
        report.append(f"| {msg['name']} | {pgn} | {sa} | {esito} | {real} |")
    # applica le rimappature univoche al testo (rinumerando i BO_ e i riferimenti CM_/VAL_/BA_)
    for old, new in repl:
        text = re.sub(r'(?<!\d)' + str(old) + r'(?!\d)', str(new), text)
    write(out, text)
    rep_path = os.path.splitext(out)[0] + '_report.md'
    summary = f"OK {n_ok} · rimappati {n_remap} · ambigui {n_amb} · assenti {n_abs}"
    write(rep_path, '\n'.join(report) + f"\n\n**Riepilogo:** {summary}\n")
    print(f"[remap] {summary}")
    print(f"  DBC corretto -> {out}")
    print(f"  report       -> {rep_path}")
    print("  Nota: gli AMBIGUI (PGN proprietari condivisi) vanno verificati a mano col costruttore.")


# ---------------------------------------------------------------- MODE: makeseed
def mode_makeseed(dbc_path, out):
    text = open(dbc_path, encoding='utf-8').read()
    messages, cm_by, val_by = parse_dbc(text)
    head = ['VERSION "FMS standard seed"', '', 'NS_ :', 'BS_:', '', 'BU_: Vector__XXX', '']
    body, cms, vals = [], [], []
    kept = 0
    for msg in messages:
        if msg['pgn'] >= 0xFF00:                  # esclude i proprietari
            continue
        kept += 1
        body.append(f"BO_ {msg['boid']} {msg['name']}: {msg['dlc']} Vector__XXX")
        body += msg['sgs']; body.append('')
        cms += cm_by.get(msg['boid'], [])
        vals += val_by.get(msg['boid'], [])
    write(out, '\n'.join(head + body + [''] + cms + [''] + vals + ['']))
    print(f"[makeseed] {kept} messaggi standard (PGN < 0xFF00) -> {out}")


# ---------------------------------------------------------------- util
def write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, 'w', encoding='utf-8').write(text)


def gather_files(args):
    if args.files:
        return args.files
    return sorted(glob.glob(os.path.join(args.data, 'candump*.csv')))


def main():
    ap = argparse.ArgumentParser(description="Banco di lavoro DBC dal dump")
    ap.add_argument('mode', choices=['inventory', 'skeleton', 'remap', 'makeseed'])
    ap.add_argument('--data', default=os.path.join(ROOT, 'data'))
    ap.add_argument('--files', nargs='*')
    ap.add_argument('--dbc', help='DBC esistente (remap) o sorgente (makeseed)')
    ap.add_argument('--seed', default=SEED_DEFAULT, help='seed DBC standard (skeleton)')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    if args.mode == 'makeseed':
        if not args.dbc:
            ap.error('makeseed richiede --dbc')
        mode_makeseed(args.dbc, args.out); return

    rows = load_frames(gather_files(args))
    if not rows:
        ap.error('nessun frame trovato (controlla --data/--files)')

    if args.mode == 'inventory':
        mode_inventory(rows, args.out)
    elif args.mode == 'skeleton':
        mode_skeleton(rows, args.out, args.seed)
    elif args.mode == 'remap':
        if not args.dbc:
            ap.error('remap richiede --dbc')
        mode_remap(rows, args.dbc, args.out)


if __name__ == '__main__':
    main()
