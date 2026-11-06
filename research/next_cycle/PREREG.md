# PREREG.md: Research Cycle 3 Pre-Registration
**Status:** FROZEN & COMMITTED BEFORE CANDIDATE TESTING  
**Date:** 2026-11-06  
**Cycle:** Research Cycle 3 — Independent Swing Strategy Testing  
**Research Mode:** Strictly Offline Research — No Live Trading, No Automatic Order Placement  
**Fixed Random Seed:** `42`  

---

## 1. Research Objectives & Scope

The objective of Research Cycle 3 is to evaluate exactly three genuinely distinct, peer-reviewed/established swing-trading hypotheses against the frozen Phase 2 baseline (Candidate C1b India):
1. **Candidate 1 — Residual Momentum (Blitz, Huij, and Martens, 2011):** Ranks equities by idiosyncratic residual momentum after purging broad-market and industry-sector factor returns over the trailing 12-1 window.
2. **Candidate 2 — Frog-in-the-Pan Momentum (Da, Gurun, and Warachka, 2014):** Ranks equities within the positive medium-term momentum cohort by Information Discreteness ($ID = \text{sgn}(\text{PRET}) \times [\%neg - \%pos]$) to isolate smooth, continuous price appreciation paths prone to investor underreaction.
3. **Candidate 3 — Connors RSI(2) Mean Reversion (Larry Connors):** Trade-based daily swing mean-reversion buying extreme pullbacks ($\text{RSI}(2) \le 10$) in long-term uptrends ($\text{Close} > \text{SMA}200$) with quick profit exits ($\text{Close} > \text{SMA}5$) or a 5-day time stop.

Additionally, a pre-registered **Turnover-Buffer Control** (rank retention band 1–30) is evaluated to measure turnover reduction and fee drag savings.

---

## 2. Frozen Universe & Data Scope

