# DESIGN.md

Swing Intel (Algo-trading frontend) design system.
Reference: OpenStock dashboard. Dark, dense, calm.

## Design read

- Product: personal trading decision-support dashboard
- User: one trader, daily use, scans signals and positions
- Vibe: dark tech, data-first, restrained motion
- Dials: VARIANCE 4, MOTION 3, DENSITY 7

## Hard rules

- No feature, route, API call or page logic is removed or changed
- All 8 routes stay: `/`, `/watchlist`, `/positions`, `/journal`, `/backtests`, `/news`, `/settings`, `/system`
- IN / US market switch stays
- Regime badge, live feed status, refresh button stay
- SSE alert toast stays
- Risk disclaimer footer stays
- Pages keep using `slate-*` and `indigo-*` classes. The theme is changed in `tailwind.config.js`, not per page
- **Never show UNKNOWN, STALE, DELAYED or BLOCKED in a green style.** Missing data must look different from good data
- Currency symbols are never mixed: INR values use ₹, US values use $. No combined INR+USD totals
- Every number shows its source and "as of" time (see Status language)

## Stack

- React 18, Vite, Tailwind v3, react-router-dom v6
- Icons: lucide-react only (already in project). One family, no emoji, no hand-drawn SVG
- Fonts: `@fontsource-variable/plus-jakarta-sans`, `@fontsource-variable/jetbrains-mono` (self-hosted)

## Color tokens

Neutrals (`slate` remapped, warm near-black):

| Token | Hex | Use |
|---|---|---|
| slate-950 | #0d0f0e | app background, sidebar, top bar |
| slate-900 | #181b1a | cards, panels, inputs |
| slate-800 | #222625 | active nav item, hover, table header |
| slate-700 | #2e3331 | borders, scrollbar |
| slate-600 | #444a48 | muted borders |
| slate-500 | #656c69 | captions, group labels |
| slate-400 | #8a918e | secondary text |
| slate-300 | #aeb4b1 | body text on panels |
| slate-100 | #e8eae9 | primary text |

Accent (`indigo` remapped to emerald):

| Token | Hex | Use |
|---|---|---|
| indigo-500 | #10b981 | primary button, brand mark |
| indigo-400 | #34d399 | icons, active accents, focus ring |
| indigo-300 | #6ee7b7 | accent text on dark |
| indigo-950 | #042a1f | accent tint backgrounds |

Semantic (unchanged, used by pages):

- Bullish / profit / triggered: emerald
- Caution / approaching / stale: amber
- Weak / loss / stop: rose
- Secondary data series (SMA lines, shadow mode): blue, purple

Rule: never use color alone. Pair with a label, sign (+/-) or icon.

CSS variables in `index.css`: `--background 13 15 14`, `--surface 24 27 26`, `--border 46 51 49`.

## Typography

- Sans: Plus Jakarta Sans Variable, 400 / 500 / 600 / 700 / 800
- Mono: JetBrains Mono Variable, for prices, levels, percentages, table numbers
- Numbers use tabular figures (`font-feature-settings: 'tnum'`)
- Scale: page title 18 bold, panel title 14-16 bold, body 12-14, caption 10-11
- Group labels: 10px, uppercase, tracking-widest, slate-500
- Min body text 12px

## Layout

```
+-----------+-----------------------------------------+
| Sidebar   | Top bar (sticky)                        |
| 256px     +-----------------------------------------+
| fixed     | Main (max 1600px, p-4 / lg:p-8)         |
|           |                                         |
|           | Footer: risk disclaimer                 |
+-----------+-----------------------------------------+
```

- Desktop (lg and up): sidebar is static, always visible
- Below lg: sidebar is a drawer (slides from left, dark backdrop), opened by a menu button in the top bar
- Content width: `max-w-[1600px]`
- Spacing: 4px base. Panel gap 24px. Card padding 16-20px
- Radius: cards `rounded-xl` (12px), pills `rounded-full`, buttons `rounded-lg`

## Navigation

Sidebar groups (same 8 pages as the old navbar):

| Group | Items |
|---|---|
| Markets | Dashboard, Watchlist & Live |
| Portfolio | Positions & Portfolio, Journal & Stats |
| Research | Backtests, News & Disclosures |
| System | Settings, System Health |

- Defined once in `components/navItems.ts`. Sidebar and command palette both read from it
- Active item: `bg-slate-800`, white text, semibold
- Hover: `bg-slate-900`
- Item height at least 40px
- `Ctrl/Cmd + K` opens the "Go to page" palette
- Palette: filter by name or group, arrow keys to move, Enter to go, Esc to close

## Components

Sidebar
- Brand mark (emerald square, "S") + "Swing Intel" + "Decision Support"
- Primary button: "Go to page" with `Ctrl K` hint
- Grouped nav
- Bottom: live feed status (pulse dot) and short disclaimer line

Top bar
- Page title + market subtitle
- Market pills: India, United States. Active = emerald tint + emerald border. `aria-pressed` set
- Regime chip: `{IN|US} Regime: BULLISH | CAUTION | WEAK`
- Regime numbers (xl screens): Close, 50 SMA, 200 SMA in mono
- Refresh icon button (aria-label set)

