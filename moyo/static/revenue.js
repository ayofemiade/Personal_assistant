/* Revenue Toolkit, Phase 1 (docs/revenue). Uses app.js helpers: $, $$, esc, icon, api, card, pill, emptyState,
   skeleton, errorState, toast, usd, money, humanDate, localISO, addDays, renderers, refresh, renderMoneyTab.
   Moyo never sends messages: drafts open in YOUR WhatsApp/Gmail, you press send, then tell Moyo it's sent. */

const REV_SERVICES = [["website", "Website"], ["web_app", "Software / web app"], ["ai_agent", "AI agent / voice"], ["automation", "Automation"],
  ["integration", "API integration"], ["consulting", "Consulting"], ["maintenance", "Maintenance"], ["hosting", "Hosting & domain"], ["other", "Other"]];
const REV_OPEN = ["new", "contacted", "engaged", "discovery", "proposal", "negotiation"];
let revTab = (() => { try { return localStorage.getItem("moyo.revTab") || "today"; } catch { return "today"; } })();
const dueText = (iso) => { if (!iso) return ""; const days = Math.round((new Date(iso + "T00:00") - new Date(localISO() + "T00:00")) / 864e5);
  return days < 0 ? `${-days} day${days < -1 ? "s" : ""} overdue` : days === 0 ? "today" : humanDate(iso); };
const valueText = (d) => (d.value != null ? money(d.value, d.currency) : "");
const titleText = (name, title) => { const t = String(title || ""); return t.startsWith(name + " · ") ? t.slice(name.length + 3) : t === name ? "" : t; };

function sheet(label, html) {
  const dlg = document.createElement("dialog"); dlg.className = "sheet"; dlg.setAttribute("aria-label", label);
  dlg.innerHTML = `<button class="btn btn-ghost icon sm x" aria-label="Close">${icon("x", "sm")}</button>${html}`;
  document.body.appendChild(dlg); dlg.showModal();
  const opener = document.activeElement;
  dlg.addEventListener("close", () => { dlg.remove(); opener?.focus?.(); });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.querySelector(".x").onclick = () => dlg.close();
  return dlg;
}
const setBody = (dlg, html) => { dlg.innerHTML = `<button class="btn btn-ghost icon sm x" aria-label="Close">${icon("x", "sm")}</button>${html}`; dlg.querySelector(".x").onclick = () => dlg.close(); };

