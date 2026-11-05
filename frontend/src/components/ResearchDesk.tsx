import React, { useMemo, useState } from 'react';
import { Activity, BarChart3, Bell, BookOpen, Gavel, Newspaper, Radar, Scale, ShieldCheck, TrendingDown, TrendingUp } from 'lucide-react';
import { apiClient } from '../api/client';
import { Signal } from '../types';

const roleGroups = [
  { group: 'Find', roles: ['Scout'] },
  { group: 'Analyse', roles: ['Technician', 'Fundamentalist', 'Newsdesk'] },
  { group: 'Plan and protect', roles: ['Planner', 'Risk Manager'] },
  { group: 'Decide and notify', roles: ['Bull', 'Bear', 'Judge', 'Messenger'] },
];
const icons: Record<string, React.ElementType> = { Scout: Radar, Technician: BarChart3, Fundamentalist: BookOpen, Newsdesk: Newspaper, Planner: Activity, 'Risk Manager': ShieldCheck, Bull: TrendingUp, Bear: TrendingDown, Judge: Gavel, Messenger: Bell };

function statusStyle(status: string) {
  if (status === 'PASS' || status === 'CLEAR' || status === 'GREEN') return 'border-emerald-800 text-emerald-300 bg-emerald-950/50';
  if (status === 'BLOCK' || status === 'FAIL' || status === 'RED') return 'border-rose-800 text-rose-300 bg-rose-950/40';
  if (status === 'UNKNOWN' || status === 'NOT EVALUATED') return 'border-slate-700 border-dashed text-slate-400 bg-slate-900';
  return 'border-amber-800 text-amber-300 bg-amber-950/40';
}

