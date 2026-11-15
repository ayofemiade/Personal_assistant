"""Revenue Toolkit tables (docs/revenue/REVENUE_TOOLKIT_DATA_MODEL.md).

Money is stored as INTEGER minor units (kobo / cents) with the original currency and a per-row
exchange-rate snapshot. Ledger rows are append-only; corrections go to `adjustments`.
"""
from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_norm TEXT NOT NULL,
    industry TEXT, location TEXT, website TEXT, socials TEXT, notes TEXT,
    source TEXT NOT NULL DEFAULT 'user', confirmed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_companies_name ON companies(name_norm) WHERE archived_at IS NULL;

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    full_name TEXT NOT NULL,
    role TEXT, notes TEXT,
    consent_status TEXT NOT NULL DEFAULT 'unknown' CHECK (consent_status IN ('unknown','opted_in','opted_out')),
    opted_out_at TEXT,
    source TEXT NOT NULL DEFAULT 'user', confirmed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_contacts_company ON contacts(company_id);

CREATE TABLE IF NOT EXISTS contact_channels (
    id INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('phone','whatsapp','email','instagram','linkedin','other')),
    value TEXT NOT NULL, value_norm TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0, verified INTEGER NOT NULL DEFAULT 0,
    UNIQUE(kind, value_norm)
);

