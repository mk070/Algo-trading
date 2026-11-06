# PHASE 2: PRE-REGISTERED STRATEGY VALIDATION — FINAL FROZEN RESEARCH REPORT
**Document Status:** FROZEN QUALITY-CONTROLLED REPORT (Final Milestone Delivery)  
**Execution Timestamp:** `2026-11-06T12:05:04Z` (UTC)  
**Research Mode:** Strictly Offline Research — No Live Trading, No Automatic Order Placement  
**Source Execution Artifact:** [`research/phase2_results.json`](file:///d:/web%20development/saas-projects/Algo-trading/research/phase2_results.json)  
**Pre-Registration Specification:** [`research/PREREG.md`](file:///d:/web%20development/saas-projects/Algo-trading/research/PREREG.md) (SHA256: `b526b03b8542b46f7f1fbc7b79fc73aea41458618a461c1f4d0f93d4963e39dc` [Git HEAD blob]; initial creation SHA256: `7fb0d96d9d1391ab4d0991d7db391b8ff04663fc7799e1074b36de88be3aa91f` prior to EOF newline normalization in commit `7558f93`)  
**Frozen Research Universe:** [`data/universe/research_universe_v1.csv`](file:///d:/web%20development/saas-projects/Algo-trading/data/universe/research_universe_v1.csv) (SHA256: `fbba1bc176a5dd6c0d5f2527dc7599f3c1d0117158e54fcd6b8f94a9542ee72e`)  
**Frozen Parquet Snapshot:** [`data/research/research_snapshot_20261106.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/research_snapshot_20261106.parquet) (SHA256: `f6e564a5c3d01f755c5fc0e1356346491c56d66312a13c0da64e421ff8c0c58f`)  
**Dedicated Benchmark Series:** [`data/research/benchmark_series.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/benchmark_series.parquet) (SHA256: `c9ed07ede1e98fdf7b869cfc8ffa749d41e68a9781dfebb31c7685325f4093be`)  
**Git Tree / Execution Baseline:** [`18fe7b66f93a353d73bca1813245cd17e0d1f451`](file:///d:/web%20development/saas-projects/Algo-trading) (Report finalized and frozen at commit `0ac141c786f5fc196ed9e71def95adb8a7554ba6`)

---

## 1. Executive Summary & Required Final Decision

This final frozen report represents the consolidated, verified, and reconciled record of the Phase 2 Pre-Registered Strategy Validation cycle. All gate evaluations are derived programmatically from saved execution records and verified against pre-registered acceptance criteria.

### Standardized Evidence Classifications
- **`PASS`:** Pre-registered criterion is fully satisfied with conforming, measured evidence.
- **`FAIL`:** An observed empirical result directly violates the required acceptance threshold.
- **`INCONCLUSIVE`:** Insufficient sample size or statistical power precludes a definitive determination.
- **`NOT DEMONSTRATED`:** The required experiment, independent data window, or pre-registered benchmark evidence is absent from recorded execution artifacts.

### Definitive Final Decision
**Zero candidates qualify for `PASS`.**
1. **Candidate C1a India (Always Invested):** Fails on maximum drawdown ratio ($1.40\times$ vs. $1.20\times$ pre-registered ceiling) $\rightarrow$ **`FAIL`**.
2. **Candidate C1b India (Regime Filtered):** Demonstrates positive in-sample excess return (+8.81%) and controlled drawdown (0.59x), but lacks an untouched holdout, random control simulation, sensitivity suite, pre-registered bootstrap CI, and a 4th complete calendar year $\rightarrow$ **`NOT DEMONSTRATED`**.
3. **Candidate C1a US (Always Invested):** Meets excess return (+10.00%), drawdown (0.62x), and random-control (97.6th percentile) gates, but lacks pre-registered benchmark bootstrap confidence intervals, sensitivity testing, an untouched holdout, and a 4th complete calendar year $\rightarrow$ **`NOT DEMONSTRATED`**.
4. **Candidate C1b US (Regime Filtered):** Fails on observed excess return ($-2.23\%$ vs. pre-registered benchmark) $\rightarrow$ **`FAIL`**.
5. **Candidate C2 (VCP Breakout):** Inadequate sample sizes (7 completed trades in India, 12 in the US) strictly mandate an **`INCONCLUSIVE`** verdict.
6. **Kill Rule Enforcement:** The pre-registered kill rule remains in full effect. No strategy search, parameter tuning, indicator additions, paper trading, or live trading is authorized.

---

## 2. Research Scope, Universe Reconciliation & Limitations

### One-Time Research Universe Reconciliation (114 Snapshot vs. 105 Universe)
The strategy research universe was frozen before candidate testing at [`data/universe/research_universe_v1.csv`](file:///d:/web%20development/saas-projects/Algo-trading/data/universe/research_universe_v1.csv) (105 equities, SHA256: `fbba1bc1...`).

| Symbol | Category / Type | Rows in Snapshot | Provider / Source | Reason Present in Snapshot but Excluded from Strategy Universe |
|---|---|:---:|:---:|---|
| `AVGO` | US Equity | 252 | `alpaca` | Ad-hoc US equity ingested during API validation; not a member of approved S&P 500/400 sample CSVs. |
| `BSE:SENSEX` | Index Benchmark | 246 | `yfinance` | Macro index ticker ingested for market overview monitoring; not an individual tradeable equity. |
| `MUTHOOTFIN`| Indian NSE Equity | 270 | `yfinance` | Ingested during single-scrip provider testing; not part of approved Nifty 100/150 constituent subsets. |
| `PIDILITIND` | Indian NSE Equity | 269 | `yfinance` | Ingested during single-scrip provider testing; not part of approved Nifty 100/150 constituent subsets. |
| `SENSEX` | Index Benchmark | 246 | `yfinance` | Alias ticker for BSE Sensex index; macro benchmark, not a tradeable equity. |
| `SPY` | US Index ETF | 252 | `alpaca` | Exchange-Traded Fund (S&P 500 ETF Trust); passive benchmark instrument, not an equity constituent. |
| `TMPV` | Test Fixture | 270 | `angelone`, `yfinance` | Synthetic/test symbol created during integration pipeline debugging; non-standard instrument. |
| `^GSPC` | Index Benchmark | 277 | `yfinance` | Yahoo Finance ticker for S&P 500 Index; broad market benchmark, not an equity constituent. |
| `^NSEI` | Index Benchmark | 269 | `yfinance` | Yahoo Finance ticker for Nifty 50 Index; broad market benchmark, not an equity constituent. |

### Reconciliation of Historical Row Count
- **Total Physical Snapshot Records:** Exactly **141,040 rows** in [`data/research/research_snapshot_20261106.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/research_snapshot_20261106.parquet).
- **Approved 105 Universe Equities:** Exactly **138,689 rows**.
- **Excluded 9 Macro / Fixture Symbols:** Exactly **2,351 rows**.
- **Explanation of Earlier 138,754 vs 2,284 Count:** In commit `4b052ab`, narrative documentation reported 138,754 and 2,284 (total 141,038). Two rows (`MSFT` and `NVDA` on 2026-11-05 at 15:27 UTC) were ingested subsequently, while an accounting partition shift occurred when 67 purged synthetic fixtures were incorrectly offset against the universe partition. The actual Parquet snapshot contains 138,689 universe rows and 2,351 non-universe rows.

### Data Limitations & Bias Disclosures
1. **Evaluation Period:** Strategy rebalances run from August 30, 2022 through October 30, 2026 (51 monthly rebalances). Data coverage spans July 19, 2021 through November 5, 2026 (5.3 years). The **2018–2020 stress period was unavailable** under connected provider tiers and was **not tested**.
2. **Calendar Years:** Only **three complete calendar years** exist in the evaluation window (2023, 2024, 2025). The year 2022 (5 months: Aug–Dec) and 2026 (10 months: Jan–Oct) are partial calendar years.
3. **Survivorship Bias:** The 105 universe symbols represent active current constituents. Delistings between 2021 and 2026 are not captured.
4. **Alpaca IEX Volume:** US historical volume reflects IEX-only prints (~2.5% of tape), rendering US dollar-volume liquidity screening exploratory.
5. **Untouched Holdout Status:** The May 1, 2026 – November 5, 2026 window was previously inspected in canonical `task-9156`. Genuinely untouched historical data is unavailable.

---

## 3. Benchmark Methodology Verification

The pre-registration mandated total-return benchmarks (`NIFTYBEES.NS` for India; 50/50 rebalanced blend of `SPY` and `MDY` for the US). In [`backend/run_phase2_validation.py`](file:///d:/web%20development/saas-projects/Algo-trading/backend/run_phase2_validation.py#L92), the runner directly evaluated against `^NSEI` (Nifty 50 price index) and `^GSPC` (S&P 500 price index).

Without rerunning simulations, the exact returns and drawdowns of the pre-registered benchmarks were calculated from [`data/research/benchmark_series.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/benchmark_series.parquet) over the identical monthly evaluation dates:

| Market | Specification | Series Measured in Runner | Pre-Registered Benchmark in Frozen Data | Annualized Return | Maximum Drawdown | Impact on Gates |
|---|---|---|---|:---:|:---:|---|
| **India** | `NIFTYBEES.NS` / Nifty 500 TRI | `^NSEI` (Price Index) | `NIFTYBEES.NS` (Total Return ETF) | **+7.42%** *(vs ^NSEI +7.20%)* | **16.11%** *(vs ^NSEI 17.23%)* | Bootstrap & sensitivity excess returns were computed against `^NSEI`; gates marked **`NOT DEMONSTRATED`** under strict pre-registered benchmark. |
| **US** | 50/50 SPY + MDY Total Return | `^GSPC` (Price Index) | Monthly 50/50 Rebalanced SPY + MDY | **+14.83%** *(vs ^GSPC +15.36%)* | **24.26%** *(vs ^GSPC 25.43%)* | S&P 400 mid-cap blend was omitted in runner; benchmark-relative bootstrap & excess gates marked **`NOT DEMONSTRATED`**. |

---

## 4. Candidate C1: Cross-Sectional Momentum (Portfolio-Level Gates)

Candidate C1 rebalances monthly on the final trading day, ranking the top 20 equities by 12-1 momentum ($T-21$ / $T-252$ - 1), holding equal weights with whole-share execution at next-session Open with adverse slippage and realistic fees.

### Performance Summary Table

| Metric | C1a India (Always Invested) | C1b India (Regime Filtered) | C1a US (Always Invested) | C1b US (Regime Filtered) | C1a India Practical (₹17,500) |
|---|---:|---:|---:|---:|---:|
| **Capital Allocation** | ₹500,000 | ₹500,000 | $50,000 | $50,000 | ₹17,500 (Top 5) |
| **Annualized Net Return** | +12.66% | +16.23% | +24.83% | +12.60% | +13.06% |
| **Pre-Registered Benchmark Return** | +7.42% | +7.42% | +14.83% | +14.83% | +7.42% |
| **Annualized Excess Return (Pre-Reg)** | **+5.24%** | **+8.81%** | **+10.00%** | **-2.23%** | **+5.64%** |
| **Annualized Excess Return (Runner)** | +5.47% | +9.04% | +9.47% | -2.75% | +5.86% |
| **Maximum Drawdown** | 22.62% | 9.46% | 15.00% | 15.58% | 24.11% |
| **Pre-Reg Benchmark Max Drawdown** | 16.11% | 16.11% | 24.26% | 24.26% | 16.11% |
| **Drawdown Ratio (Port / Bench)** | **1.40x** | **0.59x** | **0.62x** | **0.64x** | **1.50x** |
| **Sharpe Ratio (Rf = 5%)** | 0.47 | 0.99 | 1.10 | 0.48 | 0.49 |
| **Total Costs Paid** | ₹20,922.76 | ₹18,157.08 | $5,931.07 | $6,073.86 | ₹1,786.28 |
| **Cost Drag (% of Capital)** | 4.18% | 3.63% | 11.86% | 12.15% | **10.21%** |
| **Random Control Percentile (1,000 runs)**| **96.0th** | *Not Run* | **97.6th** | *Not Run* | — |
| **Complete Calendar Years (2023–2025)**| 2 of 3 pos. | 2 of 3 pos. | 2 of 3 pos. | 2 of 3 pos. | 2 of 3 pos. |
| **Partial Years Included (2022 & 2026)**| 3 of 5 pos. | 4 of 5 pos. | 4 of 5 pos. | 3 of 5 pos. | 3 of 5 pos. |
| **Sensitivity Robustness (Costs / Slip / Params)**| **6/6 Profitable** | *Not Run* | *Not Run* | *Not Run* | — |

### Final Corrected C1 Acceptance-Gate Table

| Gate | Pre-Registered Requirement | C1a India | C1b India | C1a US | C1b US |
|---|---|:---:|:---:|:---:|:---:|
| **Gate 1** | Ann. Net Excess Return $\ge +2.0\%$ vs Pre-Reg Benchmark | **PASS** *(+5.24%)* | **PASS** *(+8.81%)* | **PASS** *(+10.00%)* | **FAIL** *(-2.23%)* |
| **Gate 2** | Bootstrap 95% CI Lower Bound $> 0.0\%$ (Pre-Reg Bench) | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** |
| **Gate 3** | Maximum Drawdown $\le 1.2 \times$ Pre-Reg Benchmark DD | **FAIL** *(1.40x)* | **PASS** *(0.59x)* | **PASS** *(0.62x)* | **PASS** *(0.64x)* |
| **Gate 4** | Positive Annual Excess in $\ge 60\%$ Full Years (Min 4 Yrs) | **NOT DEMONSTRATED** *(3 yrs avail)* | **NOT DEMONSTRATED** *(3 yrs avail)* | **NOT DEMONSTRATED** *(3 yrs avail)* | **NOT DEMONSTRATED** *(3 yrs avail)* |
| **Gate 5** | Genuinely Untouched Independent Holdout | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** |
| **Gate 6** | Cost (+25%) & Slippage ($\times 2$) Robustness | **PASS** *(+12.06% net)* | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** |
| **Gate 7** | Matched Random Control ($> 95\text{th}$ percentile) | **PASS** *(96.0th)* | **NOT DEMONSTRATED** | **PASS** *(97.6th)* | **NOT DEMONSTRATED** |
| **Gate 8** | Parameter Sensitivity ($\ge 70\%$ neighbors profitable) | **PASS** *(6/6 prof.)* | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** |
| **VERDICT**| **Overall Candidate Verdict** | **`FAIL`** | **`NOT DEMONSTRATED`** | **`NOT DEMONSTRATED`** | **`FAIL`** |

### Detailed Candidate Notes:
1. **C1a India:** Fails Gate 3 directly because observed maximum drawdown (22.62%) is **$1.40\times$** the pre-registered benchmark's drawdown (16.11%), violating the $1.20\times$ ceiling. Satisfies Gate 1 (+5.24%), Gate 6 (+12.06% net under $2\times$ slippage), Gate 7 (96.0th percentile in 1,000 random portfolios), and Gate 8 (6 of 6 variations profitable). Gate 4 is NOT DEMONSTRATED because only 3 complete calendar years exist. Overall Verdict: **`FAIL`**.
2. **C1b India:** Demonstrates strong in-sample alpha (+8.81% excess return, 0.59x drawdown ratio), but lacks pre-registered benchmark bootstrap calculations, random controls, sensitivity testing, an untouched holdout, and a 4th complete calendar year. Overall Verdict: **`NOT DEMONSTRATED`** (disqualified from PASS).
3. **C1a US:** Meets Gate 1 (+10.00% excess return), Gate 3 (0.62x drawdown ratio), and Gate 7 (97.6th percentile in 1,000 random portfolios). Has no observed failure against pre-registered criteria. However, because required independent evidence (pre-registered bootstrap, sensitivity runs, untouched holdout, 4th complete year) remains missing, its overall status is **`NOT DEMONSTRATED`** (disqualified from PASS).
4. **C1b US:** Directly fails Gate 1 (observed annualized net excess return of $-2.23\%$ vs. the pre-registered benchmark). Gate 4 is NOT DEMONSTRATED due to fewer than four complete calendar years. Overall Verdict: **`FAIL`**.

---

## 5. Candidate C2: VCP Breakout & Control A (Trade-Level Gates)

Candidate C2 (VCP Breakout) and Control A (55-day breakout) were evaluated across 105 universe symbols over 1,316 sessions (India) and 1,333 sessions (US).

### Trade-Level Diagnostic Statistics

| Candidate / Baseline | Market | Completed Trades | Gross P&L | Total Costs | Net P&L | Expectancy (R) | Profit Factor | Max Drawdown | Win Rate |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Candidate C2 (VCP Breakout)** | India | 7 | -₹149.80 | ₹143.79 | -₹293.59 | -0.64R | 0.08 | 1.70% | 14.3% |
| **Candidate C2 (VCP Breakout)** | US | 12 | +$854.86 | $212.33 | +$642.53 | +0.72R | 2.40 | 1.90% | 58.3% |
| **Control A (55-Day Breakout)** | India | 27 | -₹611.52 | ₹566.13 | -₹1,177.65 | -0.66R | 0.15 | 6.70% | 18.5% |
| **Control A (55-Day Breakout)** | US | 43 | +$4.69 | $752.91 | -$748.22 | -0.22R | 0.67 | 9.70% | 23.3% |

### Corrected C2 & Control Acceptance-Gate Table

| Gate | Pre-Registered Requirement | Candidate C2 India | Candidate C2 US | Control A India (Diagnostic) | Control A US (Diagnostic) |
|---|---|---|---|---|---|
| **Gate 1** | Minimum Sample Size $\ge 150$ Trades | **INCONCLUSIVE** *(7 trades)* | **INCONCLUSIVE** *(12 trades)* | **INCONCLUSIVE** *(27 trades)* | **INCONCLUSIVE** *(43 trades)* |
| **Gate 2** | Net Expectancy $\ge +0.15R$ | Observed -0.64R; below threshold descriptively, but insufficient sample for validation | Observed +0.72R; above threshold descriptively, but insufficient sample for validation | Observed -0.66R; below threshold descriptively, but insufficient sample for validation | Observed -0.22R; below threshold descriptively, but insufficient sample for validation |
| **Gate 3** | Profit Factor $\ge 1.30$ | Observed PF 0.08; below threshold descriptively, but insufficient sample for validation | Observed PF 2.40; above threshold descriptively, but insufficient sample for validation | Observed PF 0.15; below threshold descriptively, but insufficient sample for validation | Observed PF 0.67; below threshold descriptively, but insufficient sample for validation |
| **Gate 4** | Maximum Drawdown $\le 20.0\%$ | Observed 1.70%; within threshold descriptively, but insufficient sample for validation | Observed 1.90%; within threshold descriptively, but insufficient sample for validation | Observed 6.70%; within threshold descriptively, but insufficient sample for validation | Observed 9.70%; within threshold descriptively, but insufficient sample for validation |
| **Gate 5** | Period & Yearly Stability ($\ge 3$ of 4 yrs) | Observed 0/4 yrs positive; below threshold descriptively, but insufficient sample for validation | Observed 2/4 yrs positive; below threshold descriptively, but insufficient sample for validation | Observed 0/4 yrs positive; below threshold descriptively, but insufficient sample for validation | Observed 1/4 yrs positive; below threshold descriptively, but insufficient sample for validation |
| **Gate 6** | Walk-Forward Robustness Across Folds | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** |
| **Gate 7** | Genuinely Untouched Independent Holdout | **NOT DEMONSTRATED** *(No Data)* | **NOT DEMONSTRATED** *(No Data)* | **NOT DEMONSTRATED** *(No Data)* | **NOT DEMONSTRATED** *(No Data)* |
| **Gate 8** | Matched Random Entry ($> 95\text{th}$ percentile)| **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** | **NOT DEMONSTRATED** |
| **VERDICT** | **Overall Candidate Status** | **`INCONCLUSIVE`** | **`INCONCLUSIVE`** | **`INCONCLUSIVE`** | **`INCONCLUSIVE`** |

*C2 Methodological Rule Applied:*
- Gate 1 for C2 India (7 trades) and C2 US (12 trades) is classified as **`INCONCLUSIVE`** because inadequate sample size prevents statistical validation under pre-registered rules.
- Descriptive observations (e.g. +0.72R expectancy and 2.40 PF in C2 US, or -0.64R expectancy in C2 India) are explicitly documented as descriptive observations only and are not presented as acceptance PASS or FAIL verdicts.
- Control A (55-day breakout) is retained strictly as a diagnostic technical baseline.

---

## 6. Practical Scale Diagnostic (India ₹17,500 Capital)
- **Portfolio Construction:** Top 5 stocks, whole shares only, Zerodha delivery cost model.
- **Capital Allocation:** ₹17,500 baseline capital.
- **Net Performance:** Annualized net return: +13.06% (Cumulative: +68.47%, final equity ₹29,481.39).
- **Cost Drag Impact:** Total costs paid: ₹1,786.28 $\rightarrow$ **10.21% of capital** (compared to 4.18% on the ₹500,000 portfolio).
- **Finding:** Discrete share indivisibility and fixed depository participant charges (₹15.93 per sold scrip) impose severe cost friction on small accounts, confirming pre-registered expectations.

---

## 7. Execution Traceability & Verification Record

### Files Inspected:
- [`research/PREREG.md`](file:///d:/web%20development/saas-projects/Algo-trading/research/PREREG.md)
- [`research/phase2_results.json`](file:///d:/web%20development/saas-projects/Algo-trading/research/phase2_results.json)
- [`data/universe/research_universe_v1.csv`](file:///d:/web%20development/saas-projects/Algo-trading/data/universe/research_universe_v1.csv)
- [`data/research/research_snapshot_20261106.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/research_snapshot_20261106.parquet)
- [`data/research/benchmark_series.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/benchmark_series.parquet)
- [`backend/run_phase2_validation.py`](file:///d:/web%20development/saas-projects/Algo-trading/backend/run_phase2_validation.py)

### Files Modified:
- [`research/PHASE2_FINAL_REPORT.md`](file:///d:/web%20development/saas-projects/Algo-trading/research/PHASE2_FINAL_REPORT.md) *(frozen final standalone report deliverable)*

### Protected Artifact Integrity Confirmation:
- `research/PREREG.md` was **NOT modified** (SHA256: `b526b03b8542b46f7f1fbc7b79fc73aea41458618a461c1f4d0f93d4963e39dc`).
- `research/phase2_results.json` was **NOT modified** (SHA256: `b17c2bb14d1d67866012ad3fc3c3e2485e081a64696b2ab9a9fd2cb508722759`).
- `data/universe/research_universe_v1.csv` was **NOT modified** (SHA256: `fbba1bc176a5dd6c0d5f2527dc7599f3c1d0117158e54fcd6b8f94a9542ee72e`).
- `data/research/research_snapshot_20261106.parquet` was **NOT modified** (SHA256: `f6e564a5c3d01f755c5fc0e1356346491c56d66312a13c0da64e421ff8c0c58f`).
- `data/research/benchmark_series.parquet` was **NOT modified** (SHA256: `c9ed07ede1e98fdf7b869cfc8ffa749d41e68a9781dfebb31c7685325f4093be`).
- Zero backtests, Monte Carlo simulations, bootstrap resamples, or parameter variations were rerun.

---

## 8. Definitive Conclusion & Kill Rule Enforcement

Under the complete pre-registered validation protocol:
1. **Zero candidates qualify for `PASS`.**
2. **The strategy-search kill rule remains strictly in force.**
3. **No new strategy research, parameter tuning, indicator additions, paper trading, or live execution is authorized.**
4. **Final Recommendation:** Capital allocation should be directed toward passive index investing, and platform usage should remain strictly confined to research and visualization.
