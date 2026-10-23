"""Reproduce every number and figure in the paper.

  python3 experiments/run_eval.py            -> experiments/out/results.json, figures, archive

Deterministic: the only randomness is seeded.
"""
import copy
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kanakku import canon, chain, diff, estimate, vintage  # noqa: E402
from kanakku.sources import rbi_wss_fx  # noqa: E402

OUT = os.path.join(ROOT, "experiments", "out")
DATA = os.path.join(ROOT, "data", "raw", "wss_fx.csv")
GDP = os.path.join(ROOT, "data", "raw", "gdp_vintages.json")
FETCHED = "2026-10-23T00:00:00Z"
S = rbi_wss_fx.SERIES


def build_rbi():
    with open(DATA, "rb") as f:
        raw = canon.sha256(f.read())
    recs, prev = [], None
    for rel, wid, t in rbi_wss_fx.snapshots_from_csv(DATA):
        url = (f"https://rbi.org.in/Scripts/WSSView.aspx?Id={wid}" if wid.isdigit() else
               "https://www.rbi.org.in/Scripts/BS_ViewWssExtractdetails.aspx?id=" + wid.replace("extract", ""))
        prev = chain.new_record(prev, source="rbi", series=S, url=url, fetched_at=FETCHED, published=rel,
                                raw_sha256=raw, table=t)
        recs.append(prev)
    return recs


# ---------------------------------------------------------------- E1 integrity
def rewrite_from(recs, i, mutate):
    out, prev = recs[:i], (recs[i - 1] if i else None)
    for j in range(i, len(recs)):
        t = copy.deepcopy(recs[j]["table"])
        if j == i:
            mutate(t)
        r = recs[j]
        prev = chain.new_record(prev, source=r["source"], series=r["series"], url=r["url"],
                                fetched_at=r["fetched_at"], published=r["published"], raw_sha256=r["raw_sha256"],
                                table=t)
        out.append(prev)
    return out


def bump(t):
    t["rows"][0]["lvl_inr"] += 1


def attacks(recs):
    n = len(recs)
    for i in range(n):
        r = copy.deepcopy(recs); r[i]["table"]["rows"][0]["lvl_inr"] += 1
        yield "edit value (no re-hash)", i, r
        r = copy.deepcopy(recs); r[i]["published"] = "2000-01-01"
        yield "edit metadata (no re-hash)", i, r
        r = copy.deepcopy(recs); bump(r[i]["table"]); r[i]["table_sha256"] = canon.digest(r[i]["table"])
        r[i]["hash"] = chain.record_hash(r[i])
        yield "edit + re-hash one record", i, r
        if i < n - 1:
            yield "delete one record", i, recs[:i] + recs[i + 1:]
            r = recs[:]; r[i], r[i + 1] = r[i + 1], r[i]
            yield "swap two records", i, r
            yield "truncate tail", i, recs[:i + 1]
        yield "rewrite + re-hash all later", i, rewrite_from(recs, i, bump)


def e1(recs):
    every = [{"seq": r["seq"], "hash": r["hash"]} for r in recs]
    monthly = every[3::4] + ([every[-1]] if (len(every) - 1) % 4 != 3 else [])
    res = {}
    for name, i, forged in attacks(recs):
        row = res.setdefault(name, {"trials": 0, "chain_only": 0, "monthly_witness": 0, "weekly_witness": 0})
        row["trials"] += 1
        row["chain_only"] += not chain.verify(forged).ok
        row["monthly_witness"] += not chain.verify(forged, monthly).ok
        row["weekly_witness"] += not chain.verify(forged, every).ok
    return res


