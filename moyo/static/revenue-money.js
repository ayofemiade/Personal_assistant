/* Revenue Toolkit, Phase 2: Money tab (collected, owed, invoices, payments, renewals) + proposals in the deal sheet.
   Every money action goes through Moyo's confirmation step (/api/action → /api/confirm). Moyo never sends anything. */

const STATE_LABEL = { draft: ["Draft", ""], issued: ["Sent · unpaid", "info"], part_paid: ["Part-paid", "accent"], paid: ["Paid", "good"],
  overdue: ["Overdue", "warn"], void: ["Void", ""], historical: ["History", ""], approved: ["Approved", "info"], sent: ["Sent", "info"],
  accepted: ["Accepted", "good"], rejected: ["Rejected", "warn"], expired: ["Expired", "warn"] };
const statePill = (s) => { const [l, t] = STATE_LABEL[s] || [s, ""]; return pill(esc(l), t); };
const curSum = (o) => Object.entries(o || {}).map(([c, v]) => money(v, c)).join(" + ") || "₦0";

/* ---------- confirm-tier actions: show Moyo's own summary, then you decide ---------- */
async function confirmAction(name, args, after) {
  let r; try { r = await api("POST", "/api/action/" + name, args); } catch (e) { toast(e.message); return; }
  if (!r.needs_confirmation) { r.error ? toast(r.reply) : (toast(r.reply), after?.(), refresh()); return; }
  const dlg = sheet("Confirm", `<h2 class="sheet-h">Please confirm</h2><p style="white-space:pre-line">${esc(r.reply)}</p>
    <div class="actions" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-no>Cancel</button><button class="btn btn-primary" data-yes>Yes, confirm</button></div>`);
  $("[data-no]", dlg).onclick = async () => { await api("POST", "/api/confirm", { pending_id: r.pending_id, accept: false }).catch(() => {}); dlg.close(); };
  $("[data-yes]", dlg).onclick = async () => { try { const d = await api("POST", "/api/confirm", { pending_id: r.pending_id, accept: true });
    dlg.close(); toast(d.reply); if (!d.error) { after?.(); refresh(); } } catch (e) { toast(e.message); } };
  $("[data-yes]", dlg).focus();
}

const parseItems = (text) => text.split(/\n/).map((l) => l.trim()).filter(Boolean).map((l) => {
  const m = l.match(/^(.*?)\s*[-–:]\s*([₦$]?[\d,.]+\s*[kKmM]?)\s*$/); return m ? { description: m[1].trim(), amount: m[2] } : { description: l }; });

