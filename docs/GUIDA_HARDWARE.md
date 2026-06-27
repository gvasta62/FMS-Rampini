# Guida — Primo collegamento hardware (dati live)

Come collegare un PC al bus **FMS** del veicolo e alimentare la dashboard in tempo reale,
con i comandi esatti per **Windows**, **Raspberry Pi** e **PC Linux**.

> ⚠️ **Sicurezza.** Collegarsi solo al **connettore FMS** (progettato per la lettura), in
> **modalità *listen-only*** (lettura passiva: non si trasmette nulla sul bus). L'intervento su un
> mezzo in esercizio va **autorizzato**. Verifica sul connettore FMS del veicolo i pin **CAN‑H**,
> **CAN‑L**, **GND** (la piedinatura dipende dal costruttore: chiedere a Rampini se non documentata).

Parametri del bus FMS: **CAN 2.0B / J1939**, **250 000 bit/s (250 kbit/s)**.

---

## 0. Cosa serve (riepilogo acquisti)

| PC | Adattatore consigliato | Costo | Driver/software |
|---|---|---|---|
| **Windows** | **PEAK PCAN‑USB** (consigliato) · in alternativa CANable 2.0 / Kvaser Leaf | €40–250 | driver dell'adattatore + `pip install python-can` (gratis) |
| **Linux / laptop** | Korlan USB2CAN · Innomaker · CANable 2.0 | €25–55 | nessuno (SocketCAN nativo) |
| **A bordo (fisso)** | **Raspberry Pi** + **CAN HAT** (PiCAN2/3) | €80–150 | nessuno (SocketCAN nativo) |

Software: **gratuito al 100%** (l'unico costo è l'adattatore).

---

## A. Windows (PEAK PCAN‑USB o CANable)

1. **Installa i driver dell'adattatore**
   - PEAK: driver da peak‑system.com (include `PCANBasic`).
   - CANable: di norma compare come **porta COM** (firmware *slcan*) — annota il numero COM in *Gestione dispositivi*.

2. **Installa Python e la libreria CAN** (una sola, gratuita)
   ```bat
   pip install python-can
   ```

3. **Collega l'adattatore** al connettore FMS (CAN‑H, CAN‑L, GND).

4. **Trova il canale** (facoltativo)
   - PEAK: di solito `PCAN_USBBUS1` (verifica con *PCAN‑View*).
   - CANable/slcan: il numero **COM** (es. `COM3`).

5. **Avvia l'agente** (nella cartella del progetto)
   ```bat
   :: PEAK PCAN-USB
   python tools\live_agent.py --source can --backend pythoncan --can-interface pcan --iface PCAN_USBBUS1 --bitrate 250000

   :: CANable (slcan su COM3)
   python tools\live_agent.py --source can --backend pythoncan --can-interface slcan --iface COM3 --bitrate 250000

   :: per salvare anche su file mentre cattura, aggiungi:  --save cattura_2026-06-27.csv
   ```

6. **Apri la dashboard in locale** (per evitare blocchi "mixed content" della versione https):
   ```bat
   python -m http.server 8000
   ```
   poi nel browser `http://localhost:8000/src/index.html` → barra **«Dati in tempo reale»** →
   **Connetti live** (`ws://localhost:8770`).

7. **Salva il dump**: scrivi il nome nel campo e premi **«Salva dump CSV»**.

---

## B. Raspberry Pi + CAN HAT (PiCAN2/3) — installazione fissa a bordo

1. **Monta il HAT** sui GPIO e collega **CAN‑H / CAN‑L / GND** al connettore FMS.

2. **Abilita SPI e l'overlay CAN** in `/boot/firmware/config.txt` (o `/boot/config.txt` su versioni vecchie):
   ```ini
   dtparam=spi=on
   dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
   ```
   > Il valore `oscillator` dipende dalla scheda: **PiCAN2 = 16000000** (16 MHz); alcune varianti usano 8 MHz. Controlla il quarzo del tuo HAT.

3. **Riavvia**:
   ```bash
   sudo reboot
   ```

4. **Attiva l'interfaccia a 250 kbit/s, solo ascolto**
   ```bash
   sudo ip link set can0 up type can bitrate 250000 listen-only on
   ```
   (in alternativa lascia fare all'agente: aggiungi `--up --listen-only` al comando del punto 6).

5. **Verifica i frame grezzi** (facoltativo):
   ```bash
   sudo apt install can-utils
   candump can0          # devono scorrere i frame del bus
   ```

6. **Avvia l'agente**
   ```bash
   python3 tools/live_agent.py --source can --iface can0 --bitrate 250000 --listen-only --save cattura.csv
   ```

7. **Apri la dashboard** (sul Pi o da un altro PC):
   - sul Pi: `python3 -m http.server 8000` → `http://localhost:8000/src/index.html`
   - da un altro PC sulla stessa rete: apri la dashboard in locale e in **Connetti live** usa `ws://<IP-del-Pi>:8770`
     (l'agente è in ascolto su tutte le interfacce). Trova l'IP con `hostname -I`.

---

## C. PC Linux + adattatore USB‑CAN

- **Adattatori SocketCAN nativi** (Korlan USB2CAN, Innomaker gs_usb):
  ```bash
  sudo ip link set can0 up type can bitrate 250000 listen-only on
  python3 tools/live_agent.py --source can --iface can0 --listen-only --save cattura.csv
  ```
- **CANable con firmware slcan** (compare come `/dev/ttyACM0`):
  ```bash
  sudo slcand -o -c -s5 /dev/ttyACM0 can0   # -s5 = 250 kbit/s
  sudo ip link set can0 up
  python3 tools/live_agent.py --source can --iface can0 --save cattura.csv
  ```

---

## Verifica e risoluzione problemi

| Sintomo | Causa probabile / rimedio |
|---|---|
| Nessun frame in dashboard | bitrate diverso da **250000**; CAN‑H/CAN‑L invertiti; manca GND; non in *listen-only* |
| `RTNETLINK: Operation not permitted` | manca `sudo` sui comandi `ip link` |
| `candump can0` non mostra nulla | interfaccia non attiva o cablaggio errato; ricontrolla i punti 4–5 |
| La dashboard https non si connette a `ws://localhost` | apri la dashboard **in locale** (`http://localhost:8000/...`) per evitare il blocco *mixed content* |
| Backend `python-can` assente | `pip install python-can` |
| Elenco interfacce | `python3 tools/live_agent.py --list` |

Il file salvato (`.csv`) è in **formato candump** ed è **ricaricabile** nella dashboard
(«Carica file CSV») o utilizzabile con gli strumenti del progetto.
