"""First-run seed: only things Moyosore has actually told Moyo (kind/source recorded)."""
from __future__ import annotations

from moyo.db import now_iso

PROJECTS = [
    ("MoyoCode Technologies", "client", "Technology business: websites, custom software, AI agents, voice AI, automation, APIs, consulting."),
    ("$10K Challenge", "revenue", "Earn $10,000 between 8 Nov 2026 and 8 Feb 2027 (basis: money earned)."),
    ("Personal Brand", "content", "Daily TikTok + Instagram videos, 2–3 LinkedIn posts/week, consistent X presence."),
    ("ConvergsAI", "other", "AI product being explored."),
    ("University", "study", "Software engineering studies."),
    ("Personal", "personal", "Gym, reading, rest, learning."),
]

MEMORY = [
    ("profile", "fact", "Name: Moyosore Ayofemi-Adetoye. Nigerian software engineering student, developer and entrepreneur."),
    ("business", "fact", "Founder of MoyoCode Technologies (websites, custom software, AI agents, AI voice systems, automation, API integrations, consulting)."),
    ("goals", "fact", "Wants MoyoCode to become a profitable, reputable, scalable tech company serving Nigerian and international clients, focused on solving valuable problems with software, AI and automation."),
    ("goals", "fact", "$10K challenge: earn $10,000 (money EARNED, not contracted or collected) from 8 Nov 2026 to 8 Feb 2027. $0 earned as of 12 Nov 2026."),
    ("content", "fact", "Publishing commitments: a video every day on TikTok and Instagram, ~2–3 LinkedIn posts a week, consistent X presence."),
    ("content", "fact", "Instagram is a Business account; TikTok is a personal account. Tracks views, likes and comments per post."),
    ("projects", "fact", "ConvergsAI is an AI product being explored."),
    ("routine", "fact", "Typical day: wake, startup meeting at work, then own tasks toward the $10K goal; gym in the evening; more work after."),
    ("tools", "fact", "Uses Google Calendar, Spotify Premium, Antigravity, VS Code, Chrome, Windows Terminal, Notion."),
    ("preferences", "preference", "Prioritise: 1) $10K revenue work, 2) MoyoCode client delivery, 3) leads/sales/follow-ups/proposals, 4) content, 5) university/learning, 6) personal development. Urgent client work, exams, health and personal commitments can override."),
    ("preferences", "preference", "Wants a productive but sustainable life: time for study, gym, reading, rest and learning. Do not fill every hour."),
    ("routine", "assumption", "Startup meeting assumed 09:00–10:00 weekdays and gym 18:00–19:30; times not yet confirmed."),
]


def seed(con) -> None:
    ts = now_iso()
    for name, cat, desc in PROJECTS:
        con.execute("INSERT OR IGNORE INTO projects(name, category, description) VALUES (?,?,?)", (name, cat, desc))
    for cat, kind, content in MEMORY:
        src = "Moyo (needs confirmation)" if kind == "assumption" else "Moyosore (onboarding chat, 12 Nov 2026)"
        con.execute("INSERT INTO memory(category, kind, content, source, confirmed, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)", (cat, kind, content, src, 0 if kind == "assumption" else 1, ts, ts))