/* ================================================================ page */
renderers.money = async (el) => {
  const ov = await api("GET", "/api/rev/overview"), st = ov.stats, ch = st.challenge;
  const need = st.deals_needed_at_avg ? ` · about <b>${st.deals_needed_at_avg} deals</b> to go at your average invoice (${money(st.avg_past_invoice_ngn, "NGN")})` : "";
  el.innerHTML = `<div class="page-head"><div><h1>Revenue</h1>
      <div class="sub">${usd(ch.earned_usd)} ${esc(ch.progress_word)} of ${usd(ch.target_usd)} · ${ch.days_left} days left${need}</div></div></div>
    <form class="capture" id="capform" autocomplete="off">
      <label class="sr-only" for="capin">Tell Moyo about a lead</label>
      <input id="capin" placeholder="Tell Moyo about a lead: “Met Tunde from Kemi Stores, wants a store, around 400k, follow up Monday”" maxlength="2000">
      <button class="btn btn-primary">${icon("plus", "sm")} Add lead</button></form>
    <div id="capcard"></div>
    <div class="seg" role="tablist" aria-label="Revenue sections">${[["today", `Today${ov.today.length ? ` · ${ov.today.length}` : ""}`], ["pipeline", `Pipeline · ${st.open}`], ["money", "Money"]]
      .map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${revTab === k}">${l}</button>`).join("")}</div>
    <div id="revbody" role="tabpanel"></div>`;
  $("#capform").onsubmit = (e) => { e.preventDefault(); previewCapture($("#capin").value.trim()); };
  $$("[data-tab]", el).forEach((b) => (b.onclick = () => { revTab = b.dataset.tab; try { localStorage.setItem("moyo.revTab", revTab); } catch {}
    $$("[data-tab]", el).forEach((x) => x.setAttribute("aria-selected", x === b)); renderRevTab(ov); }));
  renderRevTab(ov);
};

function renderRevTab(ov) {
  const box = $("#revbody");
  if (revTab === "pipeline") return renderPipeline(box, ov);
  if (revTab === "money") { box.innerHTML = skeleton(4); return renderMoneyTab(box).catch((e) => (box.innerHTML = errorState(e.message))); }
  return renderToday(box, ov);
}

/* ================================================================ capture */
async function previewCapture(text) {
  const box = $("#capcard"); if (!text) return $("#capin").focus();
  box.innerHTML = card({ body: skeleton(3) });
  let f; try { f = await api("POST", "/api/rev/capture/preview", { text }); } catch (e) { box.innerHTML = card({ body: errorState(e.message) }); return; }
  const ai = new Set(f.ai_fields || []);
  const tag = (k) => (ai.has(k) ? ` ${pill("AI suggestion: check", "info")}` : "");
  const inp = (k, label, extra = "") => `<label class="field grow"><span>${label}${tag(k)}</span><input name="${k}" value="${esc(f[k] ?? "")}" ${extra}></label>`;
  box.innerHTML = card({ title: "Check before saving", meta: "Moyo read this from your note. Fix anything that's wrong.", cls: "capture-card", body: `
    <form id="capsave"><div class="fields">
      ${inp("company", "Company", 'placeholder="Leave empty if the person is the client"')}${inp("contact_name", "Contact person")}
      ${inp("phone", "Phone / WhatsApp", 'inputmode="tel"')}${inp("email", "Email", 'type="email"')}
    </div><div class="fields" style="margin-top:10px">
      <label class="field"><span>Need</span><select name="service"><option value="">Not sure</option>${REV_SERVICES.map(([k, l]) => `<option value="${k}" ${f.service === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="field"><span>Value</span><input name="value" type="number" min="0" step="any" value="${f.value ?? ""}" style="width:140px"></label>
      <label class="field"><span>Currency</span><select name="currency"><option ${f.currency !== "USD" ? "selected" : ""}>NGN</option><option ${f.currency === "USD" ? "selected" : ""}>USD</option></select></label>
      <label class="field"><span>Stage</span><select name="stage">${REV_OPEN.map((s) => `<option ${s === (f.stage || "new") ? "selected" : ""}>${s}</option>`).join("")}</select></label>
    </div><div class="fields" style="margin-top:10px">
      ${inp("next_action", "Next step", 'placeholder="e.g. Send proposal"')}
      <label class="field"><span>When</span><input name="next_action_due" type="date" value="${esc(f.next_action_due || "")}"></label>
      <input type="hidden" name="source" value="${esc(f.source || "other")}"><input type="hidden" name="source_detail" value="${esc(f.source_detail || "")}">
      <input type="hidden" name="notes" value="${esc(f.notes || "")}"><input type="hidden" name="need" value="${esc(f.need || "")}">
    </div>
    ${!f.next_action_due ? `<div class="foot" style="color:var(--warn)">No follow-up date: every deal needs a next step, or it will show up as “No next step”.</div>` : ""}
    <div class="actions" style="margin-top:14px;justify-content:flex-end"><button type="button" class="btn" id="capcancel">Cancel</button><button class="btn btn-primary">Save lead</button></div></form>` });
  $("#capcancel").onclick = () => (box.innerHTML = "");
  $("#capsave").onsubmit = async (e) => {
    e.preventDefault(); const v = Object.fromEntries(new FormData(e.target));
    for (const k of Object.keys(v)) if (v[k] === "") delete v[k];
    if (v.value) v.value = +v.value; v.ai_fields = [...ai];
    try { const r = await api("POST", "/api/rev/capture/commit", v); box.innerHTML = ""; $("#capin").value = "";
      toast(r.reused_contact ? `Saved and linked to ${r.reused_contact}, who was already in Moyo` : "Lead saved"); refresh(); }
    catch (err) { toast(err.message); }
  };
  box.querySelector("input")?.focus();
}

