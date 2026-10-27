"""
test_offline_logic.py - runs the REAL COBOL (GnuCOBOL, -std=ibm) and the
REAL REXX (Regina) on all scenarios WITHOUT TK5, and compares the result
with the Python reference implementation.

    python tests/test_offline_logic.py

Emulated (standard utilities, not our code): the SORT steps (EBCDIC order),
the IDCAMS REPRO into/out of the target KSDS (duplicate keys rejected).
Needs: cobc (GnuCOBOL 3.x) and regina (Regina REXX). Linux / WSL / macOS.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
import gen_data                       # noqa: E402
import validator_core as vc           # noqa: E402

COBOL = ROOT / "mainframe" / "cobol" / "MIGMATCH.cbl"
REXX = ROOT / "mainframe" / "rexx" / "MIGREXX.rexx"

# Regina replacement for the two EXECIO routines. Like BREXX, it strips
# trailing blanks from records it reads.
SHIM = r'''
ReadAll:
   parse arg zzdd
   zzp = value('MIGDIR',,'ENVIRONMENT')'/'zzdd
   io.0 = 0
   zzn = 0
   do while lines(zzp) > 0
      zzn = zzn + 1
      io.zzn = strip(linein(zzp), 'T')
   end
   call lineout zzp
   io.0 = zzn
   return

WriteAll:
   parse arg zzdd
   zzp = value('MIGDIR',,'ENVIRONMENT')'/'zzdd'.out'
   address system 'rm -f' zzp
   do zzi = 1 to out.0
      call lineout zzp, out.zzi
   end
   call lineout zzp
   return
'''


def fixed(path: Path, lines: list[str], lrecl: int) -> None:
    path.write_bytes(b"".join(l.ljust(lrecl)[:lrecl].encode("ascii")
                              for l in lines))


def read_fixed(path: Path, lrecl: int) -> list[str]:
    b = path.read_bytes().decode("ascii")
    return [b[i:i + lrecl] for i in range(0, len(b), lrecl)]


def run_case(name: str, src: list[str], tgt: list[str], work: Path,
             exe: Path) -> list[str]:
    d = work / name
    d.mkdir()
    # SORTSRC / SORTTGT: SORT FIELDS=(1,80,CH,A) in EBCDIC
    ssorted = sorted(src, key=vc.ebcdic_key)
    tsorted = sorted(tgt, key=vc.ebcdic_key)
    # LOADKSDS + UNLOAD: the KSDS keeps the first record of each key
    ksds, seen = [], set()
    for t in tsorted:
        if t[:18] not in seen:
            seen.add(t[:18])
            ksds.append(t)
    fixed(d / "SRCIN", ssorted, 80)
    fixed(d / "TGTIN", ksds, 80)
    env = dict(os.environ, **{f"DD_{n}": str(d / n) for n in
                              ("SRCIN", "TGTIN", "DEDUP", "EXCOUT", "CTLOUT")})
    p = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    if p.returncode not in (0, 12):
        return [f"COBOL RC {p.returncode}: {p.stdout}{p.stderr}"]
    (d / "SRCRAW").write_text("".join(l + "\n" for l in src))
    (d / "TGTRAW").write_text("".join(l + "\n" for l in tgt))
    (d / "CTLIN").write_text(read_fixed(d / "CTLOUT", 150)[0] + "\n")
    (d / "EXCIN").write_text("".join(l + "\n" for l in read_fixed(d / "EXCOUT", 100)))
    rx = work / "migrexx_test.rexx"
    rx.write_text(REXX.read_text().split("/* ==IO-BEGIN==")[0] + SHIM)
    p = subprocess.run(["regina", str(rx)], env=dict(os.environ, MIGDIR=str(d)),
                       capture_output=True, text=True)
    oracle = vc.reconcile(src, tgt)
    if p.returncode != oracle.rc:
        return [f"REXX RC {p.returncode} expected {oracle.rc}\n{p.stdout}{p.stderr}"]
    kv, exc = vc.parse_migout((d / "MIGOUT.out").read_text())
    errors = vc.compare_to_oracle(kv, exc, oracle)
    for dd, w in (("EXCSORT", 100), ("REPORT", 133), ("MIGOUT", 133),
                  ("AUDREC", 120), ("EXCREC", 120)):
        for ln in (d / f"{dd}.out").read_text().splitlines():
            if len(ln) > w:
                errors.append(f"{dd}: record longer than LRECL {w}")
                break
    keys = [ln[:20] for ln in (d / "EXCREC.out").read_text().splitlines()]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        errors.append("EXCREC keys are not unique and ascending (REPRO would fail)")
    if " " in "".join(k.strip() for k in keys):
        errors.append("EXCREC key contains a blank")
    return errors


def edge_cases() -> dict[str, tuple[list[str], list[str]]]:
    def S(c, a, n, b, d, s):
        return (c.ljust(8) + a.ljust(10) + n.ljust(20) + b + d + s).ljust(80)

    def T(c, a, n, b, d, s):
        return (c.ljust(8) + a.ljust(10) + n.ljust(30) + b.ljust(12) + d + s).ljust(80)
    ok_s = S("C0000001", "A000000001", "ASHA RAO", "00000500000", "20260101", "A")
    ok_t = T("C0000001", "A000000001", "ASHA RAO", "000005000.00", "2026-01-01", "A")
    return {
        "edge_badfmt": (
            [ok_s, S("C0000002", "A000000002", "BAD BAL", "00000100000", "20260102", "A"),
             S("C0000003", "A000000003", "BAD DATE", "00000100000", "20260103", "A"),
             S("C0000004", "A000000004", "SRC NONNUM", "0000010000X", "20260104", "A"),
             S("C0000005", "A000000005", "O'NEIL", "00000100000", "20260105", "A")],
            [ok_t, T("C0000002", "A000000002", "BAD BAL", "1000.00", "2026-01-02", "A"),
             T("C0000003", "A000000003", "BAD DATE", "000001000.00", "2026/01/03", "A"),
             T("C0000004", "A000000004", "SRC NONNUM", "000001000.00", "2026-01-04", "A"),
             T("C0000005", "A000000005", "O'NEIL X", "000001000.00", "2026-01-05", "A")]),
        "edge_empty_tgt": ([ok_s], []),
        "edge_empty_src": ([], [ok_t]),
        "edge_interleaved": (
            [S("C0000001", "A000000001", "A", "00000000100", "20260101", "A"),
             S("C0000003", "A000000003", "C", "00000000300", "20260101", "A")],
            [T("C0000002", "A000000002", "B", "000000002.00", "2026-01-01", "A"),
             T("C0000003", "A000000003", "C", "000000003.00", "2026-01-01", "A")]),
    }


def main() -> int:
    if not (shutil.which("cobc") and shutil.which("regina")):
        print("cobc/regina not installed - skipped")
        return 0
    work = Path(tempfile.mkdtemp(prefix="migtk5_"))
    exe = work / "migmatch"
    subprocess.run(["cobc", "-x", "-std=ibm", "-o", str(exe), str(COBOL)],
                   check=True, capture_output=True)
    bad = 0
    cases = {}
    for sc in gen_data.SCENARIOS:
        d = gen_data.write_scenario(sc, work / "data")
        cases[sc] = (vc.read_lines(str(d / "src_extract.txt")),
                     vc.read_lines(str(d / "tgt_extract.txt")))
    cases.update(edge_cases())
    for name, (src, tgt) in cases.items():
        errs = run_case(name, src, tgt, work, exe)
        print(f"{name:17s}", "PASS" if not errs else "FAIL")
        for e in errs:
            print("   -", e)
        bad += bool(errs)
    shutil.rmtree(work, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
