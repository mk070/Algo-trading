# DESIGN.md — Swing Intel Institutional Terminal Design System

> **Design References:** OpenStock Institutional Terminal (`media_1793638532510_bdff647d.jpg` & `media_1793638536835_63a4946c.jpg`) + Swing Intel Live Watchlist (`media_1793624821332_7bf4e74f.png`).  
> **Aesthetic Profile:** Dark tech, institutional data-density, high-contrast typography, calm financial terminal.  
> **Dials:** `DESIGN_VARIANCE: 4` | `MOTION_INTENSITY: 3` | `VISUAL_DENSITY: 8`  
> **Anti-AI-Slop Invariant:** Zero purple gradients, zero glassmorphism blur traps, zero emoji navigation icons, 100% tabular figures, 100% manual-only broker execution.

---

## 1. Audit & Gap Reconciliation: All Discussed Features vs. OpenStock UI

Every capability discussed across the project has been audited and mapped into the OpenStock terminal shell:

| Domain / Feature | Project Implementation State | Addressed in Design? | Resolution in Final DESIGN.md |
| :--- | :--- | :--- | :--- |
| **8 Preserved Routes** | `/`, `/watchlist`, `/positions`, `/journal`, `/backtests`, `/news`, `/settings`, `/system` | ✅ Yes | All 8 routes preserved; organized into 4 semantic groups in `Sidebar.tsx` + `navItems.ts`. |
| **Market Switcher** | India (`NSE`) & United States (`NASDAQ`/`NYSE`) | ✅ Yes | Modeled as OpenStock inline pill selector (`• United States`, `• India`) with session subtitle. |
| **Market Regime** | Bullish / Caution / Weak + Index vs SMA50 & SMA200 | ✅ Yes | Dedicated Topbar chip with live tabular mono values and expandable trend metrics. |
| **OpenStock Workspace Tabs** | Browser-style tabs (`[Overview] [★ Watchlist] [TMPV ×] [+]`) | ✅ Yes | **Section 5.B & 6.B**: Topbar multi-tab bar enabling instant switching without reloads. |
| **Watchlist & Opportunity Radar Table** | Live quotes (`TMPV NSE ₹644.00`), setups, guardrails, feed lanes | ✅ Yes | **Section 7**: Direct 1:1 institutional refinement of `media_1793624821332_7bf4e74f.png`. |
| **Manual Watchlist Import** | Paste / CSV, Angel One instrument master validation, diff preview | ✅ Yes | **Section 7.C**: Import modal, 5-tier badge classification, soft-delete, stale import banner. |
| **TradingView Terminal (`lightweight-charts@5.2.1`)** | Multi-timeframe (1D/15m), 5 MAs, RSI & ATR panes, VCP overlays, drawings | ✅ Yes | **Section 8**: Full dark-canvas styling (`#090d16`), strategy overlays, manual drawing tools. |
| **OpenStock Market Pulse** | 4 Index cards (SENSEX, RELIANCE, TCS, HDFCBANK / SPY, QQQ, DIA, IWM) | ✅ Yes | **Section 6.C**: High-impact cards with JetBrains Mono prices, delta badges, and provider tags. |
| **OpenStock Sector Leaders & Sparkline** | 12-month sector trend line/area chart + stock list | ✅ Yes | **Section 6.D**: Mounted on Overview/Dashboard page with sector tabs (Banks, Tech, Industry). |
| **OpenStock Grouped Quotes Table** | India/US leaders grouped by sector (`BANKS`, `TECHNOLOGY`) | ✅ Yes | **Section 6.E**: Modeled directly after `media_1793638536835_63a4946c.jpg`. |
| **Market Heatmap** | Treemap sized by market cap, colored by today's % change | ✅ Yes | **Section 6.F**: S&P 500 / Nifty 50 treemap widget on Dashboard. |
| **Live Data Freshness Badges** | Two-lane quote contract (`LIVE`, `DELAYED`, `STALE`, `DISCONNECTED`) | ✅ Yes | **Section 3.D**: High-contrast indicator pills with pulsing ping animation on live feeds. |
| **Zerodha Portfolio Split Valuation** | Broker snapshot (₹1,000 capital) vs Angel One live calculated LTP | ✅ Yes | **Section 9**: Side-by-side valuation cards with audit provenance tags. |
| **Financial News & Sentiment Engine** | Multi-feed RSS (Yahoo Finance, Finnhub, Google), score (-1 to +1) | ✅ Yes | **Section 10**: Clean chronological feed with sentiment badges and symbol tags on `/news`. |
| **Sidebar User Profile Tile** | User profile box at bottom left (`[Z] SBV367 - Connected`) | ✅ Yes | **Section 5.A**: Modeled after OpenStock profile tile (`media_1793638532510_bdff647d.jpg`). |
| **Global Quick Search (`Ctrl K`)** | Instant universe symbol search, page navigation, direct actions | ✅ Yes | **Section 5.A & 5.C**: High-visibility emerald button at top of sidebar + shortcut modal. |
| **Zero Broker Execution Guardrail** | 100% manual order placement strictly preserved | ✅ Invariant | Hard rule: no order execution endpoints, copyable broker tickets only. |

