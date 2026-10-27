# Context 1 — TK5 facts (verified by running jobs)

Every statement below was checked by submitting jobs to a real TK5 system
(MVS-TK5 Update 4 under SDL Hercules 4.9.1). The evidence is the job number
and the message seen. Where the official TK5 manual says something newer
(Update 5), that is noted as well.

## 1. The system
| Item | Value |
|---|---|
| OS | OS/VS2 MVS 3.8J, distribution **MVS-TK5** (Rob Prins), runs on Hercules |
| Start | `mvs.bat` (Windows) or `./mvs` (Linux/Mac) in the `mvs-tk5` folder |
| Terminal | any TN3270 client (x3270, wc3270, Vista TN3270, CryptoTerm) → `localhost:3270` |
| TSO users | `HERC01`/`HERC02` password `CUL8TR` (privileged), `HERC03`/`HERC04` password `PASS4U` (normal), `IBMUSER`/`IBMPASS` (recovery only) |
| Security | RAKF (RACF-like). Jobs from the card reader must carry `USER=HERC01,PASSWORD=CUL8TR` on the JOB card |
| Shutdown | TSO READY prompt: `SHUTDOWN`, then `LOGOFF` |
| Hercules web console | `http://localhost:8038` (commands can be typed there too) |
| User catalog | `HERC01.*` → `SYS1.UCAT.TSO` on volume **TSO001** |
| Disk for user data | volumes TSO001–TSO003 (permanent), WORK01–WORK04 (temporary); `UNIT=SYSDA` works |

## 2. Getting jobs in and output out (no Zowe on MVS 3.8)
From `conf/tk5.cnf`:
```
000C 3505 ${RDRPORT:=3505} sockdev ascii trunc eof   <- card reader on TCP port 3505
000E 1403 prt/prt00e.txt                              <- printer for output class A
000F 1403 prt/prt00f.txt                              <- printer for class Z/other
```
- **Submit by socket:** open TCP `localhost:3505`, send the JCL as ASCII
  lines (≤ 80 columns), then close. Verified (jobs 1–36).
- **Submit from the Hercules console:** `devinit 00c C:\path\job.jcl ascii trunc eof`,
  then put the socket back with `devinit 00c 3505 sockdev ascii trunc eof`.
  Verified (job 35).
- **Output:** with `MSGCLASS=A` and `SYSOUT=*`, everything is printed to
  `prt/prt00e.txt` on the PC. Each job is framed by
  `****A  START  JOB  nn  NAME` and `****A   END   JOB  nn  NAME` banners.
  The step table looks like
  ` 8.31.46 JOB   13  HERC01PC   LOAD                IDCAMS    RC= 0008`.
- `MSGCLASS=H` holds output in JES2, so it can be viewed in TSO
  (RFE/RPF outlist) instead of the printer file.

## 3. COBOL = IBM ANS COBOL (IKFCBL00, COBOL-68 level)
- Procedures in `SYS2.PROCLIB`: `COBUC`, `COBUCG`, `COBUCL` (compile + link),
  `COBUCLG`, `COBULG`. Sample job `SYS2.JCLLIB(TESTCOB)`.
- `COBUCL` = step `COB` (PGM=IKFCBL00, PARM='LOAD,SUPMAP,...') + step `LKED`
  (PGM=IEWL, SYSLIB=SYS1.COBLIB). Override with `//COB.SYSIN` and
  `//LKED.SYSLMOD DD DSN=HERC01.MIG.LOAD(MIGMATCH),DISP=SHR`.
- **Not supported** (verified): `FILE STATUS` → `IKF1017I-E FILE INVALID IN
  SELECT CLAUSE` (job 4). From the language level: no `EVALUATE`, no
  `END-IF`/`END-READ`, no inline `PERFORM`, no intrinsic `FUNCTION`s, no
  reference modification `(1:4)`, no `SIGN ... SEPARATE`, no `STRING`.
- **Supported** (verified): `SELECT f ASSIGN TO UT-S-ddname`, `RECORDING MODE
  IS F`, `LABEL RECORDS ARE STANDARD`, `BLOCK CONTAINS 0 RECORDS`, 77/88 levels,
  `REDEFINES`, `NUMERIC` class test, `PERFORM ... UNTIL`, `READ ... AT END`,
  `WRITE ... FROM`, `DISPLAY` (to `SYSOUT` DD), and **`MOVE n TO RETURN-CODE`**,
  which becomes the step RC (job 5: `RC= 0008`).
- 77-level items must come **before** any 01 item in WORKING-STORAGE
  (`IKF2030I-C`).
- `IKF4072I-W EXIT FROM PERFORMED PROCEDURE ASSUMED` is a harmless warning,
  so a clean compile ends **RC 0004**.
- No native VSAM in this COBOL. The `VSAMIO` call routine (SYSC.LINKLIB) is
  **not cataloged** on TK5 (`LISTCAT LEVEL(SYSC)` → not found). So the project
  unloads the KSDS with IDCAMS and COBOL reads a sequential file.

## 4. SORT = OS/360 Sort/Merge for MVS 3.8 (not DFSORT)
- Procedure `SORT` in SYS2.PROCLIB → `PGM=IERRCO00`, SORTWK allocated
  dynamically. DD names `SORTIN`, `SORTOUT`, `SYSIN`, `SYSOUT`.
- `SORT FIELDS=(1,80,CH,A)` works (jobs 7, 19–34). Version 1.04 on the test
  system; the TK5 manual says Update 5 has 1.05.
