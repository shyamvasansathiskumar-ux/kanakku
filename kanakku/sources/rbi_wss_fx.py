"""RBI Weekly Statistical Supplement, table 2: Foreign Exchange Reserves.

The table prints five rows (total and four components) and eight numbers per
row: the level in ₹ crore and US$ million, then the change over the week,
since end-March and over the year, each in both currencies. Every figure is
rounded on its own, so a total can differ from the sum of its parts by a unit
(the RBI footnote says so).
"""
import csv
import html.parser
import re
from datetime import datetime

from ..canon import make_table

SERIES = "rbi.wss.fx_reserves"
ITEMS = [("1", "Total Reserves"), ("1.1", "Foreign Currency Assets"), ("1.2", "Gold"),
         ("1.3", "SDRs"), ("1.4", "Reserve Position in the IMF")]
COLUMNS = ["lvl_inr", "lvl_usd", "wk_inr", "wk_usd", "em_inr", "em_usd", "yr_inr", "yr_usd"]
UNIT = {"inr": "INR crore", "usd": "USD million"}
# Every printed figure is rounded to the nearest unit, so each is off from the
# exact value by at most 0.5. A check that adds or subtracts n printed figures
# is off by at most n/2, and because the printed figures are integers the
# check's result is an integer, so it is off by at most floor(n/2):
#   level(t+1) - change(t+1) - level(t)   3 figures -> at most 1 unit
#   total - (four components)             5 figures -> at most 2 units
# Anything larger cannot be rounding.
TOLERANCE_IMPLIED = 1
TOLERANCE_IDENTITY = 2
TOLERANCE = TOLERANCE_IMPLIED


def table_from_rows(as_on, endmarch, rows):
    """rows: {item_code: {col: int}} -> canonical table."""
    out = []
    for code, name in ITEMS:
        r = {"as_on": as_on, "item": code, "name": name}
        r.update({c: int(rows[code][c]) for c in COLUMNS})
        out.append(r)
    return make_table(SERIES, ["as_on", "item"], ["name"] + COLUMNS, out, unit=UNIT,
                      notes={"end_march": str(endmarch)})


def snapshots_from_csv(path):
    """Read the evaluation dataset (one line per row per release) into
    [(release_date, wssview_id, table)] in release order."""
    by = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["release_date"], r["wssview_id"], r["as_on"], r["endmarch_label"])
            by.setdefault(key, {})[r["row"]] = {c: r[c] for c in COLUMNS}
    out = []
    for (rel, wid, as_on, em), rows in sorted(by.items()):
        out.append((rel, wid, table_from_rows(as_on, em, rows)))
    return out


class _Cells(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        s = data.strip()
        if s:
            self.text.append(s)


_NUM = re.compile(r"^-?\d[\d,]*$")
_ASON = re.compile(r"As on\s+([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s+(\d{4})")
_EM = re.compile(r"End-?\s*March\s+(\d{4})")


def parse_html(html_text):
    """Parse the published HTML table. Returns a canonical table.
    Raises ValueError if anything expected is missing, rather than guessing."""
    p = _Cells()
    p.feed(html_text)
    tokens = p.text
    joined = " ".join(tokens)
    m = _ASON.search(joined)
    if not m:
        raise ValueError("no 'As on' date")
    as_on = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date().isoformat()
    em = _EM.search(joined)
    if not em:
        raise ValueError("no End-March column")
    rows = {}
    for code, name in ITEMS:
        idx = None
        for i, t in enumerate(tokens):
            if name.lower() in t.lower() and (t.startswith(code) or (i > 0 and tokens[i - 1] == code)):
                idx = i
                break
        if idx is None:
            raise ValueError(f"row not found: {code} {name}")
        nums = []
        for t in tokens[idx + 1:]:
            if _NUM.match(t):
                nums.append(int(t.replace(",", "")))
                if len(nums) == 8:
                    break
            elif t in ("#", "*"):
                continue
            elif nums:
                break
        if len(nums) != 8:
            raise ValueError(f"row {code}: expected 8 numbers, got {len(nums)}")
        rows[code] = dict(zip(COLUMNS, nums))
    return table_from_rows(as_on, em.group(1), rows)
