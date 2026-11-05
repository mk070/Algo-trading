import React, { useEffect, useRef } from 'react';

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

  const dataSource = market === 'IN' ? 'NIFTY 50' : 'SPX500';
  const exchanges = market === 'IN' ? ['BSE', 'NSE'] : [];

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

    const widgetConfig = {
      exchanges: exchanges,
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
    <div
      ref={containerRef}
      className="w-full rounded-xl overflow-hidden bg-slate-950 border border-slate-800/80"
      style={{ height: resolvedHeight, minHeight: '360px' }}
    />
  );
};
