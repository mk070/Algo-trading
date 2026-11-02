import React, { useState } from 'react';
import { BarChart3, X, Maximize2, Minimize2 } from 'lucide-react';
import { CandleChart } from './CandleChart';

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

  if (!isOpen || !symbol) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className={`w-full ${
          isFullScreen ? 'max-w-[98vw] h-[96vh]' : 'max-w-6xl max-h-[92vh]'
        } bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col transition-all duration-200`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800 bg-slate-900/90">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-400">
              <BarChart3 className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-white text-sm">{symbol} Interactive Terminal</h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
                  {market === 'IN' ? 'NSE' : 'NASDAQ'}
                </span>
              </div>
            </div>
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
        <div className="p-3 sm:p-4 overflow-y-auto flex-1 bg-slate-950">
          <CandleChart
            symbol={symbol}
            market={market}
            trigger={trigger}
            stop={stop}
            target={target}
            fullHeight={isFullScreen}
          />
        </div>
      </div>
    </div>
  );
};
