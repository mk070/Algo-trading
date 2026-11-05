# ENHANCEMENT: RESEARCH DESK, FUNDAMENTAL TRAFFIC LIGHTS, PRE-BREAKOUT FIX, STRATEGY LAB

Incremental task on the existing platform (FastAPI, React/Vite, Neon PostgreSQL). **Do not restart or replace architecture. Do not change existing thresholds or strategy rules without showing evidence and getting explicit owner approval.** No automatic broker execution. Source of truth: `SWING_ALGO_BUILD_SPEC.md`, `DESIGN.md`.

## 0. Inspect first, then report (no code yet)
1. Gap table (`DONE | PARTIAL | MISSING`) for every item below, with file references.
2. **Reproduce three observed problems with fixtures before fixing anything:**
   - **P1: "STATE: BLOCKED" is unexplained.** The list shows a setup but the owner cannot see why it is blocked.
   - **P2: Setups appear only after the breakout.** The owner saw a stock (Grasim) listed only after it had reached the day's high. Check whether the pivot is computed from a base window that includes the signal day, which would make a stock that already broke out look like a fresh near-pivot setup. Reconstruct the stock's scan history for the last 60 sessions from stored `scans`/`signals`/bars and report: first session it passed each stage, and the session it broke out.
   - **P3: A stock with two weak quarters still shows as a setup.** Confirm that no fundamental check exists today (only the earnings blackout and news flags).

## 1. P1: make BLOCKED self-explanatory (small, do first)
Every list row and card shows `BLOCKED: <stage> / <check>: <value> vs <threshold>` (e.g. `Risk / cost gate: 0.34R vs 0.25R max`) from the existing `decision_stage_results`; a tooltip explains the check in plain English. Add a legend for all states. No logic change.

## 2. P2: lead time before the breakout
- If confirmed: when the signal day itself made the new base high and closed at or above the prior pivot, classify it `BROKE_OUT_TODAY` (shown as extended/late, with the no-chase rule) and **not** as a fresh WATCHLIST/APPROACHING setup. Compute the pivot from the base **excluding the signal day** for that classification. Put the change behind `vcp.pivot_excludes_signal_day`, show before/after counts over the last 60 sessions, and re-run the backtest; report any change in results. **Owner approval required before enabling by default.**
- Add a **Pre-breakout watchlist** tier shown at the evening scan: valid base, trend template pass, contraction and volume dry-up present, close below the pivot by the configured proximity, with the planned trigger/stop/size already computed, so the owner sees it before the move. Intraday APPROACHING alerts are unchanged.
- **Lead-time KPI** (Journal/System): for every historical breakout in the universe, how many sessions earlier did the scanner first flag it (median, % flagged before vs after the breakout day, % never flagged). Report this in the final report.

## 3. Fundamentalist: traffic lights (new layer, informational first)
Goal: a small set of main checks, each Green / Yellow / Red / UNKNOWN with the value, period and source, so a non-expert can read it. **Heuristic thresholds, not validated**; all in `config/fundamentals.yaml`; sector-aware; UNKNOWN is never green.

| Check | Green | Yellow | Red |
|---|---|---|---|
| Latest-quarter profit growth (YoY, consolidated) | >= +15% | 0 to +15% | < 0% |
| **Last 2 quarters** net profit | both positive and rising | mixed | **loss, or two consecutive YoY declines** |
| Revenue growth (YoY) | >= 10% | 0 to 10% | < 0% |
| Operating margin vs 4 quarters ago | expanding | within +/-1 pt | down by more than 2 pts |
| ROCE (ROE for banks/NBFCs) | >= 15% (ROE >= 12%) | 10-15% (8-12%) | below those |
| Debt/Equity (not for financials) and interest coverage | D/E < 0.5 and coverage >= 3 | D/E 0.5-1.5 or coverage 1.5-3 | D/E > 1.5 or coverage < 1.5 |
| **Valuation: P/E vs sector median** (not absolute P/E) | < 0.8x sector median | 0.8-1.3x | > 1.5x, or negative earnings |
| Promoter holding (4-quarter change) and pledge | stable/rising, pledge < 5% | pledge 5-25% | fall > 3 pts or pledge > 25% |