/* ================================================================ Money tab */
renderMoneyTab = async function (el) {
  const m = await api("GET", "/api/rev/money"), ch = m.challenge;
  const hist = m.invoices.filter((i) => i.historical), live = m.invoices.filter((i) => !i.historical);
  el.innerHTML = `${!m.ngn_per_usd ? banner("Set your ₦/$ rate first, so Moyo never guesses a conversion.", `<button class="btn sm" data-go="settings">Set rate</button>`, "warn") : ""}
  <div class="grid">
    <div class="c-12">${card({ body: `<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline">
        <div><span class="hero-num">${usd(ch.earned_usd)}</span> <span class="muted">of ${usd(ch.target_usd)} collected</span></div>
        ${pill(ch.on_track ? "On pace" : `${usd(Math.abs(ch.gap_vs_pace_usd))} behind steady pace`, ch.on_track ? "good" : "warn")}</div>
      <div class="progress" role="img" aria-label="${ch.pct}% of target collected"><i style="width:${ch.pct}%"></i><b style="left:${Math.min(100, ch.expected_by_now_usd / ch.target_usd * 100)}%"></b></div>
      <div class="progress-legend"><span>${ch.pct}% collected · only money actually received counts</span><span>marker = steady pace today</span></div>
      <div class="stats" style="--cols:4">${stat(usd(ch.remaining_usd), "still to collect")}${stat(usd(ch.required_per_week_usd), "needed per week")}${stat(usd(ch.earned_this_week_usd), "collected this week")}${stat(ch.days_left, "days left")}</div>
      <div class="stats secondary" style="--cols:3">${stat(esc(curSum(m.outstanding_by_currency)), "owed to you (sent invoices)")}${stat(esc(curSum(m.overdue_by_currency)), "of that, overdue")}${stat(usd(ch.weighted_pipeline_usd), "weighted pipeline (estimate)")}</div>` })}</div>
    <div class="c-12">${card({ title: "Money owed to you", meta: m.owed.length ? `${m.owed.length} unpaid invoice${m.owed.length > 1 ? "s" : ""}` : "", body: m.owed.length ? `<div class="rows">${m.owed.map((i, n) => `
      <div class="row wrap"><div class="grow"><div class="title">${esc(i.client)} <span class="meta">${esc(i.number)} · ${money(i.balance, i.currency)} of ${money(i.total, i.currency)}</span></div>
        <div class="meta">${i.state === "overdue" ? `<span style="color:var(--warn)">Overdue since ${humanDate(i.due_date)}</span>` : `Due ${humanDate(i.due_date)}`}</div></div>
        ${statePill(i.state)}<button class="btn ${n === 0 ? "btn-primary" : ""} sm" data-pay="${i.id}">Record payment</button>
        ${i.deal_id ? `<button class="btn btn-ghost sm" data-remind="${i.id}">Remind</button>` : ""}</div>`).join("")}</div>`
      : emptyState("Nobody owes you money right now", "When you send an invoice, mark it as sent here. It then shows up until it's paid.") })}</div>
    <div class="c-12">${card({ title: "Invoices", meta: "drafts are never sent by Moyo: mark them sent after you send them", body: `
      <details class="add"><summary class="btn btn-primary sm">${icon("plus", "sm")} New invoice</summary>${invoiceForm()}</details>
      <div class="tablewrap" style="margin-top:12px">${live.length ? `<table><thead><tr><th>Number</th><th>Client</th><th>Date</th><th class="r">Total</th><th class="r">Still owed</th><th>Status</th><th></th></tr></thead><tbody>
        ${live.map((i) => `<tr><td>${esc(i.number)}</td><td>${esc(i.client)}</td><td>${humanDate(i.issue_date)}</td><td class="r">${money(i.total, i.currency)}</td>
          <td class="r">${["issued", "part_paid", "overdue"].includes(i.state) ? money(i.balance, i.currency) : "–"}</td><td>${statePill(i.state)}</td>
          <td class="r nowrap">${i.pdf_path ? `<button class="btn btn-ghost sm" data-open="${i.id}">PDF</button>` : ""}
            ${i.state === "draft" ? `<button class="btn sm" data-issue="${esc(i.number)}">Mark sent</button>` : ""}
            ${["issued", "part_paid", "overdue"].includes(i.state) ? `<button class="btn sm" data-pay="${i.id}">Payment</button>` : ""}
            ${["draft", "issued", "overdue"].includes(i.state) && !i.paid ? `<button class="btn btn-ghost sm" data-void="${esc(i.number)}">Void</button>` : ""}</td></tr>`).join("")}</tbody></table>`
        : emptyState("No invoices yet", "Create one here, from an accepted proposal, or say “create an invoice for Kemi Stores, website 450k, 50% deposit”.")}</div>
      ${hist.length ? `<details class="more" style="margin-top:10px"><summary>Past invoices (history, ${hist.length}): not counted toward the $10K, payment status not recorded</summary>
        <div class="tablewrap"><table><tbody>${hist.map((i) => `<tr><td>${esc(i.number)}</td><td>${esc(i.client)}</td><td>${humanDate(i.issue_date)}</td><td class="r">${money(i.total, i.currency)}</td></tr>`).join("")}</tbody></table></div></details>` : ""}` })}</div>
    <div class="c-7">${card({ title: "Payments received", end: `<button class="btn sm" id="newpay">${icon("plus", "sm")} Record payment</button>`, body: m.payments.length ? `<div class="tablewrap"><table><thead><tr><th>Date</th><th>From</th><th class="r">Amount</th><th>Paid</th><th></th></tr></thead><tbody>
      ${m.payments.map((p) => `<tr class="${p.reversed ? "faint" : ""}"><td>${humanDate(p.received_date)}</td><td>${esc(p.payer_label || p.company || "n/a")}<div class="xs muted">${esc(p.method.replace("_", " "))}${p.reference ? " · " + esc(p.reference) : ""}</div></td>
        <td class="r">${money(p.amount, p.currency)}${p.refunded_minor ? `<div class="xs muted">refunded ${money(p.refunded_minor / 100, p.currency)}</div>` : ""}</td>
        <td class="xs nowrap">${p.reversed ? "cancelled entry" : p.allocations.map((a) => esc(a.number)).join(", ") || (p.unallocated_minor ? "credit (no invoice)" : "")}</td>
        <td class="r nowrap">${p.reversed ? "" : `<button class="btn btn-ghost sm" data-refund="${p.id}">Refund</button><button class="btn btn-ghost sm" data-reverse="${p.id}">Mistake?</button>`}</td></tr>`).join("")}</tbody></table></div>`
      : emptyState("No payments recorded yet", "When money lands in your account, record it here or say “log payment ₦200,000 from Kemi Stores”.") })}</div>
    <div class="c-5">${card({ title: "Renewals coming up", meta: "from hosting, domain and maintenance you've invoiced before", body: m.renewals.length ? `<div class="rows">${m.renewals.map((r) => `
      <div class="row wrap"><div class="grow"><div class="title">${esc(r.company)}</div><div class="meta">${esc(r.kind)} · last on ${esc(r.last_invoice)}${r.last_amount ? " · " + money(r.last_amount, r.currency) : ""}</div></div>
        ${pill(r.days < 0 ? `${-r.days} days late` : humanDate(r.due), r.days <= 30 ? "warn" : "")}</div>`).join("")}</div>` : emptyState("No renewals in the next year", "") })}</div>
    ${m.legacy_earnings.length ? `<div class="c-12">${card({ title: "Earlier money log", meta: "entries from before the ledger; paid ones still count", body: `<div class="tablewrap"><table><tbody>${m.legacy_earnings.map((e) => `<tr><td>${humanDate(e.earned_date)}</td><td>${esc(e.client || "n/a")}</td><td class="r">${money(e.amount, e.currency)}</td><td>${e.payment_status === "paid" ? pill("paid", "good") : pill("not paid")}</td></tr>`).join("")}</tbody></table></div>` })}</div>` : ""}
  </div>`;
  $$("[data-go]", el).forEach((b) => (b.onclick = () => show(b.dataset.go)));
  wireInvoiceForm(el, null);
  const byId = (id) => m.invoices.find((i) => i.id === +id);
  $$("[data-pay]", el).forEach((b) => (b.onclick = () => paymentSheet(byId(b.dataset.pay), m.owed)));
  $("#newpay").onclick = () => paymentSheet(null, m.owed);
  $$("[data-open]", el).forEach((b) => (b.onclick = () => api("POST", `/api/rev/invoice/${b.dataset.open}/open`).catch((e) => toast(e.message))));
  $$("[data-issue]", el).forEach((b) => (b.onclick = () => confirmAction("issue_invoice", { number: b.dataset.issue })));
  $$("[data-void]", el).forEach((b) => (b.onclick = () => reasonSheet("Void invoice", "Why void it? (It stays on record.)", (reason) => confirmAction("void_invoice", { number: b.dataset.void, reason }))));
  $$("[data-refund]", el).forEach((b) => (b.onclick = () => refundSheet(m.payments.find((p) => p.id === +b.dataset.refund))));
  $$("[data-reverse]", el).forEach((b) => (b.onclick = () => reasonSheet("Cancel a mistaken entry", "What was wrong? (e.g. entered twice, wrong amount). Money actually returned to a client is a refund, not this.",
    (reason) => confirmAction("reverse_payment", { payment_id: +b.dataset.reverse, reason }))));
  $$("[data-remind]", el).forEach((b) => (b.onclick = () => { const i = byId(b.dataset.remind);
    openDraft(i.deal_id, "whatsapp", `Friendly payment reminder for invoice ${i.number}: balance ${money(i.balance, i.currency)}, due ${i.due_date}. Polite, short, include that the bank details are on the invoice.`); }));
};

