"""Quick capture: one sentence (typed or spoken) → a proposed lead you confirm.

"Met Tunde from Kemi Stores, needs an online store, budget around 400k, 0803 123 4567, follow up Monday"
→ {company: Kemi Stores, contact_name: Tunde, service: website, value: 400000 NGN, phone: +234803…, next_action_due: …}

Local rules first (no network). The free AI model is asked only for fields the rules missed; its fields are
listed in `ai_fields` so the UI marks them "AI suggestion". Nothing is saved here."""
from __future__ import annotations

import json
import re
from datetime import date

from moyo.dates import parse_amount, parse_date
from moyo.db import today

SERVICE_WORDS = [  # (regex, service key) checked in order
    (r"\b(ai agent|chat ?bot|voice (?:agent|assistant|system)|ai (?:assistant|system))\b", "ai_agent"),
    (r"\b(automat\w*|workflow|zapier|n8n)\b", "automation"),
    (r"\b(api|integrat\w*|payment gateway|paystack integration)\b", "integration"),
    (r"\b(mobile app|web ?app|app|software|platform|dashboard|portal|crm|erp|saas|system)\b", "web_app"),
    (r"\b(website|web site|site|landing page|e-?commerce|online store|store|shop|portfolio|blog|revamp|redesign)\b", "website"),
    (r"\b(maintenance|support|retainer)\b", "maintenance"),
    (r"\b(hosting|domain|renewal)\b", "hosting"),
    (r"\b(consult\w*|advice|audit)\b", "consulting"),
]
NAME = r"[A-Z][\w'’.-]*(?:\s+(?:[A-Z][\w'’.-]*|&|and|of))*"
CONTACT_CUES = r"(?i:met|meeting with|spoke (?:to|with)|talked (?:to|with)|called|chatted with|call from|message from|dm from|referral:?)"
COMPANY_CUES = r"(?i:from|at|of|owner of|works at|ceo of|founder of|for)"
FOLLOW_CUES = r"(?:follow(?:[\s-]?up)?|call (?:him|her|them|back)?|check in|remind me|send (?:the |a )?(?:proposal|quote|invoice)|meet(?:ing)?|reach out)"


def _find_date(text: str, ref: date) -> str | None:
    words = re.split(r"\s+", text.strip())
    for n in (4, 3, 2, 1):  # longest phrase first ("next friday", "23 nov")
        for i in range(len(words) - n + 1):
            chunk = re.sub(r"[,.;!?]+$", "", " ".join(words[i:i + n]))
            try:
                d = parse_date(chunk, ref)
            except Exception:
                d = None
            if d:
                return d.isoformat()
    return None


def _find_amount(text: str):
    cands = re.findall(r"(?:₦|\$|ngn\s?|usd\s?|n)?\d[\d,]*(?:\.\d+)?\s?(?:k|m|million|thousand|naira|dollars?|usd|ngn)?\b",
                       text, re.I)
    best = None
    for c in cands:
        if re.fullmatch(r"\+?\d{9,}", c.replace(" ", "")):  # a phone number, not money
            continue
        a = parse_amount(c.strip())
        if a and (a[1] or re.search(r"[kKmM]|thousand|million|naira|dollar|₦|\$", c) or a[0] >= 10000):
            best = a
            break
    return best


