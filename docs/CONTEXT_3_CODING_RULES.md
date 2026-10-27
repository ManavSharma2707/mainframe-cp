# Context 3 — Rules for changing code safely on TK5

## Workflow for any change
1. Edit the file in `mainframe/` (never edit `build/`, which is generated).
2. Run the local tests:
   - `python tests/test_python.py`
   - `python tests/test_offline_logic.py` (needs GnuCOBOL + Regina; on
     Windows use WSL)
3. Run `python python/deploy.py build`. It recompiles and reloads the REXX.
   COB RC must be ≤ 4 and LKED RC 0.
4. Run `python python/run_batch.py --scenario seeded`. It must print
   "verified".
5. Run `python tests/test_tk5_live.py --no-setup` to check all scenarios.
6. If the reference implementation (`validator_core.py`) and TK5 disagree,
   work out which one is wrong from the job output in `runs/<batch>/joblog.txt`.
   Fix that one, and keep both identical.

## COBOL (IKFCBL00, COBOL-68)
- Fixed format: columns 1-6 blank, 7 indicator (`*` for comments), code in
  8-72. Upper case only. No tabs.
- Use `SELECT x ASSIGN TO UT-S-DDNAME.` Do not use FILE STATUS, EVALUATE,
  END-IF / END-READ, inline PERFORM, FUNCTION, reference modification,
  STRING, or `SIGN SEPARATE`.
- Put all 77-level items before the first 01 in WORKING-STORAGE.
- Every IF ends at the period. For nested logic use `IF ... ELSE IF ...` in
  one sentence, or PERFORM a paragraph. Put `READ ... AT END ...` in its own
  sentence (the AT END clause ends at the period).
- Use REDEFINES instead of reference modification (see `TGT-BAL-TXT`,
  `TGT-DATE-TXT`).
- End with `MOVE n TO RETURN-CODE` and `STOP RUN`.
- Expect `IKF4072I-W` warnings, so the compile ends RC 4. Anything `-E` or
  `-C` must be fixed.
- GnuCOBOL check: `cobc -x -std=ibm MIGMATCH.cbl`. It maps `UT-S-SRCIN` to
  the environment variable `DD_SRCIN`.

## REXX (BREXX/370)
- The first line is `/* REXX */`. Keep lines ≤ 72 columns.
- **Never use `|` or `||`.** Concatenate by abuttal (`a''b`, `x'-'y`) or with
  a blank (`a b`).
- EXECIO strips trailing blanks, so use `left(io.i, lrecl)` before `substr`.
- Use `verify(s,'0123456789') = 0` for big numbers, not `datatype(s,'W')`.
- Keep the `ReadAll` / `WriteAll` routines last, between the
  `==IO-BEGIN==` / `==IO-END==` markers. The offline test replaces them
  with a Regina version.
- Exit codes 0/4/8/12 are decisions. Use 16 for any internal failure (`Die`,
  `FATAL`).
- VSAMIO keys must not contain blanks.

## JCL (MVS 3.8)
- Use `COND=` (no IF/THEN). `COND=(code,op,step.procstep)` means **skip** the
  step when *code op RC* is true.
- KSDS: always `INDEXED UNIQUE ... VOLUMES(@VOL@)`.
- GDG (+1): `DCB=(@HLQ@.MIG.GDGMODEL,RECFM=..,LRECL=..,BLKSIZE=..)`.
- Inline data containing `//` or `/*`: `DD DATA,DLM=$$` and a `$$` line.
- Statements ≤ 71 columns, cards ≤ 80. Use the tokens `@HLQ@`, `@PASSWORD@`,
  `@CLASS@`, `@MSGCLASS@`, `@UNIT@`, `@VOL@`.
- Keep `MSGCLASS=A` for automation (output goes to `prt/prt00e.txt`).

## Python
- Python 3.10+. The only dependencies are `streamlit` and `pandas`.
- Files are written with LF line ends and ASCII. Cards are exactly 80
  columns.
- New scenario: add it to `gen_data.SCENARIOS` and `EXPECT`, and to
  `tests/test_tk5_live.py` EXPECT.
