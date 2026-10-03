from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bonsai_verify as B  # noqa: E402

SRC = "def f(xs):\n    best = max(e['mae_adverse'] for e in xs)\n    return best\n\n" + "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"


class BonsaiVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "m.py").write_text(SRC, encoding="utf-8")
        self.log = self.root / "claims.log.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def status(self, **c):
        return B.check_claim(self.root, c)["status"]

    def test_grounded_even_with_different_whitespace(self):
        self.assertEqual(self.status(file="m.py", line=2, quote="best = max(e['mae_adverse']   for e in xs)"), "GROUNDED")

    def test_fabricated_quote_is_ungrounded(self):
        self.assertEqual(self.status(file="m.py", line=2, quote="if capital == 0: raise ValueError"), "UNGROUNDED")

    def test_missing_file_and_traversal_are_bad_ref(self):
        self.assertEqual(self.status(file="absent.py", quote="best = max(e['mae_adverse']"), "BAD_REF")
        self.assertEqual(self.status(file="../../etc/passwd", quote="root:x:0:0:root:/root"), "BAD_REF")

    def test_short_quote_is_vague(self):
        self.assertEqual(self.status(file="m.py", quote="max("), "VAGUE")

    def test_far_line_is_misplaced(self):
        self.assertEqual(self.status(file="m.py", line=40, quote="best = max(e['mae_adverse']"), "MISPLACED")

    def test_verify_judge_score_flow(self):
        claims = self.root / "c.json"
        claims.write_text(json.dumps([
            {"id": "1", "claim": "max sans garde", "file": "m.py", "line": 2, "quote": "best = max(e['mae_adverse']"},
            {"id": "2", "claim": "inventée", "file": "m.py", "line": 3, "quote": "assert capital > 0 and fees is not None"},
        ]), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(B.main(["--log", str(self.log), "verify", str(claims), "--task", "t", "--root", str(self.root)]), 0)
        self.assertIn("ancrées : 1/2", buf.getvalue())
        uid = [e["uid"] for e in B.read_log(self.log) if e.get("type") == "claim" and e["status"] == "GROUNDED"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(B.main(["--log", str(self.log), "judge", uid, "real"]), 0)
            bad = [e["uid"] for e in B.read_log(self.log) if e.get("type") == "claim" and e["status"] == "UNGROUNDED"][0]
            self.assertEqual(B.main(["--log", str(self.log), "judge", bad, "real"]), 2)  # écartée d'office
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            B.main(["--log", str(self.log), "score", "--task", "t"])
        out = buf.getvalue()
        self.assertIn("borne basse 50%", out)
        self.assertIn("borne haute 50%", out)
        self.assertIn("n = 2 < 30", out)

    def test_chunks_cover_the_file_with_overlap(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            B.main(["--log", str(self.log), "chunks", str(self.root / "m.py"), "--lines", "20", "--overlap", "5"])
        heads = [l for l in buf.getvalue().splitlines() if l.startswith("### chunk")]
        self.assertGreaterEqual(len(heads), 3)
        self.assertIn("L1-L20", heads[0])
        self.assertIn("L16-", heads[1])


if __name__ == "__main__":
    unittest.main()
