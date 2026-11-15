# Moyo AI: Design System

> Living document. Every new feature must follow it, and every visual decision that changes it is recorded in §9.
> Code source of truth: `moyo/static/style.css` (tokens at the top) and the render helpers in `moyo/static/app.js`.

---

## 1. Identity

**Moyo** (Yoruba: *joy*) is a calm, warm, competent executive assistant: closer to a trusted chief of staff
handing you a morning note than to a sci-fi AI cockpit.

| Principle | What it means in the UI |
|---|---|
| **Calm over busy** | One clear focus per screen. Secondary info is collapsed or summarised ("+30 promos"), never dumped. |
| **Warm, not neon** | Warm ink/paper neutrals and one saffron accent ("Lagos morning"). No neon, glow, glass blur or decorative gradients. |
| **Editorial clarity** | Page titles and key numbers use a serif (Fraunces) for a "briefing note" feel. Everything else uses Inter. |
| **Numbers are sacred** | Tabular figures, units always shown, nothing estimated without saying so, empty data shown as "n/a" not 0. |
| **Honest states** | Every surface has designed loading, empty, error and success states that tell you what to do next. |
| **Keyboard-first desktop app** | Sidebar navigation, Ctrl+K command bar, visible focus, no hover-only actions. |

Inspiration (principles only, nothing copied): the restraint of Linear, the readable density of Things 3,
the "note from a person" tone of a well-written morning newsletter.

## 2. Tokens

### Colour (defined once in `:root`, dark theme follows `prefers-color-scheme`)
| Token | Light (paper) | Dark (ink) | Use |
|---|---|---|---|
| `--bg` | `#F6F3EE` | `#13110F` | app background |
| `--surface` | `#FFFFFF` | `#1B1916` | cards, panels |
| `--surface-2` | `#EFEBE4` | `#24211D` | inset areas, table headers, hover |
| `--line` | `#E2DCD2` | `#33302B` | hairlines, borders |
| `--text` | `#1D1A16` | `#F1ECE4` | primary text |
| `--text-2` | `#5F584E` | `#ADA597` | secondary text (AA on surface) |
| `--text-3` | `#857D71` | `#857D70` | captions, placeholders (large/secondary only) |
| `--accent` | `#B4650F` | `#F2A93B` | primary action, focus ring, active nav (saffron) |
| `--accent-ink` | `#FFFFFF` | `#1B1308` | text on accent |
| `--accent-soft` | `#F6E6CF` | `#3A2A12` | selected/active backgrounds |
| `--good` / `--good-soft` | `#1E7A4F` / `#DDF0E5` | `#5CC995` / `#17301F` | money earned, on track, success |
| `--warn` / `--warn-soft` | `#B4421E` / `#F8E0D6` | `#F08A6A` / `#3A1E15` | behind pace, overdue, errors to fix |
| `--info` / `--info-soft` | `#2D5FA8` / `#DFE8F6` | `#79A7EB` / `#18243A` | calendar events, neutral notices |
| category hues | revenue `--good`, client `--info`, sales `--accent`, content `#B5487A`/`#E58AB0`, study `#7C5BB5`/`#B9A0F0`, personal `#55803A`/`#9CC77D`, other `--text-3` | | 6px dots + timeline edge only |

Rules: accent is used for **one primary action per area** and active state. Status colours never decorate.
Body text contrast ≥ 4.5:1, large text/icons ≥ 3:1 (checked for both themes).

### Typography
| Token | Value | Use |
|---|---|---|
| `--font-display` | Fraunces 600, fallback Georgia | page titles, greeting, hero numbers |
| `--font-ui` | Inter 400/500/600, fallback Segoe UI | everything else |
| Scale | 12 / 13 / 14 (base) / 16 / 20 / 28 / 40 px | caption / small / body / lead / section / page title / hero number |
| Numbers | `font-variant-numeric: tabular-nums` | all metrics, times, money |
| Labels | sentence case, 13px, `--text-2` | no ALL-CAPS headings (they shouted and all looked the same) |

