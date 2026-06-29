# Relazione Tecnica Dettagliata
## Decodifica e validazione del bus FMS (CAN J1939) di un autobus elettrico Rampini Eltron

**Progetto:** FMS-Rampini
**Committente interno:** Busitalia — Direzione Ingegneria Parco Mezzi (SAVIT)
**Sito:** Deposito di Terni
**Mezzo:** Rampini Eltron 8 m, elettrico a batteria
**Periodo:** maggio–giugno 2026
**Repository:** https://github.com/gvasta62/FMS-Rampini
**Dashboard online:** https://gvasta62.github.io/FMS-Rampini/

---

## Indice

1. Sintesi esecutiva
2. Contesto e problema iniziale
3. Diagnosi della causa radice
4. Materiale di partenza e acquisizione dati
5. Architettura della soluzione
6. Pipeline di decodifica J1939
7. Risultati: validazione fisica dei dati
8. Confronto con il costruttore (quesiti R1–R12)
9. Analisi del dump esteso
10. Stato dei contatori energetici e diagnostica
11. Ripartizione delle responsabilità sui punti aperti
12. Hardware di acquisizione raccomandato
13. Conclusioni e prossimi passi
14. Appendice: anagrafica nodi e mappa PGN

---

## 1. Sintesi esecutiva

Il progetto nasce per risolvere un'anomalia operativa: la dashboard ChargePoint/Viriciti non
mostrava alcun dato proveniente da un autobus elettrico Rampini Eltron del deposito di Terni.
L'indagine ha individuato la causa radice in un **disallineamento della topologia ECU** tra il file
DBC utilizzato (derivato da un template FMS diesel) e l'architettura reale del mezzo elettrico, che
provocava lo scarto silenzioso dei frame per mancata corrispondenza PGN+source.

È stata sviluppata una **dashboard web autonoma** (HTML/CSS/JS vanilla, nessuna dipendenza) capace
di decodificare i dump CAN con il DBC corretto e presentare le grandezze fisiche con statistiche e
grafici. Sono state estratte **86 grandezze su 10 sottosistemi** da 24 messaggi CAN distinti, con
coerenza fisica validata contro la documentazione tecnica.

Il confronto con il costruttore (12 quesiti, R1–R12) ha chiuso la fase analitica. L'analisi del
**dump esteso** (~350.000 frame, 12,5 minuti in marcia) ha confermato empiricamente le indicazioni
ricevute e ha quantificato la criticità residua: la bassa frequenza del messaggio energetico
(BMS_ENERGY, 0,08 Hz) che limita la reattività dei contatori sulla dashboard.

---

## 2. Contesto e problema iniziale

L'infrastruttura di telemetria di flotta Busitalia integra i mezzi elettrici tramite il canale
**FMS (Fleet Management System)**, uno standard del settore autobus basato su **CAN J1939** a
250 kbit/s, che espone un sottoinsieme normalizzato di parametri veicolo verso un gateway in sola
lettura. I dati confluiscono nella piattaforma ChargePoint/Viriciti.

Sul Rampini Eltron di Terni la dashboard di flotta risultava **completamente priva di dati**: nessun
segnale di velocità, stato batteria, consumi. Il gateway FMS era fisicamente presente e il bus
attivo, ma il livello applicativo non produceva grandezze.

---

## 3. Diagnosi della causa radice

Il file DBC in uso era stato derivato da un **template FMS per mezzi diesel**, ancorato al **source
address 17** (la ECU motore tipica di un powertrain endotermico). L'autobus elettrico ha però una
**topologia ECU completamente diversa**: non esiste una ECU motore su source 17, e le funzioni sono
distribuite su nodi differenti (BMS, EVCU, tachigrafo, ecc.).

In J1939 l'identificativo esteso a 29 bit incapsula priorità, PGN e **source address**. La
piattaforma scartava i frame quando la coppia **PGN + source** non corrispondeva alla definizione
attesa dal DBC. Poiché i source reali del mezzo elettrico non coincidevano con quelli del template
diesel, **tutti i frame venivano silenziosamente scartati**: nessun errore esplicito, semplicemente
nessun dato.

La diagnosi ha richiesto la **classificazione sistematica** dei 60 messaggi del DBC originale:

- 20 messaggi con source **corretto**;
- 23 messaggi con source **errato** (da rimappare);
- 17 messaggi con PGN **mai presente** sul bus reale.

Sono stati applicati 10 rimappamenti di source non ambigui (EBC1, EEC1, ETC2, DC1, DC2, TCO1, AIR1,
VHDR, AMB, DD1), più correzioni mirate: scala dell'odometro (VHDR da 5 a 0,005, unità da m a km) e
inversione del segno di BatteryPower (scala da 2 a −2, confermata dalla correlazione in marcia).

