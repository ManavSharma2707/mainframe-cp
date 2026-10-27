# CLAUDE.md — Legacy-to-Modern Data Migration Validator (TK5 edition)

You are helping a beginner finish a college mainframe course project.
Read this file first, then `docs/CONTEXT_1_TK5_FACTS.md`,
`docs/CONTEXT_2_DESIGN.md` and `docs/CONTEXT_3_CODING_RULES.md` before you change
anything. The user manual for doing everything by hand is `docs/USER_MANUAL.md`.

## What the project is
A pre-cutover approval gate for a data migration, running as one batch job
(`MIGRUN`) on **MVS 3.8J (TK5) under the Hercules emulator** on the user's own PC.
It validates a legacy extract against the converted target. Duplicates are
removed, both sides are matched by key, and every exception is listed. The
counts are cross-checked, and the job ends RC 0 / 4 / 8 / 12, which drives an
APPROVE / REJECT gate. Course topics covered: **SORT (OS/360 Sort/Merge, the
TK5 stand-in for DFSORT), COBOL, REXX (BREXX/370), JCL, VSAM**. Python is used
for test data, automation and a Streamlit UI. **DB2 is NOT used.** The
professor said no DB2, so VSAM KSDS replaces the DB2 target table and the
audit tables.

## Hard rules (never break)
1. Work only on the user's **local TK5**. Never connect to the college
   mainframe, IBM servers, Zowe, z/OSMF or any DB2.
2. Create, change or delete datasets **only under `<HLQ>.MIG.*`** (HLQ =
   the TSO userid, default `HERC01`). Never modify `SYS1.*`, `SYS2.*`, `BREXX.*`
   or any other system dataset. Reading the system procedure libraries is fine.
3. Never edit TK5's own files (DASD images, `conf/`, scripts). The one
   exception: you may *read* `conf/tk5.cnf` to find the reader port.
4. Only `python/deploy.py setup` (SETUP job) deletes the audit history. Ask
   the user before running it again after the first time.
5. Do not "fix" a mainframe source to make a test pass without telling the user
   what was wrong. Show the job output that proves the problem.
6. Keep the characters `| \ [ ] ^ ~ ` ! { }` out of all JCL, COBOL, REXX and
   data. The card reader's ASCII→EBCDIC translation garbles them. `render.py`
   lints this.

## Status: built and tested
Everything here was run on a real TK5 (Update 4, Hercules 4.9.1). Results:
- **Live end-to-end on TK5:** `tests/test_tk5_live.py` ran SETUP and BUILD,
  all 5 scenarios and the VSAM history. All 5 scenarios gave the expected
  decision, and every run was **identical** to the independent Python reference
  implementation (all counts and every exception row).
- **Offline:** `tests/test_offline_logic.py` runs the real COBOL (GnuCOBOL
  `-std=ibm`) and REXX (Regina) on 9 cases, all PASS.
- **Unit tests:** `tests/test_python.py` has 11 tests, all pass.
The user's TK5 may be a newer update. Run `python python/check_tk5.py` first.

## Layout
```
mainframe/jcl/     CHECK SETUP BUILD MIGRUN HIST   (templates with @TOKENS@)
mainframe/cobol/   MIGMATCH.cbl   COBOL-68 style for IKFCBL00
mainframe/rexx/    MIGREXX.rexx (decision, report, audit records)
                   MIGHIST.rexx (reads VSAM audit KSDS via BREXX VSAMIO)
python/            render.py tk5client.py deploy.py run_batch.py history.py
                   submit.py check_tk5.py gen_data.py validator_core.py app.py
tests/             test_python.py test_offline_logic.py test_tk5_live.py
docs/              CONTEXT_1..3, PROMPT.md, USER_MANUAL.md
build/ data/ runs/ generated (git-ignored)
```

## How things run (no Zowe)
- **Submit:** send the JCL text to the Hercules card reader socket
  (device `000C`, port `3505`, `ascii trunc eof`). See `python/tk5client.py`.
- **Output:** jobs use `MSGCLASS=A`, which goes to the printer file
  `<tk5_dir>/prt/prt00e.txt`. A job is finished when
  `****A   END   JOB nnn JOBNAME` appears. Step RCs come from the
  `IEFACTRT` lines.
- **Results:** REXX writes `MIG.RECON.MIGOUT`, which is printed between
  `MIGOUT-BEGIN` and `MIGOUT-END`. `run_batch.py` parses that block into
  `runs/<BATCH_ID>/`.

## Commands (from the `python` folder)
```
cp config.example.json config.json   # set tk5_dir to the mvs-tk5 folder
python check_tk5.py                  # environment check (read-only job)
python deploy.py all                 # SETUP (once) + BUILD
python run_batch.py --scenario seeded   # REJECTED RC 8 (also: dups clean conflict dup_target)
python history.py                    # VSAM audit history (BREXX VSAMIO)
streamlit run app.py                 # UI
python ../tests/test_python.py ; python ../tests/test_tk5_live.py
```

## Expected results
| scenario | decision | RC | key numbers |
|---|---|---|---|
| seeded | REJECTED | 8 | 1020 raw, 20 identical dups, 1000 unique, 995 target, 975 matched, 15 changed, 10 missing, 5 extra |
| dups | WARNING | 4 | 20 identical duplicates only |
| clean | APPROVED | 0 | everything matches |
| conflict | REJECTED | 8 | 3 DUPKEY (same key, different data) |
| dup_target | ABORTED | 12 | VSAM REPRO rejected 1 duplicate target key (LOADKSDS RC 8) |
