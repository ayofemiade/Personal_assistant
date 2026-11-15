# Moyo AI: a local-first personal executive assistant

Moyo is a personal AI assistant I built to run my day and my business (MoyoCode Technologies) from my own laptop.
You can wake it with a clap and a phrase, talk to it, and it helps plan the day, track a revenue goal, manage clients and
follow-ups, draft messages, create invoices and proposals, and watch Instagram/TikTok performance. Your data stays in a local
database, and Moyo never sends messages, spends money or changes anything important without your confirmation.

**Highlights**
- **Wake-up:** clap, pause, say *"let's get to work"*. Clap detection is done with plain signal maths, and the phrase is
  recognised **offline** (Vosk). A small orb then reads a short brief and asks if you want the full dashboard.
- **Two-way voice:** talk to Moyo (Gemini Live). It answers from your real data and can propose actions, which you confirm.
- **Revenue toolkit:** contacts/companies/deals (duplicate-proof), one-line lead capture, a ranked "who to contact today" list
  with reasons, drafts that open in **your own** WhatsApp/Gmail, WhatsApp chat import + AI summaries you confirm, a proper
  money ledger (invoices, partial payments, refunds; integer minor units, append-only), proposals with versions, renewals.
- **Daily life:** plan, tasks, morning briefing, reminders with quiet hours, weekly review, memory you control,
  workspace launcher (allowlisted apps only), Gmail + Google Calendar (read-only), Instagram + TikTok analytics (read-only).
- **Safety by design:** every action goes through a permission gateway (read / low / confirm / prohibited) with an audit log;
  emails, chats and web content are treated as untrusted data; client names and amounts are hidden before typed requests go to
  a cloud model; money is always calculated in code, never by the AI.

**Stack:** Python 3.13 (FastAPI, SQLite), vanilla JS/CSS dashboard in a Chrome app window, tkinter orb, Gemini free tier
(+ Groq fallback), Gemini Live, Vosk (offline speech), Kokoro (offline voice), Windows Credential Manager for secrets,
pytest (190+ tests). Runs on Windows; **₦0/month** on free tiers. Design docs: `docs/revenue/`, `MOYO_AI_DESIGN_SYSTEM.md`.

**Run it yourself (Windows):** install [uv](https://docs.astral.sh/uv/), clone this repo, run `moyo.cmd`
(first run sets up Python packages). Optional: copy `config/workspaces.example.json` to `config/workspaces.json`, download the
Kokoro and Vosk models into `models/`, and connect Google/Instagram/TikTok with your own developer apps
(`docs/GOOGLE_SETUP.md`, `docs/SOCIAL_SETUP.md`). Your keys are stored in Windows Credential Manager, never in files.

---

# Using Moyo

## Start / stop
| What | How |
|---|---|
| Start Moyo | Double-click **`moyo.cmd`**, or press **Ctrl+Alt+M** once the shortcut is installed |
| Install the Ctrl+Alt+M shortcut | `powershell -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1` (add `-Startup` to also start Moyo at login) |
| Stop Moyo | Double-click **`moyo-stop.cmd`** |
| Run tests | `uv run pytest` |

Moyo runs a small server on **http://127.0.0.1:8765** (your laptop only) and opens in a Chrome app window.

## Talking to Moyo (command bar, Ctrl+K)
Handled instantly and offline:
- `what's my plan` · `read my briefing` · `how much have I earned` · `did I post on TikTok today`
- `add task send proposal to Tunde tomorrow urgent` · `remind me to call Kemi Friday at 3pm`
- `add a recurring task to publish an Instagram reel every day at 7pm`
- `move proposal to Monday` · `done 4` (task number) · `done send proposal`
- `new lead Chukwuemeka Foods, website redesign, $500` · `mark Chukwuemeka Foods as proposal`
- `follow up with Tunde Thursday` · `log payment ₦200,000 from Adebayo Ventures` (asks you to confirm)
- `I posted on TikTok: <topic>` · `open coding mode` · `pause the music` · `next song` · `volume down`
- `what do you know about me` · `remember that <fact>` · `forget <topic>` (asks you to confirm)

Anything else goes to the **free cloud models** (Gemini 3.5 Flash-Lite → 3.1 Flash-Lite → 3.5 Flash → Groq
gpt-oss-120b, in that order). **Known client names and money amounts are replaced with placeholders before
leaving the laptop** and restored locally. The cloud can only *propose* actions; they still pass the safety gateway.

## Start my day & reminders
- **Start my day:** the Today button, typing "good morning", the morning notification, or **Ctrl+Alt+S**
  (run `scripts\install-shortcut.ps1` once more to create it). It opens your chosen workspace, starts its music and reads the briefing aloud.
  Configure in **Settings → Morning & reminders**.
- **Reminders** (bell, top-right): posting reminder (19:00), overdue/today follow-ups, emails from leads, meetings 15 min ahead,
  Google/Instagram connection problems, end-of-day review, Monday pace check, Sunday weekly review.
  Important/urgent items also pop up on the desktop, never during quiet hours (22:30–07:00, except urgent). Each reminder fires once.
- **Weekly review:** Review page → "This week" (money, leads, tasks, posts, top post), all from your data.
- Desktop pop-ups use a built-in, injection-safe notifier (`moyo/notify.py`); they appear as "Windows PowerShell" in Windows' notification settings.

## Clap to wake: clap, then say "let's get to work"
- **Turn it on/off:** Settings → Morning & reminders → Clap to wake. "Try the wake orb" shows the orb without clapping.
- **How:** clap once, then say **"let's get to work"** within ~6 seconds ("let's get work" also counts).
  A small Moyo orb appears top-right, says a short brief (money, tasks due, next commitment, top priority) with captions,
  then asks "Want to see your full dashboard?". **Answer out loud**: "open my dashboard" / "yes", "start my day", or "later" / "not now" (offline, in memory only). Or press **Enter** = open dashboard, **S** = start my day, **Esc** = later (auto-closes after 90 s).
- **Why the phrase:** this laptop's mic processing dulls claps to almost room-noise level, so a clap alone was unreliable.
  A clap only makes Moyo listen for a few seconds; the phrase decides. Speech recognition is offline (Vosk, `models/`), limited to this one phrase.
- **Test it any time:** `.venv\Scripts\python -m moyo.clap --phrase-test` (prints what it heard; nothing is saved).
- **For it to work right after you log in,** Moyo must run in the background: `scripts\install-shortcut.ps1 -Startup`.
- **Privacy:** while it's on, the mic stays open (Windows shows its mic icon; Moyo's sidebar shows "Listening for claps").
  Audio stays in memory only; nothing is recorded, stored or sent. Paused during quiet hours unless you allow it.

