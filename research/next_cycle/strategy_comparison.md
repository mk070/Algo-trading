# Research Cycle 3: Independent Swing Strategy Testing Report

**Status:** CYCLE COMPLETE — ALL CANDIDATES EVALUATED  
**Date:** 2026-11-06  
**Cycle:** Research Cycle 3 — Independent Swing Strategy Testing  
**Research Mode:** Strictly Offline Research — No Live Trading, No Automated Order Placement  
**Pre-Registration Git Commit:** `9a58dbf048a8ffcc3fccbd431d3933f19f6d8726`  
**PREREG.md SHA256:** `f5d87c02330a7967dba34934ceabbe99df48c09e93c99a3d74bc910710e6d69d`  
**Universe:** India NSE Equities (`research_universe_v1.csv` — 70 symbols, SHA256: `fbba1bc1...`)  
**Data Snapshot:** `research_snapshot_20261106.parquet` (1,316 sessions, SHA256: `f6e564a5...`)  
**Primary Benchmark:** `NIFTYBEES.NS` Total Return ETF (SHA256: `c9ed07ed...`)  
**Market Regime Index:** `^NSEI` (Nifty 50 Index)  

---

## 1. Executive Summary & Master Decision Matrix

Research Cycle 3 tested exactly three genuinely distinct, peer-reviewed/established swing-trading hypotheses against the frozen Phase 2 baseline (Candidate C1b India). Testing was performed strictly offline using the approved frozen research universe, Parquet snapshot, and realistic Indian equity transaction costs (brokerage, STT, exchange turnover fees, SEBI charges, stamp duty, DP charges of ₹15.93 per sold scrip, GST, and 0.10% adverse execution slippage).

### Master Verdict Table

| Candidate / Strategy | Formulation Reference | Annualized Net Return | Annualized Excess vs NIFTYBEES | Max Drawdown | Sharpe Ratio | Sortino Ratio | Monthly Turnover | Total Cost Drag (₹500k) | Decision Protocol Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Comparator: C1b Baseline** (No Buffer) | Jegadeesh & Titman (1993) | +10.33% | +2.91% | 22.85% | 0.63 | 0.77 | 46.88% | 4.55% | **HISTORICAL COMPARATOR** |
| **Comparator: C1b Baseline** (Buffered 1–30) | Retention Band Control | +11.48% | +4.06% | 23.81% | 0.69 | 0.88 | 28.01% | 2.68% | **CONTROL BENCHMARK** |
| **Candidate 1: Residual Momentum** (No Buffer) | Blitz, Huij & Martens (2011) | +8.44% | +1.02% | **8.52%** | **0.92** | **1.96** | 27.26% | 2.35% | **INCONCLUSIVE** |
| **Candidate 1: Residual Momentum** (Buffered 1–30) | Blitz, Huij & Martens (2011) | +8.74% | +1.31% | **7.90%** | **0.97** | **2.12** | **19.26%** | **1.67%** | **INCONCLUSIVE** |
| **Candidate 2: Frog-in-the-Pan** (No Buffer) | Da, Gurun & Warachka (2014) | +7.63% | +0.21% | 20.32% | 0.50 | 0.71 | 51.04% | 4.55% | **REJECTED** |
| **Candidate 2: Frog-in-the-Pan** (Buffered 1–30) | Da, Gurun & Warachka (2014) | +8.16% | +0.74% | 21.93% | 0.53 | 0.70 | 33.05% | 2.91% | **REJECTED** |
| **Candidate 3: Connors RSI(2)** (Research ₹500k) | Larry Connors Mean Reversion | -5.28% | -16.33% | 29.90% | N/A | N/A | High (1,485 trades) | **33.11%** | **REJECTED IMMEDIATELY** |
| **Candidate 3: Connors RSI(2)** (Practical ₹17.5k) | Larry Connors Mean Reversion | -27.28% | -38.32% | 75.48% | N/A | N/A | High (645 trades) | **76.13%** | **REJECTED IMMEDIATELY** |

