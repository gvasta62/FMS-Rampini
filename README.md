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

L'agente legge il bus via **SocketCAN nativo** e streama i frame J1939 (`{pgn,source,ts,d}`) via **WebSocket**;
la dashboard li decodifica con lo stesso `decoder.js` e aggiorna tabelle e grafici su una **finestra scorrevole di 5 minuti**, con riconnessione automatica.

**Hardware per leggere il bus FMS** (CAN J1939, 250 kbit/s, connettore FMS, *listen-only* consigliato):
adattatore USB-CAN (PEAK/Kvaser) per PC, oppure Raspberry Pi + CAN HAT (PiCAN2/3) per una soluzione fissa a bordo.

## Documentazione e materiali
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
