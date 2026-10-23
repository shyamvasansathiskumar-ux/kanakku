"""Derived figures that can be re-checked.

A derived figure (an exchange rate implied by two columns, a share, a cost
estimate) is only as trustworthy as its inputs and assumptions. Here every
derived figure records the exact snapshot hashes it read and the hash of
every assumption it used, so anyone can recompute it from the archive and
get the same digits, or see exactly which input changed.

Formulas are a fixed registry; nothing is evaluated from strings.
"""
from decimal import Decimal, getcontext

from .canon import digest, num

getcontext().prec = 34


def assumption(aid, value, unit, source, valid_from, note=""):
    """A dated, sourced assumption. Its hash goes into every result that uses it."""
    a = {"id": aid, "value": str(value), "unit": unit, "source": source, "valid_from": valid_from}
    if note:
        a["note"] = note
    a["sha256"] = digest({k: v for k, v in a.items() if k != "sha256"})
    return a


def _get(record, item_col, item, column):
    for row in record["table"]["rows"]:
        if row[item_col] == item:
            return num(row[column])
    raise KeyError(f"{item} not in snapshot {record['seq']}")


def _q(x, places):
    return str(x.quantize(Decimal(1).scaleb(-places)))


FORMULAS = {}


def formula(name):
    def reg(fn):
        FORMULAS[name] = fn
        return fn
    return reg


@formula("implied_rate")
def implied_rate(record, assumptions, *, item_col, item, inr_col, usd_col):
    """Rupees per US dollar implied by a table that prints both ₹ crore and US$ million."""
    crore = num(assumptions["crore"]["value"])
    million = num(assumptions["million"]["value"])
    inr = _get(record, item_col, item, inr_col) * crore
    usd = _get(record, item_col, item, usd_col) * million
    return _q(inr / usd, 4), "INR per USD"


@formula("share")
def share(record, assumptions, *, item_col, part, total, column):
    """Part as a percentage of total, from the same snapshot."""
    p, t = _get(record, item_col, part, column), _get(record, item_col, total, column)
    return _q(p * 100 / t, 2), "percent"


def derive(name, record, assumptions=(), **params):
    """Compute a registered formula on one snapshot. Returns the value plus the
    provenance needed to recompute it."""
    if name not in FORMULAS:
        raise KeyError(f"unknown formula {name}")
    amap = {a["id"]: a for a in assumptions}
    for a in assumptions:
        if digest({k: v for k, v in a.items() if k != "sha256"}) != a["sha256"]:
            raise ValueError(f"assumption {a['id']} does not match its hash")
    value, unit = FORMULAS[name](record, amap, **params)
    out = {
        "formula": name,
        "params": {k: str(v) for k, v in sorted(params.items())},
        "value": value,
        "unit": unit,
        "inputs": [{"seq": record["seq"], "hash": record["hash"], "table_sha256": record["table_sha256"]}],
        "assumptions": [{"id": a["id"], "sha256": a["sha256"]} for a in assumptions],
    }
    out["sha256"] = digest(out)
    return out


def recheck(result, records_by_seq, assumptions):
    """Recompute a stored result from the archive; True only if inputs, assumptions
    and the value all match."""
    for inp in result["inputs"]:
        r = records_by_seq.get(inp["seq"])
        if r is None or r["hash"] != inp["hash"]:
            return False
    amap = {a["id"]: a for a in assumptions}
    for a in result["assumptions"]:
        if a["id"] not in amap or amap[a["id"]]["sha256"] != a["sha256"]:
            return False
    rec = records_by_seq[result["inputs"][0]["seq"]]
    params = dict(result["params"])
    again = derive(result["formula"], rec, [amap[a["id"]] for a in result["assumptions"]], **params)
    return again["value"] == result["value"] and again["sha256"] == result["sha256"]