Cards / panels
- `bg-slate-900`, 1px `slate-800` border, `rounded-xl`
- Subtle inner top highlight + soft drop shadow (`shadow-card`)
- Optional `.hatch` diagonal texture on panel headers

Tables
- Header: `bg-slate-950`, uppercase, 11px, tracking-wider, slate-400
- Rows: `divide-slate-800/60`, hover `bg-slate-800/40`
- Numbers in mono, right-aligned where possible

Badges / states
- Pill with tinted background + same-hue border (e.g. `bg-emerald-950 text-emerald-400 border-emerald-800`)
- Approaching state may pulse. Nothing else loops

Buttons
- Primary: emerald fill, dark text (`bg-indigo-500 text-slate-950`)
- Secondary: `bg-slate-800`, light text
- Icon-only buttons always have `aria-label`

Alert toast (SSE)
- Bottom right, `bg-slate-900`, emerald border
- Bell icon, title, 2-line body, dismiss button
- `role="status"`, `aria-live="polite"`. No bounce

## Status language (shared by every page)

States use label + icon + tint. Never color alone.

| State | Label | Style |
|---|---|---|
| WATCHLIST | Watching | slate/blue pill |
| APPROACHING | Approaching | amber pill, may pulse |
| TRIGGERED (provisional) | Triggered, confirming | emerald outline pill |
| TRIGGERED (confirmed) | Confirmed | emerald filled pill |
| BROKE_OUT_TODAY / EXTENDED | Extended, do not chase | amber outline pill |
| INVALIDATED | Invalidated | rose pill |
| EXPIRED | Expired | slate pill |
| BLOCKED | Blocked | rose outline pill with lock icon, plus a reason line: `<stage> / <check>: <value> vs <threshold>` |
| PASS / WAIT | Pass / Wait | emerald / blue pill |

News coverage chips: CLEAR (emerald), REVIEW (amber), BLOCKED (rose), **UNKNOWN (slate, dashed border, "?" icon, never green)**.

Fundamental traffic lights: Green "Good", Yellow "Okay", Red "Weak", **grey "No data"**. Each shows the value in mono, the period, the source and a tooltip with the threshold and a plain-English meaning.

Provenance and freshness:
- Source chip, 10px: `Angel One · 10:42:15 IST`, `Zerodha · snapshot`, `Calculated`, `Imported`
- Feed badge: LIVE (emerald, pulses while connected), POLLING (blue), DELAYED (amber), STALE (rose), DISCONNECTED (slate)
- Stale or delayed values are dimmed and labelled. Cached values are never styled as live

## Research Desk (stock page tab and funnel)

- **Funnel strip** (Dashboard, per market): `Scanned > Trend OK > Setup > Fundamentals OK > News clear > Risk OK > PASS`, counts per stage, each stage clickable to filter the list
- **Stock row:** four compact role chips (Technical, Fundamental, News, Risk) with labels, plus the BLOCKED reason line when relevant
- **Research Desk flow (shown in this order everywhere):** Scout → Technician → Fundamentalist → Newsdesk → Planner → Risk Manager → Bull / Bear → Judge → Messenger. These are views over deterministic modules, never separate decision-makers.
- **Stage stepper on the stock page:** one step per role with PASS, WARN, FAIL, UNKNOWN, WAIT or NOT EVALUATED; highlight the first stopping step and its exact gate.
- **Role cards:** ten cards in four groups — Find (Scout), Analyse (Technician, Fundamentalist, Newsdesk), Plan and protect (Planner, Risk Manager), Decide and notify (Bull, Bear, Judge, Messenger). Each has a status chip, two stats, one-line reason and an expander with the checks behind it.
- Judge shows **checklist strength** ("9 of 11 checks passed") and the PASS/BLOCK/WAIT reasons. Never show a probability, analyst "upside" or predictive score
- Icons (lucide-react): Radar (Scout), LineChart (Technician), Scale (Fundamentalist), Newspaper (Newsdesk), TrendingUp (Bull), TrendingDown (Bear), Gavel (Judge), Send (Messenger)
- Bull/Bear text comes from templates; optional AI rewording is labelled "AI-assisted wording" and never changes a check

## Market Pulse (Dashboard, per market)

- **Index cards:** Nifty 50 and other configured indices for India, SPY/QQQ-style proxies for the US. Value, change, % change, source chip and freshness badge. US cards say "delayed" unless a verified real-time provider is configured
- **Breadth card:** % above 50 and 200-day average, new 52-week highs vs lows, advancers vs decliners, from our own universe data
- **Sector heatmap:** sector 1D / 1W / 1M return and average relative strength, from our own data (not third-party widgets). Tiles carry labels and signed numbers
- **Leaders by group:** 12-month trend sparkline per sector group (optional, Banks / Technology / Industry style tabs)
- Quote tables are grouped (by sector or by setup state) with sticky group headers

## Watchlists page (inside `/watchlist`)

