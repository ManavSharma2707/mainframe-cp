"""
history.py - runs the HIST job (BREXX VSAMIO reads MIG.AUDIT.KSDS) and
prints the validation history stored in VSAM.   python history.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import render
from tk5client import TK5, TK5Error

HERE = Path(__file__).resolve().parent


def fetch(cfg: dict) -> list[str]:
    tk = TK5(cfg)
    tk.check()
    res = tk.run(render.render_job("HIST", cfg))
    block = res.block("MIGHIST-BEGIN", "MIGHIST-END")
    if block is None:
        raise TK5Error("no history block in the output (has MIGRUN run yet?)")
    return [ln for ln in block.splitlines()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    a = ap.parse_args()
    try:
        for ln in fetch(render.load_config(Path(a.config))):
            print(ln[5:] if ln.startswith("HIST:") else ln)
    except (render.ConfigError, TK5Error) as e:
        print("ERROR:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
