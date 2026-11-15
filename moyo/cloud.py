"""Cloud fallback (Gemini free tier) for requests the local parser can't handle.

Privacy: known client/lead names and money amounts are replaced with placeholders BEFORE
anything leaves the laptop, and restored locally in the model's tool arguments.
The model can only propose actions; they still go through the Tool Gateway (tiers + confirmation)."""
from __future__ import annotations

import re

from moyo.actions import REGISTRY
from moyo.db import get_setting, rows, today

S, N = {"type": "STRING"}, {"type": "NUMBER"}
DATE = {"type": "STRING", "description": "ISO date YYYY-MM-DD"}
DECLS = [
    {"name": "get_daily_plan", "description": "Today's plan, priorities, what to work on."},
    {"name": "get_briefing", "description": "The full morning briefing."},
    {"name": "get_target_progress", "description": "Progress toward the $10K earnings target, pace, pipeline."},
    {"name": "get_content_status", "description": "Whether TikTok/Instagram/LinkedIn posts were published."},
    {"name": "list_tasks", "description": "Overdue, today's and upcoming tasks."},
    {"name": "get_calendar", "description": "What's on the user's Google Calendar (meetings, events) for a day.",
     "parameters": {"type": "OBJECT", "properties": {"day": DATE}}},
    {"name": "start_day", "description": "Run the morning routine: open the work setup, start music, read the briefing."},
    {"name": "get_inbox", "description": "Summary of the user's Gmail inbox: unread count, emails from leads/clients."},
    {"name": "get_coaching", "description": "Advice/coaching: what to focus on to make money, which leads to chase, how to get back on track."},
    {"name": "what_do_you_know", "description": "Everything stored about the user."},
    {"name": "add_task", "description": "Create a task or reminder.",
     "parameters": {"type": "OBJECT", "properties": {
         "title": S, "due": DATE, "due_time": {"type": "STRING", "description": "HH:MM 24h"},
         "priority": {"type": "INTEGER", "description": "1 urgent .. 4 low"},
         "category": {"type": "STRING", "enum": ["revenue", "client", "sales", "content", "study", "personal", "other"]},
         "recurrence": {"type": "STRING", "description": "daily | weekdays | weekly:MO,WE,FR"}},
         "required": ["title"]}},
    {"name": "complete_task", "description": "Mark a task done.",
     "parameters": {"type": "OBJECT", "properties": {"task": S}, "required": ["task"]}},
    {"name": "move_task", "description": "Reschedule a task.",
     "parameters": {"type": "OBJECT", "properties": {"task": S, "new_date": DATE}, "required": ["task", "new_date"]}},
    {"name": "add_lead", "description": "Add a sales lead/prospect.",
     "parameters": {"type": "OBJECT", "properties": {"name": S, "service": S, "value": N,
                                                      "currency": {"type": "STRING", "enum": ["USD", "NGN"]},
                                                      "followup": DATE}, "required": ["name"]}},
    {"name": "update_lead", "description": "Change a lead's stage or follow-up date.",
     "parameters": {"type": "OBJECT", "properties": {
         "name": S, "stage": {"type": "STRING", "enum": ["new", "qualified", "proposal", "negotiation", "won", "lost"]},
         "followup": DATE, "value": N}, "required": ["name"]}},
    {"name": "log_payment", "description": "Record money RECEIVED from a client (set paid=true when it was received). "
                                           "Can name the invoice it pays. The user confirms before it's saved.",
     "parameters": {"type": "OBJECT", "properties": {"amount": N, "currency": {"type": "STRING", "enum": ["USD", "NGN"]},
                                                      "client": S, "earned_date": DATE, "paid": {"type": "BOOLEAN"},
                                                      "invoice": {"type": "STRING", "description": "invoice number it pays, e.g. MC-015"},
                                                      "method": {"type": "STRING", "enum": ["bank_transfer", "paystack", "cash", "other"]},
                                                      "reference": S}, "required": ["amount", "currency"]}},
    {"name": "log_post", "description": "Record that a social post was published today.",
     "parameters": {"type": "OBJECT", "properties": {
         "platform": {"type": "STRING", "enum": ["tiktok", "instagram", "linkedin", "x"]}, "title": S},
         "required": ["platform"]}},
    {"name": "remember", "description": "Store a durable fact or preference about the user.",
     "parameters": {"type": "OBJECT", "properties": {
         "content_text": S, "kind": {"type": "STRING", "enum": ["fact", "preference", "plan"]},
         "valid_until": DATE}, "required": ["content_text"]}},
    {"name": "open_workspace", "description": "Open a workspace profile.",
     "parameters": {"type": "OBJECT", "properties": {
         "profile": {"type": "STRING", "enum": ["coding", "business", "content", "study", "general"]}},
         "required": ["profile"]}},
]
DECLS += [
    {"name": "create_invoice",
     "description": "Create a DRAFT invoice PDF in Moyocode's style (never sent). Use only amounts the user stated; "
                    "if an amount is missing, ask instead of calling.",
     "parameters": {"type": "OBJECT", "properties": {
         "client": {"type": "STRING", "description": "Who the invoice is for (person or company)"},
         "bill_to": {"type": "STRING", "description": "Optional extra lines: contact person, address"},
         "items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
             "description": S, "amount": {"type": "STRING", "description": "price per unit exactly as the user said it, e.g. 150000, ₦150,000 or AMOUNT_1"},
             "qty": {"type": "INTEGER"}, "item": {"type": "STRING", "description": "optional category e.g. Development"}},
             "required": ["description", "amount"]}},
         "discount": {"type": "STRING", "description": "discount amount as said, if any"},
         "deposit_pct": {"type": "INTEGER", "description": "e.g. 50 for a 50% deposit"},
         "due_days": {"type": "INTEGER"}, "currency": {"type": "STRING", "enum": ["NGN", "USD"]},
         "notes": {"type": "ARRAY", "items": S}},
         "required": ["client", "items"]}},
    {"name": "list_invoices", "description": "List recent invoices Moyo created, their status and what's still owed."},
    {"name": "issue_invoice", "description": "Mark an invoice as SENT to the client (after the user sent it). User confirms.",
     "parameters": {"type": "OBJECT", "properties": {"number": {"type": "STRING", "description": "e.g. MC-015"}},
                    "required": ["number"]}},
    {"name": "money_owed", "description": "Who owes the user money: unpaid and overdue invoices."},
    {"name": "capture_lead",
     "description": "Save a NEW sales lead/opportunity from what the user said (they confirm before it's saved). "
                    "Fill only what was said; leave the rest empty.",
     "parameters": {"type": "OBJECT", "properties": {
         "company": S, "contact_name": S, "role": S, "phone": S, "email": S,
         "service": {"type": "STRING", "enum": ["website", "web_app", "ai_agent", "automation", "integration",
                                                "consulting", "maintenance", "hosting", "other"]},
         "need": {"type": "STRING", "description": "what they want, in a few words"},
         "value": {"type": "STRING", "description": "budget/deal value as said, e.g. 400k, ₦400,000, AMOUNT_1"},
         "currency": {"type": "STRING", "enum": ["NGN", "USD"]},
         "stage": {"type": "STRING", "enum": ["new", "contacted", "engaged", "discovery", "proposal", "negotiation"]},
         "source": {"type": "STRING", "enum": ["referral", "inbound", "social", "outreach", "past_client", "other"]},
         "source_detail": S, "next_action": S, "next_action_due": DATE, "notes": S}}},
    {"name": "who_to_contact", "description": "Who should the user follow up with today, and why (sales follow-ups)."},
    {"name": "followed_up", "description": "Log that the user followed up with a lead/client, optionally with the next step date.",
     "parameters": {"type": "OBJECT", "properties": {"name": S, "note": S,
                    "channel": {"type": "STRING", "enum": ["whatsapp", "email", "phone", "in_person"]},
                    "next_date": DATE, "next_action": S}, "required": ["name"]}},
    {"name": "move_deal", "description": "Move a deal to another sales stage (e.g. proposal sent, won, lost).",
     "parameters": {"type": "OBJECT", "properties": {"name": S, "stage": {"type": "STRING", "enum": [
         "new", "contacted", "engaged", "discovery", "proposal", "negotiation", "won", "lost", "nurture"]},
         "lost_reason": S}, "required": ["name", "stage"]}},
    {"name": "set_next_step", "description": "Set the next action and date for a deal.",
     "parameters": {"type": "OBJECT", "properties": {"name": S, "next_action": S, "date": DATE},
                    "required": ["name", "next_action", "date"]}},
    {"name": "deal_note", "description": "Add a note to a lead/deal's history (requirements, objections, what was discussed).",
     "parameters": {"type": "OBJECT", "properties": {"name": S, "note": S}, "required": ["name", "note"]}},
    {"name": "draft_followup", "description": "Draft a follow-up message for a lead/client (the user sends it themselves).",
     "parameters": {"type": "OBJECT", "properties": {"name": S,
                    "channel": {"type": "STRING", "enum": ["whatsapp", "email"]}, "goal": S}, "required": ["name"]}},
]
assert all(d["name"] in REGISTRY for d in DECLS)

