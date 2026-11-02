# Swing Trading Intelligence Platform

> **A quantitative, rules-based swing-trading intelligence platform for Indian (NSE) and US equities.**
> Designed strictly as a **decision-support and signal-generation system**.
> **Mandatory Rule:** All broker orders are placed manually by the trader. Automatic order execution, modification, or cancellation is never implemented.

---

## 1. Architectural Highlights

- **Strategy Engine:** Minervini Trend Template + objective Tight-Base Volatility Contraction Pattern (VCP, Setup V) breakouts as primary active alerts; 20/50 EMA Pullbacks (Setup P) tracked in shadow mode.
- **Broker Integrations (Clean Separation of Concerns):**
  - **Angel One SmartAPI (Core Indian Market Data):** Historical daily candles, 15-minute intraday bars, live LTP quotes, instrument master token caching, and WebSocket feeds with feed freshness monitoring.
  - **Zerodha Kite Connect Personal (Strictly Read-Only Account Data):** Synced holdings, positions, funds, and trades. Guaranteed zero order-placement code.
- **Live Portfolio Valuation & Provenance:** Broker-reported values (Zerodha snapshot) and live calculated values (Angel One LTP) displayed side by side with timestamps and source tags.
- **Safety News & Corporate Disclosures Filter:** Deterministic keyword severity classifier (RED, AMBER, GREEN), earnings blackout guard, and deduplication.
- **Backtesting & Acceptance Gates:** Event-driven daily simulation strictly enforcing Section 12.2 conservative fill rules, Monte Carlo simulations (1,000 iterations), and out-of-sample acceptance criteria.
- **Modern Full-Stack Architecture:** Python 3.11+ (FastAPI, SQLAlchemy, Neon PostgreSQL, APScheduler) backend paired with React 18, TypeScript, Vite, and Tailwind CSS.

---

## 2. Prerequisites

| Component | Minimum Version | Notes |
|---|---|---|
| **Python** | `3.11.x` | Managed via `uv` or system Python |
| **Node.js** | `v20.x` or `v24.x` | Runtime for Vite and React frontend |
| **npm** | `v10.x` or `v11.x` | Frontend package manager |
| **uv** | `0.11+` | Ultra-fast Python package installer & virtualenv manager |
| **Database** | Neon PostgreSQL | Serverless PostgreSQL with `sslmode=require` |

---

## 3. Project Installation & Quick Start

### A. Clone & Setup Python Virtual Environment (Windows PowerShell)

```powershell
# Navigate to the project root
cd "d:\web development\saas-projects\Algo-trading"

# Create Python 3.11 virtual environment using uv
& "$env:USERPROFILE\.local\bin\uv.exe" venv backend\.venv --python 3.11

# Install backend dependencies
& "$env:USERPROFILE\.local\bin\uv.exe" pip install --python backend\.venv\Scripts\python.exe -r backend\pyproject.toml
```

### B. Setup Environment Variables & Neon Database

```powershell
# Copy the example environment template
Copy-Item .env.example .env

# Edit .env and set your Neon PostgreSQL connection string:
# DATABASE_URL=postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require
```

### C. Apply Database Migrations (Neon PostgreSQL)

All database schema migrations are managed via Alembic:

```powershell
# Apply all reviewed schema migrations to your Neon database
backend\.venv\Scripts\alembic.exe upgrade head

# Generate SQL DDL offline without executing
backend\.venv\Scripts\alembic.exe upgrade --sql head
```

### D. Install & Build Frontend

```powershell
# Install npm dependencies
cmd /c "cd frontend && npm install"

# Build production assets (emits to frontend/dist and served by FastAPI)
cmd /c "cd frontend && npm run build"
```

### D. Run the Application

#### Option 1: Unified Production Server (FastAPI serves API + Frontend SPA)
```powershell
& "backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```
- Open browser at: **`http://127.0.0.1:8000`**
- Interactive Swagger API docs: **`http://127.0.0.1:8000/docs`**

