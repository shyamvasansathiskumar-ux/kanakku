// Kanakku's verifier, in the browser. A line-for-line port of kanakku/canon.py and
// kanakku/chain.py: the same canonical encoding, the same record hash, the same checks.
// tests/test_site.py runs this file under Node against the archive and requires the
// same answers as the Python verifier.
(function (root) {
  "use strict";
  const GENESIS = "0".repeat(64);
  const FIELDS = ["v", "seq", "source", "series", "url", "fetched_at", "published", "raw_sha256", "table_sha256", "table", "prev", "hash"];
  const subtle = (root.crypto && root.crypto.subtle) || (typeof globalThis !== "undefined" && globalThis.crypto && globalThis.crypto.subtle);
  const enc = new TextEncoder();

  // Canonical JSON: keys sorted, no spaces, integers only, strings as JSON escapes them.
  // Matches json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).
  function canonical(v) {
    if (v === null) return "null";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "number") {
      if (!Number.isSafeInteger(v)) throw new Error("only safe integers are allowed: " + v);
      return String(v);
    }
    if (typeof v === "string") return JSON.stringify(v);
    if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
    if (typeof v === "object") {
      return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}";
    }
    throw new Error("cannot encode " + typeof v);
  }

  async function sha256(text) {
    const buf = await subtle.digest("SHA-256", enc.encode(text));
    return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
  }
  const digest = (obj) => sha256(canonical(obj));
  function withoutHash(rec) { const o = {}; for (const k of Object.keys(rec)) if (k !== "hash") o[k] = rec[k]; return o; }
  const recordHash = (rec) => digest(withoutHash(rec));

  async function newRecord(prev, f) {
    const rec = {
      v: 1, seq: prev ? prev.seq + 1 : 0, source: f.source, series: f.series, url: f.url,
      fetched_at: f.fetched_at, published: f.published, raw_sha256: f.raw_sha256,
      table_sha256: await digest(f.table), table: f.table, prev: prev ? prev.hash : GENESIS,
    };
    rec.hash = await recordHash(rec);
    return rec;
  }

  // Same checks, same problem kinds, same order as chain.verify() in Python.
  async function verify(records, witnessed) {
    const problems = [];
    const add = (seq, kind, detail) => problems.push({ seq, kind, detail });
    let prev = null;
    for (let i = 0; i < records.length; i++) {
      const rec = records[i];
      const keys = Object.keys(rec);
      const missing = FIELDS.filter((k) => !keys.includes(k)), extra = keys.filter((k) => !FIELDS.includes(k));
      if (missing.length || extra.length) { add(rec.seq ?? i, "format", "missing " + missing + " extra " + extra); prev = rec; continue; }
      if (rec.seq !== i) add(rec.seq, "sequence", "position " + i + " holds seq " + rec.seq);
      const want = i === 0 ? GENESIS : prev.hash;
      if (rec.prev !== want) add(rec.seq, "link", "prev does not match the hash of the record before it");
      if ((await recordHash(rec)) !== rec.hash) add(rec.seq, "hash", "record contents do not match its hash");
      if ((await digest(rec.table)) !== rec.table_sha256) add(rec.seq, "table", "table does not match table_sha256");
      if (prev && rec.fetched_at < (prev.fetched_at || "")) add(rec.seq, "time", "fetched_at goes backwards");
      prev = rec;
    }
    const head = records.length ? { seq: records[records.length - 1].seq, hash: records[records.length - 1].hash } : null;
    const bySeq = new Map(records.map((r) => [r.seq, r]));
    for (const h of witnessed || []) {
      const r = bySeq.get(h.seq);
      if (!r) add(h.seq, "truncated", "a witnessed head is missing from the archive");
      else if (r.hash !== h.hash) add(h.seq, "witness", "archive disagrees with a witnessed head (history rewritten)");
    }
    return { ok: problems.length === 0, records: records.length, head, problems };
  }

  // Parse a JSON Lines file strictly: every non-empty line must be one JSON object.
  function parseLines(text, max = 100000) {
    if (typeof text !== "string") throw new Error("not text");
    const out = [];
    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      const v = JSON.parse(line);
      if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error("each line must be a JSON object");
      out.push(v);
      if (out.length > max) throw new Error("too many lines");
    }
    return out;
  }

  // Implied-level check: level(t+1) - change(t+1) against level(t) as first published.
  function implied(records, levelCol, changeCol) {
    const out = [];
    for (let i = 0; i + 1 < records.length; i++) {
      const a = new Map(records[i].table.rows.map((r) => [r.item, r]));
      const b = new Map(records[i + 1].table.rows.map((r) => [r.item, r]));
      for (const [item, ra] of a) {
        const rb = b.get(item);
        if (!rb) continue;
        const imp = rb[levelCol] - rb[changeCol];
        out.push({ i, item, first: ra[levelCol], implied: imp, delta: imp - ra[levelCol], period: ra.as_on });
      }
    }
    return out;
  }
  const bound = (n) => Math.floor(n / 2);

  const L = { GENESIS, FIELDS, canonical, sha256, digest, recordHash, newRecord, verify, parseLines, implied, bound };
  if (typeof module !== "undefined" && module.exports) module.exports = L; else root.Ledger = L;
})(typeof window !== "undefined" ? window : globalThis);
