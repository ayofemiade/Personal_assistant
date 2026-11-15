"use strict";
/* Moyo UI. Components and rules: see MOYO_AI_DESIGN_SYSTEM.md */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const usd = (v) => (v == null ? "n/a" : "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }));
const money = (v, c) => (c === "NGN" ? "₦" : c === "USD" ? "$" : c + " ") + Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
const nf = (v) => (v == null ? "n/a" : Number(v).toLocaleString());
const CATS = ["revenue", "client", "sales", "content", "study", "personal", "other"];
const STAGES = ["new", "qualified", "proposal", "negotiation", "won", "lost"];

/* ---------- dates: always LOCAL (Lagos), never UTC ---------- */
const localISO = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const addDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return localISO(d); };
const humanDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso.slice(0, 10) + "T00:00"), diff = Math.round((d - new Date(localISO() + "T00:00")) / 864e5);
  if (diff === 0) return "Today"; if (diff === 1) return "Tomorrow"; if (diff === -1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", ...(d.getFullYear() !== new Date().getFullYear() ? { year: "numeric" } : {}) });
};
const ago = (iso) => { const m = Math.round((Date.now() - new Date(iso)) / 6e4); return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`; };

/* ---------- icons (in-house, Lucide-style strokes) ---------- */
const P = {
  today: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  tasks: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m8 12 3 3 5-6"/>',
  money: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  content: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>',
  review: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  memory: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7M8 11h5"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  ask: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  play: '<path d="m7 4 13 8-13 8z"/>', pause: '<path d="M8 4v16M16 4v16"/>', next: '<path d="m5 4 10 8-10 8zM19 5v14"/>',
  voldown: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 9.5a3.5 3.5 0 0 1 0 5"/>',
  volup: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 9.5a3.5 3.5 0 0 1 0 5M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  speaker: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 9.5a3.5 3.5 0 0 1 0 5"/>', stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>', plus: '<path d="M12 5v14M5 12h14"/>', x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="m5 12 5 5 9-10"/>', alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17.5v.01"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.01"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>', cal: '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/>',
  code: '<path d="m8 8-5 4 5 4M16 8l5 4-5 4M14 4l-4 16"/>', briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>',
  book: '<path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h7z"/>', grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  flame: '<path d="M12 21c4 0 7-2.7 7-6.8 0-3.3-2.2-5.6-4-7.7-.4 2-1.4 3.3-2.8 3.8.4-2.8-.6-5.5-3.2-7.3.2 3-1.4 5-3 6.8C4.7 11.3 5 12.9 5 14.2 5 18.3 8 21 12 21z"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
  sunrise: '<path d="M12 2v6M5.6 10.6 4.2 9.2M18.4 10.6l1.4-1.4M2 18h2M20 18h2M17 18a5 5 0 0 0-10 0M2 22h20M8 6l4-4 4 4"/>', edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>', trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
};
const icon = (n, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ""}</svg>`;

/* ---------- components ---------- */
const pill = (text, tone = "", title = "") => `<span class="pill ${tone}"${title ? ` title="${esc(title)}"` : ""}>${text}</span>`;
const catDot = (c) => `<span class="dot" style="background:var(--cat-${esc(c)})" title="${esc(c)}" aria-hidden="true"></span>`;
const card = ({ title, meta = "", end = "", body = "", cls = "", id = "" }) =>
  `<div class="card ${cls}"${id ? ` id="${id}"` : ""}>${title ? `<div class="card-head"><h2>${title}</h2>${meta ? `<span class="meta">${meta}</span>` : ""}${end ? `<div class="end">${end}</div>` : ""}</div>` : ""}${body}</div>`;
const emptyState = (title, text = "", action = "") => `<div class="empty-state"><div class="es-title">${title}</div>${text ? `<div class="muted">${text}</div>` : ""}${action ? `<div class="actions" style="margin-top:10px">${action}</div>` : ""}</div>`;
const skeleton = (lines = 3) => `<div aria-busy="true" aria-label="Loading"><div class="skel h28"></div>${Array.from({ length: lines }, (_, i) => `<div class="skel ${i % 2 ? "w60" : ""}"></div>`).join("")}</div>`;
const errorState = (msg) => `<div class="error-state">${icon("alert")}<span class="grow">${esc(msg)}</span><button class="btn sm" data-retry>${icon("refresh", "sm")} Retry</button></div>`;
const stat = (v, l) => `<div><div class="stat-v">${v}</div><div class="stat-l">${l}</div></div>`;
const banner = (text, action = "", tone = "") => `<div class="banner ${tone}">${icon(tone === "warn" ? "alert" : "info")}<div class="grow">${text}</div>${action}</div>`;

async function api(method, path, body) {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json", "X-Moyo": "1" }, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Something went wrong (${r.status})`);
  return data;
}
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 3200); }

/* ---------- navigation ---------- */
const NAV = [["today", "Today", "today"], ["tasks", "Tasks", "tasks"], ["money", "Revenue", "money"], ["content", "Content", "content"],
  ["review", "Review", "review"], ["memory", "Memory", "memory"], ["settings", "Settings", "settings"]];
$("#nav").innerHTML = NAV.map(([id, label, ic], i) => `<a href="#${id}" data-view="${id}" title="${label}">${icon(ic)}<span class="label">${label}</span><span class="kbd">${i + 1}</span></a>`).join("");
$("#cmdicon").innerHTML = icon("ask");
let current = "today";
const renderers = {};
async function show(view, { focus = false } = {}) {
  if (!renderers[view]) view = "today";
  current = view;
  $$("#nav a").forEach((a) => (a.dataset.view === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  $$(".view").forEach((v) => v.classList.toggle("on", v.id === "view-" + view));
  const el = $("#view-" + view);
  if (!el.dataset.loaded) el.innerHTML = skeleton(4);
  try { await renderers[view](el); el.dataset.loaded = "1"; }
  catch (e) { el.innerHTML = card({ body: errorState(`Couldn't load this page: ${e.message}`) }); el.querySelector("[data-retry]").onclick = () => show(view); }
  try { localStorage.setItem("moyo.view", view); } catch {}
  if (location.hash !== "#" + view) history.replaceState(null, "", "#" + view);
  if (focus) $("#main").focus({ preventScroll: true });
}
$("#nav").addEventListener("click", (e) => { const a = e.target.closest("a"); if (!a) return; e.preventDefault(); show(a.dataset.view, { focus: true }); window.scrollTo(0, 0); });
const refresh = () => show(current);

/* ---------- command bar ---------- */
function showReply(res) {
  const box = $("#reply");
  box.className = "reply" + (res.error ? " err" : "") + (res.needs_confirmation ? " confirm" : "");
  let html = `<button class="btn btn-ghost icon sm x" aria-label="Close">${icon("x", "sm")}</button>${esc(res.reply)}`;
  if (res.needs_confirmation) html += `<div class="actions" style="margin-top:12px;white-space:normal"><button class="btn btn-primary" data-ok="1">Yes, do it</button><button class="btn" data-ok="0">Cancel</button></div>`;
  if (res.via) html += `<div class="src">${res.via === "cloud" ? "Understood via " + esc(res.model || "cloud") + (res.redacted ? " · client names and amounts were hidden from the cloud" : "") : "Handled on this laptop"}</div>`;
  box.innerHTML = html;
  box.querySelector(".x").onclick = () => box.classList.add("hidden");
  $$("[data-ok]", box).forEach((b) => (b.onclick = async () => {
    try { showReply(await api("POST", "/api/confirm", { pending_id: res.pending_id, accept: b.dataset.ok === "1" })); refresh(); }
    catch (e) { showReply({ reply: e.message, error: true }); }
  }));
  if (res.needs_confirmation) box.querySelector("[data-ok='1']").focus();
}
async function runAction(name, args) {
  try { const r = await api("POST", "/api/action/" + name, args); showReply(r); if (!r.needs_confirmation && !r.error) refresh(); return r; }
  catch (e) { showReply({ reply: e.message, error: true }); }
}
$("#cmd").addEventListener("submit", async (e) => {
  e.preventDefault();
  const inp = $("#cmdin"), text = inp.value.trim(); if (!text) return;
  inp.disabled = true; showReply({ reply: "Thinking…" });
  try { const r = await api("POST", "/api/chat", { text }); showReply(r); inp.value = "";
    if (r.action === "start_day") { await show("today"); if (r.read_briefing) speakBriefing(); }
    else if (r.view && r.view !== current && !r.needs_confirmation && r.action?.startsWith("get_")) show(r.view); else if (!r.error) refresh(); }
  catch (err) { showReply({ reply: err.message, error: true }); }
  inp.disabled = false; inp.focus();
});
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("#cmdin").focus(); }
  else if (e.key === "Escape") $("#reply").classList.add("hidden");
  else if (!typing && !e.ctrlKey && !e.metaKey && !e.altKey && /^[1-7]$/.test(e.key)) show(NAV[+e.key - 1][0], { focus: true });
});
const tick = () => ($("#clock").textContent = new Date().toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }));
tick(); setInterval(tick, 15000);

/* ---------- sidebar: workspaces + music ---------- */
const WS_ICON = { coding: "code", business: "briefcase", content: "camera", study: "book", general: "grid" };
(async () => {
  try {
    const ws = await api("GET", "/api/workspaces");
    $("#wslist").innerHTML = ws.map((w) => `<button data-ws="${esc(w.key)}" title="Open ${esc(w.label)}: ${esc([...w.apps.map((a) => a.name), w.urls.length ? w.urls.length + " tabs" : "", w.music ? "music" : ""].filter(Boolean).join(", ") || "empty")}">${icon(WS_ICON[w.key] || "grid")}<span class="label">${esc(w.label.replace(/ mode$/i, ""))}</span></button>`).join("");
    $$("#wslist [data-ws]").forEach((b) => (b.onclick = () => runAction("open_workspace", { profile: b.dataset.ws })));
  } catch { $("#wslist").innerHTML = `<span class="xs faint">Workspaces unavailable</span>`; }
  $("#media").innerHTML = [["play_pause", "play", "Play or pause"], ["next", "next", "Next track"], ["volume_down", "voldown", "Volume down"], ["volume_up", "volup", "Volume up"]]
    .map(([a, ic, l]) => `<button class="btn btn-ghost icon sm" data-media="${a}" aria-label="${l}" title="${l}">${icon(ic, "sm")}</button>`).join("");
  $$("#media [data-media]").forEach((b) => (b.onclick = () => runAction("media", { action: b.dataset.media, times: b.dataset.media.startsWith("volume") ? 3 : 1 })));
})();

