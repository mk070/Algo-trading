import React, { useState } from 'react';

interface CandleBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20?: number | null;
  sma50?: number | null;
  sma200?: number | null;
  rsi14?: number | null;
  atr14?: number | null;
}

interface CandleChartProps {
  symbol: string;
  bars: CandleBar[];
  trigger?: number;
  stop?: number;
  target?: number;
}

export const CandleChart: React.FC<CandleChartProps> = ({
  symbol,
  bars,
  trigger,
  stop,
  target,
}) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  if (!bars || bars.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center bg-slate-900 border border-slate-800 rounded-lg text-slate-500">
        No candle data available
      </div>
    );
  }

  // Display recent 60-80 bars for clean visual display
  const viewBars = bars.slice(-60);
  const n = viewBars.length;

  const minPrice = Math.min(
    ...viewBars.map((b) => b.low),
    stop ? stop * 0.99 : Infinity
  );
  const maxPrice = Math.max(
    ...viewBars.map((b) => b.high),
    trigger ? trigger * 1.01 : -Infinity,
    target ? target * 1.01 : -Infinity
  );
  const priceRange = maxPrice - minPrice || 1;

  const maxVolume = Math.max(...viewBars.map((b) => b.volume)) || 1;

  const chartHeight = 320;
  const chartWidth = 720;
  const paddingRight = 60;
  const usableWidth = chartWidth - paddingRight;
  const barWidth = Math.max(2, (usableWidth / n) * 0.7);

  const getY = (val: number) => {
    return chartHeight - ((val - minPrice) / priceRange) * (chartHeight - 40) - 20;
  };

  const hoveredBar = hoverIndex !== null ? viewBars[hoverIndex] : viewBars[viewBars.length - 1];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-col gap-2 shadow-xl">
      {/* Chart Top Header & Live Candle Info */}
      <div className="flex flex-wrap items-center justify-between text-xs gap-3 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <span className="font-bold text-sm text-slate-100">{symbol}</span>
          <span className="text-slate-400">1D Timeframe</span>
          {hoveredBar && (
            <span className="text-slate-500">({hoveredBar.time})</span>
          )}
        </div>
        {hoveredBar && (
          <div className="flex items-center gap-4 text-slate-300 font-mono">
            <span>O: <span className="text-slate-100">{hoveredBar.open.toFixed(2)}</span></span>
            <span>H: <span className="text-emerald-400">{hoveredBar.high.toFixed(2)}</span></span>
            <span>L: <span className="text-rose-400">{hoveredBar.low.toFixed(2)}</span></span>
            <span>C: <span className="text-indigo-300">{hoveredBar.close.toFixed(2)}</span></span>
            {hoveredBar.rsi14 && <span>RSI: <span className="text-amber-400">{hoveredBar.rsi14.toFixed(1)}</span></span>}
            {hoveredBar.atr14 && <span>ATR: <span className="text-cyan-400">{hoveredBar.atr14.toFixed(2)}</span></span>}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-amber-400 rounded"></span> EMA 20
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-blue-400 rounded"></span> SMA 50
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-purple-400 rounded"></span> SMA 200
        </span>
        {trigger && (
          <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
            <span className="w-3 h-0.5 bg-emerald-400 border-dashed border-t"></span> Buy Trigger: {trigger.toFixed(2)}
          </span>
        )}
        {stop && (
          <span className="flex items-center gap-1.5 text-rose-400 font-medium">
            <span className="w-3 h-0.5 bg-rose-400 border-dashed border-t"></span> Stop Loss: {stop.toFixed(2)}
          </span>
        )}
        {target && (
          <span className="flex items-center gap-1.5 text-teal-400 font-medium">
            <span className="w-3 h-0.5 bg-teal-400 border-dashed border-t"></span> Target 1: {target.toFixed(2)}
          </span>
        )}
      </div>

      {/* SVG Canvas */}
      <div className="relative w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight + 60}`}
          className="w-full h-auto min-w-[600px] select-none"
        >
          {/* Horizontal Grid lines */}
          {[0.2, 0.4, 0.6, 0.8].map((ratio) => {
            const priceLevel = minPrice + ratio * priceRange;
            const y = getY(priceLevel);
            return (
              <g key={ratio}>
                <line x1="0" y1={y} x2={usableWidth} y2={y} stroke="#334155" strokeDasharray="3 3" strokeOpacity="0.4" />
                <text x={usableWidth + 6} y={y + 4} fill="#64748b" fontSize="10" fontFamily="monospace">
                  {priceLevel.toFixed(1)}
                </text>
              </g>
            );
          })}

          {/* Trigger Line */}
          {trigger && (
            <g>
              <line x1="0" y1={getY(trigger)} x2={usableWidth} y2={getY(trigger)} stroke="#10b981" strokeWidth="1.5" strokeDasharray="4 4" />
              <text x={usableWidth + 6} y={getY(trigger) + 4} fill="#10b981" fontSize="10" fontWeight="bold">
                T: {trigger.toFixed(1)}
              </text>
            </g>
          )}

          {/* Target Line */}
          {target && (
            <g>
              <line x1="0" y1={getY(target)} x2={usableWidth} y2={getY(target)} stroke="#06b6d4" strokeWidth="1.5" strokeDasharray="4 4" />
              <text x={usableWidth + 6} y={getY(target) + 4} fill="#06b6d4" fontSize="10" fontWeight="bold">
                TG: {target.toFixed(1)}
              </text>
            </g>
          )}

          {/* Stop Line */}
          {stop && (
            <g>
              <line x1="0" y1={getY(stop)} x2={usableWidth} y2={getY(stop)} stroke="#f43f5e" strokeWidth="1.5" strokeDasharray="4 4" />
              <text x={usableWidth + 6} y={getY(stop) + 4} fill="#f43f5e" fontSize="10" fontWeight="bold">
                SL: {stop.toFixed(1)}
              </text>
            </g>
          )}

          {/* EMA 20 Line */}
          <path
            d={viewBars
              .map((b, i) => {
                if (!b.ema20) return '';
                const x = (i + 0.5) * (usableWidth / n);
                const y = getY(b.ema20);
                return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
              })
              .join(' ')}
            fill="none"
            stroke="#fbbf24"
            strokeWidth="1.2"
          />

          {/* SMA 50 Line */}
          <path
            d={viewBars
              .map((b, i) => {
                if (!b.sma50) return '';
                const x = (i + 0.5) * (usableWidth / n);
                const y = getY(b.sma50);
                return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
              })
              .join(' ')}
            fill="none"
            stroke="#60a5fa"
            strokeWidth="1.5"
          />

          {/* SMA 200 Line */}
          <path
            d={viewBars
              .map((b, i) => {
                if (!b.sma200) return '';
                const x = (i + 0.5) * (usableWidth / n);
                const y = getY(b.sma200);
                return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
              })
              .join(' ')}
            fill="none"
            stroke="#c084fc"
            strokeWidth="1.5"
          />

          {/* Candlesticks & Volume Bars */}
          {viewBars.map((b, i) => {
            const x = (i + 0.5) * (usableWidth / n);
            const isBullish = b.close >= b.open;
            const color = isBullish ? '#10b981' : '#f43f5e';

            const yOpen = getY(b.open);
            const yClose = getY(b.close);
            const yHigh = getY(b.high);
            const yLow = getY(b.low);

            const candleTop = Math.min(yOpen, yClose);
            const candleHeight = Math.max(2, Math.abs(yClose - yOpen));

            // Volume bar in bottom pane
            const volHeight = (b.volume / maxVolume) * 45;
            const volY = chartHeight + 50 - volHeight;

            return (
              <g
                key={i}
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex(null)}
                className="cursor-pointer"
              >
                {/* Candle wick */}
                <line x1={x} y1={yHigh} x2={x} y2={yLow} stroke={color} strokeWidth="1.2" />
                {/* Candle body */}
                <rect
                  x={x - barWidth / 2}
                  y={candleTop}
                  width={barWidth}
                  height={candleHeight}
                  fill={color}
                  rx="1"
                />
                {/* Volume bar */}
                <rect
                  x={x - barWidth / 2}
                  y={volY}
                  width={barWidth}
                  height={volHeight}
                  fill={color}
                  opacity="0.35"
                />
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
};

