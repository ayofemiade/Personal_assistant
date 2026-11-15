"""Moyo AI — Stage 0 local LLM benchmark (stdlib only; talks to Ollama on 127.0.0.1).

Measures generation speed and whether the model can turn Moyo commands into
structured JSON intents (the main job we'd give a local model).
Run: python stage0/llm_bench.py qwen3:4b qwen2.5:1.5b
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:11434/api/chat"

SYSTEM = (
    "You convert a user's command into ONE JSON object and nothing else. Schema: "
    '{"intent": one of [add_task, move_task, log_payment, add_lead, query_plan, '
    'query_target, open_workspace, music, memory_forget, other], '
    '"title": string|null, "date": string|null, "amount": number|null, '
    '"currency": "NGN"|"USD"|null, "entity": string|null}. '
    "Use relative dates as spoken (e.g. 'tomorrow', 'Friday')."
)

CASES = [
    ("Add a task to contact that potential client tomorrow.", {"intent": "add_task", "date": "tomorrow"}),
    ("Move the proposal task to Friday.", {"intent": "move_task", "date": "friday"}),
    ("Log a payment of 200,000 naira from Adebayo Ventures.", {"intent": "log_payment", "amount": 200000, "currency": "NGN"}),
    ("New lead: Chukwuemeka Foods wants a website redesign for $500.", {"intent": "add_lead", "amount": 500, "currency": "USD"}),
    ("What's my plan for today?", {"intent": "query_plan"}),
    ("How much have we earned towards the 10K target?", {"intent": "query_target"}),
    ("Open my coding workspace.", {"intent": "open_workspace"}),
    ("Pause the music.", {"intent": "music"}),
    ("Forget the ConvergsAI pricing idea.", {"intent": "memory_forget"}),
    ("Remind me to follow up with Tunde on Thursday.", {"intent": "add_task", "date": "thursday"}),
]


def chat(model: str, prompt: str) -> tuple[str, dict]:
    body = json.dumps({
        "model": model, "stream": False, "format": "json", "think": False,
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    return data["message"]["content"], data


def check(got: dict, want: dict) -> bool:
    for k, v in want.items():
        g = got.get(k)
        if isinstance(v, str):
            if not isinstance(g, str) or v.lower() not in g.lower():
                return False
        elif isinstance(v, (int, float)):
            try:
                if abs(float(g) - v) > 0.5:
                    return False
            except (TypeError, ValueError):
                return False
    return True


def bench(model: str) -> dict:
    t0 = time.perf_counter()
    chat(model, "Pause the music.")  # warm-up / load
    load_s = time.perf_counter() - t0
    ok, lat, toks, gen_s = 0, [], 0, 0.0
    fails = []
    for prompt, want in CASES:
        t = time.perf_counter()
        text, meta = chat(model, prompt)
        lat.append(time.perf_counter() - t)
        toks += meta.get("eval_count", 0)
        gen_s += meta.get("eval_duration", 0) / 1e9
        try:
            got = json.loads(text)
        except json.JSONDecodeError:
            got = {}
        if check(got, want):
            ok += 1
        else:
            fails.append({"prompt": prompt, "got": got})
    return {
        "model": model, "first_load_s": round(load_s, 1), "accuracy": f"{ok}/{len(CASES)}",
        "avg_latency_s": round(sum(lat) / len(lat), 2),
        "gen_tokens_per_s": round(toks / gen_s, 1) if gen_s else None, "failures": fails,
    }


if __name__ == "__main__":
    models = sys.argv[1:] or ["qwen3:4b"]
    out = [bench(m) for m in models]
    print(json.dumps(out, indent=2))
