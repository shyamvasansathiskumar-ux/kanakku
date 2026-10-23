# Threat model

## What Kanakku protects
The record of **what a publisher showed, as Kanakku saw it, and when**.

## Who might want to change that record, and how

| Adversary | Can do | Caught by |
|---|---|---|
| Someone who edits one archived snapshot | change a value or a date | record hash (100% in tests) |
| Someone who edits and re-hashes one snapshot | rewrite one record consistently | the next record's `prev` link; for the newest record, the witnessed head |
| Someone who deletes, reorders or inserts snapshots | change the sequence | `seq` and `prev` checks |
| The archive keeper, rewriting history end to end | recompute every hash | **only** a head published outside their control |
| The archive keeper, dropping the newest snapshots | cut the tail | **only** a witnessed head newer than the cut |
| The publisher, silently editing an old page | change what an old URL shows | the archive keeps what was fetched; implied-level checks flag a restatement in the next release |

## Out of scope
- Proving what the publisher served to *other* people (needs publisher signatures or many independent archivers).
- A compromised fetcher that records false data from the start (mitigated by independent re-collection and the identity/implied checks, not prevented).
- Availability: the archive can be deleted; keep copies (git remotes, Zenodo).

## Witnessing in this repository
The heads file and the git history both record heads. For stronger witnessing, post the head hash somewhere public and timestamped after each update (a public post, an email to a mailing list, or an RFC 3161 timestamp).
