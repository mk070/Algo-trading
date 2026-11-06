# PREREG.md: Pre-Registration of Phase 2 Strategy Validation
**Status:** FROZEN & COMMITTED BEFORE CANDIDATE TESTING  
**Date:** 2026-11-06  
**Research Mode:** Strictly Offline Research — No Live Trading, No Automatic Order Placement  
**Random Seed:** `42` (Fixed across all bootstrap resamples and Monte Carlo random draws)

---

## 1. Research Objective & Hypotheses

The objective of Phase 2 is to determine through controlled, reproducible experiments whether any strategy candidate demonstrates a repeatable positive edge after realistic transaction costs and slippage.

### Evaluated Candidates (Maximum 3 Configurations):
1. **Candidate C1a (Primary Research Hypothesis):** Low-turnover cross-sectional momentum (12-1 momentum), monthly rebalanced, top-20 equal-weighted portfolio, **Always Invested**.
2. **Candidate C1b (Primary Research Hypothesis Variant):** Low-turnover cross-sectional momentum (12-1 momentum), monthly rebalanced, top-20 equal-weighted portfolio, **Market-Regime Filtered** (invested only when broad-market index close > 200-day simple moving average; otherwise 100% cash).
3. **Candidate C2 (Existing Strategy):** Volatility Contraction Pattern (VCP) breakout, using original frozen rules and parameters.

### Controls:
- **Control A:** Existing 55-day high breakout (technical trend baseline).
- **Control B (C1):** 1,000 independent random-selection portfolios drawn from the identical eligible universe with identical equal-weighting, whole-share sizing, next-open execution, and transaction costs.
- **Control B (C2 & 55-Day):** 1,000 matched random-entry simulations sharing identical holding constraints, exits, and costs.

### Benchmarks:
- **Benchmark A (Primary Passive Benchmark):**
  - **India:** Nifty 50 Total Return Index (`NIFTYBEES.NS` / `^NSEI`).
  - **United States:** Predefined dividend-adjusted 50/50 blend of Large-Cap (`SPY`) and Mid-Cap (`MDY`) Total Return ETFs.
- **Benchmark B (Equal-Weight Universe Benchmark):** Monthly equal-weighted portfolio of all eligible stocks in the approved research universe.

---

## 2. Frozen Data Scope & Universe

### Approved Strategy Research Universe:
- **File:** `research/research_universe_v1.csv` (and `data/universe/research_universe_v1.csv`)
- **Symbol Count:** 105 equities (70 India NSE -EQ equities across Nifty 100 and Nifty Midcap 150; 35 US equities across S&P 500 and S&P MidCap 400).
- **SHA256:** `fbba1bc176a5dd6c0d5f2527dc7599f3c1d0117158e54fcd6b8f94a9542ee72e`

### Historical Price Data:
- **Snapshot File:** `data/research/research_snapshot_20261106.parquet`
- **File SHA256:** `f6e564a5c3d01f755c5fc0e1356346491c56d66312a13c0da64e421ff8c0c58f`
- **Canonical Logical Data SHA256:** `0c8f745455f3a61268d900902de037a2eb82b729b68204c25adff5c78a2dcac5`
- **Total Rows in Snapshot:** 141,040 rows (138,689 in approved 105-symbol universe, 2,351 in 9 non-universe symbols).
- **Date Span:** `2021-07-19` to `2026-11-05` (5.3 years, 1,305 to 1,333 trading sessions per symbol).

### Benchmark Data:
- **File:** `data/research/benchmark_series.parquet`
- **SHA256:** `c9ed07ede1e98fdf7b869cfc8ffa749d41e68a9781dfebb31c7685325f4093be`
- **Symbols:** `^NSEI`, `NIFTYBEES.NS`, `^GSPC`, `SPY`, `MDY` (6,619 daily bars, `2021-07-19` to `2026-11-05`).
- **Adjustment:** Dividend and split adjusted Total Return series.

---

## 3. Candidate Specifications & Rules

### Candidate C1 (Cross-Sectional Momentum):
- **Rebalance Frequency:** Monthly, on the final trading day of each calendar month ($T$).
- **Ranking Score:** Total return from 12 months prior through 1 month prior:
  $$\text{Score} = \frac{P_{T-21}}{P_{T-252}} - 1$$
  The most recent 21 trading days (~1 month) are strictly skipped to prevent short-term mean reversion contamination.
- **Lookback Requirement:** Minimum 252 trading days (~12 months) of history prior to $T-21$ (total $\ge$ 13 months).
- **Eligibility & Liquidity Filters:**
  - **India:** NSE `-EQ` series, share price $\ge$ ₹50, 60-trading-day median daily turnover $\ge$ ₹5 crore (₹50,000,000).
  - **US:** Price $\ge$ $5.00, 60-day median turnover $\ge$ $20M (documented exploratory/survivorship limitation due to Alpaca IEX ~2.5% tape volume).
- **Portfolio Construction:**
  - Select Top 20 ranked eligible stocks.
  - Target equal weight: $w_i = 1/20 = 5\%$ of total portfolio equity.