function invoiceForm(dealId = null, client = "") {
  return `<form class="form-card invform"><div class="fields">
      ${dealId ? `<input type="hidden" name="deal_id" value="${dealId}">` : `<label class="field grow"><span>Bill to</span><input name="client" required value="${esc(client)}" placeholder="e.g. Kemi Stores"></label>`}
      <label class="field grow"><span>Contact / address (optional)</span><input name="bill_to"></label>
      <label class="field"><span>Deposit %</span><input name="deposit_pct" type="number" min="0" max="100" value="50" style="width:100px"></label>
      <label class="field"><span>Discount</span><input name="discount" type="number" min="0" step="any" style="width:120px"></label>
      <label class="field"><span>Currency</span><select name="currency"><option>NGN</option><option>USD</option></select></label></div>
    <label class="field" style="margin-top:10px"><span>Items: one per line, “description - amount”</span>
      <textarea name="items" rows="3" required placeholder="Website development (kemistores.com) - 300000&#10;Hosting & domain (1 year) - 50000"></textarea></label>
    <div class="actions" style="margin-top:10px;justify-content:space-between"><span class="foot" style="margin:0">Makes a draft PDF in your Invoices folder. Nothing is sent.</span><button class="btn btn-primary">Create draft</button></div></form>`;
}
function wireInvoiceForm(root, after) {
  $$(".invform", root).forEach((f) => (f.onsubmit = async (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(f));
    const body = { client: v.client || null, deal_id: v.deal_id ? +v.deal_id : null, bill_to: v.bill_to || null, items: parseItems(v.items),
      deposit_pct: v.deposit_pct ? +v.deposit_pct : null, discount: v.discount ? +v.discount : 0, currency: v.currency };
    try { const r = await api("POST", "/api/rev/invoice", body); toast(`Draft ${r.number} created`); api("POST", `/api/rev/invoice/${r.id}/open`).catch(() => {}); after ? after() : refresh(); }
    catch (err) { toast(err.message); } }));
}

