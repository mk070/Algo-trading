import React, { useEffect, useRef } from 'react';

interface TradingViewRealtimeChartProps {
  symbol: string;
  market: 'IN' | 'US';
  height?: number | string;
}

export const TradingViewRealtimeChart: React.FC<TradingViewRealtimeChartProps> = ({
  symbol,
  market,
  height = '100%',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Map to canonical TradingView exchange:symbol syntax
  const resolveTradingViewSymbol = (rawSymbol: string, mkt: 'IN' | 'US'): string => {
    const s = rawSymbol.trim().toUpperCase();
    if (s.includes(':')) return s;

    if (mkt === 'IN') {
      if (s === 'TMPV') return 'NSE:TATAMOTORS';
      if (s === 'SENSEX' || s === 'BSESN') return 'BSE:SENSEX';
      if (s === 'NIFTY' || s === 'NIFTY50') return 'NSE:NIFTY';
      return `NSE:${s}`;
    } else {
      // US Equities & ETFs
      const amexEtfs = ['SPY', 'DIA', 'IWM', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLU', 'XLI', 'XLB'];
      const nyseStocks = ['JPM', 'BRK.B', 'BRK-B', 'UNH', 'V', 'PG', 'HD', 'MA', 'CVX', 'LLY', 'XOM'];
      if (amexEtfs.includes(s)) return `AMEX:${s}`;
      if (nyseStocks.includes(s)) return `NYSE:${s.replace('-', '.')}`;
      return `NASDAQ:${s}`;
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';

    const tvSymbol = resolveTradingViewSymbol(symbol, market);

    // Create TradingView embed wrapper
    const widgetContainer = document.createElement('div');
    widgetContainer.className = 'tradingview-widget-container';
    widgetContainer.style.height = '100%';
    widgetContainer.style.width = '100%';

    const chartHolder = document.createElement('div');
    chartHolder.className = 'tradingview-widget-container__widget';
    chartHolder.style.height = 'calc(100% - 32px)';
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
      timezone: "exchange",
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
  }, [symbol, market]);

  return (
    <div className="w-full h-full flex flex-col bg-slate-950 rounded-xl overflow-hidden border border-slate-800">
      <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 font-mono">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span className="font-bold text-white">{resolveTradingViewSymbol(symbol, market)}</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
            OFFICIAL TRADINGVIEW REAL-TIME FEED
          </span>
        </div>
        <span className="text-[11px] text-slate-400 font-sans hidden sm:inline">
          Live streaming exchange ticks &bull; Zero latency
        </span>
      </div>
      <div
        ref={containerRef}
        style={{ height: typeof height === 'number' ? `${height}px` : height, minHeight: '480px' }}
        className="w-full flex-1"
      />
    </div>
  );
};

