# Pre-Registration Draft: Prospective Forward Paper-Trading Study (Cycle 4)

**Document Status:** DRAFT — AWAITING OWNER APPROVAL — STRICTLY NON-OPERATIONAL  
**Draft Date:** 2026-11-16  
**Target Study Version:** Cycle 4 Paper-Trading Engine v1.0.0 (`backend/app/engine/cycle4_paper.py`)  
**Operating Mode:** Forward Paper Observation (Simulated Research Only — No Real Capital, No Broker Order Routing)  
**Parent Source Documents:**
- [`research/PREREG.md`](file:///d:/web%20development/saas-projects/Algo-trading/research/PREREG.md) (Phase 2 Frozen Pre-Registration)
- [`research/PHASE2_FINAL_REPORT.md`](file:///d:/web%20development/saas-projects/Algo-trading/research/PHASE2_FINAL_REPORT.md) (Phase 2 Quality-Controlled Report)
- [`SWING_ALGO_BUILD_SPEC.md`](file:///d:/web%20development/saas-projects/Algo-trading/SWING_ALGO_BUILD_SPEC.md) (System Master Specification)
- [`research/cycle4/CYCLE4_READINESS_REPORT.md`](file:///d:/web%20development/saas-projects/Algo-trading/research/cycle4/CYCLE4_READINESS_REPORT.md) (Readiness Audit)

---

## 1. Executive Summary & Governance Pre-Conditions

### 1.1 Non-Derogation from Phase 2 Kill Rule
Pursuant to Section 6 of `research/PREREG.md` and Section 1 of `research/PHASE2_FINAL_REPORT.md`, Phase 2 Pre-Registered Strategy Validation concluded with zero candidates qualifying for an unconditional `PASS`. The Phase 2 kill rule remains in full legal and operational effect:
- **No live broker order placement is authorized.**
- **No automated trading alerts or order generation for deployable capital are permitted.**
- **This forward paper-trading study does NOT override, amend, or dismiss Phase 2 acceptance gates.**
- **This study is strictly an observational research experiment** designed to gather out-of-sample forward telemetry on transaction fee drag and candidate ranking stability under live quote feeds without risking financial capital.

### 1.2 Mandatory Owner Sign-off Pre-Requisite
This draft pre-registration is non-operational. Execution of prospective paper-trading runs (via scheduler or manual CLI triggers) is gated by `FORWARD_PAPER_TRADING_ENABLED=False` (default) in `backend/app/settings.py` and `backend/app/scheduler/jobs.py`. **The scheduler jobs cannot and will not execute without explicit, written owner sign-off and environment activation.**

---

## 2. Research Hypothesis & Scientific Rationale

### 2.1 Primary Research Hypothesis
**Market-Sector Regression-Alpha Purged Momentum (Candidate 1)**, when evaluated prospectively over fresh, uninspected market quotes, produces a higher risk-adjusted return and lower drawdown than the unpurged 12-1 momentum baseline (**Control C1b**), by filtering out systemic market-wide beta and sector-concentration whipsaws while preserving idiosyncratic trend persistence.

### 2.2 Secondary Research Hypothesis (Whole-Share Fee-Drag Survival)
Under retail retail-scale capital constraints (**INR 17,500.00**), whole-share sizing with a 1–30 retention buffer band limits portfolio turnover sufficiently to prevent statutory Indian equity delivery costs (STT, stamp duty, exchange charges, SEBI fees, and flat DP charges) from consuming gross strategy returns.

---

## 3. Evaluated Candidates & Scope

The prospective forward study includes strictly two isolated portfolios and one passive benchmark. No new strategies or ad-hoc indicators are permitted.

| Entity | Role | Identifier / File | Frozen Specification |
|---|---|---|---|
| **Candidate Portfolio** | Test Subject | `candidate_reg_alpha_buf30` | Market-Sector Regression-Alpha, 12-1 lookback (252 bars lookback, 21-bar skip), standardized score $S = \frac{\alpha}{\sigma_\epsilon}$, 1–30 retention buffer band. |
| **Control Portfolio** | Active Baseline | `control_c1b_buf30` | Classical 12-1 cross-sectional momentum, score $S = \frac{P_{T-21}}{P_{T-252}} - 1$, 1–30 retention buffer band. |
| **Passive Benchmark** | Passive Reference | `NIFTYBEES.NS` | Nippon India Nifty 50 BeES ETF total return series. |

### 3.1 Status of Other Strategies
1. **Candidate 3 (Dual Strength Momentum):** Preserved strictly as **HISTORICAL-REPLAY-ONLY** in `research/cycle4/replay_state/`. It is excluded from this prospective study because no independently approved prospective execution runner exists for it.
2. **Candidate 4 (Value Radar):** Preserved as **UNAVAILABLE**. No reliable point-in-time balance sheet / quarterly P&L feed exists in the live infrastructure.
3. **Setup V (VCP) & Setup P (Pullback):** Excluded per Phase 4 audit conclusions (Setup P confirmed negative expectancy; Setup V starved of trade frequency on 105-symbol universe).

---

## 4. Market, Universe & Data Sourcing

### 4.1 Approved Market & Universe
- **Market:** National Stock Exchange of India (NSE) Equity Delivery (`-EQ` series).
- **Universe File:** `data/universe/research_universe_v1.csv` (70 liquid Indian equities across Nifty 100 and Nifty Midcap 150).
- **Sector Mapping:** Fixed sector assignments defined in `research_universe_v1.csv`.
- **Exclusions:** Equities with 60-day median daily turnover < INR 50,000,000 or price < INR 50.00 are excluded dynamically at each rebalance.

### 4.2 Data Ingestion & Live Quote Source
- **Core Market Provider:** Angel One SmartAPI daily EOD candles (`angelone_provider.py`).
- **Benchmark & Fallback Provider:** Yahoo Finance (`^NSEI`, `NIFTYBEES.NS`).
- **Quote Validation:** Ingested daily bars must possess positive Open, High, Low, Close, and Volume. Bars with missing or non-positive Close are rejected.

---

## 5. Capital Allocation & Sizing Constraints

### 5.1 Simulated Research Capital
- **Starting Simulated Capital:** Exactly **INR 17,500.00** per portfolio (`initial_capital = 17500.0`).
- **Capital Separation:** Candidate and Control operate in strictly isolated accounting ledgers (`candidate_reg_alpha_buf30_state.json` and `control_c1b_buf30_state.json`). No cross-portfolio cash subsidization or netting.
- **Uninvested Cash:** Cash balance earns 0.0% interest. No margin or borrowed capital is allowed (`cash >= 0.0`).

### 5.2 Position Sizing Rules
- **Target Slots:** $N = 20$ target slots (or up to available eligible names).
- **Slot Allocation:** $\text{Target Capital Per Slot} = \frac{\text{Total Equity at Open}}{N}$.
- **Whole-Share Sizing:**
  $$\text{Target Shares} = \left\lfloor \frac{\text{Target Capital Per Slot}}{\text{Fill Price}} \right\rfloor$$
- **Cash Ceiling Enforcement:** If cash is insufficient to buy target shares, the order is scaled down:
  $$\text{Affordable Shares} = \left\lfloor \frac{\text{Available Cash}}{\text{Fill Price} \times 1.002} \right\rfloor$$
  If $\text{Affordable Shares} \le 0$, the order is skipped and logged with `REJECTED_INSUFFICIENT_CASH`. Fractional shares are strictly prohibited.

---

## 6. Execution, Slippage & Statutory Transaction Cost Model

### 6.1 Order Generation & Execution Invariants
- **Signal Generation:** Evaluated at EOD Close of trading day $T$ (15:30 IST).
- **Execution Timing:** Orders execute strictly at Open of trading day $T+1$ (09:15 IST). Zero same-bar lookahead.
- **Rebalance Cadence:** Monthly rebalance cadence with calendar-aware scheduling, synchronous across Candidate and Control.
- **Buffer Band (1–30):**
  - Enter new position only if ranked in Top 20 ($\text{rank} \le 20$).
  - Retain existing held position if it remains in Top 30 ($\text{rank} \le 30$).
  - Exit position if rank drops beyond 30 ($\text{rank} > 30$) or if market regime fails.

### 6.2 Slippage Model
- **Buy Orders:** Executed at $\text{Open} \times (1 + 0.0010)$ (+0.10% adverse slippage).
- **Sell Orders:** Executed at $\text{Open} \times (1 - 0.0010)$ (-0.10% adverse slippage).

### 6.3 Statutory Indian Delivery Cost Model (NSE Zerodha Delivery)
Cost calculation follows `calculate_zerodha_delivery_cost()` in `backend/app/engine/cycle4_paper.py`:
- **Brokerage:** INR 0.00.
- **Securities Transaction Tax (STT):** 0.10% on Buy turnover, 0.10% on Sell turnover.
- **Exchange Transaction Fee:** 0.003% of turnover.
- **SEBI Turnover Fee:** INR 10 per crore (0.0001% of turnover).
- **Stamp Duty:** 0.015% on Buy turnover (INR 0.00 on Sell).
- **Depository Participant (DP) Fee:** Flat INR 15.93 (INR 13.50 base + INR 2.43 18% GST) charged strictly upon full position closure. ₹0 on partial position trims. Deduplicated per symbol per execution day.
- **Goods and Services Tax (GST):** 18% applied to $(\text{Exchange Fee} + \text{SEBI Fee} + \text{DP Base Fee})$. (0% GST on STT and Stamp Duty).

---

## 7. Market Regime & Missing Data Handling

### 7.1 Market Regime Filter
- **Filter Definition:** `^NSEI` Close > 200-day Simple Moving Average.
- **Conservative Fail-to-Cash Invariant:** If `^NSEI` Close $\le 200\text{-day SMA}$, or if `^NSEI` data is missing, stale, NaN, or has $<200$ bars of history, the regime status evaluates to `BEAR_REGIME` (Fail-Closed).
- **Action on Bear Regime:** All existing positions are liquidated to 100% Cash at the next Open ($T+1$). No new purchases are permitted until the regime recovers to `BULL_REGIME`.

### 7.2 Missing Price & Missing Data Invariants
- **Missing Open Price ($T+1$):** If Open price for a target scrip is unavailable, the order is aborted for that session, logged in audit logs, and retry deferred to the subsequent session.
- **Missing EOD Close Price:** If Close price is unavailable during daily mark-to-market:
  - Last known average cost or prior close is carried forward.
  - The record is flagged with `is_complete_valuation = False`.
  - The missing symbol is recorded in `missing_price_symbols`.

---

## 8. Daily Equity Measurement & Reporting Cadence

### 8.1 Daily Mark-to-Market Accounting
At the close of every official NSE trading session:
$$\text{Total Equity}_t = \text{Cash}_t + \sum_{i \in \text{Holdings}} (\text{Shares}_{i,t} \times \text{Close}_{i,t})$$
$$\text{Peak Equity}_t = \max(\text{Peak Equity}_{t-1}, \text{Total Equity}_t)$$
$$\text{Drawdown Pct}_t = \frac{\text{Total Equity}_t - \text{Peak Equity}_t}{\text{Peak Equity}_t} \times 100.0$$
$$\text{Cumulative Return Pct}_t = \left(\frac{\text{Total Equity}_t}{\text{Initial Capital}} - 1.0\right) \times 100.0$$

### 8.2 Audit Trail & Ledger Logging
Every action must be persisted to:
- `research/cycle4/state/{name}_state.json` (Current account snapshot).
- `research/cycle4/state/{name}_daily_ledger.csv` (Complete daily equity time-series).
- `research/cycle4/state/{name}_trade_ledger.csv` (Detailed individual trade execution audit).
- `research/cycle4/state/rebalance_orders_audit.jsonl` (Signal-time ranking and target logs).

### 8.3 Weekly Reviews
Every Friday at 17:00 IST post-market close, an automated audit markdown report is generated at `research/cycle4/weekly_reviews/weekly_review_{YYYY-MM-DD}.md`, summarizing weekly P&L, fee drag, active positions, and benchmark comparisons.

---

## 9. Observation Duration & Stopping Conditions (Kill Switch)

### 9.1 Observation Window
- **Minimum Duration:** 6 to 8 consecutive calendar weeks of active prospective trading sessions.
- **Trade Count Goal:** $\ge 20$ completed round-trip trades where achievable given the monthly turnover schedule.

### 9.2 Strict In-Flight Invariants
- **No Parameter Tuning:** Lookback periods (252, 21), buffer bands (1–30), universe selections (70 symbols), capital allocation (INR 17,500), and cost parameters are strictly frozen. Any mid-study modification renders the entire observation run invalid.

### 9.3 Emergency Stopping Conditions (Automated Halt)
The study must halt immediately if any of the following conditions occur:
1. **Drawdown Breach:** Total equity of either portfolio drops $> 15.0\%$ below initial capital (Equity < INR 14,875.00).
2. **Excessive Cost Drag:** Cumulative statutory transaction costs exceed $5.0\%$ of initial capital (Costs > INR 875.00) while cumulative gross P&L is negative or zero.
3. **Data Pipeline Failure:** More than 3 consecutive trading sessions fail to ingest valid market data or experience unresolved valuation anomalies.
4. **Execution Divergence:** Any instance where cash drops below INR 0.00 (negative cash violation).

---

## 10. Evaluation Protocol & Final Disposition

At the conclusion of the 6–8 week observation window:
1. **Net Excess Return:** Candidate Net Return vs. Control Net Return and Benchmark Net Return.
2. **Cost Drag Ratio:** Statutory costs as a percentage of gross turnover and initial capital.
3. **Turnover Reduction:** Number of trades saved by the 1–30 retention buffer vs. unbuffered top-20 turnover.
4. **Conclusion Type:**
   - **Observational Baseline:** Results will be documented in a Cycle 4 Final Observation Report.
   - **No Phase 2 Overwrite:** Even if positive returns are observed, this exploratory study cannot overturn Phase 2's historical data limitations (missing 2020 crash, survivorship bias in historical constituents, lack of 4 full historical calendar years). Live capital trading will remain unauthorized until a full, compliant Phase 2 re-validation with clean historical point-in-time data is pre-registered and passed.

---

## 11. Sign-off & Activation Gate

| Role | Name | Status | Signature / Date |
|---|---|:---:|---|
| **Author / Quant Engineer** | Antigravity AI Engine | **PREPARED** | 2026-11-16 |
| **System Architect** | Antigravity Architecture | **VERIFIED** | 2026-11-16 |
| **System Owner / Capital Allocator** | User (`mk070`) | **PENDING APPROVAL** | `____________________` |

*To activate this study after written owner approval:*  
Set `FORWARD_PAPER_TRADING_ENABLED=True` in `.env` and restart the application daemon.
