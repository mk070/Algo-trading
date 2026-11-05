import React, { useEffect, useRef, useState } from 'react';
import { ExternalLink, RefreshCw, Zap, Clock } from 'lucide-react';

export interface TimeframeOption {
  label: string;
  interval: string;
  description: string;
}

export const TV_TIMEFRAMES: TimeframeOption[] = [
  { label: '1m', interval: '1', description: '1 Minute (Ultra Low Latency)' },
  { label: '3m', interval: '3', description: '3 Minutes' },
  { label: '5m', interval: '5', description: '5 Minutes' },
  { label: '15m', interval: '15', description: '15 Minutes (Standard Intraday)' },
  { label: '30m', interval: '30', description: '30 Minutes' },
  { label: '1h', interval: '60', description: '1 Hour' },
  { label: '2h', interval: '120', description: '2 Hours' },
  { label: '4h', interval: '240', description: '4 Hours (Swing Horizon)' },
  { label: '1D', interval: 'D', description: 'Daily (Primary Swing Trend)' },
  { label: '1W', interval: 'W', description: 'Weekly (Macro Trend)' },
  { label: '1M', interval: 'M', description: 'Monthly' },
];

interface TradingViewRealtimeChartProps {
  symbol: string;
  market: 'IN' | 'US';
  height?: number | string;
  initialInterval?: string;
  onIntervalChange?: (interval: string) => void;
}

/**
 * Maps raw symbol -> TradingView exchange:symbol for the EMBED widget.
 *
 * Key constraints:
 * - TradingView EXTERNAL embed blocks NSE:* ("symbol is only on TradingView").
 * - BSE:* symbols are allowed for Indian equities in external embeds.
 * - Indices: BSE:SENSEX works; NIFTY -> NSE:NIFTY also generally works.
 * - US: NASDAQ:SYMBOL for most tech; NYSE for banking/consumer; AMEX for ETFs.
 */
