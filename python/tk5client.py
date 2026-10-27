"""
tk5client.py - talks to TK5 without Zowe:
  * submit  : sends JCL as ASCII text to the Hercules card reader socket
              (device 000C, port 3505 - see conf/tk5.cnf in the TK5 folder)
  * wait    : watches the printer file prt/prt00e.txt (output class A)
              until the job's '****A  END  JOB nnn JOBNAME' banner appears
  * parse   : step return codes (IEFACTRT lines) and printed blocks
"""
from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path


class TK5Error(RuntimeError):
    pass


@dataclass
class JobResult:
    jobname: str
    jobnum: str
    text: str
    steps: list[tuple[str, str, str, str]] = field(default_factory=list)

    @property
    def jcl_error(self) -> bool:
        return "JOB FAILED - JCL ERROR" in self.text or \
            "IEF452I" in self.text

    @property
    def abended(self) -> list[str]:
        return [f"{s}.{p}".strip(".") + f" {rc}" for s, p, _, rc in self.steps
                if rc.startswith("AB")]

    def rc(self, step: str, procstep: str = "") -> str | None:
        for s, p, _, rc in self.steps:
            if s == step and (not procstep or p == procstep):
                return rc
        return None

    def max_cc(self) -> int | None:
        vals = [int(rc[4:]) for *_, rc in self.steps if rc.startswith("RC=")]
        return max(vals) if vals else None

    def block(self, begin: str, end: str) -> str | None:
        t = self.text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
        i = t.find(begin)
        if i < 0:
            return None
        j = t.find(end, i)
        if j < 0:
            return None
        return t[i:j + len(end)]


STEP_RE = re.compile(
    r"JOB\s+(\d+)\s+(\S+)\s+(\S+)\s+(?:(\S+)\s+)?(\S+)\s+"
    r"(RC=\s*\d{4}|AB\s+\S+|\*FLUSH\*)")


class TK5:
    def __init__(self, cfg: dict, log=print):
        self.host = cfg.get("tk5_host", "127.0.0.1")
        self.port = int(cfg.get("reader_port", 3505))
        self.prt = Path(cfg["tk5_dir"]) / "prt" / "prt00e.txt"
        self.timeout = int(cfg.get("job_timeout_seconds", 900))
        self.log = log

    def check(self) -> None:
        if not self.prt.exists():
            raise TK5Error(f"printer file not found: {self.prt}\n"
                           "Set tk5_dir in config.json to your mvs-tk5 folder.")
        try:
            socket.create_connection((self.host, self.port), timeout=5).close()
        except OSError as e:
            raise TK5Error(f"cannot connect to the TK5 card reader at "
                           f"{self.host}:{self.port} ({e}). Is TK5 running? "
                           "Wait until the IPL has finished.") from e
        time.sleep(1)   # let Hercules close the reader before the next job

    def _open_reader(self, tries: int = 5) -> socket.socket:
        # Hercules accepts a reader connection and stays silent. If it is
        # still closing the previous one it drops us at once (EOF). Detect
        # that before any JCL is sent, so a retry can never submit twice.
        for n in range(1, tries + 1):
            s = socket.create_connection((self.host, self.port), timeout=15)
            time.sleep(0.3)
            s.settimeout(0.7)
            try:
                rejected = s.recv(1) == b""
            except socket.timeout:
                rejected = False
            except OSError:
                rejected = True
            if not rejected:
                s.settimeout(15)
                return s
            s.close()
            self.log(f"card reader busy, retrying ({n}/{tries})")
            time.sleep(2)
        raise TK5Error("the TK5 card reader kept rejecting the connection. "
                       "Check the Hercules console (device 000C).")

    def submit(self, jcl: str) -> None:
        lines = jcl.replace("\r\n", "\n").rstrip("\n").split("\n")
        for n, l in enumerate(lines, 1):
            if len(l) > 80:
                raise TK5Error(f"JCL line {n} is longer than 80 columns")
        data = ("\n".join(lines) + "\n").encode("ascii")
        with self._open_reader() as s:
            s.sendall(data)
        time.sleep(1)   # let Hercules close the reader before the next job

    def run(self, jcl: str, timeout: int | None = None) -> JobResult:
        m = re.match(r"//(\S+)\s+JOB\b", jcl)
        if not m:
            raise TK5Error("first line must be the JOB card")
        jobname = m.group(1)
        start = self.prt.stat().st_size
        self.log(f"submitting {jobname} to {self.host}:{self.port}")
        self.submit(jcl)
        end_re = re.compile(r"\*\*\*\*A\s+END\s+JOB\s+(\d+)\s+"
                            + re.escape(jobname) + r"\b")
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            with open(self.prt, "rb") as f:
                f.seek(start)
                text = f.read().decode("latin-1")
            em = end_re.search(text)
            if em:
                num = em.group(1)
                st = text.find(f"START  JOB {num:>4}  {jobname}")
                body = text[st:] if st >= 0 else text
                steps = [(g[2], g[3], g[4], re.sub(r"\s+", " ", g[5]))
                         for g in STEP_RE.findall(body) if g[1] == jobname]
                self.log(f"{jobname} (JOB {num}) finished")
                return JobResult(jobname, num, body, steps)
            time.sleep(1)
        raise TK5Error(f"{jobname} did not finish within the timeout. Check "
                       "the Hercules console (is the job waiting?)")
