# Revenue Toolkit: Integration Research

Researched 13 Nov 2026. **Most WhatsApp facts below come from reputable vendor/press sources, not Meta's own docs**. Treat them as strong indications and re-check on Meta's official pages before committing money.

## 1. WhatsApp

### Findings
| Topic | Finding | Confidence / source |
|---|---|---|
| Coexistence (Business App + API on the **same** number) | Launched May 2025, but **not available for Nigerian (+234) numbers**; HighLevel suggests a new number or BSP migration instead | Medium-high: several vendors agree ([HighLevel](https://help.gohighlevel.com/support/solutions/articles/155000003417-whatsapp-coexistence-feature-for-dual-platform-messaging), [WANotifier](https://wanotifier.com/whatsapp-coexistence-guide/), [Sandra](https://sandra.ch/en/blog/whatsapp-coexistence-the-business-app-and-the-api-on-the-same-number)) |
| Pricing model | Per delivered message since 1 Jul 2025 | High ([Yournotify](https://yournotify.com/blog/whatsapp-pricing-update-2026/)) |
| Nigeria billing | Service/utility messages became **chargeable from 1 Oct 2026**, ≈ **$0.0101 (~₦14)** each; a payment method had to be linked by 30 Sep 2026 | Medium-high ([Techpoint](https://techpoint.africa/guide/whatsapp-will-charge-businesses-per-message/), [Profiled](https://profiled.ng/blog/whatsapp-%E2%82%A614-message-charge-what-nigerian-businesses-must-know)) |
| Marketing templates (Nigeria) | ≈ $0.05–0.06 per message (sources differ) | Medium ([dmly rate card](https://dmly.io/whatsapp-business-api-pricing-by-country/)) |
| Free 24-h service window replies | **Sources conflict** for Nigeria after 1 Oct 2026 | Low: must check Meta's pricing page |
| Free entry-point replies (from Click-to-WhatsApp ads / Page button) | Reported unchanged | Medium |
| BSP markup (Twilio, WATI…) | +$0.003–0.010+/message on top | Medium |
| Test setup | Meta gives a free test number for a few verified recipients; no payment needed for testing | Medium ([Omnifox](https://omnifox.io/blog/whatsapp-cloud-api-setup-guide-2026), [MyAiChats](https://myaichats.co.uk/whatsapp-cloud-api-test-number/)) |
| Webhooks | Need a **public HTTPS** endpoint, verify-token handshake, subscribe to `messages`, retries up to 7 days, sign with app secret | Medium-high ([dev.to guide](https://dev.to/instatunnel/whatsapp-cloud-api-webhooks-on-localhost-the-verify-token-handshake-retries-and-app-secret-setup-2ofo)) |
| Production number | Must not already be on WhatsApp (unless coexistence, which Nigeria can't use); new portfolios get 2 numbers | Medium ([Meta docs, older](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers)) |
| History | The API sees **only messages after connection**. It can't read your existing chats | High (inherent to the API) |
| Click-to-chat `wa.me/<number>?text=<urlencoded>` | Official, free, opens your own WhatsApp with the text pre-filled; **you** press send | High ([WhatsApp FAQ](https://whatsapp.com/faq/en/general/26000030)) |
| Export chat | Built into WhatsApp (chat → More → Export chat → without media) → `.txt` | High (app feature) |

### Options compared
| Option | Cost | Uses your current number? | Reads chats | Sends | Effort/risk |
|---|---|---|---|---|---|
| **A. Assisted (wa.me + export/paste)** | **₦0** | **Yes** | When you import/paste | You press send | Low. Works today |
| B. Cloud API on your current number | ₦/msg + you lose the WhatsApp app on that number (no coexistence in NG) | Moved to API only | New msgs only | API (approved) | High: disrupts how clients reach you |
| C. Cloud API on a **dedicated** MoyoCode number | ~₦14/service msg (+ marketing), SIM, payment method; tunnel free | No (new number) | New msgs only | API (approved) | Medium; clients must adopt the new number |
| D. BSP (WATI/Twilio…) | Subscription + markup | Same constraints as B/C | | | Paid; unnecessary for one user |
| E. Unofficial WhatsApp Web automation | "free" | Yes | Yes | Yes | **Rejected**: violates terms, risks a ban (your brief forbids it) |

### Recommendation
**Phase 1 = Option A.** It's free, official, and works with the number your clients already use. It keeps you as the sender (Level 3 approval comes built in), and it removes the real bottleneck: *remembering whom to message, and what to say*.
**Revisit Option C** when at least one of these is true: (1) inbound WhatsApp leads exceed ~10/week, (2) you run Click-to-WhatsApp ads, or (3) you want automatic logging badly enough to pay ~₦14/message. Phase 4 is designed so C plugs in without rebuilding (same `conversations/messages`, `webhook_events`).

**Do you need Moyo connected to WhatsApp so it can send by itself?** Not now, and not as autonomous sending. In Nigeria the official route can't share your current number with the app, it now costs per message, and it can't see your existing conversations. Your brief also rightly limits sending to human-approved. The assisted flow gives about 90% of the value at ₦0.

## 2. Email
| Option | Cost | Notes |
|---|---|---|
| **Gmail compose deep link** (`mail.google.com/mail/?view=cm&to=&su=&body=`) | ₦0 | Opens pre-filled; you send. No new Google permission. **Phase 1** |
| Inbound auto-logging | ₦0 | Already syncing metadata (`gmail.readonly`) *(exists)*. Match sender email → contact timeline |
| Gmail drafts via API (`gmail.compose`) | ₦0 | New restricted scope + re-consent. Optional Phase 4 |
| Sending via API (`gmail.send`) | ₦0 | Not recommended: violates "Moyo never sends" |

## 3. Payments
| Option | Cost | Notes |
|---|---|---|
| **Manual recording** of bank transfers (method, reference, date) | ₦0 | Matches how you're paid today. **Phase 1–2** |
| Paystack payment links on invoices + webhook auto-record | Local cards: **1.5% + ₦100** (₦100 waived under ₦2,500; capped at ₦2,000), per [Paystack pricing](https://paystack.com/pricing) | Useful for international/card clients. Needs public HTTPS for webhooks. Phase 4, opt-in |
| Bank statement import (CSV) for reconciliation | ₦0 | Phase 3 nice-to-have |

## 4. Other
- **Lead sources:** referrals, past clients, inbound DMs, posts, manual research. No scraping (Instagram/LinkedIn/Google Maps terms). AI may suggest target segments and draft outreach. You choose whom to contact.
- **Public endpoint (Phase 4 only):** Cloudflare Tunnel (free) on `moyocode.com` *(needs the domain's DNS on Cloudflare)*. A quick `trycloudflare` URL changes on each restart, so it's unsuitable for webhooks.