# ------------------------------------------------------------- E2 revisions
def e2(recs):
    out = {}
    for cur in ("inr", "usd"):
        kw = dict(period_col="as_on", item_col="item", level_col=f"lvl_{cur}", change_col=f"wk_{cur}")
        strict = vintage.implied_checks(recs, S, **kw)
        tol = vintage.implied_checks(recs, S, tolerance=rbi_wss_fx.TOLERANCE, **kw)
        deltas = [int(c["delta"]) for c in strict]
        out[cur] = {
            "pairs": len(strict),
            "exact": sum(d == 0 for d in deltas),
            "naive_flags": sum(d != 0 for d in deltas),
            "max_abs_delta": max(abs(d) for d in deltas),
            "delta_hist": {str(k): deltas.count(k) for k in sorted(set(deltas))},
            "revisions_at_tolerance": sum(c["kind"] == "revision" for c in tol),
        }
        ident = vintage.identity_checks(recs, S, item_col="item", total_item="1",
                                        part_items=["1.1", "1.2", "1.3", "1.4"], columns=[f"lvl_{cur}"],
                                        tolerance=rbi_wss_fx.TOLERANCE_IDENTITY)
        out[cur]["identity"] = {"checks": len(ident), "exact": sum(r["kind"] == "match" for r in ident),
                                "rounding": sum(r["kind"] == "rounding" for r in ident),
                                "mismatch": sum(r["kind"] == "mismatch" for r in ident)}
    # year-lag: level - change over year vs the level first published 52 weeks earlier
    by = {r["table"]["rows"][0]["as_on"]: r for r in recs}
    import datetime as dt
    lag = []
    for d, r in by.items():
        p = (dt.date.fromisoformat(d) - dt.timedelta(364)).isoformat()
        if p in by:
            old = {row["item"]: row for row in by[p]["table"]["rows"]}
            for row in r["table"]["rows"]:
                for cur in ("inr", "usd"):
                    lag.append(row[f"lvl_{cur}"] - row[f"yr_{cur}"] - old[row["item"]][f"lvl_{cur}"])
    out["year_lag"] = {"checks": len(lag), "exact": lag.count(0), "max_abs_delta": max(map(abs, lag))}
    em = {}
    for r in recs:
        row = r["table"]["rows"][0]
        fy = r["table"]["notes"]["end_march"]
        for cur in ("inr", "usd"):
            em.setdefault(f"{fy}_{cur}", set()).add(row[f"lvl_{cur}"] - row[f"em_{cur}"])
    out["end_march_base"] = {k: sorted(v) for k, v in em.items()}
    return out


# --------------------------------------------------------- E3 detection power
def e3(recs, trials=400, seed=7):
    rnd = random.Random(seed)
    sizes = [1, 2, 3, 5, 10, 100, 1000]
    items = ["1", "1.1", "1.2", "1.3", "1.4"]
    res = {}
    for s in sizes:
        hit = fp = 0
        for _ in range(trials):
            r = copy.deepcopy(recs)
            i = rnd.randrange(1, len(r) - 1)
            item = rnd.choice(items)
            sign = rnd.choice((-1, 1))
            for row in r[i]["table"]["rows"]:
                if row["item"] == item:
                    row["lvl_inr"] += sign * s
            found = vintage.implied_checks(r, S, period_col="as_on", item_col="item", level_col="lvl_inr",
                                           change_col="wk_inr", tolerance=rbi_wss_fx.TOLERANCE)
            flagged = {(c["first_seq"], c["implied_seq"], c["item"]) for c in found if c["kind"] == "revision"}
            truth = {(i - 1, i, item), (i, i + 1, item)}
            hit += bool(flagged & truth)
            fp += len(flagged - truth)
        res[str(s)] = {"trials": trials, "recall": hit / trials, "false_flags": fp}
    return res


# --------------------------------------------------------------- E4 GDP vintages
def e4():
    with open(GDP, encoding="utf-8") as f:
        g = json.load(f)
    recs, prev = [], None
    for v in g["vintages"]:
        rows = [{"period": p, "growth_pct": x["value"]} for p, x in v["values"].items()]
        t = canon.make_table("mospi.gdp.real_growth", ["period"], ["growth_pct"], rows, unit="percent y-o-y",
                             base=v["base"])
        prev = chain.new_record(prev, source="mospi", series="mospi.gdp.real_growth", url=v["source"],
                                fetched_at=FETCHED, published=v["released"], raw_sha256=canon.sha256(b""), table=t)
        recs.append(prev)
    schema = []
    for a, b in zip(recs, recs[1:]):
        for c in diff.compare(a["table"], b["table"]):
            if c.kind == "schema":
                schema.append({"from": a["published"], "to": b["published"], "detail": c.detail})
    m = vintage.vintage_matrix(recs, "mospi.gdp.real_growth", "growth_pct")
    base = {r["seq"]: r["table"]["base"] for r in recs}
    revs = []
    for k, vs in m.items():
        for (p0, s0, v0), (p1, s1, v1) in zip(vs, vs[1:]):
            if v0 != v1:
                revs.append({"period": k[0], "from": p0, "to": p1, "old": v0, "new": v1,
                             "delta_pp": str(canon.num(v1) - canon.num(v0)),
                             "across_bases": base[s0] != base[s1]})
    return {"vintages": len(recs), "schema_events": schema, "revisions": revs,
            "matrix": {"|".join(k): v for k, v in m.items()}}