AMOUNT_RE = re.compile(r"(?:₦|\$|ngn\s?|usd\s?)?\d[\d,]*(?:\.\d+)?\s?(?:k|m|naira|dollars?|usd|ngn)?\b", re.I)


class Redactor:
    def __init__(self, con):
        names = [r["name"] for r in rows(con.execute("SELECT DISTINCT name FROM companies"))]
        names += [r["full_name"] for r in rows(con.execute("SELECT DISTINCT full_name FROM contacts"))]
        names += [r["client"] for r in rows(con.execute("SELECT DISTINCT client FROM earnings WHERE client IS NOT NULL"))]
        self.names = sorted({n for n in names if n and len(n) > 2}, key=len, reverse=True)
        self.map: dict[str, str] = {}

    def redact(self, text: str) -> str:
        for i, n in enumerate(self.names):
            if re.search(re.escape(n), text, re.I):
                ph = f"CLIENT_{i + 1}"
                self.map[ph] = n
                text = re.sub(re.escape(n), ph, text, flags=re.I)

        def amt(m):
            s = m.group(0).rstrip()
            trail = m.group(0)[len(s):]
            if not re.search(r"[₦$]|naira|dollar|usd|ngn|\d{3,}|\dk\b", s, re.I):
                return m.group(0)  # small numbers (dates, times, counts) are fine
            ph = f"AMOUNT_{len([k for k in self.map if k.startswith('AMOUNT')]) + 1}"
            self.map[ph] = s
            return ph + trail
        return AMOUNT_RE.sub(amt, text)

    def restore(self, value):
        if isinstance(value, str):
            for ph, orig in self.map.items():
                value = value.replace(ph, orig)
            return value
        if isinstance(value, dict):
            return {k: self.restore(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.restore(v) for v in value]
        return value


def api_key(name: str = "gemini_api_key") -> str | None:
    try:
        import keyring
        return keyring.get_password("moyo-ai", name)
    except Exception:
        return None


def _openai_schema(s):
    if isinstance(s, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _openai_schema(v)) for k, v in s.items()}
    if isinstance(s, list):
        return [_openai_schema(x) for x in s]
    return s


