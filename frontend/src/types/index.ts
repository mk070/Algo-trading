export interface ChecklistItem {
  rule: string;
  passed: boolean;
  actual_value: string;
  expected_value: string;
}

export interface NewsCoverage {
  symbol: string;
  status: 'CLEAR' | 'REVIEW' | 'BLOCKED' | 'UNKNOWN';
  sources_checked: string[];
  has_earnings_blackout: boolean;
  earnings_date: string | null;
  red_events_count: number;
  amber_events_count: number;
  checked_at: string;
}

export interface Signal {
  id: number;
  scan_id?: number;
  symbol: string;
  market: string;
  setup: string;
  trigger: number;
  entry_zone_high: number;
  stop: number;
  target1: number;
  qty: number;
  risk_amount: number;
  cost_estimate: number;
  cost_in_r: number;
  rs_rank: number;
  score: number;
  atr: number;
  gap95: number;
  state: 'WATCHLIST' | 'APPROACHING' | 'TRIGGERED_PROVISIONAL' | 'TRIGGERED_CONFIRMED' | 'INVALIDATED' | 'EXTENDED' | 'EXPIRED' | 'SKIPPED' | 'BLOCKED' | 'NO_SETUP' | 'ALREADY_HELD' | 'VALID_SETUP' | 'PRE_BREAKOUT_WATCHLIST' | 'BROKE_OUT_TODAY' | string;
  sources?: string[];
  first_failing_check?: string;
  reasons: string[];
  checklist?: ChecklistItem[];
  news_coverage?: NewsCoverage;
  valid_until?: string;
  created_at?: string;
  decision_stages?: DecisionStage[];
  blocked_reason?: BlockedReason | null;
  fundamentals?: any;
  tier?: string;
  is_higher_risk?: boolean;
  setup_edge_status?: string;
  setup_note?: string;
}

export interface FunnelStage {
  key: string;
  label: string;
  count: number;
  denominator: number;
  tooltip: string;
}

export interface DecisionCheck {
  name: string;
  value: string;
  threshold: string;
  passed: boolean;
  note?: string;
}

export interface DecisionStage {
  stage_name: string;
  status: 'PASS' | 'BLOCK' | 'WAIT' | string;
  checks: DecisionCheck[];
  rejection_reasons: string[];
}

export interface BlockedReason {
  stage: string;
  check: string;
  value: string;
  threshold: string;
  note: string;
}

export interface RegimeResult {
  market: string;
  status: 'BULLISH' | 'CAUTION' | 'WEAK';
  index_symbol: string;
  last_close: number;
  sma50: number;
  sma200: number;
  is_bullish: boolean;
  allows_entries: boolean;
  size_multiplier: number;
  detail: string;
}

export interface TradePlan {
  market: string;
  session_date: string;
  regime: RegimeResult;
  signals: Signal[];
  shadow_signals: Signal[];
  candidate_opportunities?: Signal[];
  pre_breakout_watchlist?: Signal[];
  funnel?: FunnelStage[];
  coverage_summary?: any;
  universe_size: number;
  passed_filters: number;
  data_warnings: string[];
  generated_at: string;
}

export interface Position {
  id: number;
  symbol: string;
  market: string;
  source: string;
  mode: string;
  entry_date: string;
  entry_price: number;
  qty: number;
  initial_stop: number;
  active_stop: number;
  target1: number;
  status: string;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pct: number;
  unrealized_r: number;
  days_held: number;
  notes?: string;
  as_of?: string;
}

export interface JournalEntry {
  id: number;
  position_id?: number;
  symbol: string;
  market: string;
  entry_date?: string;
  entry_price?: number;
  exit_date: string;
  exit_price: number;
  qty: number;
  exit_reason: string;
  pnl_amount: number;
  pnl_pct: number;
  r_multiple: number;
  holding_days: number;
  fees_total: number;
  note?: string;
}

export interface GateCheck {
  name: string;
  target: string;
  actual: string;
  passed: boolean;
}

export interface BacktestMetrics {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  cagr_pct: number;
  total_pnl: number;
  total_return_pct: number;
  profit_factor: number;
  expectancy_r: number;
  avg_win_r: number;
  avg_loss_r: number;
  max_drawdown_pct: number;
  max_drawdown_duration_days: number;
  total_costs: number;
  costs_pct_of_gross: number | null;
  sharpe_ratio: number;
  acceptance_gates: GateCheck[];
  all_gates_passed: boolean;
  disclaimer: string;
}

