import React, { useEffect, useState } from 'react';
import { Activity, CheckCircle2, Clock, RefreshCw, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react';
import { apiClient } from '../api/client';

export const SystemHealthPage: React.FC = () => {
  const [healthData, setHealthData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchHealth = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getHealth();
      setHealthData(data);
    } catch (e) {
      console.error('Error fetching health:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'HEALTHY':
        return 'bg-emerald-950 text-emerald-400 border-emerald-800';
      case 'DEGRADED':
      case 'CONFIGURED_NOT_AUTH':
        return 'bg-amber-950 text-amber-300 border-amber-800';
      case 'DOWN':
        return 'bg-rose-950 text-rose-400 border-rose-800';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-400" />
            System Health & Provider Diagnostics
          </h1>
          <p className="text-xs text-slate-400">
            Real-time diagnostics of market data providers, portfolio APIs, and scheduled background workers.
          </p>
        </div>

        <button
          onClick={fetchHealth}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Re-check Diagnostics
        </button>
      </div>

      {/* Provider Health Cards */}
      {healthData?.providers && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Object.entries(healthData.providers).map(([key, prov]: [string, any]) => (
            <div key={key} className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between shadow">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-bold text-sm text-white uppercase">{prov.name}</h3>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${getStatusBadge(prov.status)}`}>
                    {prov.status}
                  </span>
                </div>
                <p className="text-xs text-slate-300 mb-3">{prov.message}</p>
              </div>

              <div className="pt-2 border-t border-slate-800 text-[11px] text-slate-500 font-mono flex items-center justify-between">
                <span>Realtime: {prov.is_realtime ? 'YES' : 'NO'}</span>
                {prov.latency_ms && <span>{prov.latency_ms}ms</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Background Jobs History */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800">
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <Clock className="w-4 h-4 text-indigo-400" />
            Recent Scheduler Job Runs
          </h2>
        </div>

        {!healthData?.last_job_runs || healthData.last_job_runs.length === 0 ? (
          <div className="p-8 text-center text-slate-400 text-xs">No job history recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 uppercase font-bold border-b border-slate-800 tracking-wider">
                <tr>
                  <th className="px-4 py-3">Job Name</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Started At</th>
                  <th className="px-4 py-3">Finished At</th>
                  <th className="px-4 py-3">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 font-mono">
                {healthData.last_job_runs.map((j: any, i: number) => (
                  <tr key={i} className="hover:bg-slate-800/40">
                    <td className="px-4 py-3 font-bold text-white font-sans">{j.job}</td>
                    <td className="px-4 py-3 font-sans">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          j.status === 'SUCCESS'
                            ? 'bg-emerald-950 text-emerald-400'
                            : j.status === 'RUNNING'
                            ? 'bg-blue-950 text-blue-400'
                            : 'bg-rose-950 text-rose-400'
                        }`}
                      >
                        {j.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400">{j.started_at ? new Date(j.started_at).toLocaleTimeString() : '-'}</td>
                    <td className="px-4 py-3 text-slate-400">{j.finished_at ? new Date(j.finished_at).toLocaleTimeString() : '-'}</td>
                    <td className="px-4 py-3 font-sans text-slate-400 truncate max-w-xs">{j.detail || 'Completed'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

