import { BacktestMetrics, JournalEntry, Position, Signal, TradePlan } from '../types';

const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, '');
export const API_BASE = (configuredApiBase && !configuredApiBase.includes('127.0.0.1') && !configuredApiBase.includes('localhost'))
  ? `${configuredApiBase.endsWith('/api') ? configuredApiBase.slice(0, -4) : configuredApiBase}/api`
  : (import.meta.env.PROD ? 'https://algo-trading-g9j5.onrender.com/api' : (configuredApiBase ? `${configuredApiBase}/api` : 'http://127.0.0.1:8000/api'));

export async function fetchJson<T = any>(url: string, init?: RequestInit): Promise<T> {
  // Deliberately session-only: production API credentials must not be compiled
  // into Vite output or persisted beyond an active browser session.
  const token = sessionStorage.getItem('algo_trading_api_token');
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    let detail = '';
    try {
      const parsed = JSON.parse(text);
      detail = parsed.detail || parsed.message || `Server returned ${res.status}`;
    } catch {
      if (text.includes('<!DOCTYPE') || text.includes('<html') || text.includes('The page could not be found')) {
        detail = `Backend API unreachable (${res.status} Not Found at ${url}). If hosted on Vercel, please set VITE_API_BASE_URL to your active FastAPI backend server.`;
      } else {
        detail = `Server returned ${res.status}: ${text.slice(0, 120)}`;
      }
    }
    throw new Error(detail);
  }
  const contentType = res.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const text = await res.text();
    if (text.includes('<!DOCTYPE') || text.includes('<html')) {
      throw new Error(`API returned HTML instead of JSON. Ensure VITE_API_BASE_URL points to the FastAPI backend.`);
    }
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`Invalid JSON received: ${text.slice(0, 100)}`);
    }
  }
  return res.json();
}

export interface CandleBar {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20?: number | null;
  ema50?: number | null;
  sma50?: number | null;
  sma150?: number | null;
  sma200?: number | null;
  rsi14?: number | null;
  atr14?: number | null;
}

export interface TrendTemplateRule {
  rule: string;
  passed: boolean;
  actual: string;
  expected: string;
}

export interface StrategyOverlay {
  signal_id?: number;
  setup: string;
  trigger: number;
  entry_zone_high: number;
  stop: number;
  target1: number;
  target2?: number | null;
  state: string;
  rs_rank?: number | null;
  atr?: number | null;
  reasons: string[];
  vcp_base?: {
    base_bars: number;
    start_time: string | number;
    end_time: string | number;
    base_high: number;
    base_low: number;
    pivot: number;
  } | null;
  trend_template?: TrendTemplateRule[];
}

export interface BarsResponse {
  symbol: string;
  market: string;
  timeframe: string;
  provider: string;
  feed_status: 'LIVE' | 'DELAYED' | 'STALE' | 'DISCONNECTED';
  last_quote_time?: string | null;
  current_price?: number | null;
  bars: CandleBar[];
  strategy_overlay?: StrategyOverlay | null;
}