function paymentSheet(inv, owed) {
  const opts = owed.map((o) => `<option value="${esc(o.number)}" data-client="${esc(o.client)}" data-cur="${o.currency}" ${inv && inv.id === o.id ? "selected" : ""}>${esc(o.number)} · ${esc(o.client)} · ${money(o.balance, o.currency)} owed</option>`).join("");
  const dlg = sheet("Record payment", `<h2 class="sheet-h">Record money received</h2><p class="small muted">Only record money that has actually landed. It counts toward the $10K on the date received.</p>
    <form id="payf"><div class="fields">
      <label class="field"><span>Amount</span><input name="amount" type="number" min="0.01" step="any" required value="${inv ? inv.balance : ""}" style="width:150px"></label>
      <label class="field"><span>Currency</span><select name="currency"><option ${!inv || inv.currency === "NGN" ? "selected" : ""}>NGN</option><option ${inv && inv.currency === "USD" ? "selected" : ""}>USD</option></select></label>
      <label class="field"><span>Received on</span><input name="earned_date" type="date" required value="${localISO()}" max="${localISO()}"></label></div>
    <div class="fields" style="margin-top:10px">
      <label class="field grow"><span>For invoice</span><select name="invoice"><option value="">Match automatically (oldest first)</option>${opts}</select></label>
      <label class="field grow"><span>From</span><input name="client" value="${esc(inv ? inv.client : "")}" placeholder="client name"></label></div>
    <div class="fields" style="margin-top:10px">
      <label class="field"><span>How</span><select name="method"><option value="bank_transfer">Bank transfer</option><option value="paystack">Paystack</option><option value="cash">Cash</option><option value="other">Other</option></select></label>
      <label class="field grow"><span>Reference (optional)</span><input name="reference" placeholder="e.g. transfer ref"></label></div>
    <div class="actions" style="margin-top:14px;justify-content:flex-end"><button class="btn btn-primary">Review</button></div></form>`);
  const f = $("#payf", dlg);
  f.invoice.onchange = () => { const o = f.invoice.selectedOptions[0]; if (o.value) { f.client.value = o.dataset.client; f.currency.value = o.dataset.cur; } };
  f.onsubmit = (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(f)); dlg.close();
    confirmAction("log_payment", { amount: +v.amount, currency: v.currency, client: v.client || null, earned_date: v.earned_date, paid: true,
      invoice: v.invoice || null, method: v.method, reference: v.reference || null }); };
  f.amount.focus();
}
function refundSheet(p) {
  const dlg = sheet("Refund", `<h2 class="sheet-h">Refund money to ${esc(p.payer_label || p.company || "the client")}</h2>
    <p class="small muted">For money you actually returned. It reduces your collected total. (A typing mistake is “Mistake?”, not a refund.)</p>
    <form id="reff"><div class="fields"><label class="field"><span>Amount</span><input name="amount" type="number" min="0.01" step="any" required max="${p.amount - p.refunded_minor / 100}" style="width:150px"></label>
    <label class="field grow"><span>Reason</span><input name="reason" required></label></div>
    <div class="actions" style="margin-top:14px;justify-content:flex-end"><button class="btn btn-primary">Review</button></div></form>`);
  $("#reff", dlg).onsubmit = (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(e.target)); dlg.close();
    confirmAction("refund_payment", { payment_id: p.id, amount: +v.amount, reason: v.reason }); };
}
function reasonSheet(title, prompt, then) {
  const dlg = sheet(title, `<h2 class="sheet-h">${esc(title)}</h2><form id="rsf"><label class="field"><span>${esc(prompt)}</span><input name="reason" required></label>
    <div class="actions" style="margin-top:14px;justify-content:flex-end"><button class="btn btn-primary">Continue</button></div></form>`);
  $("#rsf", dlg).onsubmit = (e) => { e.preventDefault(); const r = $("[name=reason]", dlg).value.trim(); dlg.close(); then(r); };
  $("[name=reason]", dlg).focus();
}

