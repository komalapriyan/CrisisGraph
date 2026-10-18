// Dotted grouped columns (resources) and dotted ring (severity). Uses DOT/dotColumn from dotchart.js.
const _nice = v => { if (v <= 0) return 1; const e = Math.pow(10, Math.floor(Math.log10(v))), m = v / e; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * e; };

function DotGroups(root) {
  const {P, R, YEL} = DOT, H = 250, BOT = 24, TOP = 16;
  const S = [["stock", "#3b82f6"], ["demand", "#a78bfa"], ["allocated", "#22c55e"], ["shortage", "#ef4444"]];
  root.innerHTML = `<div class="dg-legend">${S.map(([n, c]) => `<span><i style="background:${c}"></i>${n}</span>`).join("")}</div><div class="dc-wrap"><svg tabindex="0" role="img" aria-label="Resource stock, demand, allocated and shortage by category. Use arrow keys."></svg><div class="dc-tip" hidden></div></div><p class="dc-msg mute" role="status"></p>`;
  const wrap = root.querySelector(".dc-wrap"), svg = root.querySelector("svg"), tip = root.querySelector(".dc-tip"), msg = root.querySelector(".dc-msg");
  let rows = [], L = null, sel = -1;
  function draw() {
    const g = rows.length;
    if (!g) { svg.innerHTML = ""; tip.hidden = true; msg.textContent = "No resource records in the graph."; return; }
    const W = Math.max(280, wrap.clientWidth), cols = Math.floor(W / P);
    const k = Math.max(1, Math.min(6, Math.floor((cols - 1 - 3 * g - 3 * (g - 1)) / (4 * g))));
    const step = (4 * k + 6) * P, x0 = Math.max(R, (W - (g * step - 3 * P)) / 2);
    const max = _nice(Math.max(0, ...rows.flatMap(r => S.map(([n]) => r[n])))), nrows = Math.floor((H - TOP - BOT - R) / P), base = H - BOT - R;
    L = {W, k, g, max, nrows, base, colX: (a, b) => x0 + a * step + b * (k + 1) * P};
    let h = "";
    rows.forEach((r, gi) => {
      S.forEach(([n, c], si) => {
        const v = r[n], cnt = v > 0 ? Math.max(1, Math.round(v / max * nrows)) : 1;
        h += `<g data-i="${gi * 4 + si}" fill="${c}"${v > 0 ? "" : ' opacity=".6"'}>${dotColumn(L.colX(gi, si), base, cnt, k, v > 0 ? R : 1.6)}</g>`;
      });
      h += `<text x="${L.colX(gi, 0) + (4 * k + 3) * P / 2 - P / 2}" y="${H - 6}" text-anchor="middle">${esc(r.category)}</text>`;
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H);
    svg.innerHTML = `<text class="dc-max" x="2" y="10">max ${max}</text>${h}`;
    msg.textContent = `One shared axis · each dot ≈ ${+(max / nrows).toFixed(1)} units · a small hollow tick means zero`;
    if (sel >= 0 && sel < g * 4) select(sel); else tip.hidden = true;
  }
  function select(i) {
    sel = i;
    svg.querySelectorAll("g[data-i]").forEach(e => { const j = +e.dataset.i; e.setAttribute("fill", j === i ? YEL : S[j % 4][1]); });
    const gi = Math.floor(i / 4), si = i % 4, r = rows[gi], v = r[S[si][0]];
    const cnt = v > 0 ? Math.max(1, Math.round(v / L.max * L.nrows)) : 1, cx = L.colX(gi, si) + (L.k - 1) * P / 2 + R;
    tip.hidden = false; tip.innerHTML = `<b>${v} units</b><span>${esc(r.category)} · ${S[si][0]}</span>`;
    const tw = tip.offsetWidth; tip.style.left = Math.max(0, Math.min(L.W - tw, cx - tw / 2)) + "px"; tip.style.top = Math.max(2, L.base - (cnt - 1) * P - 52) + "px";
    svg.setAttribute("aria-label", `${r.category}, ${S[si][0]}: ${v} units`);
  }
  const at = e => { const b = svg.getBoundingClientRect(), x = (e.clientX - b.left) * (L.W / b.width);
    for (let a = 0; a < L.g; a++) for (let c = 0; c < 4; c++) { const x1 = L.colX(a, c) - P / 2; if (x >= x1 && x <= x1 + L.k * P + P / 2) return a * 4 + c; } return -1; };
  svg.addEventListener("pointermove", e => { if (L) { const i = at(e); if (i >= 0) select(i); } });
  svg.addEventListener("pointerdown", e => { if (L) { const i = at(e); if (i >= 0) select(i); } });
  svg.addEventListener("keydown", e => {
    if (!L || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return; e.preventDefault();
    select(Math.min(L.g * 4 - 1, Math.max(0, (sel < 0 ? 0 : sel) + (e.key === "ArrowRight" ? 1 : -1))));
  });
  new ResizeObserver(() => { if (rows.length) draw(); }).observe(wrap);
  return { set(r) { rows = r || []; draw(); } };
}

function DotRing(root) {
  const {R, YEL} = DOT, N = 60, C = 110, RAD = 88;
  const SV = [["critical", "#ef4444"], ["high", "#f97316"], ["medium", "#eab308"], ["low", "#22d3ee"], ["unrated", "#94a3b8"]];
  root.innerHTML = '<div class="dr"><svg viewBox="0 0 220 220" width="220" height="220" role="img"></svg><div class="dr-list"></div></div><p class="dc-msg mute" role="status"></p>';
  const svg = root.querySelector("svg"), list = root.querySelector(".dr-list"), msg = root.querySelector(".dc-msg");
  let counts = [], total = 0, sel = null;
  function alloc() {   // largest-remainder split of N dots; every present severity keeps >= 1 dot
    if (!total) return counts.map(() => 0);
    const raw = counts.map(c => c / total * N), d = raw.map(Math.floor);
    let rem = N - d.reduce((a, b) => a + b, 0);
    raw.map((v, i) => [v - Math.floor(v), i]).sort((a, b) => b[0] - a[0]).slice(0, rem).forEach(([, i]) => d[i]++);
    counts.forEach((c, i) => { if (c > 0 && d[i] === 0) { d[d.indexOf(Math.max(...d))]--; d[i] = 1; } });
    return d;
  }
  function draw() {
    const d = alloc(); let h = "", idx = 0;
    SV.forEach(([n, c], si) => {
      for (let j = 0; j < d[si]; j++, idx++) {
        const a = -Math.PI / 2 + idx * 2 * Math.PI / N, on = sel === n;
        h += `<circle data-s="${n}" cx="${(C + RAD * Math.cos(a)).toFixed(1)}" cy="${(C + RAD * Math.sin(a)).toFixed(1)}" r="${R}" fill="${on ? YEL : c}" opacity="${sel && !on ? .3 : 1}"/>`;
      }
    });
    if (!total) for (; idx < N; idx++) { const a = -Math.PI / 2 + idx * 2 * Math.PI / N; h += `<circle cx="${(C + RAD * Math.cos(a)).toFixed(1)}" cy="${(C + RAD * Math.sin(a)).toFixed(1)}" r="${R}" fill="var(--dot)" opacity=".2"/>`; }
    const si = SV.findIndex(x => x[0] === sel), n = sel ? counts[si] : total;
    h += sel ? `<rect x="${C - 40}" y="${C - 30}" width="80" height="60" rx="14" fill="${YEL}"/>` : "";
    h += `<text class="dr-n" x="${C}" y="${C + 6}" text-anchor="middle" style="fill:${sel ? "#161616" : "var(--ink)"}">${n}</text><text class="dr-l" x="${C}" y="${C + 24}" text-anchor="middle" style="fill:${sel ? "#161616" : "var(--mute)"}">${sel ? sel : "incidents"}</text>`;
    svg.innerHTML = h;
    list.innerHTML = SV.map(([n, c], i) => `<button data-s="${n}" aria-pressed="${sel === n}"><i style="background:${c}"></i>${n}<b>${counts[i]}</b></button>`).join("");
    msg.textContent = total ? `Dots show each severity's share of ${total} incident${total === 1 ? "" : "s"}; exact counts are in the list.` : "No incidents in the graph.";
  }
  const pick = n => { if (sel !== n) { sel = n; draw(); } };
  svg.addEventListener("pointerover", e => { const s = e.target.dataset && e.target.dataset.s; if (s) pick(s); });
  svg.addEventListener("pointerleave", () => pick(null));
  list.addEventListener("pointerover", e => { const b = e.target.closest("button"); if (b) pick(b.dataset.s); });
  list.addEventListener("pointerleave", () => pick(null));
  list.addEventListener("focusin", e => { const b = e.target.closest("button"); if (b) pick(b.dataset.s); });
  list.addEventListener("focusout", () => pick(null));
  return { set(sev) { counts = SV.map(([n]) => (sev && sev[n]) || 0); total = counts.reduce((a, b) => a + b, 0); draw(); } };
}
