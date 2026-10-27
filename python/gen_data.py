"""
gen_data.py - test data for the TK5 Migration Validator (80-column cards).

    python gen_data.py --scenario seeded       REJECTED  RC 8  (default)
    python gen_data.py --scenario dups         WARNING   RC 4
    python gen_data.py --scenario clean        APPROVED  RC 0
    python gen_data.py --scenario conflict     REJECTED  RC 8  (DUPKEY)
    python gen_data.py --scenario dup_target   ABORTED   RC 12
    python gen_data.py --scenario all

Writes data/<scenario>/src_extract.txt, tgt_extract.txt, expected.json.
SOURCE 80 : CUST-ID 1-8 | ACCT-NO 9-18 | NAME 19-38 | BALANCE 39-49
            (9 digits + 2 implied decimals) | TXN-DATE 50-57 YYYYMMDD |
            STATUS 58 | blanks 59-80
TARGET 80 : CUST_ID 1-8 | ACCT_NO 9-18 | NAME 19-48 (30) |
            BALANCE 49-60 text 000001234.56 | TXN_DATE 61-70 YYYY-MM-DD |
            STATUS 71 | blanks 72-80
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
from pathlib import Path

FIRST = ["AARAV", "ANANYA", "ARJUN", "DIYA", "ISHAAN", "KAVYA", "MEERA",
         "NEHA", "ROHAN", "SANYA", "VIKRAM", "TANVI", "KABIR", "RIYA",
         "SAMEER", "PRIYA", "NIKHIL", "ANJALI", "YASH", "POOJA"]
LAST = ["RAO", "IYER", "DAS", "SHARMA", "PATIL", "NAIR", "MEHTA", "JOSHI",
        "KULKARNI", "SINGH", "VERMA", "REDDY", "GUPTA", "DESAI", "BOSE"]
SCENARIOS = ["seeded", "dups", "clean", "conflict", "dup_target"]


def make_base(rng: random.Random, n: int = 1000) -> list[dict]:
    start = dt.date(2025, 1, 1)
    return [{"cust_id": f"C{i:07d}", "acct_no": f"A{100000000 + i * 7:09d}",
             "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}"[:20],
             "cents": rng.randint(10000, 9999999),
             "date": start + dt.timedelta(days=rng.randint(0, 600)),
             "status": rng.choice("AAAAIC")} for i in range(1, n + 1)]


def src_line(r: dict) -> str:
    return (r["cust_id"].ljust(8) + r["acct_no"].ljust(10)
            + r["name"].ljust(20) + f"{r['cents']:011d}"
            + r["date"].strftime("%Y%m%d") + r["status"]).ljust(80)


def tgt_line(r: dict) -> str:
    bal = f"{r['cents'] // 100:09d}.{r['cents'] % 100:02d}"
    return (r["cust_id"].ljust(8) + r["acct_no"].ljust(10)
            + r["name"].ljust(30) + bal + r["date"].strftime("%Y-%m-%d")
            + r["status"]).ljust(80)


EXPECT = {
    "seeded":     dict(rc=8, decision="REJECTED", raw=1020, dups=20,
                       src_unique=1000, tgt_cnt=995, matched=975,
                       mismatch=15, missing=10, extra=5),
    "dups":       dict(rc=4, decision="WARNING", raw=1020, dups=20,
                       src_unique=1000, tgt_cnt=1000, matched=1000,
                       mismatch=0, missing=0, extra=0),
    "clean":      dict(rc=0, decision="APPROVED", raw=1000, dups=0,
                       src_unique=1000, tgt_cnt=1000, matched=1000,
                       mismatch=0, missing=0, extra=0),
    "conflict":   dict(rc=8, decision="REJECTED", raw=1003, dups=3,
                       src_unique=1000, tgt_cnt=1000),
    "dup_target": dict(rc=12, decision="ABORTED", raw=1000, dups=0,
                       src_unique=1000, tgt_cnt=1000),
}


def build(scenario: str, seed: int = 42):
    rng = random.Random(seed)
    base = make_base(rng)
    exp = {"scenario": scenario, "missing_keys": [], "extra_keys": [],
           "changed": [], "dup_keys": [], "conflict_keys": []}
    src = [src_line(r) for r in base]
    if scenario in ("seeded", "dups"):
        for r in rng.sample(base, 20):
            src.append(src_line(r))
            exp["dup_keys"].append(r["cust_id"])
    if scenario == "conflict":
        for r in rng.sample(base, 3):
            other = dict(r, cents=r["cents"] + 100)
            src.append(src_line(other))
            exp["conflict_keys"].append(r["cust_id"])
    rng.shuffle(src)

    tgt = [dict(r) for r in base]
    if scenario == "seeded":
        for i in sorted(rng.sample(range(len(tgt)), 10), reverse=True):
            exp["missing_keys"].append(tgt[i]["cust_id"])
            del tgt[i]
        kinds = ["BALANCE"] * 6 + ["NAME"] * 3 + ["TXNDATE"] * 3 + ["STATUS"] * 3
        for i, kind in zip(rng.sample(range(len(tgt)), 15), kinds):
            r = tgt[i]
            if kind == "BALANCE":
                r["cents"] = max(100, r["cents"] + rng.choice(
                    [-4500, -50, 100, 2500, 99900]))
            elif kind == "NAME":
                r["name"] = r["name"][:-1] + ("Z" if r["name"][-1] == "X" else "X")
            elif kind == "TXNDATE":
                r["date"] += dt.timedelta(days=rng.randint(1, 20))
            else:
                r["status"] = "A" if r["status"] == "I" else "I"
            exp["changed"].append({"cust_id": r["cust_id"], "field": kind})
        for j in range(1, 6):
            tgt.append({"cust_id": f"C{1000 + j:07d}",
                        "acct_no": f"A{900000000 + j:09d}",
                        "name": f"EXTRA CUSTOMER {j}",
                        "cents": rng.randint(10000, 500000),
                        "date": dt.date(2026, 3, j), "status": "A"})
            exp["extra_keys"].append(f"C{1000 + j:07d}")
    tlines = [tgt_line(r) for r in tgt]
    if scenario == "dup_target":
        tlines.append(tgt_line(dict(tgt[3], name="DUPLICATE ROW")))
    rng.shuffle(tlines)
    exp.update(EXPECT[scenario])
    return src, tlines, exp


def write_scenario(scenario: str, out_root: Path, seed: int = 42) -> Path:
    src, tgt, exp = build(scenario, seed)
    d = out_root / scenario
    d.mkdir(parents=True, exist_ok=True)
    assert all(len(x) == 80 for x in src + tgt)
    (d / "src_extract.txt").write_bytes(("\n".join(src) + "\n").encode("ascii"))
    (d / "tgt_extract.txt").write_bytes(("\n".join(tgt) + "\n").encode("ascii"))
    (d / "expected.json").write_bytes(
        (json.dumps(exp, indent=2) + "\n").encode("ascii"))
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scenario", choices=SCENARIOS + ["all"], default="seeded")
    ap.add_argument("--out", default=str(Path(__file__).parent.parent / "data"))
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    for sc in (SCENARIOS if a.scenario == "all" else [a.scenario]):
        print("wrote", write_scenario(sc, Path(a.out), a.seed))


if __name__ == "__main__":
    main()
