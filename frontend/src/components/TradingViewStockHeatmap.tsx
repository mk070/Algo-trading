import React, { useEffect, useRef, useState } from 'react';

interface TradingViewStockHeatmapProps {
  market: 'IN' | 'US';
  height?: number | string;
  hasTopBar?: boolean;
}

export const TradingViewStockHeatmap: React.FC<TradingViewStockHeatmapProps> = ({
  market,
  height = '100%',
  hasTopBar = true,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [inIndex, setInIndex] = useState<'NIFTY 50' | 'SENSEX'>('NIFTY 50');

  const dataSource = market === 'IN' ? inIndex : 'SPX500';

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';

    const widgetContainer = document.createElement('div');
    widgetContainer.className = 'tradingview-widget-container';
    widgetContainer.style.width = '100%';
    widgetContainer.style.height = typeof height === 'number' ? `${height}px` : height;

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.width = '100%';
    widgetDiv.style.height = '100%';
    widgetContainer.appendChild(widgetDiv);

    const script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js';
    script.async = true;

    // TradingView official requirement: when dataSource is set to an index (e.g. NIFTY 50, SENSEX, SPX500),
    // exchanges must be empty array [] so it resolves the index constituents globally across native listings.
    const widgetConfig = {
      exchanges: [],
      dataSource: dataSource,
      grouping: 'sector',
      blockSize: 'market_cap_basic',
      blockColor: 'change',
      locale: 'en',
      symbolUrl: '',
      colorTheme: 'dark',
      hasTopBar: hasTopBar,
      isDataSetEnabled: true,
      isZoomEnabled: true,
      hasSymbolTooltip: true,
      isMonoSize: false,
      width: '100%',
      height: '100%',
    };

    script.innerHTML = JSON.stringify(widgetConfig);
    widgetContainer.appendChild(script);
    containerRef.current.appendChild(widgetContainer);

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [market, dataSource, height, hasTopBar]);

  const resolvedHeight = typeof height === 'number' ? `${height}px` : height;

  return (
    <div className="relative w-full flex flex-col">
      {market === 'IN' && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900 border-b border-slate-800 text-xs">
          <span className="text-[11px] text-slate-400 font-medium">Indian Benchmark Index:</span>
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5">
            <button
              onClick={() => setInIndex('NIFTY 50')}
              className={`px-2.5 py-0.5 rounded text-[11px] font-semibold transition ${
                inIndex === 'NIFTY 50'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              NIFTY 50 (NSE)
            </button>
            <button
              onClick={() => setInIndex('SENSEX')}
              className={`px-2.5 py-0.5 rounded text-[11px] font-semibold transition ${
                inIndex === 'SENSEX'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              SENSEX (BSE)
            </button>
          </div>
        </div>
      )}
      <div
        ref={containerRef}
        className="w-full rounded-xl overflow-hidden bg-slate-950 border border-slate-800/80"
        style={{ height: resolvedHeight, minHeight: '360px' }}
      />
    </div>
  );
};
