import React, { useState } from 'react';
import { BarChart3, Layers, Maximize2, Minimize2, X, Zap } from 'lucide-react';
import { CandleChart } from './CandleChart';
import { TradingViewRealtimeChart } from './TradingViewRealtimeChart';

interface ChartModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string | null;
  market: 'IN' | 'US';
  trigger?: number;
  stop?: number;
  target?: number;
}

export const ChartModal: React.FC<ChartModalProps> = ({
  isOpen,
  onClose,
  symbol,
  market,
  trigger,
  stop,
  target,
}) => {
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [chartMode, setChartMode] = useState<'STRATEGY' | 'TRADINGVIEW'>('STRATEGY');

  if (!isOpen || !symbol) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className={`w-full ${
          isFullScreen ? 'max-w-[98vw] h-[96vh]' : 'max-w-6xl h-[88vh] max-h-[92vh]'
        } bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col transition-all duration-200`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between px-4 sm:px-5 py-2.5 border-b border-slate-800 bg-slate-900/90 flex-wrap gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400">
              <BarChart3 className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-white text-sm">{symbol}</h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
                  {market === 'IN' ? 'NSE' : 'NASDAQ/NYSE'}
                </span>
              </div>
            </div>
          </div>

          {/* Mode Switcher: Strategy Terminal vs TradingView Real-Time */}
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-xs font-semibold">
            <button
              onClick={() => setChartMode('STRATEGY')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all ${
                chartMode === 'STRATEGY'
                  ? 'bg-indigo-600 text-white shadow font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Swing Intel Strategy terminal with VCP base, buy trigger, stop loss, EMAs, RSI, and ATR"
            >
              <Layers className="w-3.5 h-3.5 text-cyan-300" />
              <span>Strategy & Indicators</span>
            </button>
            <button
              onClick={() => setChartMode('TRADINGVIEW')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all ${
                chartMode === 'TRADINGVIEW'
                  ? 'bg-indigo-600 text-white shadow font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Official 0-latency live streaming TradingView chart"
            >
              <Zap className="w-3.5 h-3.5 text-amber-300" />
              <span>TradingView Live</span>
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setIsFullScreen(!isFullScreen)}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title={isFullScreen ? 'Exit Full Screen' : 'Full Screen'}
            >
              {isFullScreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Close (Esc)"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Chart Body */}
        <div className="p-2 sm:p-3 overflow-y-auto flex-1 bg-slate-950 min-h-0 flex flex-col">
          {chartMode === 'TRADINGVIEW' ? (
            <TradingViewRealtimeChart
              symbol={symbol}
              market={market}
              height="100%"
            />
          ) : (
            <CandleChart
              symbol={symbol}
              market={market}
              trigger={trigger}
              stop={stop}
              target={target}
              fullHeight={isFullScreen}
            />
          )}
        </div>
      </div>
    </div>
  );
};