- **`SUM FIELDS=NONE` and `EQUALS` are not available.** The Sort/Merge guide
  lists no SUM statement, and a job with `SORT ...,EQUALS` + `SUM FIELDS=NONE`
  abended **S0C1** (job 6). Duplicate removal is therefore done in COBOL. The
  sort uses the whole record as the key so the order is deterministic.
- Sort order is **EBCDIC** (letters sort before digits).
- No ICETOOL. Counting is done by COBOL and REXX.

## 5. REXX = BREXX/370 V2R5M3
- Batch procedures: `RXBATCH` (PGM=BREXX, exec read from DD `RXRUN` =
  `&SLIB(&EXEC)`) and `RXTSO` (under IKJEFT01). The project uses
  `//REXXRUN EXEC RXBATCH,EXEC=MIGREXX,SLIB='HERC01.MIG.REXX'` and adds DDs as
  `//EXEC.ddname DD ...` (the proc step is named `EXEC`).
- The exec must be a **PDS member**. An inline `//EXEC.RXRUN DD *` gave no
  output (job 8). An FB 80 PDS works (job 11).
- `exit n` sets the step RC (job 11: `RC= 0008`). A REXX syntax error gives
  RC = the REXX error number (job 9: RC 13).
- `"EXECIO * DISKR dd (STEM x."` and `"EXECIO * DISKW dd (STEM x."` work
  (count in `x.0`). **EXECIO strips trailing blanks** from records it reads,
  so always pad with `left(rec, lrecl)` before using fixed columns.
- Work as expected: `date('S')`, `time('N')`, `format()`, `datatype()`,
  `translate()`, `space()`, `%`, `>>`, `signal on novalue/syntax`, `sigl`.
- **`datatype(x,'W')` fails for numbers above 2**31** (15-digit totals were
  rejected). Use `verify(x,'0123456789') = 0`.
- **`||` must not be used**: the `|` character is garbled by the card-reader
  translation, giving "Error 13 Invalid character" (job 9). Concatenate by
  abuttal instead: `a''b`, `x'-'y`.
- VSAM: host command `VSAMIO` (KSDS only): `"VSAMIO OPEN dd (READ"`,
  `"VSAMIO READ dd (NEXT VAR rec"`, `"VSAMIO CLOSE dd"`. RC 0 is OK, 4 means
  not found or EOF, 8 is an error. Keys must not contain blanks, and the
  cluster must not be empty. Verified with MIGHIST (job 26).

## 6. VSAM / IDCAMS on MVS 3.8
- `DEFINE CLUSTER` **needs `UNIQUE`** (and `VOLUMES(TSO001)`). Without it:
  `IDC3025I INSUFFICIENT SUBALLOCATION DATA SPACE` (job 12).
- `REPRO` into an empty KSDS works (load). A **duplicate or out-of-sequence
  key** gives `IDC3314I RECORD ... OUT OF SEQUENCE`, step **RC 8**, and the
  other records are still loaded (job 13). The project uses this to catch
  duplicate keys in the target.
- `REPRO` into a non-empty KSDS works when the new keys are ascending and new.
  Audit keys are `batch-id` and `batch-id + 5-digit sequence`.
- `PRINT INDATASET(x) CHARACTER` and `DELETE ... CLUSTER PURGE` /
  `NONVSAM` / `GDG FORCE` work. Use `SET MAXCC = 0` after deletes that may
  find nothing.

## 7. GDG on MVS 3.8
- `DEFINE GDG (NAME(..) LIMIT(10) SCRATCH NOEMPTY)` works.
- A new generation `(+1)` needs a **pattern DSCB**. Without one:
  `IEF218I PATTERN DSCB RECORD NOT FOUND IN VTOC` (job 12). Fix (verified,
  job 14): create a cataloged model dataset on the catalog volume (TSO001),
  `HERC01.MIG.GDGMODEL`, and code
  `DCB=(HERC01.MIG.GDGMODEL,RECFM=FB,LRECL=80,BLKSIZE=3120)` on the `(+1)` DD.

## 8. JCL on MVS 3.8
- **No `IF/THEN/ELSE/ENDIF`, no `SET`, no `JCLLIB`, no in-stream symbols.**
  Use `COND=`:
  - run only if REXXRUN RC ≤ 4: `COND=(4,LT,REXXRUN.EXEC)`
  - run only if REXXRUN RC > 4: `COND=(4,GE,REXXRUN.EXEC)`
  - skip if RC ≥ 16: `COND=(16,LE,REXXRUN.EXEC)`
  - always run: `COND=EVEN`
- After an abend, later steps are bypassed unless they have `COND=EVEN`.
- A JCL error in any step (e.g. dataset not found) flushes the rest of the job.
- Use `DD DATA,DLM=$$` for inline data that contains `//` or `/*`.
- Job names ≤ 8 characters (the project uses userid + 1 letter).

## Sources
- *TK5 Introduction and User Manual* (Rob Prins, Thomas Armstrong, Feb 2026),
  supplied by the user: chapters 9–14.
- BREXX/370 V2R5M3 User's Guide and VSAM Guide (in TK5's `doc` folder).
- OS/360 Sort/Merge for MVS 3.8 Application Programming Guide (Jay Moseley site).
- Jay Moseley, "VSAM File Access for COBOL" — explains the COBOL VSAM limitation.
- Test system: github.com/patrickraths/MVS-TK5 (TK5 Update 4 DASD images),
  SDL Hercules 4.9.1 built from github.com/SDL-Hercules-390/hyperion.