/* ================================================================ today */
function renderToday(box, ov) {
  if (!ov.today.length) { box.innerHTML = card({ body: emptyState("Nobody needs a follow-up today", ov.stats.open ? "Every open deal has a next step that isn't due yet." : "Add your first lead above, or import a WhatsApp chat from a deal.") }); return; }
  box.innerHTML = card({ title: "Who to contact today", meta: "ranked by value, stage, how overdue and how long since you last spoke", body: `<div class="rows">${ov.today.map((i, n) => `
    <div class="row fu"><div class="grow">
      <div class="title"><button class="linkbtn" data-deal="${i.deal_id}">${esc(i.name)}</button> <span class="meta">${[titleText(i.name, i.title), i.stage_label, i.value != null ? money(i.value, i.currency) : ""].filter(Boolean).map(esc).join(" · ")}</span></div>
      <div class="chips">${i.reasons.map((r, n) => `<span class="chip${n === 0 ? " lead" : ""}">${esc(r)}</span>`).join("")}</div>
      ${i.next_action ? `<div class="meta">Next: ${esc(i.next_action)}${i.next_action_due ? " · " + dueText(i.next_action_due) : ""}</div>` : ""}</div>
      <div class="fu-actions"><button class="btn ${n === 0 ? "btn-primary" : ""} sm" data-draft="${i.deal_id}">${icon("chat", "sm")} Draft message</button>
        <button class="btn sm" data-done="${i.deal_id}">Done</button><button class="btn btn-ghost sm" data-snooze="${i.deal_id}">Snooze</button>
        <button class="btn btn-ghost sm" data-dismiss="${i.deal_id}">Dismiss</button></div></div>`).join("")}</div>` });
  $$("[data-deal]", box).forEach((b) => (b.onclick = () => openDeal(+b.dataset.deal)));
  $$("[data-draft]", box).forEach((b) => (b.onclick = () => openDraft(+b.dataset.draft, "whatsapp")));
  $$("[data-done]", box).forEach((b) => (b.onclick = () => doneSheet(+b.dataset.done)));
  $$("[data-snooze]", box).forEach((b) => (b.onclick = () => snoozeSheet(+b.dataset.snooze)));
  $$("[data-dismiss]", box).forEach((b) => (b.onclick = () => dismissSheet(+b.dataset.dismiss)));
}

const nextStepFields = (prefix = "") => `<div class="fields" style="margin-top:10px">
  <label class="field grow"><span>Next step</span><input name="next_action" placeholder="e.g. Send proposal, call back"></label>
  <label class="field"><span>When</span><input name="next_due" type="date" value="${addDays(2)}"></label></div>
  <div class="quick">${[["in 2 days", 2], ["next week", 7], ["in 2 weeks", 14]].map(([l, n]) => `<button type="button" class="btn btn-ghost sm" data-in="${n}">${l}</button>`).join("")}
  <button type="button" class="btn btn-ghost sm" data-in="none">no next step</button></div>`;
const wireQuick = (dlg) => $$("[data-in]", dlg).forEach((b) => (b.onclick = () => { $("[name=next_due]", dlg).value = b.dataset.in === "none" ? "" : addDays(+b.dataset.in); }));