export const apiClient = {
  async getHealth() {
    return fetchJson(`${API_BASE}/health`);
  },

  async getRegime(market: string = 'IN') {
    return fetchJson(`${API_BASE}/regime?market=${market}`);
  },

  async getTradePlan(market: string = 'IN', date?: string): Promise<TradePlan> {
    const url = date ? `${API_BASE}/plan?market=${market}&date=${date}` : `${API_BASE}/plan?market=${market}`;
    return fetchJson<TradePlan>(url);
  },

  async runScan(market: string = 'IN'): Promise<TradePlan> {
    return fetchJson<TradePlan>(`${API_BASE}/scan/run?market=${market}`, { method: 'POST' });
  },

  async getSignalDetail(id: number): Promise<Signal> {
    return fetchJson<Signal>(`${API_BASE}/signals/${id}`);
  },

  async getWatchlist(market: string = 'IN') {
    return fetchJson(`${API_BASE}/watchlist?market=${market}`);
  },

  async getWatchlists(market: string = 'IN') {
    return fetchJson(`${API_BASE}/watchlists?market=${market}`);
  },

  async createWatchlist(name: string, market: string = 'IN') {
    return fetchJson(`${API_BASE}/watchlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, market }),
    });
  },

  async deleteWatchlist(id: number) {
    return fetchJson(`${API_BASE}/watchlists/${id}`, { method: 'DELETE' });
  },

  async getWatchlistItems(watchlistId: number) {
    return fetchJson(`${API_BASE}/watchlists/${watchlistId}/items`);
  },

  async addWatchlistItem(watchlistId: number, data: { symbol: string; notes?: string; source?: string }) {
    return fetchJson(`${API_BASE}/watchlists/${watchlistId}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async removeWatchlistItem(watchlistId: number, itemId: number) {
    return fetchJson(`${API_BASE}/watchlists/${watchlistId}/items/${itemId}`, { method: 'DELETE' });
  },

  async importWatchlistSymbols(watchlistId: number, rawText: string, sourceTag: string = 'MANUAL_IMPORT') {
    return fetchJson(`${API_BASE}/watchlists/${watchlistId}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText, source_tag: sourceTag }),
    });
  },

  async getQuotes(symbols: string[], market: string = 'IN'): Promise<Record<string, any>> {
    return fetchJson<Record<string, any>>(`${API_BASE}/quotes?symbols=${encodeURIComponent(symbols.join(','))}&market=${market}`);
  },

  async getBars(symbol: string, market: string = 'IN', tfOrN: string | number = '1d', n: number = 600): Promise<BarsResponse> {
    const tf = typeof tfOrN === 'string' ? tfOrN : '1d';
    const limit = typeof tfOrN === 'number' ? tfOrN : n;
    return fetchJson<BarsResponse>(`${API_BASE}/bars/${symbol}?market=${market}&tf=${tf}&n=${limit}`);
  },

  async getPositions(status: string = 'OPEN', market?: string): Promise<Position[]> {
    const url = market ? `${API_BASE}/positions?status=${status}&market=${market}` : `${API_BASE}/positions?status=${status}`;
    return fetchJson<Position[]>(url);
  },

  async createPosition(data: {
    symbol: string;
    market: string;
    entry_price: number;
    qty: number;
    initial_stop: number;
    target1: number;
    signal_id?: number;
    mode?: string;
    notes?: string;
  }) {
    return fetchJson(`${API_BASE}/positions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async updatePosition(id: number, data: { active_stop?: number; target1?: number; notes?: string }) {
    return fetchJson(`${API_BASE}/positions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async closePosition(id: number, data: { exit_price: number; exit_reason: string; qty?: number; note?: string }) {
    return fetchJson(`${API_BASE}/positions/${id}/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async getJournal(): Promise<JournalEntry[]> {
    return fetchJson<JournalEntry[]>(`${API_BASE}/journal`);
  },

  async getStats() {
    return fetchJson(`${API_BASE}/stats`);
  },

  async getPortfolioValuation() {
    return fetchJson(`${API_BASE}/portfolio/valuation`);
  },

  async getPortfolioStatus() {
    return fetchJson(`${API_BASE}/portfolio/status`);
  },

  async syncPortfolio() {
    return fetchJson(`${API_BASE}/portfolio/sync`, { method: 'POST' });
  },

  async getKiteLoginUrl() {
    return fetchJson(`${API_BASE}/portfolio/kite/login-url`);
  },

  async runBacktest(params: {
    market: string;
    start_date?: string;
    end_date?: string;
    capital?: number;
    setup_filter?: string;
  }) {
    return fetchJson(`${API_BASE}/backtests`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  },

  async getNews(symbol?: string, days: number = 14, market?: string) {
    try {
      const params = new URLSearchParams();
      if (symbol) params.append('symbol', symbol);
      if (days) params.append('days', days.toString());
      if (market) params.append('market', market);
      const res = await fetch(`${API_BASE}/news?${params.toString()}`);
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  },

  async refreshNews(market: string = 'IN') {
    try {
      const res = await fetch(`${API_BASE}/news/refresh?market=${market}`, {
        method: 'POST',
      });
      return await res.json();
    } catch (e) {
      console.error('Error refreshing news:', e);
      return { status: 'ERROR', message: String(e) };
    }
  },

  async getNewsSourcesHealth() {
    try {
      const res = await fetch(`${API_BASE}/news/sources/health`);
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  },

  async getMacroCalendar() {
    try {
      const res = await fetch(`${API_BASE}/news/macro`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  },

  async getCoverageGaps() {
    try {
      const res = await fetch(`${API_BASE}/news/coverage-gaps`);
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  },

  async getSettings() {
    return fetchJson(`${API_BASE}/settings`);
  },

  async updateSettings(data: any) {
    return fetchJson(`${API_BASE}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async getAlerts() {
    return fetchJson(`${API_BASE}/alerts`);
  },

  async ackAlert(id: number) {
    return fetchJson(`${API_BASE}/alerts/${id}/ack`, { method: 'POST' });
  },

  async runScenarioLab(params: {
    symbol: string;
    market?: string;
    trigger: number;
    stop: number;
    asof_date?: string;
    n_simulations?: number;
    seed?: number;
  }) {
    return fetchJson(`${API_BASE}/scenario-lab`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
  },

  async getEarningsAnalysis(symbol: string, market: string = 'IN') {
    return fetchJson(`${API_BASE}/earnings/analysis?symbol=${symbol}&market=${market}`);
  },

  async getDecisionAudits(symbol?: string, market: string = 'IN') {
    const url = symbol ? `${API_BASE}/decision-audits?symbol=${symbol}&market=${market}` : `${API_BASE}/decision-audits?market=${market}`;
    return fetchJson(url);
  },

  async getFundamentalLights(symbol: string, market: string = 'IN') {
    return fetchJson(`${API_BASE}/fundamental-lights/${encodeURIComponent(symbol)}?market=${market}`);
  },

  async getLeadTime(market: string = 'IN') {
    return fetchJson(`${API_BASE}/research/lead-time?market=${market}&sessions=60`);
  },

  async getFundamentalOutcomes(market: string = 'IN') {
    return fetchJson(`${API_BASE}/research/fundamental-outcomes?market=${market}`);
  },

  async getPivotImpact(market: string = 'IN') {
    return fetchJson(`${API_BASE}/research/pivot-impact?market=${market}&sessions=60`);
  },

  async getValueRadar(market: string = 'IN') {
    return fetchJson(`${API_BASE}/value-radar?market=${market}`);
  },

  async importFundamentalsCsv(file: File) {
    const form = new FormData();
    form.append('file', file);
    return fetchJson(`${API_BASE}/fundamentals/import-csv`, { method: 'POST', body: form });
  },

  async getNeonServices() {
    try {
      return await fetchJson(`${API_BASE}/neon/services`);
    } catch {
      return null;
    }
  },

  async getTelegramStatus() {
    return fetchJson(`${API_BASE}/telegram/status`);
  },

  async testTelegram() {
    return fetchJson(`${API_BASE}/telegram/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
  },

  async getMarketPulse(market: string = 'IN') {
    return fetchJson(`${API_BASE}/market/pulse?market=${market}`);
  },

  async searchSymbols(query: string, market: string = 'IN') {
    return fetchJson(`${API_BASE}/search?q=${encodeURIComponent(query)}&market=${market}`);
  },

  async getCustomAlerts(market?: string, activeOnly?: boolean) {
    let url = `${API_BASE}/alerts/custom`;
    const params = new URLSearchParams();
    if (market) params.append('market', market);
    if (activeOnly) params.append('active_only', 'true');
    const qs = params.toString();
    if (qs) url += `?${qs}`;
    return fetchJson(url);
  },

  async createCustomAlert(data: {
    symbol: string;
    market: string;
    target_price: number;
    condition: string;
    notes?: string;
  }) {
    return fetchJson(`${API_BASE}/alerts/custom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async deleteCustomAlert(id: number) {
    return fetchJson(`${API_BASE}/alerts/custom/${id}`, {
      method: 'DELETE',
    });
  },
};
