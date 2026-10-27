# Context 2 — Design of the TK5 edition

## Data flow of job MIGRUN
```
inline cards ─IEBGENER─► SRC.EXTRACT ─SORT(1,80)─► SRC.SORTED ──────────┐
inline cards ─IEBGENER─► TGT.EXTRACT ─SORT(1,80)─► TGT.SORTED            │
                                       IDCAMS DEFINE + REPRO              │
                                       ▼                                  │
                              TGT.KSDS (VSAM, key 1-18)  <- "modern system table"
                                       │ IDCAMS REPRO (unload, key order) │
                                       ▼                                  ▼
                                   TGT.UNLOAD ──────────► COBOL MIGMATCH (dedupe + match-merge)
                                                     │        │         │
                                       SRC.DEDUP ◄───┘   RECON.EXCEPT   CTRL.OUT
                                                              ▼         ▼
                          BREXX MIGREXX (+ raw counts of SRC.EXTRACT / TGT.EXTRACT)
                          → RECON.EXCSORT  RECON.REPORT  RECON.MIGOUT  RECON.AUDREC  RECON.EXCREC
                                 │ IDCAMS REPRO (AUDIT step)
                                 ▼
                 MIG.AUDIT.KSDS (1 rec/batch)   MIG.EXCLOG.KSDS (1 rec/exception)
   gate:  RC<=4 → SRC.DEDUP → MIG.GATE.APPROVED(+1)      RC>4 → EXCSORT → MIG.GATE.REJECTED(+1)
   print: REPORT and MIGOUT to SYSOUT (prt00e.txt) — Python parses MIGOUT
```

## Jobs
| Job (name) | When | Steps |
|---|---|---|
| CHECK (`HERC01K`) | first, read-only | LISTDS SYS2.PROCLIB, LISTCAT, test sort |
| SETUP (`HERC01S`) | once (resets history) | DELETE / DEFINE 2 GDG bases, 2 audit KSDS, model DSCB, LOAD library |
| BUILD (`HERC01B`) | after every code change | IEBUPDTE source into `MIG.SOURCE` and `MIG.REXX`, `COBUCL` compile + link |
| MIGRUN (`HERC01V`) | each validation | CLEAN, LOADSRC, LOADTGT, SORTSRC, SORTTGT, DEFKSDS, LOADKSDS, UNLOAD, MATCH, REXXRUN, AUDIT, APPROVE, REJECT, PRINTRPT, PRINTOUT |
| HIST (`HERC01H`) | any time, read-only | BREXX VSAMIO reads AUDIT.KSDS, IDCAMS PRINT both logs |

## Datasets (all `HERC01.MIG.*`)
| Dataset | Type / LRECL | Purpose |
|---|---|---|
| SOURCE | PDS FB 80 | COBOL source (MIGMATCH) |
| REXX | PDS FB 80 | BREXX execs MIGREXX, MIGHIST |
| LOAD | PDS U | load module MIGMATCH |
| SRC.EXTRACT / TGT.EXTRACT | PS FB 80 | raw extracts (from cards) |
| SRC.SORTED / TGT.SORTED | PS FB 80 | sort output |
| TGT.KSDS | VSAM KSDS key(18,0) rec 80 | target table (replaces DB2 CUSTOMER_NEW) |
| TGT.UNLOAD | PS FB 80 | KSDS unloaded in key order (COBOL input) |
| SRC.DEDUP | PS FB 80 | unique source (cutover payload) |
| RECON.EXCEPT | PS FB 100 | exceptions from COBOL |
| CTRL.OUT | PS FB 150 | COBOL control record |
| RECON.EXCSORT | PS FB 100 | exceptions without repeats, sorted by type + key |
| RECON.REPORT | PS FBA 133 | human report |
| RECON.MIGOUT | PS FB 133 | machine-readable result (KEY=VALUE + `EXC:` lines) |
| RECON.AUDREC / EXCREC | PS FB 120 | records to add to the audit KSDS |
| AUDIT.KSDS | VSAM KSDS key(15,0) rec 120 | one row per batch (replaces DB2 MIG_BATCH_LOG) |
| EXCLOG.KSDS | VSAM KSDS key(20,0) rec 120 | one row per exception (replaces DB2 MIG_EXCEPTION) |
| GATE.APPROVED / REJECTED | GDG, limit 10 | accepted payload / rejected exceptions |
| GDGMODEL | PS on TSO001 | pattern DSCB for the GDGs |

