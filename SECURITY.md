# Security

## Reporting a problem

If you find a way to make the verifier accept a forged archive, make the website run code it shouldn't, or anything else that weakens what Kanakku claims, please report it privately:

- GitHub: **Security → Report a vulnerability** on this repository (private advisory), or
- email shyamvasansathiskumar@gmail.com with "Kanakku security" in the subject.

Please don't open a public issue for it. I'll acknowledge within 7 days and say what I'll do about it. There is no bug bounty; reports are credited in the changelog if you'd like.

## What counts

In scope:
- `kanakku/` (the archive, verifier, diff and estimate code) and `docs/ledger.js` (its browser port): any input that makes `verify` report a tampered archive as intact, or that crashes it in a way that hides a problem.
- `docs/` (the website): script injection, loading anything from another origin, leaking anything about a visitor, or being made to show a different archive than the one in this repository without the page saying so.
- `.github/workflows/`: anything that lets someone without write access change the archive.

Out of scope: the accuracy of the RBI's or MoSPI's own figures; denial of service against GitHub; the limits listed below, which are known and stated.

## Known limits (by design, stated on the site)

- The archive proves what Kanakku fetched and when, not what the publisher showed anyone else.
- The chain alone cannot detect a cut-off tail or a full rewrite by whoever controls the file. Only a head published somewhere else can. The heads file and the git history are the witnesses here; the head is also printed in the paper and in a dated public post.
- The website checks the archive it was served. If this repository itself were compromised, the page would faithfully verify the compromised copy. Compare the head with an independent copy (the paper, a post, your own clone).
- GitHub Pages can't send HTTP security headers. The site uses a meta Content-Security-Policy, Subresource Integrity on every script and stylesheet, a no-referrer policy and a script that refuses to run inside a frame. `frame-ancestors`, `Permissions-Policy` and HSTS preload can't be set from a meta tag.

See [notes/site-security.md](notes/site-security.md) for the full list of threats and the control for each.