- **Market Scope:** India (NSE `-EQ` equities).
- **Approved Strategy Universe:** [`data/universe/research_universe_v1.csv`](file:///d:/web%20development/saas-projects/Algo-trading/data/universe/research_universe_v1.csv) (70 Indian NSE `-EQ` series across Nifty 100 and Nifty Midcap 150).
  - SHA256: `fbba1bc176a5dd6c0d5f2527dc7599f3c1d0117158e54fcd6b8f94a9542ee72e`
- **Data Snapshot:** [`data/research/research_snapshot_20261106.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/research_snapshot_20261106.parquet)
  - Date Range: `2021-07-19` to `2026-11-05` (5.3 years, 1,316 daily trading sessions).
  - SHA256: `f6e564a5c3d01f755c5fc0e1356346491c56d66312a13c0da64e421ff8c0c58f`
- **Benchmark Series:** [`data/research/benchmark_series.parquet`](file:///d:/web%20development/saas-projects/Algo-trading/data/research/benchmark_series.parquet)
  - Primary Passive Benchmark: `NIFTYBEES.NS` (Nifty 50 Total Return ETF).
  - Market Regime & Diagnostic Index: `^NSEI` (Nifty 50 Index).
  - SHA256: `c9ed07ede1e98fdf7b869cfc8ffa749d41e68a9781dfebb31c7685325f4093be`
- **Capital Portfolios:**
  - Primary Gating Research Capital: **₹500,000 INR**.
  - Practical-Scale Diagnostic Capital: **₹17,500 INR**.

---

## 3. Candidate Specifications & Formulas

### Candidate 1: Residual Momentum (Blitz, Huij & Martens, 2011)
- **Hypothesis:** Conventional price momentum is contaminated by exposure to systematic market and sector risk. Removing systematic factor returns isolates high-quality idiosyncratic momentum with lower drawdowns and reduced factor tail risk.
- **Factor Model:** On each month-end ranking date $T$, using trailing daily returns from $t = T-252$ to $t = T-21$ (232 trading sessions, skipping the most recent 21 sessions):
  $$R_{i,t} = \alpha_i + \beta_{i,M} R_{M,t} + \beta_{i,S} R_{S,t} + \epsilon_{i,t}$$
  where $R_{M,t}$ is the daily return of `^NSEI` (market factor) and $R_{S,t}$ is the equal-weighted return of all other universe stocks in stock $i$'s sector (industry sector factor). If a sector has only 1 stock, $\beta_{i,S} = 0$.
- **Score Formula:** Residual returns $\epsilon_{i,t}$ are calculated over the lookback window. The ranking score is the standardized cumulative residual return (residual Sharpe ratio):
  $$\text{Score}_i = \frac{\sum_{t=T-252}^{T-21} \epsilon_{i,t}}{\sigma(\epsilon_{i})}$$
  where $\sigma(\epsilon_{i})$ is the sample standard deviation of daily residuals over the estimation window.
- **Selection & Sizing:** Top 20 stocks by $\text{Score}_i$, equal-weighted ($w_i = 5\%$), whole shares only, cash tracked at 0%.
- **Regime Filter:** Inherits C1b's rule: Invested in Top 20 only when `^NSEI` close at date $T >$ 200-day SMA; otherwise hold 100% Cash.
- **Execution:** Next trading day Open ($T+1$) with adverse slippage ($+0.10\%$ buy, $-0.10\%$ sell) and Zerodha delivery costs.

### Candidate 2: Frog-in-the-Pan Momentum (Da, Gurun & Warachka, 2014)
- **Hypothesis:** Market participants underreact to continuous, frequent, small price changes (continuous information, like a frog in warming water) compared to discrete, salient, infrequent earnings jumps. Among positive momentum stocks, smoother paths generate persistent post-formation returns.
- **Past Return Cohort:** Formation window from $T-252$ to $T-21$ (skipping most recent 21 sessions):
  $$\text{PRET}_i = \frac{P_{i, T-21}}{P_{i, T-252}} - 1$$
  Only stocks in the positive momentum cohort ($\text{PRET}_i > 0$) are eligible for selection.
- **Information Discreteness ($ID$):**
  $$ID_i = \text{sgn}(\text{PRET}_i) \times [\%neg_i - \%pos_i] = \%neg_i - \%pos_i \quad (\text{since } \text{PRET}_i > 0)$$
  where:
  - $\%neg_i = N_{neg, i} / N_i$ (fraction of sessions with $R_{i,t} < 0$).
  - $\%pos_i = N_{pos, i} / N_i$ (fraction of sessions with $R_{i,t} > 0$).
  - Zero-return days ($R_{i,t} = 0$) count in total days $N_i$ but neither in $N_{neg}$ nor $N_{pos}$.
- **Ranking Rule:** Stocks with $\text{PRET}_i > 0$ are ranked by $ID_i$ ascending (lowest $ID_i$ = most continuous positive return path = highest rank).
- **Selection & Sizing:** Top 20 stocks, equal-weighted ($w_i = 5\%$), whole shares only, cash tracked at 0%.
- **Regime Filter:** Inherits C1b's rule (`^NSEI` close $>$ 200-day SMA).
- **Execution:** Next trading day Open ($T+1$) with adverse slippage and Zerodha delivery costs.

### Candidate 3: Connors RSI(2) Mean Reversion
- **Hypothesis:** Highly liquid stocks in established primary bull trends undergo temporary liquidity squeezes and irrational panic selling, creating a robust, high-win-rate 2-to-5 day mean-reversion edge.
- **Setup Rules (Daily Signal Bar at Close):**
  1. Primary Trend Filter: $\text{Close}_t > \text{SMA}(200)_t$.
  2. Oversold Trigger: 2-period Relative Strength Index $\text{RSI}(2)_t \le 10.0$.
  3. Minimum Price & Liquidity: $\text{Close}_t \ge ₹50.0$, 60-day median daily turnover $\ge ₹50,000,000$.
- **Entry:** Buy at next trading session Open ($t+1$) at $\text{Open}_{t+1} \times (1 + 0.0010)$.
- **Exit Conditions:**
  1. Mean-Reversion Target Exit: Daily close $\text{Close}_k > \text{SMA}(5)_k$. Exit executed at next session Open ($k+1$) at $\text{Open}_{k+1} \times (1 - 0.0010)$.
  2. Time Stop Exit: If no SMA5 close occurs after 5 completed holding sessions ($k = t + 5$), exit unconditionally at next Open ($t+6$).
- **Portfolio & Risk Constraints:**
  - Maximum concurrent open positions: 10 (target 10% capital per trade).
  - Allocation Priority: If more than available slots trigger on the same day, allocate deterministically by lowest $\text{RSI}(2)$ ascending.
  - No averaging down, no margin leverage.

### Turnover-Buffer Control Rule
- Applicable to Candidates 1, 2, and Comparator C1b:
  - New stocks enter the portfolio only when ranked in the Top 20.
  - An existing holding is retained until its rank falls below 30.
  - Cash freed from stocks exiting the 1–30 band is reallocated to new Top 20 entrants.

---

## 4. Cost Model & Execution Invariants

### Exact Indian Equity Delivery Model (Zerodha / NSE):
- **Brokerage:** Flat ₹0 delivery.
- **Securities Transaction Tax (STT):** 0.10% on Buy turnover, 0.10% on Sell turnover.
- **Exchange Transaction Charges:** 0.003% of turnover.
- **SEBI Fee:** ₹10 per crore (0.0001% of turnover).
- **Stamp Duty:** 0.015% on Buy turnover.
- **Depository Participant (DP) Charge:** ₹13.50 flat per sold scrip + 18% GST (₹15.93 per sold position).
- **GST:** 18% on (Exchange fee + SEBI fee + DP charge).
- **Slippage:** 0.10% adverse fill on entry, 0.10% adverse fill on exit.

---

## 5. Decision Protocol & Acceptance Standards

In accordance with Section J of the specification, because the historical dataset was previously inspected in Phase 2, all historical tests are classified as exploratory.

### Verdict Categories:
- **`REJECTED`:** An observed empirical result directly contradicts the pre-registered hypothesis (e.g. negative excess return, excessive drawdown, negative expectancy).
- **`INCONCLUSIVE`:** Insufficient trade sample size ($N < 150$), inadequate statistical power, or insufficient history.
- **`PROMISING — FORWARD VALIDATION REQUIRED`:** Favorable exploratory historical evidence meeting baseline gates (Excess return $\ge +2.0\%$, Drawdown ratio $\le 1.20\times$, positive bootstrap CI), but strictly requiring prospective forward paper testing before any validation.
- **`VALIDATED`:** Applicable ONLY after prospective forward paper trading satisfies all pre-registered criteria over at least 8 weeks.

**No strategy is authorized for live trading or automatic order placement.**
