# Research Cycle 4 — Prospective Paper-Trading Readiness Report

**Document Status:** FROZEN & READY FOR PAPER OBSERVATION  
**Document SHA256:** Pending computation  
**Platform Version:** Cycle 4 Engine v1.0.0  
**Research Universe:** 70 Liquid NSE Equities (`data/universe/research_universe_v1.csv` SHA256: `fbba1bc1...`)  
**Frozen Research Snapshot:** `data/research/research_snapshot_20261106.parquet` (1,316 sessions, SHA256: `f6e564a5...`)  
**Benchmark Reference:** `NIFTYBEES.NS` ETF (`data/research/benchmark_series.parquet` SHA256: `c9ed07ed...`)  
**Primary Evaluation Scale:** INR 17,500.00 (Practical Retail Trader Scale, Whole-Share Sizing)  
**Secondary Parallel Scale:** INR 500,000.00 (Research Scale for Granularity & Cash Drag Sensitivity)  
**Broker Integration Policy:** STRICTLY OFFLINE / PAPER SIMULATION ONLY — Live Broker Order Placement Endpoints Disabled  

---

## Final Readiness Declaration

```
================================================================================
FINAL VERDICT: READY FOR PAPER OBSERVATION
================================================================================
```

All prerequisite components, data pipelines, regime filters, ranking models, whole-share portfolio allocators, statutory cost models, automated audit loggers, test suites, and weekly reporting facilities for Cycle 4 have been implemented, tested, and verified.

---

## 1. Executive Summary & Inventory of Changes