### Space, shape, depth, motion
- Spacing: 4-pt scale: 4, 8, 12, 16, 20, 24, 32, 48. Card padding 20; page gutter 32 (16 on small screens).
- Radius: 8 (controls), 12 (cards), 999 (pills).
- Depth: hairline borders, not shadows. A single soft shadow (`--shadow-pop`) only for floating layers (menus, dialogs, toasts).
- Motion: 120–180ms ease-out for state changes only (hover, open/close, progress fill). No looping or decorative animation.
  `prefers-reduced-motion` disables all transitions.

## 3. Layout

- **App shell:** left **sidebar** (232px) with navigation, workspace launcher and media controls; **main** column (max 1180px).
  - ≤ 1100px: sidebar collapses to a 64px icon rail (labels as tooltips + `aria-label`); two-column layouts stay.
  - ≤ 900px: content becomes single-column.
  - ≤ 760px: navigation becomes a bottom tab bar.
- **Command bar** sits in the sticky page header (not floating over content). Ctrl+K focuses it from anywhere; replies open in a panel directly under it.
- **Page header:** serif title + one-line context (e.g. "Day 5 of 92 · $805 needed this week").
- **Grids:** 12 columns, 20px gap. Two-column layouts are 7/5 (primary/secondary). Never leave a lone half-width card: secondary items become a list or stretch.

## 4. Components

