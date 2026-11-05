import React, { useEffect, useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  BarChart2,
  Activity,
  Shield,
  Users,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Target,
  Layers,
  BookOpen,
  Clock,
  Check,
  AlertCircle,
  X,
  Filter,
} from 'lucide-react';
import { API_BASE } from '../api/client';

export interface CriterionItem {
  id: string;
  name: string;
  category: string;
  target: string;
  actual: string;
  status: 'PASS' | 'CAUTION' | 'FAIL';
  explanation: string;
}

export interface FundamentalData {
  symbol: string;
  market: string;
  provider: string;
  last_updated: string;
  overall_score?: number;
  score?: number;
  verdict?: string;
  conclusion?: string;
  lynch_bucket?: string;
  passed_count?: number;
  caution_count?: number;
  failed_count?: number;
  total_criteria?: number;
  criteria_checklist?: CriterionItem[];
  company: { name: string; sector: string; industry: string; country: string };
  price: {
    current: number | null;
    w52_high: number | null;
    w52_low: number | null;
    '52w_high'?: number | null;
    '52w_low'?: number | null;
    w52_pct_from_high: number | null;
    w52_pct_from_low: number | null;
    '3y_high'?: number | null;
    '3y_low'?: number | null;
    w3y_high?: number | null;
    w3y_low?: number | null;
    beta: number | null;
    '52w_change'?: number | null;
    average_volume?: number | null;
  };
  valuation: {
    pe_trailing: number | null;
    pe_forward: number | null;
    peg: number | null;
    price_to_book: number | null;
    graham_ratio?: number | null;
    price_to_sales: number | null;
    ev_to_ebitda: number | null;
    market_cap: number | null;
    enterprise_value: number | null;
  };
  profitability: {
    roe: number | null;
    roce: number | null;
    roa: number | null;
    operating_margin: number | null;
    net_margin: number | null;
    gross_margin: number | null;
    fcf_to_net_income?: number | null;
  };
  growth: {
    revenue_growth_yoy: number | null;
    earnings_growth_yoy: number | null;
    earnings_growth_qoq: number | null;
  };
  cashflow: {
    free_cash_flow: number | null;
    operating_cash_flow: number | null;
    fcf_yield: number | null;
  };
  balance_sheet: {
    current_ratio: number | null;
    debt_to_equity: number | null;
    quick_ratio: number | null;
  };
  dividends: {
    yield: number | null;
    rate: number | null;
    payout_ratio: number | null;
  };
  ownership: {
    insider_pct: number | null;
    institutional_pct: number | null;
    short_pct_float: number | null;
  };
  analyst: {
    recommendation_mean: number | null;
    n_analysts: number | null;
    target_mean: number | null;
    target_high: number | null;
    target_low: number | null;
    upside_pct: number | null;
  };
}

