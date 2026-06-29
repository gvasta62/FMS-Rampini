# FMS-Rampini — Dashboard dump bus FMS (Rampini Eltron elettrico)

## Cos'è
Progetto **web statico** (HTML + CSS + JavaScript vanilla, **zero dipendenze, zero build**) per
leggere e presentare in modo chiaro tutti i dati contenuti in uno o più **dump del canale FMS**
(CAN J1939) registrati su un autobus elettrico **Rampini Eltron** del deposito di Terni (Busitalia).

La dashboard prende i frame CAN grezzi, li decodifica con la "chiave" del file DBC del costruttore
e mostra le grandezze fisiche (tensioni, correnti, temperature, velocità, SoC, energie, diagnostica…)
con statistiche e grafici temporali.

## Stack
- **HTML5 / CSS3 / JavaScript ES6** puro. Nessun framework, nessun bundler, nessuna CDN.
- Grafici resi con un **renderer canvas custom** (`src/chart.js`) — niente librerie esterne, funziona offline.
- Deve funzionare aprendo `src/index.html` in un browser, oppure servendo la cartella con un web server.

## Struttura
```
FMS-Rampini/
├── src/
│   ├── index.html      # pagina dashboard
│   ├── styles.css      # stile
│   ├── signals.js      # DB segnali AUTO-GENERATO dal DBC (window.FMS_DB) — NON modificare a mano
│   ├── decoder.js      # parsing CSV + decodifica J1939 (BigInt, Intel/Motorola, mux, PGN proprietari)
│   ├── chart.js        # line chart su canvas, con assi e tooltip
│   └── app.js          # orchestrazione UI, aggregazione, rendering
├── data/
│   ├── candump (18..23).csv          # i dump (6 file in questo dataset)
│   └── RAMPINI_ELTRON_TERNI_corretto.dbc   # DBC sorgente da cui si rigenera signals.js
├── docs/               # analisi (.docx), RELAZIONE_PROGETTO.md, catalogo_grandezze.json,
│                       #   infografica.html/.png, slide.html
└── tools/
    ├── gen_signals.py       # rigenera src/signals.js dal DBC
    ├── gen_presentation.py  # rigenera docs/infografica.html e docs/slide.html dal catalogo
    ├── live_agent.py        # agente live: legge il bus CAN (o riproduce i dump) -> WebSocket
    └── dbc_from_dump.py     # reverse-DBC: inventory / skeleton / remap / makeseed
```
Seed standard: `data/fms_standard_seed.dbc` (PGN < 0xFF00 J1939, riusabile per altri mezzi).

## Reverse-DBC (dal dump al DBC)
`tools/dbc_from_dump.py` costruisce/adatta il DBC di un mezzo dai dump:
`inventory` (messaggi presenti + analisi byte: costante/contatore/enum/analogico),
`skeleton` (DBC con segnali standard dal seed per i PGN noti + placeholder per-byte sui proprietari),
`remap` (adatta un DBC esistente rimappando solo i source univoci e sicuri; i PGN proprietari condivisi
restano AMBIGUI da verificare col costruttore), `makeseed` (estrae i PGN standard < 0xFF00 in un seed).
La decodifica resta a senso inverso (DBC → dashboard); questo strumento è il senso DBC←dump.

## Modalità live
`tools/live_agent.py` (solo stdlib) legge il bus via **SocketCAN nativo** (`socket.PF_CAN`) o
**riproduce i dump** (`--source replay`) e streama i frame J1939 `{pgn,source,ts,d:"hex"}` via
**WebSocket** (server fatto a mano, nessuna dipendenza). La dashboard (`app.js`) ha una **modalità
Live**: si connette via `new WebSocket()`, decodifica ogni frame con lo stesso `decoder.js`
(esposto `hexToBytes`) e mantiene una **finestra scorrevole di 5 min** ricalcolando le statistiche a
ogni tick (1 Hz), con riconnessione automatica. La modalità a file (CSV) resta invariata.

## Formato dei dump (candump *.csv)
Header: `hexCanId,canId,pgn,source,timestamp,iface,value,willBeFiltered`
- `pgn` — Parameter Group Number J1939 (intero) → identifica il **tipo di messaggio**.
- `source` — indirizzo della centralina trasmittente (ultimo byte del CAN ID).
- `timestamp` — epoch in **millisecondi**.
- `value` — payload, fino a 8 byte in **esadecimale** (es. `95301786abac0000`).
- Il numero `(N)` nel nome file è solo la sequenza di cattura; l'ordine reale si ricava dal `timestamp`.