function doneSheet(id) {
  const dlg = sheet("Log follow-up", `<h2 class="sheet-h">What happened?</h2><form id="dform">
    <label class="field"><span>Note (optional)</span><input name="note" placeholder="e.g. Called: they'll decide after Monday's meeting"></label>
    <div class="fields" style="margin-top:10px"><label class="field"><span>How</span><select name="channel"><option value="">Other</option><option>whatsapp</option><option>phone</option><option>email</option><option value="in_person">in person</option></select></label></div>
    ${nextStepFields()}<div class="actions" style="margin-top:14px;justify-content:flex-end"><button class="btn btn-primary">Save</button></div></form>`);
  wireQuick(dlg); $("[name=note]", dlg).focus();
  $("#dform", dlg).onsubmit = async (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(e.target));
    try { await api("POST", `/api/rev/deal/${id}/followup`, { action: "done", note: v.note || null, channel: v.channel || null, next_due: v.next_due || null, next_action: v.next_action || null });
      dlg.close(); toast("Follow-up logged"); refresh(); } catch (err) { toast(err.message); } };
}
function snoozeSheet(id) {
  const dlg = sheet("Snooze", `<h2 class="sheet-h">Snooze until…</h2><div class="quick">${[["Tomorrow", 1], ["In 3 days", 3], ["Next week", 7]]
    .map(([l, n]) => `<button class="btn" data-sn="${n}">${l}</button>`).join("")}</div>`);
  $$("[data-sn]", dlg).forEach((b) => (b.onclick = async () => { try { await api("POST", `/api/rev/deal/${id}/followup`, { action: "snooze", days: +b.dataset.sn }); dlg.close(); toast("Snoozed"); refresh(); } catch (e) { toast(e.message); } }));
  $("[data-sn]", dlg).focus();
}
function dismissSheet(id) {
  const dlg = sheet("Dismiss suggestion", `<h2 class="sheet-h">Why not today?</h2><p class="muted small">Moyo hides this suggestion for 7 days and remembers why.</p>
    <form id="xform"><div class="quick">${["Waiting for their reply", "They asked for more time", "Not a real opportunity", "Already handled"].map((r) => `<button type="button" class="btn btn-ghost sm" data-r="${esc(r)}">${esc(r)}</button>`).join("")}</div>
    <label class="field" style="margin-top:10px"><span>Reason</span><input name="reason" required></label>
    <div class="actions" style="margin-top:14px;justify-content:flex-end"><button class="btn btn-primary">Dismiss</button></div></form>`);
  $$("[data-r]", dlg).forEach((b) => (b.onclick = () => ($("[name=reason]", dlg).value = b.dataset.r)));
  $("#xform", dlg).onsubmit = async (e) => { e.preventDefault(); try { await api("POST", `/api/rev/deal/${id}/followup`, { action: "dismiss", reason: $("[name=reason]", dlg).value }); dlg.close(); toast("Dismissed for a week"); refresh(); } catch (err) { toast(err.message); } };
}

/* ================================================================ pipeline */
function renderPipeline(box, ov) {
  const cols = ov.board.filter((s) => s.is_open), closed = ov.board.filter((s) => !s.is_open).flatMap((s) => s.deals.map((d) => ({ ...d, _s: s.label })));
  if (!ov.stats.open && !closed.length) { box.innerHTML = card({ body: emptyState("Your pipeline is empty", "Add a lead above. Every deal moves New → Contacted → Engaged → Discovery → Proposal → Negotiation → Won.") }); return; }
  const dcard = (d) => `<button class="dcard" data-deal="${d.id}"><div class="title">${esc(d.name)}</div><div class="meta">${esc(d.service || titleText(d.name, d.title))}</div>
    <div class="dmeta">${d.value != null ? `<span>${valueText(d)}</span>` : `<span class="faint">no value</span>`}
    ${d.next_action_due ? pill(esc(dueText(d.next_action_due)), d.next_action_due < localISO() ? "warn" : "") : d.is_open ? pill("No next step", "warn") : pill(esc(d._s || d.stage_label))}</div></button>`;
  const sum = (ds) => { const t = {}; ds.forEach((d) => { if (d.value != null) t[d.currency] = (t[d.currency] || 0) + d.value; }); return Object.entries(t).map(([c, v]) => money(v, c)).join(" + "); };
  box.innerHTML = `<div class="board" role="list">${cols.map((s) => `<section class="col" role="listitem" aria-label="${esc(s.label)}">
      <div class="col-h"><b>${esc(s.label)}</b><span class="faint">${s.deals.length}${s.deals.length ? " · " + sum(s.deals) : ""}</span></div>
      ${s.deals.map(dcard).join("") || `<div class="col-empty">None</div>`}</section>`).join("")}</div>
    ${closed.length ? card({ title: "Closed in the last 30 days", body: `<div class="board closed">${closed.map(dcard).join("")}</div>` }) : ""}
    <div class="foot">Stage percentages are estimates, not statistics. Values are shown in their own currency.</div>`;
  $$("[data-deal]", box).forEach((b) => (b.onclick = () => openDeal(+b.dataset.deal)));
}