## Talking to Moyo (two-way voice)
- **Start:** the mic button next to the bell, or after the morning brief just ask a question (or say "let's talk", or press **T**).
  You can start talking about a second after the panel appears (it finishes connecting in the background, ~3 s). Say "bye" / "that's all", press **Esc**, or stay quiet ~45 s to end.
- **How:** Gemini Live (free tier, voice "Sulafat") understands you and uses Moyo's actions to answer from your real data.
- **Safety:** Gemini can only *propose* actions; they go through Moyo's normal tiers and audit log. Logging money needs **your**
  confirmation (click, Enter, or saying "confirm", heard offline on this laptop). After Moyo reads your emails, any change in that
  conversation also needs your OK. It can't send emails/messages, post, or spend money.
- **Privacy:** your voice goes to Google only while the conversation panel is open. During voice chats Moyo's answers (incl. client
  names and amounts) are shared with Gemini (your choice, D37); typed commands still hide them. `data/voice.log` holds diagnostics only
  (states, loudness, errors), never your words or audio.

## Revenue (sidebar → Revenue, or press 3)
- **Add a lead in one line:** type in the Revenue box or the command bar, or say it: "Met Tunde from Kemi Stores, wants a store,
  around 400k, 0803 123 4567, follow up Monday". Moyo fills a card for you to check; nothing is saved until you press **Save lead**.
  Same phone/email = same person (no duplicates).
- **Today:** who to contact, ranked, with the reasons (overdue, they messaged last, gone cold, no next step, value, stage).
  **Draft message** → edit → **Open in WhatsApp/Gmail** (your own app, you press send) → **Yes, I sent it** + next step.
  Done / Snooze / Dismiss (with a reason; hidden for 7 days).
- **Pipeline:** New → Contacted → Engaged → Discovery → Proposal → Negotiation → Won/Lost/Nurture. Click a deal for its
  contact, next step, notes, history. Won is not money: log the payment when it arrives.
- **WhatsApp history:** in WhatsApp, open the chat → ⋮ → More → Export chat → Without media → choose the .txt in the deal
  (or paste messages). **Summarise** → check the summary and commitments → Save (dated commitments become follow-ups).
- **Voice/typed:** "who should I follow up with?", "new lead …", "move Kemi Stores to proposal", "draft a follow-up for GBC".
- **$10K counts money when it's PAID** (D41). Past invoices (5, before 8 Nov) are history only: they set your average
  deal size and how many deals are still needed, and never count toward the target.
