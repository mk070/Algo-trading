# Research Cycle 3: Independent Swing Strategy Testing — Final Reconciled Report

**Status:** CYCLE COMPLETE — ALL METHODOLOGICAL CORRECTIONS APPLIED  
**Date:** 2026-11-06  
**Cycle:** Research Cycle 3 — Independent Swing Strategy Testing  
**Research Mode:** Strictly Offline Research — No Live Trading, No Automated Order Placement  
**Pre-Registration Git Commit:** `9a58dbf048a8ffcc3fccbd431d3933f19f6d8726`  
**PREREG.md SHA256:** `f5d87c02330a7967dba34934ceabbe99df48c09e93c99a3d74bc910710e6d69d`  
**Universe:** India NSE Equities (`research_universe_v1.csv` — 70 symbols, SHA256: `fbba1bc176a5dd6c0d5f2527dc7599f3c1d0117158e54fcd6b8f94a9542ee72e`)  
**Data Snapshot:** `research_snapshot_20261106.parquet` (1,316 sessions, SHA256: `f6e564a5c3d01f755c5fc0e1356346491c56d66312a13c0da64e421ff8c0c58f`)  
**Primary Benchmark:** `NIFTYBEES.NS` Total Return ETF (SHA256: `c9ed07ede1e98fdf7b869cfc8ffa749d41e68a9781dfebb31c7685325f4093be`)  
**Market Regime Index:** `^NSEI` (Nifty 50 Index)  

---

## 1. Executive Summary & Master Decision Matrix

Research Cycle 3 tested three distinct swing-trading hypotheses against the canonical Phase 2 baseline (Candidate C1b India). All simulations were conducted strictly offline on the approved frozen research universe and snapshot, applying exact Zerodha Indian equity delivery costs (including flat DP charges of ₹15.93 per sold scrip and 0.10% adverse execution slippage).

### Master Comparison Table (Reconciled)

| Candidate / Strategy | Formulation Reference | Annualized Net Return | Annualized Excess vs NIFTYBEES | Max Drawdown | Sharpe Ratio | Sortino Ratio | Monthly Turnover | Cumulative Cost Drag (% starting capital) | Decision Protocol Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Canonical Phase 2 Comparator: C1b India** | Clean Regime (`^NSEI > SMA200`) | +16.23% | +8.81% | 9.46% | 0.99 | 1.94 | ₹267.6k avg | 3.63% | **CANONICAL BASELINE** |
| **Cycle 3 Replicated C1b** (No Buffer) | Jegadeesh & Titman (1993) | +16.11% | +8.69% | 9.25% | 1.42 | 1.92 | 38.69% | 3.84% | **HISTORICAL COMPARATOR** |
| **Cycle 3 Replicated C1b** (Buffered 1–30) | Retention Band Control | +17.51% | +10.09% | 9.02% | 1.51 | 2.52 | 23.53% | 2.33% | **CONTROL BENCHMARK** |
| *Cycle 3 Degraded C1b Comparator* | *Weekend NaN Regime Artifact* | *+10.33%* | *+2.91%* | *22.85%* | *0.63* | *0.77* | *46.88%* | *4.55%* | *DEGRADED RUNNER (RECONCILED)* |
| **Candidate 1: Market-Sector Regression-Alpha** (No Buffer) | Idiosyncratic Alpha Standardized | +13.49% | +6.07% | 10.18% | 1.24 | 1.90 | 38.08% | 3.68% | **INCONCLUSIVE** |
| **Candidate 1: Market-Sector Regression-Alpha** (Buffered 1–30) | Idiosyncratic Alpha Standardized | +16.88% | +9.46% | **8.31%** | **1.52** | **2.41** | **24.73%** | **2.48%** | **INCONCLUSIVE** |
| **Candidate 2: Frog-in-the-Pan** (No Buffer) | Da, Gurun & Warachka (2014) | +12.42% | +5.00% | 10.27% | 1.21 | 2.02 | 42.78% | 3.87% | **REJECTED** |
| **Candidate 2: Frog-in-the-Pan** (Buffered 1–30) | Da, Gurun & Warachka (2014) | +12.83% | +5.41% | 8.44% | 1.25 | 2.08 | 28.97% | 2.65% | **REJECTED** |
| **Candidate 3: Connors RSI(2)** (Research ₹500k) | Larry Connors Mean Reversion | -5.28% | -16.33% | 29.90% | N/A | N/A | High (1,485 trades) | **33.11%** | **REJECTED IMMEDIATELY** |
| **Candidate 3: Connors RSI(2)** (Practical ₹17.5k) | Larry Connors Mean Reversion | -27.28% | -38.32% | 75.48% | N/A | N/A | High (645 trades) | **76.13%** | **REJECTED IMMEDIATELY** |
| **Published Blitz, Huij & Martens (2011)** | Fama-French 3-Factor 36m | N/A | N/A | N/A | N/A | N/A | N/A | N/A | **NOT IMPLEMENTED** |

