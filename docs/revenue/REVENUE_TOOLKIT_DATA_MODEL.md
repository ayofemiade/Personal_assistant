# Revenue Toolkit: Data Model

Status: DRAFT for review. Target: the existing **SQLite** database (`data/moyo.db`, WAL mode, foreign keys ON, daily backups *(exists)*).
The database is the only source of truth. WhatsApp, Gmail, Paystack and AI models are inputs, never the truth.

## 1. Principles

1. **Money is integer minor units.** `amount_minor INTEGER` (kobo for NGN, cents for USD) plus `currency TEXT`. There are no floats in the ledger. (The current `earnings` table uses REAL. It's empty, so we switch before any data exists.)
2. **Original currency is always kept.** Every money row stores `fx_ngn_per_usd` (the rate on its date) and `usd_minor` **at the time it's written**. Changing the rate later never rewrites history.
3. **The ledger is append-only.** Issued invoices, payments, refunds and expenses are never edited or deleted. Corrections are new `adjustments` rows that point at the original, with a reason. Only **drafts** can be edited.
4. **Commercial ≠ financial.** Deals (commitments) and the ledger (invoices, payments) are separate tables. Winning a deal creates no money rows.
5. **Provenance on facts:** `source` (`user` | `import` | `whatsapp` | `email` | `ai`) and `confirmed` (0/1). AI-derived values stay `confirmed=0` until you accept them.
6. **Soft delete** for people and deals (`archived_at`). Hard delete is only for drafts and your explicit "erase this person" request (privacy).
7. **Time:** all timestamps are stored as local ISO strings with the offset (`Africa/Lagos`, +01:00). Dates (due/earned) are plain `YYYY-MM-DD`.
8. **Idempotency:** every external event (webhook, import, sync) carries an `external_id` with a UNIQUE constraint, so replays are no-ops.

## 2. Entities

### People & organisations
```
companies(id PK, name, name_norm UNIQUE*, industry, location, website, socials JSON, notes,
          source, confirmed, created_at, updated_at, archived_at)            *unique among non-archived
contacts(id PK, company_id FK→companies NULL, full_name, role, notes, consent_status
          ('unknown'|'opted_in'|'opted_out'), opted_out_at, source, confirmed, created_at, updated_at, archived_at)
contact_channels(id PK, contact_id FK→contacts ON DELETE CASCADE, kind ('phone'|'whatsapp'|'email'|'instagram'|'linkedin'|'other'),
          value, value_norm, is_primary, verified, UNIQUE(kind, value_norm))
```
- `value_norm`: phones in E.164 (`0803…` → `+234803…`), lower-cased emails. The UNIQUE constraint is what makes duplicates impossible. A clash produces a **merge suggestion**.
- `merge_log(id, kept_contact_id, merged_contact_id, snapshot JSON, at)` makes merges reversible.

### Sales
```
pipeline_stages(id PK, key UNIQUE, label, position, is_open, is_won, is_lost, default_probability, stale_after_days)
services(id PK, key UNIQUE, label, default_price_minor, currency, recurring ('none'|'monthly'|'yearly'))
deals(id PK, company_id FK, primary_contact_id FK, title, service_id FK NULL, value_minor, currency,
      probability (0-100, NULL = stage default), probability_source ('stage'|'user'|'ai'),
      stage_key FK→pipeline_stages.key, source ('referral'|'inbound'|'social'|'outreach'|'past_client'|'other'),
      source_detail, expected_close, next_action, next_action_due, lost_reason, won_at, lost_at,
      created_at, updated_at, archived_at)
deal_contacts(deal_id, contact_id, role, PRIMARY KEY(deal_id, contact_id))
stage_history(id, deal_id FK, from_stage, to_stage, at, actor)
```

### Activity & conversations
```
activities(id PK, kind ('note'|'call'|'meeting'|'message_in'|'message_out'|'email_in'|'email_out'|
           'proposal_sent'|'invoice_sent'|'payment'|'stage_change'|'commitment'),
           channel ('whatsapp'|'email'|'phone'|'in_person'|'instagram'|'other'|NULL),
           contact_id, company_id, deal_id, occurred_at, summary, body_ref, direction, source, confirmed,
           external_id UNIQUE NULL, created_at)
conversations(id PK, contact_id FK, channel, external_thread_id, imported_from ('paste'|'export'|'api'), created_at,
              UNIQUE(channel, external_thread_id))
messages(id PK, conversation_id FK, direction, sender_label, sent_at, text, status ('draft'|'handed_off'|'sent'|
         'delivered'|'read'|'failed'), external_id UNIQUE NULL, cost_minor NULL, cost_currency NULL)
consents(id PK, contact_id FK, channel, status, evidence, at)      -- opt-in / opt-out history
follow_ups(id PK, deal_id NULL, contact_id NULL, due_date, reason, status ('open'|'done'|'snoozed'|'dismissed'),
           snoozed_until, dismissed_reason, created_by ('user'|'rule'|'ai'), confirmed, done_activity_id NULL)
```
- The existing `tasks` table *(exists)* stays for general to-dos. Follow-ups get their own table because they need scoring, snooze and dismiss reasons.
- The existing `emails` table *(exists)* links to contacts through `contact_channels` (email) instead of the current name-matching against `leads`.

### Proposals
```
proposals(id PK, deal_id FK, number UNIQUE, status ('draft'|'approved'|'sent'|'accepted'|'rejected'|'expired'),
          current_version_id, valid_until, created_at)
proposal_versions(id PK, proposal_id FK, version INT, content JSON, total_minor, currency, pdf_path, created_at,
          UNIQUE(proposal_id, version))     -- immutable once status ≥ sent
```

### Ledger (financial, append-only)
```
invoices(id PK, number UNIQUE, deal_id FK NULL, company_id FK, contact_id NULL, issue_date, due_date, currency,
         status ('draft'|'issued'|'void'), issued_at, void_reason, pdf_path, fx_ngn_per_usd, created_at)
invoice_lines(id PK, invoice_id FK, position, category, description, qty, unit_minor, amount_minor,
         kind ('service'|'pass_through'|'discount'), service_id NULL)
payments(id PK, received_date, amount_minor, currency, method ('bank_transfer'|'paystack'|'cash'|'other'),
         reference, payer_label, contact_id NULL, company_id NULL, fx_ngn_per_usd, usd_minor,
         external_id UNIQUE NULL, created_at)
payment_allocations(id PK, payment_id FK, invoice_id FK, amount_minor, created_at)   -- partial payments
refunds(id PK, payment_id FK, date, amount_minor, reason, fx_ngn_per_usd, usd_minor, created_at)
expenses(id PK, date, amount_minor, currency, category ('direct'|'pass_through'|'opex'), description,
         vendor, deal_id NULL, invoice_line_id NULL, fx_ngn_per_usd, usd_minor, receipt_path, created_at)
adjustments(id PK, target_table, target_id, field, old_value, new_value, reason, actor, at)   -- corrections
revenue_recognitions(id PK, invoice_line_id FK, recognised_on, amount_minor, currency, fx_ngn_per_usd,
         usd_minor, rule ('on_issue'|'on_delivery'|'on_payment'), reversed_by NULL, created_at)
fx_rates(date PK, ngn_per_usd, source ('user'), set_at)
```
- **Status is derived, not stored**, for paid/part-paid/overdue: `outstanding = Σ lines − Σ allocations`. One function computes it, so it can never drift.
- `revenue_recognitions` feeds the **$10K earned** figure. Pass-through lines and refunds are excluded. The recognition rule is Decision D-1.
- Totals are computed in code from lines. A stored total, if kept for speed, must match on every read (test).

### Intelligence & system
```
revenue_targets(id PK, label, start, end, amount_minor, currency, basis ('earned'|'collected'|'contracted'), exclusions JSON)
recommendations(id PK, kind, subject_table, subject_id, title, why, evidence JSON(record refs), expected_benefit,
                next_action, uncertainty, score, status ('shown'|'accepted'|'snoozed'|'dismissed'), feedback, created_at)
integration_accounts(id PK, provider, label, status, scopes, secret_ref (→ Windows Credential Manager), created_at)
webhook_events(id PK, provider, external_id UNIQUE, received_at, payload_hash, status ('new'|'processed'|'failed'),
               error, processed_at)        -- raw payloads not stored long-term (privacy)
audit_log  (exists)                          -- every write via the Tool Gateway, actor + tier
```

## 3. Constraints & indexes (key ones)
- UNIQUE: `contact_channels(kind, value_norm)`, `invoices.number`, `proposals.number`, every `external_id`, `webhook_events(provider, external_id)`.
- CHECK: `amount_minor > 0` on payments, refunds and expenses. Allocations ≤ payment amount (enforced in the transaction). Refund ≤ payment.
- Indexes: `deals(stage_key, next_action_due)`, `follow_ups(status, due_date)`, `activities(contact_id, occurred_at)`, `activities(deal_id, occurred_at)`, `payments(received_date)`, `invoices(status, due_date)`.
- Deletion: companies, contacts and deals are archived, never deleted, so the ledger keeps its references (FKs `ON DELETE RESTRICT` on ledger tables).

## 4. Transactions
- Each of these is a single SQLite transaction (`BEGIN IMMEDIATE`): issue invoice, record payment + allocations, refund, void, adjustment, merge contacts.
- Issuing an invoice snapshots the fx rate and lines, sets `issued_at`, writes `revenue_recognitions` if the rule is `on_issue`, and writes an audit entry.

## 5. Migration from what exists
| Existing *(exists)* | Rows today | Plan |
|---|---|---|
| `leads` | 0 | Replaced by companies + contacts + deals. `add_lead`/`update_lead` actions are kept as wrappers so voice and typed commands still work |
| `earnings` (REAL) | 0 | Replaced by the ledger. `log_payment` becomes "record payment" (confirm tier kept) |
| `invoices` (new today) | 1 | Moved into `invoices` + `invoice_lines` (converted to minor units). The PDF path is kept |
| `emails.lead_id` | 60 rows | Re-linked through `contact_channels` |
| `tasks.lead_id` | 0 | Kept. Optional `deal_id` added |
| Past invoices (PDF/Word, outside Moyo) | n/a | Optional import as **historical** clients/deals/invoices dated before the challenge, so they're excluded from the target. This gives a real average deal size and renewal reminders |

Before migrating: a backup (automatic daily backup *(exists)* plus an explicit pre-migration copy).
