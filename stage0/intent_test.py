# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["google-genai>=1.0", "keyring>=25", "numpy>=1.24", "soundfile>=0.12"]
# ///
"""Does Moyo pick the RIGHT ACTION from your voice? (the metric that matters)

Gemini Live hears each recording with Moyo's action list available as tools.
We record which action it chooses and with which details. Nothing is executed:
every tool call is answered with "test mode, not executed".

Run:  uv run --python 3.13 stage0/intent_test.py --audio-dir stage0/audio_v2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import keyring
import numpy as np
import soundfile as sf
from google import genai
from google.genai import types

HERE = Path(__file__).parent
MODEL = "gemini-3.1-flash-live-preview"

S = {"type": "STRING"}
TOOLS = [{"function_declarations": [
    {"name": "get_daily_plan", "description": "Show today's plan, priorities or schedule."},
    {"name": "get_content_performance", "description": "Report how a social media post performed.",
     "parameters": {"type": "OBJECT", "properties": {"platform": S, "when": S}}},
    {"name": "rank_tasks", "description": "Say which tasks are most important."},
    {"name": "add_task", "description": "Create a task or reminder.",
     "parameters": {"type": "OBJECT", "properties": {"title": S, "due": S}, "required": ["title"]}},
    {"name": "get_target_progress", "description": "Report progress toward the $10K earnings target or the weekly pace needed."},
    {"name": "open_workspace", "description": "Open a workspace profile (coding, business, content, study).",
     "parameters": {"type": "OBJECT", "properties": {"profile": S}, "required": ["profile"]}},
    {"name": "start_focus_session", "description": "Start working on a named project or topic.",
     "parameters": {"type": "OBJECT", "properties": {"topic": S}, "required": ["topic"]}},
    {"name": "recall_history", "description": "Recall what the user did on a previous day.",
     "parameters": {"type": "OBJECT", "properties": {"day": S}}},
    {"name": "move_task", "description": "Reschedule an existing task.",
     "parameters": {"type": "OBJECT", "properties": {"task": S, "new_date": S}, "required": ["new_date"]}},
    {"name": "log_payment", "description": "Record money earned from a client.",
     "parameters": {"type": "OBJECT", "properties": {"amount": {"type": "NUMBER"}, "currency": S, "client": S},
                    "required": ["amount", "currency"]}},
]}]

# expected action + key details (case-insensitive substring / numeric match)
EXPECT = {
    1: ("get_daily_plan", {}),
    2: ("get_content_performance", {"platform": "instagram"}),
    3: ("rank_tasks", {}),
    4: ("add_task", {"due": "tomorrow"}),
    5: ("get_target_progress", {}),
    6: ("open_workspace", {"profile": "cod|dev"}),
    7: ("start_focus_session", {"topic": "lead"}),
    8: ("recall_history", {}),
    9: ("move_task", {"new_date": "fri"}),
    10: ("log_payment", {"amount": 200000, "currency": "n|ngn"}),
}

SYSTEM = ("You are Moyo, Moyosore's personal assistant. The user speaks Nigerian English. "
          "When the user asks for something one of your tools can do, call that tool immediately "
          "with your best interpretation. Do not ask clarifying questions in this test.")


def ok(name, args, want):
    wname, wargs = want
    if name != wname:
        return False
    for k, v in wargs.items():
        g = args.get(k)
        if isinstance(v, (int, float)):
            try:
                if abs(float(g) - v) > 1:
                    return False
            except (TypeError, ValueError):
                return False
        elif not g or not any(p in str(g).lower() for p in v.split("|")):
            return False
    return True


async def one(client, audio):
    pcm = np.concatenate([(np.clip(audio, -1, 1) * 32767).astype("<i2"), np.zeros(16000, "<i2")])
    cfg = {"response_modalities": ["AUDIO"], "input_audio_transcription": {},
           "output_audio_transcription": {}, "system_instruction": SYSTEM, "tools": TOOLS}
    calls, heard, said = [], [], []
    t_end = t_call = None
    async with client.aio.live.connect(model=MODEL, config=cfg) as s:
        for i in range(0, len(pcm), 1600):
            await s.send_realtime_input(audio=types.Blob(data=pcm[i:i + 1600].tobytes(),
                                                         mime_type="audio/pcm;rate=16000"))
            await asyncio.sleep(0.1)
        t_end = time.perf_counter()
        await s.send_realtime_input(audio_stream_end=True)
        async for m in s.receive():
            if m.tool_call:
                for fc in m.tool_call.function_calls:
                    calls.append({"name": fc.name, "args": dict(fc.args or {})})
                    t_call = t_call or time.perf_counter()
                await s.send_tool_response(function_responses=[
                    types.FunctionResponse(id=fc.id, name=fc.name,
                                           response={"result": "test mode, not executed"})
                    for fc in m.tool_call.function_calls])
            sc = m.server_content
            if sc:
                if sc.input_transcription and sc.input_transcription.text:
                    heard.append(sc.input_transcription.text)
                if sc.output_transcription and sc.output_transcription.text:
                    said.append(sc.output_transcription.text)
                if sc.turn_complete:
                    break
    return calls, "".join(heard), "".join(said), (t_call - t_end) if t_call else None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default=str(HERE / "audio_v2"))
    a = ap.parse_args()
    d = Path(a.audio_dir)
    items = json.loads((d / "manifest.json").read_text(encoding="utf-8-sig"))
    client = genai.Client(api_key=keyring.get_password("moyo-ai", "gemini_api_key"),
                          http_options={"api_version": "v1beta"})
    rows, correct = [], 0
    for it in items:
        if it["id"] not in EXPECT:
            continue
        audio, _ = sf.read(d / it["file"], dtype="float32")
        try:
            calls, heard, said, lat = asyncio.run(asyncio.wait_for(one(client, audio), 60))
        except Exception as e:
            calls, heard, said, lat = [], "", f"ERROR {type(e).__name__}: {str(e)[:100]}", None
        first = calls[0] if calls else {"name": None, "args": {}}
        good = ok(first["name"], first["args"], EXPECT[it["id"]])
        correct += good
        rows.append({"said": it["text"], "action": first, "correct": good,
                     "transcript": heard, "moyo_said": said,
                     "seconds_to_action": round(lat, 2) if lat else None})
        mark = "✓" if good else "✗"
        print(f"{mark} \"{it['text']}\"\n    → {first['name']} {json.dumps(first['args'])}"
              + (f"   ({lat:.1f}s)" if lat else "") + (f"\n    Moyo said: {said[:90]}" if said and not calls else ""))
        time.sleep(2)
    (HERE / "intent_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lats = [r["seconds_to_action"] for r in rows if r["seconds_to_action"]]
    print(f"\nRIGHT ACTION + DETAILS: {correct}/{len(rows)}"
          + (f"   avg time to action {sum(lats) / len(lats):.2f}s" if lats else ""))


if __name__ == "__main__":
    main()
