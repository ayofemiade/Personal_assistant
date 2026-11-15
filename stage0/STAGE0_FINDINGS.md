# Stage 0 — Findings (12 Nov 2026)

All tests were run on your EliteBook (i7‑1165G7, 16 GB, Iris Xe). Nothing was installed system-wide except the approved Ollama model.

## 1. Local LLM benchmark (`stage0/llm_bench.py`)
10 Moyo commands → structured JSON intent. Machine idle, Ollama on **100% CPU** (Iris Xe not used).

| Model | Size | Correct | Avg time per command | Generation speed |
|---|---|---|---|---|
| qwen2.5:1.5b | 1.0 GB | 8/10 | **3.8 s** | 9.2 tok/s |
| qwen3:4b (downloaded today) | 2.5 GB | 8/10 | **9.8 s** | 4.8 tok/s |

Both models made mistakes that matter:
- **qwen2.5:1.5b:** read "How much have we earned towards the 10K target?" as *log a $10,000 payment*.
- **qwen3:4b:** tagged a "$500" lead as **NGN**.

**Conclusions [VERIFIED]:**
1. A local LLM is **too slow for conversational voice** on this laptop (a natural reply needs under ~2 s). It also can't be trusted with money.
2. **Design consequence:**
   - Common commands (add/move task, log payment, add lead, open workspace, music, "what's my plan") go through a **deterministic parser** that is instant and exact.
   - Conversation, planning and briefings go to the **free cloud model** (you approved anonymised text).
   - The local model is the **offline fallback** and the private summariser.
3. Speed may improve on mains power with Windows power mode set to "Best performance" [ASSUMPTION — I did not change any system settings; worth trying yourself].

## 2. OpenJarvis hands-on trial
Installed from source into an isolated venv (Python 3.13 via uv), with config sandboxed via `OPENJARVIS_HOME`. Analytics disabled (`--no-analytics`; the default is also off).

| Check | Result |
|---|---|
| Install | ✅ ~2 min, 100+ packages |
| `jarvis doctor` | 9 passed, 22 warnings; speech not configured; no security profile by default |
| One-sentence question on qwen3:4b | ❌ **183 s**, and the model's hidden `<think>` reasoning leaked into the answer |
| Network behaviour | Contacts NVIDIA NIM's public model list during `doctor`; writes a `version-check.json` (phones home for updates) |
| Scope | Includes crypto **"Pearl mining"** and wallet commands (opt-in, GPU-only, not active), plus research/benchmark tooling we don't need |

**Verdict [RECOMMENDATION — needs your OK]:** Do **not** build on OpenJarvis. Build a **lean Moyo core** and copy specific, well-scoped ideas and modules from it under Apache‑2.0 (with attribution):
- faster‑whisper and Kokoro wrappers
- the prompt-injection scanner, taint tracking, approval store and audit log
- the Google Calendar connector pattern

## 3. Voice accuracy test — needs you (≈10 min)
`stage0/voice_test.py` is ready and tested. Its dependencies are installed and it detected your **Intel Smart Sound microphone array**. You read 30 Moyo commands (including Nigerian names and naira amounts). It compares four local Whisper models for accuracy and speed. Audio stays in memory and is never saved; only text results are written.

Run it in a terminal from the project folder:
```
uv run --python 3.13 stage0/voice_test.py
```
Or `--quick` for 10 phrases. The first run downloads the models (~1.5 GB total for all four).

**Pass mark:** word error rate ≤ 10% on the command set, with ≤ 2 s per phrase. If no local model passes, the fallback is Groq's free Whisper‑large‑v3 (audio leaves the laptop) or a Whisper fine-tuned on AfriSpeech.

## 3b. Voice results so far (30 recorded phrases, fair number scoring)
| Engine | WER | Exact phrases |
|---|---|---|
| local small.en | 58.5% | 2/30 |
| Groq whisper-large-v3-turbo (cloud) | 56.2% | 3/30 |
| Gemini 3.5 Flash (cloud, 3-phrase trial) | 52.6% | 0/3 |
| local large-v3-turbo | not run (Hugging Face download stalled at 4 MB) | |
| Gemini Live (all model names tried) | HTTP 404 on connect: not available to this free key, or a regional/API-version restriction | |

**Diagnosis:** even the strongest cloud models fail the same way, so the **audio is the bottleneck**, not the engine. The recordings contain 9–25% exact digital zeros. That is heavy noise suppression/gating by the Intel Smart Sound mic array plus Windows processing. **Next:** `stage0/mic_check.py` compares 8 capture paths (MME, WASAPI, WDM-KS raw array channels, Realtek jack) on one sentence.

## 3c. Breakthrough: action accuracy with Gemini Live (`stage0/intent_test.py`)
The metric that matters is **"did Moyo pick the right action with the right details?"**, not word-for-word transcripts.

- **Clean recordings** (always-on mic, `stage0/audio_v2`): Gemini Live (`gemini-3.1-flash-live-preview`, free key, `v1beta`) with Moyo's 10 tools picked the **right action + details in 8/10**. The two misses:
  - "Move that task to Friday" → it asked "which task?" (no prior context in a one-shot test)
  - "Remind me what I was doing yesterday" → it called `get_daily_plan`
- **Time to action:** ~1.2 s average, and often immediate (it detected the end of speech by itself).
- It correctly extracted **₦200,000 + "Adebayo Ventures"**, even though every transcript engine mangled that phrase.
- For comparison, transcripts on the same clean clips: Groq Whisper 38% WER, local small.en 51%. Gemini Live's own transcript (64% WER on the old clips) is a separate weak helper, so **never use it for logic.**

## 3d. Voice decision [RECOMMENDATION]
- **Online voice:** Gemini Live does audio-in/audio-out with function calling. Every tool call goes to Moyo's Tool Gateway, which applies permission tiers and the audit log. **Money/client actions are read back for confirmation** ("Log ₦200,000 from Adebayo Ventures, correct?").
- **Mic:** the always-on stream with pre-roll buffer while voice mode is active, plus a visible indicator and hard mute.
- **Offline / quota exhausted:** text input; local STT is not good enough with this mic and accent (≥50% WER).
- **Upgrade path if needed later:** an external mic (any cheap wired headset), which should cut errors further. Not required now.

## 4. Updated cost register entries
| Component | Choice | Class | Cost |
|---|---|---|---|
| Local LLM | qwen2.5:1.5b (fast fallback) / qwen3:4b (quality fallback) via Ollama | A | $0 |
| Conversation/planning LLM | Gemini free tier (primary), Groq free tier (backup) | C | $0 (limits vary) |
| Music control | Spotify Web API with **your** Premium | E (user's own subscription) | Your Premium fee; Moyo adds $0 |
| Content metrics | IG Graph API (views, likes, comments) + TikTok Display API (view/like/comment counts) | C (free) | $0 |
| Calendar | Google Calendar API (read-only) | C (free) | $0 |
