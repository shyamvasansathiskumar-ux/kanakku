"""Tests for the website in docs/: what it loads, what it allows, and whether its
in-browser verifier (docs/ledger.js) gives exactly the same answers as the Python one.

The JavaScript checks run under Node (18+). They are skipped, not failed, if Node isn't installed.
"""
import copy
import html.parser
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kanakku import canon, chain  # noqa: E402

DOCS = os.path.join(ROOT, "docs")
NODE = shutil.which("node")


def read(path, mode="r"):
    with open(path, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


class Tags(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def page():
    p = Tags()
    p.feed(read(os.path.join(DOCS, "index.html")))
    return p.tags


EXPECTED_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
                "font-src 'self'; connect-src 'self'; manifest-src 'self'; object-src 'none'; frame-src 'none'; "
                "worker-src 'none'; media-src 'none'; base-uri 'none'; form-action 'none'; upgrade-insecure-requests")
SITE_JS = ["app.js", "ledger.js", "scene.js", "boot.js"]


class Copies(unittest.TestCase):
    def test_site_archive_is_the_archive(self):
        self.assertEqual(read(os.path.join(DOCS, "archive.jsonl"), "rb"), read(os.path.join(ROOT, "archive", "rbi_fx.jsonl"), "rb"))
        self.assertEqual(read(os.path.join(DOCS, "heads.jsonl"), "rb"), read(os.path.join(ROOT, "archive", "heads.jsonl"), "rb"))

    def test_site_gdp_is_the_dataset(self):
        self.assertEqual(json.loads(read(os.path.join(DOCS, "gdp.json"))), json.loads(read(os.path.join(ROOT, "data", "raw", "gdp_vintages.json"))))

    def test_archive_verifies_against_its_head(self):
        recs = [json.loads(line) for line in read(os.path.join(DOCS, "archive.jsonl")).splitlines() if line.strip()]
        heads = [json.loads(line) for line in read(os.path.join(DOCS, "heads.jsonl")).splitlines() if line.strip()]
        rep = chain.verify(recs, heads)
        self.assertTrue(rep.ok, rep.problems)
        self.assertEqual(heads[-1]["hash"], rep.head["hash"])


class Policy(unittest.TestCase):
    def test_csp_is_exactly_the_strict_one(self):
        metas = [a for t, a in page() if t == "meta" and a.get("http-equiv") == "Content-Security-Policy"]
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["content"], EXPECTED_CSP)

    def test_referrer_policy(self):
        self.assertIn(("meta", {"name": "referrer", "content": "no-referrer"}), page())

    def test_no_inline_scripts_or_handlers(self):
        src = read(os.path.join(DOCS, "index.html"))
        for t, a in page():
            if t == "script":
                self.assertIn("src", a, "inline <script> found")
            for k in a:
                self.assertFalse(k.startswith("on"), f"inline handler {k} on <{t}>")
            self.assertNotIn("style", a, f"inline style on <{t}>")
        self.assertNotRegex(src, r"javascript:")

    def test_everything_loads_from_this_site(self):
        for t, a in page():
            loads = t == "link" and a.get("rel") in ("stylesheet", "preload", "icon", "modulepreload", "manifest")
            url = a.get("src") or (a.get("href") if loads else None)
            if url:
                self.assertFalse(re.match(r"^(https?:)?//", url), f"<{t}> loads {url} from another origin")

    def test_every_script_and_stylesheet_has_current_integrity(self):
        for t, a in page():
            if t == "script" or (t == "link" and a.get("rel") == "stylesheet"):
                self.assertRegex(a.get("integrity", ""), r"^sha384-[A-Za-z0-9+/]{64}$", a)
        out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sri.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_new_tab_links_drop_opener_and_referrer(self):
        for t, a in page():
            if t == "a" and a.get("target") == "_blank":
                rel = set(a.get("rel", "").split())
                self.assertTrue({"noopener", "noreferrer"} <= rel, a)

    def test_only_https_links(self):
        for t, a in page():
            href = a.get("href", "")
            if t == "a" and re.match(r"^[a-z]+:", href):
                self.assertTrue(href.startswith("https://"), href)

    def test_site_code_never_writes_html_or_stores_anything(self):
        for f in SITE_JS:
            s = read(os.path.join(DOCS, f))
            for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                        "localStorage", "sessionStorage", "document.cookie", "indexedDB", "navigator.sendBeacon"):
                self.assertNotIn(bad, s, f"{bad} in {f}")

    def test_fetches_are_same_origin_relative_paths(self):
        for f in ("app.js", "scene.js"):
            for url in re.findall(r"fetch\(\s*([^,)]+)", read(os.path.join(DOCS, f))):
                self.assertNotRegex(url, r"https?:|//", f"{f}: {url}")

    def test_no_secrets_or_keys_in_the_repo(self):
        pat = re.compile(r"(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|sk-[A-Za-z0-9]{32,})")
        for dirpath, dirnames, files in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "out")]
            for name in files:
                if name.endswith((".woff2", ".png", ".pdf", ".min.js")):
                    continue
                try:
                    text = read(os.path.join(dirpath, name))
                except UnicodeDecodeError:
                    continue
                self.assertIsNone(pat.search(text), os.path.join(dirpath, name))

    def test_workflow_is_pinned_and_takes_input_as_data(self):
        wf = read(os.path.join(ROOT, ".github", "workflows", "collect.yml"))
        for use in re.findall(r"uses:\s*(\S+)", wf):
            self.assertRegex(use, r"@[0-9a-f]{40}$", f"{use} is not pinned to a commit")
        self.assertNotRegex(wf, r"run:[^\n]*\$\{\{|^\s+[^#\n]*=\"\$\{\{", "workflow pastes an expression into a script")
        self.assertNotIn("schedule:\n", wf.replace("#  schedule:", ""))


