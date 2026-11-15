# Revenue Toolkit: Roadmap

Status: DRAFT for review. Each phase ends with a demo on real screens, passing tests, and your sign-off before the next one starts.
The order is driven by the $10K math: **capture and follow-up discipline first** (it creates revenue). **Getting paid** comes second (it protects revenue). **Insight** comes third (it improves revenue). **Paid channels** come last.

## Phase 0: Decisions & foundation (short)
- You answer the decisions in the blueprint (recognition rule, pass-through, history import, AI on chats, stale thresholds).
- Pre-migration backup. Create the new tables (data model §2) and migrate the empty `leads`/`earnings` and the 1 invoice.
- Optional: import your 5 past invoices as **historical** clients (before 8 Nov, so excluded from the $10K).
- **Done when:** schema tests pass, existing features unchanged (full suite green), backup restorable.

## Phase 1: Capture & follow-up discipline ★ MVP
1. Companies/contacts/deals with duplicate prevention (E.164/email) and confirm-to-merge.
2. **Quick capture** by typing or voice → confirmation card (AI fields marked unconfirmed).
3. Pipeline board + list. Stage changes logged. "No next step" flag.
4. Follow-up engine: transparent scoring, a "Who to contact today" list, done/snooze/reschedule/dismiss.
5. Drafts → **Open in WhatsApp** (wa.me) / **Open in Gmail** → "Sent?" → logged + next action.
6. WhatsApp **chat export/paste import** → contact timeline → summary + commitments for confirmation.
7. Gmail sync links inbound emails to contact timelines.
8. Revenue section in the morning brief, orb and voice ("who should I follow up with?", "add lead…").
- **Done when:** acceptance criteria 1–6 and 8 in the PRD pass, and you've used it for real for 3 days.

## Phase 2: Proposals & getting paid
1. Ledger: invoices + lines (pass-through flag) tied to deals; **Issue** (confirm tier) with fx snapshot.
2. Payments with partial allocation, method and reference; refunds; adjustments (append-only).
3. Outstanding/overdue view + reminders ("Kemi Stores: ₦150,000 balance, 9 days overdue").
4. **$10K challenge recomputed from the ledger** using the agreed recognition rule.
5. Proposals/quotations: templates in house style, versions, status (you send).
6. Renewals: yearly/monthly services create renewal reminders (e.g. a client's yearly hosting).
- **Done when:** PRD criterion 7 passes, with ledger tests exact to the kobo/cent.

## Phase 3: Profit & insight
1. Expenses (direct / pass-through / opex), gross and net profit, profit by service.
2. Analytics with definitions and sample-size guards: sources, conversion by stage, win rate, cycle, average deal, loss reasons.
3. Strategist: pipeline health, "deals needed at current average", deal-size levers, experiments; recommendation feedback loop.
4. Bank-statement CSV reconciliation (optional).

## Phase 4: Channels (only if justified, each opt-in and costed)
- WhatsApp Cloud API on a **dedicated** number (inbound sync, approved sending, opt-out handling, cost tracking per message).
- Paystack payment links + signed webhooks → auto-recorded payments.
- Gmail drafts (`gmail.compose`).
- Cloudflare Tunnel for webhooks. Signature verification and idempotent processing.

## Dependencies
Phase 1 → 2 (deals exist before invoices link to them) → 3 (needs ledger data). Phase 4 is independent but needs the Phase 1 conversation tables.

## Risks
| Risk | Impact | Mitigation |
|---|---|---|
| **Data entry fatigue** (the system stays empty, as today) | Whole toolkit useless | Voice/one-line capture, chat import, Gmail auto-logging, brief prompts "anything new from today?" |
| AI extracts wrong facts | Bad decisions | Provenance + confirmation, never auto-fact |
| Gemini free-tier limits | Drafts/summaries unavailable | Rules work offline; model fallback chain *(exists)*; drafts have a template fallback |
| Money logic errors | Wrong financial picture | Integer minor units, one derivation function, property tests, append-only |
| WhatsApp costs/eligibility change | Phase 4 cost | Phase 1 is independent of the API; re-research before Phase 4 |
| Scope creep | Delays revenue impact | Phase gates, MVP first, "does it make money?" test |
| Laptop is the single point of failure | Data loss | Daily backups *(exists)* + recommended weekly copy to cloud drive (your choice) |

## Testing per phase
See `REVENUE_TOOLKIT_TEST_STRATEGY.md`. Every phase also gets an on-screen check (desktop/phone widths, dark/light) and an audit-log review.
