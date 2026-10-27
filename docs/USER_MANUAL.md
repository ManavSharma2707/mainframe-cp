# User manual — running the Migration Validator by hand on TK5

This manual gets you from "TK5 installed" to a finished, demonstrable
project with no AI help. Steps marked **[CHECK]** tell you what you must see
before moving on. Everything runs on your own PC. Nothing touches IBM or the
college system.

---------------------------------------------------------------------------
## 0. What you need
| Item | Notes |
|---|---|
| TK5 | the `mvs-tk5` folder (you already have it). Start with `mvs.bat` (Windows) |
| 3270 terminal | CryptoTerm, wc3270 or Vista TN3270 → host `localhost`, port `3270` |
| Python 3.10 or newer | https://www.python.org. On Windows tick "Add python to PATH" |
| This project | the `migvalid-tk5` folder, anywhere on your PC |

Install the two Python libraries once (Command Prompt in the project folder):
```
cd migvalid-tk5\python
py -m pip install -r requirements.txt
```

---------------------------------------------------------------------------
## 1. Start TK5 and log on (every session)
1. Double-click `mvs.bat` in the `mvs-tk5` folder. A console window opens and
   MVS IPLs. Wait 1–2 minutes until the messages stop scrolling.
2. In CryptoTerm, open a TN3270 session to `localhost` port `3270`. If you
   see the TK5 logo, press **RESET** and then **CLEAR**.
3. At the logon prompt type `HERC01`, Enter, password `CUL8TR`, Enter. Press
   Enter through the welcome screens until the **ISPF Primary Option Menu**
   appears.
**[CHECK]** You see the ISPF menu. TK5 is running and its card reader
(port 3505) is ready.

To stop TK5 later: in ISPF press **PF3** to reach `READY`, type `SHUTDOWN`,
Enter, then `LOGOFF`.

---------------------------------------------------------------------------
## 2. Configure the project (once)
1. Copy `python\config.example.json` to `python\config.json`.
2. Open `config.json` in Notepad and set:
   - `"tk5_dir"`: your TK5 folder, with forward slashes, e.g. `"C:/mvs-tk5"`
     or `"D:/TK5/mvs-tk5"` (the folder that contains `prt\prt00e.txt`).
   - Leave `hlq` = `HERC01` and `password` = `CUL8TR` (TK5 defaults).
   - `reader_port` stays `3505` unless your `conf\tk5.cnf` shows another
     number on the `000C 3505` line.
3. Create all the jobs:
```
py render.py
```
**[CHECK]** It prints `rendered ...` for CHECK, SETUP, BUILD, HIST and five
MIGRUN files in `build\jcl\`. Open `build\jcl\MIGRUN_SEEDED.jcl` in Notepad
and look at it. This is the real JCL that runs on MVS. It has 2,000+ lines
because the test data travels inside the job as card images.

---------------------------------------------------------------------------
## 3. How to submit a job and where to see its output
Every job file in `build\jcl\` can be submitted in **either** of two ways.

**Way A: helper script (easiest)**
```
py submit.py ..\build\jcl\CHECK.jcl --wait C:/mvs-tk5
```
This sends the file to the card reader and waits. It then prints each step
with its return code.

**Way B: no Python, through the Hercules console**
In the Hercules console window (or the web console at
`http://localhost:8038`), type:
```
devinit 00c C:\path\to\migvalid-tk5\build\jcl\CHECK.jcl ascii trunc eof
```
The job runs. Then **put the reader back** so Way A works again:
```
devinit 00c 3505 sockdev ascii trunc eof
```