## Regole di decodifica (IMPORTANTI — dal confronto DBC vs bus reale)
1. **Match per PGN con priorità al source** (`decoder.js` → `pickMsg`):
   - PGN condivisi documentati `65280/65281/65282` (0xFF00/01/02): **solo source 30 (BMS)** →
     BMS_V/BMS_T/BMS_STAT1; gli altri source (208, 73, 22, 42…) sono **ignorati** anche se
     definiti nel DBC, altrimenti sovrascrivono i dati batteria.
   - Altrimenti si preferisce sempre il **match esatto `(PGN, source)`** (es. RHCV@6, EVCU2@39,
     DM01_ECAS@47).
   - Altri PGN proprietari `≥ 0xFF00`: **nessun fallback per solo-PGN** (zona di collisione
     indirizzi) → un source non riconosciuto è spurio e va scartato. Questo esclude p.es.
     BMS_STAT2/BMS_DIAG da source 208/39/40 senza perdere messaggi legittimi.
   - PGN standard `< 0xFF00` a definizione unica: **recupero per solo-PGN** (il source del DBC
     poteva essere ereditato da un template diesel).
2. **Messaggi multipli sullo stesso PGN** (es. DM1 su 65226: BMS/RHCV/ECAS): coperti dal match
   esatto per source di cui sopra.
4. **Endianness**: `@1` = Intel/little-endian (quasi tutti), `@0` = Motorola/big-endian.
   Segnali fino a 32 bit → usare **BigInt** per shift/mask sicuri.
5. **Segnali con segno** (`-`): complemento a due su `len` bit.
6. **N/A**: payload tutto `0xFF`, oppure raw che la value-table mappa a "N.A" → escluso dalle statistiche.
7. **Multiplexing**: messaggi con selettore `M` (es. RHCV_Mux): includere i segnali senza mux
   più quelli del gruppo `m<val>` pari al valore del selettore.

## Note di dominio (dai documenti in docs/)
- `BatteryPower` (BMS_ENERGY) ha scala già invertita a `-2` nel DBC corretto; il messaggio è a 0,08 Hz.
  La **potenza istantanea** è meglio derivarla come `P = Vpack × IPack` da BMS_STAT1 (~4 Hz).
- Velocità affidabile: **CCVS/WheelBasedSpeed** (PGN 65265) e TCO1/TachoVehicleSpeed (65132).
- Contatori `EnergyOut`/`EnergyCharged` (BMS_ENERGY) restano a 0 (non popolati dal BMS): è un limite del dato, non della dashboard.
- La posizione GPS **non** transita sul FMS (la fornisce il modulo telematico).

## Stato confronto con Rampini (R1–R12) — giugno 2026
- R1–R6: recepiti (rimappamenti source + correzioni scala già nel DBC).
- **R7**: PGN 65310 (`PCU_BMS`) → IGNORE. Nel dump esteso arriva da source 40/58/59, non da 62.
- **R8a / R9**: in attesa analisi Rampini sul dump esteso (inviato).
- **R8b**: `BMS_LCD_STAT` (PGN 65296) → IGNORE. Nel dump compare solo su source 39 (Multiplex TEQ), mai su 30 (BMS).
- **R10**: anagrafica nodi `BU_` aggiunta al DBC con commenti `CM_ BU_`. Source: BMS 0x1E, Cond.batt 0x3A, Gateway DANA 0xD0, Clima 0x06, Multiplex TEQ 0x27, Interf.impianti 0x28.
- **R11**: resto DBC ok; segnali non elencati ignorabili. Nessuna modifica strutturale.
- **R12**: posizione via modulo telematico, non CAN. Confermato.
- **Frequenza BMS (dump esteso, src 30)**: BMS_V/T/STAT1/STAT2 ~4,2 Hz; **BMS_ENERGY 0,08 Hz** (mediana 5,67 s). Conferma il "~5 s" del costruttore: non è sottocampionamento.
- **Bug DBC preesistente**: segnale `FMI1_ECAS` eccede `DM01_ECAS` → blocca parsing strict di cantools (la dashboard JS lo tollera). Da correggere a parte.
- **Punti aperti Onell/ChargePoint**: widget velocità da rimappare su CCVS (65265); segno potenza da correggere lato calcolo P=V×I.

## Convenzioni di lavoro
- `signals.js` è **generato**: per modificarlo si edita il DBC e si rilancia `python3 tools/gen_signals.py`.
- Lingua UI: **italiano**. Codice e commenti: italiano/inglese tecnico.
- Nessun segreto nel repo. I dump contengono solo telemetria tecnica.
