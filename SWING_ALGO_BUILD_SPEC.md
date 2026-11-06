# SWING SIGNAL PLATFORM: BUILD SPEC FOR AN AI CODING AGENT

> **Implementation addendum (2026-11-05):** `DESIGN.md` is the active frontend design reference. `DESIGN_old.md` is retained for historical comparison only. The Research Desk flow is Scout → Technician → Fundamentalist → Newsdesk → Planner → Risk Manager → Bull / Bear → Judge → Messenger; these roles are deterministic views, not separate agents.

> Hand this whole file to the coding agent (Claude Code, Cursor, etc.) as the single source of truth.
> Stack: **Python 3.11+ (FastAPI)** backend, **React + TypeScript (Vite)** frontend, **Neon PostgreSQL** (exclusive database platform), free data sources only, free background hosting.
> A working prototype of the signal logic exists in `swing_signals.py` (provided alongside). Port and extend it; do not discard its logic.
> **v2:** integrates a second research pass (Minervini-style trend template, VCP/tight-base breakouts, signal states, 15-minute confirmation, correlation limits, US data providers). See Section 21 for what changed and why.

---

## 0. NON-NEGOTIABLE RULES FOR THE AGENT

1. **No order placement.** The app only produces signals, alerts and tracking. The owner places every order manually. Never add code that sends orders to any broker. Even though the Zerodha Kite Personal API technically supports order endpoints, wrap it in a **read-only client** (Section 6.4) and add a CI test that fails if `place_order`, `modify_order`, `cancel_order`, `convert_position` or any GTT-mutating call appears anywhere in the repo.
2. **No look-ahead bias, ever.** A signal computed on the close of day *t* may only use data up to and including day *t*. Add an automated test proving this (Section 17).
3. **No secrets in code or git.** All keys, PINs, TOTP secrets and tokens come from environment variables / `.env` (git-ignored). Provide `.env.example`.
4. **Never promise profit in the UI.** Show a persistent disclaimer: "Signals are rules-based, not advice. Past/backtested performance does not guarantee future results."
5. **Every signal must carry human-readable reasons** and exact numbers (trigger, stop, target, quantity, risk in currency).
6. **Fail loudly on bad data.** Stale, missing or inconsistent data must produce a visible "DATA WARNING" and suppress signals for the affected symbol rather than silently continuing.
7. **Be polite to free data sources:** cache aggressively, rate-limit, retry with backoff, and degrade gracefully to a fallback provider.
8. **Configuration over constants.** Every strategy/risk/cost parameter lives in `config/strategy.yaml` (Section 16) and is editable from the Settings page.
9. Build in the milestone order of Section 18 (with the core-integration override at the top of that section). After each milestone, run the tests and report what passes before moving on.
10. **Provenance everywhere.** Every number shown in the UI carries a source tag (Zerodha, Angel One, Alpaca, Calculated, Imported) and an "as of" timestamp. Broker-reported values and our own calculations are never blended silently (Section 6.6).
11. **Unknown is not clear.** Missing, failed or stale news/earnings/price data must surface as `UNKNOWN` or `STALE`, never be treated as "no problem" (Sections 5.4 and 6.3).

---

## 1. OWNER PROFILE AND DECISIONS ALREADY MADE

| Item | Decision |
|---|---|
| Markets | Indian stocks (NSE) and US stocks |
| Style | End-of-day positional **swing trading**, long-only, holding days to a few weeks |
| Execution | **Manual** (owner places orders) |
| India execution broker | **Zerodha** (orders placed by hand in Kite) |
| India account data | **Zerodha Kite Connect "Personal" (free), read-only**: holdings, positions, funds, trades. It has no historical or live-quote APIs |
| India market data | **Angel One SmartAPI** (free): historical candles, live quotes, WebSocket; yfinance as fallback |
| US broker / data | Still to confirm (Section 1 open items) |
| Capital | India: roughly 15,000-20,000 (INR). US: roughly 15,000-20,000 (**currency to confirm; see open items**) |
| Risk appetite | **Medium**: large caps plus liquid mid caps; no small caps / penny stocks |
| Monitoring cadence | Evening review plus a couple of checks during the day (mobile-friendly UI required) |
| Goal | Surface the right stocks, exact buy trigger / stop / target / size, real-time buy and sell alerts with reasons, and prove the edge with a rigorous backtest and paper trading before real money |