CREATE TABLE IF NOT EXISTS merge_log (
    id INTEGER PRIMARY KEY, kept_contact_id INTEGER NOT NULL, merged_contact_id INTEGER NOT NULL,
    snapshot TEXT NOT NULL, at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_stages (
    key TEXT PRIMARY KEY, label TEXT NOT NULL, position INTEGER NOT NULL,
    is_open INTEGER NOT NULL, is_won INTEGER NOT NULL DEFAULT 0, is_lost INTEGER NOT NULL DEFAULT 0,
    default_probability INTEGER NOT NULL, stale_after_days INTEGER
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
    default_price_minor INTEGER, currency TEXT,
    recurring TEXT NOT NULL DEFAULT 'none' CHECK (recurring IN ('none','monthly','yearly'))
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    primary_contact_id INTEGER REFERENCES contacts(id),
    title TEXT NOT NULL,
    service_id INTEGER REFERENCES services(id),
    value_minor INTEGER, currency TEXT NOT NULL DEFAULT 'NGN',
    probability INTEGER CHECK (probability IS NULL OR probability BETWEEN 0 AND 100),
    probability_source TEXT NOT NULL DEFAULT 'stage',
    stage_key TEXT NOT NULL REFERENCES pipeline_stages(key),
    source TEXT NOT NULL DEFAULT 'other',
    source_detail TEXT, expected_close TEXT,
    next_action TEXT, next_action_due TEXT,
    notes TEXT, lost_reason TEXT, won_at TEXT, lost_at TEXT, historical INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_deals_stage ON deals(stage_key, next_action_due);

CREATE TABLE IF NOT EXISTS deal_contacts (
    deal_id INTEGER NOT NULL REFERENCES deals(id), contact_id INTEGER NOT NULL REFERENCES contacts(id), role TEXT,
    PRIMARY KEY (deal_id, contact_id)
);

CREATE TABLE IF NOT EXISTS stage_history (
    id INTEGER PRIMARY KEY, deal_id INTEGER NOT NULL REFERENCES deals(id),
    from_stage TEXT, to_stage TEXT NOT NULL, at TEXT NOT NULL, actor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('note','call','meeting','message_in','message_out','email_in','email_out',
        'proposal_sent','invoice_sent','payment','stage_change','commitment','created')),
    channel TEXT, contact_id INTEGER REFERENCES contacts(id), company_id INTEGER REFERENCES companies(id),
    deal_id INTEGER REFERENCES deals(id),
    occurred_at TEXT NOT NULL, summary TEXT NOT NULL, direction TEXT,
    source TEXT NOT NULL DEFAULT 'user', confirmed INTEGER NOT NULL DEFAULT 1,
    external_id TEXT UNIQUE, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_act_contact ON activities(contact_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_act_deal ON activities(deal_id, occurred_at);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY, contact_id INTEGER REFERENCES contacts(id), channel TEXT NOT NULL,
    external_thread_id TEXT, imported_from TEXT NOT NULL, title TEXT, summary TEXT, created_at TEXT NOT NULL,
    UNIQUE(channel, external_thread_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    direction TEXT, sender_label TEXT, sent_at TEXT, text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent', external_id TEXT UNIQUE, cost_minor INTEGER, cost_currency TEXT
);
CREATE TABLE IF NOT EXISTS consents (
    id INTEGER PRIMARY KEY, contact_id INTEGER NOT NULL REFERENCES contacts(id), channel TEXT NOT NULL,
    status TEXT NOT NULL, evidence TEXT, at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id INTEGER PRIMARY KEY, deal_id INTEGER REFERENCES deals(id), contact_id INTEGER REFERENCES contacts(id),
    due_date TEXT NOT NULL, reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','snoozed','dismissed')),
    snoozed_until TEXT, dismissed_reason TEXT,
    created_by TEXT NOT NULL DEFAULT 'user', confirmed INTEGER NOT NULL DEFAULT 1,
    done_activity_id INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fu_status ON follow_ups(status, due_date);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY, deal_id INTEGER REFERENCES deals(id), number TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','sent','accepted','rejected','expired')),
    current_version_id INTEGER, valid_until TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposal_versions (
    id INTEGER PRIMARY KEY, proposal_id INTEGER NOT NULL REFERENCES proposals(id), version INTEGER NOT NULL,
    content TEXT NOT NULL, total_minor INTEGER, currency TEXT, pdf_path TEXT, created_at TEXT NOT NULL,
    UNIQUE(proposal_id, version)
);

-- ledger (append-only; Phase 2 logic) ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS ledger_invoices (
    id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE,
    deal_id INTEGER REFERENCES deals(id), company_id INTEGER REFERENCES companies(id),
    contact_id INTEGER REFERENCES contacts(id), bill_to TEXT,
    issue_date TEXT NOT NULL, due_date TEXT, currency TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','void')),
    issued_at TEXT, void_reason TEXT, pdf_path TEXT, fx_ngn_per_usd REAL, historical INTEGER NOT NULL DEFAULT 0,
    payment_status_known INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_invoice_lines (
    id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES ledger_invoices(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL, category TEXT, description TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 1,
    unit_minor INTEGER NOT NULL, amount_minor INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'service' CHECK (kind IN ('service','pass_through','discount')),
    service_id INTEGER REFERENCES services(id)
);
CREATE TABLE IF NOT EXISTS ledger_payments (
    id INTEGER PRIMARY KEY, received_date TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL, method TEXT NOT NULL DEFAULT 'bank_transfer', reference TEXT, payer_label TEXT,
    contact_id INTEGER REFERENCES contacts(id), company_id INTEGER REFERENCES companies(id),
    fx_ngn_per_usd REAL, usd_minor INTEGER, external_id TEXT UNIQUE, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_allocations (
    id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL REFERENCES ledger_payments(id) ON DELETE RESTRICT,
    invoice_id INTEGER NOT NULL REFERENCES ledger_invoices(id) ON DELETE RESTRICT,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_refunds (
    id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL REFERENCES ledger_payments(id) ON DELETE RESTRICT,
    date TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK (amount_minor > 0), reason TEXT NOT NULL,
    fx_ngn_per_usd REAL, usd_minor INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_expenses (
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency TEXT NOT NULL, category TEXT NOT NULL CHECK (category IN ('direct','pass_through','opex')),
    description TEXT NOT NULL, vendor TEXT, deal_id INTEGER REFERENCES deals(id),
    fx_ngn_per_usd REAL, usd_minor INTEGER, receipt_path TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_adjustments (
    id INTEGER PRIMARY KEY, target_table TEXT NOT NULL, target_id INTEGER NOT NULL, field TEXT NOT NULL,
    old_value TEXT, new_value TEXT, reason TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fx_rates (date TEXT PRIMARY KEY, ngn_per_usd REAL NOT NULL, source TEXT NOT NULL, set_at TEXT NOT NULL);

-- intelligence & integrations ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, subject_table TEXT, subject_id INTEGER, title TEXT NOT NULL,
    why TEXT, evidence TEXT, expected_benefit TEXT, next_action TEXT, uncertainty TEXT, score REAL,
    status TEXT NOT NULL DEFAULT 'shown', feedback TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS integration_accounts (
    id INTEGER PRIMARY KEY, provider TEXT NOT NULL, label TEXT, status TEXT, scopes TEXT, secret_ref TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_events (
    id INTEGER PRIMARY KEY, provider TEXT NOT NULL, external_id TEXT NOT NULL, received_at TEXT NOT NULL,
    payload_hash TEXT, status TEXT NOT NULL DEFAULT 'new', error TEXT, processed_at TEXT,
    UNIQUE(provider, external_id)
);
"""

STAGES = [  # key, label, position, open, won, lost, probability (estimate), stale after days
    ("new", "New lead", 1, 1, 0, 0, 10, 2),
    ("contacted", "Contacted", 2, 1, 0, 0, 15, 3),
    ("engaged", "Engaged", 3, 1, 0, 0, 25, 4),
    ("discovery", "Discovery", 4, 1, 0, 0, 35, 4),
    ("proposal", "Proposal sent", 5, 1, 0, 0, 50, 4),
    ("negotiation", "Negotiation", 6, 1, 0, 0, 70, 2),
    ("won", "Won", 7, 0, 1, 0, 100, None),
    ("lost", "Lost", 8, 0, 0, 1, 0, None),
    ("nurture", "Nurture", 9, 0, 0, 0, 5, 30),
]

SERVICES = [
    ("website", "Website design & development", "none"),
    ("web_app", "Custom software / web app", "none"),
    ("ai_agent", "AI agent / voice system", "none"),
    ("automation", "Business automation", "none"),
    ("integration", "API integration", "none"),
    ("consulting", "Technical consulting", "none"),
    ("maintenance", "Maintenance & support", "yearly"),
    ("hosting", "Hosting & domain", "yearly"),
    ("other", "Other", "none"),
]


def ensure(con) -> None:
    con.executescript(SCHEMA)
    con.executemany("INSERT OR IGNORE INTO pipeline_stages(key, label, position, is_open, is_won, is_lost, "
                    "default_probability, stale_after_days) VALUES (?,?,?,?,?,?,?,?)", STAGES)
    con.executemany("INSERT OR IGNORE INTO services(key, label, recurring) VALUES (?,?,?)", SERVICES)
    migrate_legacy_leads(con)
    from moyo.revenue import ledger
    ledger.ensure_columns(con)
    con.executescript("""CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE, client TEXT NOT NULL,
        bill_to TEXT, issue_date TEXT NOT NULL, due_date TEXT, currency TEXT NOT NULL DEFAULT 'NGN', items TEXT NOT NULL,
        discount REAL NOT NULL DEFAULT 0, deposit_pct INTEGER, layout TEXT NOT NULL, notes TEXT, subtotal REAL NOT NULL,
        total REAL NOT NULL, status TEXT NOT NULL DEFAULT 'draft', pdf_path TEXT, created_at TEXT NOT NULL);""")
    ledger.migrate_legacy_invoices(con)


def migrate_legacy_leads(con) -> int:
    """One-time: copy rows from the pre-D41 `leads` table into companies + deals (kept, not deleted)."""
    if not con.execute("SELECT name FROM sqlite_master WHERE name='leads'").fetchone():
        return 0
    done = {r[0] for r in con.execute("SELECT source_detail FROM deals WHERE source_detail LIKE 'legacy-lead:%'")}
    from moyo.revenue import crm
    n = 0
    stage_map = {"qualified": "engaged"}
    for l in con.execute("SELECT * FROM leads").fetchall():
        key = f"legacy-lead:{l['id']}"
        if key in done:
            continue
        co = crm.get_or_create_company(con, l["name"], source="import")
        cid = None
        if l["contact"]:
            kind = "email" if "@" in l["contact"] else "phone"
            try:
                ex = crm.find_contact_by_channel(con, kind, l["contact"])
                cid = ex["id"] if ex else crm.create_contact(con, l["name"], company_id=co["id"], **{kind: l["contact"]})["id"]
            except crm.CRMError:
                cid = None
        d = crm.create_deal(con, f"{l['name']} · {l['service']}" if l["service"] else l["name"], company_id=co["id"],
                            contact_id=cid, value=l["value"], currency=l["currency"] or "NGN",
                            stage_k=stage_map.get(l["stage"], l["stage"]), service=None, source=l["source"] or "other",
                            source_detail=key, next_action="Follow up" if l["next_followup"] else None,
                            next_action_due=l["next_followup"], notes=l["notes"], actor="migration",
                            created_at=l["created_at"])
        if l["next_followup"]:
            crm.sync_deal_followup(con, d["id"])
        n += 1
    return n