---

## 2. Hard Invariants & Non-Negotiables

1. **Zero Feature or Route Removal:** Every existing page, route, API call, calculation, and strategy rule remains active.
2. **Zero Automated Broker Execution:** All orders are manually placed by the trader at their broker. The UI only provides decision-support copyable order tickets.
3. **Zero Class Breakage via Central Remapping:** Existing JSX across all 8 pages uses `slate-*` and `indigo-*` classes. The dark OpenStock aesthetic is achieved by remapping these color scales centrally in `tailwind.config.js`.
4. **Anti-AI-Slop Principles:**
   - **No emoji used as interface icons:** All icons must come from `lucide-react` (e.g., `<LineChart />` replaces `📈`, `<Bell />` replaces `🚨`).
   - **No purple / rainbow gradient buttons:** Only solid, purposeful tokens (OpenStock emerald `#10b981` for primary CTA, warm slate for surfaces).
   - **No decorative glassmorphism blurs on core data tables:** Backgrounds are solid near-black `#181b1a` with crisp `#2e3331` structural borders.
   - **No ungrounded marketing fluff:** Clear, concise institutional copy with real market provenance.

---

## 3. Color Token Architecture

Modeled directly after the **OpenStock terminal**: deep, warm near-black canvas (`#0d0f0e`), solid surface panels (`#181b1a`), high-contrast slate text, and crisp emerald accents (`#10b981`).

### A. Neutrals (`slate` scale remapped to OpenStock Warm Near-Black)

| Tailwind Token | Hex Value | Usage in Application |
| :--- | :--- | :--- |
| `slate-950` | `#0d0f0e` | Main application background, static sidebar, sticky topbar canvas |
| `slate-900` | `#181b1a` | Card surfaces, terminal panels, table container backgrounds, modal bodies |
| `slate-800` | `#222625` | Active nav items, table row hover states, table header fills, input backgrounds |
| `slate-700` | `#2e3331` | High-contrast structural borders, dividers, subtle button outlines |
| `slate-600` | `#444a48` | Muted borders, secondary button borders, scrollbar thumbs |
| `slate-500` | `#656c69` | Group header labels, muted caption text, inactive icon fills |
| `slate-400` | `#8a918e` | Secondary body text, table column headers, helper notes |
| `slate-300` | `#aeb4b1` | Primary body text on cards, active parameter values, form labels |
| `slate-100` | `#e8eae9` | Primary headings, prominent prices, high-emphasis metrics |

### B. Primary Accent (`indigo` scale remapped to OpenStock Emerald)

| Tailwind Token | Hex Value | Usage in Application |
| :--- | :--- | :--- |
| `indigo-500` | `#10b981` | Primary CTA buttons, "Search stocks" button, active tab indicator, brand mark |
| `indigo-400` | `#34d399` | Active icon highlights, focus rings, keyboard shortcut pills (`⌘K`) |
| `indigo-300` | `#6ee7b7` | High-emphasis accent text on dark containers |
| `indigo-950` | `#042a1f` | Accent tint fills, active pill selections, selected table rows |

### C. Semantic State Colors

Never communicate state by color alone; always accompany with a sign (`+`/`-`), label, or icon:

- **Bullish / Profit / Confirmed:** Emerald (`#10b981` / `#34d399`) — buy triggers, positive % changes, confirmed setups.
- **Caution / Approaching / Stale:** Amber (`#f59e0b` / `#fbbf24`) — setups near breakout (<2.5% to trigger), delayed data feeds.
- **Weak / Loss / Invalidation:** Rose (`#f43f5e` / `#fb7185`) — stop loss levels, negative returns, rejected guardrails.
- **Secondary Data Lines:** Blue (`#3b82f6`) & Purple (`#a855f7`) — SMA50, SMA200, relative strength rankings.
- **Target / Reference:** Cyan (`#06b6d4`) — 2R target levels, ATR line.

### D. Data Feed Reliability Badges

| Feed Status | CSS Classes | Behavior & Visual Indicator |
| :--- | :--- | :--- |
| **`LIVE`** | `bg-emerald-950/80 text-emerald-400 border border-emerald-800` | Green pip with active CSS ping animation. Real-time tick latency &lt;20s. |
| **`DELAYED`** | `bg-amber-950/80 text-amber-400 border border-amber-800` | Solid amber pip. Quote delayed (e.g. 15m YFinance / BSE-delayed). |
| **`STALE`** | `bg-rose-950/80 text-rose-400 border border-rose-800` | Solid red pip + elapsed time. Automated trigger evaluation is suspended. |
| **`DISCONNECTED`** | `bg-slate-800 text-slate-400 border border-slate-700` | Solid gray pip + Reconnect button. Provider session is inactive. |

---

## 4. Typography & Numeric Precision Standards

- **Primary UI Sans:** `@fontsource-variable/plus-jakarta-sans` (Weights: 400, 500, 600, 700, 800) for headers, labels, and prose.
- **Financial & Numeric Mono:** `@fontsource-variable/jetbrains-mono` (Weights: 400, 500, 600, 700) for all prices, percentages, triggers, volumes, and table cells.
- **Tabular Figures Requirement:** All numbers in tables, cards, and charts must enforce tabular numerals so decimal points align vertically:
  ```css
  font-feature-settings: "tnum" 1, "cv01" 1;
  font-variant-numeric: tabular-nums;
  ```
- **Type Scale:**
  - Page Title: `text-lg font-extrabold tracking-tight text-slate-100` (18px)
  - Card / Panel Header: `text-sm font-bold text-slate-100` (14px)
  - Group Category Label: `text-[10px] font-bold uppercase tracking-wider text-slate-500`
  - Body Text: `text-xs leading-relaxed text-slate-300` (12px)
  - Numeric Displays: `text-sm font-mono font-bold text-slate-100`

---

## 5. Navigation & Terminal Shell Architecture

```
+-------------------------------------------------------------------------------------------------------------+
| SIDEBAR (256px Fixed)          | TOPBAR (Sticky h-14, border-b border-slate-800 bg-slate-950/95)             |
|                                +-----------------------------------------------------------------------------+
| [S] SWING INTEL                | Workspace Tabs: [Overview] [★ Watchlist (14)] [TMPV ×] [+]                 |
| Institutional Terminal         | Market Switcher: [• United States] [• India]                                |
|                                | Market Regime: [• IN BULLISH] Nifty: 24,180 | SMA50: 23,850                 |
| [ Search stocks        ⌘K ]    | Actions: [Refresh ⟳] [SSE Alert Bell]                                       |
|                                +-----------------------------------------------------------------------------+
| MARKETS                        | MAIN CONTENT CANVAS (max-w-[1600px] mx-auto, p-4 lg:p-6)                     |
|  • Dashboard (/)               |                                                                             |
|  • Watchlist & Live (/watchlist)| - OpenStock Market Pulse: 4 Index Cards (SENSEX, RELIANCE, TCS, HDFCBANK)   |
|                                | - Sector Leaders 12-Month Sparkline + Grouped Quotes Table                  |
| PORTFOLIO                      | - Watchlist Opportunity Monitoring Radar (TMPV NSE, ₹644.00, etc.)          |
|  • Positions & Value (/positions)|                                                                            |
|  • Journal & Stats (/journal)  | - TradingView Interactive Chart Terminal (when active)                      |
|                                |                                                                             |
| RESEARCH                       +-----------------------------------------------------------------------------+
|  • Backtesting Lab (/backtests)| PERSISTENT COMPLIANCE FOOTER (Border-t border-slate-900 bg-slate-950)       |
|  • News & Sentiment (/news)    | "Signals are decision-support only. Zero automated broker orders. All       |
|                                |  orders are placed manually by the account owner."                          |
| SYSTEM                         +-----------------------------------------------------------------------------+
|  • Settings (/settings)        |
|  • System Health (/system)     |
|                                |
| WATCHING (Pinned symbols)      |
|  • RELIANCE   ₹1,163.55  -0.44%|
|  • TMPV         ₹644.00  +0.00%|
|                                |
| USER PROFILE TILE              |
|  [Z] madhan (SBV367)           |
|  • Angel One: LIVE             |
+--------------------------------+
```

