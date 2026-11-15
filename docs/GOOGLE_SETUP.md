# Connect Moyo to Gmail & Google Calendar (free, ~10 minutes)

Moyo talks to Google through **your own free Google Cloud app**, so your data goes straight from Google
to your laptop with no third-party service in between. You do the sign-ins and the clicks. Moyo never sees your password.

**What Moyo gets:** read-only access to Gmail and Calendar. It **cannot** send, delete or change anything.
It syncs calendar events and email **senders + subjects**; an email's content is fetched only when you press *Open*.
**Cost:** $0. No billing account or card is needed. If any screen asks for payment details, stop: Moyo is designed to run at $0.

---

## 1. Create the project
1. Go to **https://console.cloud.google.com** and sign in with the Google account whose Gmail/Calendar you want Moyo to use.
2. Accept the Cloud terms if asked (first time only).
3. Top bar → project picker → **New project** → name it `Moyo AI` → **Create**, then make sure it's selected.

## 2. Turn on the two APIs
1. Menu ☰ → **APIs & Services → Library**.
2. Search **Gmail API** → open → **Enable**.
3. Back to Library → search **Google Calendar API** → open → **Enable**.

## 3. Set up the sign-in screen (Google Auth Platform)
1. Menu ☰ → **APIs & Services → OAuth consent screen** (it may be called **Google Auth Platform**) → **Get started**.
2. **App name:** `Moyo` · **User support email:** your email → Next.
3. **Audience:** **External** → Next.
4. **Contact email:** your email → Next → tick the user-data policy → **Create**.
5. Open **Audience** → under *Publishing status* click **Publish app** → **Confirm**.
   - This matters: in "Testing" mode Google logs Moyo out **every 7 days**. "In production" keeps it connected.
   - Your app stays *unverified*, which is fine for personal use (you'll see a warning when connecting; see step 5).

## 4. Create the Desktop client and download it
1. Open **Clients** (or *Credentials*) → **Create client** (or *Create credentials → OAuth client ID*).
2. **Application type: Desktop app** · Name: `Moyo desktop` → **Create**.
3. Click **Download JSON** (a file like `client_secret_….json`).

## 5. Connect in Moyo
1. Open Moyo (**Ctrl+Alt+M**) → **Settings** → **Google: Gmail & Calendar**.
2. **Choose File** → pick the JSON you downloaded. Moyo stores it in Windows Credential Manager.
   You can then delete the downloaded file.
3. Click **Connect Google**. A browser tab opens:
   - Choose your account.
   - You'll see **"Google hasn't verified this app"**. That's expected because it's your own app.
     Click **Advanced → Go to Moyo (unsafe)**.
   - **Tick both boxes** (read Gmail, read Calendar) → **Continue**.
   - The tab says *"Moyo is now connected to Google"*. Close it.
4. Back in Moyo the card shows **connected**, and the first sync runs. Your calendar appears in **Today → Schedule**,
   and recent mail appears in **Today → Inbox**.

## Afterwards
- Moyo re-syncs every 15 minutes while it's running, or press **Sync now**.
- Once your calendar has your real startup meeting and gym times, delete the guessed ones in
  **Settings → Daily schedule** so they don't appear twice.
- **Disconnect** any time in Moyo (revokes access and deletes Moyo's local copies), or at
  https://myaccount.google.com/permissions.

## Troubleshooting
| Message | Fix |
|---|---|
| "This client is a 'Web application'" | Create the client again as **Desktop app** (step 4). |
| "Google refused the request (403). Is the API enabled?" | Enable the Gmail API and Calendar API (step 2), wait a minute, then Sync now. |
| "access expired or was revoked" | You may still be in Testing mode: **Publish app** (step 3.5), then Connect again. |
| "you didn't tick: …" | Connect again and tick both permission boxes. |
| "didn't return a refresh token" | Remove Moyo at myaccount.google.com/permissions, then Connect again. |