@unittest.skipUnless(NODE, "node is not installed")
class SameAnswers(unittest.TestCase):
    """docs/ledger.js and kanakku/chain.py must agree on everything."""

    HARNESS = r"""
const L = require(process.argv[1]); const fs = require('fs');
const recs = L.parseLines(fs.readFileSync(process.argv[2], 'utf8'));
const heads = L.parseLines(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const out = { verify: await L.verify(recs, heads), tables: [], forged: [] };
  for (const r of recs) out.tables.push(await L.digest(r.table));
  const bump = (t) => { t.rows[0].lvl_inr += 1; };
  const copy = (x) => JSON.parse(JSON.stringify(x));
  for (const i of [0, 1, 20, 57, 58]) {
    for (const k of ['edit', 'rehash1', 'delete', 'swap', 'truncate', 'rewrite']) {
      let r = copy(recs);
      if (k === 'edit') bump(r[i].table);
      if (k === 'rehash1') { bump(r[i].table); r[i].table_sha256 = await L.digest(r[i].table); r[i].hash = await L.recordHash(r[i]); }
      if (k === 'delete') r.splice(Math.min(i, r.length - 2), 1);
      if (k === 'swap') { const j = Math.min(i, r.length - 2); [r[j], r[j + 1]] = [r[j + 1], r[j]]; }
      if (k === 'truncate') r = r.slice(0, Math.min(i, r.length - 2) + 1);
      if (k === 'rewrite') { const o = r.slice(0, i); let p = i ? o[i - 1] : null; for (let j = i; j < r.length; j++) { if (j === i) bump(r[j].table); p = await L.newRecord(p, r[j]); o.push(p); } r = o; }
      out.forged.push({ k, i, records: r, alone: await L.verify(r, []), witnessed: await L.verify(r, heads) });
    }
  }
  const inr = L.implied(recs, 'lvl_inr', 'wk_inr'), usd = L.implied(recs, 'lvl_usd', 'wk_usd');
  out.implied = { n: inr.length + usd.length, nonzero: inr.concat(usd).filter((c) => c.delta !== 0).length, over: inr.concat(usd).filter((c) => Math.abs(c.delta) > L.bound(3)).length };
  const bad = [];
  for (const t of ['[1]', '"x"', '{"a":1}\n[2]', 'not json']) { try { L.parseLines(t); bad.push('accepted ' + t); } catch (e) {} }
  try { L.canonical({ a: 1.5 }); bad.push('accepted a float'); } catch (e) {}
  out.rejects = bad;
  process.stdout.write(JSON.stringify(out));
})();
"""

    @classmethod
    def setUpClass(cls):
        res = subprocess.run([NODE, "-e", cls.HARNESS, os.path.join(DOCS, "ledger.js"), os.path.join(DOCS, "archive.jsonl"),
                              os.path.join(DOCS, "heads.jsonl")], capture_output=True, text=True, timeout=300)
        if res.returncode:
            raise RuntimeError(res.stderr)
        cls.js = json.loads(res.stdout)
        cls.recs = [json.loads(line) for line in read(os.path.join(DOCS, "archive.jsonl")).splitlines() if line.strip()]
        cls.heads = [json.loads(line) for line in read(os.path.join(DOCS, "heads.jsonl")).splitlines() if line.strip()]

    def test_same_head(self):
        py = chain.verify(self.recs, self.heads)
        self.assertTrue(self.js["verify"]["ok"])
        self.assertEqual(self.js["verify"]["head"]["hash"], py.head["hash"])

    def test_same_canonical_encoding(self):
        self.assertEqual(self.js["tables"], [canon.digest(r["table"]) for r in self.recs])

    def test_same_verdict_on_every_forgery(self):
        self.assertEqual(len(self.js["forged"]), 30)
        for f in self.js["forged"]:
            for which, heads in (("alone", []), ("witnessed", self.heads)):
                py = chain.verify(f["records"], heads)
                js = f[which]
                self.assertEqual(js["ok"], py.ok, (f["k"], f["i"], which))
                self.assertEqual([(p["seq"], p["kind"]) for p in js["problems"]], [(p["seq"], p["kind"]) for p in py.problems], (f["k"], f["i"], which))

    def test_the_head_catches_what_the_chain_misses(self):
        by = {(f["k"], f["i"]): f for f in self.js["forged"]}
        for i in (0, 1, 20, 57):
            self.assertFalse(by[("rewrite", i)]["alone"]["problems"])
            self.assertTrue(by[("rewrite", i)]["witnessed"]["problems"])
        self.assertFalse(by[("rehash1", 58)]["alone"]["problems"])
        self.assertTrue(by[("rehash1", 58)]["witnessed"]["problems"])

    def test_same_rounding_numbers(self):
        self.assertEqual(self.js["implied"], {"n": 580, "nonzero": 143, "over": 0})

    def test_rejects_bad_input(self):
        self.assertEqual(self.js["rejects"], [])


if __name__ == "__main__":
    unittest.main()