/* ================================================================ deal sheet: proposals & invoices */
async function loadDocs(dlg, d, reload) {
  const box = $("#docsec", dlg); if (!box) return;
  let docs; try { docs = await api("GET", `/api/rev/deal/${d.id}/docs`); } catch (e) { box.innerHTML = `<h3>Proposals & invoices</h3>${errorState(e.message)}`; return; }
  box.innerHTML = `<h3>Proposals & invoices</h3>
    ${docs.proposals.length ? `<div class="rows">${docs.proposals.map((p) => `<div class="row wrap"><div class="grow"><div class="title">${esc(p.number)} · v${p.version} <span class="meta">${money(p.total, p.currency)}${p.valid_until ? " · valid until " + humanDate(p.valid_until) : ""}</span></div></div>
      ${statePill(p.state)}<button class="btn btn-ghost sm" data-popen="${p.id}">PDF</button>
      ${["draft", "approved"].includes(p.status) ? `<button class="btn btn-ghost sm" data-pedit="${p.id}">Edit</button><button class="btn sm" data-psent="${p.id}">Mark sent</button>` : ""}
      ${p.status === "sent" ? `<button class="btn btn-ghost sm" data-pedit="${p.id}">Revise</button><button class="btn sm" data-pacc="${p.id}">Accepted</button><button class="btn btn-ghost sm" data-prej="${p.id}">Rejected</button>` : ""}
      ${p.status === "accepted" ? `<button class="btn btn-primary sm" data-pinv="${p.id}">Create invoice</button>` : ""}</div>`).join("")}</div>` : `<div class="small muted">No proposal yet.</div>`}
    ${docs.invoices.length ? `<div class="rows" style="margin-top:6px">${docs.invoices.map((i) => `<div class="row wrap"><div class="grow"><div class="title">${esc(i.number)} <span class="meta">${money(i.total, i.currency)}${["issued", "part_paid", "overdue"].includes(i.state) ? " · " + money(i.balance, i.currency) + " owed" : ""}</span></div></div>${statePill(i.state)}</div>`).join("")}</div>` : ""}
    <div class="actions" style="margin-top:10px"><button class="btn sm" id="newprop">${icon("plus", "sm")} New proposal</button>
      <details class="more" style="display:inline-block"><summary class="btn btn-ghost sm">${icon("plus", "sm")} New invoice</summary>${invoiceForm(d.id)}</details></div>`;
  const again = () => { loadDocs(dlg, d, reload); };
  wireInvoiceForm(box, again);
  $("#newprop", box).onclick = () => proposalSheet(d, null, again);
  $$("[data-popen]", box).forEach((b) => (b.onclick = () => api("POST", `/api/rev/proposal/${b.dataset.popen}/open`).catch((e) => toast(e.message))));
  $$("[data-pedit]", box).forEach((b) => (b.onclick = async () => proposalSheet(d, await api("GET", `/api/rev/proposal/${b.dataset.pedit}`), again)));
  const status = async (id, status, reason) => { try { await api("POST", `/api/rev/proposal/${id}/status`, { status, reason }); toast(`Proposal marked ${status}`); again(); reload?.(); refresh(); } catch (e) { toast(e.message); } };
  $$("[data-psent]", box).forEach((b) => (b.onclick = () => { if (confirm("Mark this proposal as sent? Only do this after you've sent it to the client yourself.")) status(+b.dataset.psent, "sent"); }));
  $$("[data-pacc]", box).forEach((b) => (b.onclick = () => status(+b.dataset.pacc, "accepted")));
  $$("[data-prej]", box).forEach((b) => (b.onclick = () => reasonSheet("Proposal rejected", "Why did they say no? (helps you learn what loses deals)", (r) => status(+b.dataset.prej, "rejected", r))));
  $$("[data-pinv]", box).forEach((b) => (b.onclick = async () => { try { const r = await api("POST", `/api/rev/proposal/${b.dataset.pinv}/invoice`); toast(`Invoice ${r.number} drafted from the proposal`);
    api("POST", `/api/rev/invoice/${r.id}/open`).catch(() => {}); again(); } catch (e) { toast(e.message); } }));
}

