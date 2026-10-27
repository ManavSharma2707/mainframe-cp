# The prompt (paste into your coding assistant, opened in the `migvalid-tk5` folder)

Copy everything between the lines into the assistant. Start TK5 first and wait
until the IPL has finished (the TSO logon screen appears in your 3270
terminal).

---

```
You are helping me finish my college mainframe course project, "Legacy-to-
Modern Data Migration Validator". It runs on MY OWN local TK5 (MVS 3.8J on
the Hercules emulator). The project is already built and was tested on a real
TK5. Your job is to install it on my TK5, run it, verify it and help me
present it. I am a beginner: before every step explain in 1-2 plain sentences
what you will do, and afterwards what the output means. Keep messages short.

FIRST read these files completely, in this order, and follow them:
  README.md
  docs/CONTEXT_1_TK5_FACTS.md
  docs/CONTEXT_2_DESIGN.md
  docs/CONTEXT_3_CODING_RULES.md
  docs/USER_MANUAL.md   (what I would do by hand - use it for wording)

HARD RULES - never break them:
1. Only my local TK5. Never connect to any college mainframe, IBM server,
   Zowe, z/OSMF or DB2. DB2 is not used in this project at all.
2. Create/change/delete datasets ONLY under <HLQ>.MIG.* (HLQ from
   python/config.json, default HERC01). Never touch SYS1.*, SYS2.*, BREXX.*
   or any other system dataset, and never edit TK5's own files (dasd, conf,
   scripts). Reading conf/tk5.cnf is allowed.
3. Do not re-run "python deploy.py setup" after the first time without
   asking me (it deletes the VSAM audit history).
4. Keep the characters | \ [ ] ^ ~ ` ! { } out of JCL, COBOL, REXX and data.
5. If something fails, show me the exact message from the job output, explain
   it, propose a fix and wait for my OK before changing mainframe code.
6. Never print my passwords other than the TK5 default ones already in
   config.example.json.

STEP 1 - Check my PC (tell me what you find, fix only what is missing):
  - Python 3.10+ (on Windows "py --version" or "python --version").
  - pip install -r python/requirements.txt
  - Find my TK5 folder (the folder that contains mvs.bat / mvs, conf\,
    prt\). Ask me if you cannot find it. Read conf/tk5.cnf and confirm the
    card reader line looks like "000C 3505 ... sockdev ascii trunc eof" and
    the printer "000E 1403 prt/prt00e.txt". Tell me the port number.
  - Check that TCP port 3505 on localhost accepts a connection (TK5 must be
    running).
STEP 2 - Configure: copy python/config.example.json to python/config.json.
  Set "tk5_dir" to my TK5 folder (forward slashes are fine on Windows), and
  "reader_port" if it is not 3505. Keep hlq HERC01 / password CUL8TR unless
  I tell you another userid. Run:  cd python ; python render.py
  It must say "rendered" for every job with no lint errors.
STEP 3 - Environment check: python check_tk5.py
  Every line must be OK. Report the BREXX and Sort/Merge versions. If a check
  fails, read runs/CHECK_output.txt, explain, and stop.
STEP 4 - Install: python deploy.py all
  Expected: SETUP steps RC 0000; BUILD: LOADCOB/LOADRX 0000, COMPILE.COB
  0004 (warnings only), COMPILE.LKED 0000.
STEP 5 - Run the five scenarios one by one and show a table of the
  results (decision, RC, raw, dups, unique, target, matched, changed,
  missing, extra) plus the "verified" line:
    python run_batch.py --scenario seeded       REJECTED  RC 8
    python run_batch.py --scenario dups         WARNING   RC 4
    python run_batch.py --scenario clean        APPROVED  RC 0
    python run_batch.py --scenario conflict     REJECTED  RC 8
    python run_batch.py --scenario dup_target   ABORTED   RC 12
  For seeded the numbers must be 1020/20/1000/995/975/15/10/5.
STEP 6 - VSAM history: python history.py  (one line per batch from the KSDS)
STEP 7 - Tests: python ../tests/test_python.py  and
  python ../tests/test_tk5_live.py --no-setup . If GnuCOBOL and Regina REXX
  are available (Linux/WSL) also run python ../tests/test_offline_logic.py .
STEP 8 - UI: start "streamlit run app.py" (from the python folder), give me
  the local URL and tell me exactly what to click to show: the REJECTED
  seeded batch, the Missing / Changed / Duplicates tabs, the Verification
  tab ("identical to the independent Python implementation") and History.
STEP 9 - Presentation help: list (a) the screenshots I should take (job step
  table of MIGRUN from prt/prt00e.txt, the REXX report, the VSAM history,
  the UI tabs, and in my 3270 terminal the HERC01.MIG.* dataset list), (b)
  the slide changes from docs/USER_MANUAL.md section 9, and (c) a 5-minute
  demo script.

If my TK5 differs from the tested one (e.g. a newer Update, different port,
different userid), adapt ONLY the config, explain the difference, and re-run
check_tk5.py. Stop at the end of each STEP and wait for me to say "next".
```

---

## If you want the assistant to rebuild everything from nothing

Use the prompt above. The project already contains every file, and
rebuilding from scratch only adds risk. If you still want it, add this line:
"Before STEP 1, regenerate build/ and data/ with render.py and gen_data.py;
do not rewrite mainframe/ sources unless a check fails."