- Named list tabs, count badges, "+" to create a list
- Filter chips: All, Near breakout, Valid setup, Waiting for confirmation, Blocked, No setup (with first failing check)
- Add stock: typeahead (market-scoped), "Add to watchlist" button on scanner rows and stock pages, optional one-line note
- Import dialog: paste or CSV, import report (resolved / ambiguous / unresolved / unsupported / duplicate), diff preview on re-import
- Label on imported lists: "Manually imported Zerodha watchlist (not synchronised)" with last import date
- Columns: symbol, company, price and day change with source and freshness, trend, RS, setup state, distance to trigger, news chip, fundamentals light, last scan time

## Stock page and chart workspace

- Layout: chart on the left (`lightweight-charts`), tabbed panel on the right: Research Desk, Decision trail, News & Events, Fundamentals, Replay Lab, Costs. Below lg the tabs stack under the chart
- Chart toolbar: timeframe (1D, 15m), indicator toggles (EMA 20/50, SMA 50/150/200, Volume, RSI, ATR) remembered per user, drawing tools (horizontal line, trendline, rectangle, Fibonacci retracement/extension), "Open in TradingView" link
- Overlays: trigger, entry-zone ceiling, stop and target lines, VCP base box, signal markers, trend-template drawer. Overlay colors come from tokens: emerald for trigger/target, rose for stop, blue/purple for MA lines
- Pane order: price, volume, RSI, ATR. Crosshair synced across panes
- Fundamentals tab: the traffic-light checklist plus a "More detail" link-out button (opens the company's page on a fundamentals site in a new tab)

## Search and navigation

- `Ctrl/Cmd + K` opens one palette with two groups: **Pages** and **Stocks** (market-scoped, shows price, sector, freshness). A "Search stocks" button sits at the top of the sidebar
- Optional **Recent stocks strip** under the top bar (up to 6, stored in the browser, closable). Off by default; no route changes
- Sidebar groups keep the 8 existing routes. Alerts and custom price alerts open in a **drawer** from the bell, not a new route

## Alerts drawer

- Bell in the top bar with unread counts **per market** (IN and US badges), so a US alert is visible while viewing India
- Tabs: Active, History. Filters by type, symbol, market. Acknowledge button per alert
- Custom price alerts: level, direction, symbol, labelled "Manual alert". Same freshness rules as system alerts
- Toast behaviour unchanged (SSE, `role="status"`)

## Motion

- Duration 150-200ms, ease-out, color / opacity / transform only
- Sidebar drawer: 200ms translate
- Live dot: ping only while connected
- `prefers-reduced-motion`: all animation and transition effectively off

## Accessibility

- Text contrast at least 4.5:1 on its surface
- Visible focus ring: 2px emerald, 2px offset, on every interactive element
- Touch targets at least 40px (pills 32px min on desktop)
- Dialog (palette) uses `role="dialog"`, `aria-modal`, focuses input on open
- Gain / loss never shown by color only

## Files

| File | Role |
|---|---|
| `tailwind.config.js` | palette remap, fonts, `shadow-card` |
| `src/index.css` | CSS vars, base, scrollbar, `.hatch`, reduced motion |
| `src/main.tsx` | font imports |
| `src/App.tsx` | shell: sidebar + top bar + routes + toast + footer |
| `src/components/Sidebar.tsx` | grouped nav, drawer, status |
| `src/components/Topbar.tsx` | title, market pills, regime, refresh |
| `src/components/CommandPalette.tsx` | Ctrl K page switcher |
| `src/components/navItems.ts` | single source of nav items |
| `src/components/Navbar.tsx` | old navbar, now unused, kept |
| `src/components/StatusBadge.tsx` | state, news-coverage and traffic-light badges (single source of labels and styles) |
| `src/components/SourceChip.tsx` | provenance chip + freshness badge |
| `src/components/ResearchDesk.tsx` | ten deterministic role cards, stage stepper, role chips |
| `src/components/FundamentalsPanel.tsx` | traffic-light checklist and link-out |
| `src/components/MarketPulse.tsx` | index cards, breadth, sector heatmap |
| `src/components/AlertsDrawer.tsx` | bell drawer, history, custom alerts |
| `src/components/StockSearch.tsx` | stock group inside the command palette |

## Next (not done)

- Dashboard: remove duplicate regime banner (now in top bar), add summary strip (setups count, universe, passed filters, session date) and the funnel strip
- Watchlist: sticky header, state filter chips, group by setup, import/add UI
- Positions / Journal: stat cards row on top, same tables below
- Backtests / News: tab bar inside page instead of long scroll; Strategy Lab comparison table
- Stock page: Research Desk and Fundamentals tabs
- Market Pulse cards and heatmap built from our own data

## Do not

- Do not mix icon libraries
- Do not use emoji as icons
- Do not add purple gradients, glass blur on every panel, or looping animations
- Do not hardcode hex in components. Use tokens
- Do not remove or rename any existing feature while restyling
- Do not use third-party widgets as data sources for decisions
- Do not show analyst targets, probabilities or predictive scores in the Research Desk