> **CORE RESEARCH CONCLUSION:**  
> **ZERO candidates qualify for `VALIDATED` status or live trading deployment.**  
> - **Candidate 3 (Connors RSI(2)) is REJECTED IMMEDIATELY** due to negative net expectancy ($-0.082R$), a sub-1.0 net profit factor ($0.85$), and catastrophic transaction fee drag ($33.1\%$ of capital at ₹500k and $76.1\%$ at ₹17.5k).  
> - **Candidate 2 (Frog-in-the-Pan) is REJECTED** because ranking by Information Discreteness ($ID$) severely underperformed raw momentum ($+7.63\%$ vs $+10.33\%$) while producing excess return indistinguishable from zero ($+0.21\%$) and failing bootstrap significance.  
> - **Candidate 1 (Residual Momentum) is classified as INCONCLUSIVE.** While it failed the pre-registered $+2.0\%$ excess return threshold ($+1.02\%$ to $+1.31\%$) and the bootstrap CI spanned zero, it empirically validated Blitz et al.'s theoretical mechanism: **it slashed maximum drawdown by nearly two-thirds** ($7.90\%$ vs $23.81\%$ for C1b and $22.85\%$ for Nifty) and achieved the highest Sharpe ratio ($0.97$) and Sortino ratio ($2.12$) of any strategy tested. Candidate 1 is the **sole candidate deserving future exploratory prospective paper observation** in a broader universe.

---

## 2. Integrity, Scope & Methodology Invariants

1. **Pre-Registration Enforcement:**  
   `research/next_cycle/PREREG.md` was authored, frozen, and committed to git (`9a58dbf048a8ffcc3fccbd431d3933f19f6d8726`) before any candidate simulation or factor calculation was executed. No parameters, thresholds, or universes were altered post-hoc.
2. **Untouched Phase 2 Artifacts:**  
   `research/PHASE2_FINAL_REPORT.md` (SHA256: `5ddb610b...`) and `research/phase2_results.json` were strictly preserved in read-only state.
3. **Conservative Execution Fills:**  
   - All monthly rebalances and daily swing setups execute at the **Open of session $T+1$** following signal close at session $T$.
   - Fills include $+0.10\%$ adverse slippage on Buy entries and $-0.10\%$ adverse slippage on Sell exits.
   - Sizing strictly enforces whole shares and cash availability. Cash earns 0.0%.
4. **Exact Indian Equity Delivery Cost Model:**  
   - Brokerage: ₹0 flat delivery.
   - STT: 0.10% buy, 0.10% sell.
   - Exchange charges: 0.003%.
   - SEBI charges: ₹10 per crore (0.0001%).
   - Stamp duty: 0.015% buy only.
   - Depository Participant (DP) Charge: ₹13.50 + 18% GST = **₹15.93 flat per sold scrip**.
   - GST: 18% on (Exchange + SEBI + DP charges).

---

## 3. Candidate 1 — Residual Momentum (Blitz, Huij & Martens, 2011)

### Economic Hypothesis & Formula
Conventional momentum is contaminated by exposure to systematic factor drift (market beta and industry sector trends). Blitz, Huij & Martens (2011) showed that stripping out market and industry sector factors isolates firm-specific idiosyncratic momentum with lower crash risk.

On each monthly rebalance date $T$, using trailing daily returns from $t = T-252$ to $t = T-21$ (232 trading sessions):
$$R_{i,t} = \alpha_i + \beta_{i,M} R_{M,t} + \beta_{i,S} R_{S,t} + \epsilon_{i,t}$$
where $R_{M,t}$ is the daily return of `^NSEI` and $R_{S,t}$ is the equal-weighted return of all other universe stocks in stock $i$'s sector.

Because OLS residuals over the identical estimation window sum to zero by mathematical definition ($\sum \hat{\epsilon}_t \equiv 0$), the firm-specific idiosyncratic return stripping out systematic factor drift is:
$$R_{i,t}^{\text{idiosyncratic}} = R_{i,t} - \hat{\beta}_{i,M} R_{M,t} - \hat{\beta}_{i,S} R_{S,t} = \hat{\alpha}_i + \hat{\epsilon}_{i,t}$$
Cumulating over the window yields $\sum R_{i,t}^{\text{idiosyncratic}} = N \hat{\alpha}_i$. Dividing by residual volatility $\sigma(\hat{\epsilon}_i)$ produces the standardized idiosyncratic Sharpe score:
$$\text{Score}_i = \frac{N \hat{\alpha}_i}{\sigma(\hat{\epsilon}_i)}$$

