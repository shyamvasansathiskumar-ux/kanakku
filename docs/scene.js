// Kanakku's world: the archive itself, as a ledger of 59 cards, one per weekly RBI release,
// each as tall as that week's total reserves. Brass links join each card to the one before it,
// a pulse of light runs along the chain the way the verifier walks it, and a seal hangs over
// the newest card: the published head. In the tamper chapter one card is pulled out and every
// link after it turns red.
import { createWorld, THREE, smooth } from "./world.js";

const ACC = new THREE.Color("#1f4e79");
const INK = new THREE.Color("#15120e");
const PAPER = new THREE.Color("#f4ede0");
const FLAG = new THREE.Color("#b3401f");
const BRASS = new THREE.Color("#c49a3a");

// Keyframes per stage: [x, y, z, scale, yaw, tamper, fade, seal, camX, camY, camZ]
const K = [
  /* 0 hero     */ [2.6, -0.2, -1.2, 0.95, -0.62, 0, 0, 1, 0, 0.9, 10.2],
  /* 1 problem  */ [-2.6, -0.3, -2.0, 0.8, -0.35, 0, 1, 0, 0, 1.0, 10.4],
  /* 2 chain    */ [2.4, 0.1, -2.4, 0.78, -0.9, 0, 0, 1, 0, 1.1, 10.4],
  /* 3 lab      */ [0.0, -0.1, -2.0, 0.9, -0.2, 1, 0, 1, 0, 0.9, 10.4],
  /* 4 rounding */ [-2.9, -0.2, -2.4, 0.72, -0.5, 0, 0, 1, 0, 1.0, 10.6],
  /* 5 year     */ [0.0, 1.0, -3.6, 0.95, 0.0, 0, 0, 1, 0, 1.4, 10.8],
  /* 6 gdp      */ [-4.4, 0.6, -4.4, 0.55, -0.7, 0, 0, 0.6, 0, 1.0, 10.6],
  /* 7 verify   */ [-3.6, -1.3, -2.8, 0.62, -0.95, 0, 0, 1.4, 0, 1.0, 10.4],
  /* 8 limits   */ [-3.2, 0.4, -3.0, 0.6, -0.4, 0, 0, 1, 0, 1.2, 10.8],
  /* end        */ [2.6, 0.0, -2.0, 0.9, -0.6, 0, 0, 1, 0, 0.9, 10.2],
];
const MOBILE = (k, i) => [0.4, 3.9, -4.2, k[3] * 0.45, k[4], k[5], k[6], Math.min(1, k[7]), 0, 0.6, 12.5];

function frame(stage, mobile) {
  const i = Math.max(0, Math.min(K.length - 2, Math.floor(stage)));
  const f = smooth(0.15, 0.85, stage - i);
  const a = mobile ? MOBILE(K[i], i) : K[i], b = mobile ? MOBILE(K[i + 1], i + 1) : K[i + 1];
  return a.map((v, j) => v + (b[j] - v) * f);
}

async function weeklyTotals() {
  try {
    const res = await fetch("archive.jsonl", { cache: "force-cache", credentials: "omit" });
    const text = await res.text();
    const out = [];
    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      const r = JSON.parse(line);
      const row = r.table && r.table.rows && r.table.rows.find((x) => x.item === "1");
      if (row && Number.isFinite(row.lvl_usd)) out.push(row.lvl_usd);
    }
    if (out.length > 1) return out;
  } catch (e) { /* fall through to a flat ledger */ }
  return new Array(59).fill(1);
}

