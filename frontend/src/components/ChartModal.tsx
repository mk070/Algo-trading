import React, { useEffect, useState } from 'react';
import { BarChart3, Layers, Loader2, Maximize2, Minimize2, X, Zap } from 'lucide-react';
import { CandleChart } from './CandleChart';
import { TradingViewRealtimeChart } from './TradingViewRealtimeChart';
import { tradingViewChartUrl } from '../utils/tradingView';
import { API_BASE, fetchJson } from '../api/client';

/** Trade context for showing chart in trade-card mode. */
export interface TradeChartContext {
  tradeId: number;
  tradeType: 'paper' | 'backtest';
  signal_date?: string | null;
  entry_date?: string | null;
  entry_price?: number | null;
  exit_date?: string | null;
  stop_price?: number | null;
  planned_exit_date?: string | null;
  reason_text?: string | null;
}

interface ChartModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string | null;
  market: 'IN' | 'US';
  trigger?: number;
  stop?: number;
  target?: number;
  /** When set, the chart shows trade-card mode with markers instead of live strategy overlay. */
  tradeContext?: TradeChartContext;
}

export const ChartModal: React.FC<ChartModalProps> = ({
  isOpen,
  onClose,
  symbol,
  market,
  trigger,
  stop,
  target,
  tradeContext,
}) => {
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [chartMode, setChartMode] = useState<'STRATEGY' | 'TRADINGVIEW'>('STRATEGY');
  const [tradeChartData, setTradeChartData] = useState<any>(null);
  const [tradeChartLoading, setTradeChartLoading] = useState(false);
  const [tradeChartError, setTradeChartError] = useState<string | null>(null);

  // Escape key listener for modal accessibility
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Fetch trade chart data when in trade-card mode
  useEffect(() => {
    if (!isOpen || !tradeContext) return;
    setTradeChartLoading(true);
    setTradeChartError(null);
    fetchJson(
      `${API_BASE}/lab/trade/${tradeContext.tradeType}/${tradeContext.tradeId}/chart?before=60&after=10`
    )
      .then(data => {
        setTradeChartData(data);
        setTradeChartLoading(false);
      })
      .catch(e => {
        setTradeChartError(e.message || 'Failed to load chart');
        setTradeChartLoading(false);
      });
  }, [isOpen, tradeContext?.tradeId, tradeContext?.tradeType]);

  if (!isOpen || !symbol) return null;

  const isTradeMode = !!tradeContext;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-0 sm:p-2 md:p-4 bg-slate-950/85 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className={`w-full ${
          isFullScreen
            ? 'h-full sm:h-[96vh] sm:max-w-[98vw] sm:rounded-2xl'
            : 'h-full sm:h-[88vh] sm:max-h-[92vh] sm:max-w-6xl sm:rounded-2xl'
        } bg-slate-900 border-0 sm:border border-slate-700/80 shadow-2xl overflow-hidden flex flex-col transition-all duration-200`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between px-3 sm:px-5 py-2 sm:py-2.5 border-b border-slate-800 bg-slate-900/90 gap-2 shrink-0">
          <div className="flex items-center gap-2 sm:gap-2.5 min-w-0">
            <div className="w-6 h-6 sm:w-7 sm:h-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400 shrink-0">
              <BarChart3 className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 sm:gap-2">
                <h3 className="font-bold text-white text-xs sm:text-sm font-mono truncate">{symbol}</h3>
                <span className="px-1.5 py-0.5 rounded text-[9px] sm:text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700 shrink-0">
                  {market === 'IN' ? 'NSE' : 'NASDAQ/NYSE'}
                </span>
                {isTradeMode && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-indigo-900/50 text-indigo-300 border border-indigo-800 shrink-0">
                    TRADE VIEW
                  </span>
                )}
              </div>
              {isTradeMode && tradeContext.reason_text && (
                <p className="text-[10px] text-slate-400 mt-0.5 truncate max-w-xs">{tradeContext.reason_text}</p>
              )}
            </div>
          </div>

          {/* Mode Switcher — only show in non-trade mode */}
          {!isTradeMode && (
            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-[11px] sm:text-xs font-semibold shrink-0">
              <button
                onClick={() => setChartMode('STRATEGY')}
                className={`flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1 rounded-md transition-all ${
                  chartMode === 'STRATEGY'
                    ? 'bg-indigo-600 text-white shadow font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Layers className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-cyan-300 shrink-0" />
                <span className="hidden xs:inline sm:inline">Strategy</span>
                <span className="inline xs:hidden">Strat</span>
              </button>
              <button
                onClick={() => setChartMode('TRADINGVIEW')}
                className={`flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1 rounded-md transition-all ${
                  chartMode === 'TRADINGVIEW'
                    ? 'bg-indigo-600 text-white shadow font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Official 0-latency live streaming TradingView chart"
              >
                <Zap className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-amber-300 shrink-0" />
                <span className="hidden xs:inline sm:inline">TradingView Live</span>
                <span className="inline xs:hidden">TV Live</span>
              </button>
            </div>
          )}

          <div className="flex items-center gap-1 shrink-0">
            <a
              href={tradingViewChartUrl(symbol, market)}
              target="_blank"
              rel="noreferrer"
              className="flex min-h-[32px] items-center gap-1 rounded-lg border border-slate-700 px-2 text-[10px] text-slate-300 hover:bg-slate-800"
              title="Open symbol on TradingView"
            >
              Open in TradingView <Zap className="h-3 w-3" />
            </a>
            <button
              onClick={() => setIsFullScreen(!isFullScreen)}
              className="p-1 sm:p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors hidden sm:flex items-center justify-center"
              title={isFullScreen ? 'Exit Full Screen' : 'Full Screen'}
            >
              {isFullScreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
            <button
              onClick={onClose}
              className="p-1 sm:p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors flex items-center justify-center min-w-[32px] min-h-[32px]"
              title="Close (Esc)"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Trade info legend (trade mode) */}
        {isTradeMode && tradeContext && (
          <div className="flex flex-wrap gap-4 px-4 py-2 bg-slate-950/60 border-b border-slate-800 text-xs">
            {tradeContext.signal_date && (
              <div>
                <span className="text-slate-500">Signal: </span>
                <span className="text-purple-300 font-mono">{tradeContext.signal_date}</span>
              </div>
            )}
            {tradeContext.entry_date && (
              <div>
                <span className="text-slate-500">Entry: </span>
                <span className="text-emerald-300 font-mono">{tradeContext.entry_date}</span>
                {tradeContext.entry_price && (
                  <span className="text-emerald-400 font-mono ml-1">@ ₹{tradeContext.entry_price.toFixed(2)}</span>
                )}
              </div>
            )}
            {tradeContext.stop_price && (
              <div>
                <span className="text-slate-500">Stop: </span>
                <span className="text-red-300 font-mono">₹{tradeContext.stop_price.toFixed(2)}</span>
              </div>
            )}
            {tradeContext.planned_exit_date && (
              <div>
                <span className="text-slate-500">Planned exit: </span>
                <span className="text-amber-300 font-mono">{tradeContext.planned_exit_date}</span>
              </div>
            )}
            {tradeContext.exit_date && (
              <div>
                <span className="text-slate-500">Exited: </span>
                <span className="text-blue-300 font-mono">{tradeContext.exit_date}</span>
              </div>
            )}
          </div>
        )}

        {/* Modal Chart Body */}
        <div className="p-1 sm:p-2 md:p-3 overflow-y-auto flex-1 bg-slate-950 min-h-0 flex flex-col">
          {isTradeMode ? (
            // Trade chart mode: show loading/error or CandleChart with preloaded bars
            tradeChartLoading ? (
              <div className="flex items-center justify-center h-full text-slate-500">
                <Loader2 className="w-6 h-6 animate-spin mr-2" />
                Loading trade chart…
              </div>
            ) : tradeChartError ? (
              <div className="flex items-center justify-center h-full text-red-400 text-sm">
                {tradeChartError}
              </div>
            ) : tradeChartData ? (
              <CandleChart
                symbol={symbol}
                market={market}
                bars={tradeChartData.bars}
                fullHeight={isFullScreen}
                tradeMarkers={tradeChartData.markers}
                tradeSegments={tradeChartData.segments}
              />
            ) : null
          ) : chartMode === 'TRADINGVIEW' ? (
            <TradingViewRealtimeChart symbol={symbol} market={market} height="100%" />
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
