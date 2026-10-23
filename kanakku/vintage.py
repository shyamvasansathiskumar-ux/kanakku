"""Vintages: what was published about each period, and when.

A *vintage* is the value of a figure as it stood in one snapshot. Keeping
every vintage, rather than only the newest number, is what lets anyone ask
"what did the dashboard say on 1 May?" and get an answer that can be checked.

Two checks here go beyond a plain diff:

* implied_checks  Many tables print a level and its change since the last
                  release. The previous level is then implied: level - change.
                  Comparing it with the level first published last time shows
                  whether last week's figure was quietly revised.
* identity_checks A total should equal the sum of its parts.

Both need a tolerance, because each printed figure is rounded on its own.
"""
from decimal import Decimal

from .canon import num


def vintage_matrix(records, series, value_col, key_cols=None):
    """{key: [(published, seq, value), ...]} across all snapshots of a series."""
    out = {}
    for r in records:
        if r["series"] != series:
            continue
        t = r["table"]
        kc = key_cols or t["key"]
        for row in t["rows"]:
            k = tuple(str(row[c]) for c in kc)
            out.setdefault(k, []).append((r["published"], r["seq"], row[value_col]))
    return out


def first_releases(matrix):
    return {k: v[0][2] for k, v in matrix.items()}


def revisions_between_vintages(matrix, tolerance=0):
    """For each key, every change between consecutive vintages."""
    out = []
    for k, vs in matrix.items():
        for (p0, s0, v0), (p1, s1, v1) in zip(vs, vs[1:]):
            d = num(v1) - num(v0)
            if d != 0:
                kind = "rounding" if abs(d) <= Decimal(tolerance) else "revision"
                out.append({"key": list(k), "from": p0, "to": p1, "old": str(v0), "new": str(v1),
                            "delta": str(d), "kind": kind})
    return out


def _single_period(table, period_col):
    periods = {row[period_col] for row in table["rows"]}
    if len(periods) != 1:
        raise ValueError(f"expected one {period_col} per snapshot, got {sorted(periods)}")
    return periods.pop()


def implied_checks(records, series, *, period_col, item_col, level_col, change_col, tolerance=0):
    """Compare each first-published level with the level implied by the next
    release (next level - next change). Snapshots must be in release order and
    hold one period each."""
    snaps = [r for r in records if r["series"] == series]
    out = []
    for a, b in zip(snaps, snaps[1:]):
        pa = _single_period(a["table"], period_col)
        pb = _single_period(b["table"], period_col)
        rows_a = {row[item_col]: row for row in a["table"]["rows"]}
        rows_b = {row[item_col]: row for row in b["table"]["rows"]}
        for item in sorted(rows_a.keys() & rows_b.keys()):
            first = num(rows_a[item][level_col])
            implied = num(rows_b[item][level_col]) - num(rows_b[item][change_col])
            d = implied - first
            kind = "match" if d == 0 else ("rounding" if abs(d) <= Decimal(tolerance) else "revision")
            out.append({"period": pa, "next_period": pb, "item": item, "column": level_col,
                        "first": str(first), "implied": str(implied), "delta": str(d), "kind": kind,
                        "first_seq": a["seq"], "implied_seq": b["seq"]})
    return out


def identity_checks(records, series, *, item_col, total_item, part_items, columns, tolerance=0):
    """Check total == sum(parts) in every snapshot, for each column."""
    out = []
    for r in records:
        if r["series"] != series:
            continue
        rows = {row[item_col]: row for row in r["table"]["rows"]}
        if total_item not in rows or not all(p in rows for p in part_items):
            out.append({"seq": r["seq"], "kind": "incomplete"})
            continue
        for c in columns:
            d = num(rows[total_item][c]) - sum(num(rows[p][c]) for p in part_items)
            kind = "match" if d == 0 else ("rounding" if abs(d) <= Decimal(tolerance) else "mismatch")
            out.append({"seq": r["seq"], "published": r["published"], "column": c, "delta": str(d), "kind": kind})
    return out
