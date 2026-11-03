import React, { useEffect, useRef } from 'react';
import { ExternalLink, Zap } from 'lucide-react';

interface TradingViewRealtimeChartProps {
  symbol: string;
  market: 'IN' | 'US';
  height?: number | string;
}

export const TradingViewRealtimeChart: React.FC<TradingViewRealtimeChartProps> = ({
  symbol,
  market,
  height = '580px',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Map to canonical TradingView exchange:symbol syntax.
  // NOTE: TradingView external widget blocks "NSE:*" symbols with "This symbol is only available on TradingView".
  // BSE symbols ("BSE:RELIANCE", "BSE:TCS", etc.) are allowed for live external embedding.
  const resolveTradingViewSymbol = (rawSymbol: string, mkt: 'IN' | 'US'): string => {
    const s = rawSymbol.trim().toUpperCase();
    if (s.includes(':')) return s;

    if (mkt === 'IN') {
      if (s === 'TMPV' || s === 'TATAMOTORS') return 'BSE:TATAMOTORS';
      if (s === 'SENSEX' || s === 'BSESN') return 'BSE:SENSEX';
      if (s === 'NIFTY' || s === 'NIFTY50') return 'BSE:SENSEX';
      return `BSE:${s}`;
    } else {
      // US Equities & ETFs
      const amexEtfs = ['SPY', 'DIA', 'IWM', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLU', 'XLI', 'XLB'];
      const nyseStocks = ['JPM', 'BRK.B', 'BRK-B', 'UNH', 'V', 'PG', 'HD', 'MA', 'CVX', 'LLY', 'XOM'];
      if (amexEtfs.includes(s)) return `AMEX:${s}`;
      if (nyseStocks.includes(s)) return `NYSE:${s.replace('-', '.')}`;
      return `NASDAQ:${s}`;
    }
  };

  const tvSymbol = resolveTradingViewSymbol(symbol, market);
  const directTvUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(market === 'IN' ? `NSE:${symbol}` : tvSymbol)}`;
  const resolvedHeight = typeof height === 'number' ? `${height}px` : (height || '580px');

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';

    // Create TradingView embed wrapper
    const widgetContainer = document.createElement('div');
    widgetContainer.className = 'tradingview-widget-container';
    widgetContainer.style.height = '100%';
    widgetContainer.style.width = '100%';

    const chartHolder = document.createElement('div');
    chartHolder.className = 'tradingview-widget-container__widget';
    chartHolder.style.height = '100%';
    chartHolder.style.width = '100%';
    widgetContainer.appendChild(chartHolder);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval: "D",
      timezone: market === 'IN' ? "Asia/Kolkata" : "America/New_York",
      theme: "dark",
      style: "1",
      locale: "en",
      enable_publishing: false,
      allow_symbol_change: true,
      calendar: false,
      support_host: "https://www.tradingview.com",
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: true,
      backgroundColor: "#0d0f0e",
      gridColor: "#172033",
      withdateranges: true,
      details: true,
      hotlist: false,
    });

    widgetContainer.appendChild(script);
    containerRef.current.appendChild(widgetContainer);

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [symbol, market, tvSymbol]);

  return (
    <div
      style={{ height: resolvedHeight }}
      className="w-full flex flex-col bg-slate-950 rounded-xl overflow-hidden border border-slate-800 min-h-[380px] sm:min-h-[520px]"
    >
      <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs flex-wrap gap-2">
        <div className="flex items-center gap-2 font-mono">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span className="font-bold text-white">{tvSymbol}</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
            TRADINGVIEW LIVE TICK STREAM
          </span>
          {market === 'IN' && (
            <span className="text-[10px] text-slate-400 font-sans hidden md:inline">
              (BSE feed &bull; TradingView blocks external embed for NSE)
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <a
            href={directTvUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 transition"
          >
            <span>Open on TradingView.com</span>
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
      <div
        ref={containerRef}
        style={{ height: 'calc(100% - 37px)', width: '100%' }}
        className="w-full flex-1 min-h-[340px] sm:min-h-[480px]"
      />
    </div>
  );
};
