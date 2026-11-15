# Revenue Toolkit: Cost Register

Target: **$0/month for Phases 0–3.** Prices were checked 13 Nov 2026 (see the integration research for sources). Every paid item is opt-in and needs your approval.

| Dependency | Phase | Truly free? | Card needed? | Limits / restrictions | Licence | Possible future charge | Privacy note |
|---|---|---|---|---|---|---|---|
| SQLite, FastAPI, Python (exists) | 0–3 | Yes | No | none practical for one user | Public domain / MIT / PSF | none | local only |
| Headless Chrome PDF (exists) | 2 | Yes | No | n/a | already installed | none | local only |
| Gemini API free tier (exists) | 1–3 | Yes, within quota | No | daily caps (e.g. gemini-3.5-flash ≈ 20/day; flash-lite higher), rate limits | Google ToS | Paid tier only if you opt in | Free-tier inputs may be used by Google to improve products. Typed paths are redacted (D7); voice and imported chats per decisions D37/D-6 |
| Groq free tier (exists, fallback) | 1–3 | Yes, within quota | No | rate limits | Groq ToS | paid tier opt-in | redacted inputs |
| Vosk offline speech (exists) | 1 | Yes | No | n/a | Apache-2.0 | none | offline |
| Gemini Live voice (exists) | 1 | Yes, within quota | No | session/rate limits | Google ToS | opt-in | voice → Google while the orb is open (D11/D37) |
| `wa.me` click-to-chat | 1 | Yes | No | you press send | WhatsApp ToS | none | text goes to WhatsApp only when you send |
| WhatsApp export/paste import | 1 | Yes | No | manual step | n/a | none | stored locally |
| Gmail read sync + compose links (exists) | 1 | Yes | No | API quotas ample | Google ToS | none | metadata only |
| **WhatsApp Cloud API** | 4 | **No** | **Yes** (payment method required) | per message: service/utility ≈ $0.0101 (~₦14), marketing ≈ $0.05–0.06 in NG; free window status unclear post-1 Oct 2026 | Meta ToS | **usage-based** | messages pass through Meta; webhook payloads processed and discarded |
| Dedicated SIM/number for WhatsApp API | 4 | No | No | one-off SIM cost | n/a | airtime to keep it active | |
| Cloudflare Tunnel | 4 | Yes (free plan) | No | needs moyocode.com DNS on Cloudflare | Cloudflare ToS | none expected | traffic through Cloudflare |
| **Paystack** links/webhooks | 4 | No fee to integrate; **per transaction** | Business account | local: 1.5% + ₦100 (waived < ₦2,500), cap ₦2,000 | Paystack ToS | per payment (often passed to the client) | payer data at Paystack |

## Operating cost forecast
| Scenario | Monthly |
|---|---|
| Phases 0–3 as designed | **₦0** |
| + WhatsApp API, 300 service/utility msgs/month | ≈ 300 × $0.0101 ≈ **$3 (~₦4k)** + SIM airtime (*estimate; rates to re-verify*) |
| + 100 marketing templates/month | ≈ +$5–6 |
| + Paystack on ₦1M collected by card | ≈ ₦15,000 + ₦100×n (cap ₦2,000/txn) |

## Cost controls (for Phase 4)
Monthly spend cap setting. A per-message cost is recorded on `messages.cost_minor`. A warning appears at 80% of the cap, and sending stops at 100% until you raise it. No marketing templates without explicit per-campaign approval.