---

## 4. Materiale di partenza e acquisizione dati

**Dump CAN analizzati** (formato `candump`, esportazione CSV con colonne
`hexCanId,canId,pgn,source,timestamp,iface,value,willBeFiltered`):

- **Dump statico**: ~60.000 frame, 60 s, mezzo fermo.
- **Dump esteso (in marcia)**: ~350.000 frame, 12,5 minuti, velocità fino a 52 km/h, suddiviso in
  6 file (`candump (18..23).csv`).

**DBC**: `RAMPINI_ELTRON_TERNI_corretto.dbc` — 61 messaggi, 171 segnali, frutto della correzione del
template originale con le risposte del costruttore.

**Documentazione tecnica** del costruttore per la validazione dei valori attesi (SOH nominale,
tensioni di pacco e cella, range di velocità).

---

## 5. Architettura della soluzione

La dashboard è una **applicazione web statica** progettata per massima portabilità e zero
manutenzione infrastrutturale:

- **Nessuna dipendenza esterna**: HTML, CSS e JavaScript vanilla. Si apre anche da filesystem.
- **Pubblicazione GitHub Pages**: i colleghi accedono da browser senza account né installazioni.
- **Doppia modalità**: caricamento di dump da file (drag-and-drop o auto-caricamento) e **modalità
  live** via WebSocket da un agente Python che legge il bus in tempo reale.

**Struttura del repository:**

```
FMS-Rampini/
├── src/    index.html, styles.css, signals.js (auto-gen), decoder.js, chart.js, app.js
├── data/   candump (18..23).csv + RAMPINI_ELTRON_TERNI_corretto.dbc + manifest.json
├── docs/   RELAZIONE_PROGETTO.md, RELAZIONE_TECNICA_DETTAGLIATA.md, infografica, slide, catalogo
├── tools/  gen_signals.py, gen_presentation.py, dbc_from_dump.py, live_agent.py
└── index.html, README.md, CLAUDE.md
```

---

## 6. Pipeline di decodifica J1939

**Fase 1 — Generazione del database segnali** (`tools/gen_signals.py` → `src/signals.js`): il DBC
viene parsato per produrre, per ogni messaggio, PGN, source, DLC e l'elenco dei segnali con bit di
start, lunghezza, endianness, segno, scala, offset, unità, value-table e multiplexing.

**Fase 2 — Decoder J1939** (`src/decoder.js`): parsing veloce del CSV, estrazione dei bit con BigInt
(gestione Intel/Motorola), applicazione di segno/scala/offset, value-table, multiplexing. Regola
chiave per i **PGN proprietari** (0xFF00–0xFFFF): si decodificano solo dal source corretto (BMS = 30
per i messaggi batteria); sui PGN condivisi si seleziona la definizione in base al source.

**Fase 3 — Aggregazione e UI** (`src/app.js`): unione di più dump per timestamp, calcolo delle
statistiche per segnale e per messaggio, generazione dei segnali derivati, tabelle filtrabili,
selettore grafico multi-segnale.

**Fase 4 — Grafici** (`src/chart.js`): line chart su canvas con assi, griglia, decimazione e
tooltip, fino a 8 grandezze a confronto.

**Segnale derivato chiave**: `Potenza istantanea = Vpack × IPack`, calcolata da BMS_STAT1 (~4 Hz),
molto più reattiva del `BatteryPower` nativo di BMS_ENERGY (0,08 Hz).

---

## 7. Risultati: validazione fisica dei dati

Dal dump sono state estratte **86 grandezze con dati** su **10 sottosistemi**, da **24 messaggi**
CAN distinti. La coerenza fisica è stata validata contro la documentazione tecnica:

| Grandezza | Valore nel dump | Atteso | Esito |
|---|---|---|---|
| SOH (stato di salute batteria) | 94,8 % | 94,8 % | identico |
| Velocità ruote | 0 – 52,1 km/h | 0–52 km/h | identico |
| Tensione pacco (Vpack) | 619,7 – 640,3 V | ~636 V nominale | coerente |
| Corrente pacco (IPack) | −116,7 – +251,4 A | positiva in trazione | coerente |
| Tensione cella max/min | 3,23 – 3,34 V | ~3,31 V | coerente |
| Temperatura celle | 29 – 31 °C | normale | coerente |
| SoC | 57 – 59 % | coerente con marcia | coerente |
| EnergyOut / EnergyCharged | 0 (fissi) | anomalia nota | contatori BMS non popolati |
| EnergyRegen | ~6.512 kWh (fondo scala) | anomalia nota | confermata |
| Potenza derivata V×I | −74,6 … +156,1 kW | trazione/recupero | coerente |
| Odometro (VHDR) | 509,8 – 515,2 km | crescente | coerente |

