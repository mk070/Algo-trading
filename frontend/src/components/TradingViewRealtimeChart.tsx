import React, { useEffect, useRef } from 'react';
import { ExternalLink } from 'lucide-react';

interface TradingViewRealtimeChartProps {
  symbol: string;
  market: 'IN' | 'US';
  height?: number | string;
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

  // Already qualified
  if (s.includes(':')) return s;

  if (mkt === 'IN') {
    // Indices - these work directly in TV embed
    if (s === 'SENSEX' || s === 'BSESN') return 'BSE:SENSEX';
    if (s === 'NIFTY' || s === 'NIFTY50') return 'NSE:NIFTY';
    if (s === 'BANKNIFTY') return 'NSE:BANKNIFTY';
    // Equities - use BSE prefix (NSE is blocked in external embed)
    return `BSE:${s}`;
  }

  // US stocks/ETFs
  const amexEtfs = ['SPY', 'QQQ', 'DIA', 'IWM', 'GLD', 'SLV', 'TLT', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLU', 'XLI', 'XLB', 'ARKK', 'ARKG'];
  const nyseStocks = [
    'JPM', 'BAC', 'GS', 'MS', 'C', 'WFC', 'BRK.B', 'BRK-B', 'UNH', 'V', 'MA', 'PG', 'HD',
    'CVX', 'XOM', 'LLY', 'JNJ', 'PFE', 'MRK', 'ABT', 'MCD', 'KO', 'WMT', 'DIS', 'BA', 'CAT',
    'GE', 'IBM', 'RTX', 'HON', 'MMM', 'T', 'VZ',
  ];
  if (amexEtfs.includes(s)) return `AMEX:${s}`;
  if (nyseStocks.includes(s)) return `NYSE:${s.replace('-', '.')}`;
  return `NASDAQ:${s}`;
}

export const TradingViewRealtimeChart: React.FC<TradingViewRealtimeChartProps> = ({
  symbol,
  market,
  height = '580px',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const tvSymbol = resolveTVSymbol(symbol, market);

  // "Open on TradingView.com" link - always uses NSE for Indian equities (the full site supports it)
  const directTvUrl = market === 'IN'
    ? `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(
        symbol === 'SENSEX' || symbol === 'BSESN' ? 'BSE:SENSEX' :
        symbol === 'NIFTY' || symbol === 'NIFTY50' ? 'NSE:NIFTY' :
        `NSE:${symbol}`
      )}`
    : `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;

  const resolvedHeight = typeof height === 'number' ? `${height}px` : (height || '580px');

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';

    // Wrapper must be full-size for autosize to work
    const wrapper = document.createElement('div');
    wrapper.className = 'tradingview-widget-container';
    wrapper.style.cssText = 'height:100%;width:100%;';

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.cssText = 'height:calc(100% - 32px);width:100%;';
    wrapper.appendChild(widgetDiv);

    const copyright = document.createElement('div');
    copyright.className = 'tradingview-widget-copyright';
    copyright.style.cssText = 'font-size:10px;color:#6b7280;text-align:right;padding:4px 8px;';
    copyright.innerHTML = '<a href="https://www.tradingview.com/" rel="noopener" target="_blank" style="color:#6b7280;">TradingView</a>';
    wrapper.appendChild(copyright);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;

    const config = {
      autosize: true,
      symbol: tvSymbol,
      interval: 'D',
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
  }, [tvSymbol, market]);

  return (
    <div
      style={{ height: resolvedHeight }}
      className="w-full flex flex-col bg-slate-950 rounded-xl overflow-hidden border border-slate-800"
    >
      {/* Header bar */}
      <div className="flex-shrink-0 px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between gap-2 flex-wrap text-xs">
        <div className="flex items-center gap-2 font-mono">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="font-bold text-white tracking-wide">{tvSymbol}</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800 uppercase tracking-wider">
            OFFICIAL TRADINGVIEW REAL-TIME FEED
          </span>
          {market === 'IN' && tvSymbol.startsWith('BSE:') && (
            <span className="text-[10px] text-slate-500 hidden md:inline">
              BSE feed &middot; NSE embed blocked externally
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-slate-400 hidden sm:inline">Live streaming exchange ticks &middot; Zero latency</span>
          <a
            href={directTvUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors font-medium"
          >
            <span>Open on TradingView &nearr;</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* Chart area - must be flex-1 so it fills remaining height */}
      <div
        ref={containerRef}
        className="flex-1 w-full min-h-0"
        style={{ minHeight: '480px' }}
      />
    </div>
  );
};