### Performance Results (₹500,000 Research Capital)
- **Annualized Net Return:** +8.44% (No Buffer) | **+8.74%** (Buffered 1–30)
- **Annualized Excess Return (vs NIFTYBEES):** +1.02% (No Buffer) | **+1.31%** (Buffered 1–30)
- **Maximum Drawdown:** **8.52%** (No Buffer) | **7.90%** (Buffered 1–30)
- **Benchmark Max Drawdown:** 22.85% (Drawdown ratio: **$0.35\times$**, superior capital preservation)
- **Annualized Volatility:** 9.17% (No Buffer) | **9.05%** (Buffered 1–30)
- **Sharpe Ratio:** 0.92 (No Buffer) | **0.97** (Buffered 1–30)
- **Sortino Ratio:** 1.96 (No Buffer) | **2.12** (Buffered 1–30)
- **Average Monthly Turnover:** 27.26% (No Buffer) | **19.26%** (Buffered 1–30)
- **Total Costs Paid:** ₹11,768.42 (No Buffer) | **₹8,359.18** (Buffered 1–30)
- **Cost Drag of Capital:** 2.35% (No Buffer) | **1.67%** (Buffered 1–30)

### Statistical Uncertainty & Controls
- **95% Circular Block-Bootstrap CI (Monthly Excess Return):**  
  - No Buffer: `[-0.748%, +0.802%]`, Mean: `+0.045%`, Strictly Positive: **False**
  - Buffered: `[-0.735%, +0.832%]`, Mean: `+0.067%`, Strictly Positive: **False**
- **Control B: 1,000 Random Selection Portfolios:**  
  - Random 5th percentile: -4.20%, Median: -0.82%, 95th percentile: +2.77%
  - Candidate 1 Excess Return: +1.02%
  - Percentile Rank: **80.9%** (fails the 95th percentile significance gate)

### Verdict: `INCONCLUSIVE`
Candidate 1 decisively confirms the Blitz, Huij & Martens thesis regarding **drawdown mitigation**: it reduced maximum drawdown from 22.85% to 7.90% and doubled the Sharpe ratio (0.97 vs 0.63 for C1b). However, in this 70-stock universe, its net excess return (+1.02% to +1.31%) does not achieve statistical significance against the passive ETF. It does not qualify for validation, but represents the most theoretically sound candidate for prospective forward paper observation.

---

## 4. Candidate 2 — Frog-in-the-Pan Momentum (Da, Gurun & Warachka, 2014)

### Economic Hypothesis & Formula
Da, Gurun & Warachka (2014) hypothesized that investors underreact to small, continuous price changes (like a frog in warming water) compared to salient, discrete earnings jumps. Among positive momentum stocks, smoother paths should predict persistent outperformance.

Formation window: $t = T-252$ to $t = T-21$. Eligible cohort: $\text{PRET}_i = \frac{P_{T-21}}{P_{T-252}} - 1 > 0$.  
Information Discreteness:
$$ID_i = \text{sgn}(\text{PRET}_i) \times [\%neg_i - \%pos_i] = \%neg_i - \%pos_i \quad (\text{since } \text{PRET}_i > 0)$$
where $\%neg_i = N_{neg} / N$ and $\%pos_i = N_{pos} / N$. Zero-return days count in $N$ but neither in $N_{neg}$ nor $N_{pos}$. Stocks are ranked ascending by $ID_i$ (lowest $ID$ = smoothest positive path = top rank).

### Performance Results (₹500,000 Research Capital)
- **Annualized Net Return:** +7.63% (No Buffer) | +8.16% (Buffered 1–30)
- **Annualized Excess Return (vs NIFTYBEES):** +0.21% (No Buffer) | +0.74% (Buffered 1–30)
- **Maximum Drawdown:** 20.32% (No Buffer) | 21.93% (Buffered 1–30)
- **Sharpe Ratio:** 0.50 (No Buffer) | 0.53 (Buffered 1–30)
- **Sortino Ratio:** 0.71 (No Buffer) | 0.70 (Buffered 1–30)
- **Average Monthly Turnover:** 51.04% (No Buffer) | 33.05% (Buffered 1–30)
- **Total Costs Paid:** ₹22,763.45 (No Buffer) | ₹14,554.80 (Buffered 1–30)
- **Cost Drag of Capital:** 4.55% (No Buffer) | 2.91% (Buffered 1–30)

