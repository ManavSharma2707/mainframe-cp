"""
check_tk5.py - verifies that YOUR TK5 matches what this project expects.
Run it once before deploy.py.        python check_tk5.py
Checks: card reader reachable, printer file found, job runs under your
userid, procedures COBUCL / RXBATCH / SORT exist, BREXX installed, sort works.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import render
from tk5client import TK5, TK5Error

HERE = Path(__file__).resolve().parent


def main() -> int:
    try:
        cfg = render.load_config(HERE / "config.json")
        tk = TK5(cfg)
        tk.check()
        print("OK   card reader", f"{tk.host}:{tk.port}", "and printer", tk.prt)
        res = tk.run(render.render_job("CHECK", cfg), timeout=300)
    except (render.ConfigError, TK5Error) as e:
        print("FAIL", e)
        return 1
    t = res.text
    checks = {
        "job ran (no JCL error, no RAKF/password problem)":
            not res.jcl_error and res.rc("LIST") is not None,
        "procedure COBUCL (COBOL compile+link)": re.search(r"^\s+COBUCL\s*$", t, re.M),
        "procedure RXBATCH (BREXX batch)": re.search(r"^\s+RXBATCH\s*$", t, re.M),
        "procedure SORT (OS/360 Sort/Merge)": re.search(r"^\s+SORT\s*$", t, re.M),
        "BREXX libraries cataloged": "RXLIB" in t,
        "sort step ended RC 0": res.rc("SORTCHK", "SORT") == "RC= 0000",
    }
    bad = 0
    for k, v in checks.items():
        print("OK  " if v else "FAIL", k)
        bad += not v
    m = re.search(r"BREXX\.(V\dR\dM\d)\.RXLIB", t)
    if m:
        print("info BREXX version", m.group(1))
    m = re.search(r"Sort/Merge for MVS 3\.8 Version ([\d.]+)", t)
    if m:
        print("info OS/360 Sort/Merge version", m.group(1))
    if bad:
        (HERE.parent / "runs").mkdir(exist_ok=True)
        (HERE.parent / "runs" / "CHECK_output.txt").write_text(t)
        print("see runs/CHECK_output.txt")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