### Open items the agent must surface in the UI Settings page (do not guess silently)
- **US capital currency** (USD vs INR-equivalent). Default config assumes USD 17,500; owner must confirm.
- **India broker** (affects cost model; see Section 4.3) and **US broker** (fees, fractional shares, FX/remittance costs).
- Whether the owner wants after-tax P&L estimates (tax rules change; keep rates configurable, never hard-coded).
- **US real-time data provider** (default recommendation: Alpaca free plan, pending the owner's confirmation and eligibility check; yfinance alone does not meet the real-time requirement).
- **Monthly budget** for US market data and news (default 0; Section 16 `budget`). Paid feeds stay off until the owner sets a budget.
- Whether to import Zerodha Console CSV reports (tradebook, P&L, charges) from day one (default: supported and optional).
- **Risk profile:** conservative baseline (0.5% per trade, 2% open risk) for both markets. India "small-account mode" with higher risk is an explicit opt-in (Section 4.3), not a default.

---

## 2. PRODUCT OVERVIEW AND WORKFLOW

```
EVENING (after each market closes)
  data refresh -> regime check -> universe filter -> screener -> setups
  -> news/earnings filter -> risk sizing + cost gate -> ranked "Trade Plan" for next session
  -> Telegram summary + dashboard

DURING MARKET HOURS (watchlist + open positions only)
  poll prices -> trigger hit? -> BUY alert (price, qty, stop, target, reasons)
                 stop/target/trail hit? -> SELL alert
                 setup invalidated / chasing too far? -> CANCEL / SKIP alert
                 new negative announcement on a holding? -> WARNING alert

OWNER ACTIONS (in UI)
  "I took this trade" (enter actual fill, qty) -> becomes an Open Position
  "I exited" (enter actual exit) -> Journal entry with R-multiple and costs
```

Modes: **Live signals**, **Paper** (auto-simulates fills for every signal so the strategy is tracked without the owner trading), **Backtest**.

---

## 3. STRATEGY SPECIFICATION

Philosophy: trade only with the trend, in the strongest stocks, when the market is healthy, enter at a precisely defined point, risk a small fixed amount, cut losers fast and let winners run. The system does not predict; it filters, waits for a defined entry, and calculates risk before entry.

There are **two candidate entry setups** that share one filter stack and one exit system: **Setup V (tight-base / VCP-style breakout)** and **Setup P (pullback to the 20/50 EMA)**. Research on retail swing traders repeatedly mentions both ideas (consolidation breakouts with small stops; low-volume pullbacks to the 20/50 EMA after a strong move), but those accounts are self-reported anecdotes, not proof. **Launch configuration: Setup V is the primary and the only setup that raises live alerts. Setup P is implemented but experimental: disabled for live alerts and run in shadow mode** (it logs would-be signals and paper results so evidence accumulates without alerting). Enable Setup P for live alerts only if it shows an out-of-sample edge. Both setups are backtested independently and combined (Section 12.3). Starting with one reliable strategy reduces overfitting and the number of things that can go wrong. All defaults are starting hypotheses.

### 3.1 Market regime filter (per market)
- Index: India `^NSEI` (Nifty 50), US `^GSPC` (S&P 500). Provider symbols are configurable.
- **Bullish** if `close > SMA200` and `close > SMA50`. Otherwise **Weak**.
- Weak regime: no new entries (setting `regime.block_new_entries=true`). Open positions still managed.
- Optional "Caution" tier: index below SMA50 but above SMA200 allows only the highest-ranked setups at half size (`regime.caution_size_mult=0.5`).

### 3.2 Universe (medium risk)
- India: Nifty 100 + Nifty Midcap 150 constituents (about Nifty 250). Load constituent CSVs from NSE's index site into `data/universe/`, refresh monthly. Verify the current CSV URL at build time.
- US: S&P 500 + S&P MidCap 400 (free lists, e.g. via public tables). Store in `data/universe/`.
- **Exclude:** small caps, ETFs (v1), stocks listed under 1 year, stocks failing liquidity or volatility filters below.
- **Liquidity:** 20-day average traded value >= `min_value` (India default 10 crore INR; US default USD 20M). Price floors: India >= INR 50, US >= USD 10.
- **Volatility cap (medium risk):** ATR(14)/price <= `max_atr_pct` (default 6%).
- **Affordability:** one share must cost <= `max_share_price_pct_of_capital` (default 25%) of that market's capital, or the stock is shown as "unaffordable" and excluded.
- Optional: exclude symbols on NSE surveillance lists (ASM/GSM) if obtainable free.

### 3.3 Stock selection: trend template + relative strength (Minervini-inspired)
Compute on daily bars: `SMA50/150/200`, `EMA20/50`, `RSI14` (Wilder), `ATR14` (Wilder), `avg_vol20`, `avg_vol50`, `high252`, `low252`, `ret21`, `ret63`, `ret126`.

**Trend template (all must pass; each rule toggleable in config):**
1. `close > SMA150` and `close > SMA200`
2. `SMA150 > SMA200`
3. `SMA200` rising: `SMA200[t] > SMA200[t-21]`
4. `SMA50 > SMA150` and `SMA50 > SMA200`
5. `close > SMA50` and `EMA20 > EMA50`
6. `close >= 1.30 * low252` (at least 30% above the 52-week low)
7. `close >= 0.75 * high252` (within 25% of the 52-week high; Setup V prefers within 15%)
8. **Relative strength:** `rs_rank >= 0.70`, where `rs_rank` = percentile of `0.5*ret63 + 0.5*ret126` within the market's filtered universe, AND the stock's `ret126` exceeds the market index's `ret126`.

**Overextension guard (do not buy stretched stocks):** reject if `close > 1.25 * SMA50` or `ret21 > extension_ret21_max` (default 30%). Do NOT copy the "top 1-month gainers over 30%" rule blindly; instead expose `ret21`/`ret63` as ranking features and flag "extended" so the backtest can show whether filtering them helps.

Candidates failing any rule are discarded. Each rule result is stored so the UI can show a pass/fail checklist per stock.

### 3.4 Setup P: PULLBACK TO 20/50 EMA IN UPTREND
All must hold on the signal day *t*:
- Within the last 5 bars, `low <= EMA20 * 1.01` (touched the 20-EMA zone).
- `min(RSI14 over last 5 bars) < 45`.
- Turning up: `RSI14[t] > RSI14[t-1]` AND `close[t] > close[t-1]`.
- `close > SMA50` and `close < 0.97 * high55` (a real pullback, not at highs).
- **Trigger (buy-stop):** `high[t] + 0.1*ATR14`, rounded to tick. Only buy if price trades above it: buyers have resumed.
- **Initial stop:** `min(lowest_low(last 7 bars) - 0.2*ATR, trigger - 1.0*ATR)` and never wider than `trigger - 3.0*ATR`.

### 3.5 Setup V: TIGHT-BASE (VCP-STYLE) BREAKOUT
A stock that has already advanced, then consolidates with shrinking volatility and volume under a clear resistance (the **pivot**). The pattern is subjective when drawn by hand, so implement it with these **objective** rules (all parameters in config):
- **Base window:** test `N` from `base_min_bars` (15) to `base_max_bars` (40); use the best-fitting `N` that satisfies the rules below. `pivot = max(high over the base window)`.
- **Depth:** `(pivot - base_low)/pivot <= max_base_depth_pct` (default 20%); depth <= 12% earns a ranking bonus.
- **Volatility contraction:** `ATR14[t] <= atr_contraction_ratio * ATR14[t-25]` (default 0.85) AND the price range of the last third of the base is <= `0.7x` the range of the first third. Optionally require 2-3 successively smaller pullbacks via a zig-zag swing detector (config `min_contractions`, default 2).
- **Tightness:** `(max high - min low over last 5 bars)/close <= tight_5d_pct` (default 5%).
- **Volume dry-up:** `mean(volume last 10 bars) <= 0.9 * avg_vol50` and average down-day volume < average up-day volume inside the base.
- **Support:** no daily close below `SMA50` inside the base; price holds near `EMA20` or `EMA50`.
- **Proximity:** `close` within `pivot_proximity_pct` (default 3%) below the pivot to enter the shortlist.
- **Trigger (buy-stop):** `pivot + 0.1*ATR14`, rounded to tick.
- **Entry zone:** `trigger` up to `trigger + entry_zone_atr*ATR14` (default 0.5 ATR, max 2%). Above the zone = extended; do not chase.
- **Stop (structural invalidation):** `lowest low of the last stop_bars (10) bars - 0.2*ATR14`. Require `1.0*ATR <= trigger - stop <= 2.5*ATR` and `(trigger-stop)/trigger <= max_stop_pct` (default 8%). If the structural stop is wider than allowed, **reject the setup**; never tighten the stop artificially.
- **Reward/risk check:** first target = `trigger + 2R`. Reject if major overhead resistance (e.g. a prior swing high or the 52-week high) sits below `trigger + min_rr_to_resistance*R` (default 1.5R) unless the breakout is to new 52-week highs.
- **Confirmation levels:** *Provisional (intraday):* a **15-minute candle closes above the trigger** and the volume pace is >= `volume_pace_min` (default 1.5x) the expected volume for that time of day (use the symbol's intraday volume profile from recent sessions; fall back to a linear profile). *Confirmed:* the **daily close** is above the pivot, in the upper half of the day's range, with volume >= 1.5x `avg_vol20`.
- **Baseline variant for ablation tests:** `require_contraction=false` reduces this to "price within 5% of the 55-day high", the simple breakout rule from v1, so the backtest can show whether the VCP conditions add value.

### 3.6 Signal states, validity and alert content
Every signal moves through a state machine (applies to both setups):

| State | Meaning |
|---|---|
| WATCHLIST | Passes the trend template and has a valid base/pullback structure; not yet near the trigger |
| APPROACHING | Price within `approach_pct` (default 1.5%) of the trigger |
| TRIGGERED (provisional) | Price above trigger and inside the entry zone; 15-minute close and volume pace confirmed -> **BUY alert** |
| TRIGGERED (confirmed) | Daily close confirms the breakout -> follow-up alert |
| INVALIDATED | Price hits the stop before triggering, closes below SMA50, trend template fails, RED news appears, or the market regime turns Weak |
| MISSED / EXTENDED | Price runs beyond the entry zone -> **SKIP alert**: do not chase |
| EXPIRED | `valid_sessions` elapsed (default 1; setting allows 2) without a trigger |

Do not raise a TRIGGERED alert if the price feed is stale, liquidity is insufficient, event risk is flagged, the cost gate fails, or the regime is Weak.

**Every alert must contain:** exact entry level and acceptable entry range, stop and invalidation price, profit-management plan, reward/risk, volume and relative-strength explanation, market-regime status, news/earnings risk, the last price and its timestamp, and the signal creation timestamp.

### 3.7 Ranking
Score = `100*rs_rank` + bonuses: +10 if market regime Bullish and sector (if available) is in the top 40% by sector RS, +5 volume dry-up before breakout, minus penalties for upcoming earnings (blocked, Section 5) and for cost drag (Section 4.3). Show top `N` per market (default 6).

### 3.8 Exit system (applies to open positions; evaluated at EOD plus live)
Let `R0 = entry - initial_stop`.
1. **Hard stop:** price <= active stop -> SELL ALL.
2. **Breakeven + trail:** once the highest high since entry >= `entry + 1R`, active stop = `max(initial_stop, entry, highest_high_since_entry - 3*ATR14)` (chandelier trail).
3. **Partial profit:** at `entry + 2R` -> SELL HALF (configurable fraction), trail the rest.
4. **Trend break:** daily close < SMA50 -> SELL ALL (alert at EOD; execute next session).
5. **Time stop:** held >= 15 sessions and price < `entry + 0.5R` -> SELL ALL (free the capital).
6. **Earnings guard:** results within 2 trading days -> alert "decide: exit/reduce/hold" (Section 5).
7. All stops are for the **owner to place as a stop-loss order at the broker** (GTT / SL order) right after entry. The UI must remind the owner to do this. A stop is **not guaranteed**: overnight gaps can fill worse.

### 3.9 Gap-risk model (mid caps gap more)
- For each symbol compute the 95th-percentile adverse overnight gap over the last 250 sessions (`gap95`).
- Effective risk per share used for sizing = `max(entry - stop, entry*gap95*0.5 + (entry - stop)*0.5)` (blend; configurable). Purpose: shrink size on gappy stocks.
- Show "gap risk" badge on each signal.

---

## 4. RISK, POSITION SIZING AND COST GATE

### 4.1 Portfolio limits (per market, configurable)
**Conservative research baseline (default for both markets):**
- `risk_per_trade_pct` **0.5%** of that market's capital; `max_portfolio_heat_pct` (sum of open risk to stops) **2%**. Lower values are allowed in config.
- `max_open_positions`: US **4**, India **2**.
- `max_position_pct` default **33%** of capital (single position cap).
- `max_per_sector` default **1** open position (sector from provider metadata when available).
- **Correlation cluster limit:** compute 60-day daily-return correlation among open positions and candidates; pairs with correlation >= `corr_threshold` (default 0.75) count as one cluster; allow at most **1 position per cluster**. Five banking stocks are not five independent bets.
- `daily_new_trades_max` default 2. Optional "pause after N consecutive losses" (default off).
- Never increase size after a win streak or add to losers; a size-increase warning appears in the UI if the owner enters a quantity above the planned quantity.
- **The cost gate (Section 4.3) is the first line of defence for small accounts:** it rejects uneconomical trades instead of raising risk to make them fit.

### 4.2 Sizing
```
risk_amount = capital * risk_per_trade_pct
qty_risk    = floor(risk_amount / effective_risk_per_share)
qty_cap     = floor(capital * max_position_pct / trigger)
qty         = min(qty_risk, qty_cap)       # whole shares; fractional only if broker supports (config)
```
Reject if `qty < 1`, if heat/position limits would be breached, or if the cost gate fails.

### 4.3 Cost model and COST GATE (critical with small capital)
Implement `CostModel` per market with all components configurable and **verified against the owner's broker's current charge page** (brokers change fees):
- India delivery (typical components): brokerage (broker-specific; e.g. a flat amount or % with a minimum), **STT 0.1% on both buy and sell**, exchange transaction charges (about 0.003% of turnover), SEBI turnover fee, **stamp duty on buy (about 0.015%)**, GST 18% on brokerage + transaction + DP charges, and a **flat DP charge per scrip on every sell** (roughly INR 13-24 plus GST depending on broker). With a small account, the flat DP charge can be a large share of the planned risk.
- US: broker commission (often zero), regulatory fees, **FX conversion spread / remittance costs** if the owner funds a US broker from India (configurable flat + percent).
- `slippage_pct` per market (default India mid cap 0.15%, large cap 0.05%; US 0.05%), applied against the owner on each fill in the backtest and in expected-cost estimates.

**Cost gate:** compute `round_trip_cost` in currency for the planned qty.
- Reject the trade if `round_trip_cost > max_cost_in_R * risk_amount` (default `max_cost_in_R = 0.25`, meaning costs may not eat more than a quarter of the risked amount).
- Show cost in R on every signal ("costs = 0.18R").
- Illustration (approximate, verify with real numbers): a INR 5,800 position held a few weeks may pay roughly INR 45-50 in round-trip charges (mostly flat DP + STT), around 0.8% of the position, which is material relative to a 5% stop. The gate exists so the app tells the owner when a trade is too small to be worth it.

**Small-account finding (important):** with roughly INR 17,500 of capital, a 0.5% risk is about INR 87 per trade. With a 5% stop that is a position of only about INR 1,750, and round-trip charges of roughly INR 35-50 (mostly the flat DP charge plus STT; depends on broker) would consume a large share of the risked amount, so the cost gate will reject most Indian trades at baseline risk. **That is the correct, honest outcome**, not a bug.
Options for the owner, in order of preference: (1) run India in **paper mode** (signals and tracking continue; no real money) until capital supports sensible position sizes; (2) increase capital; (3) opt in to `small_account_mode` (default risk 1.5%, heat 3%, max 2 positions), which the UI must label as **higher-risk** and show the larger drawdown it implies. Raising risk merely to absorb fixed costs is not automatically sound, so it is never the default. All numbers here are approximations; the app computes exact values.

### 4.4 Tax (optional)
`tax.enabled=false` by default. If enabled, apply configurable short-term/long-term rates and show after-tax estimates in Journal stats only. Never hard-code rates; show "verify current rates".

---

## 5. NEWS AND EVENT FILTER (SAFETY LAYER, NOT A SIGNAL SOURCE)

News is used to **avoid blow-ups and add context**. Do not generate buy signals from headlines.
**Isolation Invariant:** News, rumors, sentiment, and AI summaries may only BLOCK or flag REVIEW. They can NEVER generate a BUY signal, change position sizing, modify stops, or alter profit targets.

### 5.1 Approved Free Data Sources & Terms Compliance
- **Compliance Policy:** Automated scraping of exchange web pages (e.g. `nseindia.com`, `bseindia.com`), cookie-primed scraping sessions, or unofficial web scrapers (`dalal`, `india-corp-actions`, `BseIndiaApi`) are **strictly prohibited** by exchange terms of use. The platform exclusively uses sanctioned syndication channels and public APIs.
- **India Disclosures (NSE):** Official NSE RSS feeds (`Corporate_announcements.xml`, `Board_Meetings.xml`, `Corp_action.xml`, `Financial_Results.xml`) hosted under `https://nsearchives.nseindia.com/content/RSS/`. Polled at 5-15 min frequency respecting feed TTL.
- **India Disclosures (BSE):** BSE publishes no sanctioned machine-readable feed without browser scraping. BSE coverage is explicitly documented and reported as `UNAVAILABLE` (never scraped).
- **US Disclosures (SEC EDGAR):** Official SEC EDGAR Submissions API (`https://data.sec.gov/submissions/CIK{cik}.json`) and 8-K documents. Free, no API key required. Declares honest `SEC_USER_AGENT` per SEC Fair Access policy. Paced $\le 10$ req/s.
- **Broad News Discovery (GDELT DOC 2.0 API):** Free, no API key required (`https://api.gdeltproject.org/api/v2/doc/doc`). Queries by verified company names and aliases, polled with $\ge 6$s rate pacing.
- **Supplementary US News (Finnhub):** Free company news endpoint. Optional. If `FINNHUB_API_KEY` is unset, the engine operates seamlessly in free keyless mode.
- **Macro Policy Releases (Central Banks):** Official RSS feeds from the Reserve Bank of India (`https://www.rbi.org.in/rss/pressreleases.xml`) and the US Federal Reserve (`https://www.federalreserve.gov/feeds/press_monetary.xml`).

### 5.2 Rules (deterministic keyword + calendar logic; no LLM needed in v1)
- **Earnings blackout:** block new entries if results/earnings fall within `earnings_block_days` (default 7 calendar days) after the signal date. For open positions, alert 2 trading days before results.
- **Severity classifier** on announcement titles/subjects using editable keyword lists in `config/news_rules.yaml`:
  - RED (block entry + immediate alert if held): fraud, forensic audit, SEBI order/penalty, auditor resignation, CFO/CEO sudden resignation, default, insolvency, rating downgrade, trading suspension, promoter pledge invocation, large block sell-down by promoters.
  - AMBER (flag, no block): fund-raise/dilution, board meeting for results, change in key personnel (non-sudden), litigation.
  - GREEN (informational): order wins, buyback, dividend, upgrades, capacity expansion.
- Corporate-action safety: detect splits/bonuses and verify price series is adjusted; re-pull history for the symbol when an action occurs.
- Each signal and position page shows a **News & Events** panel (last 14 days) with severity chips.

### 5.3 Intelligence, Disambiguation & Syndication Modules (v2.3)
- **Entity Resolution & Ticker Collision Guard:** Disambiguates common words/tickers (e.g., `TCS` = "Tax Collected at Source", `BEL` = "Belgium") using legal entity name normalization. Short bare tickers route to `TICKER_ONLY` for manual review, never confirmed relevance.
- **Wire Syndication Clustering:** Detects wire agency attribution (Reuters, PTI, ANI, IANS, Bloomberg, PR Newswire) and clusters identical syndicated stories across publishers into a single cluster ID.
- **Rumour & Hedged Language Classifier:** Flags speculative phrases ("sources said", "reportedly", "people familiar", "mulls", "unconfirmed") as `UNVERIFIED RUMOUR`. Official regulatory filings are never flagged as rumour.
- **Analyst Action Extractor (Strict Null Rule):** Parses brokerage upgrades, downgrades, and target prices. If a field is not explicitly present in the text, it remains strictly `null` (None). Never synthesizes or hallucinates ratings.
- **Deterministic Materiality Evaluator:** Computes score via $\text{Materiality} = \text{Category Weight} \times \text{Source Authority} \times \text{Recency Decay} \times \text{Price Reaction}$ to categorize items as `HIGH`, `MEDIUM`, or `LOW`.
- **Contextual Price Reaction:** Computes day's % price move and ATR multiple to show whether market has already priced the news.
- **Extractive Summarizer:** Deterministic 2-sentence extractive summary interface combining headline and first non-redundant sentence. Zero hallucination risk.

### 5.4 News data model, de-duplication and coverage status
- **Timestamps & Latency Classes:** store `published_at` separately from `ingested_at`. Use 4 empirical latency classes (`near-real-time`, `delayed`, `periodic/batch`, `unavailable`). Never label internet feeds as "real-time".
- **De-duplication:** normalized token + time bucket deduplication key (`dedupe_key`), combined with wire syndication cluster ID (`syndication_cluster_id`).
- **Coverage status per symbol per scan (stored in `news_coverage`):**

| Status | Meaning |
|---|---|
| `CLEAR` | All required sources were fetched successfully within `max_source_age_min`, no offline coverage gaps exist, the earnings/results date is known and outside the blackout window, and no AMBER/RED flags exist. |
| `REVIEW` | AMBER flags, an upcoming result inside the warning window, macro caution window, unverified rumour, or partial source coverage; the owner must read the items before buying. |
| `BLOCKED` | RED flag or earnings blackout; no entry signal is raised. |
| `UNKNOWN` | A required source failed, is stale (>60m), unconfigured, or an offline coverage gap was recorded during market hours. **UNKNOWN is NEVER shown or treated as CLEAR.** |

- `news.unknown_policy`: `warn` (default; signal is allowed but carries a prominent "NEWS UNKNOWN: REVIEW MANUALLY" flag and a ranking penalty) or `block`.
- Every BUY alert and signal card shows the coverage status, which sources were checked, and when.

### 5.5 Macroeconomic Event Calendar (2026)
- Versioned calendar in `config/macro_calendar.yaml` with RBI MPC and US FOMC meeting dates.
- Automated caution window flags trades within `caution_window_trading_days` (default 1 trading day) as `REVIEW` with clear macro caution banners.

### 5.6 Optional AI summaries (off by default; never a signal source)
- Purpose: short summaries and category suggestions for official filings and articles, to save reading time.
- **Guardrails:** summaries are labelled "AI summary: verify with source" and always link the original; the AI never outputs buy/sell calls, scores or price targets; deterministic rules (Section 5.2) remain the authority for severity, and the AI may only **escalate** an item to REVIEW, never downgrade a RED/AMBER item; no private data (positions, balances) is sent to the model; cache results; enforce `news.ai_summaries.monthly_budget_usd`; disable automatically when no key or budget is configured; log model, prompt version and token cost.

---

## 6. DATA LAYER (FREE SOURCES)

### 6.1 Provider interface
```python
class MarketDataProvider(Protocol):
    name: str
    def daily_bars(self, symbols: list[str], start: date, end: date) -> dict[str, pd.DataFrame]: ...
    def quotes(self, symbols: list[str]) -> dict[str, Quote]: ...   # last price, day volume, timestamp
    def health(self) -> ProviderHealth: ...
```
Bars columns: `date, open, high, low, close, adj_close, volume` (split/dividend adjusted for indicators; keep raw close for order-price display).

### 6.2 Implementations
1. **YFinanceProvider** (research and fallback provider only): free, unofficial, **delayed**; flagged `realtime=false`, so it may populate charts and daily history but **never fires live trigger alerts**. Symbols `RELIANCE.NS`, `AAPL`. Batch downloads, `auto_adjust=True` for indicators.
2. **AngelOneProvider** (**CORE, mandatory primary for India**; use recorded fixtures/mocks in development if credentials are not ready): free SmartAPI; `pip install smartapi-python pyotp`; login with client code + PIN + TOTP via `SmartConnect`; historical via `getCandleData` (daily), live via LTP/quote. Notes: sessions expire daily (re-login each morning job), throttle about 3 req/s (sleep ~0.35s between calls), respect per-request candle limits by chunking date ranges, map NSE symbols to SmartAPI tokens using Angel One's published instrument master JSON (refresh daily). Verify all of this against the current SmartAPI docs before coding.
3. **AlpacaProvider** (US; **default recommendation for real-time US data, pending the owner's confirmation and eligibility check**; yfinance alone does not meet the real-time requirement): the free Basic plan gives real-time **IEX-only** data, **30 WebSocket symbols**, about 200 historical calls/minute, history since 2016, and no access to the most recent 15 minutes of historical data; the paid Algo Trader Plus plan (about USD 99/month) adds all US exchanges and unlimited symbols (verify current terms). Caution: IEX volume is only a fraction of consolidated volume, so **compute volume-pace baselines from the same feed** (or from yfinance daily consolidated volume), never mix feeds when comparing volume. The 30-symbol limit is enough for a short watchlist.
4. **IBKRProvider** (optional, US): only if the owner already trades US stocks through Interactive Brokers; the free streaming feed is non-consolidated and full coverage may need paid exchange subscriptions. Do not buy any data subscription until the owner confirms their US broker and the need.
5. Optional later: Kite Connect (paid plan needed for data), Upstox/Fyers free APIs. Keep provider choice a config setting.
- **Streaming strategy:** use historical candles for the broad scan, then subscribe to live prices **only for shortlisted symbols and open positions** (Angel One SmartAPI documents WebSocket limits per connection; verify before coding).

### 6.3 Reliability rules
- Provider chain per market: `[primary, fallback]`. On failure/staleness, switch to fallback and raise a health warning on the dashboard.
- **Cross-check job (weekly):** compare 20 random symbols' last 30 closes between providers; flag if deviation > 0.5%.
- **Validation per series:** no gaps longer than expected holidays (use `exchange_calendars`: XNSE, XNYS), no zero/negative prices, volume >= 0, high >= max(open, close), low <= min(open, close), last bar date equals the last completed session.
- **Feed freshness (strict, per feed, configurable):** trigger, stop and target alerts may be fired only from a **real-time** feed whose last tick is no older than `monitor.freshness.websocket_tick_max_age_sec` (default 20 s, and the WebSocket heartbeat must be healthy) or, in polling fallback, whose last REST quote is no older than `rest_quote_max_age_sec` (default 60 s). Otherwise mark the symbol STALE, suppress trigger alerts, and raise a DATA alert if staleness persists beyond `persistent_stale_alert_sec` during market hours. Delayed feeds never fire trigger alerts (`delayed_feed_policy: informational_only`). Compare exchange timestamps with the server clock and warn if skew exceeds `clock_skew_warn_sec` (require NTP time sync on the host).
- Store all bars in SQLite (`bars_daily`), update incrementally, keep 3 years of history (backtests may request more, fetch lazily and cache).
- Time zones: store UTC, display IST by default. NSE session 09:15-15:30 IST; NYSE/Nasdaq 09:30-16:00 America/New_York (handle DST). Use exchange calendars for holidays and early closes.

### 6.4 Portfolio provider: Zerodha Kite Connect "Personal" (READ-ONLY)
**Role split:** Angel One SmartAPI supplies *market data*; Zerodha Kite Personal supplies *the owner's real account data* so the dashboard reflects actual holdings, positions, funds and trades. Kite Personal has no historical-chart or live-quote APIs, so it is never used for prices. It is never used to place, modify or cancel orders.

- **Interface:** `PortfolioProvider` with `profile()`, `funds()`, `holdings()`, `positions()`, `orders()`, `trades()`. Implementation `KitePortfolioReader` wraps the official `kiteconnect` Python library but exposes **only** these read methods.
- **Endpoints used (via library):** user profile, margins (equity segment), portfolio holdings, portfolio positions, orders, trades. Verify names against the current Kite Connect docs.
- **Login flow (daily):** the owner registers a Kite Connect app (free Personal) and a redirect URL in the Kite developer console (for local use, a loopback URL such as `http://127.0.0.1:<port>/api/portfolio/kite/callback` works; for remote hosting use the app's HTTPS callback). The app's "Connect Zerodha" button opens `https://kite.zerodha.com/connect/login?v=3&api_key=...`; after login Kite redirects with a short-lived `request_token`, which the backend exchanges for an `access_token` (checksum = SHA-256 of `api_key + request_token + api_secret`, handled by the library's `generate_session`).
- **Token lifetime:** the access token **expires every day (around 06:00 IST) and there is no refresh token**. The app must detect auth errors, show a "Reconnect Zerodha" banner, and send a Telegram reminder around 08:45 IST on trading days. Kite sessions may also be invalidated if the owner logs into certain other platforms, so treat any invalid-token error as "reconnect needed". **Do not store the owner's Zerodha password or TOTP secret and do not script the login**; the owner logs in manually once a day. Store the access token only in memory or in a file with owner-only permissions; never log it.
- **Sync schedule:** every `portfolio.sync_interval_min` (default 5) during NSE hours, plus once after the close. Save raw payloads to `broker_snapshots`.
- **Reconciliation rules:**
  1. A new BUY (position or trade) in a symbol that has a live signal from the same session creates a position (`source=KITE`, linked `signal_id`), pre-filled with the signal's stop and target; the owner confirms or edits the stop. Never auto-trust.
  2. Holdings and positions **not matched to any signal are not swing trades**: list them under "Other holdings (not tracked)". The owner can toggle "Track as swing" to apply exit rules. This prevents sell alerts on long-term investments.
  3. A SELL (quantity reduced or a SELL trade) closes or partially closes the tracked position, computes realised P/L, and writes the journal entry after asking for the exit reason.
  4. Same-day delivery buys can appear under positions before they show in holdings after settlement; merge both views by symbol and date to avoid duplicates (verify actual behaviour in testing).
  5. Orders/trades show whether the owner placed the **stop-loss order** the app recommends; if a tracked position has no matching open stop order, show a prominent reminder.
- **Funds:** `capital_source: manual | kite_cash`. With `kite_cash`, sizing uses `min(swing_capital_cap, available cash)` so the app never sizes against the owner's entire account; warn if cash is less than the planned position cost.
- **Reports:** Zerodha Console reports (P&L, tradebook, charges statements) are not part of this API tier; provide an optional CSV import for them later.
- **Scope:** Zerodha is India-only. US positions stay manual (or come from the US broker's API later).
- **Symbol mapping:** one `instruments` table maps Kite `tradingsymbol` (e.g. `RELIANCE`), Angel One symbol and token (e.g. `RELIANCE-EQ`), and yfinance (`RELIANCE.NS`). Unit-test at least 20 symbols, including special characters (for example `M&M`, `BAJAJ-AUTO`) and a renamed stock.
- **Rate limits and failure handling:** throttle to a few requests per second, back off on HTTP 429, and degrade gracefully (the dashboard keeps working on manual positions if Kite is disconnected).

### 6.5 Real-time monitoring (WebSocket first, polling as fallback)
- **India:** subscribe to Angel One's WebSocket feed **only for shortlisted signals and open positions** (verify current connection and token-subscription limits in the SmartAPI docs). Re-authenticate and **re-subscribe after the daily login**; track the feed token separately from the API session.
- **US:** if Alpaca is confirmed, use its WebSocket for the shortlist (the free plan allows 30 symbols, so cap the live shortlist accordingly).
- **Subscription manager:** adds/removes symbols as signals appear, expire or positions open/close; never exceeds provider limits; logs every change.
- **Resilience:** heartbeat timeout, automatic reconnect with exponential backoff (`monitor.reconnect_backoff_sec`), gap detection after reconnect (back-fill missed minutes from the historical/intraday endpoint), and automatic fallback to REST LTP polling every `polling_interval_sec` with a visible "polling mode" badge.
- **CandleBuilder:** build 1-minute and 15-minute candles from ticks (aligned to exchange session times) so the 15-minute close confirmation (Section 3.5) can be evaluated live; reconcile against the provider's intraday candles at session end and log any mismatch.
- **Alert engine** consumes ticks/candles, applies the signal state machine (Section 3.6), the freshness rules (Section 6.3) and de-duplication, then dispatches alerts. Interval polling at five minutes is **not** sufficient for breakout alerts.

### 6.6 Portfolio valuation and data provenance
Zerodha Personal supplies account data but no live quotes; Angel One supplies prices. The dashboard combines them but must keep their origins visible:

| Metric | Source |
|---|---|
| Holdings and quantity | Zerodha (read-only sync) |
| Average buy price | Zerodha |
| Current market price | Angel One (WebSocket/LTP) |
| **Estimated live P&L** = `(Angel One LTP - Zerodha average price) * quantity`, before charges | Our calculation |
| Broker-reported P&L / last price | Zerodha snapshot, shown separately with its timestamp |
| Historical realised P&L | Stored trades and imported Zerodha reports |
| Trading signals, stops, targets, quantities | Our strategy engine |

- Show broker-reported and calculated P&L side by side with their timestamps; flag differences larger than a threshold (price timing, corporate actions, symbol mapping errors).
- **Report imports (supported from v1, optional to use):** import Zerodha Console CSVs (tradebook, P&L, charges). The Kite Personal API does not provide complete historical reports, so imports fill the gap for realised P&L, charges and journal accuracy. Validate file format, hash each file to prevent double import, map symbols through the `instruments` table, and store rows in `imported_reports` / `report_trades`; reconcile against synced trades and flag mismatches.
- Every UI value uses a source chip and an "as of" time (rule 10); stale values are dimmed.

---

## 7. ARCHITECTURE AND REPO LAYOUT

```
swing-platform/
  README.md
  docker-compose.yml
  .env.example
  config/
    strategy.yaml
    news_rules.yaml
  data/                      # git-ignored: sqlite db, universe csvs, caches
  backend/
    pyproject.toml
    app/
      main.py                # FastAPI app, lifespan starts scheduler
      settings.py            # pydantic-settings, loads yaml + env
      db.py  models.py       # SQLAlchemy/SQLModel
      providers/             # base.py, yfinance_provider.py, angelone_provider.py, news_nse_bse.py, news_us.py
      engine/
        indicators.py  regime.py  universe.py  screener.py
        setups.py  sizing.py  costs.py  exits.py  gaprisk.py
        newsfilter.py  planner.py   # planner orchestrates scan -> TradePlan
      backtest/
        simulator.py  metrics.py  walkforward.py  montecarlo.py
      scheduler/jobs.py      # APScheduler jobs
      notify/telegram.py  notify/dispatcher.py
      api/                   # routers: signals, positions, journal, backtests, settings, news, system, stream
    tests/
  frontend/
    package.json  vite.config.ts  tailwind.config.ts
    src/
      api/ (typed client)  components/  pages/  hooks/  lib/
  .github/workflows/         # optional EOD scan workflow (Section 15)
```
- Python libs: `fastapi`, `uvicorn`, `sqlmodel` (or SQLAlchemy 2), `pydantic-settings`, `apscheduler`, `pandas`, `numpy`, `yfinance`, `exchange_calendars`, `smartapi-python`, `pyotp`, `httpx`, `tenacity`, `pyyaml`, `pytest`, `ruff`, `mypy`.
- Frontend libs: React 18, TypeScript, Vite, Tailwind, TanStack Query, React Router, `lightweight-charts` (open-source candlesticks), Recharts for stats, Zod for API types. Mobile-first responsive; installable PWA (manifest + service worker) so the owner can open it from the phone home screen.
- Single process in v1 (FastAPI + in-process APScheduler). Keep job functions pure and idempotent so they can later run from cron/GitHub Actions.

---

## 8. DATABASE SCHEMA (Neon PostgreSQL)

Neon PostgreSQL is the sole application database from day one (strictly no SQLite support, no dual adapters, no planned future database migration). Configured via `DATABASE_URL` with connection pooling (`QueuePool`, `pool_size=10`, `max_overflow=20`, `pool_recycle=300`, `pool_pre_ping=True` to seamlessly survive serverless autosuspend/wakeups), transient retry handling (`tenacity`), transaction management context, timezone-aware UTC timestamps (`TIMESTAMPTZ`), and reviewed Alembic migrations (`backend/alembic/versions/`). Automated tests use isolated rollback transaction fixtures guaranteeing actual trading records are never deleted or modified.

- `instruments(id SERIAL PRIMARY KEY, symbol, market, name, sector, industry, provider_token, active, added_at TIMESTAMPTZ)`
- `bars_daily(symbol, date, open, high, low, close, adj_close, volume, source, PRIMARY KEY(symbol,date))`
- `scans(id SERIAL PRIMARY KEY, market, run_at TIMESTAMPTZ, session_date, regime, regime_detail_json, universe_size, passed_filters, data_warnings_json)`
- `signals(id SERIAL PRIMARY KEY, scan_id FK, symbol, market, setup, trigger, entry_zone_high, stop, target1, qty, risk_amount, cost_estimate, cost_in_r, rs_rank, score, atr, gap95, reasons_json, news_flags_json, state[WATCHLIST|APPROACHING|TRIGGERED_PROVISIONAL|TRIGGERED_CONFIRMED|INVALIDATED|EXTENDED|EXPIRED|SKIPPED], valid_until, created_at TIMESTAMPTZ)`
- `positions(id SERIAL PRIMARY KEY, symbol, market, source[MANUAL|KITE], tracked_as_swing, signal_id FK, mode[LIVE|PAPER], entry_date, entry_price, qty, initial_stop, active_stop, target1, status[OPEN|CLOSED], notes, created_at TIMESTAMPTZ)`
- `fills(id SERIAL PRIMARY KEY, position_id FK, side[BUY|SELL], date, price, qty, fees_total, fees_json)`
- `journal(id SERIAL PRIMARY KEY, position_id FK, symbol, market, entry_date, entry_price, exit_date, exit_price, qty, exit_reason, pnl_amount, pnl_pct, r_multiple, holding_days, fees_total, mae, mfe, tags, note)`
- `alerts(id SERIAL PRIMARY KEY, ts TIMESTAMPTZ, type[BUY|SELL|SELL_HALF|CANCEL|SKIP|NEWS|DATA|SYSTEM], symbol, market, title, body, payload_json, delivered_telegram, acknowledged, retry_count, last_reminder_ts TIMESTAMPTZ)`
- `news_events(id SERIAL PRIMARY KEY, symbol, source, source_id, title, url, published_at TIMESTAMPTZ, ingested_at TIMESTAMPTZ, severity, category, dedupe_key, canonical_event_id, ai_summary, raw_json, match_confidence, is_unverified, syndication_cluster_id, materiality, summary, price_change_day_pct, price_atr_multiple, analyst_action_json)`
- `news_source_state(source PRIMARY KEY, last_polled_at TIMESTAMPTZ, consecutive_failures, last_successful_poll_at TIMESTAMPTZ, error_message, is_healthy)`
- `news_coverage_gaps(id SERIAL PRIMARY KEY, source, market, symbol, error_message, detected_at TIMESTAMPTZ, resolved_at TIMESTAMPTZ)`
- `earnings_filings(id SERIAL PRIMARY KEY, symbol, market, period_type, period_ended, filing_date, revenue, operating_profit, net_profit, eps, currency, source_name, source_url, consensus_eps, consensus_source, severity, flags_json, ai_summary, created_at TIMESTAMPTZ)`
- `news_coverage(id SERIAL PRIMARY KEY, scan_id FK, symbol, status[CLEAR|REVIEW|BLOCKED|UNKNOWN], sources_checked_json, checked_at TIMESTAMPTZ)`
- `macro_events(id SERIAL PRIMARY KEY, ts TIMESTAMPTZ, region, title, importance, source)`
- `imported_reports(id SERIAL PRIMARY KEY, kind[TRADEBOOK|PNL|CHARGES], file_hash UNIQUE, imported_at TIMESTAMPTZ, row_count)` and `report_trades(id SERIAL PRIMARY KEY, report_id FK, symbol, side, qty, price, trade_date, charges_json)`
- `backtest_runs(id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ, config_json, universe, start_date, end_date, metrics_json, status)` and `backtest_trades(id SERIAL PRIMARY KEY, run_id FK, symbol, setup, entry_date, entry_price, exit_date, exit_price, exit_reason, qty, pnl, r_multiple, costs)`
- `broker_snapshots(id SERIAL PRIMARY KEY, ts TIMESTAMPTZ, broker, kind[HOLDINGS|POSITIONS|MARGINS|TRADES|ORDERS], payload_json)`
- `settings_kv(key PRIMARY KEY, value_json, updated_at TIMESTAMPTZ)`, `job_runs(id SERIAL PRIMARY KEY, job, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, status, detail)`
- `decision_audits(id SERIAL PRIMARY KEY, symbol, market, asof_date, mode, final_decision, setup, trigger, stop, target1, qty, risk_amount, cost_in_r, config_hash, code_version, data_source, created_at TIMESTAMPTZ)`
- `decision_stage_results(id SERIAL PRIMARY KEY, audit_id FK, stage_name, status, checks_json, rejection_reasons_json)`

Alembic migrations (`backend/alembic/`) manage all schema evolution. Point-in-time database snapshot backup and restore procedures are provided via `backend/app/db_backup.py` and scheduled nightly (`job_db_backup`). Database health and connection pool metrics are monitored continuously at `/api/health/db`.

---

## 9. BACKEND API (FastAPI, JSON, typed with Pydantic)

All routes under `/api`. Protect with a bearer token from env `APP_TOKEN` (single-user app; the UI stores it locally). Provide OpenAPI docs at `/docs`.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | provider health, last job runs, data freshness, warnings |
| GET | `/regime?market=IN\|US` | regime status with the numbers behind it |
| GET | `/plan?market=&date=` | today's Trade Plan (ranked signals with reasons, qty, cost-in-R, news flags) |
| GET | `/signals/{id}` | full signal detail incl. indicator snapshot for the chart |
| POST | `/scan/run?market=` | run a scan on demand (async job, returns job id) |
| GET | `/watchlist` | active signals + open positions with live prices, distance to trigger/stop |
| GET | `/quotes?symbols=` | latest cached quotes with staleness flags |
| GET | `/bars/{symbol}?tf=1d\|15m&n=250` | OHLCV + EMA20/50, SMA50/150/200, RSI14, ATR14, feed status, and strategy overlay |
| GET/POST | `/positions` | list / create ("I took this trade": actual price, qty, date, signal id) |
| PATCH | `/positions/{id}` | edit stop, notes |
| POST | `/positions/{id}/close` | record exit (price, qty, date, reason) -> writes journal row |
| GET | `/journal`, `/stats` | trade log, equity curve, win rate, expectancy (R), profit factor, max drawdown, by setup and market |
| POST | `/backtests` | start backtest with config overrides; GET `/backtests/{id}` results and trades |
| GET/PUT | `/settings` | read/write strategy, risk, cost, schedule and notification settings (validated) |
| GET | `/news?symbol=&days=14` | classified events |
| GET | `/portfolio/kite/login-url` | returns the Kite login URL for the "Connect Zerodha" button |
| GET | `/portfolio/kite/callback` | receives `request_token`, exchanges it for the daily access token |
| GET | `/portfolio/status` | connection state, token expiry, last sync time |
| POST | `/portfolio/sync` | run a read-only sync now |
| GET | `/portfolio/holdings`, `/portfolio/untracked` | synced holdings; holdings not tracked as swing |
| POST | `/portfolio/track/{symbol}` | toggle "track as swing" with stop and notes |
| GET | `/portfolio/valuation` | holdings valued with live prices: broker-reported vs calculated P&L, each with source and timestamp |
| POST | `/portfolio/import` | upload Zerodha Console CSV (tradebook / P&L / charges); returns validation summary |
| GET | `/news/coverage?symbols=` | CLEAR / REVIEW / BLOCKED / UNKNOWN per symbol with sources checked |
| GET | `/alerts` | alert history; POST `/alerts/{id}/ack` |
| GET | `/stream` | **Server-Sent Events** pushing new alerts and price ticks to the UI |

Conventions: ISO dates, UTC timestamps with explicit tz, money as Decimal strings plus currency code, consistent error envelope `{error:{code,message,detail}}`.

---

## 10. SCHEDULER / BACKGROUND JOBS (APScheduler, exchange-calendar aware)

All times local to the exchange; skip holidays via `exchange_calendars`; jobs are idempotent and log to `job_runs`.

| Job | When | Action |
|---|---|---|
| `refresh_universe` | monthly | reload constituent lists, update `instruments` |
| `eod_refresh_IN` | ~16:30 IST on trading days | pull daily bars, validate |
| `eod_scan_IN` | right after refresh | regime -> screen -> setups -> news filter -> sizing -> save plan -> Telegram summary |
| `eod_refresh_US` / `eod_scan_US` | ~16:45 America/New_York | same for the US |
| `news_refresh` | every 30 min during market hours + evening | pull announcements/calendars, classify |
| `stream_IN` / `stream_US` | continuous during that market's hours | WebSocket workers for the shortlist + open positions (Section 6.5): build candles, evaluate states/triggers/stops/targets, enforce freshness, send de-duplicated alerts; auto-fallback to REST polling every `polling_interval_sec` |
| `positions_eod` | after each market's scan | evaluate exit rules (trend break, time stop, earnings guard), update trailing stops, alert |
| `paper_tracker` | after each scan and during monitor | simulate fills for every live signal and every shadow-mode signal in PAPER mode using Section 12 fill rules |
| `kite_sync` | every 5 min during NSE hours + after close | read-only holdings/positions/funds/trades sync and reconciliation (Section 6.4) |
| `kite_reminder` | ~08:45 IST on trading days | Telegram reminder if the Kite session has expired |
| `data_crosscheck` | weekly | provider cross-check (Section 6.3) |
| `db_backup` | nightly | SQLite backup |
| `angelone_login` | daily pre-market IST | refresh SmartAPI session (if enabled) |

Startup behaviour: on boot, run a catch-up (if the last EOD scan is older than the last session, run it now).

---

## 11. FRONTEND SPEC (React + TypeScript)

Design goals: fast, calm, mobile-first (owner checks from a phone), dark/light theme, clear numbers, no clutter. Always show currency symbols and market tags (IN/US).

### Pages
1. **Dashboard (default)**
   - Market regime cards (IN, US): Bullish/Caution/Weak with the numbers (index close vs SMA50/200).
   - **Today's Trade Plan**: per market, ranked signal cards. Each card: symbol, setup badge (Tight-base breakout / Pullback), state badge (Watchlist / Approaching / Triggered / Invalidated / Extended), trend-template pass/fail checklist, **Buy above X**, **Stop Y**, **Target Z (2R)**, **Qty N**, risk in currency, cost in R, gap-risk badge, news chips, and an expandable "Why" list of reasons. Buttons: "Open chart", "I took this trade", "Skip".
   - Live strip: nearest-to-trigger names with distance %, alerts feed, data-health indicator.
   - If there are no setups, show "No qualifying setups: doing nothing is a valid trade."
2. **Signal detail**: Interactive TradingView candlestick chart (`lightweight-charts@5.2.1`) supporting Daily and 15m timeframes, EMA20/50, SMA50/150/200, volume overlay, separate RSI14 & ATR14 panels, VCP consolidation base box, trigger/stop/target/entry-zone lines, signal confirmation markers, 8-point Minervini Trend Template drawer, manual drawing tools (horizontal line, trendline, rectangle), and data feed provenance status (LIVE / DELAYED / STALE / DISCONNECTED).
3. **Watchlist/Live**: table of active signals and open positions with live price, % to trigger, % to stop, staleness dot; auto-refresh via SSE.
4. **Positions**: (auto-synced from Zerodha where connected, with a "Synced" badge, a "Mark as swing trade" toggle and an "Other holdings (not tracked)" list; manual entry for US) open positions with entry, qty, active stop (with "move stop to X at your broker" prompts when the trail moves), unrealized P/L in currency and R, days held, next-rule warnings (earnings in N days, close below SMA50), "Record exit" dialog.
5. **Journal & Analytics**: (includes import of Zerodha Console CSV reports) trade table with filters; equity curve; win rate, avg win/loss, expectancy in R, profit factor, max drawdown, by setup/market/month; paper-vs-live comparison; notes and tags.
6. **Backtests**: configure (market, dates, parameter overrides), run, view equity curve, drawdown chart, trade list, monthly returns heatmap, parameter-sensitivity view, acceptance-gate checklist (pass/fail from Section 12.4).
7. **Settings**: Zerodha connection status with a daily "Reconnect" button, capital per market and currency (manual or capped by available Kite cash), risk %, limits, cost model fields (broker preset + custom), regime options, schedule/monitor interval, providers and credentials status (never display secrets), Telegram setup test button, theme, disclaimer text.
8. **System/Logs**: provider health, job history, data warnings, last scan details.

### UI behaviours
- Source chips and "as of" times on every number (rule 10); a live-feed status badge (WebSocket / polling / STALE / delayed); news coverage chips (CLEAR / REVIEW / BLOCKED / UNKNOWN).
- SSE connection with auto-reconnect; toast + sound option for BUY/SELL alerts; browser notifications permission.
- Every alert deep-links to the relevant signal/position.
- "Copy order summary" button (e.g. `BUY RELIANCE | trigger 1234.50 | SL 1180 | qty 3`) for convenience; reminder text: "Place a stop-loss order at your broker immediately after you are filled."
- Accessible colors (do not rely on red/green alone), keyboard navigable, loading skeletons, empty states, error boundaries.

---

## 12. BACKTESTER SPECIFICATION

### 12.1 Engine
Event-driven daily simulation over the chosen universe and period, reusing the **same engine modules** as live (no duplicate logic). Portfolio-level: respects capital, risk %, max positions, heat, sector limits, daily trade limits, cost gate, regime filter, earnings blackout (when historical earnings dates are available; otherwise flag the run "earnings filter not applied" in results).

### 12.2 Fill rules (conservative, deterministic)
- Signals generated on the close of day *t*; orders live on day *t+1* only.
- **Buy-stop entry:** if `open[t+1] >= trigger` -> fill at `open` (gap-up, no better); elif `high[t+1] >= trigger` -> fill at `trigger`; else no trade. Add slippage against the trader.
- **Stop exit:** if `open <= stop` -> fill at `open` (gap-through); elif `low <= stop` -> fill at `stop`. Add slippage.
- **Same-bar ambiguity:** if both stop and target are touched in one bar, assume the **stop hit first**.
- Target/partial: fill at the target price if `high >= target` (and not gapped lower rules above).
- Trend-break and time-stop exits execute at the **next open**.
- Apply the full `CostModel` on both legs, including flat DP charge per sell.

### 12.3 Bias controls and honesty
- **Survivorship bias:** free data only has today's constituents. Label every result "optimistic: survivorship bias" and prefer relative comparisons (strategy vs buy-and-hold index over the same dates).
- **No parameter tuning on the whole sample.** Provide **walk-forward** (e.g. optimize on 3 years, test on the next 1 year, roll) and a held-out final period never used for tuning.
- **Sensitivity grid:** vary key parameters +/-20% (RS cutoff, ATR multiples, RSI threshold, trail multiple); show whether results hold. A strategy that only works at one exact setting is rejected.
- **Candidate comparison (ablation):** run Setup P alone, Setup V alone, the simple 55-day-high baseline, and the combination. Also compare exit variants: partial profit at 2R plus trailing stop versus a pure trailing stop. Enable only what survives out-of-sample; do not keep a component because it sounds good.
- **Monte Carlo:** shuffle trade order 1,000 times to show the distribution of max drawdown and ending equity.
- Test periods must include stress periods (e.g. 2020 crash, 2022 drawdown, India's mid/small-cap corrections).

### 12.4 Acceptance gates (displayed as a checklist; defaults, editable)
All of these should pass on the **out-of-sample** portion before the owner uses real money:
- Trades >= 150 (combined across markets where needed).
- Expectancy after costs >= **+0.15R** per trade.
- Profit factor >= **1.3**.
- Max drawdown <= **20%** of capital (and the owner confirms they can tolerate it).
- Positive in both halves of the sample and in at least 3 of 4 calendar years tested.
- Still profitable with slippage doubled and costs +25%.
- Parameter-sensitivity: >= 70% of neighbouring parameter sets remain profitable.
Expectancy per trade in R: `E = (P_win * avg_win_R) - (P_loss * avg_loss_R) - cost_R`, where `cost_R` is trading cost divided by initial risk. Net positive expectancy matters more than a high win rate.
Metrics: CAGR, total return, volatility, Sharpe/Sortino (clearly labelled), max drawdown and duration, win rate, avg win/avg loss, expectancy (R), profit factor, exposure %, turnover, costs as % of gross profit, longest losing streak, best/worst trade, % of profit from top 5 trades.

### 12.5 What free data cannot backtest
Free intraday history is short (for example only a limited window of 15-minute bars), so the **15-minute confirmation and intraday volume-pace rules cannot be validated over many years**. Backtests therefore use **daily bars with conservative fills** (Section 12.2), and the intraday confirmation is validated through **paper trading and forward logging** (store each alert's price, 15-minute candle, volume pace and the price actually available a few minutes later to measure slippage). Report this limitation on every backtest page.

### 12.6 Reconciled Accounting & Execution Invariants (Audit-Verified 2026-11-05)
1. **Gross vs. Net P&L Consistency:**
   - `Gross_PnL = (exit_reference - entry_reference) * qty` (or sum across partial and remaining legs).
   - `Total_Costs = Round_Trip_Brokerage_Taxes + Entry_Slippage + Exit_Slippages`.
   - `Net_PnL = Gross_PnL - Total_Costs`.
   - At trade level: `trade.gross_pnl - trade.costs == trade.pnl`.
   - At portfolio level: `gross_profit - gross_loss - total_costs == total_pnl` and `net_profit - net_loss == total_pnl`.
2. **Slippage Deducted Once:** Slippage is applied directly to execution fill prices (`fill_price = trigger * (1 + slip_pct)` for entries, `exit_price = exit_ref * (1 - slip_pct)` for exits). `CostModel.calculate_round_trip` is called with `include_slippage=False` to strictly prevent double-counting.
3. **Conservative Same-Candle Ambiguity:** When a daily candle's high touches the profit target and its low touches the stop loss, the simulator assumes the **stop was hit first** (conservative bias).
4. **Next-Open Exits:** Exits triggered by daily close conditions (SMA50 trend break, time stops) are queued as `exit_pending` and filled at the next session's `open * (1 - slip_pct)`.
5. **Pending Order Reservation & Duplicate Prevention:** Pending orders reserve position count and portfolio heat. Instruments already open or pending cannot generate duplicate entries.
6. **Mark-to-Market Equity & Drawdown:** Daily portfolio equity tracks realized P&L plus marked-to-market unrealized P&L (net of estimated round-trip costs and adverse exit slippage). Maximum drawdown is evaluated from the complete daily equity curve rather than closed-trade steps alone.
7. **Walk-Forward Validation Protocol:**
   - Windows with insufficient history (< 300 bars) return `status="INSUFFICIENT_DATA"` (never auto-pass).
   - Empty validation windows (0 trades) are strictly rejected (`passed=False`).
   - Training windows (`curr_start` to `train_end`) and out-of-sample testing windows (`train_end + 1 day` to `test_end`) are strictly non-overlapping.
   - Final holdout data (`holdout_months`) is set aside untouched and is excluded from parameter optimization.
   - Trials count is explicitly recorded (`trials_recorded`), and strategies are never approved solely by virtue of rank.

### 12.8 Historical Market Data Expansion & Research Readiness (Phase 1 Implemented 2026-11-05)
1. **Session Targets & Research Eligibility Gates:**
   - **Target (5 Years):** 1,250 actual trading sessions per eligible universe symbol.
   - **Interim Minimum (3 Years):** 750 actual trading sessions.
   - **Strict Research Gate (1.2 Years):** 300 trading sessions. Any symbol under 300 bars returns `status="INSUFFICIENT_DATA"` and is strictly disqualified from backtest evaluation.
2. **Split-Adjusted OHLC & Geometric Integrity:**
   - Raw OHLCV is strictly preserved in `DailyBar` (`open`, `high`, `low`, `close`, `volume`).
   - Split adjustments scale all 4 OHLC price points by the exact same multiplier (`split_adj_open`, `split_adj_high`, `split_adj_low`, `split_adj_close`), strictly preserving candlestick geometry and body/shadow proportions:
     $$\frac{H - L}{H_{adj} - L_{adj}} = \text{const}$$
   - Cash dividend adjustments are isolated in `dividend_factor = adj_close / split_adj_close` and never mutate historical price levels.
3. **Exchange Calendar Reconciliation:**
   - US and Indian trading calendars (`calendars.py`) map all official exchange holidays from 2020 through 2027+.
   - Legitimate holidays (e.g. NSE Republic Day, Diwali, Eid; US Thanksgiving, Good Friday, Memorial Day) are never treated as missing sessions.
4. **Resumable Ingestion & Quality Precedence:**
   - Checkpoints tracked per symbol in `ingestion_checkpoints` and `ingestion_runs`.
   - Multi-tier precedence guard in PostgreSQL upsert:
     $$\text{Alpaca SIP (4)} > \text{Angel One / Alpaca IEX (3)} > \text{YFinance (2)} > \text{Synthetic (1)}$$
   - Lower-quality fallback data is strictly prevented from overwriting primary broker data.
5. **Data Provenance & Survivorship Bias Limitations:**
   - All US Alpaca data is explicitly labeled `alpaca_iex` (documenting ~2.5% US tape coverage).
   - Because the 105-symbol universe uses current constituents, survivorship bias is explicitly disclosed in API responses, logs, and frontend dashboards until point-in-time constituent reconstruction is available.

### 12.9 Independent Historical Data Quality Audit (Phase 3 Verified 2026-11-05)
1. **Reconciliation Invariant:**
   - Database total: 141,038 bars (138,754 in 105-symbol universe, 2,284 in 9 index benchmarks/ad-hoc testing symbols).
   - 67 orphaned synthetic holiday fixtures purged from `bars_daily`.
   - Zero duplicate `(symbol, date)` records; zero price envelope violations.
2. **Provider Split Alignment Invariant:**
   - Angel One SmartAPI and Alpaca IEX retroactively adjust historical candles for splits and bonuses.
   - `apply_verified_corporate_actions` inspects boundary ratio ($C_{pre}/C_{post}$) across ex-dates to prevent double adjustment when the feed is already split-adjusted.
   - Zero artificial split discontinuities (>40% drop) across all 105 universe symbols over the full 5-year lookback.
3. **Calendar Completeness:**
   - Official holidays expanded for NSE and US (Ganesh Chaturthi, Guru Nanak Jayanti, 2026 holidays, US President Carter National Day of Mourning).
   - 19 US symbols exhibit 2 missing sessions solely due to zero volume prints on the Alpaca IEX tape.

---

## 13. PAPER TRADING MODE

- Every signal that reaches TRIGGERED, and every would-be signal from shadow-mode setups (e.g. experimental Setup P), is also tracked as a PAPER position using the same fill rules as the backtest. This runs automatically so there is evidence even on days the owner does not trade.
- Dashboard compares **paper results vs backtest expectations** (expectancy, win rate, slippage observed). Recommend at least **6-8 weeks / 20+ trades** of paper results consistent with the backtest before going live with small size.
- Live trades entered by the owner are stored separately (`mode=LIVE`) and compared against paper to measure execution slippage and discipline (e.g. "trades taken that were not signals").

---

## 14. NOTIFICATIONS

- **Telegram bot** (free): env `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`. Message types: EOD plan summary, BUY trigger, SELL/stop/target, CANCEL/SKIP, NEWS warning, DATA/SYSTEM warning. Keep messages short with the key numbers and top 2 reasons; include a link to the signal page (if the app is reachable).
- Dispatcher with de-duplication, quiet hours (per market), and rate limiting. Failure to deliver must not crash jobs; log and retry with backoff.
- Optional: email via SMTP (free provider) behind a flag. In-app SSE alerts always on.

---

## 15. FREE BACKGROUND HOSTING OPTIONS (pick one; verify current free-tier terms before relying on any)

| Option | How | Notes |
|---|---|---|
| **A. Owner's own always-on PC / laptop / Raspberry Pi** | `docker compose up -d`, auto-start on boot | Most reliable and truly free. Needs the machine on during market hours. Use Tailscale (free tier) for private phone access. |
| **B. Free cloud VM (e.g. Oracle Cloud "Always Free")** | Run the same docker-compose on a small VM; reverse proxy (Caddy) + HTTPS; protect with `APP_TOKEN` and ideally Tailscale | Availability/capacity varies by region and account; confirm before committing. |
| **C. Split mode (zero server)** | GitHub Actions scheduled workflow runs the **EOD refresh + scan**, writes `plan.json` into the repo / a static site, and sends Telegram; React app is built as a static site (GitHub Pages / Cloudflare Pages) that reads `plan.json` | Scheduled workflows can run late and are not suitable for minute-level monitoring; intraday alerts would be unreliable. Never commit secrets: use repository secrets. Free-minute limits depend on repo visibility; **do not make a public repo containing personal positions**. |

Recommended: **A or B** for the full app (live monitor), optionally **C** as a backup that still delivers the evening plan if the main machine is down.
Provide: `Dockerfile` for backend, `Dockerfile` for frontend (nginx static) or serve the built frontend from FastAPI, `docker-compose.yml`, a `make` or `justfile` with `dev`, `test`, `scan-now`, `backtest` targets, and a README with step-by-step setup including creating the Telegram bot and (optionally) the Angel One API app.

---

## 16. CONFIGURATION (`config/strategy.yaml`, defaults)

```yaml
markets:
  IN:
    enabled: true
    currency: INR
    capital: 17500
    index_symbol: "^NSEI"
    universe: ["NIFTY100", "NIFTYMIDCAP150"]
    min_avg_traded_value: 100000000      # 10 crore INR
    min_price: 50
    tick: 0.05
    data_providers: ["angelone", "yfinance"]   # first available wins; falls back automatically
    max_open_positions: 2
    risk_per_trade_pct: 0.5
    max_portfolio_heat_pct: 2
    small_account_mode:               # explicit opt-in, higher risk
      enabled: false
      risk_per_trade_pct: 1.5
      max_portfolio_heat_pct: 3
    slippage_pct: 0.10
  US:
    enabled: true
    currency: USD                          # CONFIRM with owner
    capital: 17500
    index_symbol: "^GSPC"
    universe: ["SP500", "SP400"]
    min_avg_traded_value: 20000000
    min_price: 10
    tick: 0.01
    data_providers: ["alpaca", "yfinance"]   # alpaca = default real-time candidate: CONFIRM with owner
    max_open_positions: 4
    risk_per_trade_pct: 0.5
    max_portfolio_heat_pct: 2
    slippage_pct: 0.05

risk:                               # fallbacks; per-market values above override
  risk_per_trade_pct: 1.0
  max_position_pct: 33
  max_portfolio_heat_pct: 2
  max_per_sector: 1
  corr_threshold: 0.75
  daily_new_trades_max: 2
  max_atr_pct: 6.0
  max_share_price_pct_of_capital: 25
  max_cost_in_R: 0.25


regime:
  block_new_entries: true
  caution_size_mult: 0.5

screen:
  rs_lookback_days: 126
  rs_min_rank: 0.70
  top_n_per_market: 6
  valid_sessions: 1

pullback:                           # Setup P: EXPERIMENTAL
  enabled: false                    # no live alerts until validated out-of-sample
  shadow_mode: true                 # still logs would-be signals + paper results
  ema_len: 20
  touch_tolerance: 1.01
  rsi_len: 14
  rsi_dip_below: 45
  swing_low_bars: 7
  trigger_atr_buffer: 0.1
  stop_atr_buffer: 0.2
  min_risk_atr: 1.0
  max_risk_atr: 3.0
  min_pullback_from_high55: 0.03

trend_template:
  sma_fast: 50
  sma_mid: 150
  sma_slow: 200
  sma200_rising_bars: 21
  min_above_52w_low: 1.30
  max_below_52w_high: 0.25          # within 25% of 52-week high
  prefer_below_52w_high_v: 0.15
  rs_blend: [0.5, 0.5]              # ret63, ret126 weights
  extension_ret21_max: 0.30
  max_above_sma50: 1.25

vcp:                                # Setup V
  enabled: true
  base_min_bars: 15
  base_max_bars: 40
  max_base_depth_pct: 20
  atr_contraction_ratio: 0.85
  min_contractions: 2
  tight_5d_pct: 5
  volume_dryup_ratio: 0.9
  pivot_proximity_pct: 3
  approach_pct: 1.5
  trigger_atr_buffer: 0.1
  entry_zone_atr: 0.5
  stop_bars: 10
  stop_atr_buffer: 0.2
  min_risk_atr: 1.0
  max_risk_atr: 2.5
  max_stop_pct: 8
  min_rr_to_resistance: 1.5
  volume_pace_min: 1.5
  confirm_timeframe_min: 15
  require_contraction: true          # false = simple 55-day-high baseline for ablation
  chase_limit_atr: 1.0


exits:
  breakeven_at_R: 1.0
  trail_atr_mult: 3.0
  partial_at_R: 2.0
  partial_fraction: 0.5
  trend_break_sma: 50
  time_stop_sessions: 15
  time_stop_min_R: 0.5

news:
  earnings_block_days: 7
  earnings_warn_trading_days: 2
  block_on_red: true
  unknown_policy: warn              # warn | block : UNKNOWN is never treated as CLEAR
  dedupe_window_hours: 48
  max_source_age_min: 60            # a source not refreshed within this window makes coverage UNKNOWN
  macro_event_caution: true
  ai_summaries:
    enabled: false                  # optional, off by default; never creates signals
    monthly_budget_usd: 0

monitor:
  mode: websocket                   # websocket | polling (polling = fallback)
  polling_interval_sec: 30
  heartbeat_timeout_sec: 30
  reconnect_backoff_sec: [1, 2, 5, 10, 30]
  freshness:
    websocket_tick_max_age_sec: 20
    rest_quote_max_age_sec: 60
    persistent_stale_alert_sec: 120
    clock_skew_warn_sec: 2
    delayed_feed_policy: informational_only   # delayed feeds never fire trigger alerts

costs:                 # VERIFY against the owner's broker; these are editable presets
  IN:
    preset: zerodha                    # owner places orders on Zerodha; alternatives: angelone (brokerage = lower of 20 or 0.1%, min 5; DP 20)
    brokerage: {type: "flat", flat: 0} # Zerodha delivery brokerage is typically zero: VERIFY
    stt_pct_buy: 0.1
    stt_pct_sell: 0.1
    exchange_txn_pct: 0.003
    sebi_per_crore: 10
    stamp_buy_pct: 0.015
    dp_flat_per_scrip_sell: 13.5       # plus GST via gst_pct; sources differ (13.5 + GST vs ~15.34 total): VERIFY on Zerodha's charges page
    gst_pct: 18
  US:
    commission_per_order: 0
    regulatory_pct: 0.003
    fx_spread_pct: 0.5                  # if funding from India; owner-specific
    fixed_per_trade: 0

tax:
  enabled: false

portfolio:
  provider: kite_personal            # read-only
  sync_interval_min: 5
  capital_source: manual             # manual | kite_cash
  swing_capital_cap: 17500
  auto_track_unmatched_holdings: false
  import_zerodha_csv: true          # tradebook / P&L / charges report import

budget:
  monthly_us_market_data_usd: 0
  monthly_news_data_usd: 0
```

---

## 17. TESTING REQUIREMENTS

- **Indicators:** SMA/EMA/RSI(Wilder)/ATR(Wilder) match reference values from a trusted library on fixed fixtures.
- **No look-ahead test (mandatory):** for 50 random dates, compute signals using full history, then recompute using history truncated at that date; results for that date must be identical.
- **Fill-rule tests:** gap-up above trigger fills at open; gap-down through stop fills at open; same-bar stop+target resolves to the stop.
- **Cost model tests:** hand-calculated examples for India and US round trips; cost gate rejects/accepts correctly at the boundary.
- **Sizing tests:** respects risk %, position cap, heat, sector limit, whole-share rounding.
- **Provider tests:** mocked responses; fallback switching; staleness detection; validation catches bad candles.
- **News tests:** keyword classifier against sample titles; earnings blackout date arithmetic; de-duplication.
- **Scheduler tests:** holiday skipping, DST changes, catch-up on startup, idempotency (running a job twice creates no duplicates).
- **API tests:** schema validation, auth, error envelope.
- **Frontend:** component tests for signal card and position calculators; Playwright smoke test of Dashboard -> Signal detail -> "I took this trade" -> Positions -> "Record exit" -> Journal.
- CI (GitHub Actions): `ruff`, `mypy`, `pytest`, frontend `tsc`, `eslint`, build.

---

## 18. MILESTONES (build in this order; stop and verify at each)
**Core-integration override:** Angel One (milestone 9, including the WebSocket monitor of Section 6.5) and Zerodha read-only sync (milestone 9b) are **core requirements, not optional extras**. Build them immediately after milestone 2 (engine core), before the UI, using recorded fixtures or mocks if credentials are not ready. yfinance is the fallback/research provider only. Launch with **one active setup (Setup V)**; Setup P stays in shadow mode.

1. **Foundation**: repo, config loader, DB + migrations, exchange calendars, provider interface, `YFinanceProvider`, bar storage and validation. *Done when:* 250 symbols' daily history loads, caches, and validation warnings display in `/health`.
2. **Engine core**: indicators, regime, universe filters, screener, both setups, exits, gap risk. Port logic from `swing_signals.py`. *Done when:* CLI `scan --market IN` prints a ranked plan with reasons and the no-look-ahead test passes.
3. **Risk and costs**: sizing, portfolio limits, `CostModel`, cost gate. *Done when:* cost tests pass and small-capital examples show reasons for rejection.
4. **Backtester**: simulator with fill rules, metrics, walk-forward, Monte Carlo, acceptance-gate report. *Done when:* each setup (and the ablation baselines) runs separately and combined, and a 5+ year run produces a report with all gate checks displayed (pass or fail honestly).
5. **API + persistence**: all routes in Section 9, auth, SSE. *Done when:* OpenAPI docs show all routes and API tests pass.
6. **Scheduler + monitor + alerts + Telegram**: jobs from Section 10, de-duplicated alerts. *Done when:* a simulated trigger crossing sends exactly one Telegram message and one SSE event.
7. **React UI**: Dashboard, Signal detail with chart, Watchlist, Positions, Journal, Settings, System. *Done when:* the Playwright smoke test passes on desktop and a 390px-wide mobile viewport.
8. **News/events layer**: India announcements/results/board meetings, US earnings/EDGAR, classifier, blackout, UI panel. *Done when:* a held symbol with a RED announcement raises an alert and a symbol with results in 3 days is blocked.
9. **Angel One provider (CORE and mandatory for India; includes WebSocket monitoring)**: login with TOTP, daily candles, live LTP, instrument-token mapping, rate limiting, fallback to yfinance. *Done when:* weekly cross-check shows < 0.5% deviation on sampled closes.
9b. **Zerodha Kite read-only portfolio sync (CORE)** with live valuation (Section 6.6) and optional CSV report import: daily login flow, token-expiry handling, read-only client, reconciliation rules, untracked-holdings list, and the CI test that forbids order calls. *Done when:* a mocked Kite session syncs holdings/positions, a simulated BUY links to a signal, a SELL closes it into the journal, and the "no order endpoints" test passes.
10. **Paper mode + comparison views**, PWA install, backups, Docker packaging, README, optional GitHub Actions split mode.
11. **Hardening**: logging, error budgets, load test of the scan on a 500-symbol universe (< 3 minutes), security review of secrets and auth.

---

## 19. SECURITY, COMPLIANCE AND DISCLAIMERS

- Single-user app: bearer token auth, CORS restricted, HTTPS when exposed; prefer private access (Tailscale / local network). Never expose positions publicly.
- Secrets only in `.env` or the host's secret store; redact them in logs; Settings page shows only "configured / not configured".
- Respect data-source terms: use official or documented endpoints where possible, keep request volumes low, cache, and identify yourself correctly (e.g. SEC `User-Agent`). Unofficial NSE/BSE/Yahoo endpoints may change or block; the app must keep working in a degraded mode with clear warnings.
- This software is a **decision-support tool**, not investment advice, and the owner is solely responsible for trades. It is not a SEBI/SEC-registered advisory service; do not share signals publicly or commercially without checking the applicable regulations.
- Every report and backtest page carries the warning: backtested results are hypothetical, assume imperfect data, and do not guarantee future performance.

---

## 20. DEFINITION OF DONE (WHOLE PROJECT)

- Evening scan produces, for IN and US, a ranked plan with reasons, trigger, stop, target, quantity, cost-in-R and news flags, delivered to Telegram and the dashboard.
- During market hours the monitor sends de-duplicated BUY / SELL / CANCEL / NEWS alerts using fresh quotes only.
- The owner can record trades, see live position status and trailing-stop instructions, and review a journal with R-multiple analytics.
- The backtester runs the exact live logic with conservative fills and full costs, reports honest acceptance gates, and flags survivorship bias.
- Paper mode accumulates evidence automatically, including shadow-mode results for experimental setups.
- Live valuation shows broker-reported and calculated values with sources and timestamps.
- News coverage is explicit (CLEAR / REVIEW / BLOCKED / UNKNOWN) and missing data is never treated as clear.
- Trigger alerts come only from fresh real-time feeds.
- All tests pass; the app runs from `docker compose up` on a free host with a documented setup.

---

## 21. CHANGE LOG (v2) AND RESEARCH NOTES

**Adopted from the second research pass:** Minervini-style trend template with 52-week-high/low proximity and relative strength against the index; VCP/tight-base breakout as the primary candidate setup; signal state machine (Watchlist, Approaching, Triggered, Invalidated); explicit entry zone and "do not chase" rule; 15-minute provisional confirmation plus daily-close confirmation; correlation-cluster limit; conservative US risk of 0.5% with limited open risk; expectancy formula; official-source-first news (NSE announcements/RSS, SEC EDGAR); Alpaca/IBKR as optional US data sources; signal-only scope to avoid broker order-API and retail-algo compliance issues.

**Changed or rejected, and why:**
- **Setup choice is decided by data, not belief.** Both Setup V and Setup P are tested separately and combined; the Reddit-derived ideas are anecdotes and self-reported results (including a claimed high-return trader who also disclosed large earlier losses), not evidence.
- **Overextension guard instead of a raw "top 30% monthly gainers" filter.**
- **India risk per trade is higher than the US default** because fixed delivery charges make 0.5% unworkable on a ~INR 17,500 account (Section 4.3). If the owner dislikes that risk level, run India in paper mode until capital is larger.
- **Intraday confirmation cannot be fully backtested with free data** (Section 12.5); it is validated in paper/forward testing.
- **Database:** Neon PostgreSQL from day one. Built directly for the intended production PostgreSQL environment with connection pooling, serverless pre-ping/reconnect handling, and Alembic migrations. SQLite support and dual database adapters are explicitly excluded.
- **Paid data/news subscriptions are deferred** until the owner's US broker and actual needs are confirmed.
- **Regulatory note:** retail algorithmic-trading rules and broker API conditions (including static-IP and order-tagging requirements for API order placement) have been changing; the app is signal-only and never calls order APIs. Re-verify the broker's current API terms before using its market-data API.

**v2.1 (broker roles):** India market data from Angel One SmartAPI (historical candles, live quotes, WebSocket) with yfinance fallback; India account data from the free Zerodha Kite Connect Personal tier, strictly read-only (holdings, positions, funds, trades), with a daily manual login because the access token expires each day. The India cost preset now assumes Zerodha for execution; confirm current charges because published figures differ. Kite Personal has no historical or live-quote APIs, so it is never a price source.

**v2.2 (review corrections):** Angel One and Zerodha promoted to core integrations; yfinance demoted to fallback; WebSocket monitoring with strict freshness limits replaces 5-minute polling (the old 20-minute stale threshold was far too loose for breakouts); explicit news timestamps, de-duplication and coverage statuses with UNKNOWN never treated as clear; licensed-news and optional AI-summary extension points with guardrails; live valuation with source provenance; Zerodha CSV import supported from v1; Setup V is the only live setup at launch with Setup P in shadow mode; risk baseline returned to a conservative 0.5% per trade and 2% open risk for both markets, with a higher-risk India "small-account mode" only as an explicit opt-in; unconfirmed decisions (capital, US provider, budgets) kept configurable.

**v2.4 (Neon PostgreSQL Mandate):** Neon PostgreSQL is established as the sole application database from the beginning. No SQLite support, no secondary adapters, and no migration paths from SQLite. All models standardized with `TIMESTAMPTZ`, Alembic handles reviewed migrations, connection pooling is configured with `QueuePool` and `pool_pre_ping=True` for Neon serverless wakeups, and test suites utilize isolated rollback fixtures to guarantee actual trading records are never deleted or modified.

---

## 22. RESEARCH DESK AND FUNDAMENTAL LIGHTS IMPLEMENTATION ADDENDUM

The current implementation adds the following without changing existing technical thresholds:

- Every production `/api` route requires the `APP_TOKEN` bearer credential. Render sets `ENV=production`, generates the token, and runs Alembic migrations before FastAPI starts. Health probe routes remain public.
- Signal list responses include the persisted decision audit stages and a structured first blocked check. The dashboard and signal cards render the stage, check, measured value, threshold and note.
- `vcp.pivot_excludes_signal_day` defaults to `false`. When explicitly enabled, the candidate pivot excludes the signal bar and a qualifying close at/above the prior pivot is labeled `BROKE_OUT_TODAY`; it is not presented as a fresh near-pivot setup. Do not enable the default without owner review of paired counts and backtest results.
- The evening plan has a separate `PRE_BREAKOUT_WATCHLIST` tier for valid VCP bases below the pivot with the existing technical checks and calculated plan. Intraday APPROACHING monitoring remains as implemented.
- `/api/research/pivot-impact` compares both pivot policies using the same stored daily bars, universe slice, cost model and backtest window. `/api/research/lead-time` compares stored 55-day breakout events with first retained Scanner + Setup Validator pass audits; it reports audit coverage caveats.
- `config/fundamentals.yaml` holds heuristic thresholds and defaults to `warn`. The traffic-light evaluator labels yfinance unofficial/incomplete and returns UNKNOWN for missing values. A user-initiated normalized CSV import is available. Snapshots are attached to signals, surfaced in the Fundamentalist role, and reported against forward journal outcomes. `block_on_red` is explicit opt-in; `warn` records a review reason without changing trigger, stop or size.
- The dashboard Research Desk presents the ten roles in the order defined by `DESIGN.md`, with stage stepper, role chips, template cases, Judge checklist strength and state legend. Value Radar returns research-only ideas from stored snapshots and routes no trades around the existing pipeline.
- Charts retain lightweight-charts, local drawing persistence, and now include Fibonacci retracement/extension lines, a TradingView link and visual-only Pine export.

Known limitations: historical scan signals are not retained for every session, so lead-time estimates can undercount earlier scanner flags. yfinance does not consistently provide sector-median valuation, promoter pledge/holding history, reliably consolidated filings or point-in-time restatements. The fundamental lights are informational heuristics, not validated. Intraday historical depth and accuracy remain insufficient for multi-year 1H/4H backtests. Gemini summarization, ABCD and automated Fibonacci-pullback strategies, holdout-based candidate selection and the full Strategy Lab protocol remain separate work; Fibonacci chart drawings are manual only. Free-tier AI limits and terms must be verified before enabling Gemini. The connected Neon database inspected during implementation did not yet contain `signals.fundamentals_json`; apply Alembic migration `003` before using snapshot-backed fundamentals routes.

### 22.1 Stored-data reproduction snapshot (2026-11-05)

- The India research window covered 60 stored market sessions, 2026-08-14 through 2026-11-05, on the same 30-symbol slice for both pivot policies. Each policy produced 1 candidate session and 0 `BROKE_OUT_TODAY` classifications. Both backtests produced 0 trades, so the paired result is inconclusive and shows no measured performance difference. The signal-day-excluded flag remains off.
- The lead-time calculation found 38 stored 55-day breakout events in the India universe, with 100% lacking an earlier retained Scanner + Setup Validator pass audit. This is an audit-retention coverage result, not proof the scanner never flagged those stocks: stored qualifying passes are concentrated on 2026-11-02 through 2026-11-04.
- Grasim has 60 daily bars from 2026-08-10 through 2026-11-04, but only four retained India scan sessions (2026-11-02 through 2026-11-05). Its retained 2026-11-05 signal is a blocked PULLBACK. The first retained failure is Scanner / Market Regime (`WEAK` vs `BULLISH or CAUTION`); the setup stage also records two trend-template failures. This cannot reconstruct the requested 60-session setup-stage history or confirm a prior VCP breakout from retained records.

### 22.2 Backtest accounting review and rerun (2026-11-05)

- Corrected metric accounting: expectancy now averages the already-net trade R values once; net profit factor is labelled as after-cost; cost drag uses pre-cost gross winning P&L and fails as N/A when there is no gross profit; drawdown duration is date-derived rather than a constant.
- Corrected simulation accounting: slippage is represented by adverse fills and excluded from the second fee deduction; pending orders count against position and heat limits; remaining positions are marked to market daily and liquidated at the end of the test. Acceptance thresholds and setup thresholds were not changed.
- Read-only rerun used the top 30 current India universe symbols and 290 stored sessions (2025-09-29 through 2026-11-05), not the requested two years. After slippage, next-open exit, partial-profit and daily mark-to-market fixes, Setup V: 3 trades, -200.40 net P&L, -0.78R expectancy, 0.00 net PF, 3,378.0% cost drag; Setup P: 19 trades, -320.58, -0.27R, 0.51 net PF, 81.9% cost drag; combined: 18 trades, -337.95, -0.33R, 0.38 net PF, 105.1% cost drag. All three fail the acceptance gates. Results are still too sparse and the universe is survivorship-biased; none is eligible to be called a solid/profitable strategy.
- Further engine gaps remain: trend-break and time-stop exits trigger at the following session's open, and the configured partial-profit fraction is now realized and aggregated into the position trade; historical regime/earnings gates and point-in-time constituents are unavailable; buy-and-hold/random-entry controls and an untouched holdout are not yet wired into Strategy Lab. Do not tune thresholds to rescue these samples.


---

## 23. FULL-NSE UNIVERSE COVERAGE, RESEARCH FUNNEL, FUNDAMENTAL SNAPSHOTS & VALUE RADAR (2026-11-06)

This addendum documents the operational enhancement for full-NSE universe scanning, transparent funnel metrics, structured fundamental snapshot storage, and the Value Radar engine. In strict accordance with the non-negotiable rules, **no strategy rules, technical thresholds, regime logic, or risk gates were modified**, and **no order placement capability was introduced**.

### 23.1 Universe: Angel One Instrument Master Ingestion
- **Master Scrip Ingestion:** Ingests official Angel One instrument master (`data/cache/angelone/instrument_master.json`, 2,745 NSE equity items).
- **Compliant Free Filter:** Series `-EQ` selected by default. Filters out SME/surveillance series (`-BE`, `-SM`, `-ST`, `-BZ`) and non-equity instruments (ETFs matching `*BEES*`, `*ETF*`, `*GSEC*`, `*INVIT*`, `*REIT*`, Gold bonds). Resulting non-ETF eligible candidate universe: 2,636 NSE equities.
- **Tiers & Risk Classification:** Instruments are tiered as `Large`, `Mid`, or `Small` based on index constituents and 20-day ADV. Stocks in the `Small` tier are tagged `is_higher_risk = True` and excluded from primary live BUY signals unless explicitly enabled in Settings.
- **Seven-Stage Coverage Audit:** Visible in the Universe Coverage panel and exportable via `/api/universe/coverage/export-csv`:
  `Listed -> Has Data -> Enough History (>=252 bars) -> Liquid (ADV >= 50L) -> Passes Filters -> Scanned`.
  Every instrument receives exactly one status: `SCANNED`, `NO_DATA`, `INSUFFICIENT_HISTORY`, `ILLIQUID`, `PRICE_FLOOR`, `VOLATILITY_CAP`, `SERIES_EXCLUDED`, or `DATA_ERROR`.
- **Corporate Action Integrity Check:** Verification audits (`/api/universe/audit-splits`) detect unadjusted corporate actions (>40% unadjusted price drops around historical split ex-dates) against verified reference circulars.
- **Universe-Wide Relative Strength:** RS rank calculation evaluates relative percentile across the entire scanned liquid universe, not a sub-sample.

### 23.2 Sequential Funnel and Transparent Status Labels
- **Single Monotonic Pipeline:** Funnel counts follow strict sequential evaluation:
  `Scanned >= Trend Template OK >= Valid Setup >= Fundamentals Not RED >= News Not BLOCKED >= Risk OK >= PASS`.
  A later stage can never exceed an earlier stage.
- **Regime Block Disambiguation:** When Market Regime is `WEAK`, rows display the exact distance string:
  `BLOCKED: Regime WEAK (Nifty 23,810.85 below SMA200 24,017.32, -0.86%)`.
  The dashboard tab is labeled `Patterns (blocked by regime)` so blocked setups are never misread as trade ideas. Downstream execution stages that were not reached are marked `NOT EVALUATED`.
- **Strategy Lab Audit Caveat:** Candidates produced by Setup P (EMA Pullback) carry the badge `NO VALIDATED EDGE (Setup P - Task 9156 audit)` to ensure users understand the research desk context.

### 23.3 Fundamental Snapshots Architecture
- **Table `fundamental_snapshots`:** Persisted in Neon PostgreSQL with columns `(symbol, market, as_of, period_end, source, revenue_yoy, profit_yoy, op_margin, roce, roe, debt_equity, interest_coverage, pe, sector_median_pe, promoter_holding, pledge_pct, completeness, traffic_lights_json, updated_at)`.
- **Completeness & Traffic Lights:** Completeness is evaluated as `COMPLETE` (>= 5 primary metrics), `PARTIAL` (1-4 metrics), or `NONE` (0 metrics).
- **Rule of Honest Missing Data:** Missing fundamental metrics evaluate to grey `UNKNOWN`, never green.
- **Weekly Ingestion Job:** Scheduled background job refreshes Large & Mid cap liquid equities weekly via polite yfinance batch caching and manual CSV imports.

### 23.4 Value Radar Engine
- **Cross-Universe Scanning:** Evaluates all scanned universe stocks with fundamental snapshots against value criteria:
  1. Valuation: Green/Yellow vs sector median.
  2. Quality: ROCE/ROE >= Yellow.
  3. Growth: Revenue/Profit YoY not Red.
  4. Technical Stabilizing: Price above 200 SMA or valid base forming.
- **Transparent "Why Zero" Breakdown:** When zero candidates pass, the UI exposes the exact pipeline tally:
  `Total Scanned`, `With Fundamentals`, `No Fundamentals`, `Excluded: Valuation`, `Excluded: Quality`, `Excluded: Growth`, `Excluded: Technical Stabilizing`, `Passed Tier`.
- **Disclaimers:** Every radar idea is tagged `VALUE_RADAR` and labelled "Research idea, not a signal; subject to value trap / cyclical peak risks."