| Component | Spec |
|---|---|
| **Button** | `.btn` (neutral, bordered), `.btn-primary` (accent, max one per area), `.btn-ghost` (text), `.btn-danger` (warn text). Height 36 (32 small). Icon + label; icon-only buttons need `aria-label` + tooltip. |
| **Card** | `.card`: surface, 1px line, radius 12, padding 20. Header = title (16px/600) + optional meta + right-aligned action. No ALL-CAPS. |
| **Stat** | value (serif for hero, Inter 600 for others) + label underneath in `--text-2`. Units always visible. |
| **Pill** | status only: `good`, `warn`, `info`, `accent`, neutral. Max one pill per row item. |
| **List row** | 44px min height, hairline separators, primary text + meta line, actions on the right (visible, not hover-only). |
| **Timeline** | time column (tabular) + 3px category edge + title; "now" marker; past items dimmed and collapsible. |
| **Form** | Every input has a visible `<label>` (or `aria-label` when inline). Optional fields are hidden behind "More options". Primary submit right-aligned. |
| **Disclosure** | Native `<details>/<summary>` for secondary content (full briefing, add forms, activity log, promos). |
| **Banner** | Inline, actionable: icon + one sentence + action button. Warn for blockers, info for tips. |
| **Toast** | Bottom-right, 3s, `role="status"`, for confirmations of completed actions. |
| **Dialog** | For reading an email and confirmations; Esc closes; focus moves into it and returns afterwards. |
| **Icons** | Inline SVG, 1.75px stroke, 18px, `currentColor` (Lucide-style, drawn in-house). No emoji as UI icons. |
| **Wake orb** | Desktop overlay outside the browser (tkinter). Always dark tokens (`--surface` #1B1916, accent #F2A93B) so it reads on any wallpaper; 380 px wide (DPI-scaled), top-right 24 px from the edges, Windows 11 rounded corners, fully opaque. Starts as dot + "Moyo · Waking up", grows as captions arrive. Pulsing saffron dot = awake/speaking, steady = waiting for you. One primary button (Open dashboard), keyboard first (Enter / S / Esc), auto-closes after 90 s. Captions always shown, so it works with the sound off. |
| **Mic indicator** | Sidebar, under the clock: green dot + "Listening for claps" whenever the mic is open (dot only on the icon rail). Pulse respects reduced motion. |

## 5. States (required for every data surface)
| State | Pattern |
|---|---|
| Loading | Skeleton lines in the card's shape (shimmer off under reduced motion). Never a blank card. |
| Empty | One sentence on what this is + the single next action (button or example command). |
| Error | What failed in plain words + **Retry**. Keep the user's typed input. |
| Success | Toast for actions; inline ✓ for saved settings. |
| Partial / unavailable data | "n/a" with a tooltip saying why (e.g. "too early: posted < 24h ago"). |

## 6. Interaction
- Navigation: sidebar links (`aria-current="page"`), number keys 1–7 jump to sections when not typing, Ctrl+K command bar, Esc closes panels and dialogs.
- Destructive or money actions always confirm (Tool Gateway). The UI never bypasses it.
- Progressive disclosure: show today's decisions first; details one click away.
- Dates are shown in the user's local time (Africa/Lagos) and human format ("Fri 13 Nov"); ISO only in exports.

## 7. Accessibility checklist (per feature)
- [ ] Keyboard reachable, logical tab order, visible `:focus-visible` ring (2px accent + offset)
- [ ] Labels for every control; icon buttons have `aria-label`
- [ ] Contrast checked in light and dark
- [ ] `role="status"`/`aria-live` for async results (command replies, toasts)
- [ ] No information by colour alone (pills carry text)
- [ ] Works at 200% zoom, at 1024px and at 400px widths
- [ ] Reduced-motion respected

## 8. Audit of v0.1 UI (13 Nov 2026) → what changed
| # | Problem found | Fix |
|---|---|---|
| A1 | Today page 2,600px tall: briefing, coaching, plan, schedule, content, follow-ups, a full inbox and workspaces all expanded | Focus-first layout; inbox shows only people/leads, with promos summarised; workspaces moved to the sidebar |
| A2 | Floating command dock covers content (Top 3, schedule) at every scroll position | Command bar moved into the sticky header |
| A3 | Every card identical (ALL-CAPS label, same weight), so no hierarchy | Serif page/hero type, sentence-case card titles, primary vs secondary columns |
| A4 | Generic "AI purple" accent, emoji icons (🎬💼🔥📅) | Saffron identity, in-house SVG icon set |
| A5 | Unbalanced grids: Top 3 card half-empty beside a long schedule; lone half-width cards; orphan stat wrapping | 7/5 grid with Plan (Top 3 + coaching) and compact Schedule; stats in fixed rows |
| A6 | Briefing text duplicated figures shown in cards and was cut off by a fade mask | Briefing becomes a "Listen / Read" disclosure; numbers live in one place |
| A7 | Forms always open, unlabeled ("45", "once"), US date placeholders | Labelled fields, "Add" disclosure panels, local dates |
| A8 | **Bug:** default dates used UTC (`toISOString`), so between 00:00 and 01:00 Lagos time, earnings and tasks defaulted to *yesterday* | Local-date helper used everywhere |
| A9 | Settings: one long undifferentiated scroll (rate, schedule, Google, socials, voice, log) | Grouped sections with an in-page index; activity log collapsed |
| A10 | Memory items editable only by clicking text (no affordance) | Explicit Edit button → inline field with Save/Cancel |
| A11 | No loading/error states: cards blank while loading; failed requests silently empty | Skeletons + inline error with Retry for every view |
| A12 | Schedule overlaps (assumed "Startup meeting" and calendar standups both shown) | Calendar events win; assumed fixed blocks that overlap a calendar event are hidden and noted |
| A13 | Focus outlines missing on many controls; nav not announced as current | `:focus-visible` everywhere; `aria-current` |

## 8b. Verification record: redesign v1 (13 Nov 2026)
Rendered with Playwright (Chromium) and inspected, not assumed:
- **Screens:** all 7 views at 1440×900 dark; Today in light theme; Today at 1024×768 (icon rail, 2 columns) and 420×860 (bottom nav, single column).
  Horizontal overflow = 0 at every size.
- **Interactions (demo database):** command bar → task added (P1, local "tomorrow" date) → appears in Tasks → completed via checkbox; memory Edit → Save →
  restored; keyboard `6` → Memory, `Esc` closes reply, `Ctrl+K` focuses command bar; Log-money form defaults to the local date (UTC bug A8 fixed).
- **States:** simulated network failure shows "Couldn't load this page …" + Retry → Retry recovers.
- **Accessibility scan:** 0 unlabelled inputs/selects/textareas, 0 unnamed buttons across all views (details opened). Console: 0 errors.
- **Regression:** 103 automated tests pass (incl. new: calendar event hides overlapping assumed block).

Every future feature repeats this: render it, inspect it at 1440 / 1024 / 420 in both themes, scan labels, test empty/error states.

## 9. Decision log
| Date | Decision | Why |
|---|---|---|
| 2026-11-13 | Saffron accent on warm ink/paper neutrals | Distinctive, warm, readable; avoids the generic AI-purple dashboard look |
| 2026-11-13 | Fraunces (display) + Inter (UI), both OFL via Google Fonts with system fallbacks | Editorial "briefing" character; still works offline thanks to fallbacks |
| 2026-11-13 | Sidebar shell instead of top tabs | Desktop-app feel, room for workspace launcher, scales to more sections |
| 2026-11-13 | Command bar in header, not floating | It covered content; a header placement is always visible without overlap |
| 2026-11-13 | Voice picker: current voice first, full list behind a disclosure; Gemini voices show name + mood | 27 always-open voices dominated Settings |
| 2026-11-13 | Post titles in tables use text colour (accent on hover) | A column of saffron links competed with real actions |
| 2026-11-13 | UI/UX Pro Max skill **not installed yet** (MIT, third-party CLI) | Awaiting Moyosore's approval; this system was built from first principles |
| 2026-11-13 | **UI/UX Pro Max installed** (approved) as a local design reference (MIT licence), pinned upstream commit. Installed from the GitHub source, not the npm CLI (npm package lists no repository). | Inspected first: stdlib-only Python, local CSV data, no network or subprocess at runtime; writes only with `--persist` |
| 2026-11-13 | `scroll-padding` for the sticky top bar and mobile bottom nav | First Pro Max query flagged WCAG 2.2 "focus not obscured"; verified a focused field stays fully visible |

| 2026-11-13 | **Notifications:** bell + panel in the top bar; level dot (warn = urgent, accent = important, neutral = info); unread badge in accent; desktop toasts brief and silent (sound only for urgent); every item has one clear action | Pro Max "toast notifications": brief, auto-dismiss; anything actionable stays in-app |
| 2026-11-13 | "Start my day" is the single primary action in Today's header until the routine has run, then it disappears | One primary action per area; avoids a stale button |
| 2026-11-13 | Wake orb shows captions as well as speaking; the previous sentence dims when the question appears | Works muted and in noisy rooms; the question is the one thing to act on |
| 2026-11-13 | **Revenue area:** page head + one-line capture bar + segmented tabs (Today · Pipeline · Money). Today = ranked rows with reason chips (first chip = why today, highlighted) and ONE primary "Draft message" (top item only). Pipeline = horizontal board of stage columns with compact deal cards (overdue/no-next-step pills in warn). Deal details, drafts, done/snooze/dismiss and AI-summary review use `dialog.sheet` | One primary action per area; reasons make AI-free ranking explainable; sheets keep context |
| 2026-11-13 | `[hidden]` always wins (`display:none !important`); email/tel inputs share the input style | Found in verification: "Why lost?" showed on open deals; email box unstyled |
| 2026-11-13 | Talk (mic) button hidden ≤760px | It pushed the bell off-screen on phones; voice opens on the laptop anyway |
| 2026-11-13 | Card headers wrap (`flex-wrap`) instead of squeezing the title | Clap card's action button pushed "Clap to wake" onto three lines at phone width |

## 10. Tools
- **UI/UX Pro Max** (MIT, local design reference): search its style, colour, typography and UX guidance before
  designing a new surface or reviewing one.
  Treat results as guidance, then reconcile with this document. Moyo's identity tokens win unless a rule is about accessibility or usability.
  Update by re-cloning upstream, re-inspecting the scripts, and replacing the folder (record the new commit in `UPSTREAM_COMMIT.txt`).
- **Playwright** (headless browser): render and screenshot at 1440 / 1024 / 420, dark and light, for every UI change.
