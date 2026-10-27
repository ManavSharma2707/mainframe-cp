"""
app.py - Streamlit dashboard for the TK5 Migration Validator.

    streamlit run app.py          (from the python folder)

Data sources (sidebar):
  * TK5 runs      - results saved by run_batch.py from the real TK5 jobs
  * Offline demo  - the Python reference implementation on generated data
                    (works without TK5; clearly labelled as such)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_data                      # noqa: E402
import validator_core as vc          # noqa: E402

ROOT = HERE.parent
RUNS = ROOT / "runs"
DATA = ROOT / "data"
COLORS = {"APPROVED": ("#1b873f", "SAFE TO CUT OVER"),
          "WARNING": ("#b7791f", "SAFE TO CUT OVER - IDENTICAL DUPLICATES DROPPED"),
          "REJECTED": ("#c53030", "DO NOT CUT OVER"),
          "ABORTED": ("#6b46c1", "HOLD - CONTROLS DISAGREE OR INPUT INVALID")}

st.set_page_config(page_title="Migration Validator", page_icon=":mag:",
                   layout="wide")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def list_runs() -> list[Path]:
    if not RUNS.exists():
        return []
    return sorted((p for p in RUNS.iterdir()
                   if p.is_dir() and (p / "result.txt").exists()),
                  key=lambda p: p.name, reverse=True)


def load_run(d: Path) -> dict:
    lines = lambda n: vc.read_lines(str(d / n)) if (d / n).exists() else []  # noqa: E731
    return {"origin": "tk5", "id": d.name,
            "summary": vc.parse_result(read(d / "result.txt")),
            "exc": vc.parse_excsort(read(d / "exceptions.txt")),
            "report": read(d / "report.txt"), "joblog": read(d / "joblog.txt"),
            "src": lines("src_extract.txt"), "tgt": lines("tgt_extract.txt"),
            "expected": json.loads(read(d / "expected.json") or "{}"),
            "meta": json.loads(read(d / "meta.json") or "{}")}


def load_offline(sc: str) -> dict:
    d = gen_data.write_scenario(sc, DATA)
    src = vc.read_lines(str(d / "src_extract.txt"))
    tgt = vc.read_lines(str(d / "tgt_extract.txt"))
    res = vc.reconcile(src, tgt)
    s = vc.result_to_dict(res)
    s["BATCH_ID"] = f"OFFLINE-{sc}"
    return {"origin": "offline", "id": s["BATCH_ID"], "summary": s,
            "exc": res.exceptions, "report": "", "joblog": "", "src": src,
            "tgt": tgt, "expected": json.loads(read(d / "expected.json") or "{}"),
            "meta": {}}


def num(s: dict, k: str) -> int:
    try:
        return int(str(s.get(k, "0")).strip() or 0)
    except ValueError:
        return 0


def frame(exc: list) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Type": e.err_type, "Customer": e.cust_id, "Account": e.acct_no,
          "Field": e.field, "Source value": e.src_val,
          "Target value": e.tgt_val} for e in exc],
        columns=["Type", "Customer", "Account", "Field", "Source value",
                 "Target value"])


def run_tool(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                       cwd=HERE)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------- sidebar
st.sidebar.title("Migration Validator")
st.sidebar.caption("TK5 / MVS 3.8J  -  SORT, COBOL, REXX, JCL, VSAM")
runs = list_runs()
mode = st.sidebar.radio("Data source", ["TK5 runs", "Offline demo"],
                        index=0 if runs else 1)
view = None
if mode == "TK5 runs":
    if runs:
        view = load_run(RUNS / st.sidebar.selectbox("Batch", [r.name for r in runs]))
    else:
        st.sidebar.info("No TK5 run saved yet - use 'Run on TK5' below.")
else:
    view = load_offline(st.sidebar.selectbox("Scenario", gen_data.SCENARIOS))
    st.sidebar.caption("Computed by the Python reference implementation, "
                       "NOT by TK5.")

with st.sidebar.expander("Run on TK5"):
    sc = st.selectbox("Test scenario", gen_data.SCENARIOS, key="sc_run")
    if st.button("Submit MIGRUN"):
        if not (HERE / "config.json").exists():
            st.error("python/config.json is missing (copy config.example.json).")
        else:
            with st.spinner("Job submitted to the card reader - waiting..."):
                rc, out = run_tool(["run_batch.py", "--scenario", sc])
            st.code(out, language="text")
            if rc == 0:
                st.success("Done - pick the new batch above.")
            else:
                st.error(f"run_batch.py ended with exit code {rc}")
    if st.button("Read VSAM audit history"):
        with st.spinner("Running job HIST (BREXX VSAMIO)..."):
            rc, out = run_tool(["history.py"])
        st.session_state["vsam_hist"] = out

# ------------------------------------------------------------------- main
st.title("Legacy-to-Modern Data Migration Validator")
st.caption("Pre-cutover approval gate on TK5: SORT -> COBOL -> REXX -> JCL "
           "gate, target table and audit trail in VSAM KSDS")
if view is None:
    st.info("Choose **Offline demo** in the sidebar to see the dashboard.")
    st.stop()

S = view["summary"]
dec = S.get("DECISION", "UNKNOWN")
col, msg = COLORS.get(dec, ("#4a5568", "UNKNOWN"))
origin = "real TK5 job output" if view["origin"] == "tk5" else \
    "Python reference implementation (offline)"
st.markdown(
    f"<div style='border-left:8px solid {col};padding:12px 18px;"
    f"background:{col}22;border-radius:6px'><span style='font-size:1.6rem;"
    f"font-weight:700;color:{col}'>{dec}</span> &nbsp; RC {S.get('RC', '?')}"
    f" &nbsp;-&nbsp; <b>{msg}</b><br><span style='opacity:.75'>Batch "
    f"{view['id']} &middot; {origin}</span></div>", unsafe_allow_html=True)
if S.get("REASON"):
    st.warning("Reason: " + S["REASON"])
st.write("")
k = st.columns(9)
for c, (lab, key) in zip(k, [
        ("Raw source", "SRC_RAW"), ("Identical dups", "DUP_SAME"),
        ("Conflicting dups", "DUP_CONF"), ("Unique source", "SRC_UNIQUE"),
        ("Target (KSDS)", "TGT_CNT"), ("Matched", "MATCHED"),
        ("Changed", "MISMATCH"), ("Missing", "MISSING"), ("Extra", "EXTRA")]):
    c.metric(lab, f"{num(S, key):,}")

df = frame(view["exc"])
tabs = st.tabs(["Overview", "Missing in target", "Extra in target",
                "Changed values", "Duplicates", "Verification",
                "Report & job log", "History"])

with tabs[0]:
    a, b = st.columns([3, 2])
    with a:
        st.subheader("Where did every record go?")
        st.bar_chart(pd.DataFrame({"records": [
            num(S, "MATCHED"), num(S, "MISMATCH"), num(S, "MISSING"),
            num(S, "EXTRA")]}, index=["Matched", "Changed", "Missing in target",
                                      "Extra in target"]))
    with b:
        st.subheader("Control checks")
        m, c_, mi, e, u, t = (num(S, x) for x in (
            "MATCHED", "MISMATCH", "MISSING", "EXTRA", "SRC_UNIQUE", "TGT_CNT"))
        ok = lambda x: "OK" if x else "FAILED"  # noqa: E731
        st.write(f"**Source:** {m:,} + {c_:,} + {mi:,} = {m + c_ + mi:,} "
                 f"unique source {u:,} - {ok(m + c_ + mi == u)}")
        st.write(f"**Target:** {m:,} + {c_:,} + {e:,} = {m + c_ + e:,} "
                 f"KSDS rows {t:,} - {ok(m + c_ + e == t)}")
        st.write(f"**Target extract vs KSDS:** {num(S, 'TGT_RAW'):,} vs {t:,} "
                 f"- {ok(num(S, 'TGT_RAW') == t)}")
        st.write(f"**Source extract:** {num(S, 'SRC_RAW'):,} = {u:,} unique + "
                 f"{num(S, 'DUP_SAME'):,} identical + {num(S, 'DUP_CONF'):,} "
                 "conflicting duplicates")
        try:
            sb, tb = float(S.get("SRC_BAL_TOT", 0)), float(S.get("TGT_BAL_TOT", 0))
            st.write(f"**Balance totals:** source {sb:,.2f} / target {tb:,.2f} "
                     f"(difference {tb - sb:,.2f})")
        except ValueError:
            pass
    if not df.empty:
        st.download_button("Download exceptions (CSV)", df.to_csv(index=False),
                           "exceptions.csv", "text/csv")


def name_balance(d: pd.DataFrame, col_: str) -> pd.DataFrame:
    d = d.copy()
    parts = d[col_].str.rsplit(" ", n=1, expand=True)
    d["Customer name"] = parts[0].str.strip()
    d["Balance"] = parts[1] if parts.shape[1] > 1 else ""
    return d[["Customer", "Account", "Customer name", "Balance"]]


with tabs[1]:
    st.caption("In the legacy extract, not in the target KSDS.")
    d = df[df["Type"] == "MISSING"]
    if d.empty:
        st.success("No missing records.")
    else:
        st.dataframe(name_balance(d, "Source value"), hide_index=True,
                     width="stretch")
with tabs[2]:
    st.caption("In the target KSDS, not in the legacy extract.")
    d = df[df["Type"] == "EXTRA"]
    if d.empty:
        st.success("No extra records.")
    else:
        st.dataframe(name_balance(d, "Target value"), hide_index=True,
                     width="stretch")
with tabs[3]:
    st.caption("Same key on both sides, a value differs (one row per field).")
    d = df[df["Type"] == "MISMATCH"]
    if d.empty:
        st.success("No changed values.")
    else:
        f = sorted(d["Field"].unique())
        sel = st.multiselect("Field", f, default=f)
        st.bar_chart(d["Field"].value_counts())
        st.dataframe(d[d["Field"].isin(sel)][["Customer", "Account", "Field",
                     "Source value", "Target value"]], hide_index=True, width="stretch")
with tabs[4]:
    st.caption("Identical copies are dropped by MIGMATCH and only counted "
               "(RC 4). Copies with DIFFERENT data are DUPKEY exceptions (RC 8).")
    conf = df[df["Type"] == "DUPKEY"]
    if not conf.empty:
        st.error(f"{len(conf)} key(s) with conflicting copies - review by hand:")
        st.dataframe(conf[["Customer", "Account", "Source value", "Target value"]]
                     .rename(columns={"Source value": "Kept copy",
                                      "Target value": "Dropped copy"}),
                     hide_index=True, width="stretch")
    dups = vc.find_duplicates(view["src"]) if view["src"] else []
    if dups:
        st.dataframe(pd.DataFrame(dups), hide_index=True, width="stretch")
    elif conf.empty:
        st.success("No duplicate keys in the source extract.")
with tabs[5]:
    if view["src"] or view["tgt"]:
        oracle = vc.reconcile(view["src"], view["tgt"])
        if view["origin"] == "tk5":
            diffs = vc.compare_to_oracle(S, view["exc"], oracle)
            if diffs:
                st.error("TK5 result differs from the reference implementation:")
                for x in diffs:
                    st.write("- " + x)
            else:
                st.success("The TK5 result is identical to the independent "
                           "Python implementation (all counts, the decision and "
                           "every exception row).")
        else:
            st.info("Offline mode: this IS the reference result.")
    exp = view["expected"]
    if exp:
        st.subheader("Answer key (expected.json)")
        mp = {"raw": "SRC_RAW", "dups": "DUPS", "src_unique": "SRC_UNIQUE",
              "tgt_cnt": "TGT_CNT", "matched": "MATCHED", "mismatch": "MISMATCH",
              "missing": "MISSING", "extra": "EXTRA", "rc": "RC",
              "decision": "DECISION"}
        rows = [{"Item": k, "Expected": str(exp[k]),
                 "Actual": str(S.get(v, "")),
                 "OK": "yes" if str(S.get(v, "")) == str(exp[k]) else "NO"}
                for k, v in mp.items() if k in exp]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if view["meta"].get("steps"):
        st.subheader("Job steps")
        st.dataframe(pd.DataFrame(view["meta"]["steps"],
                     columns=["Step", "Procstep", "Program", "Result"]),
                     hide_index=True, width="stretch")
with tabs[6]:
    if view["report"]:
        st.code(view["report"], language="text")
    else:
        st.info("The REXX report exists only for real TK5 runs.")
    if view["joblog"]:
        with st.expander("Complete job output (from prt00e.txt)"):
            st.code(view["joblog"][:200000], language="text")
with tabs[7]:
    if st.session_state.get("vsam_hist"):
        st.subheader("History stored in VSAM (MIG.AUDIT.KSDS via BREXX VSAMIO)")
        st.code(st.session_state["vsam_hist"], language="text")
    rows = []
    for r in list_runs():
        s = vc.parse_result(read(r / "result.txt"))
        rows.append({"Batch": r.name, "Decision": s.get("DECISION"),
                     "RC": num(s, "RC"), "Raw": num(s, "SRC_RAW"),
                     "Changed": num(s, "MISMATCH"), "Missing": num(s, "MISSING"),
                     "Extra": num(s, "EXTRA"), "Conflicts": num(s, "DUP_CONF")})
    if rows:
        h = pd.DataFrame(rows)
        st.subheader("Runs saved on this PC")
        st.dataframe(h, hide_index=True, width="stretch")
        st.line_chart(h.sort_values("Batch").set_index("Batch")[
            ["Changed", "Missing", "Extra", "Conflicts"]])
    else:
        st.info("History appears after the first TK5 run.")
