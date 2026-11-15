# Revenue Toolkit: System Architecture

Status: DRAFT for review. This design **extends** Moyo as it exists today. Nothing working gets rewritten.

## 1. What exists and is reused (inspected 13 Nov 2026)

| Part | Today | Reuse |
|---|---|---|
| Runtime | Python 3.13, FastAPI on `127.0.0.1:8765`, started at login (`--no-window`) | ✔ unchanged |
| Storage | SQLite WAL `data/moyo.db`, daily backups, settings table | ✔ new tables + migration |
| Safety | **Tool Gateway** `actions.py`: tiers read/low/confirm/prohibited, pending confirmations, audit log | ✔ every revenue write goes through it |
| AI | `cloud.py`: Gemini free tier → Groq fallback, **Redactor** (client names/amounts → placeholders, restored locally), numeric validation in `coach.py` | ✔ strategist + drafting reuse it |
| Voice | Gemini Live conversation (`voice.py`), offline Vosk wake/confirm, half-duplex, untrusted-content taint | ✔ "who should I follow up with?", quick capture by voice |
| Brief/reminders | `briefing.py`, `reminders.py` (dedupe keys, quiet hours, toasts) | ✔ revenue section + follow-up/overdue reminders |
| Gmail | read-only metadata sync every 15 min; bodies on demand | ✔ auto-log emails to contact timelines |
| Documents | invoice PDFs in house style via headless Chrome (`invoices.py`) | ✔ proposals use the same renderer |
| UI | vanilla JS SPA, design system (saffron/ink, Fraunces + Inter), sidebar | ✔ new "Revenue" area, same components |

## 2. Component view

```
                ┌──────────────── Moyo desktop (this laptop) ────────────────┐
 You ──typed──▶ │ Command bar / forms ─┐                                      │
 You ──voice──▶ │ Orb (Gemini Live) ───┼─▶ Tool Gateway (tiers, confirm, audit)│
                │                      │        │                             │
                │  Revenue services:   ▼        ▼                             │
                │  capture · crm · pipeline · followups · proposals · ledger  │
                │  · analytics · strategist                                    │
                │            │                     ▲                           │
                │            ▼                     │ rules + scores            │
                │        SQLite (source of truth) ─┘                           │
                │            ▲          ▲            ▲                         │
                │   Gmail sync    WhatsApp import   (later) webhook inbox      │
                └────────────│──────────│────────────│─────────────────────────┘
                             │          │            │  public HTTPS only in Phase 4
                         Google     your phone   Cloudflare Tunnel → Meta / Paystack
 Outbound: Moyo never sends. It opens wa.me / Gmail compose pre-filled; YOU press send.
```

Package layout (new): `moyo/revenue/{models.py, crm.py, pipeline.py, followups.py, ledger.py, proposals.py, analytics.py, strategist.py, importers.py, channels.py}`. Each module exposes plain functions. `actions.py` registers them with tiers.

## 3. Key technical decisions

| # | Decision | Why | Alternative rejected |
|---|---|---|---|
| T1 | Stay local: SQLite + FastAPI on the laptop | $0, private, already reliable, single user | Supabase/Postgres cloud: extra cost/complexity, data leaves the laptop |
| T2 | Integer minor units + per-row fx snapshot | exact money, history never rewritten | REAL/float (current `earnings`): rounding drift |
| T3 | Append-only ledger + `adjustments` | auditability, the spec's "no destructive edits" rule | editable rows |
| T4 | Derived statuses (paid/overdue) computed in one function | can't drift out of sync | stored status flags |
| T5 | Rules first, AI second for prioritisation | explainable, testable, works offline/when quota is exhausted | LLM ranking (opaque, invents) |
| T6 | AI drafts with placeholders (Redactor), names restored locally | typed/drafting path keeps client data local (D7) | sending raw CRM to the cloud |
| T7 | Assisted sending (wa.me / Gmail compose) in Phase 1 | official, free, works with your *current* WhatsApp number, keeps a human in the loop | WhatsApp Cloud API now: costs ₦/msg, needs a new number in Nigeria, public endpoint |
| T8 | Webhooks only through Cloudflare Tunnel (Phase 4) with signature checks | laptop isn't publicly reachable; free tunnel, no open ports | port-forwarding, unofficial relays |
| T9 | Duplicate prevention by normalised channels (E.164/email) + confirm-to-merge | one coherent history per person | fuzzy auto-merge (silent errors) |

## 4. Data flows

**Quick capture:** text/voice → local parser (names, phones, amounts, dates *(exists: `dates.py`, `commands.py`)*) → if needed AI extraction on redacted text → **confirmation card** (fields marked "AI suggestion") → on confirm: company/contact/deal/follow-up are written in one transaction, plus audit.

**Follow-up loop:** nightly and on change: the rule engine scores open deals → `follow_ups` + `recommendations` → morning brief/orb/Today list → you pick **Draft** → strategist drafts (placeholders → restored) → you edit → **Open in WhatsApp/Gmail** → you send → "Sent?" → `activities(message_out)` + new next action.

**Conversation import:** WhatsApp "Export chat" `.txt` / paste → parser (date, sender, text; Nigerian date formats) → `conversations/messages` (dedupe by hash) → summary + commitments proposed (AI on that text only, consent per import, see Decision D-6) → you confirm → follow-ups/notes.

**Money:** invoice draft → **Issue** (confirm tier) → snapshot + recognition (rule D-1) → payment recorded (confirm tier) → allocations → derived outstanding → challenge/analytics read only from the ledger.

## 5. Security boundaries
- **Trust zones:** (1) you and the UI, (2) Moyo's server and DB, (3) external content: WhatsApp text, emails, imported files and AI output are **untrusted data**. Zone 3 can never trigger a write by itself. Writes come only from your confirmation, or from low-tier actions you initiated. After untrusted content is read in a voice session, writes need confirmation *(exists: taint rule)*.
- **Local API guard** *(exists)*: Host/Origin checks, `X-Moyo` header on writes, binding to 127.0.0.1.
- **Secrets:** Windows Credential Manager *(exists)*. Never in the DB, logs or git.
- **Logs:** voice/diagnostic logs never contain message content *(exists pattern)*. The audit log stores IDs, not message bodies.
- **Prompt injection:** AI receives conversation text wrapped as quoted data with an instruction never to follow it. AI output is only ever *proposals* that pass through the confirmation UI.
- **Phase 4 webhooks:** verify `X-Hub-Signature-256` (Meta) / `x-paystack-signature`, idempotent by `external_id`, payload discarded after processing (only the fields we need are kept).

## 6. AI capabilities and limits
| Capability | Engine | Data sent | Guard |
|---|---|---|---|
| Field extraction from notes | local parser → Gemini free tier on redacted text | redacted text | confirmation card |
| Follow-up drafts | Gemini (redacted, placeholders restored locally) | stage, last-touch summary, service | you edit/send |
| Conversation summary/commitments | Gemini on the imported text (D-6) | that conversation only | proposals need confirmation |
| Prioritisation | **rules** (score factors visible) | none | n/a |
| Revenue brief & insights | rules + numbers; Gemini only for wording | aggregates + redacted | numbers validated against DB *(exists: coach validation)* |
| Probabilities | stage defaults you can edit; **never presented as statistics** | n/a | label "estimate" |