/* ---------- voice (natural voices with fallback) ---------- */
const Speaker = {
  audio: null, stopped: true, onchange: null, used: "",
  async fetchClip(text, engine, voice, speed) {
    const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json", "X-Moyo": "1" }, body: JSON.stringify(engine ? { text, engine, voice, speed } : { text }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "voice unavailable");
    return { url: URL.createObjectURL(await r.blob()), used: r.headers.get("X-Moyo-Voice") || "" };
  },
  play(url) { return new Promise((res, rej) => { this.audio = new Audio(url); this.audio.onended = res; this.audio.onerror = rej; this.audio.play().catch(rej); }); },
  browserSay(text, voiceName, speed) { return new Promise((res) => { const u = new SpeechSynthesisUtterance(text.replace(/\$/g, " dollars ").replace(/₦/g, " naira "));
    const v = speechSynthesis.getVoices().find((x) => x.name === voiceName); if (v) u.voice = v; u.rate = speed || 1; u.onend = res; u.onerror = res; speechSynthesis.speak(u); }); },
  stop() { this.stopped = true; this.audio?.pause(); speechSynthesis.cancel(); this.onchange?.(false); },
  async speak(text, opts = {}) {
    this.stop(); this.stopped = false; this.onchange?.(true);
    const parts = text.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean), pref = opts.pref || {};
    try {
      if (pref.engine === "browser") { for (const p of parts) { if (this.stopped) break; await this.browserSay(p, pref.voice, pref.speed); } return; }
      let next = this.fetchClip(parts[0], opts.engine, opts.voice, opts.speed);
      for (let i = 0; i < parts.length && !this.stopped; i++) {
        let clip;
        try { clip = await next; } catch (e) {
          if (opts.engine) throw e;
          toast("Natural voices unavailable, using the basic voice"); for (const p of parts.slice(i)) { if (this.stopped) break; await this.browserSay(p); } return;
        }
        this.used = clip.used;
        if (i + 1 < parts.length) next = this.fetchClip(parts[i + 1], opts.engine, opts.voice, opts.speed);
        if (!this.stopped) await this.play(clip.url).catch(() => {});
        URL.revokeObjectURL(clip.url);
      }
    } finally { if (!this.stopped) { this.stopped = true; this.onchange?.(false); } }
  },
};

/* ---------- notification centre ---------- */
const LEVEL = { urgent: "Urgent", important: "Important", info: "For later" };
async function loadNotifications() {
  let n; try { n = await api("GET", "/api/notifications"); } catch { return; }
  const badge = $("#badge");
  badge.textContent = n.unread > 9 ? "9+" : n.unread; badge.classList.toggle("hidden", !n.unread);
  $("#bell").setAttribute("aria-label", n.unread ? `Notifications, ${n.unread} unread` : "Notifications");
  const panel = $("#notifpanel");
  panel.innerHTML = `<div class="card-head" style="margin-bottom:6px"><h2>Notifications</h2><div class="end">${n.unread ? `<button class="btn btn-ghost sm" id="readall">Mark all read</button>` : ""}</div></div>
    ${n.items.length ? n.items.map((x) => `<div class="notif ${x.read_at ? "read" : ""}"><span class="lvl ${x.level}" title="${LEVEL[x.level]}"></span><div>
      <div class="title">${esc(x.title)}</div>${x.body ? `<div class="meta">${esc(x.body)}</div>` : ""}
      <div class="meta">${LEVEL[x.level]} · ${ago(x.created_at)}</div>
      ${x.view ? `<button class="link-btn" data-nview="${esc(x.view)}" data-nid="${x.id}">${x.view === "start-day" ? "Start my day" : "Open"}</button>` : ""}</div></div>`).join("")
      : emptyState("You're all caught up", "Moyo will tell you about overdue follow-ups, posting reminders, meetings and your weekly review here.")}
    <div class="foot">Desktop pop-ups for important and urgent items, never during quiet hours. Change in <a href="#settings" data-nview="settings">Settings</a>.</div>`;
  const ra = $("#readall"); if (ra) ra.onclick = async () => { await api("POST", "/api/notifications/read", {}); loadNotifications(); };
  $$("[data-nview]", panel).forEach((b) => (b.onclick = async (e) => { e.preventDefault(); toggleNotif(false);
    if (b.dataset.nid) await api("POST", "/api/notifications/read", { ids: [+b.dataset.nid] }).catch(() => {});
    if (b.dataset.nview === "start-day") startDay(); else show(b.dataset.nview === "settings" ? "settings" : b.dataset.nview, { focus: true });
    loadNotifications(); }));
}
function toggleNotif(open) {
  const p = $("#notifpanel"), b = $("#bell"); open = open ?? p.classList.contains("hidden");
  p.classList.toggle("hidden", !open); b.setAttribute("aria-expanded", String(open));
  if (open) { loadNotifications(); setTimeout(() => p.querySelector("button, a")?.focus(), 50); }
}
$("#bellicon").innerHTML = icon("bell");
$("#talkicon").innerHTML = icon("mic");
$("#talkbtn").onclick = async () => {
  try { const r = await api("POST", "/api/wake/talk"); toast(r.opened ? "Moyo is listening (top-right). Your voice goes to Google Gemini while it's open." : "Moyo's orb is already open."); }
  catch (e) { toast("Couldn't start voice: " + e.message); } };