/* ================================================================ deal sheet */
async function openDeal(id) {
  const dlg = sheet("Deal", skeleton(6));
  const load = async () => {
    let r; try { r = await api("GET", `/api/rev/deal/${id}`); } catch (e) { setBody(dlg, errorState(e.message)); return; }
    const d = r.deal, c = r.contact, ch = (k) => c?.channels.find((x) => x.kind === k || (k === "phone" && x.kind === "whatsapp"));
    setBody(dlg, `<h2 class="sheet-h">${esc(d.name)}</h2><div class="muted small">${esc(titleText(d.name, d.title) || d.stage_label)}${d.source && d.source !== "other" ? " · source: " + esc(d.source) + (d.source_detail ? " (" + esc(d.source_detail) + ")" : "") : ""}</div>
      ${r.today ? `<div class="chips" style="margin-top:10px">${r.today.reasons.map((x, n) => `<span class="chip${n === 0 ? " lead" : ""}">${esc(x)}</span>`).join("")}</div>` : ""}
      <form id="dealf" class="fields" style="margin-top:14px">
        <label class="field"><span>Stage</span><select name="stage">${r.stages.map((s) => `<option value="${s.key}" ${s.key === d.stage_key ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select></label>
        <label class="field"><span>Value</span><input name="value" type="number" min="0" step="any" value="${d.value ?? ""}" style="width:130px"></label>
        <label class="field"><span>Currency</span><select name="currency"><option ${d.currency === "NGN" ? "selected" : ""}>NGN</option><option ${d.currency === "USD" ? "selected" : ""}>USD</option></select></label>
        <label class="field grow"><span>Next step</span><input name="next_action" value="${esc(d.next_action || "")}"></label>
        <label class="field"><span>When</span><input name="next_action_due" type="date" value="${esc(d.next_action_due || "")}"></label>
        <label class="field grow lostwhy" ${d.stage_key === "lost" ? "" : "hidden"}><span>Why lost?</span><input name="lost_reason" value="${esc(d.lost_reason || "")}"></label>
        <div class="actions" style="align-self:flex-end"><button class="btn">Save</button></div></form>
      <div class="sheet-sec"><h3>Contact</h3>${c ? `<div><b>${esc(c.full_name)}</b>${c.role ? ` · ${esc(c.role)}` : ""}</div>
          <div class="small muted">${c.channels.map((x) => `${esc(x.kind)}: ${esc(x.value)}`).join(" · ") || "No phone or email yet"}</div>` : `<div class="small muted">No contact person yet.</div>`}
        ${!c || !ch("phone") || !ch("email") ? `<form id="contf" class="fields" style="margin-top:8px">
          ${c ? "" : `<label class="field grow"><span>Name</span><input name="full_name" required></label>`}
          ${!ch("phone") ? `<label class="field"><span>WhatsApp / phone</span><input name="phone" inputmode="tel"></label>` : ""}
          ${!ch("email") ? `<label class="field"><span>Email</span><input name="email" type="email"></label>` : ""}
          <div class="actions" style="align-self:flex-end"><button class="btn sm">Add</button></div></form>` : ""}
        <div class="actions" style="margin-top:10px"><button class="btn btn-primary sm" data-dr="whatsapp">${icon("chat", "sm")} Draft WhatsApp</button><button class="btn sm" data-dr="email">${icon("mail", "sm")} Draft email</button></div></div>
      <div class="sheet-sec"><h3>WhatsApp history</h3>
        <p class="small muted">In WhatsApp: open the chat → ⋮ → More → <b>Export chat</b> → <b>Without media</b>, then choose the .txt here, or paste messages.</p>
        <div class="fields"><label class="field"><span class="sr-only">Chat export file</span><input type="file" id="wafile" accept=".txt,text/plain"></label></div>
        <details class="more"><summary>Paste messages instead</summary><textarea id="wapaste" rows="4" style="width:100%;margin-top:6px"></textarea><button class="btn sm" id="wapastego" style="margin-top:6px">Import pasted text</button></details>
        ${r.conversations.length ? `<div class="rows" style="margin-top:8px">${r.conversations.map((v) => `<div class="row"><div class="grow"><div class="title">${v.n} messages · imported ${humanDate(v.created_at)}</div>
          ${v.summary ? `<div class="meta">${esc(v.summary)}</div>` : ""}</div><button class="btn sm" data-sum="${v.id}">${v.summary ? "Summarise again" : "Summarise"}</button></div>`).join("")}</div>
          <div class="foot">Summaries are written by Gemini (free tier) from the chat text. You review them before anything is saved.</div>` : ""}</div>
      <div class="sheet-sec" id="docsec"><h3>Proposals & invoices</h3>${skeleton(1)}</div>
      <div class="sheet-sec"><h3>Notes & history</h3><form id="notef" class="capture"><label class="sr-only" for="notein">Add a note</label><input id="notein" placeholder="Add a note: requirements, objections, what was agreed…"><button class="btn sm">Add</button></form>
        <ol class="tl">${r.timeline.map((a) => `<li><span class="tl-k">${esc(a.kind.replace("_", " "))}${a.channel ? " · " + esc(a.channel) : ""}</span><span class="tl-t">${esc(humanDate(a.occurred_at))}</span><div>${esc(a.summary)}</div>
          ${a.source && a.source.startsWith("ai") ? pill("AI, confirmed by you", "info") : ""}</li>`).join("")}</ol></div>`);
    const f = $("#dealf", dlg);
    f.stage.onchange = () => (f.querySelector(".lostwhy").hidden = f.stage.value !== "lost");
    f.onsubmit = async (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(f));
      const body = { stage: v.stage, value: v.value === "" ? null : +v.value, currency: v.currency, next_action: v.next_action || null, next_action_due: v.next_action_due || null };
      if (v.stage === "lost") body.lost_reason = v.lost_reason || null;
      try { await api("PATCH", `/api/rev/deal/${id}`, body); toast(v.stage === "won" ? "Marked won. Log the payment when the money arrives." : "Saved"); load(); refresh(); } catch (err) { toast(err.message); } };
    const cf = $("#contf", dlg);
    if (cf) cf.onsubmit = async (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(cf));
      try { await api("POST", `/api/rev/deal/${id}/contact`, { full_name: v.full_name || c?.full_name || d.name, phone: v.phone || null, email: v.email || null }); toast("Contact saved"); load(); }
      catch (err) { toast(err.message); } };
    $$("[data-dr]", dlg).forEach((b) => (b.onclick = () => openDraft(id, b.dataset.dr)));
    $("#notef", dlg).onsubmit = async (e) => { e.preventDefault(); const t = $("#notein", dlg).value.trim(); if (!t) return;
      try { await api("POST", `/api/rev/deal/${id}/note`, { text: t }); load(); } catch (err) { toast(err.message); } };
    const doImport = async (text, source) => { try { const r2 = await api("POST", "/api/rev/import", { deal_id: id, text, source });
      toast(r2.new ? `Imported ${r2.new} new message${r2.new > 1 ? "s" : ""}` : "Already imported: no new messages"); load(); refresh(); } catch (err) { toast(err.message); } };
    $("#wafile", dlg).onchange = async (e) => { const file = e.target.files[0]; if (file) doImport(await file.text(), "export"); };
    $("#wapastego", dlg).onclick = () => { const t = $("#wapaste", dlg).value.trim(); if (t) doImport(t, "paste"); };
    $$("[data-sum]", dlg).forEach((b) => (b.onclick = () => summarySheet(+b.dataset.sum, id, load)));
    loadDocs(dlg, d, load);
  };
  load();
}

/* ================================================================ draft → your WhatsApp/Gmail → "I sent it" */
async function openDraft(id, channel, goal = null) {
  const dlg = sheet("Draft message", `<h2 class="sheet-h">Draft ${channel === "email" ? "email" : "WhatsApp message"}</h2>${skeleton(3)}`);
  let dr; try { dr = await api("POST", "/api/rev/draft", { deal_id: id, channel, goal }); } catch (e) { setBody(dlg, errorState(e.message)); return; }
  const phone = dr.wa_link ? dr.wa_link.split("?")[0].split("/").pop() : null, email = dr.gmail_link ? decodeURIComponent(dr.gmail_link.match(/to=([^&]*)/)[1]) : null;
  setBody(dlg, `<h2 class="sheet-h">Draft ${channel === "email" ? "email" : "WhatsApp message"}</h2>
    <div class="small muted">${dr.source === "template" ? "From a template (AI unavailable)" : "Written by " + esc(dr.source) + " · client names and amounts were hidden from the AI"} · edit freely, nothing is sent until you press send in ${channel === "email" ? "Gmail" : "WhatsApp"}.</div>
    ${channel === "email" ? `<label class="field" style="margin-top:12px"><span>Subject</span><input id="drsub" value="${esc(dr.subject || "")}"></label>` : ""}
    <label class="field" style="margin-top:12px"><span>Message</span><textarea id="drtext" rows="7" style="width:100%">${esc(dr.text)}</textarea></label>
    ${dr.missing.length && !(channel === "email" ? email : phone) ? banner(`No ${channel === "email" ? "email" : "WhatsApp/phone number"} saved for this contact. Add it in the deal, or copy the text.`, "", "warn") : ""}
    <div class="actions" style="margin-top:12px">
      ${channel !== "email" && phone ? `<button class="btn btn-primary" id="drwa">${icon("ext", "sm")} Open in WhatsApp</button>` : ""}
      ${channel === "email" && email ? `<button class="btn btn-primary" id="drgm">${icon("ext", "sm")} Open in Gmail</button>` : ""}
      <button class="btn" id="drcopy">Copy text</button></div>
    <form id="sentf" class="sheet-sec" hidden><h3>Did you send it?</h3>${nextStepFields()}
      <div class="actions" style="margin-top:12px;justify-content:flex-end"><button type="button" class="btn" id="notsent">Not yet</button><button class="btn btn-primary">Yes, I sent it</button></div></form>`);
  const text = () => $("#drtext", dlg).value.trim(), askSent = () => { $("#sentf", dlg).hidden = false; wireQuick(dlg); $("#sentf button.btn-primary", dlg).focus(); };
  $("#drwa", dlg)?.addEventListener("click", () => { window.open(`https://wa.me/${phone}?text=${encodeURIComponent(text())}`, "_blank", "noopener"); askSent(); });
  $("#drgm", dlg)?.addEventListener("click", () => { window.open(`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(email)}&su=${encodeURIComponent($("#drsub", dlg).value)}&body=${encodeURIComponent(text())}`, "_blank", "noopener"); askSent(); });
  $("#drcopy", dlg).onclick = async () => { try { await navigator.clipboard.writeText(text()); toast("Copied"); } catch { toast("Couldn't copy: select the text instead"); } askSent(); };
  $("#notsent", dlg).onclick = () => dlg.close();
  $("#sentf", dlg).onsubmit = async (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(e.target));
    try { await api("POST", "/api/rev/sent", { deal_id: id, channel, text: text(), next_due: v.next_due || "", next_action: v.next_action || null }); dlg.close(); toast("Logged. Nice work."); refresh(); }
    catch (err) { toast(err.message); } };
  $("#drtext", dlg).focus();
}

/* ================================================================ AI summary → you confirm */
async function summarySheet(convId, dealId, after) {
  const dlg = sheet("Conversation summary", `<h2 class="sheet-h">Summarising…</h2>${skeleton(4)}`);
  let s; try { s = await api("POST", `/api/rev/conversation/${convId}/summarize`); } catch (e) { setBody(dlg, errorState(e.message)); return; }
  if (s.error) { setBody(dlg, `<h2 class="sheet-h">Summary unavailable</h2>${errorState(s.error)}`); return; }
  setBody(dlg, `<h2 class="sheet-h">Check the summary</h2><div class="small muted">Written by ${esc(s.model || "AI")} from the chat. Edit it, untick anything wrong, then save.</div>
    <label class="field" style="margin-top:12px"><span>Summary</span><textarea id="sumt" rows="4" style="width:100%">${esc(s.summary)}</textarea></label>
    ${s.requirements.length ? `<div class="sheet-sec"><h3>Requirements</h3><ul class="small">${s.requirements.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    ${s.budget_mentioned ? `<div class="small"><b>Budget mentioned:</b> ${esc(s.budget_mentioned)} <span class="faint">(not saved as the deal value unless you change it)</span></div>` : ""}
    ${s.objections.length ? `<div class="small" style="margin-top:6px"><b>Objections:</b> ${s.objections.map(esc).join("; ")}</div>` : ""}
    <div class="sheet-sec"><h3>Commitments</h3>${s.commitments.length ? s.commitments.map((c, n) => `<div class="fields commit" data-n="${n}" style="margin:6px 0">
        <label class="check"><input type="checkbox" checked> ${c.who === "me" ? "You" : "They"}: ${esc(c.what)}${c.when ? ` <span class="faint">(${esc(c.when)})</span>` : ""}</label>
        <label class="field"><span class="sr-only">Due date</span><input type="date" aria-label="Due date for: ${esc(c.what)}"></label></div>`).join("") : `<div class="small muted">None found.</div>`}
      <div class="foot">A commitment with a date becomes a follow-up. Without a date, it's saved as a note.</div></div>
    <form id="sumf" class="sheet-sec"><h3>Next step</h3><div class="fields"><label class="field grow"><span>Next step</span><input name="next_action" value="${esc(s.suggested_next_step || "")}"></label>
      <label class="field"><span>When</span><input name="next_due" type="date" value="${addDays(2)}"></label></div>
      <div class="actions" style="margin-top:12px;justify-content:flex-end"><button type="button" class="btn" id="sumx">Discard</button><button class="btn btn-primary">Save</button></div></form>`);
  $("#sumx", dlg).onclick = () => dlg.close();
  $("#sumf", dlg).onsubmit = async (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(e.target));
    const commitments = $$(".commit", dlg).filter((row) => row.querySelector("input[type=checkbox]").checked)
      .map((row) => { const c = s.commitments[+row.dataset.n]; return { who: c.who, what: c.what, due: row.querySelector("input[type=date]").value || null }; });
    try { const r = await api("POST", `/api/rev/conversation/${convId}/confirm`, { deal_id: dealId, summary: $("#sumt", dlg).value.trim(), commitments, next_step: v.next_action || null, next_due: v.next_due || null });
      dlg.close(); toast(`Saved${r.follow_ups ? ` · ${r.follow_ups} follow-up${r.follow_ups > 1 ? "s" : ""} added` : ""}`); after?.(); refresh(); }
    catch (err) { toast(err.message); } };
}
