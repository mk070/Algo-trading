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
} from 'lucide-react';
import { API_BASE } from '../api/client';

interface FundamentalData {
  symbol: string;
  market: string;
  provider: string;
  last_updated: string;
  company: { name: string; sector: string; industry: string; country: string };
  price: {
    current: number | null;
    w52_high: number | null;
    w52_low: number | null;
    w52_pct_from_high: number | null;
    w52_pct_from_low: number | null;
    beta: number | null;
  };
  valuation: {
    pe_trailing: number | null;
    pe_forward: number | null;
    peg: number | null;
    price_to_book: number | null;
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
  const v = val * 100;
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function fmtLargeCap(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return '—';
  if (Math.abs(val) >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
  return `$${val.toFixed(0)}`;
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

function scoreData(data: FundamentalData): number {
  let score = 50; // start at 50
  const v = data.valuation;
  const p = data.profitability;
  const g = data.growth;
  const b = data.balance_sheet;
  const cf = data.cashflow;
  const o = data.ownership;
  const a = data.analyst;

  // Valuation (max ±12)
  if (v.pe_trailing != null) {
    if (v.pe_trailing > 0 && v.pe_trailing < 15) score += 5;
    else if (v.pe_trailing > 0 && v.pe_trailing < 25) score += 2;
    else if (v.pe_trailing > 50) score -= 5;
    else if (v.pe_trailing < 0) score -= 3;
  }
  if (v.peg != null && v.peg > 0) {
    if (v.peg < 1) score += 5;
    else if (v.peg < 1.5) score += 2;
    else if (v.peg > 3) score -= 4;
  }
  if (v.price_to_book != null) {
    if (v.price_to_book < 2) score += 2;
    else if (v.price_to_book > 10) score -= 2;
  }

  // Profitability (max ±15)
  if (p.roe != null) {
    if (p.roe > 0.2) score += 6;
    else if (p.roe > 0.12) score += 3;
    else if (p.roe < 0) score -= 5;
  }
  if (p.operating_margin != null) {
    if (p.operating_margin > 0.2) score += 5;
    else if (p.operating_margin > 0.1) score += 2;
    else if (p.operating_margin < 0) score -= 5;
  }
  if (p.net_margin != null) {
    if (p.net_margin > 0.15) score += 4;
    else if (p.net_margin > 0.05) score += 1;
    else if (p.net_margin < 0) score -= 4;
  }

  // Growth (max ±12)
  if (g.revenue_growth_yoy != null) {
    if (g.revenue_growth_yoy > 0.2) score += 6;
    else if (g.revenue_growth_yoy > 0.1) score += 3;
    else if (g.revenue_growth_yoy < 0) score -= 4;
  }
  if (g.earnings_growth_yoy != null) {
    if (g.earnings_growth_yoy > 0.25) score += 6;
    else if (g.earnings_growth_yoy > 0.1) score += 3;
    else if (g.earnings_growth_yoy < -0.1) score -= 5;
  }

  // Balance Sheet (max ±8)
  if (b.current_ratio != null) {
    if (b.current_ratio > 2) score += 3;
    else if (b.current_ratio > 1) score += 1;
    else if (b.current_ratio < 1) score -= 4;
  }
  if (b.debt_to_equity != null) {
    if (b.debt_to_equity < 0.3) score += 5;
    else if (b.debt_to_equity < 1) score += 2;
    else if (b.debt_to_equity > 3) score -= 5;
  }

  // Free Cash Flow (max ±5)
  if (cf.free_cash_flow != null) {
    if (cf.free_cash_flow > 0) score += 5;
    else score -= 3;
  }

  // Ownership (max ±4)
  if (o.insider_pct != null) {
    if (o.insider_pct > 0.1) score += 2;
  }
  if (o.short_pct_float != null) {
    if (o.short_pct_float > 0.2) score -= 4;
    else if (o.short_pct_float < 0.05) score += 2;
  }

  // Analyst (max ±5)
  if (a.upside_pct != null) {
    if (a.upside_pct > 0.2) score += 5;
    else if (a.upside_pct > 0.1) score += 2;
    else if (a.upside_pct < -0.1) score -= 3;
  }

  return Math.min(100, Math.max(0, Math.round(score)));
}

function RatingGauge({ score }: { score: number }) {
  const color =
    score >= 70 ? '#10b981' : score >= 50 ? '#f59e0b' : '#f43f5e';
  const label =
    score >= 80 ? 'STRONG BUY' :
    score >= 65 ? 'BUY' :
    score >= 50 ? 'HOLD' :
    score >= 35 ? 'CAUTION' : 'AVOID';

  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="w-16 h-16 rounded-full border-4 flex items-center justify-center font-mono font-black text-xl"
        style={{ borderColor: color, color }}
      >
        {score}
      </div>
      <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color }}>
        {label}
      </span>
      <span className="text-slate-500 text-[9px]">/ 100</span>
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
      <div className="p-6 text-center text-slate-400 text-xs animate-pulse">
        Loading fundamental analysis for {symbol}...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 flex flex-col items-center gap-3 text-center">
        <AlertTriangle className="w-6 h-6 text-amber-400" />
        <p className="text-slate-400 text-xs">{error || 'No data available'}</p>
        <button
          onClick={fetchData}
          className="text-xs px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-200 border border-slate-700"
        >
          Retry
        </button>
      </div>
    );
  }

