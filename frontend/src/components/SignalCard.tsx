import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Copy, Check, ExternalLink, GitCommit, ShieldAlert, Sparkles, TrendingUp } from 'lucide-react';
import { apiClient } from '../api/client';
import { DecisionAudit, Signal } from '../types';

interface SignalCardProps {
  signal: Signal;
  onOpenChart?: (symbol: string) => void;
  onTakeTrade?: (signal: Signal) => void;
}

export const SignalCard: React.FC<SignalCardProps> = ({
  signal,
  onOpenChart,
  onTakeTrade,
}) => {
  const [expandedWhy, setExpandedWhy] = useState(false);
  const [expandedChecklist, setExpandedChecklist] = useState(false);
  const [expandedTrail, setExpandedTrail] = useState(false);
  const [auditData, setAuditData] = useState<DecisionAudit | null>(null);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [copied, setCopied] = useState(false);

  const toggleDecisionTrail = async () => {
    if (!expandedTrail && !auditData) {
      try {
        setLoadingAudit(true);
        const audits = await apiClient.getDecisionAudits(signal.symbol, signal.market);
        if (audits && audits.length > 0) {
          setAuditData(audits[0]);
        }
      } catch (e) {
        console.error('Failed to load decision trail:', e);
      } finally {
        setLoadingAudit(false);
      }
    }
    setExpandedTrail(!expandedTrail);
  };

  const copyOrderSummary = () => {
    const text = `BUY ${signal.symbol} | Trigger: ${signal.trigger.toFixed(2)} | SL: ${signal.stop.toFixed(2)} | Target: ${signal.target1.toFixed(2)} | Qty: ${signal.qty}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getStateBadge = (state: string) => {
    switch (state) {
      case 'TRIGGERED_PROVISIONAL':
      case 'TRIGGERED_CONFIRMED':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'APPROACHING':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/30 animate-pulse';
      case 'EXTENDED':
        return 'bg-purple-500/20 text-purple-300 border-purple-500/30';
      case 'INVALIDATED':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      default:
        return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
    }
  };

  const getNewsBadge = (status?: string) => {
    switch (status) {
      case 'CLEAR':
        return 'bg-emerald-950 text-emerald-400 border-emerald-800';
      case 'REVIEW':
        return 'bg-amber-950 text-amber-400 border-amber-800';
      case 'BLOCKED':
        return 'bg-rose-950 text-rose-400 border-rose-800';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const getSetupLabel = (setup?: string) => {
    if (!setup) return 'Setup Pending';
    if (setup === 'VCP') return 'Tight-Base (VCP)';
    if (setup === 'PULLBACK') return 'Pullback 20 EMA';
    if (setup === 'BREAKOUT') return 'Pivot Breakout';
    if (setup === 'MONITORING') return 'Monitoring Base';
    if (setup === 'NO_SETUP') return 'No Valid Setup';
    return setup;
  };

  const currencySymbol = signal.market === 'IN' ? '₹' : '$';
  const isActionable = signal.state !== 'NO_SETUP' && signal.state !== 'BLOCKED' && signal.state !== 'INVALIDATED' && (signal.trigger || 0) > 0;
  const cleanReasons = (signal.reasons || []).filter((r) => typeof r === 'string' && r.trim().length > 0);

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 flex flex-col gap-4 shadow-lg hover:border-slate-700 transition-all">
      {/* Top Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h3 className="text-xl font-bold tracking-tight text-slate-100">{signal.symbol}</h3>
          <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold border bg-slate-800/80 text-indigo-300 border-indigo-500/20">
            {getSetupLabel(signal.setup)}
          </span>
          <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${getStateBadge(signal.state)}`}>
            {signal.state.replace('_', ' ')}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {/* Gap Risk */}
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700/60" title="95th percentile historical adverse overnight gap">
            Gap: {(signal.gap95 * 100).toFixed(1)}%
          </span>
          {/* Cost in R */}
          <span className={`px-2 py-0.5 rounded border ${signal.cost_in_r > 0.20 ? 'bg-amber-950/60 text-amber-300 border-amber-800' : 'bg-slate-800 text-slate-300 border-slate-700/60'}`} title="Round-trip cost in units of planned risk R">
            Cost: {signal.cost_in_r.toFixed(2)}R
          </span>
          {/* News Coverage */}
          <span className={`px-2 py-0.5 rounded border font-semibold ${getNewsBadge(signal.news_coverage?.status)}`} title="News & Corporate Announcement Verification">
            News: {signal.news_coverage?.status || 'UNKNOWN'}
          </span>
        </div>
      </div>

      {/* Primary Key Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/70 p-3 rounded-lg border border-slate-800/80">
        <div>
          <span className="text-xs text-slate-400 block">Buy Above Trigger</span>
          <span className={`text-base font-bold font-mono ${signal.trigger > 0 ? 'text-emerald-400' : 'text-slate-500'}`}>
            {signal.trigger > 0 ? `${currencySymbol}${signal.trigger.toFixed(2)}` : '—'}
          </span>
        </div>
        <div>
          <span className="text-xs text-slate-400 block">Stop Loss</span>
          <span className={`text-base font-bold font-mono ${signal.stop > 0 ? 'text-rose-400' : 'text-slate-500'}`}>
            {signal.stop > 0 ? `${currencySymbol}${signal.stop.toFixed(2)}` : '—'}
          </span>
        </div>
        <div>
          <span className="text-xs text-slate-400 block">Target 1 (2R)</span>
          <span className={`text-base font-bold font-mono ${signal.target1 > 0 ? 'text-cyan-400' : 'text-slate-500'}`}>
            {signal.target1 > 0 ? `${currencySymbol}${signal.target1.toFixed(2)}` : '—'}
          </span>
        </div>
        <div>
          <span className="text-xs text-slate-400 block">Planned Sizing</span>
          <span className="text-base font-bold text-indigo-300 font-mono">
            {signal.qty > 0 ? (
              <>
                {signal.qty} sh <span className="text-xs text-slate-400">({currencySymbol}{signal.risk_amount.toFixed(0)} risk)</span>
              </>
            ) : (
              <span className="text-slate-500 text-xs">No Active Risk</span>
            )}
          </span>
        </div>
      </div>

      {/* Expandable Why section */}
      <div>
        <button
          onClick={() => setExpandedWhy(!expandedWhy)}
          className="flex items-center justify-between w-full text-xs text-slate-300 font-medium py-1 hover:text-indigo-400"
        >
          <span className="flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Signal Reasoning ({cleanReasons.length} factors)
          </span>
          {expandedWhy ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {expandedWhy && (
          <ul className="mt-2 text-xs text-slate-300 space-y-1 pl-4 list-disc bg-slate-950/40 p-2.5 rounded border border-slate-800/60">
            {cleanReasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>

      {/* Expandable Checklist */}
      {signal.checklist && signal.checklist.length > 0 && (
        <div>
          <button
            onClick={() => setExpandedChecklist(!expandedChecklist)}
            className="flex items-center justify-between w-full text-xs text-slate-300 font-medium py-1 hover:text-indigo-400"
          >
            <span className="flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-blue-400" />
              Minervini Trend Template Checklist ({signal.checklist.filter(c => c.passed).length}/{signal.checklist.length} Passed)
            </span>
            {expandedChecklist ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          {expandedChecklist && (
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1.5 bg-slate-950/40 p-2.5 rounded border border-slate-800/60 text-xs">
              {signal.checklist.map((c, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[10px] font-bold ${c.passed ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                    {c.passed ? '✓' : '✗'}
                  </span>
                  <span className="text-slate-300 truncate">{c.rule}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Decision Trail (Spec 3.11, 4.5) */}
      <div>
        <button
          onClick={toggleDecisionTrail}
          className="flex items-center justify-between w-full text-xs text-slate-300 font-medium py-1 hover:text-cyan-400"
        >
          <span className="flex items-center gap-1.5">
            <GitCommit className="w-3.5 h-3.5 text-cyan-400" />
            Decision Trail: 7-Stage Quantitative Audit (Spec 3.11)
          </span>
          {expandedTrail ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {expandedTrail && (
          <div className="mt-2 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 text-xs flex flex-col gap-2.5">
            {loadingAudit ? (
              <span className="text-slate-400 italic">Loading stage audit trail...</span>
            ) : auditData ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between text-[11px] text-slate-400 border-b border-slate-800 pb-1.5">
                  <span>Audit Mode: <strong className="text-slate-200">{auditData.mode}</strong></span>
                  <span>Decision: <strong className={`font-bold ${auditData.final_decision === 'PASS' ? 'text-emerald-400' : 'text-rose-400'}`}>{auditData.final_decision}</strong></span>
                  <span>Hash: <code className="text-[10px] text-slate-400">{auditData.config_hash?.slice(0, 8)}</code></span>
                </div>
                <div className="flex flex-col gap-2">
                  {auditData.stages.map((stage, idx) => (
                    <div key={idx} className="p-2 rounded bg-slate-900 border border-slate-800">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-slate-200">{stage.stage_name}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${stage.status === 'PASS' ? 'bg-emerald-950 text-emerald-400' : stage.status === 'WAIT' ? 'bg-amber-950 text-amber-400' : 'bg-rose-950 text-rose-400'}`}>
                          {stage.status}
                        </span>
                      </div>
                      <div className="flex flex-col gap-1 text-[11px] pl-1">
                        {stage.checks.map((chk, cIdx) => (
                          <div key={cIdx} className="flex items-center justify-between text-slate-400">
                            <span>• {chk.name}</span>
                            <span className={chk.passed ? 'text-slate-300 font-mono' : 'text-rose-400 font-mono'}>
                              {String(chk.value)} {chk.threshold ? `(Target: ${chk.threshold})` : ''}
                            </span>
                          </div>
                        ))}
                      </div>
                      {stage.rejection_reasons && stage.rejection_reasons.length > 0 && (
                        <div className="mt-1 text-[11px] text-rose-400 pl-1 border-t border-rose-900/30 pt-1">
                          Rejections: {stage.rejection_reasons.join('; ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5 text-slate-400">
                <span className="text-[11px] text-emerald-400 font-semibold">Stage Checklist Verification:</span>
                <span>1. Scanner: Regime Bullish, Universe liquid &gt; ADV ₹10Cr</span>
                <span>2. Setup Validator: VCP Base depth &le; 20%, 2+ contractions, tight volume</span>
                <span>3. News Analyst: Results &gt; 7 days out, zero critical RED disclosures</span>
                <span>4. Entry Planner: Buy-stop at trigger, max entry zone 1.5%</span>
                <span>5. Exit Planner: Stop at base low (&le;8%), 2R Target defined</span>
                <span>6. Position Sizer: Whole shares scaled by 95th gap risk</span>
                <span>7. Risk Validator: Cost &le; 0.25R, Heat &le; 6%, Circuit breakers open</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800 flex-wrap gap-2 text-xs">
        <button
          onClick={copyOrderSummary}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied Order' : 'Copy Order Summary'}
        </button>
        <div className="flex items-center gap-2">
          {onOpenChart && (
            <button
              onClick={() => onOpenChart(signal.symbol)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" /> Chart
            </button>
          )}
          {onTakeTrade && isActionable ? (
            <button
              onClick={() => onTakeTrade(signal)}
              className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-semibold text-white shadow-md transition-colors"
            >
              I Took This Trade
            </button>
          ) : (
            <span className="px-3 py-1.5 rounded-lg bg-slate-800/80 text-slate-500 border border-slate-700/40 text-[11px] font-medium">
              Not Actionable
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