function proposalSheet(d, p, after) {
  const c = p ? p.content : { title: d.service || titleText(d.name, d.title) || d.title, deposit_pct: 50, valid_days: 14 };
  const lines = (k) => esc((c[k] || []).join("\n"));
  const ta = (k, label, rows = 3, hint = "") => `<label class="field" style="margin-top:10px"><span>${label}</span><textarea name="${k}" rows="${rows}" placeholder="${esc(hint)}">${["scope", "deliverables", "exclusions", "assumptions"].includes(k) ? lines(k) : esc(c[k] || "")}</textarea></label>`;
  const dlg = sheet("Proposal", `<h2 class="sheet-h">${p ? `${esc(p.number)} · edit (saves as v${p.version + 1})` : "New proposal"} · ${esc(d.name)}</h2>
    <div class="small muted">Moyo can draft the wording from this deal's notes and chats (names and amounts hidden from the AI). <b>Prices are always yours.</b></div>
    <div class="actions" style="margin-top:10px"><button class="btn sm" id="pai">${icon("chat", "sm")} Draft wording with AI</button></div>
    <form id="propf">
      <label class="field" style="margin-top:10px"><span>Title</span><input name="title" value="${esc(c.title || "")}"></label>
      ${ta("problem", "The challenge (their problem)", 3)}${ta("solution", "Our solution", 3)}
      ${ta("scope", "Scope of work (one per line)", 4)}${ta("deliverables", "Deliverables (one per line)", 3)}${ta("exclusions", "Not included (one per line)", 2)}
      ${ta("timeline", "Timeline", 2, "e.g. 3 weeks from deposit")}${ta("assumptions", "Assumptions (one per line)", 2)}
      <label class="field" style="margin-top:10px"><span>Pricing: one per line, “item - amount”</span><textarea name="pricing" rows="3" required placeholder="Website design & development - 400000&#10;Hosting & domain (1 year) - 50000">${esc((c.pricing || []).map((x) => `${x.description} - ${x.amount}`).join("\n"))}</textarea></label>
      <div class="fields" style="margin-top:10px">
        <label class="field"><span>Currency</span><select name="currency"><option ${c.currency !== "USD" ? "selected" : ""}>NGN</option><option ${c.currency === "USD" ? "selected" : ""}>USD</option></select></label>
        <label class="field"><span>Deposit %</span><input name="deposit_pct" type="number" min="0" max="100" value="${c.deposit_pct ?? 50}" style="width:100px"></label>
        <label class="field"><span>Valid for (days)</span><input name="valid_days" type="number" min="1" value="${c.valid_days || 14}" style="width:110px"></label></div>
      ${ta("revisions", "Revisions", 2)}${ta("support", "Support after launch", 2)}
      <div class="actions" style="margin-top:14px;justify-content:flex-end"><button type="button" class="btn" data-x>Cancel</button><button class="btn btn-primary">Save & make PDF</button></div></form>`);
  const f = $("#propf", dlg);
  $("[data-x]", dlg).onclick = () => dlg.close();
  $("#pai", dlg).onclick = async (e) => { e.target.disabled = true; e.target.textContent = "Drafting…";
    try { const r = await api("POST", "/api/rev/proposal/ai", { deal_id: d.id });
      for (const k of ["problem", "solution", "timeline"]) if (r[k] && !f[k].value.trim()) f[k].value = r[k];
      for (const k of ["scope", "deliverables", "exclusions", "assumptions"]) if (r[k]?.length && !f[k].value.trim()) f[k].value = r[k].join("\n");
      toast(`Drafted by ${r.model}. Check every line; only empty boxes were filled.`); }
    catch (err) { toast(err.message); } e.target.disabled = false; e.target.textContent = "Draft wording with AI"; };
  f.onsubmit = async (e) => { e.preventDefault(); const v = Object.fromEntries(new FormData(f));
    const content = { ...v, pricing: parseItems(v.pricing), deposit_pct: v.deposit_pct === "" ? null : +v.deposit_pct, valid_days: +v.valid_days };
    try { const r = p ? await api("PUT", `/api/rev/proposal/${p.id}`, content) : await api("POST", "/api/rev/proposal", { deal_id: d.id, content });
      dlg.close(); toast(`${r.number} v${r.version} saved`); api("POST", `/api/rev/proposal/${r.id}/open`).catch(() => {}); after?.(); }
    catch (err) { toast(err.message); } };
}
