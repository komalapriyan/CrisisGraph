// Single place for the API base. Override: localStorage.setItem("cg_api","http://host:8000/api")
const API = localStorage.getItem("cg_api") || "http://127.0.0.1:8000/api";
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const SEV = {critical:"#ef4444", high:"#f97316", medium:"#eab308", low:"#22d3ee", unrated:"#94a3b8"};
async function j(path, opt) {
  let r;
  try { r = await fetch(API + path, opt); } catch (e) { throw new Error("Cannot reach backend at " + API); }
  if (!r.ok) { const e = await r.json().catch(() => ({})); const err = new Error(e.detail || "HTTP " + r.status); err.status = r.status; throw err; }
  return r.json();
}