### A. Fixed Left Sidebar ([`Sidebar.tsx`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/components/Sidebar.tsx))
- **Brand Header:** Deep emerald square mark with white stylized `S` + "SWING INTEL" + "Institutional Terminal".
- **Top Search CTA:** Full-width high-contrast emerald button directly under brand:
  ```html
  <button class="w-full bg-indigo-500 hover:bg-indigo-400 text-slate-950 font-bold py-2 px-3 rounded-lg text-xs flex items-center justify-between shadow-sm transition">
    <span class="flex items-center gap-2"><Search class="w-3.5 h-3.5" /> Search stocks</span>
    <kbd class="text-[10px] bg-indigo-600/30 px-1.5 py-0.5 rounded text-slate-900 font-mono">⌘K</kbd>
  </button>
  ```
- **4 Grouped Navigation Sections:** Defined in [`navItems.ts`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/components/navItems.ts):
  1. **Markets:** Overview (`/`), Watchlists & Live Monitoring (`/watchlist`).
  2. **Portfolio:** Positions & Valuation (`/positions`), Trade Journal (`/journal`).
  3. **Research:** Backtesting Lab (`/backtests`), News & Sentiment (`/news`).
  4. **System:** Settings & Accounts (`/settings`), System Health & Latency (`/system`).
- **Pinned Watchlist (`WATCHING`):** Quick-reference list of starred symbols with live prices and % changes. Clicking opens the stock in a workspace tab.
- **Bottom Profile & Broker Tile:**
  - Modeled directly after the user profile box in OpenStock (`media_1793638532510_bdff647d.jpg`).
  - Displays user identity: `[Z] madhan (SBV367)` with green status pip ("Zerodha Connected").
  - Displays live quote provider state: `• Angel One SmartAPI: LIVE`.

### B. Sticky Topbar ([`Topbar.tsx`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/components/Topbar.tsx))
- **Browser-Style Workspace Tabs:**
  - Tab 1: `Overview` (Dashboard)
  - Tab 2: `★ Watchlist (14)` (Watchlist Page)
  - Tab 3: Active Chart tab (e.g., `TMPV ×`)
  - `+` button to open Quick Search and add new tabs.
- **Inline Market Selector Pills:**
  - Modeled after OpenStock: `[• United States] [• India]`.
  - Active pill: `bg-indigo-950 text-indigo-300 border border-indigo-700/80 font-bold`.
- **Regime Badge & Tabular Breadth:**
  - Left badge: `IN BULLISH` (`bg-emerald-950 text-emerald-400 border border-emerald-800`).
  - Right tabular metrics: `Index: 24,180 | SMA50: 23,850 | SMA200: 22,900` in JetBrains Mono.
- **Global Actions:** Manual Scan Refresh button (with rotating animation during fetch) + SSE Alert notification bell.

---

## 6. OpenStock Dashboard Layout (Overview / `/`)

Modeled directly after OpenStock screenshots `media_1793638532510_bdff647d.jpg` (US) and `media_1793638536835_63a4946c.jpg` (India).

### A. Subtitle Bar
- Dynamic market status: `India · open now · live data` or `India · closed now · end of day data`.
- Data provenance tag: `Delayed · refreshed hourly` or `Live quotes via Angel One SmartAPI`.

### B. OpenStock Pulse Index Cards ([`MarketPulseWidget.tsx`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/components/MarketPulseWidget.tsx))
4 high-impact market pulse cards:
- **India (`IN`):**
  1. `SENSEX`: `₹75,692.78` | `↗ +1.66%  +1,233.25 vs prev close`
  2. `RELIANCE`: `₹1,163.55` | `↘ -0.44%  -5.20 vs prev close`
  3. `TCS`: `₹2,496.00` | `↗ +0.62%  +15.50 vs prev close`
  4. `HDFCBANK`: `₹692.30` | `↗ +1.07%  +7.30 vs prev close`
