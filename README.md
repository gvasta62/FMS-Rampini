# FMS-Rampini — Dashboard dump bus FMS

🔗 **Dashboard online:** https://gvasta62.github.io/FMS-Rampini/

Dashboard web statica (HTML/CSS/JS vanilla, **nessuna dipendenza**) per leggere in modo chiaro tutti
i dati contenuti in uno o più **dump del canale FMS** (CAN J1939) di un autobus elettrico
**Rampini Eltron** (deposito di Terni, Busitalia).

I frame CAN grezzi vengono decodificati con la "chiave" del DBC del costruttore e presentati come
grandezze fisiche con statistiche e grafici temporali.

## Avvio rapido

**Opzione A — apri il file** (più semplice):
1. Apri `src/index.html` nel browser.
2. Trascina i file `data/candump (18..23).csv` nella dashboard (o «Carica file CSV»).

**Opzione B — web server** (abilita anche l'auto-caricamento):
```bash
cd FMS-Rampini
python3 -m http.server 8000
# poi apri  http://localhost:8000/src/index.html  e premi "Auto-carica data/"
```

## Cosa mostra
- **Grandezze**: tabella di tutte le grandezze decodificate (ultimo valore, min/media/max, n. campioni,
  N/A), con filtro testuale e grafico temporale per ogni segnale.
- **Messaggi**: i messaggi CAN presenti (PGN, descrizione, frame, frequenza Hz, source), più l'elenco
  dei messaggi del DBC mai trasmessi in questi dump.
- **Grafico**: andamento temporale di una o più grandezze a confronto (max 8), con tooltip.
- Grandezza **derivata** `Potenza istantanea = Vpack × IPack` da BMS_STAT1 (~4 Hz), più reattiva del
  `BatteryPower` di BMS_ENERGY (0,08 Hz).

## Modalità live (dati in tempo reale)
La dashboard può ricevere i frame **in diretta** dal bus FMS, oltre che da file.

1. Avvia l'**agente** (legge il bus o riproduce i dump) — solo libreria standard Python, nessuna dipendenza:
   ```bash
   # Prova senza hardware: riproduce i dump in tempo reale
   python3 tools/live_agent.py --source replay --loop

   # Bus reale (Raspberry Pi/PC con interfaccia CAN configurata):
   #   sudo ip link set can0 type can bitrate 250000 listen-only on && sudo ip link set up can0
   python3 tools/live_agent.py --source can --iface can0
   ```
2. Nella dashboard, nella barra **«Dati in tempo reale»**, premi **Connetti live** (URL agente, default `ws://localhost:8770`).

L'agente legge il bus via **SocketCAN nativo** e streama i frame J1939 (`{id,pgn,source,ts,d}`) via **WebSocket**;
la dashboard li decodifica con lo stesso `decoder.js` e aggiorna tabelle e grafici su una **finestra scorrevole di 5 minuti**, con riconnessione automatica.

### Salvare il dump catturato live (con nome a scelta)
- **Dal browser:** in modalità live, scrivi il **nome file** nel campo accanto e premi **«Salva dump CSV»** → scarica un
  file `candump`-compatibile (`hexCanId,canId,pgn,source,timestamp,iface,value,willBeFiltered`), **ricaricabile** nella dashboard stessa.
- **Dall'agente (sul PC che cattura):** aggiungi `--save NOMEFILE.csv` al comando.

### Configurazione hardware (nell'agente)
```bash
python3 tools/live_agent.py --list                 # elenca le interfacce CAN
# Linux/SocketCAN (nativo, zero dipendenze):
python3 tools/live_agent.py --source can --iface can0 --bitrate 250000 --listen-only --up
# Windows o adattatori PEAK/Kvaser/CANable (backend python-can, free: pip install python-can):
python3 tools/live_agent.py --source can --backend pythoncan --can-interface pcan --iface PCAN_USBBUS1 --bitrate 250000
```
Parametri: `--bitrate` (FMS = 250000), `--listen-only`, `--up` (Linux: configura e attiva l'interfaccia, root), `--iface`/`--can-interface`.

📘 **Guida passo-passo al primo collegamento hardware** (Windows / Raspberry Pi / Linux, con i comandi esatti):
[`docs/GUIDA_HARDWARE.md`](docs/GUIDA_HARDWARE.md)

**Hardware consigliato** (CAN J1939, 250 kbit/s, connettore FMS, *listen-only*):
- **Linux/Raspberry Pi** → adattatore USB-CAN SocketCAN (es. **Korlan USB2CAN**, **Innomaker**, **CANable 2.0**) o **CAN HAT** (PiCAN2/3): l'agente funziona **senza dipendenze**.
- **PC Windows** → **PEAK PCAN-USB** (consigliato) o **Kvaser Leaf** / **CANable**: usa il backend `python-can` (una sola libreria gratuita).

## Documentazione e materiali
- 🎬 **Presentazione (Gamma)** — keynote del progetto: https://gamma.app/docs/sen9ik1pnpck0kq (esportabile in PDF/PPTX dall'editor: Share → Export)
- 📄 **Relazione dettagliata** del progetto: [`docs/RELAZIONE_PROGETTO.md`](docs/RELAZIONE_PROGETTO.md)
- 📊 **Infografica** di tutte le grandezze: [`docs/infografica.html`](docs/infografica.html) · online: https://gvasta62.github.io/FMS-Rampini/docs/infografica.html (anteprima PNG: `docs/infografica.png`)
- 🖥️ **Slide** (deck navigabile con le frecce): [`docs/slide.html`](docs/slide.html) · online: https://gvasta62.github.io/FMS-Rampini/docs/slide.html
- 🗂️ **Catalogo grandezze** (dati grezzi): [`docs/catalogo_grandezze.json`](docs/catalogo_grandezze.json)
- 📚 Analisi tecnica originale: `docs/Analisi_FMS_Rampini_Eltron.docx`, `docs/Analisi_Dump_Esteso_FMS.docx`

## Struttura
```
FMS-Rampini/
├── src/       index.html, styles.css, signals.js (auto-gen), decoder.js, chart.js, app.js
├── data/      candump (18..23).csv  +  RAMPINI_ELTRON_TERNI_corretto.dbc  +  manifest.json
├── docs/      RELAZIONE_PROGETTO.md, infografica.html/.png, slide.html, catalogo_grandezze.json, analisi .docx
├── tools/     gen_signals.py (DBC→signals.js)  ·  gen_presentation.py (catalogo→infografica/slide)
├── index.html (pagina indice/landing con i link agli strumenti) · .nojekyll
├── README.md
└── CLAUDE.md
```

## Piano (com'è stato costruito)
1. **Analisi dump + DBC**: capito il formato `candump` (PGN/source/timestamp/value hex) e parsato il
   DBC (61 messaggi, 171 segnali) verificando che i PGN calcolati coincidano con la documentazione.
2. **Generazione DB segnali** (`tools/gen_signals.py` → `src/signals.js`): per ogni messaggio PGN,
   source, DLC, segnali (bit start/len, endianness, segno, scala, offset, unità, tabelle valori,
   commenti, multiplexing).
3. **Decoder J1939** (`decoder.js`): parsing CSV veloce, estrazione bit con BigInt (Intel/Motorola),
   gestione segno/scala/offset, value-table, multiplexing, regola dei **PGN proprietari** (solo
   source 30), scelta della definizione per source sui PGN condivisi.
4. **Aggregazione + UI** (`app.js`): unione di più dump per timestamp, statistiche per segnale e per
   messaggio, segnali derivati, tabelle filtrabili, selettore grafico multi-segnale.
5. **Grafici** (`chart.js`): line chart su canvas con assi, griglia, decimazione e tooltip.

## Generare o adattare il DBC di un mezzo (reverse-DBC)
Lo strumento `tools/dbc_from_dump.py` usa i dump per **costruire o adattare un DBC** di un nuovo veicolo.
Quattro modalità:

```bash
# Inventario di tutti i messaggi presenti + analisi byte (costante / contatore / enum / analogico):
python3 tools/dbc_from_dump.py inventory --data data --out docs/dump_inventory.md

# Scheletro DBC: segnali STANDARD completi per i PGN J1939 noti (dal seed) +
# placeholder per-byte sui PGN proprietari, con commenti-indizio:
python3 tools/dbc_from_dump.py skeleton --data data --out nuovo_mezzo.dbc

# Adatta un DBC esistente al mezzo: rimappa i source che il dump conferma,
# segnala come AMBIGUI i PGN proprietari condivisi (da verificare col costruttore):
python3 tools/dbc_from_dump.py remap --dbc esistente.dbc --data data --out rimappato.dbc

# (una tantum) crea il seed standard estraendo i PGN < 0xFF00 da un DBC:
python3 tools/dbc_from_dump.py makeseed --dbc data/RAMPINI_ELTRON_TERNI_corretto.dbc --out data/fms_standard_seed.dbc
```

**Flusso tipico** per un mezzo nuovo:
1. cattura un dump (live o fornito dal costruttore);
2. `inventory` per vedere cosa trasmette; `skeleton` per partire da un DBC pre-popolato sugli standard;
3. rifinisci a mano i segnali **proprietari** (gli unici che il dato da solo non rivela) usando i commenti-indizio;
4. `python3 tools/gen_signals.py` + ricarica la dashboard per **validare** i valori (plausibilità fisica).

> I segnali **FMS standard** si ricavano automaticamente; i **proprietari** (PGN 0xFF00–0xFFFF) richiedono i documenti del costruttore — il dump aiuta solo a ipotizzarli e la dashboard a validarli.

## Rigenerare il DB segnali dal DBC
Se il DBC cambia:
```bash
python3 tools/gen_signals.py
```

## Note di dominio (vedi `docs/`)
- Velocità affidabile su **CCVS/WheelBasedSpeed** (PGN 65265) e TCO1 (65132).
- `BatteryPower` ha già la scala corretta (−2) nel DBC; trasmesso però a sola 0,08 Hz.
- Contatori `EnergyOut`/`EnergyCharged` possono restare a 0 (non popolati dal BMS).
- La posizione **GPS non transita sul FMS**: la fornisce il modulo telematico.