$("#bell").onclick = () => toggleNotif();
document.addEventListener("click", (e) => { if (!e.target.closest(".bell-wrap")) toggleNotif(false); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#notifpanel").classList.contains("hidden")) { toggleNotif(false); $("#bell").focus(); } });
loadNotifications(); setInterval(loadNotifications, 60000);
updateMicIndicator(); setInterval(updateMicIndicator, 60000);

/* ---------- start my day ---------- */
async function speakBriefing() {
  const sp = $("#speak");
  try {
    const [{ current: pref }, d] = await Promise.all([api("GET", "/api/voices"), api("GET", "/api/dashboard")]);
    if (!lastCoaching) { try { lastCoaching = await api("GET", "/api/coaching"); } catch {} }
    const coachText = lastCoaching?.speech ? "\n\nNow, my coaching for today.\n\n" + lastCoaching.speech : "";
    if (sp) sp.innerHTML = `${icon("speaker", "sm")} Preparing voice…`;
    Speaker.speak(d.text.replace(/\n\nLet's get started\.$/, "") + coachText + "\n\nLet's get started.", { pref });
  } catch (e) { toast("Couldn't read the briefing: " + e.message); }
}
async function startDay() {
  await show("today");
  try { const r = await api("POST", "/api/routine/start"); showReply({ reply: r.reply, via: "local" }); loadNotifications();
    if (r.read_briefing) speakBriefing(); }
  catch (e) { showReply({ reply: e.message, error: true }); }
}

/* ================================================================ TODAY */
let lastCoaching = null;
renderers.today = async (el) => {
  const d = await api("GET", "/api/dashboard");
  const ch = d.challenge, plan = d.plan, cs = d.content, pipe = d.pipeline;
  const nowHM = new Date().toTimeString().slice(0, 5);
  const greeting = d.text.split("\n")[0].split(".")[0];
  const banners = [];
  if (!d.ngn_per_usd) banners.push(banner("Set your ₦/$ rate so naira payments can count toward the $10K.", `<button class="btn sm" data-go="settings">Set rate</button>`, "warn"));
  if (!plan.schedule_confirmed) banners.push(banner("Your meeting and gym times are still my guesses.", `<button class="btn sm" data-go="settings">Confirm schedule</button>`));
  const past = plan.blocks.filter((b) => b.end <= nowHM), upcoming = plan.blocks.filter((b) => b.end > nowHM);
  const tlRow = (b) => `<div class="tl-row ${b.kind} ${b.start <= nowHM && nowHM < b.end ? "now" : ""} ${b.end <= nowHM ? "past" : ""}" ${b.category ? `style="border-left-color:var(--cat-${esc(b.category)})"` : ""}>
      <span class="t">${b.start}–${b.end}</span><span class="src">${b.kind === "calendar" ? icon("cal", "sm") : ""}${esc(b.title.replace(/^📅\s*/, ""))}</span></div>`;
  const briefing = d.text.split("\n\n").slice(1).join("\n\n");

  el.innerHTML = `
  <div class="page-head"><div>
      <h1>${esc(greeting)}.</h1>
      <div class="status-strip">
        <span>${new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</span>
        <span><b>${usd(ch.earned_usd)}</b> of ${usd(ch.target_usd)} earned</span>
        <span><b>${usd(ch.required_per_week_usd)}</b> needed per week</span>
        <span><b>${ch.days_left}</b> days left</span>
        ${cs.daily_streak ? `<span>${icon("flame", "sm")} <b>${cs.daily_streak}-day</b> posting streak</span>` : ""}
      </div></div>
    <div class="actions">${d.routine_ran_today ? "" : `<button class="btn btn-primary" id="startday">${icon("sunrise", "sm")} Start my day</button>`}
      <button class="btn" id="speak">${icon("speaker", "sm")} Listen to briefing</button><button class="btn" data-go="review">${icon("review", "sm")} Review</button></div>
  </div>
  ${banners.join("")}
  <details class="more" style="margin:-6px 0 18px"><summary>Read the full briefing</summary><div class="card" style="margin-top:8px"><div class="briefing-text">${esc(briefing)}</div></div></details>
  <div class="grid">
    <div class="c-7 stack">
      ${card({ title: "Plan for today", meta: plan.top3.length ? "your top 3, in order" : "", body:
        plan.top3.length ? `<div>${plan.top3.map((p, i) => `<div class="priority"><span class="n">${i + 1}</span><div><div class="title">${esc(p.title)}</div><div class="why">${catDot(p.category)} ${esc(p.why)}</div></div>
          ${p.task_id ? `<button class="btn btn-ghost icon sm" data-done="${p.task_id}" aria-label="Mark “${esc(p.title)}” done" title="Mark done">${icon("check", "sm")}</button>` : ""}</div>`).join("")}</div>
          ${plan.unscheduled.length ? `<div class="foot">${plan.unscheduled.length} more item(s) don't fit today. I kept a ${plan.buffer_pct}% buffer instead of overbooking you.</div>` : ""}`
        : emptyState("Nothing planned yet", "Tell Moyo what matters today.", `<button class="btn sm" data-fill="add task ">${icon("plus", "sm")} Add a task</button>`) })}
      ${card({ id: "coachcard", title: "Coaching", body: skeleton(3) })}
    </div>
    <div class="c-5 stack">
      ${card({ title: "$10K challenge", end: pill(ch.on_track ? "On pace" : `${usd(Math.abs(ch.gap_vs_pace_usd))} behind`, ch.on_track ? "good" : "warn"), body: `
        <div><span class="hero-num">${usd(ch.earned_usd)}</span> <span class="muted">of ${usd(ch.target_usd)}</span></div>
        <div class="progress" role="img" aria-label="${ch.pct}% of target; the marker shows where steady pace would be"><i style="width:${ch.pct}%"></i><b style="left:${Math.min(100, (ch.expected_by_now_usd / ch.target_usd) * 100)}%"></b></div>
        <div class="progress-legend"><span>${ch.pct}% ${ch.progress_word || "earned"}</span><span>marker = steady pace</span></div>
        <div class="stats" style="--cols:3">${stat(usd(ch.remaining_usd), "remaining")}${stat(usd(ch.required_per_week_usd), "per week")}${stat(usd(ch.weighted_pipeline_usd), "in pipeline")}</div>` })}
      ${card({ title: "Schedule", meta: `${Math.round(plan.planned_minutes / 6) / 10}h of ${Math.round(plan.free_minutes / 6) / 10}h free planned`, body: `
        ${past.length ? `<details class="more" style="margin-bottom:6px"><summary>Earlier today (${past.length})</summary><div class="timeline" style="margin-top:6px">${past.map(tlRow).join("")}</div></details>` : ""}
        <div class="timeline">${upcoming.map(tlRow).join("") || emptyState("Day's done", "Nothing left on the schedule.")}</div>
        ${plan.hidden_assumed?.length ? `<div class="foot">Hidden because your calendar has something at the same time: ${plan.hidden_assumed.map(esc).join(", ")}.</div>` : ""}` })}
    </div>
    <div class="c-4">${card({ title: "Content today", end: cs.daily_streak ? pill(`${icon("flame", "sm")} ${cs.daily_streak}-day streak`, "accent") : "", body: `<div class="rows">
      ${[["tiktok", "TikTok"], ["instagram", "Instagram"]].map(([p, l]) => `<div class="row"><div class="grow"><div class="title">${l}</div><div class="meta">${cs.today[p] ? "Posted today" : "Not posted yet"}</div></div>
        ${cs.today[p] ? pill(`${icon("check", "sm")} done`, "good") : `<button class="btn sm" data-post="${p}">Mark posted</button>`}</div>`).join("")}
      <div class="row"><div class="grow"><div class="title">LinkedIn</div><div class="meta">${cs.linkedin_this_week} of ${cs.linkedin_target} this week</div></div>
        <button class="btn sm" data-post="linkedin">Log post</button></div></div>
      <div class="foot">Synced TikTok and Instagram posts tick automatically. Stats are on the <a href="#content" data-go="content">Content</a> page.</div>` })}</div>
    <div class="c-4">${card({ title: "Follow-ups", body: pipe.followups_due.length
      ? `<div class="rows">${pipe.followups_due.map((f) => `<div class="row"><div class="grow"><div class="title">${esc(f.name)}</div><div class="meta">${esc(f.stage)} · ${humanDate(f.date)}</div></div>${f.overdue ? pill("overdue", "warn") : pill("today", "accent")}</div>`).join("")}</div>`
      : pipe.open ? emptyState("Nothing due today", "Every open lead has a future follow-up date.")
        : emptyState("No leads yet", "Your pipeline is where the $10K comes from.", `<button class="btn sm" data-go="money">${icon("plus", "sm")} Add a lead</button>`) })}</div>
    <div class="c-4">${card({ id: "inboxcard", title: "Inbox", body: skeleton(2) })}</div>
  </div>`;

  $$("[data-go]", el).forEach((b) => (b.onclick = (e) => { e.preventDefault(); show(b.dataset.go, { focus: true }); }));
  $$("[data-fill]", el).forEach((b) => (b.onclick = () => { const i = $("#cmdin"); i.value = b.dataset.fill; i.focus(); }));
  $$("[data-done]", el).forEach((b) => (b.onclick = () => runAction("complete_task", { task_id: +b.dataset.done })));
  $$("[data-post]", el).forEach((b) => (b.onclick = () => runAction("log_post", { platform: b.dataset.post, title: null })));
  const sp = $("#speak");
  Speaker.onchange = (on) => { if (document.body.contains(sp)) sp.innerHTML = on ? `${icon("stop", "sm")} Stop` : `${icon("speaker", "sm")} Listen to briefing`; };
  sp.onclick = () => (!Speaker.stopped ? Speaker.stop() : speakBriefing());
  const sd = $("#startday"); if (sd) sd.onclick = () => { sd.disabled = true; startDay(); };
  loadCoaching(false);
  loadInbox();
};

async function loadCoaching(refresh) {
  const box = $("#coachcard"); if (!box) return;
  const head = (end) => `<div class="card-head"><h2>Coaching</h2><div class="end">${end}</div></div>`;
  if (refresh) box.innerHTML = head("") + skeleton(3);
  let c;
  try { c = await api("GET", "/api/coaching" + (refresh ? "?refresh=true" : "")); }
  catch (e) { box.innerHTML = head("") + errorState(e.message); box.querySelector("[data-retry]").onclick = () => loadCoaching(true); return; }
  lastCoaching = c;
  if (!document.body.contains(box)) return;
  const src = c.source === "ai"
    ? `AI coach (${esc(c.model)}). Every number is checked against your data${c.dropped_unverified ? `; ${c.dropped_unverified} unverifiable point(s) removed` : ""}. Client names never leave this laptop.`
    : `From your data directly${c.note ? `. ${esc(c.note)}` : ""}`;
  box.innerHTML = head(`${pill(c.source === "ai" ? "AI" : "rules", c.source === "ai" ? "accent" : "")}<button class="btn btn-ghost icon sm" id="coachref" aria-label="Refresh coaching" title="Refresh">${icon("refresh", "sm")}</button>`) +
    (c.headline ? `<div class="coach-head">${esc(c.headline)}</div>` : "") +
    (c.points.length ? `<div>${c.points.map((p, i) => `<div class="priority"><span class="n">${i + 1}</span><div><div class="title">${esc(p.action)}</div>${p.why ? `<div class="why">${esc(p.why)}</div>` : ""}</div><span></span></div>`).join("")}</div>`
      : emptyState("Nothing urgent", "Your numbers look fine for today.")) + `<div class="foot">${src}</div>`;
  $("#coachref").onclick = () => loadCoaching(true);
}

const KIND = { lead: ["lead", "accent"], client: ["client", "good"], personal: ["", ""], updates: ["update", ""], promotions: ["promo", ""], social: ["social", ""], forums: ["forum", ""] };
async function loadInbox() {
  const box = $("#inboxcard"); if (!box) return;
  const head = (end = "") => `<div class="card-head"><h2>Inbox</h2><div class="end">${end}</div></div>`;
  let ib;
  try { ib = await api("GET", "/api/inbox"); }
  catch (e) { box.innerHTML = head() + errorState(e.message); box.querySelector("[data-retry]").onclick = loadInbox; return; }
  if (!ib.connected) { box.innerHTML = head() + emptyState("Gmail isn't connected", "Connect it to see emails from leads and clients here.", `<button class="btn sm" data-go2="settings">Connect Google</button>`);
    box.querySelector("[data-go2]").onclick = () => show("settings"); return; }
  const people = ib.important.slice(0, 5), others = ib.all.filter((e) => !ib.important.includes(e));
  const row = (e) => `<div class="row"><div class="grow"><div class="title ${e.unread ? "unread" : ""}">${esc(e.from_name || e.from_email)} ${KIND[e.kind]?.[0] ? pill(KIND[e.kind][0], KIND[e.kind][1]) : ""}</div>
    <div class="meta">${esc(e.subject)} · ${ago(e.received_at)}</div></div><button class="btn sm" data-open="${esc(e.id)}" aria-label="Open email from ${esc(e.from_name || e.from_email)}">Open</button></div>`;
  box.innerHTML = head(`${pill(`${ib.unread_24h} unread`, ib.from_leads.length ? "accent" : "")}<button class="btn btn-ghost icon sm" id="mailsync" aria-label="Sync inbox" title="Sync">${icon("refresh", "sm")}</button>`) +
    (ib.error ? banner(esc(ib.error), "", "warn") : "") +
    (people.length ? `<div class="rows">${people.map(row).join("")}</div>` : emptyState("No emails from people or leads", "Only newsletters and notifications in the last few days.")) +
    (others.length ? `<details class="more" style="margin-top:6px"><summary>${others.length} promotions and updates</summary><div class="rows">${others.slice(0, 15).map(row).join("")}</div></details>` : "") +
    `<div class="foot">Moyo syncs senders and subjects only. Opening an email fetches it live; it's never saved or sent to an AI.</div>`;
  $("#mailsync").onclick = async () => { $("#mailsync").disabled = true; try { const r = await api("POST", "/api/google/sync"); if (!r.ok) toast(r.error); } catch (e) { toast(e.message); } loadInbox(); };
  $$("[data-open]", box).forEach((b) => (b.onclick = () => openEmail(b.dataset.open, b)));
}
async function openEmail(id, opener) {
  const dlg = document.createElement("dialog"); dlg.className = "sheet"; dlg.setAttribute("aria-label", "Email");
  dlg.innerHTML = skeleton(4); document.body.appendChild(dlg); dlg.showModal();
  dlg.addEventListener("close", () => { dlg.remove(); opener?.focus(); });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  try {
    const e = await api("GET", "/api/inbox/" + encodeURIComponent(id));
    dlg.innerHTML = `<button class="btn btn-ghost icon sm x" aria-label="Close">${icon("x", "sm")}</button><h2 style="font:600 20px/1.3 var(--font-display);padding-right:36px">${esc(e.subject)}</h2>
      <div class="small muted" style="margin-top:6px">From ${esc(e.from)} · ${esc(e.date)}</div>
      <div class="banner info" style="margin-top:14px">${icon("info")}<div class="grow small">This is the sender's text. Moyo treats it as information only and never follows instructions inside emails.</div></div>
      <div class="mailbody">${esc(e.body) || '<span class="muted">(no text content)</span>'}</div>
      <div class="actions"><a class="btn" href="${esc(e.gmail_link)}" target="_blank" rel="noopener">${icon("ext", "sm")} Open in Gmail</a></div>`;
  } catch (err) { dlg.innerHTML = `<button class="btn btn-ghost icon sm x" aria-label="Close">${icon("x", "sm")}</button>${errorState(err.message)}`; dlg.querySelector("[data-retry]").onclick = () => { dlg.close(); openEmail(id, opener); }; }
  dlg.querySelector(".x").onclick = () => dlg.close(); dlg.querySelector(".x").focus();
}

/* ================================================================ TASKS */
renderers.tasks = async (el) => {
  const d = await api("GET", "/api/dashboard"), ov = d.tasks_overview;
  const total = ov.overdue.length + ov.today.length + ov.upcoming.length + ov.no_date.length;
  const prioPill = (p) => (p === 1 ? pill("P1", "warn") : p === 2 ? pill("P2", "accent") : "");
  const row = (t) => `<div class="row">
    <input type="checkbox" data-done="${t.id}" aria-label="Mark “${esc(t.title)}” done">
    <div class="grow"><div class="title">${catDot(t.category)} ${esc(t.title)} ${prioPill(t.priority)} ${t.recurrence ? pill(`${icon("refresh", "sm")} ${esc(t.recurrence)}`) : ""}</div>
      <div class="meta">${esc(t.category)} · ${t.estimate_min} min${t.due_time ? " · " + esc(t.due_time) : ""}${t.project ? " · " + esc(t.project) : ""}</div></div>
    <input type="date" value="${esc(t.due_date || "")}" data-move="${t.id}" aria-label="Due date for ${esc(t.title)}">
    <select data-prio="${t.id}" aria-label="Priority for ${esc(t.title)}">${[1, 2, 3, 4].map((p) => `<option value="${p}" ${p === t.priority ? "selected" : ""}>P${p}</option>`).join("")}</select></div>`;
  const group = (title, list, tone) => (list.length ? `<div class="group-label">${title} ${pill(list.length, tone)}</div><div class="rows">${list.map(row).join("")}</div>` : "");
  el.innerHTML = `<div class="page-head"><div><h1>Tasks</h1><div class="sub">${total} open · ${ov.done_today} done today</div></div></div>
  ${card({ body: `<form id="tform">
      <div class="fields">
        <label class="field grow"><span>New task</span><input name="title" required placeholder="e.g. Send proposal to Tunde"></label>
        <label class="field"><span>Due</span><input type="date" name="due"></label>
        <label class="field"><span>Time</span><input type="time" name="due_time"></label>
        <button class="btn btn-primary">${icon("plus", "sm")} Add task</button>
      </div>
      <details class="more" style="margin-top:10px"><summary>More options</summary><div class="fields" style="margin-top:10px">
        <label class="field"><span>Category</span><select name="category"><option value="">Automatic</option>${CATS.map((c) => `<option value="${c}">${c[0].toUpperCase() + c.slice(1)}</option>`).join("")}</select></label>
        <label class="field"><span>Priority</span><select name="priority"><option value="3">P3 · Normal</option><option value="1">P1 · Urgent</option><option value="2">P2 · High</option><option value="4">P4 · Low</option></select></label>
        <label class="field"><span>Estimate (minutes)</span><input type="number" name="estimate_min" value="45" min="5" max="480" step="5" style="width:150px"></label>
        <label class="field"><span>Repeats</span><select name="recurrence"><option value="">Doesn't repeat</option><option value="daily">Every day</option><option value="weekdays">Weekdays</option><option value="weekly:MO,WE,FR">Mon, Wed, Fri</option></select></label>
      </div></details></form>` })}
  <div style="height:20px"></div>
  ${card({ body: total ? group("Overdue", ov.overdue, "warn") + group("Today", ov.today, "accent") + group("Next 7 days", ov.upcoming) + group("No date", ov.no_date)
    : emptyState("All clear", "No open tasks. Add one above, or type “add task …” in the command bar.") })}`;
  $("#tform").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target));
    const args = { title: f.title, due: f.due || null, due_time: f.due_time || null, priority: +f.priority, estimate_min: +f.estimate_min };
    if (f.category) args.category = f.category; if (f.recurrence) { args.recurrence = f.recurrence; args.due = args.due || localISO(); }
    await runAction("add_task", args); };
  $$("[data-done]", el).forEach((b) => (b.onchange = () => runAction("complete_task", { task_id: +b.dataset.done })));
  $$("[data-move]", el).forEach((b) => (b.onchange = () => b.value && runAction("move_task", { task_id: +b.dataset.move, new_date: b.value })));
  $$("[data-prio]", el).forEach((b) => (b.onchange = async () => { try { await api("PATCH", "/api/tasks/" + b.dataset.prio, { priority: +b.value }); toast("Priority updated"); refresh(); } catch (e) { toast(e.message); } }));
};

/* ================================================================ MONEY */
async function renderMoneyTab(el) {  // the "Money" tab inside Revenue (revenue.js)
  const [d, inv] = await Promise.all([api("GET", "/api/money"), api("GET", "/api/invoices")]), ch = d.challenge, pipe = d.pipeline;
  el.innerHTML = `<div class="sub muted" style="margin:0 0 12px">$10K challenge · counts money when it's paid · ${humanDate(ch.start)} to ${humanDate(ch.end)} · day ${ch.days_elapsed} of ${ch.days_total}</div>
  ${!d.ngn_per_usd ? banner("Set your ₦/$ rate before logging naira, so Moyo never guesses a conversion.", `<button class="btn sm" data-go="settings">Set rate</button>`, "warn") : ""}
  <div class="grid">
    <div class="c-12">${card({ body: `<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline">
        <div><span class="hero-num">${usd(ch.earned_usd)}</span> <span class="muted">of ${usd(ch.target_usd)} ${ch.progress_word || "earned"}</span></div>
        ${pill(ch.on_track ? "On pace" : `${usd(Math.abs(ch.gap_vs_pace_usd))} behind steady pace`, ch.on_track ? "good" : "warn")}</div>
      <div class="progress" role="img" aria-label="${ch.pct}% of target"><i style="width:${ch.pct}%"></i><b style="left:${Math.min(100, ch.expected_by_now_usd / ch.target_usd * 100)}%"></b></div>
      <div class="progress-legend"><span>${ch.pct}% ${ch.progress_word || "earned"}</span><span>marker = where steady pace would be today</span></div>
      <div class="stats" style="--cols:4">${stat(usd(ch.remaining_usd), "still to earn")}${stat(usd(ch.required_per_week_usd), "needed per week")}${stat(usd(ch.earned_this_week_usd), "earned this week")}${stat(ch.days_left, "days left")}</div>
      <div class="stats secondary" style="--cols:4">${stat(usd(ch.collected_usd), "cash collected")}${stat(usd(ch.outstanding_usd), "earned, not yet paid")}${stat(usd(ch.weighted_pipeline_usd), `weighted pipeline${ch.pipeline_coverage != null ? ` · ${Math.round(ch.pipeline_coverage * 100)}% of gap` : ""}`)}${stat(pipe.avg_won_deal_usd != null ? usd(pipe.avg_won_deal_usd) : "n/a", "average won deal")}</div>` })}</div>
    <div class="c-12">${card({ title: "Money logged", meta: `${d.earnings.length} logged · only paid money counts toward the $10K`, body: `
      <details class="add"><summary class="btn btn-primary sm">${icon("plus", "sm")} Log money earned</summary>
        <form id="eform" class="form-card"><div class="fields">
          <label class="field"><span>Amount</span><input name="amount" type="number" min="1" step="any" required style="width:140px"></label>
          <label class="field"><span>Currency</span><select name="currency"><option>NGN</option><option>USD</option></select></label>
          <label class="field grow"><span>Client</span><input name="client" placeholder="e.g. Adebayo Ventures"></label>
          <label class="field"><span>Date earned</span><input name="earned_date" type="date" value="${localISO()}"></label>
        </div><div class="actions" style="margin-top:12px;justify-content:space-between"><label class="check"><input type="checkbox" name="paid"> Already paid</label>
          <button class="btn btn-primary">Review & log</button></div><div class="foot" style="margin-top:8px">You'll confirm before anything is recorded.</div></form></details>
      <div class="tablewrap" style="margin-top:12px">${d.earnings.length ? `<table><thead><tr><th>Date</th><th>Client</th><th class="r">Amount</th><th class="r">USD</th><th>Status</th></tr></thead><tbody>
        ${d.earnings.map((e) => `<tr><td>${humanDate(e.earned_date)}</td><td>${esc(e.client || "n/a")}</td><td class="r">${money(e.amount, e.currency)}</td><td class="r">${usd(e.usd_amount)}</td>
          <td>${e.payment_status === "paid" ? pill("paid", "good") : `<button class="btn sm" data-paid="${e.id}">Mark paid</button>`}</td></tr>`).join("")}</tbody></table>`
        : emptyState("No earnings yet", "When a client pays or work is delivered, log it here or say “log payment ₦200,000 from …”.")}</div>` })}</div>
    <div class="c-12">${card({ title: "Invoices", meta: `${inv.length} created · drafts are never sent by Moyo`, body: `
      <details class="add"><summary class="btn btn-primary sm">${icon("plus", "sm")} New invoice</summary>
        <form id="iform" class="form-card"><div class="fields">
          <label class="field grow"><span>Bill to</span><input name="client" required placeholder="e.g. Kemi Stores"></label>
          <label class="field grow"><span>Contact / address (optional)</span><input name="bill_to" placeholder="e.g. Mrs Kemi Adeyemi, Ibadan"></label>
          <label class="field"><span>Deposit %</span><input name="deposit_pct" type="number" min="0" max="100" value="50" style="width:110px"></label>
          <label class="field"><span>Discount (₦)</span><input name="discount" type="number" min="0" step="any" style="width:130px"></label>
        </div>
        <label class="field" style="margin-top:12px"><span>Items: one per line, “description - amount”</span>
          <textarea name="items" rows="3" required placeholder="Website development (kemistores.com) - 300000&#10;Website maintenance (annual) - 150000"></textarea></label>
        <div class="actions" style="margin-top:12px;justify-content:space-between"><span class="foot" style="margin:0">Creates a PDF in your Invoices folder for you to review. Nothing is sent.</span>
          <button class="btn btn-primary">Create draft</button></div></form></details>
      <div class="tablewrap" style="margin-top:12px">${inv.length ? `<table><thead><tr><th>Number</th><th>Client</th><th>Date</th><th class="r">Total</th><th>Status</th><th></th></tr></thead><tbody>
        ${inv.map((i) => `<tr><td>${esc(i.number)}</td><td>${esc(i.client)}</td><td>${humanDate(i.issue_date)}</td><td class="r">${money(i.total, i.currency)}</td>
          <td>${pill(esc(i.status), i.status === "paid" ? "good" : "")}</td><td class="r">${i.pdf_path ? `<button class="btn sm" data-inv="${i.id}">Open PDF</button>` : ""}</td></tr>`).join("")}</tbody></table>`
        : emptyState("No invoices yet", "Create one here, or say “create an invoice for Kemi Stores, website development 450,000 naira, 50% deposit”.")}</div>` })}</div>
  </div>`;
  $("#iform").onsubmit = (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target));
    const items = f.items.split(/\n/).map((l) => l.trim()).filter(Boolean).map((l) => { const m = l.match(/^(.*?)\s*[-–:]\s*([₦$]?[\d,.]+\s*[kKmM]?)\s*$/);
      return m ? { description: m[1].trim(), amount: m[2] } : { description: l }; });
    runAction("create_invoice", { client: f.client, bill_to: f.bill_to || null, items, deposit_pct: f.deposit_pct ? +f.deposit_pct : null, discount: f.discount ? +f.discount : 0 }); };
  $$("[data-inv]", el).forEach((b) => (b.onclick = async () => { try { await api("POST", `/api/invoices/${b.dataset.inv}/open`); } catch (err) { toast(err.message); } }));
  $$("[data-go]", el).forEach((b) => (b.onclick = () => show(b.dataset.go)));
  $("#eform").onsubmit = (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target));
    runAction("log_payment", { amount: +f.amount, currency: f.currency, client: f.client || null, earned_date: f.earned_date, paid: !!f.paid }); };
  const patch = async (path, body, msg) => { try { await api(body ? "PATCH" : "POST", path, body); toast(msg); refresh(); } catch (e) { toast(e.message); } };
  $$("[data-paid]", el).forEach((b) => (b.onclick = () => patch(`/api/earnings/${b.dataset.paid}/paid`, null, "Marked paid")));
};

