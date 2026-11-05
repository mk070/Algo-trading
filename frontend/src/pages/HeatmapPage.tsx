import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  LayoutGrid,
  TrendingUp,
  TrendingDown,
  Search,
  RefreshCw,
  BarChart2,
  BookOpen,
  Filter,
  Layers,
  Globe,
  SlidersHorizontal,
  X,
  Zap,
  CheckCircle2,
  AlertCircle,
  Eye,
  Maximize2,
  Columns,
} from 'lucide-react';
import { API_BASE } from '../api/client';
import { ChartModal } from '../components/ChartModal';
import { FundamentalReport } from '../components/FundamentalReport';
import { TradingViewStockHeatmap } from '../components/TradingViewStockHeatmap';

interface StockHeatmapItem {
  symbol: string;
  name: string;
  sector: string;
  industry?: string;
  price: number | null;
  change: number;
  change_pct: number;
  volume: number;
  is_positive: boolean;
}

interface SectorGroup {
  name: string;
  count: number;
  average_change_pct: number;
  is_positive: boolean;
  stocks: StockHeatmapItem[];
}

interface HeatmapResponse {
  market: 'IN' | 'US';
  timestamp: string;
  total_stocks: number;
  advancing: number;
  declining: number;
  unchanged: number;
  sectors: SectorGroup[];
}

interface HeatmapPageProps {
  currentMarket: 'IN' | 'US';
  onMarketChange?: (market: 'IN' | 'US') => void;
}

function getTileStyles(pct: number) {
  if (pct >= 3.0) {
    return {
      bg: 'bg-emerald-600/90 hover:bg-emerald-500',
      text: 'text-white',
      badge: 'bg-emerald-900/90 text-white',
      border: 'border-emerald-400/80',
    };
  }
  if (pct >= 1.5) {
    return {
      bg: 'bg-emerald-700/80 hover:bg-emerald-600',
      text: 'text-emerald-50',
      badge: 'bg-emerald-950/80 text-emerald-200',
      border: 'border-emerald-500/60',
    };
  }
  if (pct >= 0.5) {
    return {
      bg: 'bg-emerald-800/60 hover:bg-emerald-700/70',
      text: 'text-emerald-100',
      badge: 'bg-emerald-950 text-emerald-300',
      border: 'border-emerald-600/40',
    };
  }
  if (pct > 0.05) {
    return {
      bg: 'bg-emerald-950/60 hover:bg-emerald-900/60',
      text: 'text-emerald-200',
      badge: 'bg-emerald-950/90 text-emerald-300',
      border: 'border-emerald-700/40',
    };
  }
  if (pct >= -0.05) {
    return {
      bg: 'bg-slate-800/80 hover:bg-slate-700/80',
      text: 'text-slate-200',
      badge: 'bg-slate-900 text-slate-300',
      border: 'border-slate-700/60',
    };
  }
  if (pct > -0.5) {
    return {
      bg: 'bg-rose-950/60 hover:bg-rose-900/60',
      text: 'text-rose-200',
      badge: 'bg-rose-950/90 text-rose-300',
      border: 'border-rose-700/40',
    };
  }
  if (pct > -1.5) {
    return {
      bg: 'bg-rose-900/60 hover:bg-rose-800/70',
      text: 'text-rose-100',
      badge: 'bg-rose-950 text-rose-300',
      border: 'border-rose-600/40',
    };
  }
  if (pct > -3.0) {
    return {
      bg: 'bg-rose-700/80 hover:bg-rose-600',
      text: 'text-rose-50',
      badge: 'bg-rose-950/80 text-rose-200',
      border: 'border-rose-500/60',
    };
  }
  return {
    bg: 'bg-rose-600/90 hover:bg-rose-500',
    text: 'text-white',
    badge: 'bg-rose-900/90 text-white',
    border: 'border-rose-400/80',
  };
}

