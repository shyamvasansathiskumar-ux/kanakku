// Kanakku's page. Loads the real archive from this site, verifies it with ledger.js, and runs
// the tamper lab, the rounding check, the year chart and the GDP table on it.
// Rules: data never becomes HTML (textContent only), nothing is fetched from another origin,
// and nothing the visitor does is stored or sent anywhere.
(() => {
  "use strict";
  const L = window.Ledger;
  const $ = (id) => document.getElementById(id);
  const SVGNS = "http://www.w3.org/2000/svg";
  function el(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k === "on") for (const [ev, fn] of Object.entries(v)) e.addEventListener(ev, fn);
      else e.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) e.append(typeof k === "string" ? document.createTextNode(k) : k);
    return e;
  }
  function svg(tag, attrs = {}) { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v)); return e; }
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const day = (iso) => { const [y, m, d] = String(iso).split("-"); return MONTHS[+m - 1] ? `${+d} ${MONTHS[+m - 1]} ${y}` : String(iso); };
  const IN = (n) => Number(n).toLocaleString("en-IN");
  const short = (h) => h.slice(0, 10) + "…" + h.slice(-6);
  const deepCopy = (x) => JSON.parse(JSON.stringify(x));
  const NAMES = { "1": "Total reserves", "1.1": "Foreign currency assets", "1.2": "Gold", "1.3": "SDRs", "1.4": "Reserve position in the IMF" };

  async function getText(path, limit) {
    const res = await fetch(path, { cache: "no-cache", credentials: "omit", referrerPolicy: "no-referrer" });
    if (!res.ok) throw new Error(path + " " + res.status);
    const t = await res.text();
    if (t.length > limit) throw new Error(path + " is larger than expected");
    return t;
  }

  // ------------------------------------------------------------------ hero
  async function hero(recs, heads) {
    const r = await L.verify(recs, heads);
    $("hcN").textContent = String(r.records);
    $("hcHead").textContent = short(r.head.hash);
    $("hcHead").title = r.head.hash;
    $("termHead").textContent = r.head.hash;
    const ok = r.ok && heads.length > 0 && heads[heads.length - 1].hash === r.head.hash;
    $("hcOk").textContent = ok ? "intact · matches the published head" : "does not verify";
    $("hcOk").className = "pill " + (ok ? "ok" : "bad");
    const n = recs.length;
    if (n >= 2) {
      $("h57").textContent = short(await L.recordHash(recs[n - 2]));
      $("p58").textContent = short(recs[n - 1].prev);
      $("h58").textContent = short(await L.recordHash(recs[n - 1]));
    }
    $("wHead").textContent = heads.length ? short(heads[heads.length - 1].hash) : "none";
    $("wOk").textContent = ok ? "yes" : "no";
    return r;
  }

  // -------------------------------------------------------------- tamper lab
  const ATTACKS = [
    { k: "edit", t: "Change one figure", d: "Add ₹1 crore to that week's total. No hashes touched." },
    { k: "meta", t: "Change its date", d: "Say the week was published a day later." },
    { k: "rehash1", t: "Change it and re-seal it", d: "Edit the figure, then recompute that record's own hashes." },
    { k: "delete", t: "Delete the week", d: "Remove the record entirely." },
    { k: "swap", t: "Swap two weeks", d: "Put the week after it first." },
    { k: "truncate", t: "Cut the archive short", d: "Throw away every week after this one." },
    { k: "rewrite", t: "Rewrite from here", d: "Edit the figure, then re-seal every record after it. The keeper's attack." },
  ];
  async function forge(recs, k, i) {
    const r = deepCopy(recs);
    const n = r.length;
    const bump = (rec) => { rec.table.rows[0].lvl_inr += 1; };
    if (k === "edit") { bump(r[i]); return r; }
    if (k === "meta") { r[i].published = r[i].published.slice(0, 8) + String(+r[i].published.slice(8) + 1).padStart(2, "0"); return r; }
    if (k === "rehash1") { bump(r[i]); r[i].table_sha256 = await L.digest(r[i].table); r[i].hash = await L.recordHash(r[i]); return r; }
    if (k === "delete") { r.splice(Math.min(i, n - 2), 1); return r; }
    if (k === "swap") { const j = Math.min(i, n - 2); [r[j], r[j + 1]] = [r[j + 1], r[j]]; return r; }
    if (k === "truncate") return r.slice(0, Math.min(i, n - 2) + 1);
    if (k === "rewrite") {
      const out = r.slice(0, i);
      let prev = i ? out[i - 1] : null;
      for (let j = i; j < n; j++) {
        const t = r[j].table;
        if (j === i) bump({ table: t });
        prev = await L.newRecord(prev, { ...r[j], table: t });
        out.push(prev);
      }
      return out;
    }
    return r;
  }
  function lab(recs, heads) {
    let attack = "edit", busy = false;
    const at = $("labAt");
    at.max = String(recs.length - 1);
    $("labPick").replaceChildren(...ATTACKS.map((a) => el("button", {
      type: "button", class: "chip" + (a.k === attack ? " on" : ""), "data-k": a.k, "aria-pressed": String(a.k === attack), text: a.t,
      on: { click: () => { attack = a.k; [...$("labPick").children].forEach((b) => { const on = b.dataset.k === attack; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); }); run(); } },
    })));
    const strip = $("labStrip");
    strip.replaceChildren(...recs.map(() => el("i")));
    async function run() {
      if (busy) return;
      busy = true;
      const i = Number(at.value);
      const rec = recs[i];
      $("labAtTxt").textContent = `${day(rec.published)} · seq ${rec.seq}`;
      const a = ATTACKS.find((x) => x.k === attack);
      try {
        const forged = await forge(recs, attack, i);
        const alone = await L.verify(forged, []);
        const witnessed = await L.verify(forged, heads);
        const bad = new Set(witnessed.problems.map((p) => p.seq));
        [...strip.children].forEach((c, j) => { c.className = j >= forged.length && j < recs.length ? "gone" : bad.has(j) ? "bad" : ""; });
        const verdict = (r) => (r.ok ? ["missed", "Passes. The forgery is invisible."] : ["caught", r.problems.map((p) => `${p.kind} at seq ${p.seq}`).slice(0, 3).join(" · ") + (r.problems.length > 3 ? ` · +${r.problems.length - 3} more` : "")]);
        const [s1, t1] = verdict(alone), [s2, t2] = verdict(witnessed);
        $("labOut").replaceChildren(
          el("p", { class: "lab-what" }, el("b", { text: a.t + ". " }), a.d),
          el("div", { class: "lab-res" },
            el("div", { class: "res " + s1 }, el("span", { class: "label bare", text: "Chain alone" }), el("b", { text: s1 === "caught" ? "Caught" : "Missed" }), el("small", { text: t1 })),
            el("div", { class: "res " + s2 }, el("span", { class: "label bare", text: "Against the published head" }), el("b", { text: s2 === "caught" ? "Caught" : "Missed" }), el("small", { text: t2 }))),
          s1 === "missed" && s2 === "caught" ? el("p", { class: "fine on-ink", text: "This is why the head is published somewhere else: the chain on its own can't see this attack." }) : null);
      } catch (e) {
        $("labOut").replaceChildren(el("p", { text: "This attack couldn't be run in this browser." }));
      } finally { busy = false; }
    }
    let tmr;
    at.addEventListener("input", () => { clearTimeout(tmr); tmr = setTimeout(run, 120); });
    run();
  }

  // --------------------------------------------------------------- rounding
  function rounding(recs) {
    const bn = $("bn");
    const bnote = () => {
      const n = Number(bn.value), b = L.bound(n);
      $("bOut").textContent = String(b);
      $("bNote").textContent = n === 3 ? "Level − change − last week's level: 3 printed figures, so rounding explains at most 1." :
        n === 5 ? "Total − four components: 5 printed figures, so rounding explains at most 2." :
        `${n} printed figures: rounding explains at most ${b}.`;
    };
    bn.addEventListener("input", bnote); bnote();

    const all = (rs) => [...L.implied(rs, "lvl_inr", "wk_inr"), ...L.implied(rs, "lvl_usd", "wk_usd")];
    const checks = all(recs);
    // A real restatement, planted in a copy: week 20's gold, re-published 2 crore higher in its own release.
    const tampered = deepCopy(recs);
    tampered[20].table.rows.find((r) => r.item === "1.2").lvl_inr += 2;
    const plantedChecks = all(tampered);
    let mode = "naive", planted = false;
    function draw() {
      const data = planted ? plantedChecks : checks;
      const counts = new Map();
      for (const c of data) counts.set(c.delta, (counts.get(c.delta) || 0) + 1);
      const keys = [...counts.keys()].sort((a, b) => a - b);
      const max = Math.max(...counts.values());
      const tol = L.bound(3);
      $("hist").replaceChildren(...keys.map((k) => {
        const n = counts.get(k);
        const flagged = mode === "naive" ? k !== 0 : Math.abs(k) > tol;
        const bar = el("i");
        bar.style.height = Math.max(4, (n / max) * 100) + "%";
        return el("div", { class: "bar" + (flagged ? " flag" : "") }, el("span", { class: "c", text: IN(n) }), bar, el("span", { class: "k", text: (k > 0 ? "+" : "") + k }));
      }));
      const flagged = data.filter((c) => (mode === "naive" ? c.delta !== 0 : Math.abs(c.delta) > tol)).length;
      $("verdict").textContent = mode === "naive"
        ? `A plain diff flags ${IN(flagged)} of ${IN(data.length)} checks as revisions. ${planted ? "Two of them are real. Can you tell which?" : "Every one of them is rounding."}`
        : `With the rounding bound: ${flagged} flagged. ${planted ? `Both are the change you planted in ${day(recs[20].table.rows[0].as_on)}'s gold figure: it breaks the check on either side of that week.` : "The RBI's weekly table was never restated."}`;
    }
    const chips = [...document.querySelectorAll("#rounding [data-mode]")];
    chips.forEach((b) => b.addEventListener("click", () => {
      mode = b.dataset.mode;
      chips.forEach((o) => { const on = o === b; o.classList.toggle("on", on); o.setAttribute("aria-pressed", String(on)); });
      draw();
    }));
    const plant = el("button", { type: "button", class: "btn ghost sm", text: "Plant a 2-unit restatement",
      on: { click: () => { planted = !planted; plant.textContent = planted ? "Remove it" : "Plant a 2-unit restatement"; draw(); } } });
    $("verdict").after(plant);
    draw();
  }

  // ------------------------------------------------------------- the year
  function year(recs) {
    const rows = recs.map((r) => new Map(r.table.rows.map((x) => [x.item, x])));
    let item = "1", cur = "usd", sel = recs.length - 1;
    $("ySeries").replaceChildren(...Object.entries(NAMES).map(([k, v]) => el("button", {
      type: "button", class: "chip" + (k === item ? " on" : ""), "data-k": k, "aria-pressed": String(k === item), text: v.replace("Reserve position in the IMF", "IMF position").replace("Foreign currency assets", "Currency assets"),
      on: { click: (e) => { item = k; [...$("ySeries").children].forEach((b) => { const on = b === e.currentTarget; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); }); draw(); } },
    })));
    document.querySelectorAll("#year [data-cur]").forEach((b) => b.addEventListener("click", () => {
      cur = b.dataset.cur;
      document.querySelectorAll("#year [data-cur]").forEach((o) => { const on = o === b; o.classList.toggle("on", on); o.setAttribute("aria-pressed", String(on)); });
      draw();
    }));
    const W = 1000, H = 300, P = { l: 70, r: 16, t: 18, b: 34 };
    const chart = $("chart");
    const slider = el("input", { type: "range", min: "0", max: String(recs.length - 1), value: String(sel), class: "ysl", "aria-label": "Week" });
    chart.after(slider);
    slider.addEventListener("input", () => { sel = Number(slider.value); draw(); });

    function draw() {
      const vals = rows.map((m) => m.get(item)["lvl_" + cur]);
      const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.08 || 1;
      const y0 = lo - pad, y1 = hi + pad;
      const X = (i) => P.l + (i / (vals.length - 1)) * (W - P.l - P.r);
      const Y = (v) => P.t + (1 - (v - y0) / (y1 - y0)) * (H - P.t - P.b);
      const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${NAMES[item]} by week` });
      for (let g = 0; g <= 4; g++) {
        const v = y0 + ((y1 - y0) * g) / 4;
        s.append(svg("line", { x1: P.l, x2: W - P.r, y1: Y(v), y2: Y(v), class: "grid" }));
        const t = svg("text", { x: P.l - 10, y: Y(v) + 4, class: "ax", "text-anchor": "end" }); t.textContent = IN(Math.round(v)); s.append(t);
      }
      [0, Math.floor((vals.length - 1) / 2), vals.length - 1].forEach((i) => {
        const t = svg("text", { x: X(i), y: H - 10, class: "ax", "text-anchor": i === 0 ? "start" : i === vals.length - 1 ? "end" : "middle" });
        t.textContent = day(recs[i].table.rows[0].as_on); s.append(t);
      });
      const area = svg("path", { class: "area", d: `M${X(0)},${Y(vals[0])} ` + vals.map((v, i) => `L${X(i)},${Y(v)}`).join(" ") + ` L${X(vals.length - 1)},${H - P.b} L${X(0)},${H - P.b} Z` });
      const line = svg("path", { class: "line", d: vals.map((v, i) => `${i ? "L" : "M"}${X(i)},${Y(v)}`).join(" ") });
      s.append(area, line);
      vals.forEach((v, i) => s.append(svg("circle", { cx: X(i), cy: Y(v), r: i === sel ? 6 : 2.6, class: i === sel ? "dot sel" : "dot" })));
      s.append(svg("line", { x1: X(sel), x2: X(sel), y1: P.t, y2: H - P.b, class: "cursor" }));
      s.addEventListener("pointermove", (e) => {
        const b = s.getBoundingClientRect();
        const x = ((e.clientX - b.left) / b.width) * W;
        const i = Math.round(((x - P.l) / (W - P.l - P.r)) * (vals.length - 1));
        if (i >= 0 && i < vals.length && i !== sel) { sel = i; slider.value = String(i); draw(); }
      });
      chart.replaceChildren(s);
      detail(rows, item, cur, sel);
    }
    function detail() {
      const r = rows[sel].get(item), as = r.as_on, unit = cur === "usd" ? "US$ mn" : "₹ cr";
      const next = rows[sel + 1] ? rows[sel + 1].get(item) : null;
      const imp = next ? next["lvl_" + cur] - next["wk_" + cur] : null;
      const tot = rows[sel].get("1");
      const rate = (tot.lvl_inr * 1e7) / (tot.lvl_usd * 1e6);
      const pairs = [
        ["Week ending", day(as)],
        ["Released", day(recs[sel].published)],
        ["First published", `${IN(r["lvl_" + cur])} ${unit}`],
        ["Implied by the next release", imp == null ? "– (latest release)" : `${IN(imp)} ${unit}`],
        ["Difference", imp == null ? "–" : (imp - r["lvl_" + cur] === 0 ? "none" : `${imp - r["lvl_" + cur] > 0 ? "+" : ""}${imp - r["lvl_" + cur]} (rounding)`)],
        ["Change over the week", `${r["wk_" + cur] > 0 ? "+" : ""}${IN(r["wk_" + cur])} ${unit}`],
        ["₹ per US$ implied by the table", rate.toFixed(2)],
        ["Record", `seq ${recs[sel].seq} · ${short(recs[sel].hash)}`],
      ];
      $("week").replaceChildren(...pairs.map(([k, v]) => el("div", {}, el("dt", { text: k }), el("dd", { text: v }))));
    }
    draw();
  }

  // ---------------------------------------------------------------- gdp
  function gdp(g) {
    const vs = g.vintages;
    const periods = [];
    vs.forEach((v) => Object.keys(v.values).forEach((p) => { if (!periods.includes(p)) periods.push(p); }));
    const rank = (p) => { const [fy, q] = p.split(" "); return fy + (q === "FY" ? "9" : q.slice(1)); };   // Q1..Q4, then the year
    periods.sort((a, b) => (rank(a) < rank(b) ? -1 : 1));
    const head = el("tr", {}, el("th", { text: "Release" }), el("th", { text: "Base" }), ...periods.map((p) => el("th", { text: p.replace("2025-26 ", "").replace("FY", "2025–26 year").replace("2026-27 Q1", "2026–27 Q1") })));
    let lastBase = null;
    const body = vs.map((v) => {
      const moved = lastBase && lastBase !== v.base; lastBase = v.base;
      return el("tr", { class: moved ? "rebase" : "" }, el("td", { text: day(v.released) }), el("td", { class: "mono", text: v.base }),
        ...periods.map((p) => el("td", { class: v.values[p] ? "v" : "", text: v.values[p] ? v.values[p].value : "" })));
    });
    $("gdpTable").replaceChildren(el("thead", {}, head), el("tbody", {}, ...body));
    $("gdpNote").textContent = "Real GDP growth, % year on year, as stated at each release. Blank: not recorded, not withdrawn. The line marks the move to the 2022–23 base. The Q2 restatement of Feb 2026 and the June 2026 vintage are from news reports of the official releases.";
  }

  function fail(msg) {
    $("hcOk").textContent = msg; $("hcOk").className = "pill bad";
    $("labOut").replaceChildren(el("p", { text: "The archive didn't load, so there's nothing to tamper with. Refresh to try again." }));
  }

  Promise.all([getText("archive.jsonl", 2_000_000), getText("heads.jsonl", 200_000), getText("gdp.json", 200_000)])
    .then(async ([a, h, g]) => {
      const recs = L.parseLines(a), heads = L.parseLines(h), gj = JSON.parse(g);
      window.KANAKKU = { recs };
      document.dispatchEvent(new CustomEvent("kanakku:data", { detail: { recs } }));
      await hero(recs, heads);
      lab(recs, heads); rounding(recs); year(recs); gdp(gj);
      if (window.ScrollTrigger) ScrollTrigger.refresh();
    })
    .catch(() => fail("couldn't load the archive"));
})();
