import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileSpreadsheet,
  Filter,
  Info,
  Layers,
  Newspaper,
  Radio,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { EarningsAnalysisResult } from '../types';

export const NewsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'DISCLOSURES' | 'SOURCES' | 'EARNINGS'>('DISCLOSURES');
  const [events, setEvents] = useState<any[]>([]);
  const [sourcesHealth, setSourcesHealth] = useState<any[]>([]);
  const [macroData, setMacroData] = useState<any>(null);
  const [coverageGaps, setCoverageGaps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [searchSymbol, setSearchSymbol] = useState('');

  // Earnings Analyst state
  const [earningsSymbol, setEarningsSymbol] = useState('RELIANCE');
  const [earningsMarket, setEarningsMarket] = useState<'IN' | 'US'>('IN');
  const [earningsData, setEarningsData] = useState<EarningsAnalysisResult | null>(null);
  const [earningsLoading, setEarningsLoading] = useState(false);

  const fetchNews = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getNews(searchSymbol || undefined, 14);
      setEvents(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Error fetching news:', e);
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchSourcesHealth = async () => {
    try {
      const [health, macro, gaps] = await Promise.all([
        apiClient.getNewsSourcesHealth(),
        apiClient.getMacroCalendar(),
        apiClient.getCoverageGaps(),
      ]);
      setSourcesHealth(Array.isArray(health) ? health : []);
      setMacroData(macro && !macro.detail ? macro : null);
      setCoverageGaps(Array.isArray(gaps) ? gaps : []);
    } catch (e) {
      console.error('Error fetching source health:', e);
      setSourcesHealth([]);
      setCoverageGaps([]);
    }
  };

  const fetchEarnings = async () => {
    if (!earningsSymbol) return;
    try {
      setEarningsLoading(true);
      const data = await apiClient.getEarningsAnalysis(earningsSymbol.trim().toUpperCase(), earningsMarket);
      setEarningsData(data);
    } catch (e) {
      console.error('Error fetching earnings analysis:', e);
    } finally {
      setEarningsLoading(false);
    }
  };

  useEffect(() => {
    fetchNews();
  }, [searchSymbol]);

  useEffect(() => {
    if (activeTab === 'SOURCES') {
      fetchSourcesHealth();
    } else if (activeTab === 'EARNINGS') {
      fetchEarnings();
    }
  }, [activeTab, earningsMarket]);

  const filteredEvents = events.filter((e) => {
    if (severityFilter === 'ALL') return true;
    return e.severity === severityFilter;
  });

  const getSeverityBadge = (sev: string) => {
    switch (sev) {
      case 'RED':
        return 'bg-rose-950 text-rose-300 border-rose-800';
      case 'AMBER':
        return 'bg-amber-950 text-amber-300 border-amber-800';
      default:
        return 'bg-emerald-950 text-emerald-400 border-emerald-800';
    }
  };

  const getMaterialityBadge = (mat: string) => {
    switch (mat) {
      case 'HIGH':
        return 'bg-rose-900/60 text-rose-200 border-rose-700';
      case 'MEDIUM':
        return 'bg-amber-900/60 text-amber-200 border-amber-700';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'HEALTHY':
        return 'bg-emerald-950 text-emerald-300 border-emerald-800';
      case 'DEGRADED':
        return 'bg-amber-950 text-amber-300 border-amber-800';
      case 'UNAVAILABLE':
        return 'bg-slate-800 text-slate-400 border-slate-700';
      case 'OPTIONAL_UNSET':
        return 'bg-blue-950 text-blue-300 border-blue-800';
      default:
        return 'bg-rose-950 text-rose-300 border-rose-800';
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Top Segmented Mode Selector */}
      <div className="flex items-center gap-3 border-b border-slate-800 pb-3 flex-wrap">
        <button
          onClick={() => setActiveTab('DISCLOSURES')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'DISCLOSURES' ? 'bg-indigo-600 text-white shadow-md' : 'text-slate-400 hover:text-white bg-slate-900'
          }`}
        >
          <Newspaper className="w-4 h-4" />
          Exchange Disclosures & News
        </button>
        <button
          onClick={() => setActiveTab('SOURCES')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'SOURCES' ? 'bg-indigo-600 text-white shadow-md' : 'text-slate-400 hover:text-white bg-slate-900'
          }`}
        >
          <Activity className="w-4 h-4" />
          Free Source Health & Compliance
        </button>
        <button
          onClick={() => setActiveTab('EARNINGS')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'EARNINGS' ? 'bg-indigo-600 text-white shadow-md' : 'text-slate-400 hover:text-white bg-slate-900'
          }`}
        >
          <FileSpreadsheet className="w-4 h-4" />
          Earnings Analyst (XBRL / 10-Q & YoY/QoQ)
        </button>
      </div>

      {activeTab === 'DISCLOSURES' && (
        <>
          {/* Header */}
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h1 className="text-xl font-bold text-white flex items-center gap-2">
                <Newspaper className="w-5 h-5 text-indigo-400" />
                Corporate Disclosures & Event Intelligence
              </h1>
              <p className="text-xs text-slate-400">
                Safety layer: deterministic keyword risk classification on official exchange announcements.
              </p>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <input
                type="text"
                placeholder="Search symbol (e.g. RELIANCE)..."
                value={searchSymbol}
                onChange={(e) => setSearchSymbol(e.target.value.toUpperCase())}
                className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
              />

              <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs">
                {['ALL', 'RED', 'AMBER', 'GREEN'].map((sev) => (
                  <button
                    key={sev}
                    onClick={() => setSeverityFilter(sev)}
                    className={`px-3 py-1 rounded-md font-semibold transition-all ${
                      severityFilter === sev ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {sev}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Compliance & Safety Notice */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs text-slate-300 flex items-start gap-3">
            <ShieldAlert className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div>
                <strong className="text-white">Rule 11 (Unknown is not clear):</strong> Missing, stale (&gt;60m), or offline coverage marks stocks as <span className="font-mono text-amber-400 font-bold">UNKNOWN</span>, never <span className="font-mono text-emerald-400 font-bold">CLEAR</span>.
              </div>
              <div className="text-slate-400">
                Isolation Invariant: News and sentiment can only BLOCK or flag REVIEW. They never generate BUY signals, modify sizing, or alter stops.
              </div>
            </div>
          </div>

          {/* Events List */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h2 className="text-sm font-bold text-white">
                Classified Disclosures ({filteredEvents.length})
              </h2>
              <span className="text-xs text-slate-500">Last 14 days</span>
            </div>

            {loading ? (
              <div className="p-8 text-center text-xs text-slate-400">Loading disclosures...</div>
            ) : filteredEvents.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">No disclosures found for criteria.</div>
            ) : (
              <div className="divide-y divide-slate-800">
                {filteredEvents.map((e, idx) => (
                  <div key={idx} className="p-4 hover:bg-slate-850 transition-colors flex flex-col gap-2.5">
                    <div className="flex items-center justify-between flex-wrap gap-2 text-xs">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-white text-sm">{e.symbol}</span>
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono text-[11px] border border-slate-700">
                          {e.source}
                        </span>
                        <span className={`px-2 py-0.5 rounded text-[11px] font-bold border ${getSeverityBadge(e.severity)}`}>
                          {e.severity}
                        </span>
                        {e.materiality && (
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getMaterialityBadge(e.materiality)}`}>
                            {e.materiality} Materiality
                          </span>
                        )}
                        {e.is_unverified ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-300 border border-amber-800 flex items-center gap-1">
                            <Radio className="w-2.5 h-2.5" /> UNVERIFIED RUMOUR
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/60 text-emerald-400 border border-emerald-800 flex items-center gap-1">
                            <CheckCircle2 className="w-2.5 h-2.5" /> OFFICIAL FILING
                          </span>
                        )}
                        {e.syndication_cluster_id && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 font-mono">
                            Wire Cluster: {e.syndication_cluster_id.slice(-8)}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 text-slate-400 font-mono text-[11px]">
                        {e.price_change_day_pct !== null && e.price_change_day_pct !== undefined && (
                          <span className={`px-2 py-0.5 rounded font-bold border ${
                            e.price_change_day_pct >= 0
                              ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                              : 'text-rose-400 bg-rose-950 border-rose-800'
                          }`}>
                            Day: {e.price_change_day_pct >= 0 ? '+' : ''}{e.price_change_day_pct}%
                            {e.price_atr_multiple ? ` (${e.price_atr_multiple}x ATR)` : ''}
                          </span>
                        )}
                        <div className="flex items-center gap-1 text-slate-500">
                          <Clock className="w-3.5 h-3.5" />
                          <span>{new Date(e.published_at).toLocaleString('en-IN')}</span>
                        </div>
                      </div>
                    </div>

                    <p className="text-xs text-slate-200 font-semibold">{e.title}</p>

                    {e.summary && e.summary !== e.title && (
                      <p className="text-xs text-slate-400 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        {e.summary}
                      </p>
                    )}

                    {/* Brokerage Analyst Action card if present */}
                    {e.analyst_action && e.analyst_action.brokerage && (
                      <div className="p-2.5 bg-indigo-950/40 border border-indigo-900/60 rounded-lg text-xs flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-indigo-300 font-bold">{e.analyst_action.brokerage}</span>
                          <span className="text-slate-400">Action:</span>
                          <span className="font-mono text-white font-bold">{e.analyst_action.action || 'RATING'}</span>
                        </div>
                        <div className="flex items-center gap-3 font-mono text-[11px]">
                          {e.analyst_action.new_rating && (
                            <span className="text-emerald-400">Rating: {e.analyst_action.new_rating}</span>
                          )}
                          {e.analyst_action.new_target && (
                            <span className="text-cyan-300">Target: {e.analyst_action.new_target}</span>
                          )}
                        </div>
                      </div>
                    )}

                    {e.url && (
                      <div>
                        <a
                          href={e.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300"
                        >
                          View Official Disclosure Source <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {activeTab === 'SOURCES' && (
        <div className="flex flex-col gap-6">
          {/* Header */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
            <h1 className="text-xl font-bold text-white flex items-center gap-2">
              <Activity className="w-5 h-5 text-indigo-400" />
              Sanctioned Free News Sources & Compliance Health
            </h1>
            <p className="text-xs text-slate-400 mt-1">
              Strict compliance: Zero web scraping of prohibited endpoints. RSS syndication and official public APIs only.
            </p>
          </div>

          {/* BSE Policy Banner */}
          <div className="p-4 bg-slate-900 border border-amber-900/60 rounded-xl text-xs text-amber-200 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <strong className="text-white block mb-0.5">BSE India Policy Notice:</strong>
              BSE does not provide a sanctioned machine-readable RSS syndication feed without browser scraping. Automated scraping of exchange website portals violates terms of use. BSE coverage is explicitly marked <span className="font-mono text-amber-400 font-bold">UNAVAILABLE</span> (never scraped). Indian regulatory disclosures are served via official NSE RSS feeds (<span className="font-mono text-xs">nsearchives.nseindia.com</span>).
            </div>
          </div>

          {/* Offline Coverage Gaps Banner if any */}
          {coverageGaps.length > 0 && (
            <div className="p-4 bg-rose-950/50 border border-rose-800 rounded-xl text-xs text-rose-300 flex items-start gap-3">
              <WifiOff className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <strong className="text-white block mb-0.5">Offline Coverage Gaps Recorded:</strong>
                <ul className="list-disc pl-4 space-y-0.5 mt-1">
                  {coverageGaps.map((g, idx) => (
                    <li key={idx}>
                      {g.source}: Started at {g.gap_start} ({Math.round(g.duration_sec)}s downtime). Status: {g.status}.
                    </li>
                  ))}
                </ul>
                <p className="text-slate-400 mt-1 text-[11px]">
                  During coverage gaps, symbols default to UNKNOWN to guarantee zero trades on blind data.
                </p>
              </div>
            </div>
          )}

          {/* Sources Health Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h2 className="text-sm font-bold text-white">Configured Free Sources</h2>
              <span className="text-xs text-slate-500">Live Health Monitoring</span>
            </div>

            <div className="divide-y divide-slate-800 text-xs">
              {Array.isArray(sourcesHealth) && sourcesHealth.length > 0 ? (
                sourcesHealth.map((src, idx) => (
                  <div key={idx} className="p-4 flex items-center justify-between flex-wrap gap-3">
                    <div className="flex flex-col gap-1 max-w-md">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-sm">{src.name}</span>
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono text-[10px]">
                          {src.market}
                        </span>
                      </div>
                      <span className="font-mono text-slate-500 text-[11px]">{src.source}</span>
                      {src.note && <span className="text-slate-400 italic text-[11px]">{src.note}</span>}
                    </div>

                    <div className="flex items-center gap-4 flex-wrap">
                      <div className="text-right">
                        <span className="text-slate-500 block text-[10px]">Latency Class:</span>
                        <span className="font-mono text-slate-300 font-semibold">{src.latency_class}</span>
                      </div>

                      <div className="text-right">
                        <span className="text-slate-500 block text-[10px]">Median Latency:</span>
                        <span className="font-mono text-slate-300 font-semibold">
                          {src.median_latency_sec ? `${src.median_latency_sec}s` : 'N/A'}
                        </span>
                      </div>

                      <div>
                        <span className={`px-2.5 py-1 rounded text-xs font-bold border ${getStatusBadge(src.status)}`}>
                          {src.status}
                        </span>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-8 text-center text-xs text-slate-400">
                  No source health records available or backend server is starting up.
                </div>
              )}
            </div>
          </div>

          {/* Macro Calendar Caution Window */}
          {macroData && macroData.calendar && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
              <h2 className="text-sm font-bold text-white flex items-center gap-2 mb-3">
                <Calendar className="w-4 h-4 text-indigo-400" />
                2026 Central Bank Monetary Policy Calendar (RBI MPC & US FOMC)
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                {macroData.calendar.events?.slice(0, 8).map((ev: any, idx: number) => (
                  <div key={idx} className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white">{ev.authority}</span>
                        <span className="text-slate-400">{ev.region}</span>
                      </div>
                      <span className="text-slate-300 block text-[11px] mt-0.5">{ev.title}</span>
                    </div>
                    <div className="text-right font-mono text-[11px] text-cyan-400">
                      {ev.decision_date}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'EARNINGS' && (
        <div className="flex flex-col gap-6">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-white flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-indigo-400" />
                Earnings Analyst (Exchange Filings XBRL & SEC EDGAR)
              </h1>
              <p className="text-xs text-slate-400">
                YoY/QoQ comparison, deterministic weak-results detection, and verified consensus surprise checks.
              </p>
            </div>

            <div className="flex items-center gap-3 flex-wrap text-xs">
              <div>
                <label className="text-slate-400 block mb-1">Market:</label>
                <select
                  value={earningsMarket}
                  onChange={(e) => setEarningsMarket(e.target.value as any)}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
                >
                  <option value="IN">India (NSE / BSE XBRL)</option>
                  <option value="US">US (SEC EDGAR 10-Q)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Symbol:</label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={earningsSymbol}
                    onChange={(e) => setEarningsSymbol(e.target.value.toUpperCase())}
                    className="w-28 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-bold"
                  />
                  <button
                    onClick={fetchEarnings}
                    disabled={earningsLoading}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow-md"
                  >
                    <Search className={`w-3.5 h-3.5 ${earningsLoading ? 'animate-spin' : ''}`} />
                    Lookup
                  </button>
                </div>
              </div>
            </div>
          </div>

          {earningsData && earningsData.latest_period && (
            <div className="flex flex-col gap-6">
              {earningsData.severity === 'AMBER' && (
                <div className="p-4 bg-amber-950/60 border border-amber-800 rounded-xl text-xs text-amber-300 flex items-start gap-3 shadow-lg">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="text-white block mb-1">Weak-Results Flagged (Deterministic Check):</strong>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {earningsData.amber_flags.map((flag, idx) => (
                        <li key={idx}>{flag}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Reporting Period</span>
                  <span className="text-xl font-bold font-mono text-white">{earningsData.latest_period.period_type}</span>
                  <span className="text-[11px] text-slate-500 block mt-1">Ended {earningsData.latest_period.period_ended}</span>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Quarterly Revenue</span>
                  <span className="text-xl font-bold font-mono text-white">
                    {earningsData.latest_period.currency} {earningsData.latest_period.revenue?.toLocaleString()}
                  </span>
                  <span className={`text-[11px] font-bold block mt-1 ${earningsData.revenue_yoy_pct && earningsData.revenue_yoy_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {earningsData.revenue_yoy_pct !== null && earningsData.revenue_yoy_pct !== undefined ? `${earningsData.revenue_yoy_pct >= 0 ? '+' : ''}${earningsData.revenue_yoy_pct}% YoY` : 'YoY N/A'}
                  </span>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Net Profit</span>
                  <span className="text-xl font-bold font-mono text-white">
                    {earningsData.latest_period.currency} {earningsData.latest_period.net_profit?.toLocaleString()}
                  </span>
                  <span className={`text-[11px] font-bold block mt-1 ${earningsData.profit_yoy_pct && earningsData.profit_yoy_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {earningsData.profit_yoy_pct !== null && earningsData.profit_yoy_pct !== undefined ? `${earningsData.profit_yoy_pct >= 0 ? '+' : ''}${earningsData.profit_yoy_pct}% YoY` : 'YoY N/A'}
                  </span>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl">
                  <span className="text-xs text-slate-400 block mb-1">Diluted EPS</span>
                  <span className="text-xl font-bold font-mono text-indigo-300">
                    {earningsData.latest_period.eps?.toFixed(2)}
                  </span>
                  <span className={`text-[11px] font-bold block mt-1 ${earningsData.eps_yoy_pct && earningsData.eps_yoy_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {earningsData.eps_yoy_pct !== null && earningsData.eps_yoy_pct !== undefined ? `${earningsData.eps_yoy_pct >= 0 ? '+' : ''}${earningsData.eps_yoy_pct}% YoY` : 'YoY N/A'}
                  </span>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
                <h2 className="text-sm font-bold text-white mb-2">Consensus & Earnings Surprise Analysis</h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 block">Consensus Status:</span>
                    <span className={`font-bold font-mono ${earningsData.consensus_status === 'VERIFIED' ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {earningsData.consensus_status}
                    </span>
                    <span className="text-[10px] text-slate-500 block mt-1">
                      {earningsData.latest_period.consensus_source || 'No verified institutional consensus source'}
                    </span>
                  </div>

                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 block">Reported vs Consensus Surprise:</span>
                    <span className="font-bold font-mono text-white">
                      {earningsData.eps_surprise_pct !== null && earningsData.eps_surprise_pct !== undefined
                        ? `${earningsData.eps_surprise_pct >= 0 ? '+' : ''}${earningsData.eps_surprise_pct}%`
                        : 'UNKNOWN (Unverified)'}
                    </span>
                    <span className="text-[10px] text-slate-500 block mt-1">
                      Strict rule: Missing consensus never produces synthetic surprise
                    </span>
                  </div>

                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-500 block">Operating Margin:</span>
                    <span className="font-bold font-mono text-cyan-400">
                      {earningsData.operating_margin_pct ? `${earningsData.operating_margin_pct}%` : 'N/A'}
                    </span>
                    <span className="text-[10px] text-slate-500 block mt-1">
                      {earningsData.prior_operating_margin_pct ? `Prior: ${earningsData.prior_operating_margin_pct}%` : ''}
                    </span>
                  </div>
                </div>
              </div>

              <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-xs flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-2 text-slate-300">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Official Filing Source: <strong>{earningsData.latest_period.source_name}</strong></span>
                </div>
                {earningsData.latest_period.source_url && (
                  <a
                    href={earningsData.latest_period.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold"
                  >
                    View Official Filing <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