**Where is the output?** All jobs use `MSGCLASS=A`. Their whole output (JCL
listing, messages, step return codes, printed reports) is appended to the
file **`mvs-tk5\prt\prt00e.txt`** on your PC. Open it in Notepad++ or VS Code
and search for your job name (e.g. `HERC01V`). The **step table** near the
top of each job is the most important part:
```
 8.41.51 JOB   21  HERC01V    MATCH               MIGMATCH  RC= 0000
 8.41.51 JOB   21  HERC01V    REXXRUN   EXEC      BREXX     RC= 0008
```
`RC=` is the return code, `AB Sxxx` means an abend, and `*FLUSH*` means the
step was skipped on purpose (COND) or after an error.

*Tip:* to read output inside TSO instead, change `"msgclass"` to `"H"` in
`config.json` and run `py render.py` again. Jobs are then held in JES2, and
you view them in RFE/RPF (see section 8). Way A's `--wait` needs class A, so
switch back afterwards.

---------------------------------------------------------------------------
## 4. Check your TK5 (read-only, 1 minute)
```
py check_tk5.py
```
**[CHECK]** All lines `OK`: procedures COBUCL, RXBATCH, SORT, BREXX
libraries, sort RC 0. It also prints your BREXX and Sort/Merge versions.

---------------------------------------------------------------------------
## 5. Install: SETUP once, BUILD after any code change
```
py deploy.py all
```
Or by hand: submit `build\jcl\SETUP.jcl`, then `build\jcl\BUILD.jcl`.

| Job | What it does | **[CHECK]** expected step results |
|---|---|---|
| SETUP (HERC01S) | IDCAMS deletes old objects (`SET MAXCC=0`), DEFINE GDG ×2, DEFINE CLUSTER AUDIT.KSDS + EXCLOG.KSDS (`UNIQUE`, volume TSO001), IEFBR14 allocates GDGMODEL and LOAD | DELETE, DEFINE, ALLOC all `RC= 0000` |
| BUILD (HERC01B) | IEBUPDTE loads COBOL into `HERC01.MIG.SOURCE` and both REXX execs into `HERC01.MIG.REXX`. `COBUCL` compiles (IKFCBL00) and link-edits (IEWL) into `HERC01.MIG.LOAD(MIGMATCH)` | LOADCOB/LOADRX 0000, `COMPILE COB RC= 0004` (warnings only), `COMPILE LKED RC= 0000` |

SETUP **erases the audit history**, so run it again only to start over.

---------------------------------------------------------------------------
## 6. Run a validation (job MIGRUN)
```
py run_batch.py --scenario seeded
```
By hand: submit `build\jcl\MIGRUN_SEEDED.jcl` (Way A or B) and read
`prt00e.txt`.

What each step does and what you should see for **seeded**:
| Step | Program | Purpose | RC |
|---|---|---|---|
| CLEAN | IDCAMS | deletes the work datasets of the last run | 0 |
| LOADSRC / LOADTGT | IEBGENER | writes the inline cards to SRC.EXTRACT / TGT.EXTRACT | 0 |
| SORTSRC / SORTTGT | SORT (IERRCO00) | sorts both files by key (whole record) | 0 |
| DEFKSDS | IDCAMS | DEFINE CLUSTER TGT.KSDS (the "modern system table") | 0 |
| LOADKSDS | IDCAMS | REPRO target into the KSDS (VSAM rejects duplicate keys) | 0 |
| UNLOAD | IDCAMS | REPRO KSDS to TGT.UNLOAD in key order | 0 |
| MATCH | MIGMATCH (COBOL) | drops duplicates, match-merges, writes exceptions + control record | 0 |
| REXXRUN | BREXX MIGREXX | cross-checks every count, sorts exceptions, decides | **8** |
| AUDIT | IDCAMS | REPRO the audit records into the two VSAM logs | 0 |
| APPROVE | IEBGENER | runs only if RC ≤ 4 | `*FLUSH*` |
| REJECT | IEBGENER | exceptions into GATE.REJECTED(+1) | 0 |
| PRINTRPT / PRINTOUT | IEBGENER | prints the report and the result block | 0 |

