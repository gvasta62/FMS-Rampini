#!/usr/bin/env python3
"""Rigenera src/signals.js a partire dal DBC del costruttore.

Uso:  python3 tools/gen_signals.py
Legge:  data/RAMPINI_ELTRON_TERNI_corretto.dbc
Scrive: src/signals.js   ->   window.FMS_DB = { messages:[...], proprietaryPgns:[...] }
"""
import re, json, os, glob
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBC  = os.path.join(ROOT, 'data', 'RAMPINI_ELTRON_TERNI_corretto.dbc')
OUT  = os.path.join(ROOT, 'src', 'signals.js')


def pgn_of(boid):
    """Estrae (PGN, source address) dal CAN ID a 29 bit di una definizione BO_ J1939."""
    cid = boid & 0x1FFFFFFF
    pf = (cid >> 16) & 0xFF
    ps = (cid >> 8) & 0xFF
    dp = (cid >> 24) & 1
    edp = (cid >> 25) & 1
    pgn = (edp << 17) | (dp << 16) | (pf << 8) | (ps if pf >= 240 else 0)
    return pgn, cid & 0xFF


def parse():
    dbc = open(DBC, encoding='utf-8').read()
    msgs, cur = [], None
    for line in dbc.splitlines():
        m = re.match(r'\s*BO_ (\d+) (\w+)\s*:\s*(\d+)', line)
        if m:
            pgn, sa = pgn_of(int(m.group(1)))
            cur = {'name': m.group(2), 'pgn': pgn, 'sa': sa,
                   'dlc': int(m.group(3)), 'signals': [], 'comment': ''}
            msgs.append(cur)
            continue
        s = re.match(r'\s*SG_ (\w+)\s*(M|m\d+)?\s*:\s*(\d+)\|(\d+)@([01])([+-])\s*'
                     r'\(([^,]+),([^)]+)\)\s*\[([^|]*)\|([^\]]*)\]\s*"([^"]*)"', line)
        if s and cur is not None:
            mux = s.group(2) or ''
            cur['signals'].append({
                'name': s.group(1),
                'mux': ('M' if mux == 'M' else (int(mux[1:]) if mux else None)),
                'start': int(s.group(3)), 'len': int(s.group(4)),
                'order': int(s.group(5)), 'signed': s.group(6) == '-',
                'scale': float(s.group(7)), 'offset': float(s.group(8)),
                'unit': s.group(11)})

    # tabelle valori VAL_  (chiave: pgn + nome segnale)
    valt = {}
    for m in re.finditer(r'VAL_ (\d+) (\w+)\s+(.*?);', dbc):
        pgn, _ = pgn_of(int(m.group(1)))
        pairs = re.findall(r'(-?\d+)\s+"([^"]*)"', m.group(3))
        valt.setdefault((pgn, m.group(2)), {}).update({k: v for k, v in pairs})
    for msg in msgs:
        for sg in msg['signals']:
            vt = valt.get((msg['pgn'], sg['name']))
            if vt:
                sg['vt'] = vt

    # commenti CM_
    for m in re.finditer(r'CM_ SG_ (\d+) (\w+) "([^"]*)"', dbc):
        pgn, _ = pgn_of(int(m.group(1)))
        for msg in msgs:
            if msg['pgn'] == pgn:
                for sg in msg['signals']:
                    if sg['name'] == m.group(2):
                        sg['desc'] = m.group(3)
    for m in re.finditer(r'CM_ BO_ (\d+) "([^"]*)"', dbc):
        pgn, _ = pgn_of(int(m.group(1)))
        for msg in msgs:
            if msg['pgn'] == pgn:
                msg['comment'] = m.group(2)
    return msgs


def main():
    msgs = parse()
    out = {'messages': msgs, 'proprietaryPgns': [65280, 65281, 65282]}
    js = ("// AUTO-GENERATED da RAMPINI_ELTRON_TERNI_corretto.dbc — non modificare a mano.\n"
          "// Rigenera con: python3 tools/gen_signals.py\n"
          "window.FMS_DB = " + json.dumps(out, ensure_ascii=False) + ";\n")
    open(OUT, 'w', encoding='utf-8').write(js)
    print(f"OK: {len(msgs)} messaggi, "
          f"{sum(len(m['signals']) for m in msgs)} segnali -> {OUT}")

    # report di copertura opzionale sui dump presenti
    present = Counter()
    for f in sorted(glob.glob(os.path.join(ROOT, 'data', 'candump*.csv'))):
        with open(f) as fh:
            next(fh, None)
            for line in fh:
                p = line.rstrip('\n').split(',')
                if len(p) > 3 and p[2].isdigit() and p[3].isdigit():
                    present[int(p[2])] += 1
    if present:
        dbc_pgns = {m['pgn'] for m in msgs}
        print(f"Copertura: {len(dbc_pgns & set(present))}/{len(dbc_pgns)} PGN del DBC "
              f"presenti nei dump ({sum(present.values())} frame totali).")


if __name__ == '__main__':
    main()