- **United States (`US`):**
  1. `S&P 500 (SPY)`: `$760.11` | `↗ +0.58%  +1.39 vs prev close`
  2. `Nasdaq 100 (QQQ)`: `$693.82` | `↗ +0.48%  +3.33 vs prev close`
  3. `Dow 30 (DIA)`: `$522.34` | `↗ +1.01%  +5.21 vs prev close`
  4. `Russell 2000 (IWM)`: `$282.21` | `↗ +1.03%  +2.88 vs prev close`
- **Styling:** `bg-slate-900 border border-slate-800 rounded-xl p-4`. Ticker symbols in bold white, prices in `font-mono text-xl font-bold`, delta pill in emerald (positive) or rose (negative).

### C. Leaders 12-Month Sparkline Chart
- Category selector tabs:
  - India: `[Banks] [Technology] [Industry]`
  - US: `[Financial] [Technology] [Consumer]`
- Smooth SVG/Canvas area sparkline showing 12-month performance in emerald/cyan gradient fill.
- Direct ticker listing with current prices and day changes.

### D. Grouped Quotes Table
- Modeled directly after OpenStock India screenshot (`media_1793638536835_63a4946c.jpg`):
  - Section header: `BANKS` (HDFC Bank, ICICI Bank, State Bank of India, Kotak Mahindra, Axis Bank).
  - Section header: `TECHNOLOGY` (TCS, Infosys, Wipro, HCLTech, Tech Mahindra).
- Columns (all tabular numerics): `Name`, `Value`, `Change`, `Chg%`, `Open`, `High`, `Low`, `Prev Close`.

### E. Market Sector Heatmap
- Treemap sized by market capitalization, colored by today's price change (deep green for >+3%, dark red for <-3%).
- Interactive: clicking any ticker in the heatmap opens its chart or watchlist row.

---

## 7. Watchlist & Opportunity Monitoring UI ([`WatchlistPage.tsx`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/pages/WatchlistPage.tsx))

This section refines the exact table shown in the user's uploaded screenshot (`media_1793624821332_7bf4e74f.png`), bringing it into alignment with the OpenStock terminal design system.

### A. Table Column Architecture & Typography

| Column | Typography & Alignment | Content Specification | Visual Example |
| :--- | :--- | :--- | :--- |
| **SYMBOL** | Sans font-bold, Left-aligned | Ticker symbol in bright white + Exchange badge in muted dark pill | `TMPV` `<span class="bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded text-[10px]">NSE</span>` |
| **LIVE PRICE** | JetBrains Mono font-bold, Left-aligned | Current quote with currency symbol (`₹` / `$`). Tabular figures. | `₹644.00` |
| **DAY %** | JetBrains Mono font-bold, Left-aligned | Colored pill: `+0.00%` (slate/emerald), `+2.4%` (emerald), `-1.8%` (rose) | `<span class="px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-400 font-mono text-xs">+0.00%</span>` |
| **OPPORTUNITY STATE** | Sans font-bold text-[10px], Left-aligned | Setup status pill: `VALID SETUP`, `APPROACHING`, `WAITING CONFIRMATION`, `NO SETUP` | `<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">NO SETUP</span>` |
| **TRIGGER PRICE** | JetBrains Mono font-semibold text-emerald-400 | Breakout pivot level, or `—` if no setup is formed | `—` or `₹652.10` |
| **DIST TO TRIGGER** | JetBrains Mono text-xs | Distance percentage. If &le;2.5%, amber highlight: `1.2% away`. Else `—`. | `—` or `1.2% away` |
| **STOP LOSS** | JetBrains Mono font-semibold text-rose-400 | Calculated risk level, or `—` if no setup | `—` or `₹625.00` |
| **GUARDRAIL / FAILING CHECK** | Sans text-[11px] text-slate-400 truncate | Reason why setup is blocked or valid. Tooltip shows full text. | `Passes baseline filters` or `Price < SMA50` |
| **FEED LANE** | Sans font-bold text-[9px] uppercase | Quote lane badge: `LIVE` (green), `DELAYED` (amber), `STALE` (rose) | `<span class="bg-amber-950/80 text-amber-400 border border-amber-800 text-[9px] px-1.5 py-0.5 rounded">DELAYED</span>` |
| **ACTIONS** | Right-aligned action buttons | Lucide `<LineChart />` button ("Chart") to open chart tab/modal + `<Trash2 />` icon | `[📈 Chart]` (replaced with Lucide SVG) + `[Trash]` |

