"""Deterministic command parser: instant, exact, offline. Returns (action, args) or None.
Anything it can't parse goes to the cloud fallback (moyo.cloud), which uses the same actions."""
from __future__ import annotations

import re

from moyo.dates import parse_amount, parse_date, parse_time
from moyo.db import today

DATE_WORDS = (r"(?:today|tonight|tomorrow|this (?:morning|afternoon|evening)|next week|in \d+ days?|"
              r"(?:on |by |next |this )?(?:mon|tues|wednes|thurs|fri|satur|sun)day|"
              r"(?:on |by )?\d{4}-\d{2}-\d{2}|(?:on |by )?\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
              r"(?:on |by )?\d{1,2}(?:st|nd|rd|th)? (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)")
TIME_WORDS = (r"(?:at )?(?:\d{1,2}(?::\d{2})?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
              r"\s*(?:a\.?\s?m\.?|p\.?\s?m\.?)")


def _clean(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^(hey |ok |okay )?moyo[,!.]?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*(please|pls|abeg)[.!?]*$", "", t, flags=re.I)
    t = re.sub(r"^(please|pls|can you|could you)\s+", "", t, flags=re.I)
    return t.strip().rstrip("?.!")


def _split_when(s: str) -> tuple[str, str | None, str | None]:
    """Pull a trailing date and/or time off a phrase."""
    ref = today()
    due = tm = None
    for _ in range(2):
        m = re.search(rf"\s+({TIME_WORDS})$", s, flags=re.I)
        if m and not tm:
            tm = parse_time(m.group(1))
            s = s[:m.start()]
            continue
        m = re.search(rf"\s+({DATE_WORDS})$", s, flags=re.I)
        if m and not due:
            d = parse_date(m.group(1), ref)
            if d:
                due = d.isoformat()
                s = s[:m.start()]
                continue
        break
    if tm and not due:
        due = ref.isoformat()
    return s.strip(" ,"), due, tm


def parse(text: str) -> tuple[str, dict] | None:
    t = _clean(text)
    low = t.lower()

    # ---------- revenue: quick capture ("new lead …", "met X from Y …", "spoke with …")
    if re.match(r"^(?:new lead|lead:|prospect:|met |spoke (?:to|with) |talked (?:to|with) |had a call with |call with )", low):
        return "capture_lead", {"text": t}
    if re.match(r"^(?:who should i (?:follow up|contact|call|message)|who do i (?:follow up|contact)|follow[- ]?ups?(?: today)?$)", low):
        return "who_to_contact", {}

    # ---------- money: log payment / earnings
    m = re.match(r"^(?:log|record|add)\s+(?:a\s+)?(?:payment|earning|income|revenue)?\s*(?:of\s+)?(.+?)"
                 r"(?:\s+(?:from|for|by)\s+(.+?))?(?:\s+(paid|unpaid))?$", low)
    if m and re.search(r"\d|naira|dollar|thousand|hundred|million|₦|\$", m.group(1)):
        amt = parse_amount(m.group(1))
        if amt:
            client_raw = t[m.start(2):m.end(2)] if m.group(2) else None
            client, when, _ = _split_when(client_raw) if client_raw else (None, None, None)
            # "log payment …" means money received (D41: the $10K counts collected cash), unless "unpaid"
            paid = m.group(3) == "paid" or (m.group(3) != "unpaid" and re.match(r"^(?:log|record|add)\s+(?:a\s+)?payment", low) is not None)
            return "log_payment", {"amount": amt[0], "currency": amt[1] or "NGN", "client": client or None,
                                   "earned_date": when, "paid": paid}
    m = re.match(r"^(?:i\s+)?(?:earned|made|got paid|received)\s+(.+?)\s+(?:from|for)\s+(.+)$", low)
    if m and (amt := parse_amount(m.group(1))):
        client, when, _ = _split_when(t[m.start(2):m.end(2)])
        return "log_payment", {"amount": amt[0], "currency": amt[1] or "NGN", "client": client,
                               "earned_date": when, "paid": "paid" in low or "received" in low}

    # ---------- exchange rate
    m = re.match(r"^set (?:the )?(?:exchange )?rate (?:to )?(?:₦|n)?([\d,]+)", low)
    if m:
        return "set_rate", {"ngn_per_usd": float(m.group(1).replace(",", ""))}

    # ---------- leads
    m = re.match(r"^(?:new|add)(?: a)?(?: new)? (?:lead|prospect)(?: called| named)?[:\s]+(.+)$", t, flags=re.I)
    if m:
        body = m.group(1)
        parts = [p.strip() for p in re.split(r",|\s+-\s+|\s+for\s+|\s+wants?\s+", body) if p.strip()]
        name, service, value, cur = parts[0], None, None, "USD"
        for p in parts[1:]:
            a = parse_amount(p)
            if a:
                value, cur = a[0], a[1] or "USD"
            elif not service:
                service = re.sub(r"^(a|an)\s+", "", p)
        return "add_lead", {"name": name, "service": service, "value": value, "currency": cur}
    m = re.match(r"^(?:mark|move|set) (?:the )?(?:lead |proposal for |deal with )?(.+?) (?:as|to) "
                 r"(new|qualified|proposal|proposal sent|sent|negotiation|negotiating|won|lost)$", low)
    if m:
        stage = {"sent": "proposal", "proposal sent": "proposal", "negotiating": "negotiation"}.get(m.group(2), m.group(2))
        name = t[m.start(1):m.end(1)]
        return "update_lead", {"name": name, "stage": stage}
    m = re.match(r"^(?:remind me to )?follow(?: |-)up with (.+)$", t, flags=re.I)
    if m:
        who, due, tm = _split_when(m.group(1))
        return "add_task", {"title": f"Follow up with {who}", "due": due or today().isoformat(), "due_time": tm,
                            "category": "sales", "lead": who, "estimate_min": 20}

    # ---------- tasks
    m = re.match(r"^(?:add|create|new)(?: a)?(?: recurring)? (?:task|todo|to-do)(?: to)?[:\s]+(.+)$", t, flags=re.I) \
        or re.match(r"^remind me to (.+)$", t, flags=re.I)
    if m:
        body = m.group(1)
        rec = None
        rm = re.search(r"\s+(every ?day|daily|every weekday|weekdays|every (mon|tue|wed|thu|fri|sat|sun)[a-z]*)"
                       r"(?:\s+(at .+))?$", body, flags=re.I)
        if rm:
            word = rm.group(1).lower()
            rec = "daily" if "day" in word and "week" not in word and not rm.group(2) else \
                "weekdays" if "weekday" in word else f"weekly:{rm.group(2)[:2].upper()}"
            body = body[:rm.start()] + (" " + rm.group(3) if rm.group(3) else "")
        prio = 1 if re.search(r"\b(urgent|asap|important|top priority)\b", body, re.I) else 3
        body = re.sub(r"[\s,]*\b(urgent|asap|top priority)\b[\s,]*", " ", body, flags=re.I).strip()
        title, due, tm = _split_when(body)
        args = {"title": title, "due": due or (today().isoformat() if rec else None), "due_time": tm, "priority": prio}
        if rec:
            args["recurrence"] = rec
        return "add_task", args
    m = re.match(r"^(?:move|reschedule|push|postpone) (.+?) to (.+)$", low)
    if m:
        d = parse_date(m.group(2), today())
        if d:
            tid = re.fullmatch(r"(?:task )?#?(\d+)", m.group(1))
            target = {"task_id": int(tid.group(1))} if tid else {"task": t[m.start(1):m.end(1)]}
            return "move_task", {**target, "new_date": d.isoformat()}
    m = re.match(r"^(?:done|complete|completed|finished|i finished|i did|mark) (?:task )?(.+?)(?: as done| done)?$", low)
    if m and not re.match(r"^mark .+ as (won|lost|sent|qualified|proposal|negotiation)", low):
        ref = m.group(1)
        tid = re.fullmatch(r"#?(\d+)", ref)
        return "complete_task", {"task_id": int(tid.group(1))} if tid else {"task": t[m.start(1):m.end(1)]}

    # ---------- content
    m = re.match(r"^(?:i )?(?:posted|published|uploaded)(?: (?:a|my) (?:video|post|reel))?(?: on| to)? "
                 r"(tiktok|instagram|ig|insta|linkedin|x|twitter)(?:[:\s-]+(.+))?$", low)
    if m:
        plat = {"ig": "instagram", "insta": "instagram", "twitter": "x"}.get(m.group(1), m.group(1))
        return "log_post", {"platform": plat, "title": t[m.start(2):m.end(2)] if m.group(2) else None}
    if re.search(r"did i (post|publish)|content status|posting streak", low):
        return "get_content_status", {}

    # ---------- workspace & media
    m = re.match(r"^(?:open|start|launch|load)(?: my| the)? (.+?)(?: mode| workspace| profile| setup)+$", low) \
        or re.match(r"^(?:let'?s )?(?:start )?(coding|study|business|content) mode$", low)
    if m:
        return "open_workspace", {"profile": m.group(1).strip()}
    for pat, act in ((r"^(pause|play|resume)( the)?( music)?$", "play_pause"), (r"^(next|skip)( song| track)?$", "next"),
                     (r"^(previous|last) (song|track)$", "previous"), (r"^(turn )?(the )?volume up", "volume_up"),
                     (r"^(turn )?(the )?volume down|^turn (it|the music|the volume) down", "volume_down"),
                     (r"^(mute|unmute)", "mute")):
        if re.match(pat, low):
            return "media", {"action": act, "times": 3 if act.startswith("volume") else 1}

    # ---------- memory
    if re.search(r"what do you know about me|what have you (stored|remembered)|show (my )?memory", low):
        return "what_do_you_know", {}
    m = re.match(r"^forget (?:about )?(?:the )?(.+)$", t, flags=re.I)
    if m:
        return "forget", {"about": m.group(1)}
    m = re.match(r"^remember (?:that )?(.+)$", t, flags=re.I)
    if m:
        return "remember", {"content_text": m.group(1)}

    # ---------- queries
    if re.fullmatch(r"(good morning|start (my|the) day|let'?s start( the day)?|morning routine|begin my day)[,!.]?( moyo)?", low):
        return "start_day", {}
    if re.search(r"\b(calendar|meetings?|events?|appointments?)\b", low) or \
            re.search(r"what'?s (on|happening) (today|tomorrow|this (afternoon|evening|morning))", low):
        day = "tomorrow" if "tomorrow" in low else None
        m = re.search(r"\b(?:on |this |next )?(mon|tues|wednes|thurs|fri|satur|sun)day\b", low)
        d = parse_date(m.group(0), today()) if m else parse_date(day, today()) if day else None
        return "get_calendar", {"day": d.isoformat()} if d else {}
    if re.search(r"\b(inbox|e-?mails?|gmail|my mail|any mail|unread)\b", low):
        return "get_inbox", {}
    if re.search(r"\b(coach me|coaching|advice|advise me|how (can|do) i (make|earn|get) (more )?money|"
                 r"get back on track|what am i missing)\b", low):
        return "get_coaching", {}
    if re.search(r"\b(brief|briefing|morning report)\b", low):
        return "get_briefing", {}
    if re.search(r"\b(10k|ten k|10,000|target|challenge|how much (have|did) (i|we)|earned so far|progress)\b", low):
        return "get_target_progress", {}
    if re.search(r"\b(plan|agenda|schedule|priorit|most important|what should i (do|work on)|focus on)\b", low):
        return "get_daily_plan", {}
    if re.search(r"\b(my tasks|task list|overdue|what'?s due|deadlines?)\b", low):
        return "list_tasks", {}
    return None