createWorld(document.getElementById("world"), async ({ scene, camera }) => {
  const vals = await weeklyTotals();
  const N = vals.length;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const H = vals.map((v) => 0.7 + 1.9 * (hi > lo ? (v - lo) / (hi - lo) : 0.5));
  const GAP = 0.17, W = (N - 1) * GAP;
  const BROKEN = 20;

  const ledger = new THREE.Group();
  scene.add(ledger);
  const cardMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.62, metalness: 0 });
  const cards = new THREE.InstancedMesh(new THREE.BoxGeometry(0.1, 1, 0.82), cardMat, N);
  cards.castShadow = true; cards.receiveShadow = true;
  ledger.add(cards);

  // the links: one brass ring between each card and the next
  const linkMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3, metalness: 0.85 });
  const links = new THREE.InstancedMesh(new THREE.TorusGeometry(0.055, 0.016, 10, 24), linkMat, N - 1);
  links.castShadow = true;
  ledger.add(links);

  // the spine along the tops: the record of what each week said
  const spineGeo = new THREE.BufferGeometry();
  const spinePos = new Float32Array(N * 3);
  spineGeo.setAttribute("position", new THREE.BufferAttribute(spinePos, 3));
  const spine = new THREE.Line(spineGeo, new THREE.LineBasicMaterial({ color: ACC, transparent: true, opacity: 0.55 }));
  ledger.add(spine);

  // the seal: the published head, hanging over the newest card
  const seal = new THREE.Group();
  const brass = new THREE.MeshPhysicalMaterial({ color: BRASS, roughness: 0.25, metalness: 0.9, clearcoat: 0.5 });
  const disc = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.07, 48), brass);
  disc.rotation.x = Math.PI / 2;
  const rim = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.025, 10, 64), brass);
  const tick = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.2, 0.09), new THREE.MeshStandardMaterial({ color: INK, roughness: 0.5 }));
  tick.position.set(-0.04, -0.02, 0.02); tick.rotation.z = 0.7;
  const tick2 = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.12, 0.09), tick.material);
  tick2.position.set(-0.13, -0.06, 0.02); tick2.rotation.z = -0.75;
  [disc, rim, tick, tick2].forEach((m) => { m.castShadow = true; seal.add(m); });
  scene.add(seal);

  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s3 = new THREE.Vector3(), v3 = new THREE.Vector3();
  const yAxis = new THREE.Vector3(0, 1, 0), xAxis = new THREE.Vector3(1, 0, 0), top = new THREE.Vector3();
  const col = new THREE.Color(), look = new THREE.Vector3();

  scene.userData.logo = [ledger, seal];   // shown small and centred while the page loads

  return (st) => {
    const [x, y, z, sc, yaw, tamper, fade, sealOn, cx, cy, cz] = frame(st.stage, st.mobile);
    const t = st.t;
    const pulse = (t * 9) % (N + 12);                 // the verifier walking the chain
    const pull = smooth(0, 1, tamper) * (0.6 + 0.4 * Math.sin(t * 1.6));

    ledger.position.set(x, y, z);
    ledger.scale.setScalar(sc);
    ledger.rotation.set(0, yaw + st.px * 0.12, 0);

    for (let i = 0; i < N; i++) {
      const px = i * GAP - W / 2;
      const h = H[i];
      let lift = 0, out = 0, tilt = 0;
      if (i === BROKEN) { out = pull * 0.55; tilt = pull * 0.45; lift = pull * 0.12; }
      // the problem chapter: the newest weeks keep being overwritten and vanish
      const gone = fade > 0.01 && i > N - 8 ? fade * (0.5 + 0.5 * Math.sin(t * 2.2 + i)) : 0;
      v3.set(px, h / 2 - 1.6 + lift, out);
      q.setFromAxisAngle(xAxis, tilt);
      s3.set(1, Math.max(0.001, h * (1 - gone)), 1);
      m4.compose(v3, q, s3);
      cards.setMatrixAt(i, m4);
      const hot = Math.max(0, 1 - Math.abs(i - pulse) / 2.2);
      col.copy(PAPER).lerp(ACC, hot * 0.75);
      if (i === BROKEN && pull > 0.05) col.lerp(FLAG, pull);
      cards.setColorAt(i, col);
      spinePos.set([px, h - 1.6 + lift, out + 0.41], i * 3);
      if (i < N - 1) {
        v3.set(px + GAP / 2, Math.min(h, H[i + 1]) * 0.5 - 1.6, 0.0);
        q.setFromAxisAngle(yAxis, Math.PI / 2);
        s3.setScalar(1);
        m4.compose(v3, q, s3);
        links.setMatrixAt(i, m4);
        const after = i >= BROKEN - 1 && pull > 0.05;
        links.setColorAt(i, col.copy(BRASS).lerp(FLAG, after ? pull : 0).lerp(ACC, Math.max(0, 1 - Math.abs(i + 0.5 - pulse) / 1.6) * 0.6));
      }
    }
    cards.instanceMatrix.needsUpdate = true; cards.instanceColor.needsUpdate = true;
    links.instanceMatrix.needsUpdate = true; links.instanceColor.needsUpdate = true;
    spineGeo.attributes.position.needsUpdate = true;

    // the seal hangs over the newest card and turns slowly
    ledger.updateMatrixWorld();
    top.set((N - 1) * GAP - W / 2, H[N - 1] - 1.6 + 0.75, 0).applyMatrix4(ledger.matrixWorld);
    seal.position.copy(top).add(v3.set(0, Math.sin(t * 1.3) * 0.06, 0));
    seal.scale.setScalar(Math.max(0.001, sc * (0.6 + 0.25 * sealOn)));
    seal.rotation.set(0, Math.sin(t * 0.7) * 0.6 + yaw, 0);
    brass.emissive = brass.emissive || new THREE.Color();
    const glow = Math.max(0, sealOn - 1) * 2.5;
    brass.emissive.setRGB(0.22 * glow, 0.15 * glow, 0.03 * glow);

    camera.position.set(cx + st.px * 0.35, cy - st.py * 0.2, cz);
    look.set(cx * 0.6, 0.15 + (cy - 0.9) * 0.2, -2);
    camera.lookAt(look);
  };
}, { bg: "#e8e1d3", fog: [10, 42] });