### B. 7 Opportunity Filter Tabs
Filter bar above table:
`[All]` | `[Valid Setups]` | `[Near Breakout (<2.5%)]` | `[Waiting 15m Confirmation]` | `[Blocked by Regime/Risk]` | `[Already Held]` | `[No Setup]`

### C. Manual Import & Stale Provenance Banner
- **Provenance Notice:**
  ```html
  <div class="bg-slate-900 border border-slate-800 rounded-lg p-3 text-xs flex items-center justify-between text-slate-300">
    <span class="flex items-center gap-2">
      <Clock class="w-4 h-4 text-slate-400" />
      Manually imported Zerodha watchlist (not synchronised) &mdash; Last imported: <strong>2026-11-02</strong>
    </span>
    <button class="text-indigo-400 hover:text-indigo-300 text-xs font-semibold">Re-import / Sync CSV</button>
  </div>
  ```
- If watchlist age > 7 days: Amber warning banner: `"Watchlist was imported 8 days ago and may be out of date. Re-import or verify symbols."`
- **Validation Report Table (Modal):**
  - Displays classifications: `RESOLVED` (emerald), `AMBIGUOUS` (amber), `UNRESOLVED` (rose), `UNSUPPORTED` (gray), `DUPLICATE` (slate).
  - Diff confirmation preview: `Added (+N)`, `Removed (-N)`, `Unchanged (=N)` with `Merge` or `Replace` mode.

---

## 8. TradingView Interactive Terminal Integration ([`CandleChart.tsx`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/components/CandleChart.tsx))

Institutional styling specifications for `lightweight-charts@5.2.1`:

1. **Terminal Canvas Settings:**
   - Canvas background: Solid `#090d16` (deep obsidian).
   - Gridlines: Sparse dotted `#172033` (vert & horz).
   - Crosshair: Dashed `#475569` with hover value tracking.
2. **Candles & Volume Overlays:**
   - Bullish candle: Emerald `#10b981`.
   - Bearish candle: Rose `#f43f5e`.
   - Volume: Pane 0 transparent alpha bars (`#10b98144` / `#f43f5e44`).
3. **5 Strategy Moving Average Lines:**
   - **EMA 20:** Gold/Amber `#f59e0b` (width: 1)
   - **EMA 50:** Orange `#fb923c` (width: 1)
   - **SMA 50:** Blue `#3b82f6` (width: 1)
   - **SMA 150:** Teal `#14b8a6` (width: 1)
   - **SMA 200:** Purple `#a855f7` (width: 2)
4. **Separate Dedicated Indicator Panes:**
   - **Pane 1 (RSI 14):** Purple `#c084fc` line with dashed overbought (70) and oversold (30) levels.
   - **Pane 2 (ATR 14):** Cyan `#06b6d4` line showing average true range volatility.
5. **Strategy Overlays:**
   - **VCP Base Consolidation Box:** Bounding rectangle (`fill: #6366f114`, dashed stroke `#6366f1`) marking duration, depth, and pivot.
   - **Buy Trigger Line:** Dashed emerald line `#10b981` labeled `BUY TRIGGER: X.XX`.
   - **Entry Ceiling:** Dotted teal line `#34d399` labeled `ENTRY CEILING (MAX CHASE)`.
   - **Stop Loss Line:** Dashed rose line `#f43f5e` labeled `STOP LOSS: X.XX`.
   - **2R Target Line:** Dashed cyan line `#06b6d4` labeled `TARGET 1 (2R): X.XX`.
   - **Confirmation Markers:** Arrow markers below trigger bars showing `TRIGGERED_CONFIRMED`.
   - **Minervini Trend Template Drawer:** Interactive chip showing `7/8 Pass` that expands to show the 8-point checklist.