/* ================================================================ CONTENT */
renderers.content = async (el) => {
  const [cs, perf, ss] = await Promise.all([api("GET", "/api/content"), api("GET", "/api/content/performance?days=7"), api("GET", "/api/social/status")]);
  const anyConn = ss.instagram.connected || ss.tiktok.connected;
  const n = (v) => (v == null ? '<span class="faint" title="Not available">n/a</span>' : nf(v));
  const vs = (x) => x.fresh ? pill("too early", "info", "Posted under 24 hours ago, so it's too early to judge")
    : x.views == null ? pill("no views", "", "Views aren't available from this connection")
    : x.vs_baseline == null ? pill("no baseline", "", "Needs at least 3 earlier posts with views")
    : x.vs_baseline >= 1.15 ? pill(`${x.vs_baseline}× usual`, "good") : x.vs_baseline <= 0.85 ? pill(`${x.vs_baseline}× usual`, "warn") : pill("≈ usual");
  const platCard = (p, label) => { const d = perf[p], conn = ss[p].connected;
    const meta = [d.followers != null ? `${nf(d.followers)} followers${d.followers_7d_change != null ? ` (${d.followers_7d_change >= 0 ? "+" : ""}${d.followers_7d_change} this week)` : ""}` : "",
      d.baseline_views != null ? `usual ${nf(d.baseline_views)} views` : ""].filter(Boolean).join(" · ");
    return card({ title: label, meta, body: !conn ? emptyState(`${label} isn't connected`, "Connect it in Settings to see views, likes and comments automatically.", `<button class="btn sm" data-go="settings">Open Settings</button>`)
      : d.recent.length ? `<div class="tablewrap"><table class="posts"><thead><tr><th>Post · last 7 days</th><th class="r">Views</th><th class="r">Likes</th><th class="r">Comments</th><th class="r" title="(likes + comments + shares) ÷ views">Engagement</th><th>vs usual</th></tr></thead><tbody>
        ${d.recent.map((x) => `<tr><td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc((x.title || "Untitled").slice(0, 80))}</a>` : esc(x.title || "Untitled")}<div class="xs faint">${humanDate(x.date)}</div></td>
          <td class="r">${n(x.views)}</td><td class="r">${n(x.likes)}</td><td class="r">${n(x.comments)}</td><td class="r">${x.engagement_pct != null ? x.engagement_pct + "%" : '<span class="faint">n/a</span>'}</td><td>${vs(x)}</td></tr>`).join("")}</tbody></table></div>
        <div class="foot">Engagement = (likes + comments + shares) ÷ views. Posts are compared with your own usual, not with other creators.</div>`
      : emptyState("No posts in the last 7 days", "New posts appear here after the next sync.") }); };
  const manual = cs.recent.filter((p) => p.platform === "linkedin" || p.platform === "x");
  el.innerHTML = `<div class="page-head"><div><h1>Content</h1><div class="sub">Daily TikTok and Instagram · ${cs.linkedin_target} LinkedIn posts a week</div></div>
    ${anyConn ? `<div class="actions"><button class="btn" id="csync">${icon("refresh", "sm")} Sync now</button></div>` : ""}</div>
  ${card({ body: `<div class="stats" style="--cols:4;margin-top:0">${stat(`${cs.daily_streak} ${cs.daily_streak === 1 ? "day" : "days"}`, "TikTok + Instagram streak")}${stat(`${cs.linkedin_this_week} / ${cs.linkedin_target}`, "LinkedIn this week")}
    ${stat(nf(perf.tiktok.followers), "TikTok followers")}${stat(nf(perf.instagram.followers), "Instagram followers")}</div>` })}
  <div style="height:20px"></div>
  <div class="stack">${platCard("tiktok", "TikTok")}${platCard("instagram", "Instagram")}
  ${card({ title: "LinkedIn and X", meta: "logged by hand", body: `
    <details class="add"><summary class="btn btn-primary sm">${icon("plus", "sm")} Log a post</summary>
      <form id="pform" class="form-card"><div class="fields">
        <label class="field"><span>Platform</span><select name="platform"><option value="linkedin">LinkedIn</option><option value="x">X</option><option value="tiktok">TikTok</option><option value="instagram">Instagram</option></select></label>
        <label class="field grow"><span>Topic (optional)</span><input name="title" placeholder="e.g. What I learned building an AI receptionist"></label>
        <button class="btn btn-primary">Log post</button></div></form></details>
    <div class="rows" style="margin-top:8px">${manual.map((p) => `<div class="row"><div class="grow"><div class="title">${esc(p.title || "Untitled")}</div><div class="meta">${p.platform === "x" ? "X" : "LinkedIn"} · ${humanDate(p.date)}</div></div></div>`).join("")
      || emptyState("Nothing logged yet", "LinkedIn and X don't sync automatically. Log posts here so your weekly goal stays honest.")}</div>` })}</div>`;
  $$("[data-go]", el).forEach((b) => (b.onclick = () => show(b.dataset.go)));
  $("#pform").onsubmit = (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); runAction("log_post", { platform: f.platform, title: f.title || null }); };
  const sb = $("#csync"); if (sb) sb.onclick = async () => { sb.disabled = true; sb.innerHTML = `${icon("refresh", "sm")} Syncing…`;
    try { const r = await api("POST", "/api/social/sync"); toast(r.ok ? "Stats updated" : (r.instagram_error || r.tiktok_error)); } catch (e) { toast(e.message); } refresh(); };
};

/* ================================================================ REVIEW */
renderers.review = async (el) => {
  const [r, wk] = await Promise.all([api("GET", "/api/review"), api("GET", "/api/review/week")]), s = r.saved || {};
  const pp = wk.posts, avg = (p) => (pp[p].avg_views != null ? `avg ${nf(pp[p].avg_views)} views` : "no view data");
  const weekCard = card({ title: "This week", meta: `${humanDate(wk.start)} – ${humanDate(wk.end)}`, body: `
    <div class="stats" style="--cols:4;margin-top:0">${stat(usd(wk.earned_usd), `earned · ${wk.earnings_count} payment(s)`)}${stat(wk.leads_added, "leads added")}${stat(wk.tasks_done, "tasks done")}${stat(`${wk.daily_reviews}/7`, "daily reviews")}</div>
    <div class="stats secondary" style="--cols:4">${stat(pp.tiktok.count, `TikTok · ${avg("tiktok")}`)}${stat(pp.instagram.count, `Instagram · ${avg("instagram")}`)}${stat(pp.linkedin.count, "LinkedIn posts")}${stat(pp.x.count, "X posts")}</div>
    ${wk.top_post ? `<div class="foot">Top post: “${esc((wk.top_post.title || "Untitled").slice(0, 80))}” on ${wk.top_post.platform === "tiktok" ? "TikTok" : "Instagram"}, ${nf(wk.top_post.views)} views.</div>` : ""}` });
  const done = r.done_today.map((t) => "• " + t.title).join("\n"), left = r.still_open.map((t) => "• " + t.title).join("\n");
  const fld = (n, label, val, ph = "") => `<label class="field"><span>${label}</span><textarea name="${n}" placeholder="${esc(ph)}">${esc(val)}</textarea></label>`;
  el.innerHTML = `<div class="page-head"><div><h1>Review</h1><div class="sub">${new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}${r.saved ? " · today's review saved" : ""}</div></div></div>
  ${weekCard}<div style="height:20px"></div>
  ${card({ title: "End of day", body: `<form id="rform"><div class="grid" style="gap:16px">
      <div class="c-6">${fld("completed", "What I completed", s.completed ?? done, "Pre-filled from tasks you ticked today")}</div>
      <div class="c-6">${fld("not_completed", "What I didn't complete", s.not_completed ?? left)}</div>
      <div class="c-6">${fld("value_created", "What created value (money, leads, content, learning)?", s.value_created ?? "")}</div>
      <div class="c-6">${fld("distractions", "What distracted me?", s.distractions ?? "")}</div>
      <div class="c-6">${fld("carry_over", "Move to tomorrow", s.carry_over ?? left)}</div>
      <div class="c-6">${fld("notes", "Notes", s.notes ?? "")}</div></div>
    <div class="actions" style="margin-top:16px;justify-content:space-between">${r.still_open.length ? `<button type="button" class="btn" id="carry">Move ${r.still_open.length} open task(s) to tomorrow</button>` : "<span></span>"}
      <button class="btn btn-primary">Save review</button></div></form>` })}`;
  $("#rform").onsubmit = async (e) => { e.preventDefault(); try { await api("POST", "/api/review", Object.fromEntries(new FormData(e.target))); toast("Review saved"); refresh(); } catch (err) { toast(err.message); } };
  const c = $("#carry"); if (c) c.onclick = async () => { c.disabled = true;
    try { for (const t of r.still_open) await api("POST", "/api/action/move_task", { task_id: t.id, new_date: addDays(1) }); toast("Moved to tomorrow"); } catch (e) { toast(e.message); } refresh(); };
};

/* ================================================================ MEMORY */
renderers.memory = async (el) => {
  const items = await api("GET", "/api/memory");
  const tone = { fact: "good", preference: "accent", assumption: "warn", plan: "info", historical: "" };
  const cats = [...new Set(items.map((m) => m.category))];
  const row = (m) => `<div class="row" data-row="${m.id}"><div class="grow"><div class="title" data-text>${esc(m.content)}</div>
      <div class="meta">${pill(esc(m.kind), tone[m.kind])} ${m.expired ? pill("expired", "warn") : ""} ${m.valid_until ? `until ${humanDate(m.valid_until)} · ` : ""}source: ${esc(m.source)}</div></div>
      <div class="actions">${m.kind === "assumption" ? `<button class="btn sm" data-confirm="${m.id}">Confirm</button>` : ""}
      <button class="btn btn-ghost icon sm" data-edit="${m.id}" aria-label="Edit">${icon("edit", "sm")}</button>
      <button class="btn btn-ghost icon sm btn-danger" data-del="${m.id}" aria-label="Delete">${icon("trash", "sm")}</button></div></div>`;
  el.innerHTML = `<div class="page-head"><div><h1>What Moyo knows about you</h1><div class="sub">Each item shows whether it's a fact, a preference or an assumption, and where it came from. Edit or delete anything.</div></div></div>
  ${card({ body: `<details class="add"><summary class="btn btn-primary sm">${icon("plus", "sm")} Add something to remember</summary>
    <form id="mform" class="form-card"><div class="fields">
      <label class="field grow"><span>What should Moyo remember?</span><input name="content_text" required></label>
      <label class="field"><span>Type</span><select name="kind"><option value="fact">Fact</option><option value="preference">Preference</option><option value="plan">Temporary plan</option></select></label>
      <label class="field"><span>Expires (plans only)</span><input type="date" name="valid_until"></label>
      <label class="field"><span>Category</span><input name="category" value="general" style="width:140px"></label>
      <button class="btn btn-primary">Remember</button></div></form></details>` })}
  <div style="height:20px"></div>
  <div class="stack">${cats.map((c) => card({ title: esc(c[0].toUpperCase() + c.slice(1)), meta: `${items.filter((m) => m.category === c).length}`, body: `<div class="rows">${items.filter((m) => m.category === c).map(row).join("")}</div>` })).join("")
    || card({ body: emptyState("Nothing stored yet", "Tell Moyo things like “remember that I prefer morning deep work”.") })}</div>`;
  $("#mform").onsubmit = (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target));
    runAction("remember", { content_text: f.content_text, kind: f.kind, category: f.category || "general", valid_until: f.valid_until || null }); };
  $$("[data-edit]", el).forEach((b) => (b.onclick = () => {
    const m = items.find((x) => x.id === +b.dataset.edit), t = $(`[data-row="${m.id}"] [data-text]`, el);
    t.innerHTML = `<div class="fields"><label class="field grow"><span class="sr-only">Edit memory</span><input value="${esc(m.content)}" data-input></label>
      <button class="btn btn-primary sm" data-save>Save</button><button class="btn sm" data-cancel>Cancel</button></div>`;
    const inp = $("[data-input]", t); inp.focus(); inp.select();
    $("[data-cancel]", t).onclick = refresh;
    const save = async () => { const v = inp.value.trim(); if (!v || v === m.content) return refresh(); try { await api("PATCH", "/api/memory/" + m.id, { content: v }); toast("Memory updated"); } catch (e) { toast(e.message); } refresh(); };
    $("[data-save]", t).onclick = save; inp.onkeydown = (e) => { if (e.key === "Enter") save(); if (e.key === "Escape") refresh(); };
  }));
  $$("[data-del]", el).forEach((b) => (b.onclick = async () => { const m = items.find((x) => x.id === +b.dataset.del);
    if (!confirm(`Delete this permanently?\n\n“${m.content}”`)) return; try { await api("DELETE", "/api/memory/" + m.id); toast("Deleted"); } catch (e) { toast(e.message); } refresh(); }));
  $$("[data-confirm]", el).forEach((b) => (b.onclick = async () => { try { await api("PATCH", "/api/memory/" + b.dataset.confirm, { kind: "fact", confirmed: true }); toast("Confirmed as fact"); } catch (e) { toast(e.message); } refresh(); }));
};

/* ---------- clap to wake ---------- */
const CLAP_STATE = { listening: ["Listening", "good"], off: ["Off", ""], quiet_hours: ["Paused for quiet hours", ""],
  mic_error: ["Microphone unavailable", "warn"] };
async function renderClapCard() {
  const box = $("#clapcard"); if (!box) return;
  let st, quietFrom;
  try { const [a, s] = await Promise.all([api("GET", "/api/wake/status"), api("GET", "/api/settings")]); st = a; quietFrom = s.notifications.quiet_start; }
  catch (e) { box.innerHTML = `<div class="card-head"><h2>Clap to wake</h2></div>${errorState("Couldn't load clap-to-wake status: " + e.message)}`; $("[data-retry]", box).onclick = renderClapCard; return; }
  const [label, tone] = CLAP_STATE[st.state] || [st.state, ""];
  box.innerHTML = `<div class="card-head"><h2>Clap to wake</h2><span class="meta">${pill(label, tone)}</span><div class="end"><button class="btn sm" id="clap-test">${icon("play", "sm")} Try the wake orb</button></div></div>
    <div class="rows">
      <div class="row"><div class="grow"><div class="title"><label for="clap-on">${st.mode === "clap_phrase" ? `Wake Moyo: clap, then say “${esc(st.phrase)}”` : "Wake Moyo with a double clap"}</label></div>
        <div class="meta">${st.mode === "clap_phrase" ? `A clap makes Moyo listen for a few seconds; your phrase wakes it.` : "Clap twice."} A small Moyo orb appears, gives you a short brief, then asks if you want the full dashboard.</div></div><input type="checkbox" id="clap-on" ${st.enabled ? "checked" : ""}></div>
      <div class="row"><div class="grow"><div class="title"><label for="clap-quiet">Also listen during quiet hours</label></div>
        <div class="meta">Off: the microphone is released from ${esc(quietFrom)} until your quiet hours end.</div></div><input type="checkbox" id="clap-quiet" ${st.listen_in_quiet_hours ? "checked" : ""}></div></div>
    ${st.mode === "clap_phrase" && !st.phrase_model ? `<div class="banner warn" style="margin-top:12px">${icon("alert")}<div class="grow">The offline speech model is missing from <code>models\vosk-model-small-en-us-0.15</code>.</div></div>` : ""}
    ${st.mode === "clap_phrase" || st.calibrated ? "" : `<div class="banner info" style="margin-top:12px">${icon("alert")}<div class="grow"><strong>Tune it to your claps first (about 2 minutes).</strong> In a terminal in the Moyo folder run <code>.venv\\Scripts\\python -m moyo.clap</code> and follow the prompts. Until then it uses general settings and may miss claps.</div></div>`}
    ${st.error ? `<div class="foot" style="color:var(--warn)">Microphone problem: ${esc(st.error)}</div>` : ""}
    <div class="foot">Privacy: while this is on, Moyo keeps the microphone open (Windows shows its mic icon) and checks loudness 10 ms at a time on this laptop. ${st.mode === "clap_phrase" ? "After a clap, an offline speech recogniser listens for your phrase only. " : ""}Nothing is recorded, saved or sent anywhere. ${st.last_wake ? `Last woken ${esc(st.last_wake.replace("T", " ").slice(0, 16))}.` : ""}</div>`;
  const save = async (body) => { try { await api("PUT", "/api/settings/clap", body); toast("Saved"); } catch (e) { toast(e.message); } renderClapCard(); updateMicIndicator(); };
  $("#clap-on").onchange = (e) => save({ enabled: e.target.checked });
  $("#clap-quiet").onchange = (e) => save({ listen_in_quiet_hours: e.target.checked });
  $("#clap-test").onclick = async () => { try { const r = await api("POST", "/api/wake/test"); toast(r.opened ? "Look at the top-right of your screen." : "The orb is already open."); } catch (e) { toast(e.message); } };
}
async function updateMicIndicator() {
  const el = $("#mic-indicator"); if (!el) return;
  try { const st = await api("GET", "/api/wake/status"); el.hidden = !st.listening; } catch { el.hidden = true; }
}

/* ================================================================ SETTINGS */
renderers.settings = async (el) => {
  const [s, log, wsl] = await Promise.all([api("GET", "/api/settings"), api("GET", "/api/audit?limit=80"), api("GET", "/api/workspaces")]);
  const sc = s.schedule, rt = s.routine, nt = s.notifications;
  const toggleRow = (id, title, meta, on) => `<div class="row"><div class="grow"><div class="title"><label for="${id}">${title}</label></div><div class="meta">${meta}</div></div><input type="checkbox" id="${id}" ${on ? "checked" : ""}></div>`;
  const section = (id, title, lead, body) => `<section class="block" id="set-${id}"><h2>${title}</h2>${lead ? `<p class="lead">${lead}</p>` : ""}${body}</section>`;
  el.innerHTML = `<div class="page-head"><div><h1>Settings</h1><div class="sub">Your routine, money rules, connected accounts, voice and privacy.</div></div></div>
  <nav class="toc" aria-label="Settings sections">${[["schedule", "Daily schedule"], ["routine", "Morning & reminders"], ["money", "Money"], ["accounts", "Accounts"], ["voice", "Voice"], ["privacy", "AI & privacy"], ["activity", "Activity log"]]
    .map(([id, l]) => `<a href="#set-${id}" data-toc="${id}">${l}</a>`).join("")}</nav>
  ${section("schedule", "Daily schedule", `Fixed commitments block time in your plan. ${sc.confirmed ? pill("confirmed", "good") : pill("still assumed", "warn")}`, card({ body: `<form id="sform">
      <div class="fields">
        <label class="field"><span>Day starts</span><input type="time" name="day_start" value="${esc(sc.day_start)}"></label>
        <label class="field"><span>Day ends</span><input type="time" name="day_end" value="${esc(sc.day_end)}"></label>
        <label class="field"><span>Focus block (minutes)</span><input type="number" name="focus_block_min" value="${sc.focus_block_min}" style="width:150px"></label>
        <label class="field"><span>Free-time buffer (%)</span><input type="number" name="buffer_pct" value="${sc.buffer_pct}" style="width:150px"></label></div>
      <div class="group-label" style="margin-top:20px">Fixed commitments</div>
      <div id="fixed">${sc.fixed.map((f, i) => `<div class="fields" style="margin:8px 0">
        <label class="field grow"><span class="sr-only">Name</span><input value="${esc(f.title)}" data-k="title" data-i="${i}" aria-label="Commitment name"></label>
        <label class="field"><span class="sr-only">Start</span><input type="time" value="${esc(f.start)}" data-k="start" data-i="${i}" aria-label="Start time"></label>
        <label class="field"><span class="sr-only">End</span><input type="time" value="${esc(f.end)}" data-k="end" data-i="${i}" aria-label="End time"></label>
        <label class="field"><span class="sr-only">Days</span><input value="${esc(f.days)}" data-k="days" data-i="${i}" style="width:180px" aria-label="Days, e.g. MO,TU,WE or * for every day" title="MO,TU,WE,TH,FR,SA,SU or * for every day"></label>
        <button type="button" class="btn btn-ghost icon sm btn-danger" data-rm="${i}" aria-label="Remove ${esc(f.title)}">${icon("x", "sm")}</button></div>`).join("")}</div>
      <div class="actions" style="margin-top:12px;justify-content:space-between"><button type="button" class="btn" id="addfixed">${icon("plus", "sm")} Add commitment</button>
        <button class="btn btn-primary">Save schedule</button></div></form>` }))}
  ${section("routine", "Morning & reminders", "How your day starts, and when Moyo should tap you on the shoulder.", `<div class="stack">
    ${card({ title: "Start my day", meta: rt.last_run ? `last run ${humanDate(rt.last_run)}` : "not run yet", body: `
      <div class="fields"><label class="field"><span>Workspace to open</span><select id="rt-ws"><option value="">Don't open apps</option>${wsl.map((w) => `<option value="${esc(w.key)}" ${w.key === rt.workspace ? "selected" : ""}>${esc(w.label)}</option>`).join("")}</select></label>
        <label class="field"><span>Morning prompt after</span><input type="time" id="rt-after" value="${esc(rt.prompt_after)}"></label></div>
      <div class="rows" style="margin-top:8px">
        ${toggleRow("rt-music", "Start the workspace's music", "Opens its Spotify playlist and presses play.", rt.music)}
        ${toggleRow("rt-read", "Read the briefing aloud", "In your chosen voice, including today's coaching.", rt.read_briefing)}
        ${toggleRow("rt-prompt", "Morning notification", "Once a day, a pop-up asks if you're ready to start. Clicking it runs the routine.", rt.morning_prompt)}</div>
      <div class="foot">Shortcuts: <kbd>Ctrl</kbd> <kbd>Alt</kbd> <kbd>S</kbd> starts your day (after running <code>scripts\\install-shortcut.ps1</code> again), or type “good morning”.</div>` })}
    ${card({ title: "Reminders", end: `<button class="btn sm" id="nt-test">${icon("bell", "sm")} Send a test</button>`, body: `
      <div class="rows">
        ${toggleRow("nt-on", "Reminders", "Overdue follow-ups, posting reminders, meetings, emails from leads, end-of-day and weekly reviews.", nt.enabled)}
        ${toggleRow("nt-toast", "Desktop pop-ups", "For important and urgent reminders. Everything else waits in the bell.", nt.toasts)}</div>
      <div class="fields" style="margin-top:10px">
        <label class="field"><span>Quiet hours from</span><input type="time" id="nt-qs" value="${esc(nt.quiet_start)}"></label>
        <label class="field"><span>until</span><input type="time" id="nt-qe" value="${esc(nt.quiet_end)}"></label>
        <label class="field"><span>Posting reminder at</span><input type="time" id="nt-ct" value="${esc(nt.content_reminder_time)}"></label>
        <label class="field"><span>Meeting heads-up (minutes)</span><input type="number" id="nt-ev" min="0" max="120" value="${nt.event_lead_minutes}" style="width:180px"></label></div>
      <div class="foot">During quiet hours only urgent items pop up; the rest wait in the bell.</div>` })}
    ${card({ id: "clapcard", title: "Clap to wake", body: skeleton(2) })}</div>`)}
  ${section("money", "Money", "Naira per US dollar for new entries. Each entry keeps the rate it was logged with, and Moyo never looks rates up by itself.", card({ body: `<form id="rateform"><div class="fields">
      <label class="field"><span>₦ per $1</span><input type="number" name="rate" min="100" step="any" value="${esc(s.ngn_per_usd ?? "")}" placeholder="e.g. 1500" required style="width:170px"></label>
      <button class="btn btn-primary">Review & save</button></div></form>` }))}
  ${section("accounts", "Accounts", "Read-only connections. Moyo can't send, post or change anything in these accounts.", `<div class="stack">${card({ id: "googlecard", body: skeleton(2) })}${card({ id: "socialcard", body: skeleton(3) })}</div>`)}
  ${section("voice", "Voice", "Press play to hear the same sentence in each voice, then choose your favourite. If it's ever unavailable, Moyo falls back to the next natural voice.", card({ id: "voicecard", body: skeleton(4) }))}
  ${section("privacy", "AI & privacy", "", card({ body: `<div class="rows">
      <div class="row"><div class="grow"><div class="title">Use free cloud AI for requests Moyo can't handle on this laptop</div><div class="meta">Gemini (then Groq) free tiers. Direct commands never leave this laptop.</div></div><input type="checkbox" id="cloudon" ${s.cloud.enabled ? "checked" : ""} aria-label="Use cloud AI"></div>
      <div class="row"><div class="grow"><div class="title">Hide client names and amounts from cloud AI</div><div class="meta">Recommended. They're replaced with placeholders before sending and restored here.</div></div><input type="checkbox" id="redact" ${s.cloud.redact_clients_and_amounts ? "checked" : ""} aria-label="Hide client names and amounts"></div></div>` }))}
  ${section("activity", "Activity log", "Everything Moyo has done, newest first.", card({ body: `<details class="more"><summary>Show the last ${log.length} actions</summary><div class="tablewrap" style="margin-top:10px"><table><thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Tier</th><th>Result</th></tr></thead><tbody>
      ${log.map((a) => `<tr><td class="xs">${esc(a.ts.replace("T", " ").slice(0, 16))}</td><td>${esc(a.actor)}</td><td>${esc(a.action)}</td><td>${pill(esc(a.tier), a.tier === "confirm" ? "accent" : a.tier === "prohibited" ? "warn" : "")}</td><td class="xs muted" title="${esc(a.detail || "")}">${esc(a.result)}</td></tr>`).join("")}</tbody></table></div></details>` }))}`;
  $$("[data-toc]", el).forEach((a) => (a.onclick = (e) => { e.preventDefault(); $("#set-" + a.dataset.toc).scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }));
  renderGoogleCard(); renderSocialCard(); renderVoicePicker(); renderClapCard();
  const saveRt = async (body) => { try { await api("PUT", "/api/settings/routine", body); toast("Saved"); } catch (e) { toast(e.message); } };
  $("#rt-ws").onchange = (e) => saveRt({ workspace: e.target.value || null });
  $("#rt-after").onchange = (e) => saveRt({ prompt_after: e.target.value });
  $("#rt-music").onchange = (e) => saveRt({ music: e.target.checked });
  $("#rt-read").onchange = (e) => saveRt({ read_briefing: e.target.checked });
  $("#rt-prompt").onchange = (e) => saveRt({ morning_prompt: e.target.checked });
  const saveNt = async (body) => { try { await api("PUT", "/api/settings/notifications", body); toast("Saved"); } catch (e) { toast(e.message); } };
  $("#nt-on").onchange = (e) => saveNt({ enabled: e.target.checked });
  $("#nt-toast").onchange = (e) => saveNt({ toasts: e.target.checked });
  $("#nt-qs").onchange = (e) => saveNt({ quiet_start: e.target.value });
  $("#nt-qe").onchange = (e) => saveNt({ quiet_end: e.target.value });
  $("#nt-ct").onchange = (e) => saveNt({ content_reminder_time: e.target.value });
  $("#nt-ev").onchange = (e) => saveNt({ event_lead_minutes: +e.target.value });
  $("#nt-test").onclick = async () => { try { const r = await api("POST", "/api/notifications/test"); toast(r.ok ? "Test sent. Look at the bottom-right of your screen." : "Couldn't show a desktop notification"); } catch (e) { toast(e.message); } };
  $("#rateform").onsubmit = (e) => { e.preventDefault(); runAction("set_rate", { ngn_per_usd: +new FormData(e.target).get("rate") }); };
  const saveCloud = async (body) => { try { await api("PUT", "/api/settings/cloud", body); toast("Saved"); } catch (e) { toast(e.message); } };
  $("#cloudon").onchange = (e) => saveCloud({ enabled: e.target.checked });
  $("#redact").onchange = (e) => saveCloud({ redact_clients_and_amounts: e.target.checked });
  const fixed = sc.fixed.map((f) => ({ ...f }));
  $$("#fixed input", el).forEach((i) => (i.oninput = () => (fixed[+i.dataset.i][i.dataset.k] = i.value)));
  const putFixed = async () => { try { await api("PUT", "/api/settings/schedule", { fixed }); } catch (e) { toast(e.message); } refresh(); };
  $$("[data-rm]", el).forEach((b) => (b.onclick = () => { fixed.splice(+b.dataset.rm, 1); putFixed(); }));
  $("#addfixed").onclick = () => { fixed.push({ title: "New commitment", start: "12:00", end: "13:00", days: "*" }); putFixed(); };
  $("#sform").onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target));
    try { await api("PUT", "/api/settings/schedule", { day_start: f.day_start, day_end: f.day_end, focus_block_min: +f.focus_block_min, buffer_pct: +f.buffer_pct, fixed, confirmed: true }); toast("Schedule saved"); refresh(); }
    catch (err) { toast(err.message); } };
};

async function renderGoogleCard() {
  const box = $("#googlecard"); if (!box) return;
  let s; try { s = await api("GET", "/api/google/status"); } catch (e) { box.innerHTML = errorState(e.message); box.querySelector("[data-retry]").onclick = renderGoogleCard; return; }
  const head = `<div class="card-head"><h2>${icon("mail", "sm")} Gmail & Google Calendar</h2><div class="end">${s.connected ? pill("connected", "good") : pill("not connected")}</div></div>`;
  box.innerHTML = head + (s.connected
    ? `<div class="muted">Connected${s.account ? ` as <b>${esc(s.account)}</b>` : ""} · ${s.last_sync ? "last sync " + esc(s.last_sync.slice(11, 16)) : "not synced yet"} · syncs every ${s.sync_minutes} minutes</div>
       ${s.last_sync_error ? `<div style="margin-top:10px">${banner(esc(s.last_sync_error), "", "warn")}</div>` : ""}
       <div class="actions" style="margin-top:14px"><button class="btn" id="gsync">${icon("refresh", "sm")} Sync now</button><button class="btn btn-danger" id="gdisc">Disconnect</button></div>
       <div class="foot">Reads calendar events and email senders and subjects only. Guide: <code>docs/GOOGLE_SETUP.md</code></div>`
    : `<div class="rows">
        <div class="row"><span class="pill ${s.has_client ? "good" : ""}">1</span><div class="grow"><div class="title">Upload your OAuth client file</div><div class="meta">From your free Google Cloud app (see <code>docs/GOOGLE_SETUP.md</code>).</div></div><input type="file" id="gfile" accept=".json,application/json" aria-label="Google OAuth client file"></div>
        <div class="row"><span class="pill">2</span><div class="grow"><div class="title">Sign in with Google</div><div class="meta">Allow Gmail (read) and Calendar (read).</div></div><button class="btn btn-primary" id="gconn" ${s.has_client ? "" : "disabled"}>${s.connecting ? "Waiting for Google…" : "Connect Google"}</button></div></div>
       ${s.error ? banner(esc(s.error), "", "warn") : ""}`);
  const f = $("#gfile"); if (f) f.onchange = async () => { try { await api("POST", "/api/google/client", JSON.parse(await f.files[0].text())); toast("Client file saved securely"); } catch (e) { toast(e.message); } renderGoogleCard(); };
  const c = $("#gconn"); if (c) c.onclick = async () => { try { await api("POST", "/api/google/connect"); } catch (e) { return toast(e.message); } toast("Finish signing in in the browser tab that opened");
    const poll = setInterval(async () => { const st = await api("GET", "/api/google/status"); if (!st.connecting) { clearInterval(poll); renderGoogleCard(); toast(st.connected ? "Google connected" : (st.error || "Not connected")); } }, 2000); renderGoogleCard(); };
  const sy = $("#gsync"); if (sy) sy.onclick = async () => { sy.disabled = true; try { const r = await api("POST", "/api/google/sync"); toast(r.ok ? `Synced ${r.emails} emails, ${r.events} events` : r.error); } catch (e) { toast(e.message); } renderGoogleCard(); };
  const d = $("#gdisc"); if (d) d.onclick = async () => { if (!confirm("Disconnect Google? Moyo's access is revoked and its local copies of email subjects and calendar events are deleted.")) return;
    try { await api("POST", "/api/google/disconnect"); toast("Disconnected"); } catch (e) { toast(e.message); } renderGoogleCard(); };
}

async function renderSocialCard() {
  const box = $("#socialcard"); if (!box) return;
  let s; try { s = await api("GET", "/api/social/status"); } catch (e) { box.innerHTML = errorState(e.message); box.querySelector("[data-retry]").onclick = renderSocialCard; return; }
  const ig = s.instagram, tt = s.tiktok;
  box.innerHTML = `<div class="card-head"><h2>${icon("content", "sm")} Instagram & TikTok</h2><div class="end">${(ig.connected || tt.connected) ? `<button class="btn sm" id="ssync">${icon("refresh", "sm")} Sync now</button>` : ""}</div></div>
    ${s.last_sync_error ? banner(esc(s.last_sync_error), "", "warn") : ""}
    <div class="grid" style="gap:16px">
      <div class="c-6">${card({ cls: "inset", title: "Instagram", end: ig.connected ? pill("connected", "good") : pill("not connected"), body: ig.connected
        ? `<div>@${esc(ig.account || "")}</div><div class="meta muted small">${ig.auto_renews ? `Token renews automatically (${ig.token_days_left} days left)` : `Token valid about ${ig.token_days_left} more days. Generate a new one before then.`}</div>
           ${ig.insights_error ? `<div style="margin-top:10px">${banner(esc(ig.insights_error), "", "warn")}</div>` : ""}
           <div class="actions" style="margin-top:12px"><button class="btn sm btn-danger" data-sdisc="instagram">Disconnect</button></div>`
        : `<form id="igform"><div class="fields">
             <label class="field grow"><span>Access token</span><input name="token" required autocomplete="off" type="password"></label>
             <label class="field grow"><span>Instagram account ID</span><input name="ig_id" inputmode="numeric" autocomplete="off" placeholder="1784…"></label></div>
             <div class="actions" style="margin-top:12px;justify-content:space-between"><span class="xs muted">Both are in Meta's “Token generated” box.</span><button class="btn btn-primary">Connect</button></div></form>` })}</div>
      <div class="c-6">${card({ cls: "inset", title: "TikTok", end: tt.connected ? pill("connected", "good") : pill("not connected"), body: tt.connected
        ? `<div>${esc(tt.account || "Connected")}</div><div class="actions" style="margin-top:12px"><button class="btn sm btn-danger" data-sdisc="tiktok">Disconnect</button></div>`
        : tt.has_client ? `<div class="small muted">The redirect URI in your TikTok app must be exactly <code>${esc(tt.redirect_uri)}</code></div>
            <div class="actions" style="margin-top:12px"><button class="btn btn-primary" id="ttconn">${tt.connecting ? "Waiting for TikTok…" : "Connect TikTok"}</button><button class="btn" id="ttreset">Change keys</button></div>`
        : `<form id="ttform"><div class="fields"><label class="field grow"><span>Client key</span><input name="client_key" required autocomplete="off"></label>
             <label class="field grow"><span>Client secret</span><input name="client_secret" type="password" required autocomplete="off"></label></div>
             <div class="actions" style="margin-top:12px;justify-content:flex-end"><button class="btn btn-primary">Save keys</button></div></form>` }
        )}${tt.error ? banner(esc(tt.error), "", "warn") : ""}</div>
    </div>
    <div class="foot">Official APIs, read-only. Stats sync every 3 hours${s.last_sync ? ` · last sync ${esc(s.last_sync.slice(11, 16))}` : ""}. Guide: <code>docs/SOCIAL_SETUP.md</code></div>`;
  const igf = $("#igform"); if (igf) igf.onsubmit = async (e) => { e.preventDefault(); const b = igf.querySelector("button.btn-primary"); b.disabled = true; b.textContent = "Checking…";
    try { const fd = new FormData(igf); const r = await api("POST", "/api/social/instagram/token", { token: fd.get("token"), ig_id: (fd.get("ig_id") || "").replace(/\D/g, "") || null }); toast(`Instagram connected: @${r.username}`); renderSocialCard(); }
    catch (err) { toast(err.message); b.disabled = false; b.textContent = "Connect"; } };
  const idIn = igf?.querySelector("[name=ig_id]"); if (idIn) idIn.oninput = () => { if (/[^\d\s]/.test(idIn.value)) toast("Use the long number under your username (e.g. 1784…), not the @name"); };
  const ttf = $("#ttform"); if (ttf) ttf.onsubmit = async (e) => { e.preventDefault(); try { await api("POST", "/api/social/tiktok/client", Object.fromEntries(new FormData(ttf))); toast("TikTok keys saved securely"); } catch (err) { toast(err.message); } renderSocialCard(); };
  const ttc = $("#ttconn"); if (ttc) ttc.onclick = async () => { try { await api("POST", "/api/social/tiktok/connect"); } catch (e) { return toast(e.message); } toast("Approve Moyo in the TikTok tab that opened");
    const poll = setInterval(async () => { const st = await api("GET", "/api/social/status"); if (!st.tiktok.connecting) { clearInterval(poll); toast(st.tiktok.connected ? "TikTok connected" : (st.tiktok.error || "Not connected")); renderSocialCard(); } }, 2000); renderSocialCard(); };
  const ttr = $("#ttreset"); if (ttr) ttr.onclick = () => { ttr.parentElement.outerHTML = `<form id="ttform2" style="margin-top:12px"><div class="fields"><label class="field grow"><span>Client key</span><input name="client_key" required></label><label class="field grow"><span>Client secret</span><input name="client_secret" type="password" required></label><button class="btn btn-primary">Save</button></div></form>`;
    $("#ttform2").onsubmit = async (e) => { e.preventDefault(); try { await api("POST", "/api/social/tiktok/client", Object.fromEntries(new FormData(e.target))); toast("Saved"); } catch (err) { toast(err.message); } renderSocialCard(); }; };
  $$("[data-sdisc]", box).forEach((b) => (b.onclick = async () => { if (!confirm(`Disconnect ${b.dataset.sdisc}? Your post history stays; Moyo just stops syncing.`)) return;
    try { await api("POST", `/api/social/${b.dataset.sdisc}/disconnect`); toast("Disconnected"); } catch (e) { toast(e.message); } renderSocialCard(); }));
  const ss = $("#ssync"); if (ss) ss.onclick = async () => { ss.disabled = true; try { const r = await api("POST", "/api/social/sync"); toast(r.ok ? `Synced ${r.instagram ?? 0} Instagram and ${r.tiktok ?? 0} TikTok posts` : (r.instagram_error || r.tiktok_error)); } catch (e) { toast(e.message); } renderSocialCard(); };
}

async function renderVoicePicker() {
  const box = $("#voicecard"); if (!box) return;
  let v; try { v = await api("GET", "/api/voices"); } catch (e) { box.innerHTML = errorState(e.message); box.querySelector("[data-retry]").onclick = renderVoicePicker; return; }
  const cur = v.current, browserVoices = speechSynthesis.getVoices().filter((x) => x.lang.startsWith("en"));
  const engines = { ...v.engines, browser: { ...v.engines.browser, voices: browserVoices.map((x) => ({ id: x.name, label: x.name })) } };
  const isCur = (e, id) => cur.engine === e && cur.voice === id;
  for (const x of engines.gemini?.voices || []) x.label = `${x.id} · ${x.label}`;  // name + mood, e.g. "Sulafat · Warm"
  const curLabel = engines[cur.engine]?.voices.find((x) => x.id === cur.voice)?.label || cur.voice;
  const total = Object.values(engines).reduce((n, e) => n + e.voices.length, 0);
  box.innerHTML = `<div class="row" style="padding-top:0"><div class="grow"><div class="title">${esc(curLabel)}</div><div class="meta">${esc(engines[cur.engine]?.label || cur.engine)} · your briefing voice${cur.chosen ? "" : " (default, not chosen yet)"}</div></div>
      <button class="btn icon sm" data-play="${esc(cur.engine)}|${esc(cur.voice)}" aria-label="Preview your voice">${icon("play", "sm")}</button></div>
    <details class="more" style="margin-top:8px"><summary>Choose a different voice (${total} available)</summary><div style="margin-top:12px">
    <div class="fields" style="margin-bottom:16px">
      <label class="field"><span>Speed <output id="vspeedv">${cur.speed}×</output></span><input type="range" id="vspeed" min="0.8" max="1.25" step="0.05" value="${cur.speed}" style="width:200px"></label>
      <label class="field grow"><span>Sample sentence</span><input id="vsample" value="${esc(v.sample)}"></label></div>
    <div class="voice-grid">${Object.entries(engines).map(([e, info]) => card({ cls: "inset", title: esc(info.label), body: `<div class="xs muted" style="margin:-8px 0 8px">${esc(info.note)}</div><div class="rows">${info.voices.map((x) => `<div class="row">
        <button class="btn icon sm" data-play="${esc(e)}|${esc(x.id)}" aria-label="Preview ${esc(x.label)}">${icon("play", "sm")}</button><div class="grow">${esc(x.label)}</div>
        ${isCur(e, x.id) ? pill(`${icon("check", "sm")} your voice`, "good") : `<button class="btn sm" data-use="${esc(e)}|${esc(x.id)}">Use</button>`}</div>`).join("") || emptyState("No voices found")}</div>` })).join("")}</div>
    </div></details>`;
  const det = box.querySelector("details"); try { if (sessionStorage.getItem("moyo.voiceOpen")) det.open = true; } catch {}
  det.ontoggle = () => { try { det.open ? sessionStorage.setItem("moyo.voiceOpen", "1") : sessionStorage.removeItem("moyo.voiceOpen"); } catch {} };
  $("#vspeed").oninput = (ev) => ($("#vspeedv").textContent = ev.target.value + "×");
  $("#vspeed").onchange = async (ev) => { try { await api("PUT", "/api/settings/voice", { speed: +ev.target.value }); toast("Speed saved"); } catch (e) { toast(e.message); } };
  $$("[data-play]", box).forEach((b) => (b.onclick = async () => {
    const [e, id] = b.dataset.play.split("|"), text = $("#vsample").value, speed = +$("#vspeed").value;
    if (!Speaker.stopped && b.dataset.playing) return Speaker.stop();
    $$("[data-play]", box).forEach((x) => { x.innerHTML = icon("play", "sm"); delete x.dataset.playing; });
    b.innerHTML = icon("refresh", "sm");
    Speaker.onchange = (on) => { b.innerHTML = icon(on ? "stop" : "play", "sm"); if (on) b.dataset.playing = "1"; else delete b.dataset.playing; };
    try { if (e === "browser") await Speaker.speak(text, { pref: { engine: "browser", voice: id, speed } }); else await Speaker.speak(text, { engine: e, voice: id, speed }); }
    catch (err) { b.innerHTML = icon("play", "sm"); toast(`${id}: ${err.message}`); }
  }));
  $$("[data-use]", box).forEach((b) => (b.onclick = async () => { const [e, id] = b.dataset.use.split("|");
    try { await api("PUT", "/api/settings/voice", { engine: e, voice: id, speed: +$("#vspeed").value }); toast("Voice saved"); } catch (err) { toast(err.message); } renderVoicePicker(); }));
}
speechSynthesis.onvoiceschanged = () => { if (current === "settings") renderVoicePicker(); };

/* ---------- start ---------- */
let start = (location.hash || "").slice(1);
if (start === "start-day") { history.replaceState(null, "", "#today"); startDay(); }  // from the shortcut or morning notification
else {
  if (!renderers[start]) { try { start = localStorage.getItem("moyo.view") || "today"; } catch { start = "today"; } }
  show(start);
}
window.addEventListener("hashchange", () => { const h = location.hash.slice(1); if (h === "start-day") { history.replaceState(null, "", "#today"); startDay(); } else if (renderers[h] && h !== current) show(h); });
