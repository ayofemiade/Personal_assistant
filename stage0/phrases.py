"""Shared test phrases and a fair text normaliser for Moyo's STT tests."""
from __future__ import annotations

import re

PHRASES = [
    "Moyo, what's my plan for today?",
    "How did yesterday's Instagram video perform?",
    "Which of my tasks is most important?",
    "Add a task to contact that potential client tomorrow.",
    "How much have we generated towards the ten K target?",
    "Open my development workspace.",
    "Let's work on MoyoCode's lead generation.",
    "Remind me what I was doing yesterday.",
    "Move that task to Friday.",
    "Log a payment of two hundred thousand naira from Adebayo Ventures.",
    "Add a new lead called Chukwuemeka Foods, website redesign, five hundred dollars.",
    "Mark the proposal for Oluwaseun as sent.",
    "Remind me to follow up with Tunde on Thursday at ten a.m.",
    "Start coding mode and play my focus playlist.",
    "Pause the music.",
    "Turn the volume down a little.",
    "What's on my Google Calendar this afternoon?",
    "I'm going to the gym, block two hours this evening.",
    "Did I post on TikTok today?",
    "Schedule a LinkedIn post for Wednesday about AI automation for small businesses.",
    "What do you know about me?",
    "Forget the ConvergsAI pricing idea.",
    "Show me my overdue follow-ups.",
    "How much do I need to earn per week to hit the target?",
    "Create a recurring task to publish an Instagram reel every day at seven p.m.",
    "Open Antigravity and the MoyoCode website project.",
    "Take a screenshot.",
    "Read my morning briefing.",
    "Cancel that.",
    "Good night Moyo, let's do the end of day review.",
]


def normalise(text: str) -> str:
    """Lower-case, spell out numbers and currency so '200,000 naira' == 'two hundred thousand naira'."""
    from num2words import num2words

    t = text.lower()
    t = t.replace("₦", " naira_sym ").replace("moyo code", "moyocode")
    t = re.sub(r"\$\s*([\d,]+(?:\.\d+)?)", r"\1 dollars", t)
    t = re.sub(r"([\d,]+)\s*naira_sym", r"\1 naira", t)
    t = t.replace("naira_sym", "naira")
    t = re.sub(r"(\d),(\d)", r"\1\2", t)
    t = re.sub(r"(\d+)\s*k\b", r"\1 k", t)
    t = re.sub(r"(\d)\s*(a|p)\.?\s?m\b\.?", r"\1 \2 m", t)  # 10am, 10 a.m.
    t = re.sub(r"\b(a|p)\.\s?m\.?", r"\1 m", t)            # ten a.m.
    t = re.sub(r"\bpm\b", "p m", t)                         # seven pm ("am" alone is a word)
    t = re.sub(r"\d+", lambda m: " " + num2words(int(m.group())) + " ", t)
    t = t.replace("-", " ")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    t = re.sub(r"\band\b", " ", t)  # "two hundred and five" vs "two hundred five"
    return re.sub(r"\s+", " ", t).strip()
