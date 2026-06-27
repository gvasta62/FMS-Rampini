#!/usr/bin/env python3
"""Agente live FMS-Rampini — legge il bus CAN (o riproduce i dump) e streama
i frame J1939 via WebSocket alla dashboard, che li decodifica in tempo reale.

ZERO dipendenze esterne: solo la libreria standard di Python
 - lettura bus reale via SocketCAN nativo (socket.PF_CAN), su Linux
 - server WebSocket implementato a mano (handshake + framing)

USO
  # Riproduzione dei dump in tempo reale (per provare senza hardware):
  python3 tools/live_agent.py --source replay --speed 1 --loop

  # Lettura dal bus reale (Raspberry Pi/PC con interfaccia CAN configurata):
  #   sudo ip link set can0 type can bitrate 250000 listen-only on
  #   sudo ip link set up can0
  python3 tools/live_agent.py --source can --iface can0

Poi nella dashboard: «Connetti live» su  ws://<indirizzo-agente>:8770
"""
import argparse, asyncio, base64, glob, hashlib, json, os, struct, time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
CLIENTS = set()                      # StreamWriter dei browser connessi
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    out = bytearray([0x81])           # FIN + opcode testo
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
        if not chunk:
            return False
        data += chunk
        if len(data) > 65536:
            return False
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
    print(f"[ws] client connesso: {peer}  (totale {len(CLIENTS)})")
    try:
        while await reader.read(1024):   # ignora i frame in ingresso, rileva la chiusura
            pass
    except Exception:
        pass
    finally:
        CLIENTS.discard(writer)
        try:
            writer.close()
        except Exception:
            pass
        print(f"[ws] client disconnesso: {peer}  (totale {len(CLIENTS)})")


async def broadcast(obj):
    if not CLIENTS:
        return
    msg = ws_encode(json.dumps(obj, separators=(',', ':')))
    for w in list(CLIENTS):
        try:
            w.write(msg)
        except Exception:
            CLIENTS.discard(w)


# ---------------------------------------------------------------- sorgenti
async def source_replay(speed, loop_forever, data_dir):
    """Riproduce i candump *.csv rispettando i delta temporali (× speed)."""
    rows = []
    for f in sorted(glob.glob(os.path.join(data_dir, "candump*.csv"))):
        with open(f) as fh:
            next(fh, None)
            for line in fh:
                c = line.rstrip("\n").split(",")
                if len(c) > 6 and c[2].isdigit() and c[3].isdigit() and c[4].isdigit():
                    rows.append((int(c[4]), int(c[2]), int(c[3]), c[6]))
    rows.sort(key=lambda r: r[0])
    if not rows:
        print("[replay] nessun frame trovato in", data_dir); return
    print(f"[replay] {len(rows)} frame · velocità ×{speed} · loop={loop_forever}")
    while True:
        prev = rows[0][0]
        for ts0, pgn, src, val in rows:
            dt = (ts0 - prev) / 1000.0 / speed
            if dt > 0:
                await asyncio.sleep(min(dt, 0.5))
            prev = ts0
            await broadcast({"pgn": pgn, "source": src,
                             "ts": int(time.time() * 1000), "d": val})
        if not loop_forever:
            print("[replay] fine."); return


async def source_can(iface):
    """Legge i frame dal bus reale via SocketCAN nativo (solo Linux)."""
    import socket
    sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((iface,))
    sock.setblocking(False)
    loop = asyncio.get_event_loop()
    print(f"[can] in ascolto su {iface} (listen-only consigliato)")
    while True:
        frame = await loop.sock_recv(sock, 16)
        if len(frame) < 16:
            continue
        can_id, dlc = struct.unpack_from("<IB", frame, 0)
        data = frame[8:8 + min(dlc, 8)]
        pgn, src = pgn_source(can_id & 0x1FFFFFFF)
        await broadcast({"pgn": pgn, "source": src,
                         "ts": int(time.time() * 1000), "d": data.hex()})


# ---------------------------------------------------------------- main
async def main():
    ap = argparse.ArgumentParser(description="Agente live FMS-Rampini")
    ap.add_argument("--source", choices=["replay", "can"], default="replay")
    ap.add_argument("--iface", default="can0", help="interfaccia CAN (modo can)")
    ap.add_argument("--speed", type=float, default=1.0, help="velocità replay")
    ap.add_argument("--loop", action="store_true", help="replay in loop")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    args = ap.parse_args()

    server = await asyncio.start_server(handle_client, args.host, args.port)
    print(f"[ws] WebSocket in ascolto su ws://{args.host}:{args.port}")
    if args.source == "replay":
        producer = source_replay(args.speed, args.loop, args.data)
    else:
        producer = source_can(args.iface)
    async with server:
        await asyncio.gather(server.serve_forever(), producer)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrotto.")