> **CORE DECISION & SUMMARY FINDINGS:**  
> **ZERO candidates qualify for `VALIDATED` status or live trading deployment.**  
> 1. **Candidate 3 (Connors RSI(2)) is REJECTED IMMEDIATELY.** It produces negative mathematical currency expectancy ($-₹71.67$ per trade at ₹500k, $-₹20.47$ at ₹17.5k), a net profit factor of $0.85$ (collapsing to $0.10$ at practical scale), and severe transaction cost destruction ($33.11\%$ to $76.13\%$ cumulative cost drag).  
> 2. **Candidate 2 (Frog-in-the-Pan) is REJECTED.** Ranking by Information Discreteness ($ID$) underperforms conventional momentum by over 360 to 460 bps (+12.83% vs +17.51% buffered) and fails the bootstrap significance test.  
> 3. **Candidate 1 (Market-Sector Regression-Alpha) is classified as INCONCLUSIVE.** It demonstrates robust empirical risk reduction (achieving an **8.31% maximum drawdown** vs 9.02% for C1b and 14.52% for NIFTYBEES) and a Sharpe ratio of $1.52$. However, because all historical evaluations on this dataset are exploratory and lack an independent untouched holdout, it cannot be validated without prospective forward testing.  
> 4. **Published Blitz, Huij & Martens (2011) Residual Momentum is marked as NOT IMPLEMENTED.** The required Fama-French Indian SMB and HML factors, historical balance sheet data, and 36-month pre-formation history are unavailable in the frozen snapshot.

---

## 2. Resolution of Methodological Discrepancies

### A. C1b Baseline Discrepancy Resolution
- **Phase 2 Canonical Result:** Net Annualized Return: **+16.23%**, Annualized Excess vs NIFTYBEES: **+8.81%**, Maximum Drawdown: **9.46%**, Final Equity: **₹947,619.98**.
- **Initial Cycle 3 Runner Result:** Net Annualized Return: **+10.33%**, Annualized Excess: **+2.91%**, Maximum Drawdown: **22.85%**, Final Equity: **₹759,359.05**.
- **Cause of Difference (Technical Audit):**
  1. *Regime Index Missing Bars:* In the initial Cycle 3 runner script (`backend/run_cycle3_validation.py`), `nsei` was reindexed to `close_df.index`, which contained 6 special Indian weekend/holiday trading sessions (e.g. Diwali Muhurat trading on Sunday 2023-11-12, disaster recovery live sessions on Saturdays in 2024, and Union Budget session on Sunday 2026-02-01). Because `^NSEI` index close in `bench_df` was NaN on those weekend sessions, `rolling(200, min_periods=200)` propagated NaNs across subsequent dates starting in February 2026.
  2. *Regime Filter Default Fallback:* In the initial Cycle 3 loop, `regime_pass` initialized to `True`. The condition `if pd.notna(b_c) and pd.notna(b_sma): regime_pass = b_c > b_sma` failed to execute because `b_sma` was NaN. Consequently, the initial runner stayed **100% invested throughout the 2026 market correction**, suffering deep drawdowns down to ₹759,359.
  3. *Phase 2 Implementation:* In Phase 2 (`run_phase2_validation.py`), `bench_sma200` was computed directly on the clean continuous series without NaN gaps. Phase 2 correctly detected `^NSEI Close < SMA200` in early 2025 (Jan–Mar) and early 2026 (Feb–Oct 2026), moving the portfolio to **100% Cash** at ₹947,619.98.
