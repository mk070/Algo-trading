import React, { useEffect, useState } from 'react';
import { Bell, Trash2, X } from 'lucide-react';
import { apiClient } from '../api/client';

interface CustomAlertItem {
  id: number;
  symbol: string;
  market: string;
  target_price: number;
  condition: string;
  notes?: string | null;
  triggered: boolean;
  triggered_at?: string | null;
  triggered_price?: number | null;
  active: boolean;
  created_at?: string | null;
}

interface CustomAlertsModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentMarket: 'IN' | 'US';
  defaultSymbol?: string;
}

export const CustomAlertsModal: React.FC<CustomAlertsModalProps> = ({
  isOpen,
  onClose,
  currentMarket,
  defaultSymbol,
}) => {
  const [alerts, setAlerts] = useState<CustomAlertItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form State
  const [symbol, setSymbol] = useState(defaultSymbol || '');
  const [targetPrice, setTargetPrice] = useState('');
  const [condition, setCondition] = useState<'ABOVE' | 'BELOW'>('ABOVE');
  const [notes, setNotes] = useState('');

  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getCustomAlerts(currentMarket);
      setAlerts(data);
    } catch (err: any) {
      console.error('Failed to load custom alerts:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      if (defaultSymbol) setSymbol(defaultSymbol);
      fetchAlerts();
    }
  }, [isOpen, currentMarket, defaultSymbol]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim() || !targetPrice || isNaN(Number(targetPrice))) {
      setError('Please provide a valid symbol and price target.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await apiClient.createCustomAlert({
        symbol: symbol.trim().toUpperCase(),
        market: currentMarket,
        target_price: Number(targetPrice),
        condition,
        notes: notes.trim() || undefined,
      });
      setTargetPrice('');
      setNotes('');
      await fetchAlerts();
    } catch (err: any) {
      setError(err?.message || 'Failed to create alert');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await apiClient.deleteCustomAlert(id);
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      console.error('Failed to delete alert:', err);
    }
  };

  if (!isOpen) return null;

  const activeAlerts = alerts.filter((a) => !a.triggered && a.active);
  const triggeredAlerts = alerts.filter((a) => a.triggered);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Bell className="w-4 h-4 text-amber-400" /> Custom Price Alerts ({currentMarket})
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Set user-defined price targets. Monitored continuously in background and labeled [MANUAL ALERT].
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          {/* Create Alert Form */}
          <form onSubmit={handleCreate} className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider block">
              + New Custom Price Target
            </span>

            {error && (
              <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg p-2">
                {error}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 font-medium block mb-1">Symbol</label>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  placeholder="e.g. RELIANCE"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white uppercase focus:outline-none focus:border-indigo-500"
                  required
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 font-medium block mb-1">Condition</label>
                <select
                  value={condition}
                  onChange={(e: any) => setCondition(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="ABOVE">&gt;= Above Target</option>
                  <option value="BELOW">&lt;= Below Target</option>
                </select>
              </div>

              <div>
                <label className="text-[11px] text-slate-400 font-medium block mb-1">
                  Target Price ({currentMarket === 'IN' ? '₹' : '$'})
                </label>
                <input
                  type="number"
                  step="any"
                  value={targetPrice}
                  onChange={(e) => setTargetPrice(e.target.value)}
                  placeholder="e.g. 2950.00"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                  required
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 font-medium block mb-1">Notes (Optional)</label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="e.g. Resistance test"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div className="flex justify-end pt-1">
              <button
                type="submit"
                disabled={submitting}
                className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition disabled:opacity-50 shadow-md"
              >
                {submitting ? 'Creating...' : 'Set Price Alert'}
              </button>
            </div>
          </form>

          {/* Active Alerts List */}
          <div>
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-2 flex items-center justify-between">
              <span>Active Watch Targets ({activeAlerts.length})</span>
            </h4>

            {loading && alerts.length === 0 && (
              <div className="text-xs text-slate-500 py-3 text-center">Loading alerts...</div>
            )}

            {!loading && activeAlerts.length === 0 && (
              <div className="text-xs text-slate-500 py-4 text-center border border-dashed border-slate-800 rounded-lg">
                No active custom alerts for {currentMarket}. Set one above to track specific price levels.
              </div>
            )}

            <div className="space-y-2">
              {activeAlerts.map((a) => (
                <div
                  key={a.id}
                  className="bg-slate-950/40 border border-slate-800/80 rounded-lg p-3 flex items-center justify-between hover:border-slate-700 transition"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-bold text-sm text-white">{a.symbol}</span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono ${
                        a.condition === 'ABOVE'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                      }`}
                    >
                      {a.condition === 'ABOVE' ? '≥ ABOVE' : '≤ BELOW'} {currentMarket === 'IN' ? '₹' : '$'}
                      {a.target_price.toFixed(2)}
                    </span>
                    {a.notes && <span className="text-xs text-slate-400 italic">"{a.notes}"</span>}
                  </div>

                  <button
                    onClick={() => handleDelete(a.id)}
                    className="text-slate-500 hover:text-rose-400 text-xs px-2 py-1 rounded border border-slate-800 hover:border-rose-900/60 transition"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Triggered Alerts History */}
          {triggeredAlerts.length > 0 && (
            <div>
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Triggered Alert History ({triggeredAlerts.length})
              </h4>
              <div className="space-y-2">
                {triggeredAlerts.map((a) => (
                  <div
                    key={a.id}
                    className="bg-slate-950/30 border border-slate-800/40 rounded-lg p-3 flex items-center justify-between text-xs text-slate-400"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 font-mono">
                        [MANUAL ALERT]
                      </span>
                      <span className="font-mono font-bold text-slate-200">{a.symbol}</span>
                      <span>
                        Target: {a.condition} {a.target_price.toFixed(2)}
                      </span>
                      {a.triggered_price != null && (
                        <span className="text-emerald-400 font-mono">
                          (Hit @ {a.triggered_price.toFixed(2)})
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] text-slate-500">
                        {a.triggered_at ? new Date(a.triggered_at).toLocaleTimeString() : ''}
                      </span>
                      <button
                        onClick={() => handleDelete(a.id)}
                        className="text-slate-600 hover:text-slate-400 text-[10px]"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

