import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kanakku import canon, chain, diff, estimate, vintage  # noqa: E402
from kanakku.sources import rbi_wss_fx  # noqa: E402

DATA = os.path.join(ROOT, "data", "raw", "wss_fx.csv")
FIX = os.path.join(ROOT, "tests", "fixtures", "wss_fx_sample.html")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def small_table(v=100, period="2026-01"):
    return canon.make_table("demo", ["period"], ["value"], [{"period": period, "value": v}])


def build(n=10):
    recs, prev = [], None
    for i in range(n):
        prev = chain.new_record(prev, source="demo", series="demo", url="https://example.org",
                                fetched_at=f"2026-10-{i + 1:02d}T00:00:00Z", published=f"2026-10-{i + 1:02d}",
                                raw_sha256=canon.sha256(str(i).encode()), table=small_table(100 + i))
        recs.append(prev)
    return recs


class Canon(unittest.TestCase):
    def test_stable_and_order_free(self):
        self.assertEqual(canon.canonical({"b": 1, "a": [1, "x"]}), canon.canonical({"a": [1, "x"], "b": 1}))

    def test_floats_refused(self):
        with self.assertRaises(canon.CanonError):
            canon.canonical({"x": 1.5})

    def test_duplicate_keys_refused(self):
        with self.assertRaises(canon.CanonError):
            canon.make_table("s", ["k"], ["v"], [{"k": 1, "v": 1}, {"k": 1, "v": 2}])

    def test_rows_sorted_so_order_does_not_change_hash(self):
        a = canon.make_table("s", ["k"], ["v"], [{"k": "a", "v": 1}, {"k": "b", "v": 2}])
        b = canon.make_table("s", ["k"], ["v"], [{"k": "b", "v": 2}, {"k": "a", "v": 1}])
        self.assertEqual(canon.digest(a), canon.digest(b))

    def test_num(self):
        self.assertEqual(canon.num("1,234.50"), canon.num("1234.5"))
        with self.assertRaises(canon.CanonError):
            canon.num(True)


class Chain(unittest.TestCase):
    def test_clean_chain_verifies(self):
        self.assertTrue(chain.verify(build()).ok)

    def test_every_single_edit_is_caught(self):
        recs = build()
        for i in range(len(recs)):
            r = copy.deepcopy(recs)
            r[i]["table"]["rows"][0]["value"] += 1
            self.assertFalse(chain.verify(r).ok, f"edit of table {i}")
            r = copy.deepcopy(recs)
            r[i]["published"] = "1999-01-01"
            self.assertFalse(chain.verify(r).ok, f"edit of metadata {i}")

    def test_every_deletion_reorder_and_insertion_is_caught(self):
        recs = build()
        for i in range(len(recs) - 1):
            self.assertFalse(chain.verify(recs[:i] + recs[i + 1:]).ok, f"delete {i}")
            r = recs[:]
            r[i], r[i + 1] = r[i + 1], r[i]
            self.assertFalse(chain.verify(r).ok, f"swap {i}")
            r = recs[:]
            r.insert(i + 1, copy.deepcopy(recs[i]))
            self.assertFalse(chain.verify(r).ok, f"insert {i}")

    def test_truncation_needs_a_witness(self):
        recs = build()
        self.assertTrue(chain.verify(recs[:6]).ok)  # a chain alone cannot see a cut tail
        heads = [{"seq": 9, "hash": recs[9]["hash"]}]
        rep = chain.verify(recs[:6], heads)
        self.assertFalse(rep.ok)
        self.assertEqual(rep.problems[0]["kind"], "truncated")

    def test_full_rewrite_needs_a_witness(self):
        recs = build()
        heads = [{"seq": 4, "hash": recs[4]["hash"]}, {"seq": 9, "hash": recs[9]["hash"]}]
        forged, prev = [], None
        for i, r in enumerate(recs):  # attacker rewrites record 2 and re-hashes everything after it
            t = copy.deepcopy(r["table"])
            if i == 2:
                t["rows"][0]["value"] = 999
            prev = chain.new_record(prev, source=r["source"], series=r["series"], url=r["url"],
                                    fetched_at=r["fetched_at"], published=r["published"],
                                    raw_sha256=r["raw_sha256"], table=t)
            forged.append(prev)
        self.assertTrue(chain.verify(forged).ok)
        rep = chain.verify(forged, heads)
        self.assertFalse(rep.ok)
        self.assertTrue(all(p["kind"] == "witness" for p in rep.problems))

    def test_table_hash_mismatch(self):
        recs = build(3)
        recs[1]["table_sha256"] = "0" * 64
        recs[1]["hash"] = chain.record_hash(recs[1])
        kinds = {p["kind"] for p in chain.verify(recs).problems}
        self.assertIn("table", kinds)

    def test_unknown_field_refused(self):
        recs = build(2)
        recs[1]["note"] = "x"
        self.assertEqual(chain.verify(recs).problems[0]["kind"], "format")

    def test_time_must_not_go_backwards(self):
        recs = build(3)
        r = copy.deepcopy(recs)
        prev = r[0]
        r[1] = chain.new_record(prev, source="demo", series="demo", url="u", fetched_at="2000-01-01T00:00:00Z",
                                published="x", raw_sha256="0" * 64, table=small_table())
        self.assertIn("time", {p["kind"] for p in chain.verify(r[:2]).problems})

    def test_archive_file_append_and_refuse_broken(self):
        with tempfile.TemporaryDirectory() as d:
            arc = chain.Archive(os.path.join(d, "a.jsonl"))
            for i in range(3):
                arc.append(source="demo", series="demo", url="u", fetched_at=f"2026-01-0{i + 1}T00:00:00Z",
                           published="p", raw_sha256="0" * 64, table=small_table(i))
            self.assertTrue(chain.verify(arc.records()).ok)
            heads = os.path.join(d, "heads.jsonl")
            chain.witness(arc, heads)
            self.assertTrue(chain.verify(arc.records(), chain.load_heads(heads)).ok)
            lines = read(arc.path).splitlines()
            lines[1] = lines[1].replace('"value":1', '"value":7')
            write(arc.path, "\n".join(lines) + "\n")
            with self.assertRaises(RuntimeError):
                arc.append(source="demo", series="demo", url="u", fetched_at="2026-02-01T00:00:00Z",
                           published="p", raw_sha256="0" * 64, table=small_table())