- **Reconciliation Outcome:** When the regime series is computed cleanly without NaN gap propagation, the Cycle 3 backtester replicates the Phase 2 baseline at **+16.11% annualized net return** (matching Phase 2's +16.23% within 0.12% due to whole-share and cash rounding), **9.25% maximum drawdown** (matching Phase 2's 9.46%), and ₹943,477 final equity. Both figures are transparently reported above.

### B. Benchmark Drawdown Reconciled
- **NIFTYBEES.NS (Total Return ETF):**
  - Full snapshot daily maximum drawdown (2021-07-19 to 2026-11-05): **16.11%** (recorded in Phase 2 report).
  - Evaluation period daily maximum drawdown (2022-08-30 to 2026-10-30): **15.23%** (peak ₹299.70 on 2026-01-20 to trough ₹254.05 on 2026-03-19).
  - Evaluation period month-end maximum drawdown (2022-08-30 to 2026-10-30): **14.52%** (peak ₹296.49 on 2026-01-30 to trough ₹253.44 on 2026-03-30).
- **^NSEI (Nifty 50 Index):**
  - Full snapshot daily maximum drawdown: **17.23%**.
  - Evaluation period daily maximum drawdown: **15.77%**.
  - Evaluation period month-end maximum drawdown: **14.78%** (recorded in Phase 2 report).
- **Correction:** The "22.85%" figure cited in earlier report text was a typographical misattribution of the degraded C1b strategy's drawdown into the benchmark column. `NIFTYBEES.NS` actual maximum drawdown during the evaluation period was **14.52%** (month-end) and **15.23%** (daily).

---

## 3. Residual Momentum Methodology & Attribution Correction

### Accurate Strategy Characterization
The strategy implemented in `backend/run_cycle3_validation.py` is the **Market-Sector Regression-Alpha Standardized Strategy**:
- Trailing window: $t = T-252$ to $t = T-21$ (232 trading sessions).
- Factor model: $R_{i,t} = \alpha_i + \beta_{i,M} R_{M,t} + \beta_{i,S} R_{S,t} + \epsilon_{i,t}$, where $R_M$ is `^NSEI` and $R_S$ is the equal-weighted return of all other universe stocks in stock $i$'s sector.
- Idiosyncratic return: $R_{i,t}^{\text{idiosyncratic}} = R_{i,t} - \hat{\beta}_{i,M} R_{M,t} - \hat{\beta}_{i,S} R_{S,t} = \hat{\alpha}_i + \hat{\epsilon}_{i,t}$.
- Score: $\text{Score}_i = \frac{\sum R_{i,t}^{\text{idiosyncratic}}}{\sigma(\hat{\epsilon}_i)} = \frac{N \hat{\alpha}_i}{\sigma(\hat{\epsilon}_i)}$.

### Discrepancy with Blitz, Huij and Martens (2011)
The published Blitz et al. (2011) methodology specifies:
1. Monthly stock excess returns regressed on Fama-French 3 factors (Market, SMB, HML).
2. A 36-month rolling estimation window.
3. 12-1 cumulative residual return ranking without adding back estimated alpha.
4. Standardization by residual return standard deviation over the formation period.

