import React, { useEffect, useState } from 'react';
import { AlertCircle, Bot, CheckCircle2, ChevronRight, FileText, Info, ShieldAlert, Sparkles, TrendingDown, TrendingUp } from 'lucide-react';
import { apiClient } from '../api/client';

interface AiResearchNotesProps {
  selectedSymbol?: string;
}

export const AiResearchNotes: React.FC<AiResearchNotesProps> = ({ selectedSymbol = 'RELIANCE.NS' }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    apiClient
      .getPaperTradingAiNotes(selectedSymbol)
      .then((res) => {
        if (active) setData(res);
      })
      .catch((e) => {
        console.error('Failed to load AI notes:', e);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedSymbol]);

  if (loading) {
    return (
      <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/60 animate-pulse flex items-center justify-center text-xs text-slate-400">
        <Bot className="w-4 h-4 mr-2 text-indigo-400 animate-spin" />
        Synthesizing opposing research theses & risk disclosures...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900 text-xs text-slate-400">
        AI research assistant offline or notes unavailable for {selectedSymbol}. Deterministic trading functions unaffected.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 flex flex-col gap-4">
      {/* Header & Mandatory Firewall Disclaimer */}
      <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-950 border border-indigo-800 text-indigo-400">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              AI Research Desk & Opposing Analysis: {data.symbol}
              <span className="text-[10px] font-normal px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                {data.sector}
              </span>
            </h3>
            <span className="text-[10px] text-slate-500">As of {data.as_of}</span>
          </div>
        </div>

        {/* Permanent Compliance Badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-950/60 border border-amber-800/80 text-[10px] font-semibold text-amber-300">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
          AI Research Only — Zero Order Authority
        </div>
      </div>

      {/* Opposing Theses Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Bull Case */}
        <div className="p-4 rounded-lg bg-emerald-950/20 border border-emerald-900/40 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5" />
              {data.bull_case?.title || 'Bullish Factors'}
            </span>
            <span className="text-[9px] px-2 py-0.5 rounded bg-emerald-900/60 text-emerald-300 font-mono">
              {data.bull_case?.confidence_level}
            </span>
          </div>
          <ul className="space-y-1.5 mt-1 text-xs text-slate-300">
            {data.bull_case?.evidence?.map((item: string, i: number) => (
              <li key={i} className="flex items-start gap-2">
                <ChevronRight className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Bear Case / Headwinds */}
        <div className="p-4 rounded-lg bg-rose-950/20 border border-rose-900/40 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
              <TrendingDown className="w-3.5 h-3.5" />
              {data.bear_case?.title || 'Bearish Headwinds'}
            </span>
            <span className="text-[9px] px-2 py-0.5 rounded bg-rose-900/60 text-rose-300 font-mono">
              {data.bear_case?.confidence_level}
            </span>
          </div>
          <ul className="space-y-1.5 mt-1 text-xs text-slate-300">
            {data.bear_case?.evidence?.map((item: string, i: number) => (
              <li key={i} className="flex items-start gap-2">
                <ChevronRight className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Key Risks & Citations */}
      <div className="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 text-slate-400">
          <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            <strong>Identified Tail Risks:</strong> {data.key_risks?.join(' · ')}
          </span>
        </div>
        <div className="text-[10px] text-slate-500 shrink-0">
          Sources: {data.data_sources?.join(' | ')}
        </div>
      </div>
    </div>
  );
};