class Diff(unittest.TestCase):
    def t(self, rows, cols=("v",), unit=None, base=None):
        return canon.make_table("s", ["k"], list(cols), rows, unit=unit, base=base)

    def test_classes(self):
        old = self.t([{"k": "a", "v": 10}, {"k": "b", "v": 20}, {"k": "c", "v": 30}])
        new = self.t([{"k": "a", "v": 11}, {"k": "b", "v": 25}, {"k": "d", "v": 40}])
        s = diff.summary(diff.compare(old, new, tolerance=1))
        self.assertEqual(s, {"addition": 1, "withdrawal": 1, "revision": 1, "rounding": 1, "schema": 0})

    def test_zero_tolerance_flags_everything(self):
        old = self.t([{"k": "a", "v": 10}])
        new = self.t([{"k": "a", "v": 11}])
        self.assertEqual(diff.summary(diff.compare(old, new))["revision"], 1)

    def test_per_column_tolerance(self):
        old = canon.make_table("s", ["k"], ["x", "y"], [{"k": "a", "x": 10, "y": 10}])
        new = canon.make_table("s", ["k"], ["x", "y"], [{"k": "a", "x": 11, "y": 11}])
        s = diff.summary(diff.compare(old, new, {"x": 1}))
        self.assertEqual((s["rounding"], s["revision"]), (1, 1))

    def test_schema_changes(self):
        old = self.t([{"k": "a", "v": 1}], unit="crore", base="2011-12")
        new = self.t([{"k": "a", "v": 1}], unit="crore", base="2022-23")
        self.assertEqual(diff.summary(diff.compare(old, new))["schema"], 1)
        new2 = canon.make_table("s", ["k"], ["v", "w"], [{"k": "a", "v": 1, "w": 2}])
        self.assertEqual(diff.summary(diff.compare(self.t([{"k": "a", "v": 1}]), new2))["schema"], 1)

    def test_same_number_different_spelling_is_not_a_change(self):
        self.assertEqual(diff.compare(self.t([{"k": "a", "v": "5"}]), self.t([{"k": "a", "v": "5.0"}])), [])

    def test_key_change_stops_row_comparison(self):
        old = canon.make_table("s", ["k"], ["v"], [{"k": "a", "v": 1}])
        new = canon.make_table("s", ["j"], ["v"], [{"j": "a", "v": 1}])
        ch = diff.compare(old, new)
        self.assertTrue(all(c.kind == "schema" for c in ch))