### Factor Availability Audit & Formal Classification
1. **Factor Data Audit:** Neither Fama-French SMB nor HML factor return series for India exist in `data/research/benchmark_series.parquet` (which contains only `MDY`, `NIFTYBEES.NS`, `SPY`, `^GSPC`, `^NSEI`).
2. **Fundamental Data Audit:** The snapshot `research_snapshot_20261106.parquet` contains only daily price and volume fields. No historical book-to-market data, financial balance sheets, or shares outstanding exist to construct reliable Fama-French factors without invented data.
3. **Formal Determination:**  
   - The published Blitz, Huij & Martens (2011) specification is formally marked as **`NOT IMPLEMENTED`**.  
   - The evaluated strategy is retained and reported under its accurate technical name: **Market-Sector Regression-Alpha Standardized Strategy**.  
   - No prospective paper observation is authorized under Blitz et al.'s paper attribution.

---

## 4. Reconciled Connors RSI(2) Daily Swing Calculations

### R Denominator & Expectancy Clarification
The pre-registered rules for Connors RSI(2) specify entries at next Open after RSI(2) $\le 10$ and exits at next Open after Close > SMA(5) or after 5 elapsed sessions. The strategy has **no fixed stop loss**. Therefore, standard $R$-multiple expectancy (which previously used $1 \times \text{ATR}(14)$ as an ad-hoc denominator) is mathematically unvalidated and is replaced by **Currency Expectancy per Trade** ($\text{INR per trade}$) and **Average Trade PnL %**.

### Reconciled Metrics Breakdown

| Metric | Research Capital (₹500,000) | Practical Scale (₹17,500) | Economic Reality / Friction Analysis |
| :--- | :---: | :---: | :--- |
| **Total Completed Trades** | **1,485** | **645** | Large, statistically robust sample |
| **Gross Winning Trades** | **914 (61.55%)** | **390 (60.47%)** | Gross price edge exists |
| **Net Winning Trades** | **829 (55.82%)** | **105 (16.28%)** | Fees flip 85 wins at ₹500k, and 285 wins at ₹17.5k! |
| **Gross Profit Factor** | **1.092** | **1.020** | Weak gross edge before costs |
| **Net Profit Factor** | **0.850** | **0.097** | **Net loss after realistic slippage and statutory costs** |
| **Total Net PnL** | **-₹106,431.22** | **-₹13,202.68** | Direct equity destruction |
| **Currency Expectancy per Trade** | **-₹71.67 / trade** | **-₹20.47 / trade** | **Negative mathematical expectancy** |
| **Average Trade PnL %** | -0.16% | -2.48% | Net negative average trade |
| **Average Winning Trade %** | +1.76% | +1.38% | Modest upside on bounces |
| **Average Losing Trade %** | -2.58% | -3.23% | Losses overwhelm winners |
| **Cumulative Costs Paid** | **₹165,573.87** | **₹13,322.19** | Substantial transaction fees paid |
| **Cumulative Costs (% Starting Capital)** | **33.11%** | **76.13%** | Fixed DP charges destroy small account |
| **Annualized Net Return** | **-5.28%** | **-27.28%** | Negative compounding |
| **Maximum Drawdown** | **29.90%** | **75.48%** | Severe account impairment |

### Exit Reasons Breakdown (₹500k Portfolio)
- **Target Exit ($\text{Close} > \text{SMA}5$):** 1,145 trades (77.1%), Gross Win Rate: 78.2%, Net Win Rate: **71.7%**, Average Holding: 2.8 days.
- **Time Stop (5 Completed Sessions):** 340 trades (22.9%), Gross Win Rate: 4.1%, Net Win Rate: **2.4%**, Average Holding: 5.0 days.

### Reaffirmation of Verdict: `REJECTED IMMEDIATELY`
The empirical test conclusively refutes the viability of cash-equity Connors RSI(2) daily swing mean reversion under real-world transaction friction. While gross win rate is 61.55%, the average gain on winners (+1.76%) is insufficient to overcome adverse slippage, STT, and flat DP charges (₹15.93 per sold scrip). At practical scale (₹17,500), DP charges alone turn 73% of gross winning trades into net losses, generating a catastrophic 75.48% drawdown.