**[CHECK]** In `prt00e.txt` find `MIGRATION VALIDATION REPORT`:
```
 DECISION  : REJECTED (RC 8)  DO NOT CUT OVER
   Source records in extract .....      1,020
   Identical duplicates dropped ..         20
   Unique source records .........      1,000
   Target records in VSAM KSDS ...        995
   Matched .......................        975
   Mismatched records ............         15
   Missing in target .............         10
   Extra in target ...............          5
```
followed by 30 exception rows sorted MISSING → MISMATCH → EXTRA.
`run_batch.py` also prints `TK5 result == Python reference result (verified)`.

Run the other scenarios the same way:
| Scenario file | Expected | What it shows |
|---|---|---|
| MIGRUN_CLEAN | APPROVED, RC 0, APPROVE step runs | the happy path. GATE.APPROVED gets a new generation |
| MIGRUN_DUPS | WARNING, RC 4, APPROVE runs | identical duplicates are dropped and counted |
| MIGRUN_CONFLICT | REJECTED, RC 8 | 3 DUPKEY rows: same key, different data |
| MIGRUN_DUP_TARGET | ABORTED, RC 12, LOADKSDS RC 8 | VSAM refused a duplicate key, and REXX caught the count difference |

---------------------------------------------------------------------------
## 7. VSAM audit history
```
py history.py
```
By hand: submit `build\jcl\HIST.jcl`. The BREXX exec MIGHIST opens
`HERC01.MIG.AUDIT.KSDS` with `VSAMIO` and prints one line per batch. IDCAMS
then prints the raw KSDS records.
**[CHECK]** One `HIST:` line per successful MIGRUN, with decision and counts.

---------------------------------------------------------------------------
## 8. Looking at your datasets in TSO (CryptoTerm)
- **RPF dataset list:** in ISPF type option `3.4R` (or type `RPF` at READY
  and choose the DSLIST option). Use the dataset level `HERC01.MIG`. You see
  SOURCE, REXX, LOAD, the extracts, the KSDS clusters and the GDG
  generations `GATE.APPROVED.G0001V00` etc. Put `B` (browse) next to one,
  e.g. `HERC01.MIG.RECON.REPORT`.
- **Edit and submit a small job yourself:** in RPF edit a member such as
  `HERC01.MIG.SOURCE(MYJOB)`, type JCL, and enter `SUB` on the command line.
- **Held output** (if you set msgclass H): RFE / RPF OUTLIST option.
- **VSAM from TSO:** at READY, `LISTCAT ENTRIES('HERC01.MIG.AUDIT.KSDS') ALL`.
The exact panel numbers come from the TK5 manual (chapter 12). Screens may
look slightly different on your update.

---------------------------------------------------------------------------
## 9. The dashboard (Streamlit)
```
cd migvalid-tk5\python
py -m streamlit run app.py
```
Your browser opens `http://localhost:8501`.
- **Data source → TK5 runs:** pick a batch. The banner shows the decision
  and RC. The metrics show every count.
- Tabs:
  - **Missing / Extra / Changed values:** the exception rows.
  - **Duplicates:** identical copies vs conflicting DUPKEY rows.
  - **Verification:** the TK5 result compared with the independent Python
    implementation and the answer key.
  - **Report & job log:** the REXX report and the full job output.
  - **History:** the runs on this PC, plus the "Read VSAM audit history"
    button.
- **Run on TK5** (sidebar) submits a scenario for you.
- **Offline demo** works even when TK5 is down. It is clearly labelled as
  the Python result, not TK5.

---------------------------------------------------------------------------
## 10. Changes to make in your PPT (TK5 edition)
1. **Platform:** "MVS 3.8J (TK5) on Hercules", not z/OS. DB2 is replaced by
   **VSAM KSDS**: the target table becomes TGT.KSDS, MIG_BATCH_LOG becomes
   AUDIT.KSDS, and MIG_EXCEPTION becomes EXCLOG.KSDS.