  const score = scoreData(data);
  const currency = market === 'IN' ? '₹' : '$';

  const peLynchBucket = (() => {
    const pe = data.valuation.pe_trailing;
    const peg = data.valuation.peg;
    const rev = data.growth.revenue_growth_yoy;
    if (!pe) return 'Unknown';
    if (pe < 10) return 'Deep Value';
    if (pe < 15) return 'Value';
    if (pe < 25 && peg != null && peg < 1) return 'Growth at Reasonable Price';
    if (rev != null && rev > 0.25 && pe < 40) return 'Fast Grower';
    if (pe > 50) return 'Aggressive Growth / Speculative';
    return 'Moderate Growth';
  })();

  const analystLabel = (() => {
    const m = data.analyst.recommendation_mean;
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

  return (
    <div className="flex flex-col gap-3">
      {/* Header: Conclusion + Rating */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-start gap-4 flex-wrap">
        <RatingGauge score={score} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-bold text-white text-base font-mono">{symbol}</span>
            <span className="text-slate-400 text-xs truncate">{data.company.name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              {data.company.sector}
            </span>
          </div>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            <strong className="text-slate-100">Peter Lynch Bucket:</strong> {peLynchBucket} ·{' '}
            <strong className="text-slate-100">Industry:</strong> {data.company.industry} ·{' '}
            <strong className="text-slate-100">Country:</strong> {data.company.country}
          </p>
          <p className="text-slate-400 text-[11px] mt-1 leading-relaxed">
            {a.recommendation_mean != null && (
              <>
                <strong className="text-slate-300">Analyst Consensus:</strong> {analystLabel} ({a.n_analysts} analysts) ·{' '}
                <strong className="text-slate-300">Target:</strong>{' '}
                {currency}{a.target_mean?.toFixed(2) ?? '—'} ({a.upside_pct != null ? `${(a.upside_pct * 100).toFixed(1)}% upside` : '—'}) ·{' '}
              </>
            )}
            <strong className="text-slate-300">Market Cap:</strong> {fmtLargeCap(v.market_cap)}
          </p>
          <div className="flex items-center gap-1 mt-1.5">
            <Clock className="w-3 h-3 text-slate-600" />
            <span className="text-slate-600 text-[9px]">
              Data via yfinance · delayed · {new Date(data.last_updated).toLocaleTimeString()}
            </span>
          </div>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-400 hover:text-white flex-shrink-0"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Grid of metric sections */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">

        {/* Price & 52w */}
        <Section icon={Activity} title="Price & Technical">
          <MetricRow label="Current Price" value={pr.current != null ? `${currency}${pr.current.toFixed(2)}` : '—'} />
          <MetricRow
            label="52-Week High"
            value={pr.w52_high != null ? `${currency}${pr.w52_high.toFixed(2)}` : '—'}
            note={pr.w52_pct_from_high != null ? `${(pr.w52_pct_from_high * 100).toFixed(1)}% from high` : undefined}
            signal={pr.w52_pct_from_high != null && pr.w52_pct_from_high > -0.1 ? 'good' : pr.w52_pct_from_high != null && pr.w52_pct_from_high > -0.25 ? 'warn' : 'bad'}
          />
          <MetricRow label="52-Week Low" value={pr.w52_low != null ? `${currency}${pr.w52_low.toFixed(2)}` : '—'} />
          <MetricRow
            label="3yr High / Low"
            value={pr.w52_high != null && pr.w52_low != null ? `${currency}${pr.w52_high.toFixed(0)} / ${currency}${pr.w52_low.toFixed(0)}` : '—'}
          />
          <MetricRow
            label="Beta (Market Sensitivity)"
            value={fmt(pr.beta, 2)}
            signal={pr.beta != null ? (pr.beta < 1 ? 'good' : pr.beta < 1.5 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Valuation */}
        <Section icon={DollarSign} title="Valuation">
          <MetricRow
            label="P/E (Trailing)"
            value={fmt(v.pe_trailing, 1, 'x')}
            signal={v.pe_trailing != null ? (v.pe_trailing > 0 && v.pe_trailing < 20 ? 'good' : v.pe_trailing < 35 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="P/E (Forward)"
            value={fmt(v.pe_forward, 1, 'x')}
            signal={v.pe_forward != null ? (v.pe_forward > 0 && v.pe_forward < 20 ? 'good' : v.pe_forward < 35 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="PEG Ratio"
            value={fmt(v.peg, 2, 'x')}
            note="< 1 = undervalued vs growth"
            signal={v.peg != null ? (v.peg < 1 ? 'good' : v.peg < 2 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Price / Book (P/B)"
            value={fmt(v.price_to_book, 2, 'x')}
            signal={v.price_to_book != null ? (v.price_to_book < 2 ? 'good' : v.price_to_book < 5 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow label="Price / Sales" value={fmt(v.price_to_sales, 2, 'x')} />
          <MetricRow
            label="EV / EBITDA"
            value={fmt(v.ev_to_ebitda, 1, 'x')}
            signal={v.ev_to_ebitda != null ? (v.ev_to_ebitda < 12 ? 'good' : v.ev_to_ebitda < 20 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow label="Market Cap" value={fmtLargeCap(v.market_cap)} />
          <MetricRow label="Enterprise Value" value={fmtLargeCap(v.enterprise_value)} />
        </Section>

        {/* Profitability */}
        <Section icon={TrendingUp} title="Profitability">
          <MetricRow
            label="Return on Equity (ROE)"
            value={fmtPct(p.roe)}
            signal={p.roe != null ? (p.roe > 0.2 ? 'good' : p.roe > 0.1 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Return on Capital Employed (ROCE)"
            value={fmtPct(p.roce)}
            signal={p.roce != null ? (p.roce > 0.15 ? 'good' : p.roce > 0.08 ? 'warn' : 'bad') : 'neutral'}
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
        <Section icon={BarChart2} title="Growth">
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

        {/* Balance Sheet */}
        <Section icon={Shield} title="Balance Sheet">
          <MetricRow
            label="Current Ratio"
            value={fmt(b.current_ratio, 2, 'x')}
            note="> 1.5 = healthy"
            signal={b.current_ratio != null ? (b.current_ratio > 2 ? 'good' : b.current_ratio > 1 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Quick Ratio"
            value={fmt(b.quick_ratio, 2, 'x')}
            signal={b.quick_ratio != null ? (b.quick_ratio > 1.5 ? 'good' : b.quick_ratio > 1 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Debt / Equity"
            value={fmt(b.debt_to_equity, 2, 'x')}
            note="< 1 = low leverage"
            signal={b.debt_to_equity != null ? (b.debt_to_equity < 0.5 ? 'good' : b.debt_to_equity < 1.5 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow label="Free Cash Flow" value={fmtLargeCap(cf.free_cash_flow)} signal={cf.free_cash_flow != null ? (cf.free_cash_flow > 0 ? 'good' : 'bad') : 'neutral'} />
          <MetricRow label="Operating Cash Flow" value={fmtLargeCap(cf.operating_cash_flow)} signal={cf.operating_cash_flow != null ? (cf.operating_cash_flow > 0 ? 'good' : 'bad') : 'neutral'} />
          <MetricRow
            label="FCF Yield"
            value={fmtPct(cf.fcf_yield)}
            signal={cf.fcf_yield != null ? (cf.fcf_yield > 0.04 ? 'good' : cf.fcf_yield > 0.01 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Dividends & Ownership */}
        <Section icon={Users} title="Dividends & Ownership">
          <MetricRow
            label="Dividend Yield"
            value={div.yield != null ? `${(div.yield * 100).toFixed(2)}%` : '—'}
            signal={div.yield != null ? (div.yield > 0.02 ? 'good' : div.yield > 0 ? 'warn' : 'neutral') : 'neutral'}
          />
          <MetricRow label="Dividend Rate" value={div.rate != null ? `${currency}${div.rate.toFixed(2)}` : '—'} />
          <MetricRow
            label="Payout Ratio"
            value={div.payout_ratio != null ? `${(div.payout_ratio * 100).toFixed(1)}%` : '—'}
            signal={div.payout_ratio != null ? (div.payout_ratio < 0.5 ? 'good' : div.payout_ratio < 0.8 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow
            label="Insider Ownership"
            value={own.insider_pct != null ? `${(own.insider_pct * 100).toFixed(1)}%` : '—'}
            note="Higher = more skin in game"
            signal={own.insider_pct != null ? (own.insider_pct > 0.1 ? 'good' : own.insider_pct > 0.03 ? 'warn' : 'neutral') : 'neutral'}
          />
          <MetricRow label="Institutional Ownership" value={own.institutional_pct != null ? `${(own.institutional_pct * 100).toFixed(1)}%` : '—'} />
          <MetricRow
            label="Short % of Float"
            value={own.short_pct_float != null ? `${(own.short_pct_float * 100).toFixed(1)}%` : '—'}
            note="High short = risk of squeeze or sustained sell"
            signal={own.short_pct_float != null ? (own.short_pct_float < 0.05 ? 'good' : own.short_pct_float < 0.15 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Analyst */}
        <Section icon={Target} title="Analyst Coverage">
          <MetricRow
            label="Consensus"
            value={`${analystLabel} (${fmt(a.recommendation_mean, 1)})`}
            signal={a.recommendation_mean != null ? (a.recommendation_mean <= 2 ? 'good' : a.recommendation_mean <= 3 ? 'warn' : 'bad') : 'neutral'}
          />
          <MetricRow label="Number of Analysts" value={a.n_analysts != null ? `${a.n_analysts}` : '—'} />
          <MetricRow label="Price Target (Mean)" value={a.target_mean != null ? `${currency}${a.target_mean.toFixed(2)}` : '—'} />
          <MetricRow label="Price Target (High)" value={a.target_high != null ? `${currency}${a.target_high.toFixed(2)}` : '—'} />
          <MetricRow label="Price Target (Low)" value={a.target_low != null ? `${currency}${a.target_low.toFixed(2)}` : '—'} />
          <MetricRow
            label="Implied Upside (from current)"
            value={a.upside_pct != null ? `${(a.upside_pct * 100).toFixed(1)}%` : '—'}
            signal={a.upside_pct != null ? (a.upside_pct > 0.2 ? 'good' : a.upside_pct > 0 ? 'warn' : 'bad') : 'neutral'}
          />
        </Section>

        {/* Risk flags */}
        <Section icon={AlertTriangle} title="Risk Flags">
          <MetricRow
            label="High Short Interest"
            value={own.short_pct_float != null && own.short_pct_float > 0.15 ? 'YES — CAUTION' : 'Low / N/A'}
            signal={own.short_pct_float != null && own.short_pct_float > 0.15 ? 'bad' : 'good'}
          />
          <MetricRow
            label="Negative Free Cash Flow"
            value={cf.free_cash_flow != null && cf.free_cash_flow < 0 ? 'YES — Cash Burn' : 'Positive FCF'}
            signal={cf.free_cash_flow != null && cf.free_cash_flow < 0 ? 'bad' : 'good'}
          />
          <MetricRow
            label="High Debt Load"
            value={b.debt_to_equity != null && b.debt_to_equity > 2 ? `D/E ${b.debt_to_equity.toFixed(1)}x — HIGH` : 'Manageable'}
            signal={b.debt_to_equity != null && b.debt_to_equity > 2 ? 'bad' : 'good'}
          />
          <MetricRow
            label="Negative Earnings"
            value={p.net_margin != null && p.net_margin < 0 ? 'Losing Money' : 'Profitable'}
            signal={p.net_margin != null && p.net_margin < 0 ? 'bad' : 'good'}
          />
          <MetricRow
            label="Beta Risk"
            value={pr.beta != null && pr.beta > 2 ? `Beta ${pr.beta.toFixed(1)} — HIGH VOLATILITY` : pr.beta != null ? `Beta ${pr.beta.toFixed(2)} — OK` : '—'}
            signal={pr.beta != null ? (pr.beta > 2 ? 'bad' : pr.beta > 1.5 ? 'warn' : 'good') : 'neutral'}
          />
        </Section>

        {/* DISCLAIMER */}
        <div className="sm:col-span-2 lg:col-span-3 bg-slate-950 border border-slate-800/60 rounded-xl p-3">
          <p className="text-slate-600 text-[10px] leading-relaxed">
            <AlertTriangle className="w-3 h-3 inline mr-1 text-amber-700" />
            <strong className="text-slate-500">Research only.</strong> All data sourced from Yahoo Finance (yfinance) — delayed, unverified. This rating is a rules-based heuristic score, not investment advice. 
            Promoter holding, pledging, related-party transactions, auditor qualifications, capacity utilisation, and working capital trends require company filings and are not available via this data source.
            Always verify against official exchange filings (NSE/BSE/SEC) before making any trading decisions. Past performance does not guarantee future results.
          </p>
        </div>
      </div>
    </div>
  );
};