I valori bloccati o anomali (contatori energetici a zero, EnergyRegen a fondo scala) **non sono
errori della dashboard**: sono limiti del dato prodotto a bordo dal BMS e la dashboard li espone
fedelmente.

---

## 8. Confronto con il costruttore (quesiti R1–R12)

Sono stati formalizzati 12 quesiti tecnici a Rampini. R1–R6 erano già stati recepiti (rimappamenti
di source e correzioni di scala). R7–R12 hanno chiuso la fase analitica:

| Quesito | Risposta del costruttore | Azione intrapresa | Stato |
|---|---|---|---|
| R7 | Ignorare il PGN 65310 | Messaggio `PCU_BMS` marcato IGNORE nel DBC | Chiuso |
| R8a | In attesa del dump esteso | Dump esteso inviato | In attesa |
| R8b | Ignorare `BMS_LCD_STAT`, source 39 | Messaggio marcato IGNORE nel DBC | Chiuso |
| R9 | In attesa del dump esteso | Dump inviato + frequenza verificata | In attesa |
| R10 | Tabella dei source dei nodi | Anagrafica `BU_` + commenti nel DBC | Chiuso |
| R11 | Resto del DBC corretto; ignorare i segnali non elencati | Nessuna modifica strutturale | Chiuso |
| R12 | Posizione demandata al modulo telematico | Confermato; nessuna azione su DBC | Chiuso |

---

## 9. Analisi del dump esteso

L'analisi del capture esteso (750,6 s, ~350.000 frame) ha permesso di **validare empiricamente** le
risposte del costruttore, anziché applicarle alla cieca.

**R7 — PGN 65310.** Nel dump il PGN 65310 non proviene dal source 62 (0x3E) con cui era definito nel
DBC (messaggio `PCU_BMS`), ma da tre source distinti:

| Source | Frame |
|---|---|
| 40 (0x28) — Interfaccia controllo impianti | 3.394 |
| 58 (0x3A) — Condizionatore batterie | 301 |
| 59 (0x3B) | 261 |

L'indicazione di ignorarlo è quindi coerente: non rappresenta un dato BMS utile.

**R8b — BMS_LCD_STAT (PGN 65296).** Nel dump il PGN 65296 compare **esclusivamente su source 39**
(0x27, Multiplex TEQ) — 3.344 frame — e **mai su source 30** (BMS). Nel DBC il messaggio era
erroneamente ancorato a source 30, quindi quella definizione non veniva mai soddisfatta dal bus
reale. La risposta del costruttore ("il source è 39") va letta come: il PGN su source 39 non è un
dato BMS e va ignorato. Marcato IGNORE.

**R9 — Frequenza dei messaggi BMS (source 30).** Misura delle cadenze reali sul dump esteso:

| Messaggio | PGN | N. frame | Frequenza | Periodo |
|---|---|---|---|---|
| BMS_V | 65280 | 3.178 | 4,23 Hz | ~0,24 s |
| BMS_T | 65281 | 3.143 | 4,19 Hz | ~0,24 s |
| BMS_STAT1 | 65282 | 3.100 | 4,13 Hz | ~0,24 s |
| BMS_STAT2 | 65283 | 3.072 | 4,09 Hz | ~0,24 s |
| **BMS_ENERGY** | **65289** | **60** | **0,08 Hz** | **mediana 5,67 s (5–12 s)** |

**Conclusione su R9:** la cadenza di ~5 secondi che il costruttore aveva osservato sul dump ridotto
**si conferma sul dump esteso**. Non era un effetto di sottocampionamento: la bassa frequenza di
BMS_ENERGY è reale e strutturale. Poiché `EnergyOut`, `EnergyCharged` e `BatteryPower` viaggiano
tutti su questo PGN, la loro scarsa reattività sulla dashboard è una conseguenza diretta di questa
cadenza. La dashboard mitiga il problema con la potenza derivata V×I a 4 Hz.

---

## 10. Stato dei contatori energetici e diagnostica

**Contatori energetici.** `EnergyOut` ed `EnergyCharged` risultano a zero (non popolati dal BMS);
`EnergyRegen` è a fondo scala (~6.512 kWh). Sono limiti del dato prodotto a bordo, non della
decodifica. Da chiarire con Rampini se i contatori possano essere popolati o trasferiti su un
messaggio a frequenza maggiore.

**Diagnostica (DTC).** Nel dataset analizzato risultano accese 2 spie ambra (warning):

| Spia | Sistema | Codice guasto (DTC) | Occorrenze |
|---|---|---|---|
| Ambra (warning) | BMS — batteria | SPN 57650 · FMI 0 | 1 |
| Ambra (warning) | ECAS — sospensioni pneumatiche | SPN 61507 · FMI 9 | 12 |

