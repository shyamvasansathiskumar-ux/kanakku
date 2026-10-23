"""Canonical encoding and hashing.

Every hash in Kanakku is SHA-256 over a canonical JSON encoding: keys sorted,
no insignificant whitespace, UTF-8. Numbers are stored as integers or as
decimal strings ("12.5"), never as floats, so the same table always encodes
to the same bytes on every machine.
"""
import hashlib
import json
from decimal import Decimal, InvalidOperation


class CanonError(ValueError):
    pass


def _check(obj, path="$"):
    if isinstance(obj, float):
        raise CanonError(f"float at {path}: store decimals as strings")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonError(f"non-string key at {path}")
            _check(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check(v, f"{path}[{i}]")


def canonical(obj) -> bytes:
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(obj) -> str:
    return sha256(canonical(obj))


def num(value) -> Decimal:
    """Parse an archived value (int or decimal string) into a Decimal."""
    if isinstance(value, bool):
        raise CanonError("boolean is not a number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.replace(",", "").strip())
        except InvalidOperation as e:
            raise CanonError(f"not a number: {value!r}") from e
    raise CanonError(f"not a number: {value!r}")


def make_table(series, key, columns, rows, unit=None, base=None, notes=None):
    """Build a canonical table. `key` columns identify a row; `columns` hold values."""
    if not key or not columns:
        raise CanonError("a table needs key and value columns")
    seen = set()
    out = []
    for r in rows:
        missing = [c for c in key + columns if c not in r]
        if missing:
            raise CanonError(f"row missing {missing}")
        k = tuple(str(r[c]) for c in key)
        if k in seen:
            raise CanonError(f"duplicate key {k}")
        seen.add(k)
        out.append({c: r[c] for c in key + columns})
    out.sort(key=lambda r: tuple(str(r[c]) for c in key))
    t = {"series": series, "key": list(key), "columns": list(columns), "rows": out}
    if unit is not None:
        t["unit"] = unit
    if base is not None:
        t["base"] = base
    if notes is not None:
        t["notes"] = notes
    _check(t)
    return t
