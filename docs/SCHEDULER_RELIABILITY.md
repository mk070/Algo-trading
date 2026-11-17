# Scheduler Reliability & Production Hosting Architecture

## 1. The Operational Problem: Free-Tier Web Service Inactivity Sleep

On Render's Free tier, Web Services automatically spin down ("sleep") after approximately 15 minutes of inactivity (zero inbound HTTP requests). When the web service is asleep:
- The Python process is suspended.
- In-memory `APScheduler` background threads cease execution.
- Scheduled cron jobs (e.g., 16:00 IST post-market paper rebalance, 16:30 IST EOD scanner) will **NOT** fire at their scheduled wall-clock time if the dyno is sleeping.
- Upon receiving a new HTTP request, the dyno experiences a 30–50 second cold-start delay before responding.

## 2. Implemented Execution Architecture

To solve this within the existing architectural constraints without silent assumptions:

### A. Independent Render Cron Job Service (`render.yaml`)
- A dedicated Cron Job service (`algo-paper-daily`) has been configured in `render.yaml`.
- Schedule: `"30 10 * * 1-5"` (10:30 UTC = 16:00 IST, Monday through Friday).
- Operation: Render launches an independent ephemeral container, executes `run_paper_evaluation_once()`, marks the portfolios to market, commits results directly to the authoritative Neon PostgreSQL database, and cleanly exits.
- **Independence:** This cron job executes whether the primary web service is asleep or awake.

### B. Database-Level Idempotency (`UniqueConstraint`)
- The `paper_daily_history` table enforces a strict database constraint:
  `UniqueConstraint("strategy_id", "session_date", name="uq_paper_daily_strategy_date")`
- In `run_paper_evaluation_once()`, the engine queries Neon PostgreSQL before computing:
  If a row already exists for `(strategy_id, today, run_type='FORWARD')`, execution safely returns `ALREADY_COMPLETED`.
- Even if both the web scheduler and the Render Cron Job run concurrently on the same session date, duplicate fills or duplicate daily marks are strictly impossible.

### C. Missed-Run Detection & No-Fabrication Safety Rule
- When the daily evaluator runs, `detect_missed_paper_runs()` inspects the last 7 calendar days.
- It compares exchange business days (skipping official NSE holidays and weekends via `is_exchange_holiday("IN", date)`) against recorded `paper_daily_history` dates.
- If a trading session was missed (e.g. cloud provider outage), it is audited in `job_runs` with status `MISSED_RUN`.
- **Absolute Safety Invariant:** Fills are **NEVER fabricated** for past uninspected market events. If an evaluation was missed, cash is preserved and positions remain marked at their last verified price.

## 3. Hosting Tiers & Paid Infrastructure Requirements

| Hosting Option | Reliability Guarantee | Cost | Unattended Suitability |
| :--- | :--- | :--- | :--- |
| **Render Free Web + Render Free Cron** | **Best-effort:** Free cron jobs share free compute limits. Ephemeral build spin-up may take 1–2 minutes. | **$0 / month** | Suitable for forward observation with daily manual log verification. |
| **Render Starter Plan (Always-On Web)** | **Guaranteed:** Dyno never sleeps; in-memory APScheduler runs continuously without interruption. | **$7.00 / month** | Recommended for 100% unattended, zero-maintenance background automation. |
| **External Trigger (GitHub Actions / BetterStack)** | **High:** Free GitHub Actions workflow or BetterStack ping triggers an authenticated POST/CLI daily. | **$0 / month** | Dependable free alternative to keep the dyno awake or trigger execution. |

*Notice: No subscription has been modified or upgraded. The free Cron Job design provides the safest available execution path within current zero-cost constraints.*
