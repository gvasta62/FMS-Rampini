# Relazione di progetto — Dashboard dump bus FMS (Rampini Eltron)

**Busitalia — Direzione Ingegneria Parco Mezzi**
Progetto: **FMS-Rampini** · Bus elettrico Rampini Eltron, deposito di Terni
Dashboard online: **https://gvasta62.github.io/FMS-Rampini/**
Repository: **https://github.com/gvasta62/FMS-Rampini**
Data: 27/06/2026

---

## 1. Obiettivo

Realizzare uno strumento web che permetta di **leggere in modo chiaro tutti i dati** contenuti
nei dump del canale **FMS (CAN J1939)** di un autobus elettrico Rampini Eltron, trasformando i
frame CAN grezzi in grandezze fisiche comprensibili (tensioni, correnti, temperature, velocità,
stato di carica, energie, diagnostica…), con statistiche e grafici temporali, e renderlo
accessibile ai colleghi tramite un semplice link, senza installare nulla.

## 2. Materiale di partenza

| Elemento | Descrizione |
|---|---|
| 6 file `candump (18..23).csv` | Registrazioni consecutive del bus FMS, **350.522 frame** totali, **750,6 s** (12 min 31 s) di **marcia reale** (velocità 0–52 km/h) |
| `RAMPINI_ELTRON_TERNI_corretto.dbc` | File di descrizione del costruttore: **61 messaggi, 171 segnali** — la "chiave" per decodificare i frame |
| 2 documenti di analisi (`.docx`) | Studio tecnico preliminare DBC vs bus reale (mapping PGN/source, segno potenza, velocità, energie) |

Formato di ogni riga di dump:
`hexCanId,canId,pgn,source,timestamp,iface,value,willBeFiltered`
dove `pgn` identifica il tipo di messaggio, `source` la centralina trasmittente, `timestamp` è
l'epoch in millisecondi e `value` è il payload (fino a 8 byte) in esadecimale.

## 3. Approccio e architettura

È stata scelta una **web-app statica** in HTML/CSS/JavaScript **vanilla, senza dipendenze né
build né CDN**: un singolo insieme di file che funziona aprendo `index.html` o servito da un web
server. Questo garantisce longevità, portabilità e nessun problema di manutenzione di librerie.

```
FMS-Rampini/
├── src/      index.html · styles.css · signals.js (auto-gen) · decoder.js · chart.js · app.js
├── data/     6 candump + DBC + manifest.json
├── docs/     documenti di analisi, relazione, infografica, slide, catalogo
├── tools/    gen_signals.py · gen_presentation.py
└── index.html (redirect) · .nojekyll
```

### 3.1 Generazione del database segnali (`tools/gen_signals.py`)
Il DBC viene parsato e convertito in `src/signals.js` (`window.FMS_DB`): per ogni messaggio si
estraggono PGN, source address, DLC e, per ogni segnale, bit di partenza/lunghezza, endianness,
segno, fattore di scala, offset, unità, tabelle di stato e commenti. I **PGN calcolati dal DBC
sono stati verificati uno per uno** contro la documentazione (es. BMS_STAT1 = 65282, CCVS = 65265):
corrispondenza esatta.

### 3.2 Decodifica J1939 (`src/decoder.js`)
- Parsing veloce del CSV.
- Estrazione dei bit con **BigInt** (gestione sicura di segnali fino a 32 bit), endianness
  **Intel** (`@1`) e **Motorola** (`@0`), interpretazione **con segno** (complemento a due),
  applicazione di **scala e offset**, traduzione dei valori tramite **tabelle di stato**
  (es. `16388 → "DRIVE RUN"`), gestione del **multiplexing** (es. messaggio RHCV) e dei valori
  **N/A** (payload a 0xFF).
