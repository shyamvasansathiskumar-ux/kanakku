"""Compare two snapshots of the same series and say what changed.

Every difference falls into exactly one class:

  addition    a row (key) that was not there before
  withdrawal  a row that was there before and is now gone
  revision    a published value that changed by more than the tolerance
  rounding    a value that changed by no more than the tolerance
  schema      the key, the value columns, the unit or the base changed

`rounding` exists because publishers round each figure independently: a total
can differ from the sum of its parts, or from last week's level plus this
week's change, by a unit. Flagging those as revisions would bury the real ones.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal

from .canon import num


@dataclass(frozen=True)
class Change:
    kind: str
    key: tuple = ()
    column: str = ""
    old: str = ""
    new: str = ""
    delta: str = ""
    detail: str = ""

    def as_dict(self):
        d = asdict(self)
        d["key"] = list(self.key)
        return d


def _index(table):
    return {tuple(str(r[c]) for c in table["key"]): r for r in table["rows"]}


def compare(old, new, tolerance=0):
    """Return a list of Changes from table `old` to table `new`.
    `tolerance` is an absolute amount in the table's own units (int, Decimal or
    a dict column -> amount)."""
    changes = []
    for field in ("key", "unit", "base"):
        if old.get(field) != new.get(field):
            changes.append(Change("schema", detail=f"{field}: {old.get(field)!r} -> {new.get(field)!r}"))
    added_cols = [c for c in new["columns"] if c not in old["columns"]]
    dropped_cols = [c for c in old["columns"] if c not in new["columns"]]
    if added_cols or dropped_cols:
        changes.append(Change("schema", detail=f"columns added {added_cols} dropped {dropped_cols}"))
    if old["key"] != new["key"]:
        return changes  # rows are not comparable
    a, b = _index(old), _index(new)
    common_cols = [c for c in old["columns"] if c in new["columns"]]
    for k in sorted(b.keys() - a.keys()):
        changes.append(Change("addition", key=k))
    for k in sorted(a.keys() - b.keys()):
        changes.append(Change("withdrawal", key=k))
    for k in sorted(a.keys() & b.keys()):
        for c in common_cols:
            ov, nv = a[k][c], b[k][c]
            if ov == nv:
                continue
            try:
                d = num(nv) - num(ov)
            except Exception:
                changes.append(Change("revision", k, c, str(ov), str(nv), "", "non-numeric"))
                continue
            if d == 0:
                continue  # same number written differently, e.g. "5" and "5.0"
            tol = tolerance.get(c, 0) if isinstance(tolerance, dict) else tolerance
            kind = "rounding" if abs(d) <= Decimal(tol) else "revision"
            changes.append(Change(kind, k, c, str(ov), str(nv), str(d)))
    return changes


def summary(changes):
    out = {"addition": 0, "withdrawal": 0, "revision": 0, "rounding": 0, "schema": 0}
    for ch in changes:
        out[ch.kind] += 1
    return out
