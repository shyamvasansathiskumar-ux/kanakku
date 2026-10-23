# Website and repository: threats and controls

Kanakku's site is static (GitHub Pages): no server code, no accounts, no forms, no cookies, nothing stored about visitors. That removes most of the usual attack surface. What's left, and what closes each item:

| # | Threat | Control | Checked by |
|---|---|---|---|
| 1 | A script injected through data (a crafted record, an odd GDP label) runs in the page | Data is only ever set with `textContent` or SVG attributes; no `innerHTML` with data. CSP `script-src 'self'` with no `unsafe-inline` or `unsafe-eval`, so even an injected `<script>` or `onclick=` wouldn't run | `tests/test_site.py`: no inline scripts or handlers; no `innerHTML` in app.js/ledger.js; browser run reports zero CSP violations |
| 2 | The page loads code or data from somewhere else (a CDN outage, a tampered library, tracking) | Every file is on this site; CSP `default-src 'none'` and `connect-src 'self'`; fonts self-hosted | Test: no `http(s)://` in `src`/`href` of scripts, styles, fonts or images; CSP string is exactly as expected |
| 3 | A published script or stylesheet is altered after the page was written (host, cache, proxy) | Subresource Integrity (`sha384`) on every script and stylesheet tag | `tools/sri.py --check` in the tests: any edit without re-stamping fails |
| 4 | Someone frames the page to trick clicks or pass it off as theirs | `boot.js` hides the page inside any frame and offers a link out. (`frame-ancestors` can't be set by a meta tag on Pages) | Test: framed page shows only the link |
| 5 | The visitor's address leaks to other sites through links | `<meta name="referrer" content="no-referrer">`; every outbound link has `rel="noopener noreferrer"` | Test: every `target="_blank"` link carries both |
| 6 | Mixed content or downgrade | CSP `upgrade-insecure-requests`; GitHub Pages enforces HTTPS | CSP check |
| 7 | A huge or malformed data file freezes the page | Size caps on every fetch (2 MB archive, 200 kB others); strict JSON Lines parsing, one object per line; integers only in hashing | Test: parser rejects arrays, non-objects and oversized input |
| 8 | The page says "intact" for an archive that isn't | `ledger.js` is a line-for-line port of the Python verifier, and the tests run both on the same archive and every attack class and require identical answers | `test_site.py`: JS and Python agree on the head and on all 7 attacks |
| 9 | The page's copy of the archive drifts from the repository's | The page serves `docs/archive.jsonl`; the tests require it to be byte-identical to `archive/rbi_fx.jsonl` (and the heads file) | Test |
| 10 | The whole repository is compromised and both archive and heads are replaced together | Not preventable by the page. Detectable by comparing the head with copies outside the repository: the paper, a dated public post, anyone's clone. Stated on the site and in SECURITY.md | – |
| 11 | History rewritten with a force-push, which would erase the git-history witness | Branch ruleset on `main`: block force pushes and deletion | Repository settings |
| 12 | The scheduled job is abused (script injection through its input, a compromised action) | Input passed as an environment variable and validated as a date; actions pinned to full commit SHAs; `permissions: contents: write` only; job runs only by hand until RBI replies | Workflow file review |
| 13 | A secret is committed | Nothing in the project needs a secret; GitHub secret scanning and push protection on | Repository settings; test greps for key-like strings |
| 14 | Vendored libraries carry known vulnerabilities | Exact versions listed in THIRD-PARTY-NOTICES.md; none of them process untrusted input here (they animate static page text and draw the scene) | Review on each version bump |
| 15 | Licence problems with vendored files | Licences listed; fonts OFL, three.js and Lenis MIT, GSAP's no-charge standard licence | THIRD-PARTY-NOTICES.md |
| 16 | Personal data | None collected. No analytics, no cookies, no storage, no forms | Test: no `localStorage`, `sessionStorage`, `document.cookie` in site code |
| 17 | The reader is misled by the visual | Every number on the page is computed from the archive in the browser or stated with its source; limits are on the page | Browser test reads the numbers back |

## Settings to keep switched on (GitHub)

- Settings → Rules → Rulesets: on `main`, **Block force pushes** and **Restrict deletions**.
- Settings → Code security: **Private vulnerability reporting**, **Secret scanning**, **Push protection**.
- Settings → Pages: source `main` / `docs`, **Enforce HTTPS**.
- Account: two-factor authentication (required by GitHub from 24 Nov 2026).
