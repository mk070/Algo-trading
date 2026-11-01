import React, { useState } from 'react';
import { X } from 'lucide-react';
import { Position } from '../types';

interface RecordExitModalProps {
  position: Position;
  onClose: () => void;
  onSubmit: (data: {
    position_id: number;
    exit_price: number;
    exit_reason: string;
    qty: number;
    note: string;
  }) => void;
}

export const RecordExitModal: React.FC<RecordExitModalProps> = ({
  position,
  onClose,
  onSubmit,
}) => {
  const [exitPrice, setExitPrice] = useState(position.current_price || position.entry_price);
  const [qty, setQty] = useState(position.qty);
  const [exitReason, setExitReason] = useState('Target 1 Reached (2R)');
  const [note, setNote] = useState('');

  const rInitial = position.entry_price - position.initial_stop;
  const pnlPerShare = Number(exitPrice) - position.entry_price;
  const estimatedPnl = pnlPerShare * Number(qty);
  const estimatedR = rInitial > 0 ? (estimatedPnl / (rInitial * Number(qty))) : 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      position_id: position.id,
      exit_price: Number(exitPrice),
      exit_reason: exitReason,
      qty: Number(qty),
      note,
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
          Record Position Exit: {position.symbol}
        </h2>
        <p className="text-xs text-slate-400 mb-4">
          Entry: {position.entry_price.toFixed(2)} | Qty: {position.qty} | Stop: {position.active_stop.toFixed(2)}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3 text-sm">
          <div>
            <label className="text-xs text-slate-300 block mb-1">Exit Fill Price</label>
            <input
              type="number"
              step="0.05"
              value={exitPrice}
              onChange={(e) => setExitPrice(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white font-mono"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-300 block mb-1">Exit Quantity</label>
              <input
                type="number"
                value={qty}
                onChange={(e) => setQty(parseInt(e.target.value) || 1)}
                max={position.qty}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white font-mono"
                required
              />
            </div>
            <div>
              <label className="text-xs text-slate-300 block mb-1">Exit Reason</label>
              <select
                value={exitReason}
                onChange={(e) => setExitReason(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-xs"
              >
                <option value="Target 1 Reached (2R)">Target 1 Reached (2R)</option>
                <option value="Trailing Stop Hit">Trailing Stop Hit</option>
                <option value="Hard Stop Loss Hit">Hard Stop Loss Hit</option>
                <option value="Trend Break (< 50 SMA)">Trend Break (&lt; 50 SMA)</option>
                <option value="Time Stop (Stalled > 15 days)">Time Stop (Stalled &gt; 15 days)</option>
                <option value="Earnings Blackout Guard">Earnings Blackout Guard</option>
                <option value="Manual Discretionary Exit">Manual Discretionary Exit</option>
              </select>
            </div>
          </div>

          {/* Outcome preview */}
          <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 flex items-center justify-between font-mono text-xs">
            <div>
              <span className="text-slate-400 block text-[10px]">Estimated P&L</span>
              <span className={`text-sm font-bold ${estimatedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {estimatedPnl >= 0 ? '+' : ''}{estimatedPnl.toFixed(2)}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px]">R-Multiple</span>
              <span className={`text-sm font-bold ${estimatedR >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {estimatedR >= 0 ? '+' : ''}{estimatedR.toFixed(2)}R
              </span>
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-300 block mb-1">Journal Notes / Learnings</label>
            <textarea
              rows={2}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Trailed well, exited on chandelier stop crossing..."
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
            />
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
              className="px-5 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow"
            >
              Record Exit & Save to Journal
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

