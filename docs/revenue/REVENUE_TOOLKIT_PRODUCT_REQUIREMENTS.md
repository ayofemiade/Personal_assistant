# Revenue Toolkit: Product Requirements

Status: **DRAFT for Moyosore's review**, 13 Nov 2026. Nothing below is built yet unless marked *(exists)*.

## 1. Where we actually are (verified, 13 Nov 2026)

| Fact | Source |
|---|---|
| $10K challenge: **8 Nov 2026 → 8 Feb 2027**, basis **money earned**, headline USD | D1, D2 |
| Exclusions already agreed: personal income, refunds, pass-through costs (e.g. resold hosting) | settings `challenge.exclusions` |
| ₦/$ rate is set by the owner in Settings (never guessed) | settings `ngn_per_usd` |
| Live database: **0 leads, 0 earnings, 0 tasks, 1 invoice** | `data/moyo.db` (counts only) |
| Past invoices exist outside Moyo (PDF/Word) and can be imported as history | owner's invoice folder |
| Payment practice: bank transfer, 50–80% upfront, balance on delivery | same |

**Implication.** At a typical past deal size, the target needs a steady flow of won deals every week, from an empty pipeline.
The software can't create demand. The toolkit's job is to:
1. make capturing every real opportunity effortless, and make sure no follow-up is ever dropped;
2. show where larger and recurring deals come from (deal size is the biggest lever);
3. make collected cash and outstanding money impossible to lose track of.

## 2. Goals (measurable)

| Goal | Metric (defined in §7) | Target to agree |
|---|---|---|
| Follow-up discipline | % of follow-ups done on or before their due date | ≥ 90% |
| Pipeline volume | new qualified deals per week | to agree (math says ≈ 3 won/week at current size) |
| Conversion | proposal → won rate | measured after ≥ 10 proposals |
| Deal size | average won deal (NGN and USD) | upward trend |
| Cash | outstanding > 14 days overdue | ₦0 |
| Effort | time to log a new lead | < 20 s by voice or typing |

## 3. Users and channels

- **One user:** Moyosore (owner, sales, delivery). It's built so a teammate *could* be added later, but that isn't designed for now.
- **Where conversations happen:** WhatsApp (main), phone calls, in person, email (Gmail, already connected read-only), Instagram/TikTok DMs (not readable through the APIs we have).

## 4. The revenue lifecycle (how MoyoCode actually sells)

```
Source (referral · inbound DM · social post · cold outreach · past client)
  → Capture (lead + contact + company, provenance recorded)
  → Qualify (need, budget, timeline, decision-maker → "qualified" or "nurture")
  → Conversation (WhatsApp/call/meeting: notes, requirements, objections, promises)
  → Discovery (scope questions answered)
  → Proposal/quotation (versioned PDF; sent BY Moyosore)
  → Negotiation (revisions, discounts, objections)
  → Won → Invoice(s) by milestone (deposit 50–80%, balance)  |  Lost (reason) → Nurture
  → Payment(s) recorded (partial allowed, reference, method, date, rate)
  → Delivery milestones → "earned" recognised (rule to confirm, see Decisions)
  → Retention: maintenance, renewals (e.g. a client's yearly hosting/domain), referrals, upsell
```

## 5. Features by module (MVP marked ★)

### A. Capture & lead management
- ★ **Quick capture**, typed or spoken: "Met Tunde from Kemi Stores, needs an e-commerce site, budget around 400k, follow up Monday". Moyo extracts company, contact, need, value and follow-up, then **shows a confirmation card**. Nothing is saved as fact until you confirm.
- ★ Manual add/edit form. Fields: company, contacts (name, role, phone, email, WhatsApp), industry, location, website/socials, problem, service needed, estimated value + currency, source, status, next action and date, notes.
- ★ **Provenance on every field:** `you said` / `imported` / `AI suggestion (unconfirmed)`. AI suggestions are shown differently until you confirm them.
- ★ Duplicate prevention: phone (normalised to +234…), email and company name are matched. Merging is always suggested, never automatic.
- CSV import (Phase 2). No scraping of any platform, ever.

### B. Relationships (CRM)
- ★ Companies ↔ multiple contacts. One timeline per contact and company: notes, calls, meetings, WhatsApp (pasted, exported or logged), emails (auto-matched from the Gmail sync *(exists)*), proposals, invoices, payments, stage changes.
- ★ Commitments ("I'll send the proposal Friday", "they'll pay the deposit after the board meets") become follow-ups.
- Important dates (renewals, birthdays of key contacts: optional), preferences and objections as structured notes (Phase 2).

### C. Pipeline & deals
- ★ Stages (configurable; defaults): New → Contacted → Engaged → Discovery → Proposal sent → Negotiation → Won / Lost / Nurture.
- ★ Deal: company, contacts, title, service(s), value + currency, expected close, stage, probability (**labelled as an estimate**: a stage default you can override), source, next action, loss reason, history.
- ★ Board view (kanban) and list view. Stage changes are logged.
- Won ≠ paid. Winning a deal creates nothing financial by itself.

### D. Follow-up engine
- ★ Every open deal must have a next action and date. If it doesn't, Moyo flags it as **"no next step"**.
- ★ Daily **"Who to contact today"** list. Each item is scored with transparent factors (value, stage, days since last touch, promise made, due/overdue, engagement), shows *why* it's on the list, and has actions: **Draft message · Done · Snooze · Reschedule · Dismiss (reason)**.
- ★ Cold detection: no touch in N days for the stage (defaults to agree, e.g. Contacted 3d, Proposal 4d, Negotiation 2d).
- Drafts vary by stage and history, and never repeat the last message. You always send them yourself (see §6).