2. **DFSORT:** on TK5 it is **OS/360 Sort/Merge**, which has no `SUM` and no
   `ICETOOL`. Sorting is done by SORT, duplicate removal by COBOL. Conflicting
   duplicates are now reported (DUPKEY) instead of silently dropped, which is
   an improvement.
3. **JCL gate:** `COND=` codes, not IF/THEN/ELSE (which arrived after MVS 3.8).
4. **REXX:** BREXX/370. It also writes the VSAM audit records and reads the
   history with VSAMIO.
5. **Return codes:** 0 approved, 4 warning (identical duplicates), 8 rejected,
   12 aborted (controls disagree, e.g. VSAM rejected a key), 16 REXX failure
   (fail-safe REJECT).
6. **Results slide:** the seeded numbers stay the same
   (1,020 → 1,000; 975 / 15 / 10 / 5; REJECTED RC 8). There are 50 seeded
   defects in total, and all were caught.
7. **Layouts:** the target record is now 80 bytes (name 30, balance text
   `000001234.56`, date `YYYY-MM-DD`).

---------------------------------------------------------------------------
## 11. Five-minute demo script
1. Show TK5 running and CryptoTerm logged on as HERC01. Open the RPF DSLIST
   at `HERC01.MIG`.
2. `py run_batch.py --scenario seeded`, or submit `MIGRUN_SEEDED.jcl` by
   Way B.
3. Open `prt00e.txt`. Show the step table (SORT, IDCAMS, COBOL, BREXX, COND
   gate: APPROVE flushed, REJECT ran) and the REXX report.
4. Show the dashboard: the REJECTED banner, then Missing, Changed and
   Verification.
5. `py run_batch.py --scenario clean`. The result is APPROVED, and the
   APPROVE step wrote a GDG generation.
6. `py history.py` shows the VSAM audit log listing both batches.

---------------------------------------------------------------------------
## 12. Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `cannot connect to the TK5 card reader` | TK5 not started or still IPLing. Wait, or check the port in `conf\tk5.cnf` |
| `printer file not found` | `tk5_dir` in config.json is wrong (it must contain `prt\prt00e.txt`) |
| a job never finishes | it may be waiting for a free initiator or for class A output. Check the Hercules console. Or you used Way B and forgot to switch the reader back |
| `IEF218I PATTERN DSCB RECORD NOT FOUND` | SETUP was not run (GDGMODEL missing) |
| `IDC3025I INSUFFICIENT SUBALLOCATION DATA SPACE` | a DEFINE CLUSTER without `UNIQUE`. Use the project's JCL |
| `ICH408I` / RAKF access error | wrong USER/PASSWORD on the job card (config `hlq`/`password`) |
| `COMPILE COB RC= 0008` or higher | a COBOL error (`IKFxxxxI-E`). The listing is in prt00e.txt under COB |
| `REXXRUN RC= 0016` | REXX failure. Search prt00e.txt for `MIGREXX ERROR` or `FAILED AT LINE` |
| `Error 13 ... Invalid character` from BREXX | a `|` or `\` sneaked into the REXX (not allowed on the card reader) |
| `LOADKSDS RC= 0008` | VSAM rejected duplicate keys. This is expected only for dup_target |
| `S0C7` in MATCH | non-numeric data reached a numeric field. Check the input layout |
| streamlit not found | `py -m pip install -r requirements.txt`, then `py -m streamlit run app.py` |

---------------------------------------------------------------------------
## 13. Starting over cleanly
- **New audit history:** submit SETUP again (it deletes and redefines).
- **After changing COBOL/REXX:** run `py render.py` then `py deploy.py build`.
- **Remove everything:** in RPF DSLIST `HERC01.MIG`, delete the datasets, or
  submit an IDCAMS job with `DELETE HERC01.MIG.xxx` lines. Only `HERC01.MIG.*`.