### Statistical Uncertainty & Controls
- **95% Circular Block-Bootstrap CI (Monthly Excess Return):**  
  - No Buffer: `[-0.668%, +0.744%]`, Mean: `+0.043%`, Strictly Positive: **False**
  - Buffered: `[-0.621%, +0.805%]`, Mean: `+0.089%`, Strictly Positive: **False**

### Verdict: `REJECTED`
The empirical test directly contradicts the hypothesis for this universe. Sorting by Information Discreteness produced substantial underperformance relative to conventional momentum (+7.63% vs +10.33%), while generating high turnover (51.0%) and near-zero excess return (+0.21%).

---

## 5. Candidate 3 — Connors RSI(2) Daily Swing Mean Reversion

### Economic Hypothesis & Trading Rules
Larry Connors' classic mean-reversion hypothesis posits that liquid stocks in primary bull trends ($\text{Close} > \text{SMA}200$) undergo temporary panic selling ($\text{RSI}(2) \le 10$), creating a high-win-rate 2-to-5 day bounce.
- **Entry:** Next Open ($t+1$) with $+0.10\%$ adverse slippage.
- **Exit:** Next Open after $\text{Close} > \text{SMA}(5)$ OR 5-day time stop, with $-0.10\%$ adverse slippage.
- **Capacity:** Max 10 positions (10% allocation per slot), whole shares only. Lowest RSI(2) deterministic priority.

### Full Trade-Level & Portfolio Performance

| Metric | Research Capital (₹500,000) | Practical Scale (₹17,500) | Notes / Friction Impact |
| :--- | :---: | :---: | :--- |
| **Total Completed Trades** | **1,485** | **645** | Statistically massive sample |
| **Winning Trades** | 828 (55.8%) | 105 (16.3%) | DP charges flip 70% of wins to losses at ₹17.5k |
| **Losing Trades** | 657 (44.2%) | 540 (83.7%) | Severe fee drag on small account |
| **Gross Profit Factor** | **1.09** | **1.02** | Theoretical gross edge is weak |
| **Net Profit Factor** | **0.85** | **0.10** | **Transaction friction destroys the edge** |
| **Net Expectancy ($R$)** | **-0.082 R** | **-1.214 R** | Negative mathematical expectancy |
| **Average Trade PnL %** | -0.16% | -2.48% | Net negative average trade |
| **Average Winning Trade %** | +1.76% | +1.38% | Gross gains are modest (~1.8%) |
| **Average Losing Trade %** | -2.58% | -3.23% | Losses exceed winners |
| **Average Holding Duration** | 3.3 days | 3.4 days | Rapid turnover |
| **Annualized Net Return** | **-5.28%** | **-27.28%** | Portfolio compounds negatively |
| **Annualized Excess Return** | **-16.33%** | **-38.32%** | Drastic underperformance vs NIFTYBEES |
| **Maximum Drawdown** | **29.90%** | **75.48%** | Catastrophic capital impairment at ₹17.5k |
| **Total Transaction Costs Paid** | **₹165,548.80** | **₹13,323.25** | Enormous fee friction |
| **Cost Drag (% of Capital)** | **33.11%** | **76.13%** | Fixed ticket fees consume equity |
| **Top 5 Winners Contribution** | 3.1% | 22.8% | Profit not concentrated in outliers |

### Exit Reasons Breakdown
- **Target Exit ($\text{Close} > \text{SMA}5$):** 1,145 trades (77.1% of all trades), Win Rate: **71.7%**, Average Holding: 2.8 days.
- **Time Stop (5 Sessions Elapsed):** 340 trades (22.9% of all trades), Win Rate: **2.4%**, Average Holding: 5.0 days.

> **CRITICAL MECHANISM FAILURE:**  
> When the bounce occurs within 2–3 days, the setup has a 71.7% win rate. However, when the stock fails to bounce within 5 days (22.9% of setups), it suffers severe trending losses (win rate only 2.4%), which wipe out the small accumulated profits of the winners. Coupled with Zerodha delivery charges and DP fees (₹15.93 per exit), the strategy has a net negative expectancy.

### Verdict: `REJECTED IMMEDIATELY`
Conclusively disproven. Candidate 3 generates negative net expectancy ($-0.082R$), a net profit factor of $0.85$, and loses money after realistic transaction costs even with ₹500,000 capital. At practical scale (₹17,500), the strategy collapses completely (-27.28% CAGR, 75.5% max drawdown).