def extract_local(text: str, ref: date | None = None) -> dict:
    ref = ref or today()
    t = " ".join((text or "").split())
    low = t.lower()
    out: dict = {"notes": t}
    if m := re.search(r"[\w.+-]+@[\w-]+\.[\w.]{2,}", t):
        out["email"] = m.group(0)
    if m := re.search(r"(?<![\w])(\+?\d[\d\s-]{8,}\d)(?![\w])", t):
        digits = re.sub(r"\D", "", m.group(1))
        if 10 <= len(digits) <= 15:
            out["phone"] = m.group(1).strip()
            if re.search(r"whats\s?app|wa\b", low):
                out["whatsapp"] = out["phone"]
    if a := _find_amount(t):
        out["value"], out["currency"] = a[0], (a[1] or "NGN")
    for pat, key in SERVICE_WORDS:
        if re.search(pat, low):
            out["service"] = key
            break
    if m := re.search(CONTACT_CUES + r"\s+(" + NAME + r")", t):
        name = re.split(r"\s+(?:from|at|of|who|and|,)\s*", m.group(1))[0]
        out["contact_name"] = name.strip(" .,")
    if m := re.search(r"\b" + COMPANY_CUES + r"\s+(" + NAME + r")", t):
        comp = m.group(1).strip(" .,")
        if comp and comp != out.get("contact_name"):
            out["company"] = re.sub(r"\s+(and|of)$", "", comp)
    if m := re.search(FOLLOW_CUES + r"\s+(?:on\s+|by\s+|next\s+)?(.{0,30})", t, re.I):
        d = _find_date(m.group(0), ref)
        if d:
            out["next_action_due"] = d
            out["next_action"] = re.sub(r"\s+(?:on|by)$", "", m.group(0).split(" " + m.group(1).split()[0])[0]).strip().capitalize() \
                if m.group(1) else "Follow up"
            if len(out["next_action"]) < 4 or out["next_action"].lower().startswith("follow"):
                out["next_action"] = "Follow up"
    if not out.get("company"):
        m = (re.search(r"(?i:new lead|lead:?|prospect:?)\s+(" + NAME + r")", t)
             or re.search(r"(?:^|[:,.;]\s*)(" + NAME + r")\s+(?i:wants|needs|is looking|asked|requested|would like)", t))
        if m:
            comp = re.sub(r"\s+(?:IG|DM|Instagram|TikTok|LinkedIn)\b.*$", "", m.group(1)).strip(" .,")
            if comp and comp != out.get("contact_name"):
                out["company"] = comp
    if m := re.search(r"(?i:referr(?:ed|al))(?:\s+(?i:by|from))?:?\s+(" + NAME + ")", t):
        out["source"], out["source_detail"] = "referral", m.group(1)
    elif re.search(r"\b(instagram|ig|tiktok|linkedin|twitter|x dm|dm)\b", low):
        out["source"] = "social"
    elif re.search(r"\b(reached out|messaged me|called me|inbound|found us|contacted me)\b", low):
        out["source"] = "inbound"
    elif re.search(r"\b(past client|old client|returning|renewal)\b", low):
        out["source"] = "past_client"
    if not out.get("company") and out.get("contact_name"):
        out["company"] = None  # a person can be the client; the UI asks
    return out


AI_SYSTEM = (
    "Extract a sales lead from the user's note. Reply ONLY with JSON: {\"company\": string|null, "
    "\"contact_name\": string|null, \"role\": string|null, \"need\": string|null, \"next_action\": string|null}. "
    "Use only what the note says. Never invent names, companies or needs; use null when unsure. "
    "Placeholders like PHONE_1, EMAIL_1, AMOUNT_1 are private values: ignore them.")


def extract(con, text: str, use_ai: bool = True, ref: date | None = None) -> dict:
    """Local extraction + (optional) AI for missing company/contact/need. Returns a proposal; never writes."""
    p = extract_local(text, ref)
    p["ai_fields"] = []
    missing = [k for k in ("company", "contact_name") if not p.get(k)]
    if use_ai and missing:
        safe = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]{2,}", "EMAIL_1", text)
        safe = re.sub(r"\+?\d[\d\s-]{8,}\d", "PHONE_1", safe)
        safe = re.sub(r"(?:₦|\$)\s?\d[\d,.]*\s?[kKmM]?|\b\d[\d,.]*\s?(?:k|m|million|thousand|naira|dollars?)\b", "AMOUNT_1",
                      safe, flags=re.I)
        try:
            from moyo import cloud
            res = cloud.generate_json(con, AI_SYSTEM, safe)
            data = res.get("data") if isinstance(res, dict) and "data" in res else res
            if isinstance(data, str):
                data = json.loads(data)
            for k in ("company", "contact_name", "role"):
                v = (data or {}).get(k)
                if v and not p.get(k) and "_1" not in str(v) and str(v).lower() in text.lower():
                    p[k] = str(v).strip()  # only accept names that literally appear in the note
                    p["ai_fields"].append(k)
            if (data or {}).get("need") and not p.get("need"):
                p["need"], p["ai_fields"] = data["need"], p["ai_fields"] + ["need"]
        except Exception:
            pass  # AI unavailable: the rules' result stands; the form shows what's missing
    p.setdefault("stage", "new")
    p.setdefault("source", "other")
    p["missing"] = [k for k in ("company", "contact_name", "value", "next_action_due") if not p.get(k)]
    return p