Le spie rossa di stop, MIL e di protezione risultano spente.

**Climatizzazione (HVAC/RHCV).** Potenza complessiva clima 1,4–3,2 kW (cabina guida 1,1–3 kW,
passeggeri 0–1 kW); riscaldamento a 0 kWh (clima in raffrescamento).

---

## 11. Ripartizione delle responsabilità sui punti aperti

**Lato Rampini (costruttore):**
- R8a — verifica del comportamento del messaggio sul capture completo.
- R9 — conferma definitiva sulla frequenza di BMS_ENERGY e fattibilità di popolare/accelerare i
  contatori energetici.

**Lato Onell/ChargePoint (integratore dashboard):**
- Remapping del widget velocità: il DBC espone correttamente la velocità su CCVS (PGN 65265), ma il
  widget puntava a TCO1. Da correggere la mappatura.
- Correzione della convenzione di segno della potenza: l'inversione osservata sulla dashboard deriva
  dal calcolo P = V × I lato ChargePoint, non dal DBC.

---

## 12. Hardware di acquisizione raccomandato

Per le acquisizioni sul campo su mezzi ad alta tensione si raccomanda l'interfaccia **PEAK PCAN-USB
opto-isolata (IPEH-002022)**, con isolamento galvanico fino a 500 V a protezione del PC e
dell'operatore. Collegamento sul connettore D-Sub 9 secondo CiA 303-1: **CAN_H su pin 7, CAN_L su
pin 2, GND su pin 3**. Acquisizione in **listen-only**, bitrate 250000. Nessuna terminazione
aggiuntiva: il gateway FMS è già terminato a 120 Ω.

L'agente live (`tools/live_agent.py`) supporta SocketCAN nativo (Linux/Raspberry Pi, zero
dipendenze) e il backend python-can per adattatori PEAK/Kvaser/CANable su Windows.

---

## 13. Conclusioni e prossimi passi

La fase analitica è conclusa. Il DBC è allineato alla topologia reale del mezzo, i dati sono
leggibili e fisicamente coerenti, e la dashboard è pubblicata e accessibile ai colleghi. Le
indicazioni del costruttore sono state recepite e validate sul dump esteso.

Restano due fronti, entrambi esterni all'analisi qui svolta: la chiusura di R8a/R9 lato Rampini
(frequenza e contatori energetici) e gli interventi di mappatura lato Onell/ChargePoint (widget
velocità e segno potenza). Una volta chiusi, la dashboard di flotta tornerà a esporre il mezzo in
modo completo.

**Prossimi passi operativi:**
1. Invio del dump esteso a Rampini con la sintesi del recepimento R7–R12 (mail predisposta).
2. Commit su GitHub del DBC aggiornato e della documentazione.
3. Correzione separata dell'errore preesistente `FMI1_ECAS`/`DM01_ECAS` nel DBC.
4. Apertura del ticket lato Onell/ChargePoint per widget velocità e segno potenza.

---

## 14. Appendice: anagrafica nodi e mappa PGN

**Anagrafica nodi (R10):**

| Nodo | Source (dec) | Source (hex) |
|---|---|---|
| BMS (Batteria) | 30 | 0x1E |
| Condizionatore batterie | 58 | 0x3A |
| Gateway motore DANA | 208 | 0xD0 |
| Climatizzazione Rampini | 6 | 0x06 |
| Multiplex TEQ | 39 | 0x27 |
| Interfaccia controllo impianti | 40 | 0x28 |

**Messaggi BMS principali (source 30, PGN proprietari 0xFF00–0xFFFF):**

| Messaggio | PGN | Hex | Contenuto |
|---|---|---|---|
| BMS_V | 65280 | 0xFF00 | tensioni |
| BMS_T | 65281 | 0xFF01 | temperature |
| BMS_STAT1 | 65282 | 0xFF02 | Vpack, IPack (base per potenza V×I) |
| BMS_STAT2 | 65283 | 0xFF03 | stato |
| BMS_ENERGY | 65289 | 0xFF09 | EnergyOut/Charged, BatteryPower (0,08 Hz) |
| BMS_STAT3 | 65290 | 0xFF0A | SOH, consumi |

**Messaggi marcati IGNORE:**

| Messaggio | PGN | Motivo |
|---|---|---|
| PCU_BMS | 65310 (0xFF1E) | R7 — non dato BMS utile, arriva da source 40/58/59 |
| BMS_LCD_STAT | 65296 (0xFF10) | R8b — solo su source 39 (Multiplex TEQ), non BMS |

**Velocità (FMS standard):** CCVS/WheelBasedSpeed (PGN 65265), TCO1 (PGN 65132). La velocità
affidabile è su CCVS.