export const HeatmapPage: React.FC<HeatmapPageProps> = ({ currentMarket, onMarketChange }) => {
  const [marketMode, setMarketMode] = useState<'IN' | 'US' | 'BOTH'>(currentMarket);
  const [viewType, setViewType] = useState<'visual' | 'constituents'>('visual');
  const [data, setData] = useState<HeatmapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSector, setSelectedSector] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<'WEIGHT' | 'CHANGE_DESC' | 'CHANGE_ASC'>('WEIGHT');
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Modals
  const [chartSymbol, setChartSymbol] = useState<string | null>(null);
  const [fundamentalSymbol, setFundamentalSymbol] = useState<string | null>(null);

  // Active constituent market query target
  const constituentMarket: 'IN' | 'US' = marketMode === 'BOTH' ? (currentMarket || 'US') : marketMode;

  const fetchHeatmap = useCallback(async (isSilent = false) => {
    try {
      if (!isSilent) setLoading(true);
      setError(null);
      const res = await fetch(`${API_BASE}/heatmap?market=${constituentMarket}`);
      if (!res.ok) {
        throw new Error(`Failed to load heatmap data (${res.status})`);
      }
      const json: HeatmapResponse = await res.json();
      setData(json);
    } catch (err: any) {
      if (!isSilent) setError(err.message || 'Error fetching market heatmap');
    } finally {
      if (!isSilent) setLoading(false);
    }
  }, [constituentMarket]);

  useEffect(() => {
    fetchHeatmap();
  }, [fetchHeatmap]);

  // Real-time polling every 4 seconds when autoRefresh is active
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchHeatmap(true);
    }, 4000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchHeatmap]);

  const currency = constituentMarket === 'IN' ? '₹' : '$';

  // Filtered and sorted sectors
  const filteredSectors = useMemo(() => {
    if (!data) return [];
    const query = searchQuery.trim().toLowerCase();

    return data.sectors
      .filter((sec) => {
        if (selectedSector !== 'ALL' && sec.name !== selectedSector) return false;
        return true;
      })
      .map((sec) => {
        let stocks = sec.stocks.filter((st) => {
          if (!query) return true;
          return (
            st.symbol.toLowerCase().includes(query) ||
            st.name.toLowerCase().includes(query)
          );
        });

        if (sortBy === 'CHANGE_DESC') {
          stocks = [...stocks].sort((a, b) => b.change_pct - a.change_pct);
        } else if (sortBy === 'CHANGE_ASC') {
          stocks = [...stocks].sort((a, b) => a.change_pct - b.change_pct);
        } else {
          // Weight/Volume by default
          stocks = [...stocks].sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct));
        }

        return {
          ...sec,
          stocks,
        };
      })
      .filter((sec) => sec.stocks.length > 0);
  }, [data, searchQuery, selectedSector, sortBy]);

  // Overall market stats
  const totalStocks = data?.total_stocks || 0;
  const advancing = data?.advancing || 0;
  const declining = data?.declining || 0;
  const unchanged = data?.unchanged || 0;
  const advPct = totalStocks > 0 ? (advancing / totalStocks) * 100 : 0;
  const decPct = totalStocks > 0 ? (declining / totalStocks) * 100 : 0;

  const handleSelectMarket = (m: 'IN' | 'US' | 'BOTH') => {
    setMarketMode(m);
    if (m !== 'BOTH' && onMarketChange) {
      onMarketChange(m);
    }
  };

  return (
    <div className="flex flex-col gap-4 pb-12">
      {/* ── Page Header & Controls ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-xl">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-950 border border-emerald-800/80 flex items-center justify-center text-emerald-400 shadow-inner">
              <LayoutGrid className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
                Market Sector Heatmap
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800/60 font-semibold flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                  LIVE REALTIME DATA
                </span>
              </h1>
              <p className="text-slate-400 text-xs mt-0.5">
                Real-time institutional treemap sized by market cap, coloured by day move for US & Indian markets.
              </p>
            </div>
          </div>
        </div>

        {/* Market Switcher & Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Dual / Single Market Selector */}
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl p-1">
            <button
              onClick={() => handleSelectMarket('US')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                marketMode === 'US'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>🇺🇸</span>
              <span>US S&P 500</span>
            </button>
            <button
              onClick={() => handleSelectMarket('IN')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                marketMode === 'IN'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>🇮🇳</span>
              <span>India Nifty 50</span>
            </button>
            <button
              onClick={() => handleSelectMarket('BOTH')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                marketMode === 'BOTH'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
              title="View both United States & India heatmaps side by side"
            >
              <Columns className="w-3.5 h-3.5" />
              <span>Both Markets</span>
            </button>
          </div>

          {/* Mode Switcher */}
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl p-1">
            <button
              onClick={() => setViewType('visual')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                viewType === 'visual'
                  ? 'bg-slate-800 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>Treemap</span>
            </button>
            <button
              onClick={() => setViewType('constituents')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                viewType === 'constituents'
                  ? 'bg-slate-800 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Constituents & Audit</span>
            </button>
          </div>

          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-3 py-2 rounded-xl text-xs font-mono font-medium border transition-colors flex items-center gap-1.5 ${
              autoRefresh
                ? 'bg-emerald-950/60 border-emerald-800/80 text-emerald-300'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
            }`}
            title="Toggle 4-Second Auto Refresh"
          >
            <Zap className={`w-3.5 h-3.5 ${autoRefresh ? 'text-emerald-400' : 'text-slate-500'}`} />
            <span className="hidden sm:inline">{autoRefresh ? 'Live (4s)' : 'Paused'}</span>
          </button>

          <button
            onClick={() => fetchHeatmap()}
            disabled={loading}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white transition-colors"
            title="Manual Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-emerald-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* ── Visual Treemap View (Hero Feature) ── */}
      {viewType === 'visual' && (
        <>
          {marketMode === 'BOTH' ? (
            /* Dual Split View: Both Markets Side-by-Side */
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
              {/* US Heatmap */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-3">
                <div className="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2.5">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white text-sm">🇺🇸 United States — S&P 500</span>
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/70 border border-emerald-800/60 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      Alpaca IEX Realtime
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono hidden sm:inline">
                    Sized by Market Cap · Coloured by % Move
                  </span>
                </div>
                <TradingViewStockHeatmap market="US" height={640} hasTopBar={true} />
              </div>

              {/* India Heatmap */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col gap-3">
                <div className="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2.5">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white text-sm">🇮🇳 India — NIFTY 50</span>
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/70 border border-emerald-800/60 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      Angel One SmartAPI Realtime
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono hidden sm:inline">
                    Sized by Market Cap · Coloured by % Move
                  </span>
                </div>
                <TradingViewStockHeatmap market="IN" height={640} hasTopBar={true} />
              </div>
            </div>
          ) : (
            /* Single Market Full-Width Institutional Treemap */
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-xl flex flex-col gap-3">
              <div className="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2.5 flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-base">
                    {marketMode === 'IN'
                      ? '🇮🇳 India — NIFTY 50 Real-Time Heatmap'
                      : '🇺🇸 United States — S&P 500 Real-Time Heatmap'}
                  </span>
                  <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/70 border border-emerald-800/60 px-2.5 py-0.5 rounded-full flex items-center gap-1.5 font-semibold">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    {marketMode === 'IN'
                      ? 'Angel One SmartAPI Live Feed'
                      : 'Alpaca IEX Live Feed'}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-slate-400 font-mono">
                  <span>Sized by Market Cap</span>
                  <span>•</span>
                  <span>Coloured by % Move</span>
                  <span>•</span>
                  <span className="text-emerald-400">TradingView Interactive</span>
                </div>
              </div>
              <TradingViewStockHeatmap market={marketMode} height={700} hasTopBar={true} />
            </div>
          )}
        </>
      )}

      {/* ── Market Breadth & Sentiment Bar ── */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-lg flex flex-col gap-2.5">
        <div className="flex items-center justify-between text-xs flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <span className="font-bold text-white flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5 text-emerald-400" />
              {constituentMarket === 'IN' ? 'NSE Nifty 100 Real-Time Breadth' : 'S&P 500 Leaders Real-Time Breadth'}
            </span>
            <span className="text-slate-500 font-mono text-[11px]">({totalStocks} monitored constituents)</span>
          </div>

          <div className="flex items-center gap-3 font-mono text-xs font-semibold">
            <span className="text-emerald-400 flex items-center gap-1">
              <TrendingUp className="w-3.5 h-3.5" />
              {advancing} Advancing ({advPct.toFixed(0)}%)
            </span>
            <span className="text-rose-400 flex items-center gap-1">
              <TrendingDown className="w-3.5 h-3.5" />
              {declining} Declining ({decPct.toFixed(0)}%)
            </span>
            {unchanged > 0 && <span className="text-slate-400">{unchanged} Unchanged</span>}
          </div>
        </div>

        {/* Visual Breadth Bar */}
        <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden flex shadow-inner">
          <div
            className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
            style={{ width: `${advPct}%` }}
          />
          <div
            className="h-full bg-slate-700 transition-all duration-500"
            style={{ width: `${totalStocks > 0 ? (unchanged / totalStocks) * 100 : 0}%` }}
          />
          <div
            className="h-full bg-gradient-to-r from-rose-500 to-rose-700 transition-all duration-500"
            style={{ width: `${decPct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
          <span>Advancing: {advPct.toFixed(1)}%</span>
          <span>Declining: {decPct.toFixed(1)}%</span>
        </div>
      </div>

      {/* ── Constituents & Fundamental Audit Table ── */}
      {viewType === 'constituents' && (
        <div className="flex flex-col gap-4">
          {/* Filters & Search Row */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="relative w-full sm:w-72">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search stock symbol or name..."
                className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
              <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl p-1 shrink-0">
                <span className="text-[11px] text-slate-500 px-2 flex items-center gap-1">
                  <Filter className="w-3 h-3" /> Sector:
                </span>
                <select
                  value={selectedSector}
                  onChange={(e) => setSelectedSector(e.target.value)}
                  className="bg-slate-950 text-xs text-slate-200 border border-slate-800 rounded-lg px-2.5 py-1 focus:outline-none focus:border-emerald-500"
                >
                  <option value="ALL">All Sectors ({data?.sectors.length || 0})</option>
                  {data?.sectors.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name} ({s.count})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-xl p-1 shrink-0">
                <span className="text-[11px] text-slate-500 px-2 flex items-center gap-1">
                  <SlidersHorizontal className="w-3 h-3" /> Sort:
                </span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as any)}
                  className="bg-slate-950 text-xs text-slate-200 border border-slate-800 rounded-lg px-2.5 py-1 focus:outline-none focus:border-emerald-500"
                >
                  <option value="WEIGHT">Volatility / Activity</option>
                  <option value="CHANGE_DESC">Top Gainers First</option>
                  <option value="CHANGE_ASC">Top Losers First</option>
                </select>
              </div>
            </div>
          </div>

          {/* Color Legend Scale */}
          <div className="flex items-center justify-between text-[11px] bg-slate-900/60 border border-slate-800/80 rounded-xl px-4 py-2 font-mono flex-wrap gap-2">
            <span className="text-slate-400 font-sans font-medium">Heatmap Scale:</span>
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="px-2 py-0.5 rounded bg-rose-600 text-white font-bold">&le; -3%</span>
              <span className="px-2 py-0.5 rounded bg-rose-700 text-rose-100">-2%</span>
              <span className="px-2 py-0.5 rounded bg-rose-900 text-rose-200">-1%</span>
              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300">0%</span>
              <span className="px-2 py-0.5 rounded bg-emerald-900 text-emerald-200">+1%</span>
              <span className="px-2 py-0.5 rounded bg-emerald-700 text-emerald-100">+2%</span>
              <span className="px-2 py-0.5 rounded bg-emerald-600 text-white font-bold">&ge; +3%</span>
            </div>
          </div>

          {/* Main Sector Heatmap Grid */}
          {loading && !data ? (
            <div className="py-20 flex flex-col items-center justify-center text-slate-400 gap-3">
              <RefreshCw className="w-8 h-8 animate-spin text-emerald-500" />
              <p className="text-xs">Loading live real-time market data across {constituentMarket === 'IN' ? 'NSE' : 'US'} universe...</p>
            </div>
          ) : error ? (
            <div className="py-16 bg-slate-900 border border-slate-800 rounded-2xl flex flex-col items-center gap-3 text-center p-6">
              <AlertCircle className="w-8 h-8 text-rose-400" />
              <p className="text-xs text-slate-300">{error}</p>
              <button
                onClick={() => fetchHeatmap()}
                className="text-xs px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg border border-slate-700"
              >
                Retry
              </button>
            </div>
          ) : filteredSectors.length === 0 ? (
            <div className="py-16 text-center text-slate-500 text-xs bg-slate-900 border border-slate-800 rounded-2xl">
              No stocks matched your search filters.
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {filteredSectors.map((sector) => {
                const isSectorPos = sector.average_change_pct >= 0;
                return (
                  <div
                    key={sector.name}
                    className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 sm:p-5 shadow-xl flex flex-col gap-3"
                  >
                    <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5 flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                        <h3 className="text-sm font-bold text-white tracking-tight">{sector.name}</h3>
                        <span className="text-[11px] text-slate-500 font-mono">({sector.stocks.length} stocks)</span>
                      </div>
                      <div className="flex items-center gap-2 font-mono text-xs">
                        <span className="text-slate-400">Sector Avg:</span>
                        <span
                          className={`font-bold px-2 py-0.5 rounded text-[11px] ${
                            isSectorPos ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' : 'bg-rose-950 text-rose-400 border border-rose-800/60'
                          }`}
                        >
                          {isSectorPos ? '+' : ''}{sector.average_change_pct.toFixed(2)}%
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5">
                      {sector.stocks.map((stock) => {
                        const style = getTileStyles(stock.change_pct);
                        return (
                          <div
                            key={stock.symbol}
                            onClick={() => setChartSymbol(stock.symbol)}
                            className={`${style.bg} border ${style.border} rounded-xl p-3 flex flex-col justify-between cursor-pointer transition-all duration-150 transform hover:-translate-y-0.5 shadow-sm group min-h-[90px]`}
                          >
                            <div className="flex items-start justify-between gap-1">
                              <div>
                                <span className="font-bold text-xs tracking-tight text-white block group-hover:underline">
                                  {stock.symbol}
                                </span>
                                <span className="text-[10px] text-slate-300 line-clamp-1 opacity-90">
                                  {stock.name}
                                </span>
                              </div>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setFundamentalSymbol(stock.symbol);
                                }}
                                className="p-1 rounded bg-black/30 hover:bg-black/60 text-white/80 hover:text-white transition shrink-0"
                                title="Run 7-Factor Fundamental Audit"
                              >
                                <BookOpen className="w-3 h-3" />
                              </button>
                            </div>

                            <div className="flex items-baseline justify-between mt-2 pt-1 border-t border-white/10">
                              <span className="font-mono text-xs font-bold text-white">
                                {stock.price != null ? `${currency}${stock.price.toFixed(2)}` : '—'}
                              </span>
                              <span className={`font-mono text-[11px] font-bold ${style.badge} px-1.5 py-0.2 rounded`}>
                                {stock.change_pct >= 0 ? '+' : ''}{stock.change_pct.toFixed(2)}%
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Fundamental Analysis Drawer Modal ── */}
      {fundamentalSymbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/80 backdrop-blur-sm">
          <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-4 sm:p-6">
            <button
              onClick={() => setFundamentalSymbol(null)}
              className="absolute top-4 right-4 p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
            >
              <X className="w-4 h-4" />
            </button>
            <FundamentalReport
              symbol={fundamentalSymbol}
              market={constituentMarket}
            />
          </div>
        </div>
      )}

      {/* ── Interactive Candlestick Chart Modal ── */}
      {chartSymbol && (
        <ChartModal
          isOpen={Boolean(chartSymbol)}
          onClose={() => setChartSymbol(null)}
          symbol={chartSymbol}
          market={constituentMarket}
        />
      )}
    </div>
  );
};
