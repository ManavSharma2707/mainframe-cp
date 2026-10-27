"""
test_python.py - unit tests for the Python side (no TK5 needed).
    python tests/test_python.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
import gen_data                      # noqa: E402
import render                        # noqa: E402
import validator_core as vc          # noqa: E402

CFG = {"hlq": "HERC01", "password": "CUL8TR", "job_class": "A",
       "msgclass": "A", "unit": "SYSDA", "vsam_volume": "TSO001",
       "tk5_host": "127.0.0.1", "reader_port": 3505, "tk5_dir": "."}


class TestData(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cards_are_80_columns_ascii_lf(self):
        for sc in gen_data.SCENARIOS:
            d = gen_data.write_scenario(sc, self.tmp)
            for f in ("src_extract.txt", "tgt_extract.txt"):
                b = (d / f).read_bytes()
                self.assertNotIn(b"\r", b)
                for ln in b.decode("ascii").splitlines():
                    self.assertEqual(len(ln), 80, f"{sc}/{f}")
                    self.assertFalse(set(ln) & render.FORBIDDEN)

    def test_deterministic(self):
        a = gen_data.write_scenario("seeded", self.tmp / "a")
        b = gen_data.write_scenario("seeded", self.tmp / "b")
        self.assertEqual((a / "src_extract.txt").read_bytes(),
                         (b / "src_extract.txt").read_bytes())

    def test_answer_keys(self):
        for sc in gen_data.SCENARIOS:
            d = gen_data.write_scenario(sc, self.tmp)
            e = json.loads((d / "expected.json").read_text())
            r = vc.reconcile(vc.read_lines(str(d / "src_extract.txt")),
                             vc.read_lines(str(d / "tgt_extract.txt")))
            self.assertEqual((r.rc, r.decision), (e["rc"], e["decision"]), sc)
            for k in ("raw", "dups", "src_unique", "tgt_cnt", "matched",
                      "mismatch", "missing", "extra"):
                if k in e:
                    self.assertEqual(getattr(r, k), e[k], f"{sc}.{k}")

    def test_slide_numbers(self):
        d = gen_data.write_scenario("seeded", self.tmp)
        r = vc.reconcile(vc.read_lines(str(d / "src_extract.txt")),
                         vc.read_lines(str(d / "tgt_extract.txt")))
        self.assertEqual((r.raw, r.dups, r.src_unique, r.tgt_cnt,
                          r.matched, r.mismatch, r.missing, r.extra),
                         (1020, 20, 1000, 995, 975, 15, 10, 5))
        self.assertEqual(len(r.exceptions), 30)

    def test_ebcdic_order_differs_from_ascii(self):
        self.assertLess(vc.ebcdic_key("A"), vc.ebcdic_key("1"))
        self.assertGreater("A", "1")


class TestRender(unittest.TestCase):
    def test_all_jobs_render_and_lint_clean(self):
        for name in ("SETUP", "BUILD", "HIST"):
            render.render_job(name, CFG)
        txt = render.render_job("MIGRUN", CFG, "seeded")
        self.assertIn("C0000001", txt)
        self.assertEqual(txt.count("\n$$\n"), 2)

    def test_only_own_hlq_datasets_are_written(self):
        import re
        for name in ("SETUP", "BUILD", "HIST"):
            txt = render.render_job(name, CFG)
            for m in re.finditer(r"DSN=([A-Z0-9.$#@&]+)", txt):
                self.assertTrue(m.group(1).startswith(("HERC01.MIG.", "&&")),
                                m.group(1))
        txt = render.render_job("MIGRUN", CFG, "clean")
        for m in re.finditer(r"DSN=([A-Z0-9.$#@&]+)", txt):
            self.assertTrue(m.group(1).startswith("HERC01.MIG."), m.group(1))

    def test_lint_catches_problems(self):
        self.assertTrue(render.lint("x", "//X JOB\nA|B"))
        self.assertTrue(render.lint("x", "//X JOB\n" + "A" * 81))
        self.assertTrue(render.lint("x", "//TOOLONGNAME JOB"))

    def test_bad_hlq_rejected(self):
        p = Path(tempfile.mkdtemp()) / "c.json"
        p.write_text(json.dumps(dict(CFG, hlq="TOOLONGID")))
        with self.assertRaises(render.ConfigError):
            render.load_config(p)


class TestParsers(unittest.TestCase):
    def test_migout_roundtrip(self):
        e = vc.Exc("C0000001", "A000000001", "MISSING", "*RECORD", "X 1.00", "")
        text = "MIGOUT-BEGIN\nRC=8\nDECISION=REJECTED\nEXC:" + \
            vc.exc_to_line(e) + "\nMIGOUT-END\n"
        kv, exc = vc.parse_migout(text)
        self.assertEqual(kv["RC"], "8")
        self.assertEqual(exc[0], e)


class TestApp(unittest.TestCase):
    def test_offline_mode(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "python" / "app.py"),
                               default_timeout=90).run()
        if at.sidebar.radio[0].value != "Offline demo":
            at.sidebar.radio[0].set_value("Offline demo").run()
        for sc in gen_data.SCENARIOS:
            at.sidebar.selectbox[0].select(sc).run()
            self.assertFalse(at.exception, sc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