6. **Manual Drawing Tools:** Toolbar with Select, Horizontal Line, Trendline, Rectangle, and Clear All buttons with `localStorage` persistence.

---

## 9. Portfolio & Execution Integrity UI ([`PositionsPage.tsx`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/pages/PositionsPage.tsx))

- **Split Valuation Header:**
  - **Broker Reported:** Synced directly from Zerodha Kite (`₹1,000.00` capital, cash balance, account holdings).
  - **Calculated Value:** Live market LTP calculated via Angel One SmartAPI feeds.
- **Copyable Execution Ticket:**
  ```
  +-----------------------------------------------------------------------------------+
  | BUY TMPV @ LIMIT ₹652.10 | STOP: ₹625.00 | QTY: 1 | RISK: ₹27.10 (2.7% capital)  |
  | [ Copy for Zerodha / Broker ]                                                     |
  +-----------------------------------------------------------------------------------+
  ```
  Strictly zero automated order submission buttons.

---

## 10. News & Sentiment Engine UI ([`NewsPage.tsx`](file:///d:/web%20development/saas-projects/Algo-trading/frontend/src/pages/NewsPage.tsx))

- Multi-feed integration: Yahoo Finance RSS, Finnhub, Google News RSS.
- Sentiment score badges: `BULLISH (+0.65)` (emerald), `NEUTRAL (0.00)` (slate), `BEARISH (-0.45)` (rose).
- Ticker tag chips: Filter articles by watched stocks (`TMPV`, `RELIANCE`, `TCS`).

---

## 11. Implementation File Manifest

| Target File | Architectural Role | Required Implementation Action |
| :--- | :--- | :--- |
| `frontend/tailwind.config.js` | Palette Remap | Remap `slate` to warm near-black `#0d0f0e` and `indigo` to emerald `#10b981`. |
| `frontend/src/index.css` | Base Tokens & Fonts | Import Plus Jakarta Sans & JetBrains Mono; set `font-variant-numeric: tabular-nums`. |
| `frontend/src/components/navItems.ts` | Nav Source of Truth | Define 4 groups (`Markets`, `Portfolio`, `Research`, `System`) with Lucide icons. |
| `frontend/src/components/Sidebar.tsx` | Fixed Left Navigation | OpenStock-style layout: Search CTA, grouped links, pinned list, user profile tile. |
| `frontend/src/components/Topbar.tsx` | Top Navigation & Tabs | Workspace tab strip, inline market pills, regime chip, manual refresh. |
| `frontend/src/components/QuickSearchModal.tsx` | Global Palette (`Ctrl K`) | Universal stock and page search modal with keyboard navigation. |
| `frontend/src/components/MarketPulseWidget.tsx` | Breadth & Sector Strip | 4 Pulse cards, sector leader sparkline, and grouped quotes table. |
| `frontend/src/components/CandleChart.tsx` | TradingView Terminal | Lightweight Charts v5 with multi-panes, strategy overlays, drawing tools. |
| `frontend/src/App.tsx` | App Shell | Assemble fixed Sidebar + Topbar + Main Layout + SSE Alert Toast + Footer. |

---

## 12. Quality & Anti-Slop Checklist

- [x] All 8 existing routes preserved and easily navigable via Sidebar, Topbar tabs, and `Ctrl+K`.
- [x] Zero automated broker orders: strictly manual-only execution tickets.
- [x] Exact OpenStock visual aesthetic applied: warm charcoal surfaces (`#0d0f0e`, `#181b1a`), crisp emerald accents (`#10b981`).
- [x] All financial numbers formatted in JetBrains Mono with tabular numerics.
- [x] Watchlist table (`media_1793624821332_7bf4e74f.png`) refined with high-contrast status pills and Lucide SVG icons (zero emojis).
- [x] OpenStock Market Pulse cards (SENSEX/Nifty & S&P 500/Nasdaq) and grouped sector quotes table fully integrated.
- [x] TradingView Lightweight Chart terminal mounts with 5 moving averages, RSI/ATR panes, VCP overlays, and drawing tools.
- [x] Data reliability badges (`LIVE` green pulse, `DELAYED`, `STALE`, `DISCONNECTED`) explicitly specified.
- [x] User profile tile displays broker account status (`[Z] SBV367 - Connected`) and Angel One feed status.
