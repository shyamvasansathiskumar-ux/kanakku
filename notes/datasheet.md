# Datasheet: Kanakku RBI forex-reserves vintages (v1, 23 Oct 2026)

Following Gebru et al., *Datasheets for Datasets* (CACM 2021).

## Motivation
- **Why was it created?** To test whether a public weekly series is ever restated after first release, and to measure how well a rounding-aware detector separates real restatements from rounding.
- **Who created it?** Shyam Kumar, Dept. of CSE, Rajalakshmi Engineering College, Chennai.
- **Funding.** None.

## Composition
- **Instances.** 59 weekly releases × 5 rows (Total Reserves; Foreign Currency Assets; Gold; SDRs; Reserve Position in the IMF) = 295 rows. Each row has 8 integers: level and change over week, since end-March and over the year, each in ₹ crore and US$ million.
- **Period.** Releases 5 Sep 2025 – 16 Oct 2026 (reference weeks 29 Aug 2025 – 9 Oct 2026). Complete: no week missing.
- **Identifiers.** `release_date`, `wssview_id` (RBI page id; one release came from the WSS extract page, id 63777), `as_on`, `endmarch_label`, `row`.
- **Personal data.** None. Aggregate national statistics only.
- **Errors and noise.** Each figure is rounded independently by the publisher; totals may differ from sums by up to 2 units (RBI footnote: "Difference, if any, is due to rounding off").

## Collection
- **How.** Each weekly page `rbi.org.in/Scripts/WSSView.aspx?Id=…` was read on 23 Oct 2026 and the table transcribed to CSV. Release-to-id mapping was found from RBI's weekly listing pages; ids advance by 15 per week, and every page's own date line was checked against the requested week.
- **Checks on transcription.** (1) Every row's total equals the sum of components within the rounding bound in all 118 checks; (2) every level matches the next week's level minus change within 1 unit in all 580 checks; (3) 70 year-lag checks also within 1 unit. A transcription error of 2 or more units in any level or week-change figure would have failed at least one of these checks. End-March and year columns are checked less tightly: by the stable implied end-March base (two adjacent values per year and currency, i.e. rounding) and by the 70 year-lag checks.
- **Rate.** At most 3 requests at a time, with pauses; well under one request per second overall.
- **Vintage caveat.** Pages were read on 23 Oct 2026, so each is the page *as it stood that day*. If RBI had silently edited an old page, this dataset would contain the edited version. The implied-level checks are what guard against that: an edit to one page without matching edits to the next would show up.

## Uses
- Reproducing the paper; testing revision detectors; teaching real-time data concepts.
- **Not for** financial decisions. RBI: "In case of doubt, however please check the print versions."

## Distribution and maintenance
- Distributed in the Kanakku repository (`data/raw/wss_fx.csv`) and as a hash-chained archive (`archive/rbi_fx.jsonl`; head `fb8ce7ec…3335b5`).
- Figures belong to the Reserve Bank of India and are reproduced with acknowledgement for research. Ongoing collection is paused pending RBI's reply to a permission request.
- Maintainer: Shyam Kumar. Errata via GitHub issues.

---

# Datasheet: GDP growth vintages (case study)

Five releases (29 Aug 2025 – 1 Sep 2026) of India's real GDP growth, y-o-y %. Only figures confirmed in the cited source are recorded; absent periods were not recorded, not withdrawn. Sources: All India Radio News (Aug 2025), Business Standard (Nov 2025), PIB (27 Feb 2026, 1 Sep 2026), Outlook Business (Feb 2026, Q2 restatement), IANS (Jun 2026). Two figures (Q2 2025-26 at 8.4% and the June 2026 vintage) rest on press reports rather than the MoSPI press note and should be checked against MoSPI tables before publication.
