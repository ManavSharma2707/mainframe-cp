"""
submit.py - send ANY JCL file to TK5's card reader (manual use).

    python submit.py ../build/jcl/MIGRUN_SEEDED.jcl
    python submit.py myjob.jcl --host 127.0.0.1 --port 3505 --wait C:/mvs-tk5

With --wait <mvs-tk5 folder> it waits for the job and prints the step
return codes. Without it, it only submits (look at prt/prt00e.txt).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tk5client import TK5, TK5Error


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jcl")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=3505)
    ap.add_argument("--wait", metavar="TK5_DIR", default="")
    a = ap.parse_args()
    text = Path(a.jcl).read_text()
    tk = TK5({"tk5_host": a.host, "reader_port": a.port,
              "tk5_dir": a.wait or "."})
    try:
        if not a.wait:
            tk.submit(text)
            print("submitted - the output will appear in prt/prt00e.txt")
            return 0
        res = tk.run(text)
        for s, p, pgm, rc in res.steps:
            print(f"{s:10s}{p:10s}{pgm:10s}{rc}")
    except TK5Error as e:
        print("ERROR:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
