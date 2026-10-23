"""The website, in a real browser (Chromium via Playwright).

  python3 -m http.server -d docs 8813 &
  python3 tests/e2e_site.py                 # KANAKKU_URL to point elsewhere

Checks: no console errors, no Content-Security-Policy violations, nothing missing,
the page's own verification matches the published head, every tamper-lab attack
gives the same verdict the Python verifier gives, the rounding numbers, no sideways
scroll on a phone, and that the page refuses to run inside a frame.
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

URL = os.environ.get("KANAKKU_URL", "http://localhost:8813/")
HEAD = "fb8ce7ecf986ec041cf5ddbd41b48b1f704d0e7275ea2548de53488c8c3335b5"
EXPECT = {"edit": "Caught/Caught", "meta": "Caught/Caught", "rehash1": "Caught/Caught", "delete": "Caught/Caught",
          "swap": "Caught/Caught", "truncate": "Missed/Caught", "rewrite": "Missed/Caught"}
passed = failed = 0


def check(ok, name, extra=""):
    global passed, failed
    if ok:
        passed += 1
        print("  PASS  " + name)
    else:
        failed += 1
        print("  FAIL  " + name + (f"\n        {extra}" if extra else ""))


async def run(b, vw, vh, tag):
    ctx = await b.new_context(viewport={"width": vw, "height": vh})
    pg = await ctx.new_page()
    errors, csp, missing = [], [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: (csp if "Content Security Policy" in m.text or "Refused to" in m.text else errors).append(m.text)
          if m.type == "error" else None)
    pg.on("response", lambda r: missing.append(r.url) if r.status >= 400 else None)
    await pg.goto(URL, wait_until="load")
    await pg.wait_for_function("document.getElementById('termHead').textContent.length === 64", timeout=60000)
    r = await pg.evaluate("""async () => {
      const W = (ms) => new Promise((r) => setTimeout(r, ms)), $ = (id) => document.getElementById(id);
      const out = { head: $('termHead').textContent, ok: $('hcOk').className, lab: {} };
      for (const b of [...document.querySelectorAll('#labPick .chip')]) {
        b.click();
        for (let i = 0; i < 40 && !$('labOut').querySelector('.res'); i++) await W(100);
        await W(1200);
        out.lab[b.dataset.k] = [...document.querySelectorAll('#labOut .res b')].map((x) => x.textContent).join('/');
      }
      out.naive = $('verdict').textContent;
      document.querySelector('#rounding [data-mode=aware]').click(); await W(100);
      out.aware = $('verdict').textContent;
      out.over = document.documentElement.scrollWidth - innerWidth;
      return out;
    }""")
    check(r["head"] == HEAD, f"[{tag}] the page computes the published head", r["head"])
    check("ok" in r["ok"], f"[{tag}] the page reports the chain intact")
    check(r["lab"] == EXPECT, f"[{tag}] every tamper-lab attack gets the Python verifier's verdict", r["lab"])
    check("143 of 580" in r["naive"] and "0 flagged" in r["aware"], f"[{tag}] rounding: 143 naive flags, 0 with the bound", (r["naive"], r["aware"]))
    check(r["over"] == 0, f"[{tag}] no sideways scroll", r["over"])
    check(not csp, f"[{tag}] no Content-Security-Policy violations", csp[:3])
    check(not [e for e in errors if "GL Driver" not in e], f"[{tag}] no page errors", errors[:3])
    check(not missing, f"[{tag}] nothing missing", missing[:3])

    # framed by someone else's page: it must hide itself
    fr = await ctx.new_page()
    await fr.set_content(f'<iframe src="{URL}" width="900" height="600"></iframe>')
    await fr.wait_for_timeout(4000)
    frame = fr.frames[1]
    state = await frame.evaluate("[document.documentElement.classList.contains('framed'), !!document.querySelector('.framed-note'), getComputedStyle(document.querySelector('main')).display]")
    check(state == [True, True, "none"], f"[{tag}] refuses to run inside a frame", state)
    await ctx.close()


async def tampered_script(b):
    """Serve a modified app.js: Subresource Integrity must stop the browser running it."""
    ctx = await b.new_context()
    pg = await ctx.new_page()
    msgs = []
    pg.on("console", lambda m: msgs.append(m.text) if m.type == "error" else None)

    async def evil(route):
        resp = await route.fetch()
        await route.fulfill(response=resp, body=(await resp.text()) + "\ndocument.title = 'pwned';")
    await pg.route("**/app.js", evil)
    await pg.goto(URL, wait_until="load")
    await pg.wait_for_timeout(4000)
    title = await pg.title()
    state = await pg.evaluate("document.getElementById('hcOk').textContent")
    check(title != "pwned" and state == "checking" and any("integrity" in m for m in msgs),
          "a modified script is refused by Subresource Integrity", (title, state, msgs[:1]))
    await ctx.close()


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        await tampered_script(b)
        await run(b, 1440, 900, "desktop")
        await run(b, 390, 844, "phone")
        await b.close()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


asyncio.run(main())