# ------------------------------------------------------------- E5 performance
def e5():
    out = {}
    t = canon.make_table("demo", ["k"], ["v"], [{"k": str(i), "v": i} for i in range(5)])
    for n in (10_000, 100_000):
        recs, prev = [], None
        t0 = time.perf_counter()
        for i in range(n):
            prev = chain.new_record(prev, source="d", series="d", url="u", fetched_at=f"{i:012d}",
                                    published="p", raw_sha256="0" * 64, table=t)
            recs.append(prev)
        t1 = time.perf_counter()
        ok = chain.verify(recs).ok
        t2 = time.perf_counter()
        out[str(n)] = {"append_s": round(t1 - t0, 2), "verify_s": round(t2 - t1, 2), "ok": ok}
    return out


def e6(recs):
    A = [estimate.assumption("crore", 10_000_000, "INR", "Indian numbering system: 1 crore = 10^7", "1900-01-01"),
         estimate.assumption("million", 1_000_000, "USD", "SI prefix: 1 million = 10^6", "1900-01-01")]
    by = {r["seq"]: r for r in recs}
    series = []
    for r in recs:
        x = estimate.derive("implied_rate", r, A, item_col="item", item="1", inr_col="lvl_inr", usd_col="lvl_usd")
        g = estimate.derive("share", r, [], item_col="item", part="1.2", total="1", column="lvl_usd")
        assert estimate.recheck(x, by, A) and estimate.recheck(g, by, [])
        series.append({"as_on": r["table"]["rows"][0]["as_on"], "rate": x["value"], "gold_share": g["value"],
                       "total_usd": r["table"]["rows"][0]["lvl_usd"]})
    return series


def figures(recs, r2, r3, r6):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.spines.top": False,
                         "axes.spines.right": False})
    import datetime as dt
    d = [dt.date.fromisoformat(x["as_on"]) for x in r6]
    fig, ax = plt.subplots(figsize=(3.4, 2.0))
    ax.plot(d, [x["total_usd"] / 1000 for x in r6], color="#1f3b5c", lw=1.2)
    ax.set_ylabel("Total reserves (US$ bn)")
    ax2 = ax.twinx()
    ax2.plot(d, [float(x["rate"]) for x in r6], color="#b5651d", lw=1, ls="--")
    ax2.set_ylabel("Implied ₹ per US$", color="#b5651d")
    ax2.spines["top"].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_reserves.pdf"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(3.4, 1.8))
    h = r2["inr"]["delta_hist"]
    ks = sorted(int(k) for k in h)
    ax.bar([str(k) for k in ks], [h[str(k)] for k in ks], color="#1f3b5c")
    ax.set_xlabel("Implied minus first-published level (₹ crore)")
    ax.set_ylabel("Week pairs × rows")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_deltas.pdf"))
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(3.4, 1.8))
    xs = list(r3)
    ax.plot(range(len(xs)), [r3[k]["recall"] for k in xs], marker="o", color="#1f3b5c", lw=1)
    ax.set_xticks(range(len(xs)), xs)
    ax.set_xlabel("Size of injected revision (₹ crore)")
    ax.set_ylabel("Recall")
    ax.set_ylim(-0.05, 1.05)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_power.pdf"))
    plt.close(fig)


def main():
    os.makedirs(OUT, exist_ok=True)
    recs = build_rbi()
    with open(os.path.join(OUT, "rbi_fx_archive.jsonl"), "wb") as f:
        for r in recs:
            f.write(canon.canonical(r) + b"\n")
    with open(os.path.join(OUT, "rbi_fx_heads.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps({"seq": r["seq"], "hash": r["hash"]}) + "\n")
    res = {"dataset": {"snapshots": len(recs), "rows": 5 * len(recs),
                       "first_release": recs[0]["published"], "last_release": recs[-1]["published"],
                       "head": recs[-1]["hash"], "bytes": os.path.getsize(os.path.join(OUT, "rbi_fx_archive.jsonl"))}}
    res["E1_integrity"] = e1(recs)
    res["E2_revisions"] = e2(recs)
    res["E3_power"] = e3(recs)
    res["E4_gdp"] = e4()
    res["E5_performance"] = e5()
    r6 = e6(recs)
    res["E6_estimates"] = {"weeks": len(r6), "rate_min": min(r6, key=lambda x: float(x["rate"])),
                           "rate_max": max(r6, key=lambda x: float(x["rate"])), "all_rechecked": True}
    with open(os.path.join(OUT, "estimates.json"), "w") as f:
        json.dump(r6, f, indent=1)
    figures(recs, res["E2_revisions"], res["E3_power"], r6)
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    print(json.dumps({k: v for k, v in res.items() if k != "E4_gdp"}, indent=1)[:6000])
    print(json.dumps(res["E4_gdp"], indent=1))


if __name__ == "__main__":
    main()