---

## 5. Matched Random Controls Disclosure

The pre-registered protocol required matched random controls for evaluated candidates:

| Candidate / Strategy | Random Control Status | Simulations | Random Baseline 95th Percentile | Candidate Excess Return | Percentile Rank | Control Result |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Candidate 1: Market-Sector Regression-Alpha** | **EXECUTED** | 1,000 | +5.04% | +6.07% (No Buffer) | **98.4%** | **PASSED** (Rank $\ge 95\%$) |
| **Candidate 2: Frog-in-the-Pan** | **NOT RUN / NOT DEMONSTRATED** | N/A | N/A | +5.00% | N/A | Independent control not executed |
| **Candidate 3: Connors RSI(2)** | **NOT RUN / NOT DEMONSTRATED** | N/A | N/A | -16.33% | N/A | Not executed (net expectancy is negative) |

> **Cost Metric Denominator Clarification:**  
> In all tables, the cost metric is defined as **Cumulative transaction costs paid as a percentage of starting capital** (`total_costs_paid / initial_capital * 100`). It measures total frictional drag over the 4.25-year evaluation period, not an annualized fee.

---

## 6. Turnover-Buffer Control Analysis (Reconciled)

| Strategy | Metric | No Buffer (Top 20) | Buffered (Rank 1–30) | Differential / Frictional Savings |
| :--- | :--- | :---: | :---: | :--- |
| **C1b Baseline** | Monthly Turnover | 38.69% | **23.53%** | **-39.2% turnover reduction** |
| | Cumulative Costs Paid | ₹19,218 | **₹11,634** | **₹7,584 fee savings** |
| | Annualized Net Return | +16.11% | **+17.51%** | **+1.40% net alpha enhancement** |
| | Maximum Drawdown | 9.25% | **9.02%** | Lower drawdown |
| **Candidate 1 (Market-Sector Reg-Alpha)** | Monthly Turnover | 38.08% | **24.73%** | **-35.1% turnover reduction** |
| | Cumulative Costs Paid | ₹18,391 | **₹12,416** | **₹5,975 fee savings** |
| | Annualized Net Return | +13.49% | **+16.88%** | **+3.39% net alpha enhancement** |
| | Maximum Drawdown | 10.18% | **8.31%** | **Lowest drawdown across all strategies** |
| **Candidate 2 (Frog-in-the-Pan)** | Monthly Turnover | 42.78% | **28.97%** | **-32.3% turnover reduction** |
| | Cumulative Costs Paid | ₹19,342 | **₹13,266** | **₹6,076 fee savings** |
| | Annualized Net Return | +12.42% | **+12.83%** | **+0.41% net return gain** |

---

## 7. Scale Comparison: Practical Scale (₹17,500) vs Research Capital (₹500,000)

| Strategy | ₹500k Net Ann % | ₹17.5k Net Ann % | ₹500k Cost Drag % | ₹17.5k Cost Drag % | Drag Differential |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **C1b Baseline** | +16.11% | +3.59% | 3.84% | 7.88% | **+4.04%** |
| **Candidate 1 (Market-Sector Reg-Alpha)** | +13.49% | +2.83% | 3.68% | 7.76% | **+4.08%** |
| **Candidate 2 (Frog-in-the-Pan)** | +12.42% | +1.18% | 3.87% | 9.19% | **+5.32%** |
| **Candidate 3 (Connors RSI(2))** | -5.28% | -27.28% | 33.11% | 76.13% | **+43.02%** |

### Scale Analysis
1. Flat ticket charges (DP charges of ₹15.93 per sold scrip) disproportionately penalize small accounts. On a ₹1,750 position, ₹15.93 represents a **0.91% friction tax on every exit**, completely destroying daily swing trading.
2. Whole-share integer sizing constraints prevent small accounts from purchasing high-priced equities (MRF, UltraTech, Shree Cement), creating cash drag.
3. Monthly buffered momentum strategies are the only architectures capable of generating positive net returns at ₹17,500 scale.