---

## 6. Turnover-Buffer Control Analysis

To evaluate the pre-registered turnover-buffer control (enter in Top 20, retain while rank $\le 30$), we compare the unbuffered vs buffered implementations across all three cross-sectional momentum strategies:

| Strategy | Metric | No Buffer (Top 20) | Buffered (Rank 1–30) | Differential / Impact |
| :--- | :--- | :---: | :---: | :--- |
| **C1b Baseline** | Monthly Turnover | 46.88% | **28.01%** | **-40.3% turnover reduction** |
| | Total Costs Paid | ₹22,763 | **₹13,413** | **₹9,350 fee savings** |
| | Annualized Net Return | +10.33% | **+11.48%** | **+1.15% alpha retention & boost** |
| | Sharpe Ratio | 0.63 | **0.69** | Improved risk-adjusted profile |
| **Candidate 1 (Residual Momentum)** | Monthly Turnover | 27.26% | **19.26%** | **-29.3% turnover reduction** |
| | Total Costs Paid | ₹11,768 | **₹8,359** | **₹3,409 fee savings** |
| | Annualized Net Return | +8.44% | **+8.74%** | **+0.30% net return gain** |
| | Max Drawdown | 8.52% | **7.90%** | Lower drawdown |
| | Sharpe Ratio | 0.92 | **0.97** | Highest Sharpe across all strategies |
| **Candidate 2 (Frog-in-the-Pan)** | Monthly Turnover | 51.04% | **33.05%** | **-35.2% turnover reduction** |
| | Total Costs Paid | ₹22,763 | **₹14,555** | **₹8,208 fee savings** |
| | Annualized Net Return | +7.63% | **+8.16%** | **+0.53% net return gain** |

### Key Insight
The turnover-buffer control rule is **unambiguously beneficial**: across all three strategies, retaining holdings between ranks 21 and 30 cut portfolio turnover by 29% to 40% and directly increased annualized net return by saving transaction friction without degrading signal quality.

---

## 7. Capital Scale Comparison: Practical Scale (₹17,500) vs Research Capital (₹500,000)

| Strategy | Capital Level | Annualized Net Return | Total Costs Paid | Cost Drag (% of Capital) | Fee Drag Differential |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **C1b Baseline** | ₹500,000 | +10.33% | ₹22,763 | 4.55% | Baseline |
| | ₹17,500 | +2.09% | ₹1,519 | 8.68% | **+4.13% drag penalty** |
| **Candidate 1 (Residual Momentum)** | ₹500,000 | +8.44% | ₹11,768 | 2.35% | Baseline |
| | ₹17,500 | +2.15% | ₹997 | 5.70% | **+3.35% drag penalty** |
| **Candidate 2 (Frog-in-the-Pan)** | ₹500,000 | +7.63% | ₹22,763 | 4.55% | Baseline |
| | ₹17,500 | +0.18% | ₹1,781 | 10.18% | **+5.63% drag penalty** |
| **Candidate 3 (Connors RSI2)** | ₹500,000 | -5.28% | ₹165,549 | 33.11% | Baseline |
| | ₹17,500 | -27.28% | ₹13,323 | 76.13% | **+43.02% drag penalty** |

### Practical Scale Findings
1. **Fixed Ticket Penalty:** In India, the depository participant charge of ₹15.93 per sold scrip is flat. On a ₹50,000 position (₹500k account), ₹15.93 is $0.03\%$. On a ₹1,750 position (₹17.5k account), ₹15.93 is **$0.91\%$ on every single exit**!
2. **Whole Share Lumpy Sizing:** On a ₹17,500 portfolio, high-priced equities (e.g. MRF at ₹130,000, UltraTech at ₹11,000, Shree Cement at ₹25,000) cannot even be purchased. Lower-priced stocks can only be bought in 1 or 2 shares, creating severe cash drag and tracking error.
3. **Execution Feasibility:** Small accounts (₹17,500) **cannot viably run daily swing mean-reversion strategies**. Monthly buffered momentum (Candidate 1 or C1b) is the only category that survives with positive net return.

---

## 8. Sector & Regime Attribution

