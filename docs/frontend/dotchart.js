// Dotted-column chart (SVG). Column height = real value / axis max. No random data.
// Shared by every dotted chart so spacing and dot size stay identical.
const DOT = {P: 8, R: 3, H: 232, TOP: 34, YEL: "var(--yel)"};
function dotColumn(x, baseY, n, k, r) {
  r = r || DOT.R; let s = "";
  for (let c = 0; c < k; c++) for (let i = 0; i < n; i++) s += `<circle cx="${x + c * DOT.P}" cy="${baseY - i * DOT.P}" r="${r}"/>`;
  return s;
}
function DotChart(root) {
  const {P, R, H, TOP, YEL} = DOT, MY = 14;
  root.innerHTML = '<div class="dc-wrap"><svg tabindex="0" role="img"></svg><div class="dc-tip" hidden></div></div><div class="dc-axis"><span></span><span></span><span></span></div><p class="dc-msg mute" role="status"></p>';
  const wrap = root.querySelector(".dc-wrap"), svg = root.querySelector("svg"), tip = root.querySelector(".dc-tip"),
        msg = root.querySelector(".dc-msg"), ax = root.querySelectorAll(".dc-axis span");
  const UNIT = {unmet: "units unmet", allocated: "units allocated", closed_roads: "roads closed"};
  const NAME = {unmet: "Unmet demand", allocated: "Allocated", closed_roads: "Closed roads"};
  const FMT = {hourly: {hour: "2-digit", minute: "2-digit", day: "numeric", month: "short"}, daily: {day: "numeric", month: "short"},
               weekly: {day: "numeric", month: "short"}, monthly: {month: "short", year: "numeric"}};
  let d = null, sel = -1, L = null;
  const lab = t => (d.range === "weekly" ? "week of " : "") + new Date(t * 1000).toLocaleString([], FMT[d.range]);
  const nice = v => { if (v <= 0) return 1; const e = Math.pow(10, Math.floor(Math.log10(v))), m = v / e; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * e; };
  const count = v => v == null || v === 0 ? 0 : Math.max(1, Math.round(v / L.max * L.rows));

  function draw() {
    const W = Math.max(280, wrap.clientWidth), n = d.buckets.length;
    const k = Math.max(1, Math.floor(W / (n * P)) - 1), bw = (k + 1) * P, x0 = Math.max(R, (W - (n * bw - P)) / 2);
    const vals = d.buckets.map(b => b.value).filter(v => v != null);
    L = {W, n, k, bw, x0, rows: Math.floor((H - TOP - R) / P), max: nice(Math.max(0, ...vals))};
    let h = "";
    d.buckets.forEach((b, i) => {
      const nul = b.value == null, zero = b.value === 0, c = nul || zero ? 1 : count(b.value);
      h += `<g fill="var(--dot)"${nul ? ' opacity=".16"' : zero ? ' opacity=".35"' : ""}>` + dotColumn(x0 + i * bw + R, H - R, c, k, nul || zero ? 1.6 : R) + "</g>";
    });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H);
    svg.innerHTML = `<text class="dc-max" x="2" y="10">max ${L.max}</text><g id="cols">${h}</g><g id="sel"></g>`;
    ax[0].textContent = lab(d.buckets[0].t); ax[1].textContent = lab(d.buckets[Math.floor(n / 2)].t); ax[2].textContent = lab(d.buckets[n - 1].t);
    if (sel < 0 || sel >= n) { sel = n - 1; for (let i = n - 1; i >= 0; i--) if (d.buckets[i].value != null) { sel = i; break; } }
    select(sel);
  }
  function select(i) {
    sel = i;
    svg.querySelectorAll("#cols g").forEach((g, j) => g.setAttribute("fill", j === i ? YEL : "var(--dot)"));
    const b = d.buckets[i], v = b.value, cx = L.x0 + i * L.bw + ((L.k - 1) * P) / 2 + R;
    const ytop = H - R - (Math.max(count(v), 1) - 1) * P;
    let s = ""; for (let y = ytop - P; y > MY + 10; y -= P) s += `<circle cx="${cx}" cy="${y}" r="1.8" fill="${YEL}"/>`;
    s += `<circle cx="${cx}" cy="${MY}" r="6" fill="var(--panel)" stroke="${YEL}" stroke-width="3"/>`;
    svg.querySelector("#sel").innerHTML = s;
    tip.hidden = false;
    tip.innerHTML = v == null ? `<b>No snapshot</b><span>${lab(b.t)}</span>` : `<b>${v} ${UNIT[d.metric]}</b><span>${NAME[d.metric]} · ${lab(b.t)}</span>`;
    const tw = tip.offsetWidth; tip.style.left = (cx + 16 + tw > L.W ? cx - 16 - tw : cx + 16) + "px";
    svg.setAttribute("aria-label", `${NAME[d.metric]}, ${lab(b.t)}: ${v == null ? "no snapshot" : v}`);
  }
  const at = e => { const r = svg.getBoundingClientRect(), x = (e.clientX - r.left) * (L.W / r.width); return Math.min(L.n - 1, Math.max(0, Math.floor((x - L.x0 + P / 2) / L.bw))); };
  svg.addEventListener("pointermove", e => { if (L) select(at(e)); });
  svg.addEventListener("pointerdown", e => { if (L) select(at(e)); });
  svg.addEventListener("keydown", e => {
    if (!L || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault(); select(Math.min(L.n - 1, Math.max(0, sel + (e.key === "ArrowRight" ? 1 : -1))));
  });
  new ResizeObserver(() => { if (d) draw(); }).observe(wrap);
  return {
    set(h) {
      if (!d || d.range !== h.range || d.metric !== h.metric) sel = -1;
      d = h; const any = h.buckets.some(b => b.value != null);
      msg.textContent = any ? `${h.snapshots} snapshot${h.snapshots === 1 ? "" : "s"} in range · last ${new Date(h.last_snapshot * 1000).toLocaleString()} · simulated data`
                            : "No snapshots in this range yet. One is stored whenever scenario state changes.";
      draw();
    },
    setMsg(t) { msg.textContent = t; },
    hasData() { return !!d; }
  };
}