export interface MonteCarloData {
  iterations: number;
  median_ending_equity: number;
  pct_5th_ending_equity: number;
  pct_95th_ending_equity: number;
  median_max_drawdown_pct: number;
  worst_case_max_drawdown_pct: number;
  risk_of_ruin_pct: number;
}

export interface StageCheck {
  name: string;
  value: string | number | boolean;
  threshold: string;
  passed: boolean;
  note: string;
}

export interface StageResult {
  stage_name: string;
  status: 'PASS' | 'BLOCK' | 'WAIT';
  checks: StageCheck[];
  rejection_reasons: string[];
}

export interface DecisionAudit {
  id?: number;
  symbol: string;
  market: string;
  asof_date: string;
  mode: string;
  final_decision: 'PASS' | 'BLOCK' | 'WAIT';
  setup?: string;
  trigger?: number;
  stop?: number;
  target1?: number;
  qty?: number;
  risk_amount?: number;
  cost_in_r?: number;
  config_hash?: string;
  code_version?: string;
  data_source?: string;
  stages: StageResult[];
  all_rejection_reasons?: string[];
}

export interface HorizonMetrics {
  horizon_sessions: number;
  first_passage_1r_pct?: number;
  first_passage_1r_ci?: [number, number];
  first_passage_2r_pct?: number;
  first_passage_2r_ci?: [number, number];
  first_passage_3r_pct?: number;
  stop_first_pct?: number;
  stop_first_ci?: [number, number];
  neither_pct?: number;
  median_r?: number;
  r_percentile_25?: number;
  r_percentile_75?: number;
  median_mae_r?: number;
  median_mfe_r?: number;
  avg_sessions_to_outcome?: number;
}

export interface ObservedAnalogues {
  status: 'OK' | 'INSUFFICIENT SAMPLE';
  sample_size_n: number;
  min_analogues_required: number;
  date_range?: [string, string];
  matched_regime: string;
  matched_rs_bucket: string;
  matched_atr_pct: number;
  horizons: Record<string, HorizonMetrics>;
  note?: string;
}

export interface SimulatedBootstrap {
  simulation_runs_m: number;
  seed_used: number;
  horizons: Record<string, HorizonMetrics>;
  drawdown_distribution: Record<string, number>;
  mae_distribution: Record<string, number>;
  mfe_distribution: Record<string, number>;
}

export interface ScenarioSensitivityRow {
  scenario: string;
  stop_price: number;
  stop_first_pct: number;
  target_1r_pct: number;
  median_r: number;
}

export interface ScenarioLabResult {
  symbol: string;
  asof_date: string;
  trigger_price: number;
  stop_price: number;
  risk_r: number;
  observed: ObservedAnalogues;
  simulated: SimulatedBootstrap;
  sensitivity_table: ScenarioSensitivityRow[];
  limitations_disclaimer: string;
}

export interface PeriodFinancials {
  symbol: string;
  market: string;
  period_type: string;
  period_ended: string;
  filing_date: string;
  revenue: number;
  operating_profit?: number;
  net_profit: number;
  eps: number;
  currency: string;
  source_name: string;
  source_url: string;
  consensus_eps?: number;
  consensus_source?: string;
}

export interface EarningsAnalysisResult {
  symbol: string;
  market: string;
  latest_period: PeriodFinancials;
  prior_period?: PeriodFinancials | null;
  prior_year_period?: PeriodFinancials | null;
  revenue_yoy_pct?: number | null;
  profit_yoy_pct?: number | null;
  eps_yoy_pct?: number | null;
  revenue_qoq_pct?: number | null;
  profit_qoq_pct?: number | null;
  eps_qoq_pct?: number | null;
  operating_margin_pct?: number | null;
  prior_operating_margin_pct?: number | null;
  eps_surprise_pct?: number | null;
  consensus_status: 'VERIFIED' | 'UNKNOWN';
  guidance_status: 'CONFIRMED' | 'UNKNOWN';
  severity: 'CLEAR' | 'AMBER';
  amber_flags: string[];
  source_links: string[];
  ai_summary?: string;
}


