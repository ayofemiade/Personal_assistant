# Connect Moyo to Instagram & TikTok (free, official APIs)

Moyo reads **views, likes and comments** (plus shares where offered) for your posts. It's **read-only**:
it can't post, comment, like or change anything. No scraping, no passwords. Tokens are kept in Windows Credential Manager.
**Cost:** $0. If any screen asks for payment details, stop: Moyo is designed to run at $0.

Both platforms make you create a free "developer app". You stay in **development / sandbox mode**, which is
allowed for using **your own account** and doesn't need app review.

---

## Instagram (Business account) ≈ 10 min

1. Go to **https://developers.facebook.com** → log in with Facebook → **Get started** if asked
   (Meta may want to verify your phone or email).
2. **My Apps → Create app**
   - Use case: **"Manage messaging & content on Instagram"** (the Instagram API).
   - App name: `Moyo` → **Create app**. You don't need to connect a business portfolio.
3. In the app dashboard open **Instagram → API setup with Instagram business login**.
4. Under **Generate access tokens**, click **Add account** and log in with your **Instagram Business account**.
   - If Instagram shows a **tester invite**, accept it in the Instagram app:
     *Settings → Website permissions / Apps and websites → Tester invites → Accept*.
5. Click **Generate token** next to your account → approve → **copy the token** (a long text starting with `IG…`).
6. In Moyo: **Settings → Instagram & TikTok → paste the token → Connect.**

Moyo checks the token, shows your @username, and does the first sync.
The token lasts 60 days and **Moyo renews it automatically** every week while Moyo is running.
If Moyo is off for more than 60 days, generate a new token and paste it again.

> Instagram can take **up to 48 hours** to finalise a post's views. Brand-new posts may show "n/a" at first.

---

### If views show "n/a" ("missing instagram_manage_insights")
Your token can read posts but not insights. Fix it once, and drop permissions Moyo doesn't need:
1. Meta app → **Use cases → Customise → Permissions and features**.
2. Find **`instagram_manage_insights`** (may be listed as `instagram_business_manage_insights`) → **Add**.
3. **Remove** anything Moyo doesn't use, if it's listed as added: `instagram_content_publish`, `instagram_manage_messages`,
   `instagram_manage_comments`, `ads_management`, `ads_read`. Moyo never posts, messages or runs ads, and a token
   without those powers is safer if it ever leaks.
4. Go back to **API setup with Unified login → Generate access tokens → Generate token**.
   If the consent screen lists permissions, allow **insights** and **basic**, and untick the others if offered.
5. In Moyo: **Disconnect** Instagram, then paste the new token + the account ID (`1784…`) → **Connect**.

## TikTok (personal account) ≈ 15 min

1. Go to **https://developers.tiktok.com** → **Log in** with your TikTok account → register as an individual developer if asked.
2. **Manage apps → Connect an app** (create app). Name: `Moyo`. Fill the short description.
   If it asks for an icon, any square image is fine.
3. Select the **Desktop** platform.
4. **Add products:** **Login Kit** and **Display API**.
5. **Scopes:** make sure these are ticked: `user.info.basic`, `user.info.stats`, `video.list`.
6. **Login Kit → Redirect URI (Desktop):** add exactly:
   ```
   http://127.0.0.1:8977/callback/
   ```
7. **Sandbox:** switch to **Sandbox**, create a sandbox if needed, and under **Target users** add **your own TikTok account**.
   (Sandbox only works for listed accounts, which is all Moyo needs.)
8. Copy the **Client key** and **Client secret** shown for that sandbox app.
9. In Moyo: **Settings → Instagram & TikTok → TikTok → paste Client key + Client secret → Save → Connect TikTok.**
   A TikTok tab opens; approve. It says *"Moyo is now connected to TikTok"*. Close it.

Moyo refreshes TikTok's access automatically (the refresh token lasts about a year).
TikTok only shares your **public** videos; private and draft videos aren't included.

---

## What you'll see
- **Content tab:** each post from the last 7 days with views, likes, comments and engagement
  ((likes + comments + shares) ÷ views), compared with **your usual** (the median of your previous 14 posts).
- **Morning briefing:** yesterday's posts, e.g. *"2.1 times your usual 1,000 views; engagement higher than usual."*
- **Coaching:** judges posts by engagement and against your own average, not raw views, and suggests a content experiment.
- Your daily TikTok/Instagram checklist ticks itself when a synced post exists.
- Moyo syncs every 3 hours while running, or press **↻ Sync metrics** in the Content tab.

## Troubleshooting
| Message | Fix |
|---|---|
| Instagram "token expired or invalid" | Generate a new token (step 5) and paste it again. |
| Instagram metrics show n/a | Normal for very new posts (Instagram lags up to 48h), and for some post types. |
| TikTok "redirect_uri" error | The Redirect URI must be exactly `http://127.0.0.1:8977/callback/` (step 6). |
| TikTok "didn't grant: video.list" | Add the missing scope in your TikTok app (step 5), then Connect again. |
| TikTok login says you're not allowed | Add your account under **Sandbox → Target users** (step 7). |
| "Port 8977 is busy" | Close other apps using it, or restart the laptop, then Connect again. |
