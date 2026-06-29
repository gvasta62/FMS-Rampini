# Recepimento risposte Rampini R7–R12 e analisi del dump esteso

**Progetto:** FMS-Rampini — Eltron elettrico, deposito di Terni (Busitalia)
**Data:** giugno 2026
**Dump analizzato:** capture esteso in marcia — 6 file `candump (18..23).csv`, ~350.000 frame, durata aggregata **750,6 s (12,5 min)**

---

## Sintesi delle risposte e azioni intraprese

| Quesito | Risposta Rampini | Azione sul progetto | Stato |
|---|---|---|---|
| R7 | Ignorare il PGN 65310 | Messaggio `PCU_BMS` marcato IGNORE nel DBC | Chiuso |
| R8a | In attesa del dump esteso | Dump inviato | In attesa Rampini |
| R8b | Ignorare `BMS_LCD_STAT`, source 39 | Messaggio marcato IGNORE nel DBC | Chiuso |
| R9 | In attesa del dump esteso | Dump inviato + frequenza verificata | In attesa Rampini |
| R10 | Tabella source dei nodi | Anagrafica `BU_` + commenti nel DBC | Chiuso |
| R11 | Resto del DBC ok, ignorare i segnali non elencati | Nessuna modifica strutturale ulteriore | Chiuso |
| R12 | Posizione via modulo telematico, non CAN | Confermato, nessuna azione su DBC | Chiuso |

---

## Verifica empirica sul dump esteso

L'analisi del capture esteso conferma e precisa le indicazioni di Rampini.

### R7 — PGN 65310
Nel dump il PGN 65310 **non proviene** dal source 62 (0x3E) con cui era definito nel DBC (`PCU_BMS`), ma da tre source diversi:

| Source | Frame |
|---|---|
| 40 (0x28) | 3.394 |
| 58 (0x3A) | 301 |
| 59 (0x3B) | 261 |

Coerente con l'indicazione di ignorarlo: non è un dato BMS utile.

### R8b — BMS_LCD_STAT (PGN 65296)
Nel dump il PGN 65296 compare **esclusivamente su source 39 (0x27 = Multiplex TEQ)** — 3.344 frame — e **mai su source 30 (BMS)**. Nel DBC il messaggio era erroneamente ancorato a source 30, quindi di fatto non veniva mai trasmesso da quella definizione. Marcato IGNORE.

### R9 — Frequenza dei messaggi BMS (source 30)
I messaggi BMS principali sono regolari e ad alta frequenza; **BMS_ENERGY è l'unico lento**:

| Messaggio | PGN | Frequenza | Periodo |
|---|---|---|---|
| BMS_V | 65280 | 4,23 Hz | ~0,24 s |
| BMS_T | 65281 | 4,19 Hz | ~0,24 s |
| BMS_STAT1 | 65282 | 4,13 Hz | ~0,24 s |
| BMS_STAT2 | 65283 | 4,09 Hz | ~0,24 s |
| **BMS_ENERGY** | **65289** | **0,08 Hz** | **~5–12 s (mediana 5,67 s)** |

**Conferma:** la comparsa "ogni ~5 secondi" che Rampini osservava sul dump ridotto **si conferma anche sul dump esteso** — non era un artefatto di sottocampionamento. La bassa frequenza di BMS_ENERGY (60 frame in 12,5 min) è reale e strutturale. Questo è il motivo per cui i contatori `EnergyOut`/`EnergyCharged` e `BatteryPower` su questo PGN sono poco reattivi: la dashboard usa già la grandezza derivata `Potenza = Vpack × IPack` da BMS_STAT1 (~4 Hz) per ovviare.

---

## Modifiche applicate al DBC (`RAMPINI_ELTRON_TERNI_corretto.dbc`)

1. **Anagrafica nodi `BU_`** (R10): aggiunti i 6 nodi con i rispettivi source documentati nei commenti `CM_ BU_`:
   - BMS — 0x1E (30)
   - Condizionatore_Batterie — 0x3A (58)
   - Gateway_Motore_DANA — 0xD0 (208)
   - Climatizzazione_Rampini — 0x06 (6)
   - Multiplex_TEQ — 0x27 (39)
   - Interfaccia_Controllo_Impianti — 0x28 (40)
2. **Commenti IGNORE** sui messaggi `PCU_BMS` (R7) e `BMS_LCD_STAT` (R8b), con la motivazione tratta dal dump.
3. **Nessuna rimozione fisica** dei messaggi: restano definiti e tracciati, ma documentati come da ignorare in decodifica. Conteggio invariato: 61 messaggi, 171 segnali.

> Nota tecnica: il DBC contiene un errore preesistente non correlato a questa patch (segnale `FMI1_ECAS` che eccede il messaggio `DM01_ECAS`), che impedisce il parsing in modalità strict di cantools. La dashboard JS e il parsing permissivo lo gestiscono senza problemi. Da valutare una correzione separata.

---

## Punti ancora aperti

**Lato Rampini** (in attesa della loro analisi del dump esteso):
- R8a — verifica comportamento messaggio sul capture completo
- R9 — conferma definitiva sulla frequenza BMS_ENERGY e impatto sui contatori energetici

**Lato Onell/ChargePoint** (indipendenti da queste risposte):
- Remapping widget velocità su CCVS (PGN 65265)
- Correzione convenzione segno potenza (calcolo P = V × I lato ChargePoint)