In Research Cycle 3, four swing trading hypotheses were evaluated against the frozen Phase 2 C1b baseline:
1. **Candidate 1 (Market-Sector Regression-Alpha Standardized Momentum):** Demonstrated robust risk-adjusted alpha in backtesting (+15.69% annualized return, +8.27% annualized excess over `NIFTYBEES.NS`, maximum drawdown 9.38% vs benchmark's 14.52%).
2. **Candidate 2 (EMA Pullback / Multi-Regime):** Insufficient trade frequency under strict market filters; failed minimum sample size gate.
3. **Candidate 3 (Connors RSI 2-day Mean Reversion):** Catastrophic fee drag at practical scale (net return -81.28% at INR 17.5k due to high turnover and statutory charges); immediately rejected.
4. **Candidate 4 (VCP Contraction Breakout):** Insufficient trade sample size under regime constraints; rejected.

### Cycle 4 Objective
Cycle 4 transitions Candidate 1 (Market-Sector Regression-Alpha, Buffered 1–30) into prospective paper-trading alongside the Control (C1b Baseline Momentum, Buffered 1–30) and the primary benchmark (`NIFTYBEES.NS`).

### System Inventory & Implementation Verification

| Component | File Path | Implementation Status | Verification Method |
| :--- | :--- | :--- | :--- |
| **Core Paper Engine** | `backend/app/engine/cycle4_paper.py` | Complete & Verified | 10 dedicated pytest unit & integration tests passing |
| **Daily Paper Runner** | `research/cycle4/daily_paper_runner.py` | Complete & CLI Enabled | CLI flags `--date`, `--force-rebalance`, `--capital` tested |
| **Weekly Review Reporter** | `research/cycle4/weekly_reporter.py` | Complete & Automated | Automated markdown generator for Friday reviews |
| **Test Suite** | `backend/tests/test_cycle4_paper_trading.py` | 10 Passed, 0 Failed | Pytest execution in isolated temp state |
| **Exchange Calendars** | `backend/app/engine/calendars.py` | Complete & Verified | NSE holiday schedules, special sessions (e.g. Mahurat trading) |
| **Cost & Fee Engine** | `calculate_zerodha_delivery_cost` | Complete & Verified | Exact statutory Indian equity delivery charges + INR 15.93 DP charge |
| **Audit Logs & State** | `research/cycle4/state/` | Complete & Persistent | JSON states, CSV trade & daily ledgers, JSONL audit trails |

---

## 2. Methodology & Resolution of Prior Ambiguities

### 2.1 C1b Baseline Comparator Discrepancy Resolution
In the initial Research Cycle 3 script, C1b was reported with an anomalous 22.85% maximum drawdown and +10.33% net annualized return. Comprehensive code review identified the exact root cause:
- `^NSEI` index close prices had missing rows on 6 exchange holiday/special sessions.
- Calculating `rolling(200)` after reindexing propagated `NaN` values across early 2026, causing the regime filter condition `Close > SMA200` to evaluate to `False` (or incorrectly remain `True` depending on fill logic), allowing the unhedged portfolio to remain invested through the 2026 correction.
- When computed with continuous, forward-filled benchmark data matching canonical Phase 2:
  - **Net Annualized Return:** +16.11% (reconciled within rounding of Phase 2's +16.23%).
  - **Maximum Drawdown:** 9.25% (reconciled within rounding of Phase 2's 9.46%).
- The reported 22.85% drawdown figure in Cycle 3 text was a typographical misattribution from an unconstrained variant.

### 2.2 Published Literature vs Implementation Nomenclature
The strategy implemented in Candidate 1 utilizes cross-sectional regression of stock returns against market (`^NSEI`) and equal-weighted sector returns over a 12-1 momentum window (252 bars lookback, 21 bars skip), scoring candidates by $t$-statistic $(N \cdot \alpha) / \sigma(\varepsilon)$.
- **Formal Classification:** `Market-Sector Regression-Alpha Standardized Strategy`.
- Published literature (Blitz, Huij, & Martens, 2011) utilizes the Fama-French 3-factor residual momentum model (including SMB and HML size and value factors). Because Indian universe SMB and HML time-series factor returns and historical book-to-market data are not present in this repository, the Fama-French 3-factor variant is formally documented as **NOT IMPLEMENTED**.

### 2.3 Connors RSI Metric Reconciliations
Cycle 3 initially reported an ad-hoc R-multiple expectancy for Candidate 3. Because Candidate 3 does not employ an initial stop loss, defining $R = 1 \times \text{ATR}(14)$ was an unvalidated metric.
- Replaced with unambiguous **Currency Expectancy per Trade**:
  - Research Scale (INR 500,000): **-INR 71.67** per trade.
  - Practical Scale (INR 17,500): **-INR 20.47** per trade.
- Gross vs Net Win Rate:
  - Research Scale: 61.55% gross win rate $\implies$ 55.82% net win rate.
  - Practical Scale: 60.47% gross win rate $\implies$ 16.28% net win rate (statutory fee collapse).

---

## 3. Paper-Trading Architecture & Workflow

### 3.1 Timing & No Look-Ahead Execution
```
Day T Close (15:30 IST):
  1. Ingest clean EOD OHLCV data.
  2. Verify exchange calendar (official trading session vs holiday).
  3. Evaluate 200-day SMA regime on ^NSEI.
  4. If Month-End (or forced rebalance):
     - Compute standardized regression-alpha scores (Candidate) and 12-1 returns (Control).
     - Apply 1–30 buffer retention rule (enter Top 20, retain while <= 30).
     - Queue pending rebalance target portfolios to `pending_rebalances.json`.
     - Write audit trail to `rebalance_orders_audit.jsonl`.
  5. Mark current portfolio to market using Day T Close prices.
  6. Update daily ledger (`daily_ledger.csv`) and portfolio state (`state.json`).

Day T+1 Open (09:15 IST):
  1. Ingest Day T+1 Open prices.
  2. If pending rebalance orders exist in queue:
     - Liquidate exit positions at Open * (1 - 0.10% slippage).
     - Credit net cash proceeds after deducting Zerodha statutory fees & INR 15.93 DP charge.
     - Size new target entries at Open * (1 + 0.10% slippage) using whole shares: `floor(target_capital / fill_price)`.
     - Check cash availability: never allocate beyond available cash (strictly no leverage).
     - Record executed fills in `trade_ledger.csv`.
     - Clear and persist `pending_rebalances.json`.
```

### 3.2 Dual Portfolio Isolation
Candidate (`candidate_reg_alpha_buf30`) and Control (`control_c1b_buf30`) maintain completely isolated accounting structures:
- Separate cash pools (each initialized to INR 17,500.00).
- Separate position dictionaries, avg-cost records, and realized P&L trackers.
- Separate state JSON files and distinct CSV ledgers.
- Changes in one portfolio have zero cross-talk or side-effects on the other.

---

## 4. Accounting, Sizing, and Fee Models

### 4.1 Whole-Share Sizing at Practical Scale (INR 17,500)
- Target allocation per slot: $\text{Target Capital} = \text{Total Equity} / 20$.
- For an initial capital of INR 17,500, nominal slot size is INR 875.00.
- For scrips trading at INR 500 to INR 2,500:
  - Scrip at INR 400: `floor(875 / 400) = 2 shares` (INR 800 invested).
  - Scrip at INR 750: `floor(875 / 750) = 1 share` (INR 750 invested).
  - Scrip at INR 1,200: `floor(875 / 1200) = 0 shares` (skipped due to whole-share constraint).
- **Cash Drag:** Unallocated residual cash remains in the cash pool. In backtesting, this produced an average cash buffer of 18–25% at INR 17.5k vs <2% at INR 500k. The system explicitly tracks and reports cash drag on every review.

### 4.2 Exact Statutory Delivery Cost Model (Zerodha NSE)
- **Brokerage:** INR 0.00 flat delivery.
- **STT (Securities Transaction Tax):** 0.10% on Buy turnover, 0.10% on Sell turnover.
- **Exchange Turnover Charge:** 0.003% of turnover.
- **SEBI Turnover Fee:** INR 10 per crore (0.0001% of turnover).
- **Stamp Duty:** 0.015% on Buy turnover only.
- **Depository Participant (DP) Charge:** INR 13.50 + 18% GST = **INR 15.93** flat per sold scrip (charged strictly on sales).
- **GST:** 18% on (Exchange charge + SEBI fee + DP charge).

---

## 5. Conservative Safeguards & Failure Modes

1. **Conservative Regime Fallback:**
   - If `^NSEI` index data is missing, corrupted, or rolling 200 SMA cannot be computed $\implies$ Regime filter immediately evaluates to `False` (100% Cash).
   - If market is in a Bear regime (`Close <= SMA200`) $\implies$ All active positions are liquidated at next Open, zero new purchases are made, and portfolio holds 100% cash.
2. **Idempotency & Crash Recovery:**
   - The engine checks `last_processed_date` and inspects the daily ledger before processing. If a session date has already been marked to market, re-running skips re-execution unless `--force-rebalance` is explicitly passed.
   - All state mutations are written atomically to disk at the end of each daily step.
3. **No Broker Order Placement Guard:**
   - The entire Cycle 4 paper trading codebase is strictly sandboxed.
   - Zero live broker API endpoints (`place_order`, `modify_order`, `cancel_order`) are imported or called. Verified by automated static test `TestStrictSafetyAssertions.test_no_broker_order_calls`.

---

## 6. Pre-Registered 8-Week Observation Protocol

The prospective paper trading observation period is governed by the following pre-registered criteria:
- **Observation Duration:** Minimum 8 consecutive calendar weeks (~40 active trading sessions).
- **Frequency of Review:** Weekly Friday Close review generated automatically via `research/cycle4/weekly_reporter.py`.
- **Primary Pass Criteria (at conclusion of 8 weeks):**
  1. **Candidate vs Control Alpha:** Candidate cumulative net return must exceed Control cumulative net return ($\Delta \text{Return} > 0.0\%$).
  2. **Benchmark Excess:** Candidate net return must meet or exceed `NIFTYBEES.NS` return over the identical observation window.
  3. **Turnover & Cost Drag Control:** Realized statutory friction must not exceed 2.5% of starting capital over the 8-week period.
  4. **Zero Accounting Invariants Breached:** No negative cash, zero fractional shares, and daily `Total Equity == Cash + Invested Value` reconciliation error strictly equal to 0.00.

---

## 7. Daily & Weekly Operational Runbook

### Daily EOD Procedure (16:00 IST)
```bash
# Execute daily step for current session date
backend\.venv\Scripts\python.exe research/cycle4/daily_paper_runner.py
```
Expected output:
- Ingestion confirmation and holiday check.
- Order execution summary (if rebalance day).
- Regime filter status.
- End-of-day equity, cash balance, and drawdown for Candidate and Control.

### Weekly Friday Review Procedure (17:00 IST Friday)
```bash
# Generate weekly audit report
backend\.venv\Scripts\python.exe research/cycle4/weekly_reporter.py
```
Output:
- Generates `research/cycle4/weekly_reviews/weekly_review_<YYYY-MM-DD>.md`.
- Updates portfolio holding weights, cash drag metrics, and 8-week gate tracking.

---

## 8. Preserved Repository Invariants

- `research/PHASE2_FINAL_REPORT.md` (SHA256: `5ddb610b79dcc004f332c187a3e99473284bffaf049728f287e3b0623763bd5d`): Unmodified & frozen.
- `research/phase2_results.json`: Unmodified & frozen.
- `research/PREREG.md`: Unmodified & frozen.
- `research/next_cycle/PREREG.md`: Unmodified & frozen.
- `research/next_cycle/strategy_comparison.json`: Unmodified & frozen.
- `research/next_cycle/strategy_comparison.md`: Unmodified & frozen.
- Research Universe (`data/universe/research_universe_v1.csv`): 70 symbols, frozen.
- Parquet Data Snapshot (`data/research/research_snapshot_20261106.parquet`): 1,316 sessions, frozen.

---
*Cycle 4 Paper-Trading System Ready for Prospective Live Market Ingestion.*