- **Regola dei PGN proprietari** (punto delicato emerso dall'analisi): nello spazio `0xFF00..`
  più centraline trasmettono sullo stesso PGN distinguendosi solo per il source address. La
  dashboard accetta questi frame **solo dalla centralina corretta** (i PGN condivisi
  0xFF00/01/02 e gli altri BMS solo dall'indirizzo **30**), scartando i frame spuri di altre
  centraline (208, 73, 39, 40) che altrimenti sovrascriverebbero i dati batteria. Per i PGN
  standard, invece, si mantiene il match per solo-PGN che recupera i messaggi il cui source nel
  DBC era ereditato da un template diesel.

### 3.3 Aggregazione e interfaccia (`src/app.js`)
Unisce più dump ordinandoli per timestamp, calcola per ogni grandezza conteggio campioni, N/A,
min/media/max e ultimo valore, e per ogni messaggio frequenza e source. Genera inoltre una
grandezza **derivata** — la **potenza istantanea `P = Vpack × IPack`** da BMS_STAT1 (~4 Hz) —
più reattiva del `BatteryPower` nativo (trasmesso a soli 0,08 Hz). L'interfaccia ha quattro
schede: **Grandezze** (filtrabile, con grafico per ogni segnale), **Messaggi**, **Grafico**
multi-segnale e **Info**.

### 3.4 Grafici (`src/chart.js`)
Renderer **canvas custom** (nessuna libreria): assi, griglia, decimazione automatica per le serie
lunghe e tooltip interattivo.

## 4. Risultati: i dati sono leggibili e coerenti

Dal dump sono state estratte **86 grandezze con dati** su **10 sottosistemi**, da **24 messaggi**
CAN distinti. La coerenza fisica è stata validata contro la documentazione tecnica:

| Grandezza | Valore nel dump | Atteso | Esito |
|---|---|---|---|
| SOH (stato di salute batteria) | 94,8 % | 94,8 % | ✓ identico |
| Velocità ruote | 0 – 52,1 km/h | "0–52 km/h" | ✓ identico |
| Tensione pacco (Vpack) | 619,7 – 640,3 V | ~636 V nominale | ✓ |
| Corrente pacco (IPack) | −116,7 – +251,4 A | positiva in trazione | ✓ |
| Tensione cella max/min | 3,23 – 3,34 V | ~3,31 V | ✓ |
| Temperatura celle | 29 – 31 °C | normale | ✓ |
| SoC | 57 – 59 % | coerente con marcia | ✓ |
| EnergyOut / EnergyCharged | 0 (fissi) | anomalia nota | ✓ (contatori BMS non popolati) |
| EnergyRegen | ~6.512 kWh (fondo scala) | anomalia nota | ✓ |
| Potenza derivata V×I | −74,6 … +156,1 kW | trazione/recupero | ✓ |
| Odometro (VHDR) | 509,8 – 515,2 km | crescente | ✓ |

I valori bloccati o anomali (contatori energetici a zero, EnergyRegen a fondo scala) **non sono
errori della dashboard**: sono limiti del dato prodotto a bordo dal BMS, già documentati
nell'analisi tecnica, e la dashboard li espone fedelmente.

## 5. Le grandezze disponibili sul dump (per sottosistema)

| Sottosistema | N. grandezze | Esempi |
|---|---|---|
| 🔋 Batteria / BMS | 21 | Vpack, IPack, SoC, SOH, temperature/tensioni celle, energie, potenza V×I, stato BMS |
| ⚙️ Trazione / Motore | 7 | regime motore, coppia %, pedale acceleratore, marcia, pedale freno |
| 🚌 Velocità / Odometro | 5 | velocità ruote (CCVS), velocità tachigrafo (TCO1), distanza alta risoluzione |
| ❄️ Climatizzazione (RHCV) | 12 | potenze ed energie cabina guida/passeggeri, temperature di mandata e ambiente |
| 🚪 Porte / Accessibilità | 9 | posizione/stato/blocco porte, pedana disabili |
| 🛑 Freni / Aria | 10 | pressioni aria freno di servizio, usura ferodi (per assale/ruota) |
| ⚠️ Diagnostica (DTC) | 28 | spie e codici guasto attivi del BMS e delle sospensioni ECAS (SPN/FMI/occorrenze) |
| 🌡️ Ambiente | 2 | temperatura aria esterna e interno cabina |
| 🕐 Tempo / Data | 6 | ora/data dal messaggio TD |
| 🛢️ Livelli | 2 | livello (FuelLevel) |

Il catalogo completo, grandezza per grandezza con unità, range osservato e numero di campioni, è
in **`docs/catalogo_grandezze.json`** ed è rappresentato visivamente in **`docs/infografica.html`**
e **`docs/slide.html`**.

In apertura l'infografica evidenzia un **banner delle spie cruscotto risultate accese** nel dump e
mette **in risalto i valori HVAC** (climatizzazione RHCV). Nel dataset analizzato risultano accese
**2 spie ambra (warning)**:

| Spia | Sistema | Codice guasto (DTC) | Occorrenze |
|---|---|---|---|
| 🟠 Ambra (warning) | BMS — batteria | SPN 57650 · FMI 0 | 1 |
| 🟠 Ambra (warning) | ECAS — sospensioni pneumatiche | SPN 61507 · FMI 9 | 12 |

Le spie rossa di stop, MIL (malfunzionamento) e di protezione risultano **spente**. I valori HVAC
osservati: potenza complessiva clima 1,4–3,2 kW (cabina guida 1,1–3 kW, passeggeri 0–1 kW),
energie di sessione cooling/driver/pax, temperature di mandata e ambiente; il riscaldamento risulta
a 0 kWh (clima in raffrescamento).

## 6. Note tecniche rilevanti per l'esercizio

- **Potenza**: usare la potenza derivata `V×I` (≈4 Hz) come indicatore istantaneo; il
  `BatteryPower` nativo arriva ogni 12,5 s.
- **Velocità**: disponibile e affidabile su due sorgenti (CCVS e TCO1).
- **Contatori energetici** `EnergyOut`/`EnergyCharged`: non popolati dal BMS (da segnalare a Rampini).
- **Diagnostica**: sono presenti DTC attivi su BMS (spia ambra accesa, SPN 57650) e su sospensioni
  ECAS (SPN 61507) — da approfondire.
- **Posizione GPS**: non transita sul canale FMS (la fornisce il modulo telematico); coerente con
  il fatto che il DBC non definisce messaggi di posizione.

## 7. Pubblicazione

Il progetto è pubblicato su un **repository GitHub pubblico** con **GitHub Pages** attivo
(deploy dal branch `main`). I colleghi accedono dal link
**https://gvasta62.github.io/FMS-Rampini/** con un normale browser, senza account né
installazioni: premendo «Auto-carica data/» vedono subito i dati dei dump inclusi, oppure
possono trascinare i propri file CSV per analizzarli. Gli aggiornamenti futuri sono automatici a
ogni `git push` (rebuild in ~1 minuto).

> **Nota riservatezza.** Trattandosi di repository pubblico, i dump e i documenti di analisi sono
> accessibili a chiunque e indicizzabili. Se in futuro fosse necessario limitarne l'accesso, le
> opzioni sono: rendere il repository privato (con Pages su piano a pagamento) oppure rimuovere
> `data/` e `docs/` lasciando online la sola applicazione.

## 8. Dati in tempo reale (modalità live)

La dashboard può ricevere i frame **in diretta** dal bus, oltre che da file. Un **agente**
(`tools/live_agent.py`, **solo libreria standard Python**) legge il bus via **SocketCAN nativo**
(o riproduce i dump per provare senza hardware) e li streama via **WebSocket**; la dashboard li
decodifica con lo stesso `decoder.js` e aggiorna tabelle e grafici su una **finestra scorrevole di
5 minuti**, con riconnessione automatica.

- **Salvataggio dump con nome a scelta**: in modalità live, dal browser («Salva dump CSV») o
  dall'agente (`--save FILE.csv`); il file è in **formato candump**, ricaricabile nella dashboard.
- **Configurazione hardware** nell'agente: `--bitrate` (FMS = 250000), `--listen-only`, `--up`,
  `--list`; backend `socketcan` (Linux, zero dipendenze) o `pythoncan` (Windows/PEAK/Kvaser/CANable).
- **Hardware consigliato**: USB‑CAN (PEAK PCAN‑USB, CANable) per PC, o Raspberry Pi + CAN HAT a bordo.
  **Il software è gratuito al 100%**; l'unico costo è l'adattatore CAN. Guida passo‑passo in
  `docs/GUIDA_HARDWARE.md`.

## 9. Dal dump al DBC (reverse-DBC)

Lo strumento `tools/dbc_from_dump.py` percorre il senso inverso — dai dump verso il file DBC di un
mezzo — in quattro modalità: **inventory** (inventario dei messaggi presenti + analisi byte:
costante/contatore/enum/analogico), **skeleton** (DBC con i segnali J1939 **standard** completi per
i PGN noti, dal seed `data/fms_standard_seed.dbc`, più placeholder per‑byte con commenti‑indizio sui
PGN **proprietari**), **remap** (adatta un DBC esistente rimappando solo i source univoci e sicuri;
i PGN proprietari condivisi restano *ambigui*, da verificare col costruttore), **makeseed** (estrae i
PGN standard in un seed riusabile). I segnali standard si ricavano automaticamente; i proprietari
(0xFF00–0xFFFF) richiedono i documenti del costruttore — il dump serve a ipotizzarli e la dashboard a
validarli.

## 10. Come rigenerare gli artefatti

```bash
python3 tools/gen_signals.py        # rigenera src/signals.js dal DBC
python3 tools/gen_presentation.py   # rigenera docs/infografica.html e docs/slide.html dal catalogo
python3 tools/dbc_from_dump.py inventory --data data --out docs/dump_inventory.md   # reverse-DBC
python3 tools/live_agent.py --source replay --loop                                  # agente live (prova)
```
Il catalogo (`docs/catalogo_grandezze.json`) si ottiene decodificando i dump con `src/decoder.js`.
