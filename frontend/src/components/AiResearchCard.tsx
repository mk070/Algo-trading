/**
 * AiResearchCard — displays AI research assessment for a stock symbol or news event.
 *
 * Variants:
 * - "summary": Compact card for Dashboard shortlisted opportunities & Watchlist expanded rows.
 * - "full":    Full 6-agent breakdown for Stock Detail / Opportunity Dossier modal.
 * - "news":    Single news event AI analysis for NewsPage announcements.
 *
 * Uses apiClient from ../api/client (session bearer token + API_BASE).
 * Deduplicates /api/ai/status calls across cards via a short-lived shared promise.
 *
 * Disclaimer: "AI Informational Research Only — Not a Trading Directive"
 * is always displayed.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { apiClient } from '../api/client';

type ResearchStatus = 'WATCH' | 'MONITOR' | 'REJECT' | 'INSUFFICIENT_DATA';

interface EvidenceRecord {
  source_type: string;
  source_title: string;
  source_url?: string;
  pub_timestamp?: string;
  extracted_passage?: string;
  verification_status: string;
}

interface Assessment {
  final_status: ResearchStatus;
  summary: string;
  evidence: EvidenceRecord[];
  what_would_change: string[];
  requires_human_review: boolean;
  generated_at: string;
}

export interface AiStatusPayload {
  ai_agents_enabled: boolean;
  gemini_enabled: boolean;
  agent_flags?: Record<string, boolean>;
  quota?: {
    daily_limit: number;
    used_today: number;
    quota_exhausted: boolean;
  };
}

type LoadState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'disabled'; reason: string }
  | { kind: 'quota_exhausted'; used_today: number; daily_limit: number }
  | { kind: 'not_analyzed' }
  | { kind: 'error'; message: string }
  | {
      kind: 'ok';
      data: Assessment;
      fullAgents?: Record<string, any>;
      newsAnalysis?: Record<string, any>;
    };

const STATUS_COLORS: Record<ResearchStatus, string> = {
  WATCH: 'bg-emerald-950/80 text-emerald-300 border border-emerald-700/70',
  MONITOR: 'bg-amber-950/80 text-amber-300 border border-amber-700/70',
  REJECT: 'bg-rose-950/80 text-rose-300 border border-rose-700/70',
  INSUFFICIENT_DATA: 'bg-slate-800 text-slate-300 border border-slate-700',
};

const STATUS_LABELS: Record<ResearchStatus, string> = {
  WATCH: 'Watch',
  MONITOR: 'Monitor',
  REJECT: 'Reject',
  INSUFFICIENT_DATA: 'Insufficient Data',
};

// Shared short-lived status cache to prevent N cards from firing N /api/ai/status calls
let _statusCache: { data: AiStatusPayload; ts: number } | null = null;
let _statusInflight: Promise<AiStatusPayload> | null = null;

async function getSharedAiStatus(): Promise<AiStatusPayload> {
  const now = Date.now();
  if (_statusCache && now - _statusCache.ts < 15000) {
    return _statusCache.data;
  }
  if (!_statusInflight) {
    _statusInflight = apiClient
      .getAiStatus()
      .then((data: AiStatusPayload) => {
        _statusCache = { data, ts: Date.now() };
        return data;
      })
      .finally(() => {
        _statusInflight = null;
      });
  }
  return _statusInflight;
}

export function resetAiStatusCache() {
  _statusCache = null;
  _statusInflight = null;
}

interface AiResearchCardProps {
  symbol: string;
  market?: string;
  variant?: 'summary' | 'full' | 'news';
  newsEventId?: number;
  aiStatus?: AiStatusPayload | null;
  className?: string;
}

export function AiResearchCard({
  symbol,
  market = 'IN',
  variant = 'summary',
  newsEventId,
  aiStatus,
  className = '',
}: AiResearchCardProps) {
  const [state, setState] = useState<LoadState>({ kind: 'idle' });
  const [analyzing, setAnalyzing] = useState(false);

  const load = useCallback(async () => {
    setState({ kind: 'loading' });
    try {
      const statusData = aiStatus ?? (await getSharedAiStatus());

      if (!statusData.ai_agents_enabled || !statusData.gemini_enabled) {
        setState({
          kind: 'disabled',
          reason:
            'AI research is currently disabled. Enable AI_AGENTS_ENABLED, AI_GEMINI_ENABLED, and individual agent flags in platform settings.',
        });
        return;
      }

      if (statusData.quota?.quota_exhausted) {
        setState({
          kind: 'quota_exhausted',
          used_today: statusData.quota.used_today,
          daily_limit: statusData.quota.daily_limit,
        });
        return;
      }

      if (variant === 'news' && newsEventId) {
        const newsResp = await apiClient.getAiNewsAnalysis(newsEventId);
        if (newsResp.status === 'NOT_ANALYZED') {
          setState({ kind: 'not_analyzed' });
          return;
        }
        const a = newsResp.analysis || {};
        setState({
          kind: 'ok',
          data: {
            final_status:
              a.materiality === 'HIGH' ? 'WATCH' : a.materiality === 'MEDIUM' ? 'MONITOR' : 'INSUFFICIENT_DATA',
            summary: a.summary || '',
            evidence: a.evidence || [],
            what_would_change: a.key_facts || [],
            requires_human_review: Boolean(a.requires_follow_up || a.is_rumor),
            generated_at: newsResp.generated_at || '',
          },
          newsAnalysis: a,
        });
        return;
      }

      const [data, fullResp] = await Promise.all([
        apiClient.getAiResearch(symbol),
        variant === 'full' ? apiClient.getAiResearchFull(symbol).catch(() => null) : Promise.resolve(null),
      ]);

      if (data.status === 'NOT_ANALYZED' && (!fullResp || fullResp.status === 'NOT_ANALYZED')) {
        setState({ kind: 'not_analyzed' });
        return;
      }

      setState({
        kind: 'ok',
        data: {
          final_status: (data.final_status || 'INSUFFICIENT_DATA') as ResearchStatus,
          summary: data.summary ?? '',
          evidence: data.evidence ?? [],
          what_would_change: data.what_would_change ?? [],
          requires_human_review: data.requires_human_review ?? false,
          generated_at: data.generated_at ?? '',
        },
        fullAgents: fullResp?.agents || undefined,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setState({ kind: 'error', message: msg });
    }
  }, [symbol, variant, newsEventId, aiStatus]);

  useEffect(() => {
    if (symbol) void load();
  }, [symbol, load]);

  const triggerAnalysis = async () => {
    setAnalyzing(true);
    try {
      const data =
        variant === 'news' && newsEventId
          ? await apiClient.analyzeAiNews(newsEventId)
          : await apiClient.analyzeAiResearch(symbol, market, newsEventId);

      if (data.status === 'DISABLED') {
        setState({ kind: 'disabled', reason: data.reason ?? 'AI research is disabled.' });
      } else if (data.status === 'QUOTA_EXHAUSTED') {
        setState({
          kind: 'quota_exhausted',
          used_today: data.used_today ?? 0,
          daily_limit: data.daily_limit ?? 0,
        });
      } else {
        resetAiStatusCache();
        await load();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setState({ kind: 'error', message: msg });
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className={`rounded-xl border border-slate-800 bg-slate-900/90 text-slate-100 shadow-sm ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-2 border-b border-slate-800/60">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-violet-950/80 border border-violet-700/60 px-2 py-0.5 text-[11px] font-semibold text-violet-300">
            AI Research
          </span>
          <span className="text-[11px] text-slate-400 font-mono">{symbol}</span>
        </div>
        <span className="text-[10px] text-slate-500">Not a Trading Directive</span>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {state.kind === 'idle' || state.kind === 'loading' ? (
          <div className="flex items-center gap-2 py-2 text-xs text-slate-400">
            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
            Loading AI research…
          </div>
        ) : state.kind === 'disabled' ? (
          <div className="rounded-lg bg-slate-950/70 border border-slate-800 px-3 py-2.5 text-xs text-slate-400">
            <p className="font-semibold text-slate-300">AI Research Disabled</p>
            <p className="mt-0.5 text-[11px] text-slate-500">{state.reason}</p>
          </div>
        ) : state.kind === 'quota_exhausted' ? (
          <div className="rounded-lg bg-amber-950/40 border border-amber-800/70 px-3 py-2.5 text-xs text-amber-300">
            <p className="font-semibold">Daily Quota Exhausted</p>
            <p className="mt-0.5 text-[11px] text-amber-400/90">
              {state.used_today} / {state.daily_limit} requests used today. Resets at midnight UTC. No paid fallback.
            </p>
          </div>
        ) : state.kind === 'error' ? (
          <div className="rounded-lg bg-rose-950/40 border border-rose-800/70 px-3 py-2.5 text-xs text-rose-300">
            <p className="font-semibold">Error loading AI research</p>
            <p className="mt-0.5 text-[11px]">{state.message}</p>
            <button onClick={load} className="mt-1.5 text-[11px] underline hover:text-rose-100">
              Retry
            </button>
          </div>
        ) : state.kind === 'not_analyzed' ? (
          <div className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2.5 text-xs text-slate-400 flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="font-medium text-slate-300">Not yet analyzed</p>
              <p className="text-[11px] text-slate-500">No cached AI research for {symbol}.</p>
            </div>
            <button
              onClick={triggerAnalysis}
              disabled={analyzing}
              className="rounded-lg bg-violet-600 hover:bg-violet-500 px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-50"
            >
              {analyzing ? 'Analyzing…' : 'Run AI Research'}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Status badge */}
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  STATUS_COLORS[state.data.final_status]
                }`}
              >
                {variant === 'news' && state.newsAnalysis
                  ? `${state.newsAnalysis.materiality || 'INFO'} · ${state.newsAnalysis.sentiment || 'NEUTRAL'}`
                  : STATUS_LABELS[state.data.final_status]}
              </span>
              {state.data.requires_human_review && (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-950/80 px-2 py-0.5 text-[11px] font-medium text-amber-300 border border-amber-700/70">
                  Requires Human Review
                </span>
              )}
            </div>

            {/* Summary */}
            {state.data.summary && (
              <p className="text-xs text-slate-300 leading-relaxed">{state.data.summary}</p>
            )}

            {/* Full 6-agent breakdown for Stock Detail view */}
            {variant === 'full' && state.fullAgents && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                {state.fullAgents.news_intelligence?.output && (
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[11px]">
                    <div className="font-semibold text-indigo-300 mb-1">1. News Intelligence</div>
                    <p className="text-slate-300">{state.fullAgents.news_intelligence.output.summary}</p>
                  </div>
                )}
                {state.fullAgents.company_research?.output && (
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[11px]">
                    <div className="font-semibold text-emerald-300 mb-1">
                      2. Company Research ({state.fullAgents.company_research.output.data_completeness})
                    </div>
                    <p className="text-slate-400">
                      Bull: {(state.fullAgents.company_research.output.bull_points || [])[0] || 'None'}
                    </p>
                    <p className="text-slate-400 mt-0.5">
                      Bear: {(state.fullAgents.company_research.output.bear_points || [])[0] || 'None'}
                    </p>
                  </div>
                )}
                {state.fullAgents.market_context?.output && (
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[11px]">
                    <div className="font-semibold text-cyan-300 mb-1">3. Market Context</div>
                    <p className="text-slate-300">
                      Regime: {state.fullAgents.market_context.output.index_regime || 'UNKNOWN'} · Sector:{' '}
                      {state.fullAgents.market_context.output.sector_trend || 'UNKNOWN'}
                    </p>
                  </div>
                )}
                {state.fullAgents.technical_research?.output && (
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[11px]">
                    <div className="font-semibold text-sky-300 mb-1">4. Technical Explanation</div>
                    <p className="text-slate-300">
                      {state.fullAgents.technical_research.output.plain_english_explanation}
                    </p>
                  </div>
                )}
                {state.fullAgents.risk_review?.output && (
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[11px] md:col-span-2">
                    <div className="font-semibold text-amber-300 mb-1">
                      5. Risk Review (Overall: {state.fullAgents.risk_review.output.overall_risk_level})
                    </div>
                    {(state.fullAgents.risk_review.output.risk_flags || []).length > 0 ? (
                      <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                        {state.fullAgents.risk_review.output.risk_flags.slice(0, 3).map((rf: any, idx: number) => (
                          <li key={idx}>
                            [{rf.severity}] {rf.risk_type}: {rf.description}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-slate-400">No elevated risk flags recorded.</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Evidence links */}
            {state.data.evidence.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-slate-400 mb-1 uppercase tracking-wide">Sources</p>
                <ul className="space-y-1">
                  {state.data.evidence.slice(0, 4).map((ev, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-300">
                      <span className="mt-1.5 inline-block h-1.5 w-1.5 rounded-full bg-violet-400 flex-shrink-0" />
                      {ev.source_url ? (
                        <a
                          href={ev.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline text-indigo-300 hover:text-indigo-200 break-all"
                        >
                          {ev.source_title}
                        </a>
                      ) : (
                        <span>{ev.source_title}</span>
                      )}
                      <span className="ml-1 rounded bg-slate-800 px-1 text-[10px] text-slate-400">
                        {ev.verification_status}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* What would change */}
            {state.data.what_would_change.length > 0 && (
              <details className="text-[11px]">
                <summary className="cursor-pointer text-slate-400 hover:text-slate-200 font-medium">
                  {variant === 'news' ? 'Key Facts' : 'What would change this assessment'}
                </summary>
                <ul className="mt-1 ml-3 space-y-0.5 text-slate-300 list-disc list-inside">
                  {state.data.what_would_change.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </details>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between pt-1.5 border-t border-slate-800/70">
              <span className="text-[10px] text-slate-500">
                {state.data.generated_at ? `Updated ${new Date(state.data.generated_at).toLocaleString()}` : ''}
              </span>
              <button
                onClick={triggerAnalysis}
                disabled={analyzing}
                className="text-[11px] text-violet-300 hover:text-violet-200 underline disabled:opacity-50"
              >
                {analyzing ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Disclaimer footer */}
      <div className="border-t border-slate-800/70 px-4 py-2">
        <p className="text-[10px] text-slate-500 italic">
          AI Informational Research Only — Not a Trading Directive. Deterministic signals govern all trade recommendations.
        </p>
      </div>
    </div>
  );
}

export default AiResearchCard;