function fmt(val: number | null | undefined, decimals = 2, suffix = ''): string {
  if (val == null || isNaN(val)) return '—';
  return `${val.toFixed(decimals)}${suffix}`;
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '—';
  const v = Math.abs(val) > 1.0 ? val : val * 100;
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function fmtDivYield(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '—';
  const v = Math.abs(val) > 1.0 ? val : val * 100;
  return `${v.toFixed(2)}%`;
}

function fmtUpside(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '—';
  const v = Math.abs(val) > 1.0 ? val : val * 100;
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function fmtCurrencyAmount(val: number | null | undefined, market: 'IN' | 'US'): string {
  if (val == null || isNaN(val)) return '—';
  if (market === 'IN') {
    if (Math.abs(val) >= 1e12) {
      return `₹${(val / 1e12).toFixed(2)} Lakh Cr`;
    }
    if (Math.abs(val) >= 1e7) {
      return `₹${(val / 1e7).toLocaleString(undefined, { maximumFractionDigits: 1 })} Cr`;
    }
    return `₹${val.toLocaleString()}`;
  } else {
    if (Math.abs(val) >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
    if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
    if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
    return `$${val.toFixed(0)}`;
  }
}

function MetricRow({
  label,
  value,
  signal,
  note,
}: {
  label: string;
  value: string;
  signal?: 'good' | 'warn' | 'bad' | 'neutral';
  note?: string;
}) {
  const signalClass =
    signal === 'good'
      ? 'text-emerald-400'
      : signal === 'warn'
      ? 'text-amber-400'
      : signal === 'bad'
      ? 'text-rose-400'
      : 'text-slate-200';

  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-800/50 last:border-0 group">
      <div className="flex flex-col min-w-0">
        <span className="text-slate-400 text-[11px] leading-tight">{label}</span>
        {note && <span className="text-slate-600 text-[10px] leading-tight font-sans">{note}</span>}
      </div>
      <span className={`text-xs font-mono font-bold tabular-nums ml-4 flex-shrink-0 ${signalClass}`}>
        {value}
      </span>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-0.5">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0" />
        <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">{title}</span>
      </div>
      {children}
    </div>
  );
}

function RatingGauge({ score, verdict }: { score: number; verdict?: string }) {
  const color =
    score >= 75 ? '#10b981' : score >= 50 ? '#f59e0b' : '#f43f5e';
  const label =
    verdict ||
    (score >= 80
      ? 'STRONG BUY'
      : score >= 65
      ? 'BUY'
      : score >= 50
      ? 'HOLD'
      : score >= 35
      ? 'CAUTION'
      : 'AVOID');

  return (
    <div className="flex flex-col items-center gap-1 shrink-0">
      <div
        className="w-16 h-16 rounded-full border-4 flex items-center justify-center font-mono font-black text-2xl shadow-lg"
        style={{ borderColor: color, color }}
      >
        {score}
      </div>
      <span className="text-[10px] font-bold uppercase tracking-widest text-center" style={{ color }}>
        {label}
      </span>
      <span className="text-slate-500 text-[9px] font-mono">/ 100</span>
    </div>
  );
}

interface Props {
  symbol: string;
  market: 'IN' | 'US';
}

export const FundamentalReport: React.FC<Props> = ({ symbol, market }) => {
  const [data, setData] = useState<FundamentalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<'ALL' | 'PASS' | 'CAUTION' | 'FAIL'>('ALL');
  const [activeCategory, setActiveCategory] = useState<string>('ALL');

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_BASE}/fundamentals/${encodeURIComponent(symbol)}?market=${market}`);
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt.slice(0, 120));
      }
      const json = await res.json();
      setData(json);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch fundamentals');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [symbol, market]);

  if (loading) {
    return (
      <div className="p-8 text-center text-slate-400 text-xs animate-pulse flex flex-col items-center gap-3">
        <RefreshCw className="w-5 h-5 animate-spin text-indigo-400" />
        <span>Evaluating Reddit/Medium Institutional Fundamental criteria for {symbol}...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 flex flex-col items-center gap-3 text-center">
        <AlertTriangle className="w-8 h-8 text-amber-400" />
        <p className="text-slate-400 text-xs">{error || 'No fundamental data available'}</p>
        <button
          onClick={fetchData}
          className="text-xs px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-200 border border-slate-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  const score = data.overall_score ?? data.score ?? 50;
  const currency = market === 'IN' ? '₹' : '$';
  const verdict = data.verdict || (score >= 75 ? 'STRONG BUY' : score >= 55 ? 'BUY' : 'HOLD');
  const conclusion =
    data.conclusion ||
    (score >= 75
      ? 'High-Quality Compounder: Outstanding capital returns, fortress balance sheet, and robust cash flow conversion.'
      : score >= 55
      ? 'Reasonable Quality: Healthy fundamentals with fair valuation; monitor debt and margin trends.'
      : 'High Fundamental Risk: Caution advised due to high leverage or weak cash conversion.');

  const peLynchBucket = data.lynch_bucket || 'Moderate Growth';

  const analystLabel = (() => {
    const m = data.analyst?.recommendation_mean;
    if (m == null) return '—';
    if (m <= 1.5) return 'Strong Buy';
    if (m <= 2.5) return 'Buy';
    if (m <= 3.5) return 'Hold';
    if (m <= 4.5) return 'Sell';
    return 'Strong Sell';
  })();

  const v = data.valuation;
  const p = data.profitability;
  const g = data.growth;
  const b = data.balance_sheet;
  const cf = data.cashflow;
  const div = data.dividends;
  const own = data.ownership;
  const a = data.analyst;
  const pr = data.price;

  const w52High = pr.w52_high ?? pr['52w_high'];
  const w52Low = pr.w52_low ?? pr['52w_low'];
  const y3High = pr['3y_high'] ?? pr.w3y_high;
  const y3Low = pr['3y_low'] ?? pr.w3y_low;

  // Criteria checklist
  const checklist = data.criteria_checklist || [];
  const passedCount = data.passed_count ?? checklist.filter((c) => c.status === 'PASS').length;
  const cautionCount = data.caution_count ?? checklist.filter((c) => c.status === 'CAUTION').length;
  const failedCount = data.failed_count ?? checklist.filter((c) => c.status === 'FAIL').length;

  const categories = ['ALL', ...Array.from(new Set(checklist.map((c) => c.category)))];

  const filteredChecklist = checklist.filter((item) => {
    if (filterStatus !== 'ALL' && item.status !== filterStatus) return false;
    if (activeCategory !== 'ALL' && item.category !== activeCategory) return false;
    return true;
  });

  return (
    <div className="flex flex-col gap-4">
      {/* ── Conclusion & Rating Banner (Requested by user) ── */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 sm:p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xl">
        <div className="flex items-center gap-4 min-w-0">
          <RatingGauge score={score} verdict={verdict} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="font-bold text-white text-lg font-mono tracking-tight">{symbol}</span>
              <span className="text-slate-400 text-xs truncate max-w-[200px] sm:max-w-xs">{data.company.name}</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-indigo-300 border border-indigo-900/50 font-medium">
                {data.company.sector}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/60 text-emerald-300 border border-emerald-800/50 font-mono font-bold">
                {verdict}
              </span>
            </div>

            <div className="p-2.5 rounded-xl bg-slate-950/70 border border-slate-800/80 mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400 block mb-0.5">
                Executive Conclusion:
              </span>
              <p className="text-slate-200 text-xs font-medium leading-relaxed">{conclusion}</p>
            </div>

            <p className="text-slate-400 text-[11px] leading-relaxed flex items-center gap-2 flex-wrap">
              <span>
                <strong className="text-slate-300">Lynch Style:</strong>{' '}
                <span className="text-slate-200">{peLynchBucket}</span>
              </span>
              <span>·</span>
              <span>
                <strong className="text-slate-300">Market Cap:</strong>{' '}
                <span className="text-slate-200 font-mono">{fmtCurrencyAmount(v.market_cap, market)}</span>
              </span>
              {a.target_mean != null && (
                <>
                  <span>·</span>
                  <span>
                    <strong className="text-slate-300">Target:</strong>{' '}
                    <span className="text-slate-200 font-mono">
                      {currency}{a.target_mean.toFixed(2)} ({fmtUpside(a.upside_pct)} upside)
                    </span>
                  </span>
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex md:flex-col items-center md:items-end justify-between w-full md:w-auto gap-2 border-t md:border-t-0 pt-2 md:pt-0 border-slate-800">
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white flex items-center gap-1.5 text-xs transition-colors shrink-0"
            title="Refresh Analysis"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Re-Audit</span>
          </button>
          <span className="text-slate-500 text-[10px] font-mono flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {new Date(data.last_updated).toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* ── Reddit / Medium Institutional Criteria Checklist Section ── */}
      {checklist.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 flex flex-col gap-3 shadow-lg">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-400" />
              <div>
                <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                  Reddit & Medium Institutional Screener Checklist
                </h4>
                <p className="text-[11px] text-slate-400">
                  Strict 15-criteria pass/caution/fail scorecard based on Peter Lynch, Ben Graham, and Screener.in value investing models.
                </p>
              </div>
            </div>

            {/* Status Counters */}
            <div className="flex items-center gap-2 shrink-0">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-950/70 border border-emerald-800/60 text-emerald-400 font-mono text-xs font-bold">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                {passedCount} Pass
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-950/70 border border-amber-800/60 text-amber-400 font-mono text-xs font-bold">
                <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
                {cautionCount} Caution
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-rose-950/70 border border-rose-800/60 text-rose-400 font-mono text-xs font-bold">
                <XCircle className="w-3.5 h-3.5 text-rose-400" />
                {failedCount} Fail
              </span>
            </div>
          </div>

          {/* Filter Pills */}
          <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[11px] text-slate-400 mr-1 flex items-center gap-1">
                <Filter className="w-3 h-3 text-slate-500" /> Filter:
              </span>
              <button
                onClick={() => setFilterStatus('ALL')}
                className={`text-[11px] px-2.5 py-1 rounded-lg font-medium transition-colors ${
                  filterStatus === 'ALL'
                    ? 'bg-indigo-600 text-white font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                All ({checklist.length})
              </button>
              <button
                onClick={() => setFilterStatus('PASS')}
                className={`text-[11px] px-2.5 py-1 rounded-lg font-medium transition-colors flex items-center gap-1 ${
                  filterStatus === 'PASS'
                    ? 'bg-emerald-600 text-white font-bold'
                    : 'bg-slate-800 text-emerald-400 hover:bg-slate-700'
                }`}
              >
                <Check className="w-3 h-3" /> Passed ({passedCount})
              </button>
              <button
                onClick={() => setFilterStatus('CAUTION')}
                className={`text-[11px] px-2.5 py-1 rounded-lg font-medium transition-colors flex items-center gap-1 ${
                  filterStatus === 'CAUTION'
                    ? 'bg-amber-600 text-white font-bold'
                    : 'bg-slate-800 text-amber-400 hover:bg-slate-700'
                }`}
              >
                <AlertCircle className="w-3 h-3" /> Caution ({cautionCount})
              </button>
              <button
                onClick={() => setFilterStatus('FAIL')}
                className={`text-[11px] px-2.5 py-1 rounded-lg font-medium transition-colors flex items-center gap-1 ${
                  filterStatus === 'FAIL'
                    ? 'bg-rose-600 text-white font-bold'
                    : 'bg-slate-800 text-rose-400 hover:bg-slate-700'
                }`}
              >
                <X className="w-3 h-3" /> Failed ({failedCount})
              </button>
            </div>

            {/* Category Filter */}
            <div className="flex items-center gap-1 flex-wrap">
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat)}
                  className={`text-[10px] px-2 py-0.5 rounded font-mono transition-colors ${
                    activeCategory === cat
                      ? 'bg-slate-700 text-white font-bold border border-slate-600'
                      : 'bg-slate-950 text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          {/* Checklist Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 mt-1">
            {filteredChecklist.map((c) => {
              const badgeBg =
                c.status === 'PASS'
                  ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800/80'
                  : c.status === 'CAUTION'
                  ? 'bg-amber-950/80 text-amber-300 border-amber-800/80'
                  : 'bg-rose-950/80 text-rose-300 border-rose-800/80';

              const badgeIcon =
                c.status === 'PASS' ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                ) : c.status === 'CAUTION' ? (
                  <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 text-rose-400" />
                );

              return (
                <div
                  key={c.id}
                  className="bg-slate-950/60 border border-slate-800/90 rounded-xl p-3 flex flex-col justify-between gap-2 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider block">
                        {c.category}
                      </span>
                      <h5 className="text-xs font-bold text-slate-200 leading-snug">{c.name}</h5>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-mono font-bold shrink-0 ${badgeBg}`}
                    >
                      {badgeIcon}
                      {c.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] bg-slate-900/60 px-2.5 py-1.5 rounded-lg border border-slate-800/60">
                    <div>
                      <span className="text-slate-500 text-[10px] block">Target</span>
                      <span className="font-mono text-slate-300 font-semibold">{c.target}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-slate-500 text-[10px] block">Company Actual</span>
                      <span
                        className={`font-mono font-bold ${
                          c.status === 'PASS'
                            ? 'text-emerald-400'
                            : c.status === 'CAUTION'
                            ? 'text-amber-400'
                            : 'text-rose-400'
                        }`}
                      >
                        {c.actual}
                      </span>
                    </div>
                  </div>

                  <p className="text-[11px] text-slate-400 leading-tight font-sans">
                    {c.explanation}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Deep Metric Breakdown Grid ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {/* Price & 52w */}
        <Section icon={Activity} title="Price & Technical">
          <MetricRow
            label="Current Market Price"
            value={pr.current != null ? `${currency}${pr.current.toFixed(2)}` : '—'}
          />
          <MetricRow
            label="52-Week High"
            value={w52High != null ? `${currency}${w52High.toFixed(2)}` : '—'}
            note={pr.w52_pct_from_high != null ? `${(pr.w52_pct_from_high * 100).toFixed(1)}% from high` : undefined}
            signal={pr.w52_pct_from_high != null && pr.w52_pct_from_high > -0.1 ? 'good' : pr.w52_pct_from_high != null && pr.w52_pct_from_high > -0.25 ? 'warn' : 'bad'}
          />
          <MetricRow
            label="52-Week Low"
            value={w52Low != null ? `${currency}${w52Low.toFixed(2)}` : '—'}
            note={pr.w52_pct_from_low != null ? `+${(pr.w52_pct_from_low * 100).toFixed(1)}% from low` : undefined}
          />
          <MetricRow
            label="3yr High / Low"
            value={
              y3High != null && y3Low != null
                ? `${currency}${y3High.toFixed(0)} / ${currency}${y3Low.toFixed(0)}`
                : w52High != null && w52Low != null
                ? `${currency}${w52High.toFixed(0)} / ${currency}${w52Low.toFixed(0)}`
                : '—'
            }
          />
          <MetricRow
            label="Beta (Market Sensitivity)"
            value={fmt(pr.beta, 2)}
            signal={pr.beta != null ? (pr.beta < 1 ? 'good' : pr.beta < 1.5 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Valuation */}
        <Section icon={DollarSign} title="Valuation Multiples">
          <MetricRow
            label="P/E Ratio (Trailing)"
            value={fmt(v.pe_trailing, 1, 'x')}
            signal={v.pe_trailing != null ? (v.pe_trailing > 0 && v.pe_trailing < 20 ? 'good' : v.pe_trailing < 35 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="P/E (Forward)"
            value={fmt(v.pe_forward, 1, 'x')}
            signal={v.pe_forward != null ? (v.pe_forward > 0 && v.pe_forward < 20 ? 'good' : v.pe_forward < 35 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="PEG Ratio (Peter Lynch)"
            value={fmt(v.peg, 2, 'x')}
            note="< 1.0 = Undervalued vs Growth"
            signal={v.peg != null ? (v.peg < 1 ? 'good' : v.peg < 2 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Price / Book (P/B)"
            value={fmt(v.price_to_book, 2, 'x')}
            signal={v.price_to_book != null ? (v.price_to_book < 3 ? 'good' : v.price_to_book < 7 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Graham Ratio (P/E × P/B)"
            value={v.graham_ratio != null ? `${v.graham_ratio.toFixed(1)}x` : v.pe_trailing && v.price_to_book ? `${(v.pe_trailing * v.price_to_book).toFixed(1)}x` : '—'}
            note="Ben Graham benchmark: < 22.5"
            signal={
              (v.graham_ratio ?? (v.pe_trailing && v.price_to_book ? v.pe_trailing * v.price_to_book : null)) != null
                ? (v.graham_ratio ?? (v.pe_trailing! * v.price_to_book!)) <= 22.5
                  ? 'good'
                  : 'warn'
                : 'neutral'
            }
          />
          <MetricRow label="Price / Sales" value={fmt(v.price_to_sales, 2, 'x')} />
          <MetricRow
            label="EV / EBITDA"
            value={fmt(v.ev_to_ebitda, 1, 'x')}
            signal={v.ev_to_ebitda != null ? (v.ev_to_ebitda < 14 ? 'good' : v.ev_to_ebitda < 22 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow label="Market Cap" value={fmtCurrencyAmount(v.market_cap, market)} />
        </Section>

        {/* Profitability */}
        <Section icon={TrendingUp} title="Profitability & Returns">
          <MetricRow
            label="Return on Capital Employed (ROCE)"
            value={p.roce != null ? fmtPct(p.roce) : '—'}
            note="EBIT / (Total Equity + Debt)"
            signal={p.roce != null ? (p.roce > 0.18 ? 'good' : p.roce > 0.1 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Return on Equity (ROE)"
            value={fmtPct(p.roe)}
            signal={p.roe != null ? (p.roe > 0.18 ? 'good' : p.roe > 0.12 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Return on Assets (ROA)"
            value={fmtPct(p.roa)}
            signal={p.roa != null ? (p.roa > 0.08 ? 'good' : p.roa > 0.04 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Operating Profit Margin"
            value={fmtPct(p.operating_margin)}
            signal={p.operating_margin != null ? (p.operating_margin > 0.2 ? 'good' : p.operating_margin > 0.1 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Net Profit Margin"
            value={fmtPct(p.net_margin)}
            signal={p.net_margin != null ? (p.net_margin > 0.15 ? 'good' : p.net_margin > 0.05 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow label="Gross Margin" value={fmtPct(p.gross_margin)} />
        </Section>

        {/* Growth */}
        <Section icon={BarChart2} title="Growth & Earnings">
          <MetricRow
            label="Revenue Growth (YoY)"
            value={fmtPct(g.revenue_growth_yoy)}
            note="3yr annual sales growth proxy"
            signal={g.revenue_growth_yoy != null ? (g.revenue_growth_yoy > 0.15 ? 'good' : g.revenue_growth_yoy > 0 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Earnings Growth (YoY)"
            value={fmtPct(g.earnings_growth_yoy)}
            note="3yr profit growth proxy"
            signal={g.earnings_growth_yoy != null ? (g.earnings_growth_yoy > 0.2 ? 'good' : g.earnings_growth_yoy > 0 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Earnings Growth (QoQ)"
            value={fmtPct(g.earnings_growth_qoq)}
            signal={g.earnings_growth_qoq != null ? (g.earnings_growth_qoq > 0.1 ? 'good' : g.earnings_growth_qoq > 0 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Peter Lynch Bucket"
            value={peLynchBucket}
            signal={
              peLynchBucket === 'Fast Grower' || peLynchBucket === 'Growth at Reasonable Price' ? 'good' :
              peLynchBucket === 'Value' || peLynchBucket === 'Deep Value' ? 'warn' : 'neutral'
            }
          />
        </Section>

        {/* Balance Sheet & Cash Flow */}
        <Section icon={Shield} title="Balance Sheet & Solvency">
          <MetricRow
            label="Current Ratio"
            value={fmt(b.current_ratio, 2, 'x')}
            note="> 1.5x = healthy working capital"
            signal={b.current_ratio != null ? (b.current_ratio > 1.5 ? 'good' : b.current_ratio >= 1.0 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Quick Ratio"
            value={fmt(b.quick_ratio, 2, 'x')}
            signal={b.quick_ratio != null ? (b.quick_ratio > 1.2 ? 'good' : b.quick_ratio >= 0.9 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Debt to Equity"
            value={fmt(b.debt_to_equity, 2, 'x')}
            note="< 0.5x = fortress / zero-debt"
            signal={b.debt_to_equity != null ? (b.debt_to_equity < 0.5 ? 'good' : b.debt_to_equity < 1.0 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Free Cash Flow"
            value={fmtCurrencyAmount(cf.free_cash_flow, market)}
            signal={cf.free_cash_flow != null ? (cf.free_cash_flow > 0 ? 'good' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Operating Cash Flow"
            value={fmtCurrencyAmount(cf.operating_cash_flow, market)}
            signal={cf.operating_cash_flow != null ? (cf.operating_cash_flow > 0 ? 'good' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="FCF Yield"
            value={cf.fcf_yield != null ? `${cf.fcf_yield.toFixed(2)}%` : '—'}
            signal={cf.fcf_yield != null ? (cf.fcf_yield > 4 ? 'good' : cf.fcf_yield > 1 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Dividends & Ownership */}
        <Section icon={Users} title="Dividends & Promoter / Insider">
          <MetricRow
            label="Dividend Yield"
            value={fmtDivYield(div.yield)}
            signal={div.yield != null ? (div.yield > 0.015 || div.yield > 1.5 ? 'good' : 'neutral') : 'neutral'}
          />
          <MetricRow label="Dividend Rate" value={div.rate != null ? `${currency}${div.rate.toFixed(2)}` : '—'} />
          <MetricRow
            label="Payout Ratio"
            value={fmtPct(div.payout_ratio)}
            note="< 50% = sustainable"
            signal={div.payout_ratio != null ? (div.payout_ratio < 0.5 ? 'good' : div.payout_ratio < 0.75 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Promoter / Insider Holding"
            value={fmtPct(own.insider_pct)}
            note="Skin in the game"
            signal={own.insider_pct != null ? (own.insider_pct > 0.4 ? 'good' : own.insider_pct > 0.15 ? 'warn' : 'neutral') : 'neutral'}
          />
          <MetricRow label="Institutional Ownership" value={fmtPct(own.institutional_pct)} />
          <MetricRow
            label="Short % of Float"
            value={fmtPct(own.short_pct_float)}
            signal={own.short_pct_float != null ? (own.short_pct_float < 0.05 ? 'good' : own.short_pct_float < 0.15 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Analyst & Consensus */}
        <Section icon={Target} title="Analyst Targets & Breadth">
          <MetricRow
            label="Analyst Consensus"
            value={`${analystLabel} (${fmt(a.recommendation_mean, 1)})`}
            signal={a.recommendation_mean != null ? (a.recommendation_mean <= 2 ? 'good' : a.recommendation_mean <= 3 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow label="Coverage Count" value={a.n_analysts != null ? `${a.n_analysts} Analysts` : '—'} />
          <MetricRow label="Target Price (Mean)" value={a.target_mean != null ? `${currency}${a.target_mean.toFixed(2)}` : '—'} />
          <MetricRow label="Target Price (High)" value={a.target_high != null ? `${currency}${a.target_high.toFixed(2)}` : '—'} />
          <MetricRow label="Target Price (Low)" value={a.target_low != null ? `${currency}${a.target_low.toFixed(2)}` : '—'} />
          <MetricRow
            label="Consensus Upside"
            value={fmtUpside(a.upside_pct)}
            signal={a.upside_pct != null ? (a.upside_pct > 0.15 || a.upside_pct > 15 ? 'good' : a.upside_pct > 0 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Risk Flags */}
        <Section icon={AlertTriangle} title="Institutional Risk Checks">
          <MetricRow
            label="Excessive Debt (> 1.5x D/E)"
            value={b.debt_to_equity != null && b.debt_to_equity > 1.5 ? `HIGH (${b.debt_to_equity.toFixed(2)}x)` : 'Clean / Low Debt'}
            signal={b.debt_to_equity != null && b.debt_to_equity > 1.5 ? 'bad' : 'good'}
          />
          <MetricRow
            label="Negative Free Cash Flow"
            value={cf.free_cash_flow != null && cf.free_cash_flow < 0 ? 'YES — Cash Burn' : 'Positive FCF'}
            signal={cf.free_cash_flow != null && cf.free_cash_flow < 0 ? 'bad' : 'good'}
          />
          <MetricRow
            label="Negative Net Margin"
            value={p.net_margin != null && p.net_margin < 0 ? 'Losing Money' : 'Profitable'}
            signal={p.net_margin != null && p.net_margin < 0 ? 'bad' : 'good'}
          />
          <MetricRow
            label="Pledged Shares / Related Party"
            value="Check Exchange Filings"
            note="Verify on Screener.in / SEC Edgar"
            signal="neutral"
          />
          <MetricRow
            label="Beta Volatility"
            value={pr.beta != null && pr.beta > 1.8 ? `High Vol (${pr.beta.toFixed(2)})` : pr.beta != null ? `Balanced (${pr.beta.toFixed(2)})` : '—'}
            signal={pr.beta != null ? (pr.beta > 1.8 ? 'bad' : 'good') : 'neutral'}
          />
        </Section>
      </div>

      {/* ── Institutional Legal & Research Disclaimer ── */}
      <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3.5 flex items-start gap-2.5">
        <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
        <p className="text-slate-500 text-[11px] leading-relaxed">
          <strong className="text-slate-400">Institutional Methodology & Data Disclosure:</strong> Score and pass/caution/fail tags are calculated via benchmarked value-investing criteria (Peter Lynch, Benjamin Graham, ROCE/FCF models). All live fundamental multiples are sourced via real-time and delayed exchange feeds (Yahoo Finance). Pledged percentage, capacity utilisation, auditor qualifications, and related-party transactions require statutory filings from NSE/BSE (for India) or SEC Form 10-K/10-Q (for US). This is automated quantitative decision support, not financial advice.
        </p>
      </div>
    </div>
  );
};