GROQ_TOOLS = [{"type": "function", "function": {"name": d["name"], "description": d["description"],
                                                  "parameters": _openai_schema(d.get("parameters", {"type": "OBJECT", "properties": {}}))}}
              for d in DECLS]


def _call_gemini(model: str, key: str, safe: str, sys_prompt: str):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key, http_options={"api_version": "v1beta", "timeout": 20000})
    r = client.models.generate_content(
        model=model, contents=safe,
        config=types.GenerateContentConfig(
            system_instruction=sys_prompt, temperature=0,
            tools=[types.Tool(function_declarations=DECLS)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
    for part in (r.candidates[0].content.parts if r.candidates and r.candidates[0].content else []):
        if part.function_call:
            return part.function_call.name, dict(part.function_call.args or {}), None
    return None, None, (r.text or "").strip()


def _call_groq(model: str, key: str, safe: str, sys_prompt: str):
    import json as _json

    import httpx
    r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=20,
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": model, "temperature": 0, "tools": GROQ_TOOLS, "tool_choice": "auto",
                         "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": safe}]})
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    if msg.get("tool_calls"):
        fc = msg["tool_calls"][0]["function"]
        return fc["name"], _json.loads(fc.get("arguments") or "{}"), None
    return None, None, (msg.get("content") or "").strip()