Rules: consolidated by default; show standalone when it diverges materially (holding-structure conglomerates). Cyclicals (cement, metals) can look "cheap" at peak earnings, so show a "cyclical" note and weigh valuation lightly. Banks/NBFCs use ROE, P/B and asset-quality metrics instead of D/E. A low absolute P/E is never green by itself (value traps).
- **Data policy (no scraping):** (1) exchange results pointers from the NSE RSS feed trigger a "new results" flag; (2) fundamentals from yfinance for `.NS` tickers where available (unofficial, incomplete, labelled); (3) optional **user-initiated CSV import** of the owner's own exports from a fundamentals site (check that site's terms); (4) a "More detail" link-out button to Tijori Finance / Screener (configurable URL template; verify the format; link only, never fetched by the app). Missing data = UNKNOWN with the link-out.
- `fundamentals.mode`: `off | warn | block_on_red`, **default `warn`**: any RED adds a REVIEW flag and appears in the Judge's reasons, but does not block. Fundamentals cannot be backtested honestly with free data (point-in-time and restatement problems), so evidence comes from **forward outcome tracking**: store the fundamental light state on every signal and report paper/live results by state.
- Per-metric tooltips: what it is, why it matters, the threshold used.

## 4. Research Desk (role-based view; rules do the work)
Roles are **views over the existing deterministic modules**, not separate decision-makers:

| Role | Backed by | Stats shown |
|---|---|---|
| Scout | universe + screener | Scanned, Shortlisted |
| Technician | trend template, VCP/pullback, RVOL | Analyzed, Avg RVOL |
| Fundamentalist | Section 3 | Covered, UNKNOWN count |
| Newsdesk | news engine | Headlines, coverage status counts (net tone is display-only) |
| Planner | existing entry/exit/position sizing stages | Trigger, stop, target, quantity |
| Risk Manager | existing Risk Validator | Gates passed, first failed gate |
| Bull | templated case-for from passed checks | Cases, checks passed |
| Bear | templated case-against from failed/unknown checks | Cases, checks failed |
| Judge | **existing DecisionPipeline** (PASS/BLOCK/WAIT) | Verdicts, PASS count |
| Messenger | Alert Manager + Telegram | Sent, de-duplicated |

- **No analyst target prices, no "average upside", no predictive "score" or probability.** Judge shows **checklist strength (e.g. 9 of 11 checks passed)** and the exact BLOCK/PASS reasons; label it "not a probability".
- Bull/Bear text is generated from templates and check results (works with no AI). **Gemini is optional**, used only to rephrase Bull/Bear text and summarise news for P0/P1 stocks; it never sets a check result, status or decision. Free-tier safety: a shared request queue, per-minute and daily caps, response caching keyed by input hash, shortlist-only, automatic fallback to templates on any limit or error, and no private data (positions, balances) in prompts. Verify the current free-tier limits and data-use terms before enabling.
- User-visible order everywhere: Scout → Technician → Fundamentalist → Newsdesk → Planner → Risk Manager → Bull / Bear → Judge → Messenger. Planner and Risk Manager are views of existing deterministic stages, not additional decision-makers.
- UI per DESIGN.md: funnel strip with counts per stage (clickable), four compact role chips per stock row (Technical, Fundamental, News, Risk), and a Research Desk tab on the stock page.

