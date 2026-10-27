"""
render.py - turns the templates in mainframe/ into complete, ready-to-submit
jobs in build/jcl/ and lints them (catches mistakes before TK5 sees them).

    python render.py                      -> build/jcl/SETUP.jcl, BUILD.jcl,
                                             HIST.jcl, MIGRUN_<scenario>.jcl
Tokens: @HLQ@ @PASSWORD@ @CLASS@ @MSGCLASS@ @UNIT@ @VOL@
        @COBOL:name@ / @REXX:name@  -> source code inserted (BUILD job)
        @DATA:SRC@ / @DATA:TGT@     -> 80-column data cards (MIGRUN job)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MF = ROOT / "mainframe"
BUILD = ROOT / "build"
DATA = ROOT / "data"
REQUIRED = ["hlq", "password", "job_class", "msgclass", "unit",
            "vsam_volume", "tk5_host", "reader_port", "tk5_dir"]
# characters that the ASCII->EBCDIC card reader translation garbles
FORBIDDEN = set("|\\[]^~`!{}")


class ConfigError(Exception):
    pass


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"{path} not found - copy config.example.json to "
                          "config.json and edit it")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for k in REQUIRED:
        if str(cfg.get(k, "")).strip() == "":
            raise ConfigError(f"config.json: '{k}' is empty")
    cfg["hlq"] = cfg["hlq"].strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,6}", cfg["hlq"]):
        raise ConfigError("hlq must be a TSO userid of 1-7 characters "
                          "(e.g. HERC01); job names are hlq + 1 letter")
    return cfg


def tokens(cfg: dict) -> dict[str, str]:
    return {"HLQ": cfg["hlq"], "PASSWORD": cfg["password"].upper(),
            "CLASS": cfg["job_class"], "MSGCLASS": cfg["msgclass"],
            "UNIT": cfg["unit"], "VOL": cfg["vsam_volume"].upper()}


def _code(kind: str, name: str) -> str:
    folder = {"COBOL": MF / "cobol", "REXX": MF / "rexx"}[kind]
    ext = {"COBOL": ".cbl", "REXX": ".rexx"}[kind]
    return (folder / f"{name}{ext}").read_text().replace("\r\n", "\n").rstrip("\n")


def render_text(template: str, cfg: dict, data: dict[str, list[str]] | None = None
                ) -> str:
    tk = tokens(cfg)

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if ":" in key:
            kind, name = key.split(":", 1)
            if kind in ("COBOL", "REXX"):
                return _code(kind, name)
            if kind == "DATA":
                if not data or name not in data:
                    raise ConfigError(f"no data for @{key}@")
                return "\n".join(data[name])
        if key not in tk:
            raise ConfigError(f"unknown token @{key}@")
        return tk[key]

    return re.sub(r"@([A-Z0-9_]+(?::[A-Z0-9_]+)?)@", sub, template)


def lint(name: str, text: str) -> list[str]:
    problems = []
    lines = text.split("\n")
    m = re.match(r"//(\S+)\s+JOB\b", lines[0])
    if not m or len(m.group(1)) > 8:
        problems.append(f"{name}:1 bad JOB card / job name > 8 chars")
    in_data = False
    for n, ln in enumerate(lines, 1):
        w = f"{name}:{n}"
        if len(ln) > 80:
            problems.append(f"{w}: {len(ln)} columns (card limit 80)")
        if "\t" in ln or any(ord(c) > 126 for c in ln):
            problems.append(f"{w}: tab or non-ASCII character")
        bad = FORBIDDEN & set(ln)
        if bad:
            problems.append(f"{w}: character(s) {sorted(bad)} are garbled by "
                            "the card reader")
        if "@" in ln and not in_data:
            problems.append(f"{w}: unreplaced @TOKEN@")
        if ln.startswith("//") and not in_data and len(ln) > 71 \
                and not ln.startswith("//*"):
            problems.append(f"{w}: JCL statement longer than 71 columns")
        if re.search(r"DD +DATA,DLM=\$\$", ln):
            in_data = True
        elif ln == "$$":
            in_data = False
    return problems


def data_for(scenario: str) -> dict[str, list[str]]:
    import gen_data
    d = gen_data.write_scenario(scenario, DATA)
    src = (d / "src_extract.txt").read_text().splitlines()
    tgt = (d / "tgt_extract.txt").read_text().splitlines()
    return {"SRC": src, "TGT": tgt}


def render_job(name: str, cfg: dict, scenario: str | None = None) -> str:
    tpl = (MF / "jcl" / f"{name}.jcl").read_text().replace("\r\n", "\n")
    data = data_for(scenario) if scenario else None
    text = render_text(tpl, cfg, data)
    problems = lint(name, text)
    if problems:
        raise ConfigError("lint problems:\n  " + "\n  ".join(problems))
    return text


def render_all(cfg: dict) -> list[Path]:
    import gen_data
    out = BUILD / "jcl"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name in ("CHECK", "SETUP", "BUILD", "HIST"):
        p = out / f"{name}.jcl"
        p.write_bytes(render_job(name, cfg).encode("ascii"))
        written.append(p)
    for sc in gen_data.SCENARIOS:
        p = out / f"MIGRUN_{sc.upper()}.jcl"
        p.write_bytes(render_job("MIGRUN", cfg, sc).encode("ascii"))
        written.append(p)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--config", default=str(Path(__file__).parent / "config.json"))
    a = ap.parse_args()
    try:
        files = render_all(load_config(Path(a.config)))
    except ConfigError as e:
        print("ERROR:", e)
        return 1
    for f in files:
        print("rendered", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
