#!/usr/bin/env python3
"""Agente live FMS-Rampini — legge il bus CAN (o riproduce i dump) e streama
i frame J1939 via WebSocket alla dashboard, che li decodifica in tempo reale.

Libreria standard di Python per il percorso nativo (Linux/SocketCAN); su Windows
o con adattatori non-SocketCAN si usa il backend opzionale `python-can` (free).

ESEMPI
  # Prova senza hardware: riproduce i dump in tempo reale
  python3 tools/live_agent.py --source replay --loop

  # Bus reale su Linux (SocketCAN nativo, nessuna dipendenza):
  python3 tools/live_agent.py --source can --iface can0 --bitrate 250000 --up --listen-only

  # Bus reale su Windows / adattatore PEAK/Kvaser/CANable (python-can):
  python3 tools/live_agent.py --source can --backend pythoncan --can-interface pcan --iface PCAN_USBBUS1 --bitrate 250000

  # Salvare la cattura su file mentre si streama:
  python3 tools/live_agent.py --source can --iface can0 --save cattura_2026-06-27.csv

  # Elenco interfacce CAN disponibili:
  python3 tools/live_agent.py --list

Poi nella dashboard: «Connetti live» su  ws://<indirizzo-agente>:8770
"""
import argparse, asyncio, base64, glob, hashlib, json, os, struct, subprocess, sys, time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
CLIENTS = set()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_FH = None                          # file di registrazione opzionale


# ---------------------------------------------------------------- J1939
def pgn_source(cid29):
    """Da CAN ID a 29 bit -> (PGN, source address)."""
    pf = (cid29 >> 16) & 0xFF
    ps = (cid29 >> 8) & 0xFF
    dp = (cid29 >> 24) & 1
    edp = (cid29 >> 25) & 1
    pgn = (edp << 17) | (dp << 16) | (pf << 8) | (ps if pf >= 240 else 0)
    return pgn, cid29 & 0xFF


# ---------------------------------------------------------------- WebSocket
def ws_encode(text):
    payload = text.encode('utf-8')
    out = bytearray([0x81])
    n = len(payload)
    if n < 126:
        out.append(n)
    elif n < 65536:
        out.append(126); out += struct.pack(">H", n)
    else:
        out.append(127); out += struct.pack(">Q", n)
    out += payload
    return bytes(out)