## 5. Strategy Lab (3-5 candidates, one winner, honest selection)
Candidates, all implemented through the existing engine and tested the same way:
1. **Setup V** (existing VCP/tight-base breakout).
2. **Setup P** (existing EMA pullback).
3. **55-day-high breakout baseline** (control; `vcp.require_contraction=false`).
4. **ABCD (rule-based):** swings from a zig-zag with threshold `k x ATR14`; valid bullish ABCD when BC retraces 61.8-78.6% of AB and CD is about 100% of AB (tolerance configurable) or 127-162% of BC; trigger on a bullish reversal confirmation near D; stop beyond D; targets at 38.2% and 61.8% of A to D. Trade only in an uptrend regime. Detection must be fully objective and unit-tested on synthetic patterns.
5. **Fibonacci pullback in trend:** 38.2-61.8% retracement of the last impulse leg in a trend-template stock with bullish confirmation.
**Elliott Wave is not implemented as an automated strategy:** wave counts are subjective and ambiguous, so any counting rule would be arbitrary and hard to test. Provide Fibonacci retracement/extension and trendline drawing tools on the chart for manual use only.
**Timeframes:** the validated strategies stay on daily bars. 1-hour and 4-hour are entry-refinement/confirmation only: Angel One offers ONE_HOUR but no native 4-hour interval (build 4H from 1H, aligned to the NSE session), intraday history is shallow with reported inconsistencies, so multi-year backtests of intraday strategies are not possible; they are validated by forward/paper tracking and labelled low-confidence.
**Selection protocol (to avoid picking noise):** pre-register candidates and small parameter grids before testing; walk-forward testing; a final holdout period untouched until one candidate is chosen; record the number of trials; compare with buy-and-hold and a random-entry control; apply the existing acceptance gates (trades >= 150, expectancy >= +0.15R after costs, profit factor >= 1.3, max drawdown <= 20%, stable across years, parameter sensitivity, robustness to costs). Rank only candidates that pass the gates by out-of-sample expectancy net of costs; **the winner goes live, the runner-up stays in shadow mode.** No tuned composite weights. If none passes, report that plainly and keep paper trading.

## 6. Value Radar (undervalued ideas, research list only)
A separate research list built from Section 3 lights (valuation Green/Yellow, quality at least Yellow, growth not Red) plus a technical "stabilising" condition (above the 200-day average or a valid base forming). Output is an idea list tagged `VALUE_RADAR` that can be added to a watchlist; every stock still goes through the same DecisionPipeline and Risk Validator. Label: "research idea, not a trade signal; cheap stocks can stay cheap". Warn about value traps and cyclical peaks. Track outcomes by source tag.

## 7. Charts
Keep `lightweight-charts` v5 (already integrated). TradingView's Advanced Charts / Trading Platform libraries are not licensed for personal, hobby or testing use (companies with public web projects only), so do not plan on them. Add: Fibonacci retracement/extension and improved trendline tools (client-side, persisted), a one-click "Open in TradingView" link per symbol, and an optional **Pine Script export** of the strategy lines for the owner's own TradingView account, labelled "visual only; the app is the source of truth".

## 8. Security (do first, and report)
- The README in the public repository contains what appears to be a real Telegram bot token and chat ID. **Owner must revoke the token with BotFather and create a new one**; the agent removes the secrets from README and `.env.example`, adds a placeholder-only policy, a secret-scanning check in CI, and advises rewriting git history.
- Confirm `APP_TOKEN` is **required in production** (README says optional): positions, holdings and alerts must not be reachable by anyone with the public frontend/backend URLs. Report the current state of auth on the deployed Render/Vercel setup.

## 9. Tests (offline, no credentials)
BLOCKED reason rendering for each stage; pivot-excludes-signal-day classification (BROKE_OUT_TODAY vs pre-breakout) on fixtures including the Grasim-like case; lead-time KPI maths; each fundamental check at every threshold boundary, UNKNOWN handling (never green), consolidated vs standalone, financials-specific rules, sector-median valuation; `warn` vs `block_on_red` modes; fundamentals cannot change sizing, stops or entries; Research Desk stats and templated Bull/Bear text; Gemini off, rate-limited and failing paths fall back to templates and never alter decisions; ABCD and Fibonacci detectors on synthetic patterns with objective tolerances; strategy-lab selection protocol (holdout untouched, trial count recorded); Value Radar tagging and pipeline routing; secret-scan check.

## 10. Docs and final report
Update `SWING_ALGO_BUILD_SPEC.md`, `README.md`, `DESIGN.md` references. Report: gap table, reproduction results for P1-P3, what changed and whether any existing behaviour changed, files changed, tests run, remaining limitations (fundamental data coverage, intraday history depth, unverified free-tier limits).