### E. Proposals & quotations (Phase 2)
- Templates in MoyoCode's house style (same renderer as invoices *(exists)*). Sections: client, problem, solution, scope, deliverables, exclusions, pricing, milestones, timeline, assumptions, revisions, support, validity.
- Versioned: draft → approved by you → marked sent → accepted / rejected / expired. Never sent by Moyo.

### F. Money (financial integrity: see the data model)
- ★ Invoices linked to deals (the current invoice drafts *(exists)* become part of this). Status: draft → issued (you sent it) → part-paid → paid / void.
- ★ Payments: amount, currency, date, method (bank transfer, Paystack…), reference, invoice allocation (partial payments allowed), and the exchange-rate snapshot.
- ★ Outstanding and overdue amounts, with reminders.
- Expenses and direct costs, pass-through costs, refunds and adjustments (Phase 3; the data model is ready in Phase 1).
- **Kept separate in reports:** open pipeline · won (contracted) · invoiced · earned (challenge basis) · collected · outstanding · overdue · refunds · direct costs · opex · gross profit · net profit.

### G. Analytics (Phase 3)
- Sources, qualification rate, response rate, stage conversion, win rate, average deal, cycle length, revenue and profit by service, loss reasons, follow-up effectiveness, monthly/quarterly.
- **Sample-size guard:** any rate built on fewer than 5 records shows "not enough data yet (n=3)" instead of a percentage.
- Every metric links to its definition (§7) and the records behind it.

### H. AI revenue strategist
- ★ Morning **revenue brief** (in the existing brief and orb): money position, today's follow-ups, overdue invoices, stalled deals, and "deals needed at your average size".
- ★ **Drafts** follow-ups, WhatsApp/email messages and discovery questions, personalised from the timeline.
- ★ Summaries of pasted or imported conversations, with **extracted commitments and requirements proposed for confirmation**.
- Every recommendation shows: what · why · records used (clickable) · expected benefit (only when it can be calculated from data) · next action · what's uncertain or missing.
- Feedback: 👍/👎 + reason on recommendations, which is used to adjust priorities. It's stored so you can see how Moyo is learning.
- Objection help, pipeline-health analysis and experiment suggestions come in Phase 3.

## 6. Communication (summary; full research in INTEGRATION_RESEARCH)

- **Phase 1 (₦0): "assisted sending".** Moyo drafts, you edit, then **Open in WhatsApp** (official `wa.me` click-to-chat with the text pre-filled) or **Open in Gmail** (pre-filled compose). You press send in your own app. Moyo then asks "Sent?" and logs it.
- **Bringing history in:** paste a conversation, or use WhatsApp's built-in **Export chat (without media)** `.txt`. Moyo attaches it to the contact and proposes a summary and follow-ups.
- **Later (paid, opt-in):** the official WhatsApp Cloud API on a **dedicated** MoyoCode number (Nigeria can't share one number between the app and the API). Inbound sync plus human-approved sending.
- Permission levels as specified: **Read → Draft → Human-approved send → (much later) narrow automation**. No unofficial WhatsApp Web automation, ever.

## 7. Metric definitions (single source of truth)

| Metric | Definition |
|---|---|
| Open pipeline | Sum of value of deals in open stages (original currency; USD at today's rate, shown as an estimate) |
| Weighted pipeline | Σ value × probability. **Estimate**, labelled as such |
| Won (contracted) | Value of deals moved to Won in the period |
| Invoiced | Σ issued invoice totals (excluding drafts and voids) |
| **Earned (challenge)** | Per the recognition rule (Decision D-1), excluding pass-through lines and refunds |
| Collected | Σ payments received (net of refunds), at their own date and rate |
| Outstanding | Invoiced − payments allocated to those invoices |
| Overdue | Outstanding on invoices past their due date |
| Gross profit | Earned − direct project costs − pass-through costs |
| Net profit | Gross profit − operating expenses |
| Win rate | Won ÷ (Won + Lost) closed in the period. Hidden if n < 5 |
| Avg deal | Mean won value (shown per currency) |
| Cycle length | Median days from created to Won |

## 8. Out of scope (for now)
Multi-user permissions, automated outbound messaging, bulk or marketing campaigns, lead scraping, accounting/tax filing, payroll, client portal, mobile app.

## 9. MVP acceptance criteria
1. Capture a lead by voice or typing in < 20 s. Fields extracted by AI are shown as unconfirmed until you confirm them.
2. A duplicate phone or email is detected and a merge is offered, not done automatically.
3. Every open deal shows a next action. A deal with none appears in "No next step".
4. "Who to contact today" lists items with reasons. Done, snooze, reschedule and dismiss all work and are logged.
5. A follow-up draft opens in WhatsApp or Gmail pre-filled. Nothing is sent without you pressing send. The activity is logged after you confirm.
6. A pasted or exported WhatsApp chat is attached to the right contact, and a summary plus proposed follow-ups need your confirmation.
7. An invoice is linked to a deal. Two partial payments make it "paid". Outstanding and the challenge figure update exactly (tests to the kobo/cent).
8. The morning brief and orb include the revenue section, built only from records.
9. Every money figure on screen states which metric it is (§7).