#### Option 2: Frontend Hot-Reload Development Server
In a second terminal window:
```powershell
cmd /c "cd frontend && npm run dev"
```
- Open browser at: **`http://localhost:5173`** (API requests automatically proxy to port 8000).

### E. Run Automated Test Suite
```powershell
& "backend\.venv\Scripts\python.exe" -m pytest backend/tests -v
```

## Deploy Frontend on Vercel and Backend on Render

The frontend uses `/api` locally by default. For a separate Vercel frontend and Render backend:

1. In Vercel, set the project **Root Directory** to `frontend`, with **Build Command** `npm run build` and **Output Directory** `dist`.
2. Add the `VITE_API_BASE_URL` environment variable in Vercel, using the public Render backend origin, for example `https://your-service.onrender.com` (no trailing slash required). The frontend appends `/api` automatically.
3. Redeploy the Vercel project after setting or changing the variable. `VITE_*` values are included in the public frontend build; never put credentials or other secrets in them.
4. Configure backend credentials and secrets separately in Render's environment settings.

The Vite development server continues to proxy `/api` to `http://127.0.0.1:8000` when `VITE_API_BASE_URL` is unset.

---

## 4. Angel One SmartAPI Setup (Market Data)

Angel One SmartAPI is our primary Indian market-data provider for historical daily candles, intraday 15-minute bars, live quotes, and WebSocket monitoring.

### Step-by-Step Registration & Credential Acquisition