- **Execution & Invariants:**
  - Ranking evaluated at close of date $T$.
  - Execution occurs at Open of date $T+1$ (next trading session).
  - Whole shares only: $\text{qty}_i = \lfloor \frac{\text{Target Capital}_i}{\text{Open}_{i, T+1} \times (1 + \text{slip})} \rfloor$.
  - Uninvested cash remains explicitly tracked at 0% interest.
  - Existing holdings remaining in the top 20 are rebalanced only if their target weight drifts or to align with capital.
  - Stocks exiting the top 20 are sold at Open of date $T+1$.
- **C1a (Always Invested):** Portfolio remains invested in Top 20 stocks every month regardless of market trend.
- **C1b (Market-Regime Filter):**
  - Evaluated on broad-market index (`^NSEI` for India, `^GSPC` for US).
  - If Index Close on date $T >$ 200-day Simple Moving Average: 100% invested in Top 20.
  - If Index Close on date $T \le$ 200-day Simple Moving Average: Liquidate to 100% Cash at $T+1$ Open.

### Sizing & Capital:
- **India Gating Portfolio:** ₹500,000 INR.
- **US Gating Portfolio:** $50,000 USD.
- **India Practical-Scale Portfolio (Diagnostic Only):** ₹17,500 INR, Top 5 positions.

---

## 4. Realistic Cost Model & Slippage

### India (NSE Equity Delivery):
- **Brokerage:** Flat ₹0 (Zerodha Delivery).
- **STT:** 0.10% on Buy turnover, 0.10% on Sell turnover.
- **Exchange Transaction Fee:** 0.003% of turnover.
- **SEBI Turnover Fee:** ₹10 per crore (0.0001% of turnover).
- **Stamp Duty:** 0.015% on Buy turnover.
- **DP Charge:** ₹13.50 flat per scrip sell + 18% GST.
- **GST:** 18% on (Exchange fee + SEBI fee + DP charge).
- **Slippage:** 0.10% on entry, 0.10% on exit.

### United States:
- **Brokerage:** $0.00 commission.
- **Regulatory Fee (SEC/FINRA):** 0.003% on Sell turnover.
- **FX Spread:** 0.50% on total turnover.
- **Slippage:** 0.05% on entry, 0.05% on exit.

---

## 5. Statistical Methodology & Acceptance Gates

### Block Bootstrap Confidence Intervals (C1):
- **Metric:** Monthly Net Excess Return ($R_{\text{portfolio}} - R_{\text{Benchmark A}}$).
- **Method:** Circular block bootstrap with block length = 6 months.
- **Resamples:** 2,000 bootstrap draws.
- **Confidence Level:** 95% two-sided ($[2.5\%, 97.5\%]$).
- **Random Seed:** Fixed at `42`.

### Random Selection Controls (Control B):
- 1,000 independent random portfolios generated using seed `42`.
- Candidate must achieve a net excess return exceeding the 95th percentile ($p \ge 0.95$) of the 1,000 random portfolios.

### Acceptance Gates:

#### Candidate C1 Acceptance Gates:
1. **Gate 1 (Annualized Excess Return):** Net annualized excess return $\ge +2.0\%$ vs Benchmark A.
2. **Gate 2 (Bootstrap Confidence Interval):** 95% block-bootstrap lower bound of monthly net excess return $> 0.0\%$.
3. **Gate 3 (Max Drawdown Ratio):** Maximum drawdown $\le 1.2 \times$ Benchmark A maximum drawdown.
4. **Gate 4 (Calendar Year Consistency):** Positive net excess return in $\ge 60\%$ of full calendar years (minimum 4 full years).
5. **Gate 5 (Untouched Holdout):** Positive net excess return in genuinely untouched holdout. *(Status: Disclosed as UNAVAILABLE; May–Nov 2026 was previously inspected in task-9156. Prevents unconditional PASS).*
6. **Gate 6 (Cost Sensitivity):** Net excess return remains positive under costs $+25\%$ and slippage $\times 2$.
7. **Gate 7 (Random Selection Dominance):** Performance $> 95\text{th}$ percentile of 1,000 random portfolios.
8. **Gate 8 (Parameter Sensitivity):** $\ge 70\%$ of neighboring parameter variations profitable.

#### Candidate C2 & Control A Acceptance Gates:
- $\ge 150$ completed trades.
- Net expectancy $\ge +0.15R$.
- Profit factor $\ge 1.30$.
- Max drawdown $\le 20.0\%$.
- Positive performance in both evaluation halves and $\ge 3$ of 4 calendar years.
- Walk-forward robust.
- Untouched holdout positive.
- Beat matched random-entry control at $\ge 95\text{th}$ percentile.

---

## 6. Kill Rule & Verdict Protocol

- **`PASS`:** All applicable gates satisfied, adequate sample, untouched holdout verified.
- **`FAIL`:** At least one required gate fails with adequate statistical evidence.
- **`INCONCLUSIVE`:** Insufficient observations, lack of untouched holdout, or insufficient statistical power.
- **Kill Rule:** If no candidate achieves `PASS`, strategy search ceases immediately. No parameter retuning, no indicator additions. Recommend passive indexing or research-only platform usage.
