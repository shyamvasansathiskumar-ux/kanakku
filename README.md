# Kanakku

**கணக்கு** (*kaṇakku*) — Tamil for *account*, *reckoning*.

When a government dashboard updates a number, the old number usually disappears. Kanakku keeps every version of a published figure in an archive that cannot be quietly edited, and says exactly what changed between versions: a new row, a revised value, a withdrawn row, a change of base year, or nothing but rounding.

- **Tamper-evident archive.** Each snapshot is chained to the one before it by SHA-256. Editing, deleting, reordering or inserting any snapshot breaks the chain. The newest hash (the *head*) is published outside the archive after every update, which also catches the two things a chain cannot catch alone: a cut-off tail and a full rewrite.
- **Revision detector.** Compares snapshots and classifies every difference. Where a table prints a level and its change since the last release, it also checks the level implied by the next release against the one first published, so a quiet restatement shows up even when the old page is gone.
- **Rounding-aware.** Every printed figure is rounded on its own. A check that combines *n* printed integers can be off by at most ⌊n/2⌋ units from rounding alone, so Kanakku uses that bound and nothing looser. Anything larger is reported as a revision.
- **Re-checkable estimates.** A derived figure records the hashes of the snapshots and assumptions it used, so anyone can recompute it and get the same digits.

Python 3.10+, standard library only.

**Site:** https://shyamvasansathiskumar-ux.github.io/kanakku/ — the archive verified in your browser, a tamper lab that forges copies and runs the same checks, the rounding bound, and the whole year of data.

## What we found

59 weekly releases of the RBI's foreign exchange reserves table (5 Sep 2025 – 16 Oct 2026), 295 rows, 2,360 figures:

| Check | Pairs | Exact | Off by 1 (rounding) | Revisions |
|---|---|---|---|---|
| Level implied by the next week vs first published, ₹ crore | 290 | 226 | 64 | **0** |
| Same, US$ million | 290 | 211 | 79 | **0** |
| Level implied 52 weeks later (both currencies) | 70 | 51 | 19 | **0** |
| Total vs sum of components (both currencies) | 118 | 80 | 38 | **0** |

A plain diff would have reported 143 "revisions" in the week-to-week check alone; all of them are rounding. With the rounding bound, Kanakku reports none, and in 400 trials per size finds 97% of injected restatements of 2 units (₹20 crore) and 100% from 3 units up, with no false flags.

For GDP, five releases from Aug 2025 to Sep 2026 show a base-year change (2011-12 → 2022-23) and four revisions, including Q1 2025-26 growth going from 7.8% to 6.9%.

Every number above is reproduced by one command (below).

## Use

```sh
python3 -m unittest -q tests.test_kanakku tests.test_site   # 51 tests (the site's JS verifier is checked against Python with Node)
python3 -m http.server -d docs 8813 & python3 tests/e2e_site.py   # 19 browser checks (needs Playwright)
python3 experiments/run_eval.py                     # every number and figure in the paper
python3 -m kanakku verify archive/rbi_fx.jsonl --heads archive/heads.jsonl
python3 -m kanakku diff   archive/rbi_fx.jsonl 57 58
python3 -m kanakku vintages archive/rbi_fx.jsonl rbi.wss.fx_reserves lvl_usd
```

## Layout

```
kanakku/canon.py        canonical JSON + hashing (no floats, sorted rows)
kanakku/chain.py        append-only archive, verify, witnessed heads
kanakku/diff.py         addition / withdrawal / revision / rounding / schema
kanakku/vintage.py      vintage matrix, implied-level checks, identity checks
kanakku/estimate.py     derived figures with input and assumption hashes
kanakku/fetch.py        polite fetcher (robots.txt, rate limit, descriptive UA)
kanakku/sources/        publisher adapters (RBI WSS forex reserves)
docs/ledger.js          the verifier again, in JavaScript, for the website
tools/sri.py            stamps Subresource Integrity hashes onto the site
archive/                the archive and its witnessed head
data/raw/               the evaluation datasets, as collected
experiments/            evaluation script and outputs
notes/                  datasheet, threat model, RBI permission letter
docs/                   the website (GitHub Pages)
```

## Data

`data/raw/wss_fx.csv` holds the RBI Weekly Statistical Supplement table *Foreign Exchange Reserves* for every release from 5 Sep 2025 to 16 Oct 2026, read from `rbi.org.in` on 23 Oct 2026. Source: Reserve Bank of India. Figures are reproduced with acknowledgement for research; RBI states that its website figures should be checked against the print versions in case of doubt. `data/raw/gdp_vintages.json` holds GDP growth figures from MoSPI/PIB releases and press reports, each with its source. See [notes/datasheet.md](notes/datasheet.md).

The scheduled collector is switched off until RBI responds to a request for permission (see [notes/rbi-permission-letter.md](notes/rbi-permission-letter.md)); runs are manual until then.

## Limits

- The archive proves what Kanakku *saw* and when. It cannot prove what the publisher served to anyone else.
- Without a published head, an archive keeper could rewrite the whole file. Publish the head somewhere you do not control (here: the git history and the heads file).
- The rounding bound assumes each figure is rounded to the nearest unit, as the RBI footnote states. A publisher that truncates would need a different bound.
- Five GDP releases are a case study, not a dataset.

## Security

The site loads nothing from anywhere else, runs no inline code, keeps nothing about visitors, and won't run inside another site's frame; every script carries an integrity hash. What it can't do, and how to report a problem: [SECURITY.md](SECURITY.md) and [notes/site-security.md](notes/site-security.md).

## Licence

Code: MIT. Vendored libraries and fonts: see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Data: figures belong to their publishers (Reserve Bank of India; Ministry of Statistics and Programme Implementation), reproduced with attribution.