async def ws_handshake(reader, writer):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(1024)
        if not chunk or len(data) > 65536:
            return False
        data += chunk
    key = None
    for line in data.decode('latin1').split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()
    if not key:
        return False
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    writer.write(("HTTP/1.1 101 Switching Protocols\r\n"
                  "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
    await writer.drain()
    return True


async def handle_client(reader, writer):
    peer = writer.get_extra_info('peername')
    if not await ws_handshake(reader, writer):
        writer.close(); return
    CLIENTS.add(writer)
    print(f"[ws] client connesso: {peer}  (totale {len(CLIENTS)})", flush=True)
    try:
        while await reader.read(1024):
            pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(writer)
        try:
            writer.close()
        except Exception:
            pass
        print(f"[ws] client disconnesso: {peer}  (totale {len(CLIENTS)})", flush=True)


async def emit(item):
    """Invia il frame ai client WebSocket e, se attivo, lo scrive su file."""
    if CLIENTS:
        msg = ws_encode(json.dumps(item, separators=(',', ':')))
        for w in list(CLIENTS):
            try:
                w.write(msg)
            except Exception:
                CLIENTS.discard(w)
    if SAVE_FH is not None:
        cid = item.get("id", "")
        canid = int(cid, 16) if cid else ""
        SAVE_FH.write(f'{cid},{canid},{item["pgn"]},{item["source"]},'
                      f'{item["ts"]},live,{item["d"]},false\n')


# ---------------------------------------------------------------- setup hardware
def list_interfaces():
    print("Interfacce CAN disponibili (Linux/SocketCAN):")
    try:
        subprocess.run(["ip", "-details", "link", "show", "type", "can"], check=False)
    except FileNotFoundError:
        print("  comando 'ip' non disponibile (sistema non-Linux?).")
    print("\nCon backend python-can elenca i canali con:  python3 -m can.viewer -i <interface> -L"
          "  oppure consulta la documentazione dell'adattatore.")


def setup_interface(iface, bitrate, listen_only):
    """Configura e attiva l'interfaccia SocketCAN (richiede privilegi root)."""
    lo = "on" if listen_only else "off"
    cmds = [
        ["ip", "link", "set", iface, "down"],
        ["ip", "link", "set", iface, "type", "can", "bitrate", str(bitrate), "listen-only", lo],
        ["ip", "link", "set", iface, "up"],
    ]
    print(f"[setup] {iface} @ {bitrate} bit/s, listen-only {lo}")
    for c in cmds:
        print("  $", " ".join(c))
        r = subprocess.run(c, check=False)
        if r.returncode != 0 and c[-1] != "down":
            print("  ⚠️  comando fallito — servono privilegi root? (riprova con sudo)")


# ---------------------------------------------------------------- sorgenti
async def source_replay(speed, loop_forever, data_dir):
    rows = []
    for f in sorted(glob.glob(os.path.join(data_dir, "candump*.csv"))):
        with open(f) as fh:
            next(fh, None)
            for line in fh:
                c = line.rstrip("\n").split(",")
                if len(c) > 6 and c[2].isdigit() and c[3].isdigit() and c[4].isdigit():
                    rows.append((int(c[4]), c[0], int(c[2]), int(c[3]), c[6]))
    rows.sort(key=lambda r: r[0])
    if not rows:
        print("[replay] nessun frame in", data_dir); return
    print(f"[replay] {len(rows)} frame · ×{speed} · loop={loop_forever}", flush=True)
    while True:
        prev = rows[0][0]
        for ts0, cid, pgn, src, val in rows:
            dt = (ts0 - prev) / 1000.0 / speed
            if dt > 0:
                await asyncio.sleep(min(dt, 0.5))
            prev = ts0
            await emit({"id": cid, "pgn": pgn, "source": src,
                        "ts": int(time.time() * 1000), "d": val})
        if not loop_forever:
            print("[replay] fine.", flush=True); return


async def source_can_native(iface):
    import socket
    sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((iface,))
    sock.setblocking(False)
    loop = asyncio.get_event_loop()
    print(f"[can] SocketCAN nativo in ascolto su {iface}", flush=True)
    while True:
        frame = await loop.sock_recv(sock, 16)
        if len(frame) < 16:
            continue
        can_id, dlc = struct.unpack_from("<IB", frame, 0)
        cid = can_id & 0x1FFFFFFF
        data = frame[8:8 + min(dlc, 8)]
        pgn, src = pgn_source(cid)
        await emit({"id": "%08X" % cid, "pgn": pgn, "source": src,
                    "ts": int(time.time() * 1000), "d": data.hex()})


async def source_can_pythoncan(args):
    try:
        import can
    except ImportError:
        sys.exit("Backend python-can non installato. Esegui:  pip install python-can")
    import threading
    bus = can.Bus(interface=args.can_interface, channel=args.iface,
                  bitrate=args.bitrate, receive_own_messages=False)
    loop = asyncio.get_event_loop()
    q = asyncio.Queue()
    print(f"[can] python-can ({args.can_interface}) su {args.iface} @ {args.bitrate} bit/s", flush=True)

    def reader():
        for msg in bus:
            cid = msg.arbitration_id & 0x1FFFFFFF
            pgn, src = pgn_source(cid)
            loop.call_soon_threadsafe(q.put_nowait, {
                "id": "%08X" % cid, "pgn": pgn, "source": src,
                "ts": int(time.time() * 1000), "d": bytes(msg.data).hex()})
    threading.Thread(target=reader, daemon=True).start()
    while True:
        await emit(await q.get())


# ---------------------------------------------------------------- main
async def run(args):
    server = await asyncio.start_server(handle_client, args.host, args.port)
    print(f"[ws] WebSocket in ascolto su ws://{args.host}:{args.port}", flush=True)
    if args.source == "replay":
        producer = source_replay(args.speed, args.loop, args.data)
    elif args.backend == "pythoncan":
        producer = source_can_pythoncan(args)
    else:
        if args.up:
            setup_interface(args.iface, args.bitrate, args.listen_only)
        producer = source_can_native(args.iface)
    async with server:
        await asyncio.gather(server.serve_forever(), producer)


def main():
    ap = argparse.ArgumentParser(description="Agente live FMS-Rampini")
    ap.add_argument("--source", choices=["replay", "can"], default="replay")
    ap.add_argument("--backend", choices=["socketcan", "pythoncan"], default="socketcan",
                    help="socketcan = nativo Linux; pythoncan = Windows/altri adattatori")
    ap.add_argument("--iface", default="can0", help="interfaccia/canale CAN")
    ap.add_argument("--can-interface", default="socketcan",
                    help="(python-can) tipo: pcan, kvaser, vector, slcan, ...")
    ap.add_argument("--bitrate", type=int, default=250000, help="bit/s (FMS = 250000)")
    ap.add_argument("--listen-only", action="store_true", help="modo solo-ascolto (consigliato)")
    ap.add_argument("--up", action="store_true", help="(Linux) configura e attiva l'interfaccia (root)")
    ap.add_argument("--list", action="store_true", help="elenca le interfacce CAN ed esce")
    ap.add_argument("--save", metavar="FILE.csv", help="registra la cattura su file (formato candump)")
    ap.add_argument("--speed", type=float, default=1.0, help="velocità replay")
    ap.add_argument("--loop", action="store_true", help="replay in loop")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    args = ap.parse_args()

    if args.list:
        list_interfaces(); return

    global SAVE_FH
    if args.save:
        SAVE_FH = open(args.save, "w", buffering=1)
        SAVE_FH.write("hexCanId,canId,pgn,source,timestamp,iface,value,willBeFiltered\n")
        print(f"[save] registrazione su {args.save}", flush=True)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrotto.")
    finally:
        if SAVE_FH:
            SAVE_FH.close()
            print(f"[save] file chiuso: {args.save}")


if __name__ == "__main__":
    main()