class RBI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snaps = rbi_wss_fx.snapshots_from_csv(DATA)
        recs, prev = [], None
        for rel, wid, t in cls.snaps:
            prev = chain.new_record(prev, source="rbi", series=rbi_wss_fx.SERIES, url=wid,
                                    fetched_at="2026-10-23T00:00:00Z", published=rel, raw_sha256="0" * 64, table=t)
            recs.append(prev)
        cls.recs = recs

    def test_dataset_complete(self):
        self.assertEqual(len(self.snaps), 59)
        dates = [s[0] for s in self.snaps]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual((dates[0], dates[-1]), ("2025-09-05", "2026-10-16"))

    def test_html_parser_matches_csv(self):
        t = rbi_wss_fx.parse_html(read(FIX))
        want = [s for s in self.snaps if s[0] == "2026-10-09"][0][2]
        self.assertEqual(canon.digest(t), canon.digest(want))

    def test_html_parser_refuses_partial_tables(self):
        html = read(FIX).replace("<td>4,789</td>", "")
        with self.assertRaises(ValueError):
            rbi_wss_fx.parse_html(html)

    def test_no_revision_beyond_rounding(self):
        kw = dict(period_col="as_on", item_col="item", level_col="lvl_inr", change_col="wk_inr")
        strict = vintage.implied_checks(self.recs, rbi_wss_fx.SERIES, **kw)
        tolerant = vintage.implied_checks(self.recs, rbi_wss_fx.SERIES, tolerance=rbi_wss_fx.TOLERANCE, **kw)
        self.assertEqual(len(strict), 58 * 5)
        self.assertGreater(sum(c["kind"] == "revision" for c in strict), 0)
        self.assertEqual(sum(c["kind"] == "revision" for c in tolerant), 0)

    def test_identity_holds_within_rounding(self):
        res = vintage.identity_checks(self.recs, rbi_wss_fx.SERIES, item_col="item", total_item="1",
                                      part_items=["1.1", "1.2", "1.3", "1.4"], columns=["lvl_inr", "lvl_usd"],
                                      tolerance=rbi_wss_fx.TOLERANCE_IDENTITY)
        self.assertEqual(len(res), 59 * 2)
        self.assertFalse([r for r in res if r["kind"] == "mismatch"])

    def test_injected_revision_is_found(self):
        recs = copy.deepcopy(self.recs)
        for row in recs[20]["table"]["rows"]:
            if row["item"] == "1.2":
                row["lvl_inr"] += 500  # a quiet restatement of gold, in the next release
        res = vintage.implied_checks(recs, rbi_wss_fx.SERIES, period_col="as_on", item_col="item",
                                     level_col="lvl_inr", change_col="wk_inr", tolerance=rbi_wss_fx.TOLERANCE_IMPLIED)
        hits = [c for c in res if c["kind"] == "revision"]
        self.assertEqual(len(hits), 2)  # breaks the pair before and after it
        self.assertTrue(all(h["item"] == "1.2" for h in hits))


class Estimate(unittest.TestCase):
    def setUp(self):
        _, _, t = [s for s in rbi_wss_fx.snapshots_from_csv(DATA) if s[0] == "2026-10-09"][0]
        self.rec = chain.new_record(None, source="rbi", series=rbi_wss_fx.SERIES, url="u",
                                    fetched_at="2026-10-23T00:00:00Z", published="2026-10-09",
                                    raw_sha256="0" * 64, table=t)
        self.A = [estimate.assumption("crore", 10000000, "INR", "Indian numbering", "1900-01-01"),
                  estimate.assumption("million", 1000000, "USD", "SI", "1900-01-01")]

    def test_implied_rate(self):
        r = estimate.derive("implied_rate", self.rec, self.A, item_col="item", item="1", inr_col="lvl_inr",
                            usd_col="lvl_usd")
        self.assertEqual(r["value"], "96.2844")
        self.assertTrue(estimate.recheck(r, {self.rec["seq"]: self.rec}, self.A))

    def test_recheck_catches_changed_assumption_or_input(self):
        r = estimate.derive("share", self.rec, [], item_col="item", part="1.2", total="1", column="lvl_usd")
        self.assertEqual(r["value"], "14.49")
        other = copy.deepcopy(self.rec)
        other["hash"] = "f" * 64
        self.assertFalse(estimate.recheck(r, {other["seq"]: other}, []))
        r2 = estimate.derive("implied_rate", self.rec, self.A, item_col="item", item="1", inr_col="lvl_inr",
                             usd_col="lvl_usd")
        bad = [estimate.assumption("crore", 1000000, "INR", "wrong", "1900-01-01"), self.A[1]]
        self.assertFalse(estimate.recheck(r2, {self.rec["seq"]: self.rec}, bad))

    def test_tampered_assumption_refused(self):
        a = copy.deepcopy(self.A)
        a[0]["value"] = "1"
        with self.assertRaises(ValueError):
            estimate.derive("implied_rate", self.rec, a, item_col="item", item="1", inr_col="lvl_inr",
                            usd_col="lvl_usd")

    def test_unknown_formula(self):
        with self.assertRaises(KeyError):
            estimate.derive("eval", self.rec)


class CLI(unittest.TestCase):
    def test_import_verify_diff(self):
        with tempfile.TemporaryDirectory() as d:
            arc = os.path.join(d, "a.jsonl")
            run = lambda *a: subprocess.run([sys.executable, "-m", "kanakku", *a], cwd=ROOT,
                                            capture_output=True, text=True)
            self.assertEqual(run("import-wss", DATA, arc).returncode, 0)
            out = run("verify", arc)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(json.loads(out.stdout)["records"], 59)
            heads = os.path.join(d, "heads.jsonl")
            self.assertEqual(run("witness", arc, heads).returncode, 0)
            self.assertEqual(run("verify", arc, "--heads", heads).returncode, 0)
            lines = read(arc).splitlines()
            write(arc, "\n".join(lines[:30]) + "\n")
            self.assertEqual(run("verify", arc, "--heads", heads).returncode, 1)


if __name__ == "__main__":
    unittest.main()
