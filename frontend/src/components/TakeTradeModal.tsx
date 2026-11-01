import React, { useState } from 'react';
import { X } from 'lucide-react';
import { Signal } from '../types';

interface TakeTradeModalProps {
  signal: Signal;
  onClose: () => void;
  onSubmit: (data: {
    symbol: string;
    market: string;
    entry_price: number;
    qty: number;
    initial_stop: number;
    target1: number;
    signal_id: number;
    notes: string;
  }) => void;
}

export const TakeTradeModal: React.FC<TakeTradeModalProps> = ({
  signal,
  onClose,
  onSubmit,
}) => {
  const [entryPrice, setEntryPrice] = useState(signal.trigger);
  const [qty, setQty] = useState(signal.qty);
  const [stop, setStop] = useState(signal.stop);
  const [target, setTarget] = useState(signal.target1);
  const [notes, setNotes] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      symbol: signal.symbol,
      market: signal.market,
      entry_price: Number(entryPrice),
      qty: Number(qty),
      initial_stop: Number(stop),
      target1: Number(target),
      signal_id: signal.id,
      notes,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white"
        >
          <X className="w-5 h-5" />
        </button>

        <h2 className="text-lg font-bold text-white mb-1">
          Record Trade Entry: {signal.symbol}
        </h2>
        <p className="text-xs text-slate-400 mb-4">
          Enter your actual execution details from Kite/Broker order fill.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3 text-sm">
          <div>
            <label className="text-xs text-slate-300 block mb-1">Actual Fill Price</label>
            <input
              type="number"
              step="0.05"
              value={entryPrice}
              onChange={(e) => setEntryPrice(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white font-mono"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-300 block mb-1">Filled Quantity</label>
              <input
                type="number"
                value={qty}
                onChange={(e) => setQty(parseInt(e.target.value) || 1)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white font-mono"
                required
              />
            </div>
            <div>
              <label className="text-xs text-slate-300 block mb-1">Initial Stop Loss</label>
              <input
                type="number"
                step="0.05"
                value={stop}
                onChange={(e) => setStop(parseFloat(e.target.value) || 0)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-rose-400 font-mono"
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-300 block mb-1">Target 1 (2R)</label>
            <input
              type="number"
              step="0.05"
              value={target}
              onChange={(e) => setTarget(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-cyan-400 font-mono"
              required
            />
          </div>

          <div>
            <label className="text-xs text-slate-300 block mb-1">Trade Notes / Setup Context</label>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. 15-min volume breakout confirmed, filled via GTT limit..."
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
            />
          </div>

          <div className="mt-2 p-2.5 bg-amber-950/40 border border-amber-800/60 rounded text-[11px] text-amber-300">
            <strong>Important:</strong> Place your stop-loss order (SL / GTT) at your broker immediately after this fill!
          </div>

          <div className="flex justify-end gap-2 mt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow"
            >
              Confirm Position
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

