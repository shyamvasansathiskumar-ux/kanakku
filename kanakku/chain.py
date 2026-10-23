"""The append-only archive.

One snapshot per line (JSON Lines). Each record carries the SHA-256 of the
previous record, so deleting, reordering or editing any earlier snapshot
breaks every hash after it.

A hash chain on its own cannot stop someone who controls the file from
rewriting it end to end and recomputing every hash, and it cannot show that
the newest records were cut off. Both need an outside witness: the head
(sequence number + hash) is published somewhere the archive keeper does not
control after every update, and `verify` checks the chain against every
witnessed head it is given.
"""
import json
import os
from dataclasses import dataclass, field

from .canon import canonical, digest

FORMAT = 1
GENESIS = "0" * 64
RECORD_FIELDS = {"v", "seq", "source", "series", "url", "fetched_at", "published",
                 "raw_sha256", "table_sha256", "table", "prev", "hash"}


def record_hash(rec: dict) -> str:
    return digest({k: v for k, v in rec.items() if k != "hash"})


def new_record(prev: dict | None, *, source, series, url, fetched_at, published, raw_sha256, table):
    rec = {
        "v": FORMAT,
        "seq": 0 if prev is None else prev["seq"] + 1,
        "source": source,
        "series": series,
        "url": url,
        "fetched_at": fetched_at,
        "published": published,
        "raw_sha256": raw_sha256,
        "table_sha256": digest(table),
        "table": table,
        "prev": GENESIS if prev is None else prev["hash"],
    }
    rec["hash"] = record_hash(rec)
    return rec


@dataclass
class Report:
    records: int = 0
    head: dict | None = None
    problems: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.problems

    def add(self, seq, kind, detail):
        self.problems.append({"seq": seq, "kind": kind, "detail": detail})


def verify(records, witnessed_heads=()):
    """Check a list of records. Returns a Report; Report.ok is True only if
    every link, hash, table hash and witnessed head checks out."""
    rep = Report(records=len(records))
    prev = None
    for i, rec in enumerate(records):
        extra = set(rec) - RECORD_FIELDS
        missing = RECORD_FIELDS - set(rec)
        if missing or extra:
            rep.add(rec.get("seq", i), "format", f"missing {sorted(missing)} extra {sorted(extra)}")
            prev = rec
            continue
        if rec["seq"] != i:
            rep.add(rec["seq"], "sequence", f"position {i} holds seq {rec['seq']}")
        want_prev = GENESIS if i == 0 else prev.get("hash")
        if rec["prev"] != want_prev:
            rep.add(rec["seq"], "link", "prev does not match the hash of the record before it")
        if record_hash(rec) != rec["hash"]:
            rep.add(rec["seq"], "hash", "record contents do not match its hash")
        if digest(rec["table"]) != rec["table_sha256"]:
            rep.add(rec["seq"], "table", "table does not match table_sha256")
        if prev is not None and rec["fetched_at"] < prev.get("fetched_at", ""):
            rep.add(rec["seq"], "time", "fetched_at goes backwards")
        prev = rec
    if records:
        rep.head = {"seq": records[-1].get("seq"), "hash": records[-1].get("hash")}
    by_seq = {r.get("seq"): r for r in records}
    for h in witnessed_heads:
        r = by_seq.get(h["seq"])
        if r is None:
            rep.add(h["seq"], "truncated", "a witnessed head is missing from the archive")
        elif r.get("hash") != h["hash"]:
            rep.add(h["seq"], "witness", "archive disagrees with a witnessed head (history rewritten)")
    return rep


class Archive:
    """A JSON Lines archive on disk. Appends only; never rewrites a line."""

    def __init__(self, path):
        self.path = path

    def records(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def head(self):
        recs = self.records()
        return None if not recs else recs[-1]

    def append(self, **kw):
        recs = self.records()
        rep = verify(recs)
        if not rep.ok:
            raise RuntimeError(f"refusing to append to a broken archive: {rep.problems[:3]}")
        rec = new_record(recs[-1] if recs else None, **kw)
        with open(self.path, "ab") as f:
            f.write(canonical(rec) + b"\n")
            f.flush()
            os.fsync(f.fileno())
        return rec

    def latest(self, series, before_seq=None):
        """The newest snapshot of `series` (optionally strictly before a seq)."""
        best = None
        for r in self.records():
            if r["series"] == series and (before_seq is None or r["seq"] < before_seq):
                best = r
        return best


def load_heads(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def witness(archive: Archive, heads_path):
    """Record the current head in a heads file (to be published elsewhere)."""
    h = archive.head()
    if h is None:
        return None
    entry = {"seq": h["seq"], "hash": h["hash"], "fetched_at": h["fetched_at"]}
    with open(heads_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry
