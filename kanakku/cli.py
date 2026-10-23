"""Command line.

  kanakku verify  ARCHIVE [--heads HEADS]
  kanakku diff    ARCHIVE SEQ_OLD SEQ_NEW [--tolerance N]
  kanakku vintages ARCHIVE SERIES COLUMN
  kanakku import-wss CSV ARCHIVE         (load the RBI forex evaluation dataset)
  kanakku fetch-wss DATE ARCHIVE         (fetch one week live; DATE = release Friday, YYYY-MM-DD)
  kanakku witness ARCHIVE HEADS
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone

from . import chain, diff, vintage
from .sources import rbi_wss_fx


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cmd_verify(a):
    recs = chain.Archive(a.archive).records()
    heads = chain.load_heads(a.heads) if a.heads else []
    rep = chain.verify(recs, heads)
    print(json.dumps({"ok": rep.ok, "records": rep.records, "head": rep.head,
                      "witnessed_heads_checked": len(heads), "problems": rep.problems}, indent=2))
    return 0 if rep.ok else 1


def cmd_diff(a):
    recs = {r["seq"]: r for r in chain.Archive(a.archive).records()}
    ch = diff.compare(recs[a.old]["table"], recs[a.new]["table"], a.tolerance)
    print(json.dumps({"summary": diff.summary(ch), "changes": [c.as_dict() for c in ch]}, indent=2))
    return 0


def cmd_vintages(a):
    recs = chain.Archive(a.archive).records()
    m = vintage.vintage_matrix(recs, a.series, a.column)
    print(json.dumps({"|".join(k): v for k, v in m.items()}, indent=2))
    return 0


def cmd_import_wss(a):
    arc = chain.Archive(a.archive)
    with open(a.csv, "rb") as f:
        raw_sha = chain.digest({"file": f.read().decode("utf-8")})
    n = 0
    for rel, wid, table in rbi_wss_fx.snapshots_from_csv(a.csv):
        url = f"https://rbi.org.in/Scripts/WSSView.aspx?Id={wid}" if wid.isdigit() else \
            "https://www.rbi.org.in/Scripts/BS_ViewWssExtractdetails.aspx?id=" + wid.replace("extract", "")
        arc.append(source="rbi", series=rbi_wss_fx.SERIES, url=url, fetched_at=a.fetched_at,
                   published=rel, raw_sha256=raw_sha, table=table)
        n += 1
    print(f"imported {n} snapshots")
    return 0


def cmd_fetch_wss(a):
    from .fetch import Fetcher
    d = datetime.strptime(a.date, "%Y-%m-%d")
    index = ("https://rbi.org.in/Scripts/WSSViewDetail.aspx?TYPE=Basic&PARAM1="
             + d.strftime("%m%%2F%d%%2F%Y"))
    f = Fetcher()
    body, _ = f.get(index)
    m = re.search(r"Foreign Exchange Reserves.{0,400}?WSSView\.aspx\?Id=(\d+)", body.decode("utf-8", "replace"), re.S)
    if not m:
        print("no Foreign Exchange Reserves table listed for that date", file=sys.stderr)
        return 2
    url = f"https://rbi.org.in/Scripts/WSSView.aspx?Id={m.group(1)}"
    body, raw_sha = f.get(url)
    table = rbi_wss_fx.parse_html(body.decode("utf-8", "replace"))
    arc = chain.Archive(a.archive)
    last = arc.latest(rbi_wss_fx.SERIES)
    if last and last["table_sha256"] == chain.digest(table) and last["published"] == a.date:
        print("unchanged; nothing appended")
        return 0
    rec = arc.append(source="rbi", series=rbi_wss_fx.SERIES, url=url, fetched_at=_now(),
                     published=a.date, raw_sha256=raw_sha, table=table)
    print(json.dumps({"seq": rec["seq"], "hash": rec["hash"]}))
    return 0


def cmd_witness(a):
    print(json.dumps(chain.witness(chain.Archive(a.archive), a.heads)))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="kanakku")
    s = p.add_subparsers(dest="cmd", required=True)
    v = s.add_parser("verify"); v.add_argument("archive"); v.add_argument("--heads"); v.set_defaults(f=cmd_verify)
    d = s.add_parser("diff"); d.add_argument("archive"); d.add_argument("old", type=int); d.add_argument("new", type=int)
    d.add_argument("--tolerance", type=int, default=0); d.set_defaults(f=cmd_diff)
    g = s.add_parser("vintages"); g.add_argument("archive"); g.add_argument("series"); g.add_argument("column")
    g.set_defaults(f=cmd_vintages)
    i = s.add_parser("import-wss"); i.add_argument("csv"); i.add_argument("archive")
    i.add_argument("--fetched-at", default="2026-10-23T00:00:00Z"); i.set_defaults(f=cmd_import_wss)
    w = s.add_parser("fetch-wss"); w.add_argument("date"); w.add_argument("archive"); w.set_defaults(f=cmd_fetch_wss)
    h = s.add_parser("witness"); h.add_argument("archive"); h.add_argument("heads"); h.set_defaults(f=cmd_witness)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