def generate_json(con, system: str, user: str) -> dict:
    """Ask the free model chain for a JSON answer (no tools). Returns {'data', 'model'} or {'error'}.
    Callers must pass already-anonymised content."""
    import json as _json
    cfg = get_setting(con, "cloud")
    if not cfg.get("enabled"):
        return {"error": "Cloud help is switched off in Settings."}
    gkey, qkey = api_key(), api_key("groq_api_key")
    if not gkey and not qkey:
        return {"error": "No Gemini or Groq key saved."}
    for m in cfg.get("models") or ["gemini-3.5-flash-lite"]:
        is_groq = m.startswith("groq:")
        key = qkey if is_groq else gkey
        if not key:
            continue
        try:
            if is_groq:
                import httpx
                r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=40,
                               headers={"Authorization": f"Bearer {key}"},
                               json={"model": m[5:], "temperature": 0.4, "response_format": {"type": "json_object"},
                                     "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"]
            else:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=key, http_options={"api_version": "v1beta", "timeout": 40000})
                r = client.models.generate_content(model=m, contents=user, config=types.GenerateContentConfig(
                    system_instruction=system, temperature=0.4, response_mime_type="application/json"))
                text = r.text or ""
            return {"data": _json.loads(text), "model": m}
        except Exception:
            continue  # quota / overload / bad JSON → next model
    return {"error": "The AI coach is unavailable right now (free models busy or over today's limit)."}


def interpret(con, text: str) -> dict:
    """Returns {'action': name, 'args': {...}} or {'reply': text} or {'error': ...}."""
    cfg = get_setting(con, "cloud")
    if not cfg.get("enabled"):
        return {"error": "Cloud help is switched off, so I only understand direct commands."}
    gkey, qkey = api_key(), api_key("groq_api_key")
    if not gkey and not qkey:
        return {"error": "No Gemini or Groq key saved, so I can only handle direct commands."}
    red = Redactor(con)
    safe = red.redact(text) if cfg.get("redact_clients_and_amounts", True) else text
    sys_prompt = (
        f"You are Moyo, Moyosore's personal assistant. Today is {today().strftime('%A %Y-%m-%d')}. "
        "You DO have access, through your tools, to his tasks, plan, $10K tracker, sales pipeline, content stats, "
        "memory, Google Calendar and Gmail inbox. Never say you lack access to these; call the matching tool. "
        "If the request matches a tool, call exactly one tool with your best interpretation (resolve relative "
        "dates to ISO). Placeholders like CLIENT_1 or AMOUNT_1 stand for private values: pass them through "
        "unchanged in tool arguments. If no tool fits, answer in at most two sentences and never invent "
        "numbers, clients, metrics or facts about the user.")
    models = cfg.get("models") or ["gemini-3.5-flash-lite"]
    errors = []
    for m in models:
        is_groq = m.startswith("groq:")
        key = qkey if is_groq else gkey
        if not key:
            continue
        try:
            name, args, reply = (_call_groq(m[5:], key, safe, sys_prompt) if is_groq
                                 else _call_gemini(m, key, safe, sys_prompt))
        except Exception as e:  # quota (429), overload (503), network… → try the next model
            errors.append(f"{m}: {type(e).__name__}")
            continue
        if name:
            args = red.restore(args)
            if "amount" in args and isinstance(args["amount"], str):
                from moyo.dates import parse_amount
                pa = parse_amount(args["amount"])
                if pa:
                    args["amount"] = pa[0]
                    args["currency"] = pa[1] or args.get("currency", "NGN")
            return {"action": name, "args": args, "redacted": safe != text, "model": m}
        return {"reply": red.restore(reply or "") or "Sorry, I didn't get that.", "redacted": safe != text, "model": m}
    return {"error": "Cloud help is unavailable right now (all free models busy or over today's limit). "
                     "Try a direct command."}
