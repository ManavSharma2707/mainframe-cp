"""
validator_core.py - record layouts, parsers and an independent pure-Python
"reference" implementation of the TK5 validator.

It reproduces MIGRUN exactly:
  SORT (1,80,CH,A) in EBCDIC order -> COBOL dedupe + match-merge
  -> VSAM KSDS load of the target (duplicate keys rejected)
  -> REXX decision.
Used by the tests, by run_batch.py to verify a mainframe run, and by the
Streamlit app as an offline demo when TK5 is not running.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

LRECL = 80          # source and target extracts are 80-byte card images
EXC_LRECL = 100
RANK = {"MISSING": 1, "MISMATCH": 2, "EXTRA": 3, "DUPKEY": 4}


def ebcdic_key(line: str) -> bytes:
    """Sort key identical to the mainframe sort (EBCDIC, code page 037)."""
    return line.ljust(LRECL)[:LRECL].encode("cp037", errors="replace")


@dataclass
class SrcRec:
    raw: str
    cust_id: str
    acct_no: str
    name: str
    balance_raw: str     # 11 digits, 2 implied decimals
    txn_date: str        # YYYYMMDD
    status: str

    @property
    def key(self) -> str:
        return self.cust_id + self.acct_no

    @property
    def balance(self) -> Decimal | None:
        b = self.balance_raw
        return Decimal(int(b)) / 100 if len(b) == 11 and b.isdigit() else None


@dataclass
class TgtRec:
    raw: str
    cust_id: str
    acct_no: str
    name: str            # 30 characters
    balance_txt: str     # 000001234.56
    date_txt: str        # YYYY-MM-DD
    status: str

    @property
    def key(self) -> str:
        return self.cust_id + self.acct_no

    @property
    def balance(self) -> Decimal | None:
        t = self.balance_txt
        if len(t) == 12 and t[:9].isdigit() and t[9] == "." and t[10:].isdigit():
            return Decimal(t)
        return None

    @property
    def date_norm(self) -> str | None:
        d = self.date_txt
        return d[0:4] + d[5:7] + d[8:10] if d[4:5] == "-" and d[7:8] == "-" else None


def parse_src_line(line: str) -> SrcRec:
    l = line.rstrip("\r\n").ljust(LRECL)[:LRECL]
    return SrcRec(l, l[0:8], l[8:18], l[18:38], l[38:49], l[49:57], l[57:58])


def parse_tgt_line(line: str) -> TgtRec:
    l = line.rstrip("\r\n").ljust(LRECL)[:LRECL]
    return TgtRec(l, l[0:8], l[8:18], l[18:48], l[48:60], l[60:70], l[70:71])


def read_lines(path: str) -> list[str]:
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        return [ln.rstrip("\r\n") for ln in fh if ln.strip("\r\n") != ""]


@dataclass
class Exc:
    cust_id: str
    acct_no: str
    err_type: str        # MISSING | MISMATCH | EXTRA | DUPKEY
    field: str           # *RECORD | NAME | BALANCE | TXNDATE | STATUS
    src_val: str
    tgt_val: str


@dataclass
class Result:
    raw: int = 0
    dup_same: int = 0
    dup_conf: int = 0
    src_unique: int = 0
    tgt_raw: int = 0
    tgt_cnt: int = 0
    matched: int = 0
    mismatch: int = 0
    missing: int = 0
    extra: int = 0
    rc: int = 0
    decision: str = ""
    reason: str = ""
    src_bal_tot: Decimal = Decimal("0")
    tgt_bal_tot: Decimal = Decimal("0")
    exceptions: list[Exc] = field(default_factory=list)

    @property
    def dups(self) -> int:
        return self.dup_same + self.dup_conf


def _val(name: str, bal: Decimal | None, raw_bal: str) -> str:
    """Same text as the COBOL group WS-VAL-GRP: NAME X(17), one blank,
    balance as Z(8)9.99 (or the raw characters, left aligned)."""
    b = f"{bal:12.2f}" if bal is not None else raw_bal[:12].ljust(12)
    return (name[:17].ljust(17) + " " + b).strip()


def reconcile(src_lines: list[str], tgt_lines: list[str]) -> Result:
    res = Result(raw=len(src_lines), tgt_raw=len(tgt_lines))

    # SORT FIELDS=(1,80,CH,A) + COBOL dedupe (keeps the lowest record)
    kept: dict[str, SrcRec] = {}
    order: list[str] = []
    for line in sorted(src_lines, key=ebcdic_key):
        r = parse_src_line(line)
        k = r.key
        if k in kept:
            if r.raw == kept[k].raw:
                res.dup_same += 1
            else:
                res.dup_conf += 1
                kr = kept[k]
                res.exceptions.append(Exc(
                    r.cust_id, r.acct_no, "DUPKEY", "*RECORD",
                    _val(kr.name, kr.balance, kr.balance_raw),
                    _val(r.name, r.balance, r.balance_raw)))
        else:
            kept[k] = r
            order.append(k)
    res.src_unique = len(kept)

    # SORT + IDCAMS REPRO into the KSDS: a duplicate key is rejected
    tmap: dict[str, TgtRec] = {}
    for line in sorted(tgt_lines, key=ebcdic_key):
        t = parse_tgt_line(line)
        if t.key not in tmap:
            tmap[t.key] = t
    res.tgt_cnt = len(tmap)

    for r in kept.values():
        if r.balance is not None:
            res.src_bal_tot += r.balance
    for t in tmap.values():
        if t.balance is not None:
            res.tgt_bal_tot += t.balance

    for k in sorted(kept, key=lambda x: x.encode("cp037")):
        s = kept[k]
        t = tmap.get(k)
        if t is None:
            res.missing += 1
            res.exceptions.append(Exc(s.cust_id, s.acct_no, "MISSING",
                                      "*RECORD",
                                      _val(s.name, s.balance, s.balance_raw),
                                      ""))
            continue
        diffs = []
        if s.name.rstrip() != t.name.rstrip():
            diffs.append(("NAME", s.name.strip(), t.name.strip()))
        if s.balance is None or t.balance is None:
            diffs.append(("BALANCE", s.balance_raw.strip(), t.balance_txt.strip()))
        elif s.balance != t.balance:
            diffs.append(("BALANCE", f"{s.balance:.2f}", f"{t.balance:.2f}"))
        if t.date_norm is None or t.date_norm != s.txn_date:
            diffs.append(("TXNDATE", s.txn_date.strip(), t.date_txt.strip()))
        if s.status != t.status:
            diffs.append(("STATUS", s.status.strip(), t.status.strip()))
        if diffs:
            res.mismatch += 1
            for f, a, b in diffs:
                res.exceptions.append(Exc(s.cust_id, s.acct_no, "MISMATCH",
                                          f, a, b))
        else:
            res.matched += 1
    for k, t in tmap.items():
        if k not in kept:
            res.extra += 1
            res.exceptions.append(Exc(t.cust_id, t.acct_no, "EXTRA",
                                      "*RECORD", "",
                                      _val(t.name, t.balance, t.balance_txt)))

    if res.tgt_raw != res.tgt_cnt:
        res.rc, res.decision = 12, "ABORTED"
        res.reason = f"TARGET LOAD REJECTED {res.tgt_raw - res.tgt_cnt} RECORD(S)"
    elif res.missing + res.extra + res.mismatch + res.dup_conf > 0:
        res.rc, res.decision = 8, "REJECTED"
    elif res.dup_same > 0:
        res.rc, res.decision = 4, "WARNING"
    else:
        res.rc, res.decision = 0, "APPROVED"
    res.exceptions.sort(key=lambda e: (RANK[e.err_type],
                                       (e.cust_id + e.acct_no).encode("cp037"),
                                       e.field.encode("cp037")))
    return res


# ---------------------------------------------------------------------
# parsing what the mainframe printed
# ---------------------------------------------------------------------
def parse_migout(text: str) -> tuple[dict[str, str], list[Exc]]:
    """Parse the MIGOUT-BEGIN ... MIGOUT-END block printed by MIGRUN."""
    kv: dict[str, str] = {}
    exc: list[Exc] = []
    for ln in text.splitlines():
        if ln.startswith("EXC:"):
            r = ln[4:].ljust(EXC_LRECL)
            exc.append(Exc(r[0:8].strip(), r[8:18].strip(), r[18:26].strip(),
                           r[26:34].strip(), r[34:64].strip(), r[64:94].strip()))
        elif "=" in ln and not ln.startswith("MIGOUT"):
            k, v = ln.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv, exc


def parse_result(text: str) -> dict[str, str]:
    return parse_migout(text)[0]


def parse_excsort(text: str) -> list[Exc]:
    out = []
    for ln in text.splitlines():
        if ln.strip():
            r = ln.ljust(EXC_LRECL)
            out.append(Exc(r[0:8].strip(), r[8:18].strip(), r[18:26].strip(),
                           r[26:34].strip(), r[34:64].strip(), r[64:94].strip()))
    return out


def exc_to_line(e: Exc) -> str:
    return (e.cust_id.ljust(8) + e.acct_no.ljust(10) + e.err_type.ljust(8)
            + e.field.ljust(8) + e.src_val[:30].ljust(30)
            + e.tgt_val[:30].ljust(30)).ljust(EXC_LRECL)


def result_to_dict(res: Result) -> dict[str, str]:
    return {
        "DECISION": res.decision, "RC": str(res.rc),
        "SRC_RAW": str(res.raw), "DUPS": str(res.dups),
        "DUP_SAME": str(res.dup_same), "DUP_CONF": str(res.dup_conf),
        "SRC_UNIQUE": str(res.src_unique), "TGT_RAW": str(res.tgt_raw),
        "TGT_CNT": str(res.tgt_cnt), "MATCHED": str(res.matched),
        "MISMATCH": str(res.mismatch), "MISSING": str(res.missing),
        "EXTRA": str(res.extra), "SRC_BAL_TOT": f"{res.src_bal_tot:.2f}",
        "TGT_BAL_TOT": f"{res.tgt_bal_tot:.2f}", "REASON": res.reason,
    }


COMPARE_KEYS = ["DECISION", "RC", "SRC_RAW", "DUPS", "DUP_SAME", "DUP_CONF",
                "SRC_UNIQUE", "TGT_RAW", "TGT_CNT", "MATCHED", "MISMATCH",
                "MISSING", "EXTRA", "SRC_BAL_TOT", "TGT_BAL_TOT"]


def compare_to_oracle(mf: dict[str, str], mf_exc: list[Exc],
                      oracle: Result) -> list[str]:
    """Differences between a mainframe result and the reference (empty = equal)."""
    o = result_to_dict(oracle)
    keys = ["DECISION", "RC", "SRC_RAW", "TGT_RAW", "TGT_CNT"] \
        if oracle.rc == 12 else COMPARE_KEYS
    diffs = [f"{k}: mainframe={mf.get(k)!r} reference={o[k]!r}"
             for k in keys if str(mf.get(k, "")).strip() != o[k]]
    if oracle.rc != 12:
        a = [(e.cust_id, e.acct_no, e.err_type, e.field, e.src_val, e.tgt_val)
             for e in mf_exc]
        b = [(e.cust_id, e.acct_no, e.err_type, e.field, e.src_val, e.tgt_val)
             for e in oracle.exceptions]
        if a != b:
            sa, sb = set(a), set(b)
            diffs.append(f"exception rows differ: mainframe={len(a)} "
                         f"reference={len(b)}; only mainframe: "
                         f"{sorted(sa - sb)[:3]} only reference: "
                         f"{sorted(sb - sa)[:3]}")
    return diffs


def find_duplicates(src_lines: list[str]) -> list[dict]:
    groups: dict[str, list[str]] = {}
    for ln in src_lines:
        r = parse_src_line(ln)
        groups.setdefault(r.key, []).append(r.raw)
    return [{"cust_id": k[:8], "acct_no": k[8:], "copies": len(v),
             "conflicting": len(set(v)) > 1,
             "name": parse_src_line(v[0]).name.strip()}
            for k, v in sorted(groups.items()) if len(v) > 1]