def commit(con, f: dict, actor: str = "user") -> dict:
    """Save a CONFIRMED capture: company → contact (re-used if the phone/email already exists) → deal → next step.
    One transaction; returns the deal and whether an existing contact was re-used."""
    from moyo.revenue import crm
    company_name = (f.get("company") or "").strip()
    person = (f.get("contact_name") or "").strip()
    if not company_name and not person:
        raise crm.CRMError("Tell me at least the company or the person's name.")
    con.execute("SAVEPOINT capture")
    try:
        co = crm.get_or_create_company(con, company_name or person, source="user")
        reused = None
        contact = None
        for kind in ("whatsapp", "phone", "email"):
            if f.get(kind):
                ex = crm.find_contact_by_channel(con, kind, f[kind])
                if ex:
                    contact, reused = ex, ex["full_name"]
                    break
        if not contact and person:
            contact = crm.create_contact(con, person, company_id=co["id"], phone=f.get("phone"),
                                         whatsapp=f.get("whatsapp") if f.get("whatsapp") != f.get("phone") else None,
                                         email=f.get("email"), role=f.get("role"), source="user")
        elif not contact and (f.get("phone") or f.get("email")):
            contact = crm.create_contact(con, company_name, company_id=co["id"], phone=f.get("phone"),
                                         email=f.get("email"), source="user")
        svc_label = None
        if f.get("service"):
            r = con.execute("SELECT label FROM services WHERE key=?", (f["service"],)).fetchone()
            svc_label = r["label"] if r else f["service"]
        title = f.get("title") or f"{co['name']} · {svc_label or f.get('need') or 'opportunity'}"
        d = crm.create_deal(con, title, company_id=co["id"], contact_id=contact["id"] if contact else None,
                            value=f.get("value"), currency=f.get("currency") or "NGN", stage_k=f.get("stage") or "new",
                            service=f.get("service"), source=f.get("source") or "other", source_detail=f.get("source_detail"),
                            next_action=f.get("next_action") or ("Follow up" if f.get("next_action_due") else None),
                            next_action_due=f.get("next_action_due"), notes=f.get("need"), actor=actor)
        if f.get("notes"):
            crm.log_activity(con, "note", f["notes"], deal_id=d["id"], source=actor)
        if d["next_action_due"]:
            crm.sync_deal_followup(con, d["id"])
        con.execute("RELEASE capture")
    except Exception:
        con.execute("ROLLBACK TO capture")
        con.execute("RELEASE capture")
        raise
    return {"deal": crm.get_deal(con, d["id"]), "reused_contact": reused}


def summary_text(f: dict) -> str:
    bits = [f"Company: {f.get('company') or '(none: the person is the client)'}",
            f"Contact: {f.get('contact_name') or 'not given'}" + (f" ({f['role']})" if f.get("role") else "")]
    for k, label in (("phone", "Phone"), ("email", "Email"), ("service", "Need"), ("stage", "Stage")):
        if f.get(k):
            bits.append(f"{label}: {f[k]}")
    if f.get("value"):
        bits.append(f"Value: {f['value']:,.0f} {f.get('currency') or 'NGN'}")
    if f.get("next_action_due"):
        bits.append(f"Next: {f.get('next_action') or 'Follow up'} on {f['next_action_due']}")
    if f.get("ai_fields"):
        bits.append("AI-suggested (check): " + ", ".join(f["ai_fields"]))
    return "Save this lead?\n" + "\n".join(bits)


def normalize(f: dict) -> dict:
    """Voice/AI may pass "400k" or "₦400,000" as text: convert once, before showing or saving."""
    f = {k: v for k, v in (f or {}).items() if v not in (None, "", [])}
    v = f.get("value")
    if isinstance(v, str):
        a = parse_amount(v)
        if a:
            f["value"], f["currency"] = a[0], a[1] or f.get("currency") or "NGN"
        else:
            f.pop("value")
    if f.get("next_action_due"):
        try:
            date.fromisoformat(f["next_action_due"])
        except ValueError:
            d = parse_date(f["next_action_due"], today())
            f["next_action_due"] = d.isoformat() if d else None
    return f