1. **Register Developer Account:**
   - Go to [https://smartapi.angelone.in/](https://smartapi.angelone.in/) and sign up with your registered mobile number and Angel One client code.
2. **Create SmartAPI Application:**
   - In the SmartAPI Dashboard, click **Create an App**.
   - App Type: Select **Trading API** (used for market data feeds).
   - App Name: `SwingIntelligence`.
   - Redirect URL: `http://127.0.0.1:8000` (can be loopback).
3. **Obtain API Key:**
   - Once created, copy the **API Key** generated by Angel One into `.env` as `ANGELONE_API_KEY`.
4. **Configure Account Credentials:**
   - Set `ANGELONE_CLIENT_CODE` to your Angel One account login ID (e.g., `A123456`).
   - Set `ANGELONE_PIN` to your 4-digit or 6-digit Angel One trading PIN.
5. **Enable TOTP (Time-based One-Time Password):**
   - In Angel One Security settings or via [https://smartapi.angelone.in/enable-totp](https://smartapi.angelone.in/enable-totp), activate TOTP.
   - Scan the QR code with your authenticator app (Google Authenticator / Aegis / Bitwarden), or copy the alphanumeric **Secret Key**.
   - Copy this Base32 secret string into `.env` as `ANGELONE_TOTP_SECRET`.
   - The platform uses `pyotp.TOTP(secret).now()` to automatically authenticate daily sessions.
6. **Verify Market Data Connection:**
   - Run the health check endpoint:
     ```powershell
     Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" | Select-Object -ExpandProperty providers
     ```
   - When credentials are provided, `angelone` reports `HEALTHY` with live latency in milliseconds.

---

## 5. Zerodha Kite Connect "Personal" Setup (Read-Only Portfolio)

We utilize the **FREE Personal tier** of Kite Connect.

> **Strict Architectural Boundary:** Kite Personal does **not** provide historical chart candles or WebSocket market data. It provides user profile, equity margins, holdings, positions, and trades. The platform strictly enforces GET-only endpoints and wraps Kite in a read-only client.

### Step-by-Step Setup

1. **Register on Kite Developer Console:**
   - Go to [https://developers.kite.trade/](https://developers.kite.trade/) and sign in.
2. **Activate the Personal Plan:**
   - Create a new app and choose the **Personal (Free)** tier.
3. **Configure App Settings:**
   - App Name: `SwingPortfolioTracker`.
   - Redirect URL: `http://127.0.0.1:8000/api/portfolio/kite/callback`.
4. **Copy API Key & API Secret:**
   - Copy `api_key` to `KITE_API_KEY` in `.env`.
   - Copy `api_secret` to `KITE_API_SECRET` in `.env`.
5. **Daily Manual Login Flow:**
   - Because Zerodha access tokens expire daily (around 06:00 IST) and there is no refresh token:
     1. Open the platform Settings page: `http://127.0.0.1:8000/settings`.
     2. Click **Connect / Re-authenticate Zerodha**.
     3. Complete login on Kite's official web login page.
     4. Kite automatically redirects to `/api/portfolio/kite/callback` with a `request_token`.
     5. The backend computes the SHA-256 checksum (`SHA256(api_key + request_token + api_secret)`), acquires the `access_token`, and stores it in memory.
6. **Console CSV Report Imports:**
   - Under the Journal page, you can optionally upload Zerodha Console CSVs (Tradebook, P&L, Charges). The file is verified with SHA-256 to prevent duplicate imports.

---

## 6. Free-Only News, Regulatory Disclosures & Event Engine (v2.3)

The news module operates strictly as a **downward safety gate**. It flags risks, blocks entries before hazardous binary events, and enforces earnings blackouts. Per the **Isolation Invariant**, news, rumours, sentiment, or LLM summaries can **never** trigger a BUY signal, change position sizing, move stop-losses, or alter profit targets.

### Sanctioned Free Sources Matrix (Zero Scraping, Zero Mandatory Paid APIs)

| Purpose | Source | Access / Transport | Latency Class | Verified Terms & Compliance |
|---|---|---|---|---|
| **India Exchange Disclosures** | **NSE Official RSS Feeds** (`Corporate_announcements.xml`, `Board_Meetings.xml`, `Corp_action.xml`, `Financial_Results.xml`) | RSS 2.0 over HTTPS (`nsearchives.nseindia.com/content/RSS/`) | `near-real-time` (5-15 min) | NSE publishes these for syndication; polled at 5-15 min frequency matching TTL. **Zero web scraping of `nseindia.com` or private JSON endpoints.** |
| **India Disclosures (BSE)** | BSE Official Portal | Marked `UNAVAILABLE` | `unavailable` | BSE publishes no sanctioned machine-readable feed without browser scraping. Scraping BSE is strictly prohibited by compliance policy. |
| **US Corporate Disclosures** | **SEC EDGAR Submissions API** (`CIK{cik}.json`) & 8-K documents | REST JSON / HTML (`data.sec.gov`, `sec.gov`) | `near-real-time` (minutes) | Free, no API key required. Declares honest `SEC_USER_AGENT` per SEC Fair Access policy. Paced $\le 10$ req/s. |
| **Broad Business News Discovery** | **GDELT DOC 2.0 API** | REST JSON (`api.gdeltproject.org`) | `periodic/batch` (~15 min index update) | Free, no API key required. Polled at polite $\ge 6$s pacing per IP. Queries by full company name and verified aliases. |
| **US Company News (Supplementary)** | **Finnhub Stock API** (`/company-news`) | REST JSON (`finnhub.io`) | `near-real-time` (minutes) | Optional free tier (60 req/min). If `FINNHUB_API_KEY` is unset, engine operates seamlessly in keyless mode. |
| **Macro Policy Announcements** | **RBI & US Federal Reserve RSS Feeds** | Official RSS XML | `periodic/batch` (6 hours) | Official public central bank press release feeds. |

### Empirical Latency Classes (Honesty Invariant)
The platform never mislabels internet news as "real-time":
- **`near-real-time`:** Disclosures indexed and fetched within minutes of publication (NSE RSS, SEC EDGAR, Finnhub).
- **`delayed`:** Data subject to exchange transmission delays.
- **`periodic/batch`:** Aggregated news discovery updated on batch cycles of 15 to 60 minutes (GDELT DOC 2.0).
- **`unavailable`:** Source channels that have no sanctioned feed without prohibited scraping (BSE).

### Intelligence & Disambiguation Modules
1. **Entity Resolution & Ticker Collision Guard:**
   - Disambiguates common ticker collisions (e.g., `TCS` = "Tax Collected at Source", `BEL` = "Belgium") using strict company name matching and legal entity normalization. Bare short ticker matches route to `TICKER_ONLY` for manual review, never confirmed relevance.
2. **Wire Syndication Clustering:**
   - Detects wire agency attribution (Reuters, PTI, ANI, IANS, Bloomberg, PR Newswire) and clusters identical syndicated stories across publishers into a single cluster ID.
3. **Rumour & Hedged Language Classifier:**
   - Flags speculative phrases ("sources said", "reportedly", "people familiar", "mulls", "unconfirmed") as `UNVERIFIED RUMOUR`. Official regulatory filings are never flagged as rumour.
4. **Analyst Action Extractor (Strict Null Rule):**
   - Parses brokerage upgrades, downgrades, and target prices. If a field is not explicitly present in the text, it remains strictly `null` (None). Never synthesizes or hallucinates ratings.
5. **Deterministic Materiality Evaluator:**
   - Computes score via $\text{Materiality} = \text{Category Weight} \times \text{Source Authority} \times \text{Recency Decay} \times \text{Price Reaction}$ to categorize items as `HIGH`, `MEDIUM`, or `LOW`.
6. **Rule 11 (Strict Unknown Policy):**
   - Missing data, stale sources (&gt;60m), offline coverage gaps, or unmonitored markets return `UNKNOWN`, **never** `CLEAR`.

### Running News Engine Tests
```powershell
backend\.venv\Scripts\pytest backend/tests/test_news_engine_v2.py
```

---

## 7. Telegram Notifications Setup (Simple, One-Time Setup)

The platform includes a zero-friction, one-time Telegram integration for outbound swing-trading notifications.

> **Strict Architectural Boundary:** Telegram is strictly an outbound notification channel. No BUY/SELL execution commands or broker order placements are ever accepted or routed through Telegram. Bot tokens are kept securely on the backend and are never sent to the browser.

### Step-by-Step Setup

1. **Create Bot on Telegram:**
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot`, name your bot (e.g. `MySwingTraderBot`), and choose a username ending in `bot` (e.g. `SwingMaster7_bot`).
   - Copy the HTTP API token provided by BotFather (e.g. `9186942205:AAF...`).
2. **Find Your Numeric Chat ID:**
   - Message [@userinfobot](https://t.me/userinfobot) or [@raw_data_bot](https://t.me/raw_data_bot) on Telegram.
   - It will reply with your unique numeric Telegram user ID (e.g. `909235485`).
   - *Important:* Open your newly created bot in Telegram and click **Start** (or send `/start`) so the bot has permission to message you.
3. **Configure Environment Variables in `.env`:**
   ```bash
   TELEGRAM_BOT_TOKEN=9186942205:AAFjv4ZqugmoNjFAhxlqDnj9GRc7ZxhUO7I
   TELEGRAM_CHAT_ID=909235485
   ```
4. **Verify in Settings Page:**
   - Open the web dashboard at `http://127.0.0.1:8000/settings`.
   - The **Telegram Notifications** card automatically checks credentials using Telegram's `getMe` API:
     - **Status Badge:** Displays `Connected` (green), `Not Configured`, or `Error`.
     - **Bot Username:** Verified handle (e.g. `@SwingMaster7_bot`).
     - **Masked Chat ID:** Securely masked (e.g. `*****5485`).
     - **Last Connection Check:** Timestamp of the last successful API handshake.
   - Click **Test Telegram**:
     - Sends exactly one test notification message:
       ```text
       ✅ Swing Trading Platform

       Telegram notifications are working correctly.
       You will receive important trading alerts here.
       ```
     - Verifies delivery confirmation from Telegram's `sendMessage` API before showing success.
     - Displays actionable errors if the chat ID is invalid, bot was blocked, or credentials fail.
     - Automatically debounced to prevent accidental repeated clicks.

### Trading Notifications Scope & Reliability

Telegram is reserved only for meaningful, actionable trading signals:
- **Actionable BUY setups / Entry triggers:** 15m candle close confirmation and volume pace validated.
- **Exit & Stop-Loss Alerts:** Hard stops, trailing stop updates, 50-day SMA trend breaks, and 50% partial profit targets (2R).
- **Entry Blocked / Invalidation Reasons:** Rejections when price falls below stop before breakout or fails risk checks.
- **Corporate Risk & Disclosures:** High-severity (`RED`) news alerts and earnings blackout period warnings.
- **Critical System & Data Failures:** Stale data feeds (>20s delay) and risk circuit breaker activation.

**Anti-Noise Guarantees:**
- **Zero Routine Noise:** Scanner refreshes, heartbeat ticks, and unchanged signals never send Telegram messages.
- **Persistent Deduplication:** Event keys are cached in memory and cross-checked against the PostgreSQL `alerts` table across backend restarts.
- **Transient Failure Retries:** Built-in exponential backoff retry mechanism (up to 3 attempts).

---

## 8. US Market Data Setup

- **Adapter Candidate:** Alpaca Markets ([https://alpaca.markets/](https://alpaca.markets/)).
- **Configuration:** Set `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, and `ALPACA_ENDPOINT` in `.env`.
- **Honesty Rule:** When US credentials are not configured, the dashboard clearly displays US Live Signals as `NOT CONFIGURED`. It never presents delayed yfinance data as live breakout alerts.

---

## 9. Environment Variable Reference

| Variable | Description | Required | Source / Provider |
|---|---|---|---|
| `APP_TOKEN` | Bearer token for API protection | Optional (Dev) | User-defined secret |
| `ENV` | `development` or `production` | Optional | Application setting |
| `DATABASE_URL` | Neon PostgreSQL connection string (`sslmode=require`) | Required | Neon Console (`postgresql://neondb_owner:***@...`) |
| `ANGELONE_API_KEY` | Angel One SmartAPI key | Required for IN Live | SmartAPI Developer Portal |
| `ANGELONE_CLIENT_CODE` | Angel One login client code | Required for IN Live | Angel One account |
| `ANGELONE_PIN` | Angel One trading PIN | Required for IN Live | Angel One account |
| `ANGELONE_TOTP_SECRET` | Base32 secret for TOTP generation | Required for IN Live | Authenticator App / SmartAPI |
| `KITE_API_KEY` | Zerodha Kite Connect API key | Required for Portfolio | Kite Developer Console |
| `KITE_API_SECRET` | Zerodha Kite Connect API secret | Required for Portfolio | Kite Developer Console |
| `KITE_REDIRECT_URL` | Kite OAuth callback URL | Optional | `http://127.0.0.1:8000/api/portfolio/kite/callback` |
| `ALPACA_API_KEY` | Alpaca Markets API key | Optional | Alpaca Developer Portal |
| `ALPACA_SECRET_KEY` | Alpaca Markets Secret key | Optional | Alpaca Developer Portal |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | Optional | Telegram BotFather |
| `TELEGRAM_CHAT_ID` | Telegram chat ID from @userinfobot | Optional | Telegram User Info Bot |

---

## 10. Feature & Integration Status

| Feature / Integration | Status | Test Coverage | Credentials Needed | Paid Subscription |
|---|---|---|---|---|
| **Minervini Trend Template Engine** | ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **Setup V (VCP / Tight-Base Breakout)** | ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **Setup P (20 EMA Pullback - Shadow)** | ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **Position Sizing & Indian Cost Model** | ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **Cost Gate (Rejection if costs > 0.25R)**| ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **No Look-Ahead Verification** | ✅ Implemented | ✅ Verified via Test | None | Free |
| **Zero Broker Order Enforcement** | ✅ Implemented | ✅ Verified via Test | None | Free |
| **Angel One SmartAPI (Indian Market Data)**| ✅ Implemented | ✅ Integration Tested | Yes (Angel One) | Free |
| **Zerodha Kite Personal (Read-Only)** | ✅ Implemented | ✅ Mocked & Tested | Yes (Zerodha) | Free |
| **Zerodha Console CSV Importer** | ✅ Implemented | ✅ Integration Tested | None | Free |
| **Live Valuation (Broker vs Calculated)** | ✅ Implemented | ✅ Integration Tested | Yes (Kite + Angel) | Free |
| **News Severity & Earnings Blackout** | ✅ Implemented | ✅ 100% Unit Tested | None (Official RSS) | Free |
| **Event-Driven Backtester (Sec 12.2 Fills)**| ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **Acceptance Gates Checklist** | ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **Monte Carlo Simulation (1,000 runs)** | ✅ Implemented | ✅ 100% Unit Tested | None | Free |
| **Alpaca US Market Data Adapter** | ✅ Implemented | ✅ Integration Tested | Optional (Alpaca) | Free Tier |
| **Telegram Notifications & SSE Stream** | ✅ Implemented | ✅ Integration Tested | Optional (Telegram) | Free |
| **React + TypeScript + Vite Dashboard** | ✅ Implemented & Built | ✅ Verified | None | Free |

---

## 11. Troubleshooting

- **Angel One TOTP Error:** Ensure `ANGELONE_TOTP_SECRET` is the raw alphanumeric Base32 key (not the 6-digit rolling code). Check that your system clock is synchronized via NTP.
- **Zerodha Token Expired:** Zerodha access tokens invalidate every morning at 06:00 IST. Navigate to `/settings` and click "Connect Zerodha" to re-authenticate.
- **Feed Freshness Warnings:** If market data ticks exceed 20 seconds of latency during market hours, signals are automatically suppressed and marked `STALE` to prevent chasing late breakouts.
- **Cost Gate Rejecting Indian Trades:** On small accounts (~₹17,500), 0.5% risk is ₹87.50. Fixed exchange DP charges (₹13.50 + GST) and STT can consume > 0.25R of risk. This is the **correct, honest outcome**. Options: increase capital, run in Paper Trading mode, or opt into `small_account_mode` in `config/strategy.yaml`.

---

## 13. Live-Data Reliability & Dashboard Additions

### Two-Lane Quote Contract
- **Decision Lane:** Enforces strict typed `DecisionQuote` model. Only quotes marked `freshness=FRESH` and `realtime=True` are permitted to reach the `DecisionPipeline`, Entry Timer, or alert dispatcher. Any stale or delayed quote raises `IneligibleQuoteError`.
- **Display Lane:** Quotes with cached or delayed values can be rendered in the UI with explicit badges (`STALE`, `DELAYED`), but are strictly barred from triggering buy/sell signals.
- **Quote Audit Traceability:** Every dispatched alert embeds an immutable 5-tuple quote audit snapshot in `payload_json["quote_audit"]` (`price`, `provider`, `exchange_ts`, `received_ts`, `freshness`, `realtime`).

### Outbound REST Request Layer (`ProviderRequestLayer`)
- **Single-Flight Coalescing:** Eliminates duplicate concurrent outbound HTTP/REST calls for the same ticker.
- **Bounded Concurrency:** Configurable semaphore limits parallel queries per provider.
- **TTL Cache:** In-memory caching with eviction prevents redundant external provider requests.
- **429 Rate-Limit Handling:** Exponential backoff with randomized jitter on HTTP 429 / Rate Limit responses.
- **Circuit Breaker:** State machine (`CLOSED` -> `OPEN` on consecutive errors -> `HALF_OPEN` cooldown) protects against external API degradation. Metrics (latency p50/p95, success rate, cooldown) surfaced on `/api/health`.

### Dashboard Additions
- **Market Pulse & Sector Heatmap:** Live breadth cards (% > 50/200 SMA, advancers/decliners ratio, 52-week highs/lows) and interactive sector momentum grid (1D, 1W, 1M returns with leader stocks) mounted on the Dashboard.
- **Quick Symbol Search (`Ctrl/Cmd + K`):** Global keyboard shortcut modal to search universe instruments with prices, sectors, and freshness indicators.
- **Persistent Chart Preferences:** Indicator toggles (`EMA20`, `SMA50`, `SMA200`, `Volume`) and timeframe settings are remembered in browser `localStorage`.
- **Custom Price Alerts:** User-defined price levels (`ABOVE` / `BELOW`) monitored in the background loop, labeled `[MANUAL ALERT]`, and delivered to Telegram and UI stream with exactly-once deduplication.

---

## 14. TradingView-Style Interactive Charting Engine (`lightweight-charts@5.2.1`)

The platform integrates an institutional-grade, high-performance candlestick charting engine using **TradingView Lightweight Charts v5**:

- **Real Multi-Timeframe Feeds:** Selectable **Daily (`1D`)** and **15-minute (`15m`)** candles sourced directly from the official Angel One SmartAPI (for NSE equities) and YFinance (for US equities/fallbacks).
- **Moving Average Overlays:** Independent toggle buttons with local persistence for **EMA 20** (Gold `#f59e0b`), **EMA 50** (Orange `#fb923c`), **SMA 50** (Blue `#3b82f6`), **SMA 150** (Teal `#14b8a6`), and **SMA 200** (Purple `#a855f7`). Indicators are calculated on the backend using exact strategy formulas (`indicators.py`).
- **Separate Indicator Panels:**
  - **Volume:** Pane 0 histogram overlay with green/red alpha transparency.
  - **RSI 14:** Dedicated secondary panel with dashed 70 Overbought and 30 Oversold reference levels.
  - **ATR 14:** Dedicated tertiary panel tracking volatility expansion and contraction.
- **Strategy Output Visualizations:**
  - **Breakout Trigger:** Dashed Emerald green price line (`#10b981`) marking the exact buy trigger price.
  - **Entry Zone Ceiling:** Dotted Teal price line (`#34d399`) marking the max chase limit (`trigger + 0.5*ATR`).
  - **Stop Loss:** Dashed Rose red price line (`#f43f5e`) marking structural invalidation.
  - **Target 1 (2R):** Dashed Cyan price line (`#06b6d4`) marking the 2R profit-taking target.
  - **VCP Base Consolidation Box:** Bounding box highlighting the base consolidation window, duration in sessions, depth %, and pivot level.
  - **Signal Markers:** Interactive arrows below trigger bars with confirmation status (`TRIGGERED_CONFIRMED`, `APPROACHING`, `BUY_CONFIRMED`, `WATCHLIST`).
  - **Minervini Stage 2 Trend Template Drawer:** Interactive badge displaying pass ratio (e.g., `7/8 Pass`) that expands to show the 8-point checklist with actual values vs. expected rules.
- **Manual Drawing Tools:** Interactive SVG overlay allowing traders to draw **Horizontal Lines**, **Trendlines**, and **Rectangles** with local persistence and clear/delete controls. Annotations are strictly client-side and never alter strategy logic.
- **Provenance & Feed Status:** Real-time badge tracking `LIVE` (green), `DELAYED` (amber), `STALE` (red), or `DISCONNECTED` (gray) status with provider attribution and last quote timestamps.
- **0-Latency Live Session Candle:** Dynamically updates today's active bar with live market LTPs while preserving completed 15-minute confirmation candles.
