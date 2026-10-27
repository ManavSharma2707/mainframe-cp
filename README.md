# Legacy-to-Modern Data Migration Validator — TK5 edition

A pre-cutover approval gate for a data migration, running on **MVS 3.8J (TK5)**
under the Hercules emulator. It uses **SORT, COBOL, REXX (BREXX), JCL and
VSAM**, with Python for test data, automation and a Streamlit dashboard.
No DB2 and no Zowe are involved, and everything stays on your own PC.

| Read this | For |
|---|---|
| `docs/USER_MANUAL.md` | running everything by hand, step by step |
| `docs/PROMPT.md` | a ready-made step-by-step install and demo prompt |
| `docs/CONTEXT_*.md` | background: TK5 facts, design, coding rules |

Quick start (TK5 running, from the `python` folder):
```
copy config.example.json config.json   (set tk5_dir to your mvs-tk5 folder)
py check_tk5.py
py deploy.py all
py run_batch.py --scenario seeded      -> REJECTED, RC 8, verified
py -m streamlit run app.py
```
Tested on a real TK5 (Update 4, Hercules 4.9.1): all five scenarios
matched the independent Python reference exactly.