## Record layouts
**Source extract, 80 bytes**
| Cols | Field | Picture |
|---|---|---|
| 1-8 | CUST-ID | X(8) |
| 9-18 | ACCT-NO | X(10) |
| 19-38 | NAME | X(20) |
| 39-49 | BALANCE | 9(9)V99 (unsigned, implied decimal) |
| 50-57 | TXN-DATE | YYYYMMDD |
| 58 | STATUS | X |
| 59-80 | blanks | |

**Target extract / KSDS, 80 bytes:** CUST_ID 1-8, ACCT_NO 9-18, NAME 19-48
(30 characters), BALANCE 49-60 as text `000001234.56`, TXN_DATE 61-70
`YYYY-MM-DD`, STATUS 71, blanks 72-80. COBOL normalises the balance (checks
digits and the '.', then REDEFINES) and the date (checks both '-').

**Exception, 100 bytes:** CUST 1-8, ACCT 9-18, TYPE 19-26, FIELD 27-34,
SOURCE VALUE 35-64, TARGET VALUE 65-94, blanks 95-100.
- Types: `MISSING`, `MISMATCH`, `EXTRA`, `DUPKEY`.
- Fields: `*RECORD`, `NAME`, `BALANCE`, `TXNDATE`, `STATUS`.
- For `*RECORD` rows the value is NAME (17 characters), a blank, and the
  balance edited `Z(8)9.99`.

**Control record, 150 bytes:** TAG 1-8 (`MIGCTRL ` or `MIGABORT`), then nine
10-digit counters (read, unique, dup_same, dup_conf, target, matched,
mismatch, missing, extra) at 9-98, source total (sign + 9(13)V99) at 99-114,
target total at 115-130, abort reason 131-150.

**Audit record, 120 bytes:** batch id 1-15 (key, `B` + yyyymmdd + hhmmss),
decision 16-25, RC 26-28, then 10-digit raw, dups, unique, target, matched,
mismatch, missing, extra. The exception log record is batch id + 5-digit
sequence (key 1-20) followed by the 100-byte exception.

## Decision rules (REXX)
1. **ABORTED, RC 12**, if any control disagrees:
   - the COBOL tag is `MIGABORT` (sequence error or duplicate key in its input);
   - the raw source count ≠ COBOL read count;
   - the raw target count ≠ KSDS count (**VSAM rejected duplicate keys**);
   - unique + duplicates ≠ read;
   - matched + changed + missing ≠ unique;
   - matched + changed + extra ≠ target;
   - the number of exception rows of a type ≠ its control count.
2. **REJECTED, RC 8**, if there is any missing, extra, changed or conflicting
   duplicate key.
3. **WARNING, RC 4**, if only identical duplicates were dropped.
4. **APPROVED, RC 0** otherwise.
5. A REXX failure ends **RC 16**. AUDIT is then skipped, and the gate takes
   the REJECT branch (fail-safe).

## Duplicate handling (why it differs from the PPT)
DFSORT `SUM FIELDS=NONE` does not exist on TK5. The source is sorted on the
whole record, so copies of a key are next to each other in a fixed order.
COBOL keeps the first copy. A following copy that is **identical** is
dropped and counted (`DUP_SAME`). A copy with **different data** is
reported as `DUPKEY` (`DUP_CONF`) because nobody can know which copy is
right. That is better than DFSORT, which would drop it silently.

## Test scenarios (`python/gen_data.py`, seed 42)
- **seeded:** 1,000 customers + 20 identical duplicates. The target has 10
  rows removed, 15 changed (6 balance, 3 name, 3 date, 3 status) and 5 extra.
- **dups:** 20 identical duplicates only.
- **clean:** no defects.
- **conflict:** 3 keys whose duplicate copy has a different balance.
- **dup_target:** one target key appears twice. VSAM rejects the second copy.

## Python side
- `render.py` fills the tokens, inserts the code and data cards, and lints
  (80 columns, forbidden characters, JCL ≤ 71, job name ≤ 8).
- `tk5client.py` handles socket submit, printer-file watch and step-RC parsing.
- `deploy.py` runs SETUP and BUILD and checks the RC of every step.
- `run_batch.py` renders MIGRUN with data, runs it, saves `runs/<batch>/`
  and verifies against the reference.
- `validator_core.py` is the independent reference implementation. It
  mimics the EBCDIC sort, KSDS duplicate rejection, COBOL dedupe and match,
  and the REXX decision.
- `app.py` is the Streamlit dashboard (TK5 runs or the offline demo).