function resolveTVSymbol(raw: string, mkt: 'IN' | 'US'): string {
  const s = raw.trim().toUpperCase();
  const clean = s.replace(/^(NSE|BSE):/, '').trim();

  if (mkt === 'IN') {
    // Indices - these work directly in TV embed
    if (clean === 'SENSEX' || clean === 'BSESN') return 'BSE:SENSEX';
    if (clean === 'NIFTY' || clean === 'NIFTY50') return 'NSE:NIFTY';
    if (clean === 'BANKNIFTY') return 'NSE:BANKNIFTY';
    // Equities - always use BSE prefix because TradingView embed widget blocks NSE equities with a popup
    return `BSE:${clean}`;
  }

  // Already qualified for US (e.g. NASDAQ:AAPL, NYSE:JPM, AMEX:SPY)
  if (s.includes(':')) return s;

  // US stocks/ETFs
  const amexEtfs = ['SPY', 'QQQ', 'DIA', 'IWM', 'GLD', 'SLV', 'TLT', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLU', 'XLI', 'XLB', 'ARKK', 'ARKG'];
  const nyseStocks = [
    'JPM', 'BAC', 'GS', 'MS', 'C', 'WFC', 'BRK.B', 'BRK-B', 'UNH', 'V', 'MA', 'PG', 'HD',
    'CVX', 'XOM', 'LLY', 'JNJ', 'PFE', 'MRK', 'ABT', 'MCD', 'KO', 'WMT', 'DIS', 'BA', 'CAT',
    'GE', 'IBM', 'RTX', 'HON', 'MMM', 'T', 'VZ',
  ];
  if (amexEtfs.includes(clean)) return `AMEX:${clean}`;
  if (nyseStocks.includes(clean)) return `NYSE:${clean.replace('-', '.')}`;
  return `NASDAQ:${clean}`;
}

export const TradingViewRealtimeChart: React.FC<TradingViewRealtimeChartProps> = ({
  symbol,
  market,
  height = '580px',
  initialInterval = 'D',
  onIntervalChange,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedInterval, setSelectedInterval] = useState<string>(initialInterval);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const tvSymbol = resolveTVSymbol(symbol, market);

  // Direct link to TradingView site
  const directTvUrl = market === 'IN'
    ? `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(
        symbol === 'SENSEX' || symbol === 'BSESN' ? 'BSE:SENSEX' :
        symbol === 'NIFTY' || symbol === 'NIFTY50' ? 'NSE:NIFTY' :
        `NSE:${symbol}`
      )}`
    : `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;

  const resolvedHeight = typeof height === 'number' ? `${height}px` : (height || '580px');

  const handleSelectInterval = (intv: string) => {
    setSelectedInterval(intv);
    if (onIntervalChange) {
      onIntervalChange(intv);
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';

    // Wrapper must be full-size for autosize to work
    const wrapper = document.createElement('div');
    wrapper.className = 'tradingview-widget-container';
    wrapper.style.cssText = 'height:100%;width:100%;';

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.cssText = 'height:calc(100% - 28px);width:100%;';
    wrapper.appendChild(widgetDiv);

    const copyright = document.createElement('div');
    copyright.className = 'tradingview-widget-copyright';
    copyright.style.cssText = 'font-size:10px;color:#6b7280;text-align:right;padding:2px 8px;';
    copyright.innerHTML = '<a href="https://www.tradingview.com/" rel="noopener" target="_blank" style="color:#6b7280;">TradingView Live Feed</a>';
    wrapper.appendChild(copyright);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;

    const config = {
      autosize: true,
      symbol: tvSymbol,
      interval: selectedInterval,
      timezone: market === 'IN' ? 'Asia/Kolkata' : 'America/New_York',
      theme: 'dark',
      style: '1',
      locale: 'en',
      enable_publishing: false,
      allow_symbol_change: true,
      calendar: false,
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: true,
      backgroundColor: '#0d0f0e',
      gridColor: '#172033',
      withdateranges: true,
      details: true,
      hotlist: false,
      support_host: 'https://www.tradingview.com',
    };
    script.text = JSON.stringify(config);

    wrapper.appendChild(script);
    containerRef.current.appendChild(wrapper);

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [tvSymbol, market, selectedInterval, reloadKey]);

  const currentTfOption = TV_TIMEFRAMES.find((t) => t.interval === selectedInterval) || {
    label: selectedInterval,
    description: `Interval ${selectedInterval}`,
  };

  return (
    <div
      style={{ height: resolvedHeight }}
      className="w-full flex flex-col bg-slate-950 rounded-xl overflow-hidden border border-slate-800 shadow-xl"
    >
      {/* ── Top Header Bar ── */}
      <div className="flex-shrink-0 px-3 sm:px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between gap-2 flex-wrap text-xs">
        <div className="flex items-center gap-2 font-mono flex-wrap">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="font-bold text-white tracking-wide">{tvSymbol}</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800 uppercase tracking-wider flex items-center gap-1">
            <Zap className="w-3 h-3 text-emerald-400" />
            LIVE REAL-TIME FEED
          </span>
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-mono">
            {currentTfOption.description}
          </span>
          {market === 'IN' && tvSymbol.startsWith('BSE:') && (
            <span className="text-[10px] text-slate-500 hidden md:inline">
              BSE feed &middot; NSE external embed restricted by TV
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setReloadKey((k) => k + 1)}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
            title="Force reconnect live feed without page reload"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <a
            href={directTvUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors font-medium px-2 py-1 rounded bg-indigo-950/60 border border-indigo-900/60"
          >
            <span>Full TV Site &nearr;</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* ── Dedicated Full Timeframe Selector Toolbar (Requested by User) ── */}
      <div className="flex-shrink-0 px-2 sm:px-4 py-1.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between gap-1 sm:gap-2 overflow-x-auto">
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold px-1 hidden sm:inline flex items-center gap-1">
            <Clock className="w-3 h-3 text-slate-500" /> Timeframes:
          </span>
          <div className="flex items-center bg-slate-900 rounded-lg p-0.5 border border-slate-800 gap-0.5">
            {TV_TIMEFRAMES.map((tf) => {
              const isActive = selectedInterval === tf.interval;
              return (
                <button
                  key={tf.interval}
                  onClick={() => handleSelectInterval(tf.interval)}
                  className={`px-2 sm:px-2.5 py-1 rounded text-[11px] font-mono font-bold transition-all ${
                    isActive
                      ? 'bg-indigo-600 text-white shadow-sm ring-1 ring-indigo-400'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/80'
                  }`}
                  title={tf.description}
                >
                  {tf.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="text-[10px] font-mono text-emerald-400 shrink-0 hidden md:flex items-center gap-1 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-900/50">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>Real-time Ticking</span>
        </div>
      </div>

      {/* ── Chart embed canvas ── */}
      <div
        ref={containerRef}
        className="flex-1 w-full min-h-0"
        style={{ minHeight: '440px' }}
      />
    </div>
  );
};