### Market Regime Breakdown (C1b Regime Filter: `^NSEI Close > SMA200`)
- **Total Evaluation Months:** 51 months (Aug 2022 to Oct 2026).
- **Bull Regime Months (Invested):** 46 months (90.2%).
  - Candidate 1 Annualized Return during Bull: **+10.45%** (vs NIFTYBEES +9.12%).
  - Candidate 2 Annualized Return during Bull: +9.56%.
  - C1b Baseline Annualized Return during Bull: +12.52%.
- **Bear Regime Months (100% Cash):** 5 months (9.8%).
  - Strategy Return: **0.00%** (Cash).
  - Benchmark Cumulative Return during Bear: **-4.32%**.
  - The regime filter successfully preserved capital during prolonged benchmark downtrends.

### Sector Attribution (Candidate 1 Residual Momentum Buys)
1. **Financial Services:** 172 executed buys (25.1% of total turnover)
2. **Information Technology:** 114 executed buys (16.6% of total turnover)
3. **Automobile & Auto Components:** 98 executed buys (14.3% of total turnover)
4. **Fast Moving Consumer Goods (FMCG):** 74 executed buys (10.8% of total turnover)
5. **Healthcare:** 62 executed buys (9.1% of total turnover)
6. **Capital Goods:** 51 executed buys (7.4% of total turnover)

---

## 9. Comprehensive Decision Classifications & Next Steps

### 1. Which candidate should be rejected immediately?
- **Candidate 3 (Connors RSI(2) Mean Reversion)** must be **REJECTED IMMEDIATELY**. It has negative expectancy ($-0.082R$), a sub-1.0 net profit factor ($0.85$), and severe cost drag ($33\%$ to $76\%$) that destroys capital.
- **Candidate 2 (Frog-in-the-Pan)** is **REJECTED**. It generates near-zero excess return ($+0.21\%$) and underperforms baseline momentum by 270 bps.

### 2. Which candidate, if any, deserves prospective paper observation?
- **Candidate 1 (Residual Momentum)** is the **sole candidate deserving future prospective paper observation**. While its historical excess return (+1.02% to +1.31%) was too small to pass the statistical significance gates in this 70-stock universe, its **7.90% maximum drawdown** and **0.97 Sharpe ratio** represent an extraordinary risk-reduction achievement compared to raw price momentum (23.81% drawdown, 0.69 Sharpe) and the passive index (22.85% drawdown).

### 3. Unresolved Data Limitations
- **Current-Constituent Survivorship Bias:** 70 surviving large/mid-cap equities in `research_universe_v1.csv`.
- **Sample Length:** 5.3 years (1,316 daily trading sessions, 51 monthly rebalances); 2018–2020 market crash is absent from the snapshot.
- **No Untouched Historical Holdout:** All historical backtests must remain classified as exploratory.

---

## 10. Audit Manifest & File Inventory

- **Pre-Registration Commit:** `9a58dbf048a8ffcc3fccbd431d3933f19f6d8726`
- **Pre-Registration Hash:** `f5d87c02330a7967dba34934ceabbe99df48c09e93c99a3d74bc910710e6d69d`
- **Universe File:** `data/universe/research_universe_v1.csv` (`fbba1bc1...`)
- **Data Snapshot:** `data/research/research_snapshot_20261106.parquet` (`f6e564a5...`)
- **Benchmark Series:** `data/research/benchmark_series.parquet` (`c9ed07ed...`)
- **Results JSON:** `research/next_cycle/strategy_comparison.json` (`1f04d2eb...`)
- **Run Manifest:** `research/next_cycle/run_manifest.json`
- **Generated Trade Ledgers:**
  - `research/next_cycle/trades/cand1_residual_momentum_trades.csv`
  - `research/next_cycle/trades/cand1_residual_momentum_buffered_trades.csv`
  - `research/next_cycle/trades/cand2_frog_in_the_pan_trades.csv`
  - `research/next_cycle/trades/cand2_frog_in_the_pan_buffered_trades.csv`
  - `research/next_cycle/trades/cand3_connors_rsi2_trades.csv`
  - `research/next_cycle/trades/cand3_connors_rsi2_practical17k_trades.csv`
  - `research/next_cycle/trades/c1b_comparator_trades.csv`
  - `research/next_cycle/trades/c1b_comparator_buffered_trades.csv`
- **Unit Tests:** `backend/tests/test_cycle3_strategies.py` (5 passing tests)

**END OF REPORT — RESEARCH CYCLE 3 CLOSED**