---

## 8. Final Decision Classifications

In strict accordance with the Section J Decision Protocol:

1. **`REJECTED`:**
   - **Candidate 3 (Connors RSI(2)):** Conclusively rejected. Generates negative mathematical currency expectancy ($-₹71.67$ per trade), net profit factor $0.85$, and catastrophic cost drag.
   - **Candidate 2 (Frog-in-the-Pan):** Rejected. Underperforms conventional baseline momentum by 360 to 460 bps and fails bootstrap significance.
2. **`INCONCLUSIVE`:**
   - **Candidate 1 (Market-Sector Regression-Alpha):** Classified as inconclusive. While it demonstrates strong exploratory empirical risk mitigation (**8.31% maximum drawdown**, Sharpe 1.52, Sortino 2.41), it cannot be validated because all historical tests on this dataset lack an independent untouched holdout.
3. **`NOT IMPLEMENTED`:**
   - **Published Blitz, Huij & Martens (2011) Residual Momentum:** Formal paper specification is not implemented due to lack of Indian Fama-French SMB/HML factor data and pre-2021 fundamentals.
4. **`VALIDATED`:**
   - **ZERO CANDIDATES.** Validation strictly requires prospective forward paper evaluation satisfying pre-registered gates over at least 8 weeks.
5. **Trading Authorization:**
   - **No candidate is authorized for live trading or automated order placement.**

---

## 9. Audit Manifest, Hashes & Test Outcomes

- **Pre-Registration Commit:** `9a58dbf048a8ffcc3fccbd431d3933f19f6d8726`
- **Pre-Registration Hash (`PREREG.md`):** `f5d87c02330a7967dba34934ceabbe99df48c09e93c99a3d74bc910710e6d69d`
- **Universe File (`research_universe_v1.csv`):** `fbba1bc176a5dd6c0d5f2527dc7599f3c1d0117158e54fcd6b8f94a9542ee72e`
- **Data Snapshot (`research_snapshot_20261106.parquet`):** `f6e564a5c3d01f755c5fc0e1356346491c56d66312a13c0da64e421ff8c0c58f`
- **Benchmark Series (`benchmark_series.parquet`):** `c9ed07ede1e98fdf7b869cfc8ffa749d41e68a9781dfebb31c7685325f4093be`
- **Phase 2 Report (`PHASE2_FINAL_REPORT.md`):** `5ddb610b79dcc004f332c187a3e99473284bffaf049728f287e3b0623763bd5d` (strictly unmodified)
- **Machine-Readable Results (`strategy_comparison.json`):** `2395910a186c29189093d96c7609d7f5ed0f485de79260055143ee1a50fba28d`
- **Run Manifest (`run_manifest.json`):** Fully documented with execution timestamps.
- **Unit Tests (`backend/tests/test_cycle3_strategies.py`):** 5 tests executed, **5 passed in 0.10s** (regression fixture math, Information Discreteness smooth vs jump fixture, Connors RSI2 indicators, no-lookahead truncation invariance, cost model statutory invariance).

---

## 10. Explicit Unresolved Limitations

1. **Current-Constituent Survivorship Bias:** Universe is restricted to 70 surviving NSE equities.
2. **Snapshot Window Coverage:** 5.3 years (July 2021 – November 2026), omitting the 2018–2020 bear market.
3. **Absence of Untouched Holdout:** Because the historical snapshot was inspected in prior cycles, all historical backtest results remain exploratory.
4. **Factor Library Gaps:** Fama-French SMB and HML factors for Indian equities do not exist in the repository, precluding faithful replication of multi-factor asset pricing models.

**END OF REPORT — RESEARCH CYCLE 3 FINAL RECONCILIATION CLOSED**