export const ResearchDesk: React.FC<{ signal: Signal }> = ({ signal }) => {
  const [fundamentals, setFundamentals] = useState<any>(signal.fundamentals || null);
  const [loadingFundamentals, setLoadingFundamentals] = useState(false);
  const [importMessage, setImportMessage] = useState('');
  const refreshFundamentals = async () => {
    setLoadingFundamentals(true);
    try { setFundamentals(await apiClient.getFundamentalLights(signal.symbol, signal.market)); }
    catch { setFundamentals(null); }
    finally { setLoadingFundamentals(false); }
  };
  const importFundamentals = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const result: any = await apiClient.importFundamentalsCsv(file);
      setImportMessage(`${result.rows_imported} rows imported · ${result.unmatched_signals.length} without stored signals`);
      if (result.snapshots?.[signal.symbol]) setFundamentals(result.snapshots[signal.symbol]);
    } catch (error: any) { setImportMessage(error.message || 'CSV import failed'); }
    event.target.value = '';
  };

  const allChecks = useMemo(() => signal.decision_stages?.flatMap((stage) => stage.checks || []) || [], [signal.decision_stages]);
  const passed = allChecks.filter((check) => check.passed).length;
  const failed = allChecks.length - passed;
  const stage = (name: string) => signal.decision_stages?.find((item) => item.stage_name.includes(name));
  const firstBlocked = signal.decision_stages?.find((item) => item.status === 'BLOCK');
  const roleStatus = (role: string) => {
    if (role === 'Scout') return stage('Scanner')?.status || 'NOT EVALUATED';
    if (role === 'Technician') return stage('Setup Validator')?.status || 'NOT EVALUATED';
    if (role === 'Fundamentalist') return fundamentals?.mode === 'off' ? 'NOT EVALUATED' : fundamentals?.red_count ? 'WARN' : fundamentals ? (fundamentals.unknown_count ? 'UNKNOWN' : 'PASS') : 'UNKNOWN';
    if (role === 'Newsdesk') return signal.news_coverage?.status || 'UNKNOWN';
    if (role === 'Planner') return stage('Entry Planner')?.status === 'PASS' && stage('Exit Planner')?.status === 'PASS' ? 'PASS' : stage('Entry Planner')?.status || 'WAIT';
    if (role === 'Risk Manager') return stage('Risk Validator')?.status || 'WAIT';
    if (role === 'Bull') return passed > 0 ? 'PASS' : 'WAIT';
    if (role === 'Bear') return failed > 0 ? 'WARN' : 'CLEAR';
    if (role === 'Judge') return fundamentals?.blocks ? 'BLOCK' : fundamentals?.review ? 'REVIEW' : signal.decision_stages?.some((x) => x.status === 'BLOCK') ? 'BLOCK' : signal.decision_stages?.some((x) => x.status === 'WAIT') ? 'WAIT' : 'PASS';
    return 'NOT EVALUATED';
  };
  const roleWhy = (role: string) => {
    if (role === 'Scout') return `${stage('Scanner')?.checks.filter((item) => item.passed).length || 0} scanner checks passed`;
    if (role === 'Technician') return `${stage('Setup Validator')?.checks.filter((item) => item.passed).length || 0} technical checks passed`;
    if (role === 'Fundamentalist') return fundamentals ? `${fundamentals.unknown_count} UNKNOWN · ${fundamentals.red_count} RED` : 'Unofficial data not available';
    if (role === 'Newsdesk') return `${signal.news_coverage?.red_events_count || 0} RED · ${signal.news_coverage?.amber_events_count || 0} AMBER items`;
    if (role === 'Planner') return signal.trigger ? `Trigger ${signal.trigger} · Stop ${signal.stop} · Qty ${signal.qty}` : 'Entry and exit plan pending';
    if (role === 'Risk Manager') return stage('Risk Validator')?.rejection_reasons?.[0] || 'Risk checks from decision pipeline';
    if (role === 'Bull') return allChecks.filter((item) => item.passed).slice(0, 2).map((item) => item.name).join(' · ') || 'No passed checks to cite';
    if (role === 'Bear') return allChecks.filter((item) => !item.passed).slice(0, 2).map((item) => item.name).join(' · ') || 'No failed checks recorded';
    if (role === 'Judge') return `${passed} of ${allChecks.length} checks passed · not a probability${fundamentals?.review ? ' · Fundamental RED review' : ''}`;
    return 'Alert delivery status unavailable in this view';
  };

  const stepRoles = ['Scout', 'Technician', 'Fundamentalist', 'Newsdesk', 'Planner', 'Risk Manager', 'Bull', 'Bear', 'Judge', 'Messenger'];
  return <section className="rounded-xl border border-slate-800 bg-slate-900 p-4" aria-label={`Research Desk for ${signal.symbol}`}>
    <div className="mb-3 flex items-center justify-between"><h4 className="text-sm font-bold text-slate-100">Research Desk</h4><span className="text-[10px] text-slate-500">Deterministic checks · Judge is the DecisionPipeline</span></div>
    <div className="mb-4 flex gap-1 overflow-x-auto pb-2" aria-label="Decision stage stepper">
      {stepRoles.map((role) => { const Icon = icons[role]; const status = roleStatus(role); const stopped = Boolean(firstBlocked && ((role === 'Scout' && firstBlocked.stage_name === 'Scanner') || (role === 'Technician' && firstBlocked.stage_name === 'Setup Validator') || (role === 'Fundamentalist' && firstBlocked.stage_name === 'Fundamentalist') || (role === 'Newsdesk' && firstBlocked.stage_name === 'News/Event Analyst') || (role === 'Planner' && ['Entry Planner', 'Exit Planner', 'Position Sizer'].includes(firstBlocked.stage_name)) || (role === 'Risk Manager' && firstBlocked.stage_name === 'Risk Validator'))); return <div key={role} title={`${role}: ${status}${stopped ? ' · first blocking stage' : ''}`} className={`flex min-w-fit items-center gap-1 rounded border px-2 py-1 text-[10px] ${statusStyle(status)} ${stopped ? 'ring-1 ring-rose-400' : ''}`}><Icon className="h-3 w-3"/><span>{role}</span></div>; })}
    </div>
    {firstBlocked && <p className="mb-3 text-xs text-rose-300">Stopped here: {firstBlocked.stage_name}{firstBlocked.rejection_reasons?.[0] ? ` · ${firstBlocked.rejection_reasons[0]}` : ''}</p>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {roleGroups.map((group) => <div key={group.group} className="rounded-lg border border-slate-800 bg-slate-950/40 p-2"><h5 className="mb-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">{group.group}</h5><div className="space-y-2">{group.roles.map((role) => { const Icon = icons[role]; const status = roleStatus(role); return <details key={role} className="rounded border border-slate-800 bg-slate-900/60 p-2"><summary className="flex cursor-pointer list-none items-center justify-between gap-2"><span className="flex items-center gap-1.5 text-xs font-semibold text-slate-200"><Icon className="h-3.5 w-3.5 text-slate-400"/>{role}</span><span className={`rounded border px-1.5 py-0.5 text-[9px] ${statusStyle(status)}`}>{status}</span></summary><p className="mt-2 text-[10px] leading-relaxed text-slate-400">{roleWhy(role)}</p><p className="mt-1 text-[10px] text-slate-500">Checks in pipeline: {stage(role === 'Scout' ? 'Scanner' : role === 'Technician' ? 'Setup Validator' : role === 'Newsdesk' ? 'News/Event Analyst' : role === 'Risk Manager' ? 'Risk Validator' : role === 'Planner' ? 'Entry Planner' : 'Fundamentalist')?.checks?.length || (role === 'Fundamentalist' ? fundamentals?.lights?.length || 0 : 0)}</p>{role === 'Fundamentalist' && <><button onClick={refreshFundamentals} disabled={loadingFundamentals} className="mt-2 rounded border border-slate-700 px-2 py-1 text-[10px] text-slate-300 disabled:opacity-50">{loadingFundamentals ? 'Fetching…' : fundamentals ? 'Refresh unofficial data' : 'Fetch unofficial data'}</button><label className="ml-2 inline-flex cursor-pointer rounded border border-slate-700 px-2 py-1 text-[10px] text-slate-300">Import owner CSV<input className="sr-only" type="file" accept=".csv,text/csv" onChange={importFundamentals}/></label>{importMessage && <p className="mt-1 text-[10px] text-slate-400">{importMessage}</p>}{fundamentals?.lights && <ul className="mt-2 space-y-1">{fundamentals.lights.map((light: any) => <li key={light.metric} title={`${light.why} Threshold: ${light.threshold}`} className="flex justify-between gap-2 text-[10px] text-slate-400"><span>{light.metric}</span><span className={light.status === 'UNKNOWN' ? 'text-slate-500' : light.status === 'RED' ? 'text-rose-300' : light.status === 'GREEN' ? 'text-emerald-300' : 'text-amber-300'}>{light.status}: {light.value}</span></li>)}</ul>}{fundamentals?.detail_url && <a className="mt-2 inline-block text-[10px] text-indigo-300 underline" href={fundamentals.detail_url} target="_blank" rel="noreferrer">More detail ↗</a>}</>}</details>; })}</div></div>)}
    </div>
    <p className="mt-3 text-[10px] text-slate-500">Bull and Bear use passed, failed and unknown checks. No analyst targets, upside estimates or probabilities.</p>
  </section>;
};