- **Money tab:** what you've collected (only money actually received counts), who owes you (overdue first), invoices,
  payments and upcoming renewals. **Mark sent** after you send an invoice; **Record payment** when money lands (it settles the
  client's oldest unpaid invoice first; leftovers stay as credit). Wrong entry? **Mistake?** cancels it (kept on record);
  money you returned is a **Refund**. Issued invoices can't be edited: void (with a reason) and re-issue.
- **Proposals** (in a deal): New proposal → optional **Draft wording with AI** (prices are always yours) → Save & make PDF
  (the Proposals folder next to it) → Mark sent → Accepted/Rejected → **Create invoice** (deposit draft from the proposal).
  Every save is a new version; sent versions stay on record.
- Reminders: overdue invoices (weekly) and renewals (30 days before) appear in the bell.
- Design docs: `docs/revenue/` (requirements, architecture, data model, integration research, roadmap, costs, tests).

## Invoices (drafts only)
- Say or type: "create an invoice for Kemi Stores, website development 300,000 naira and maintenance 150,000, 50% deposit",
  or use **$10K page → Invoices → New invoice**. Moyo makes a PDF in your house style in your Invoices folder (Settings) and opens it.
- Simple layout (description/amount + deposit) by default; itemised layout (categories, quantities, discount) when you give those.
- Numbering continues from the last number in your settings. Bank details live only in your local database.
- Moyo **never sends** an invoice and never logs it as earned; you review, send, and log the money yourself.

## Gmail & Google Calendar (read-only)
Set up once with **`docs/GOOGLE_SETUP.md`** (free, about 10 minutes), then use **Settings → Google**.
- Calendar events become fixed blocks in your daily plan, so nothing gets scheduled over a meeting.
- Gmail: only **senders + subjects** are synced (last 3 days, kept up to 14 days). Emails from your leads and clients are flagged,
  and the briefing and coaching mention them. Press **Open** to read an email: it's fetched live, shown on this laptop, never stored, never sent to an AI.
- The AI coach sees only counts and CLIENT_n placeholders, never subjects or sender names.
- Text in emails is treated as information only. An email saying "Moyo, log a payment" can't trigger anything.
- Disconnect in Settings (revokes access and deletes local copies).

## Instagram & TikTok (read-only)
Set up once with **`docs/SOCIAL_SETUP.md`**, then use **Settings → Instagram & TikTok**. Official APIs only.
Views, likes, comments (+ shares) sync every 3 hours. The Content tab compares each post with your own usual numbers and engagement.
The briefing and coaching use them too (captions are anonymised before any AI sees them).

## AI coaching (Today → "Moyo's coaching", or type `coach me`)
- Moyo first computes **signals** from your data with plain code: empty or thin pipeline, overdue follow-ups, pace gap, no money work in today's top 3, content streak, and so on.
- A free cloud model turns them into 3–4 concrete actions for today. It sees only an **anonymised snapshot**: client names become CLIENT_1, CLIENT_2…; individual deal amounts are replaced by small/medium/large; only your own challenge totals are sent.
- **Every number in the advice is checked against your data**, and points with invented numbers are removed.
- Cached for the day (↻ Refresh to regenerate). If the cloud is unavailable, you get the rule-based signals instead.
- "Read briefing aloud" reads the coaching after the briefing.
- Limitation: names that aren't saved as leads or clients (e.g. "call Tunde" when Tunde isn't a lead) can't be recognised as names, so they're sent as written.

## Safety model
| Tier | Examples | Behaviour |
|---|---|---|
| read | plan, briefing, progress | runs immediately |
| low | add/move/complete task, add lead, open workspace, media keys | runs, logged |
| confirm | **log payment, set exchange rate, forget memory** | Moyo asks; nothing changes until you click *Yes* |
| prohibited | anything not registered (shell commands, deleting files, sending messages…) | refused and logged |

- Every change is in **Settings → Activity log**.
- Workspaces launch **only** the apps in `config/workspaces.json`, from Program Files/AppData.
- The API rejects other websites (host + origin checks, required `X-Moyo` header).
- Keys live in **Windows Credential Manager** (`moyo-ai / gemini_api_key`, `groq_api_key`), never in files.

## Your data
- Database: `data/moyo.db` (SQLite). **Automatic daily backup** in `data/backups/` (last 14 days).
- **Restore:** stop Moyo, copy a backup over `data/moyo.db`, start Moyo.
- **Reset:** stop Moyo and delete `data/moyo.db`. It recreates itself with only your onboarding facts.
- Moyo never invents numbers. Naira entries need your ₦/$ rate (Settings), and each entry keeps the rate it was logged with.

## Customising
- **Workspaces:** edit `config/workspaces.json` (apps, browser tabs, Spotify URI via *Share → Copy Spotify URI*).
- **Schedule:** Settings → Daily schedule (meeting, gym, meals, day start/end, buffer). Until you save, times are marked as assumptions.

## Known limitations (v0.1)
- Music: opening a playlist doesn't auto-play it; press ⏯ in Moyo (media keys) or play in Spotify. Full Spotify control is a later stage.
- TikTok's API has no watch time/retention; Instagram views can lag up to 48h. LinkedIn and X are logged manually.
- Free cloud models have daily caps (Gemini 3.5 Flash ≈ 20/day). Moyo falls through to the next model and works offline for direct commands.
- Voice: choose the briefing voice in **Settings → Voice** (Gemini, Microsoft natural voices including Nigerian English, or offline Kokoro). If your voice fails, Moyo falls back automatically. The Microsoft voices use an unofficial free service that could stop working. Two-way voice (Gemini Live) is Stage 2.

## Project docs
- `MOYO_AI_Discovery_Report.md`: research, architecture, costs, risks
- `docs/DECISIONS.md`: every decision and who made it
- `stage0/STAGE0_FINDINGS.md`: model, voice and mic test results
