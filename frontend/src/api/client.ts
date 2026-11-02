import { BacktestMetrics, JournalEntry, Position, Signal, TradePlan } from '../types';

const API_BASE = '/api';

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
    const res = await fetch(`${API_BASE}/health`);
    return res.json();
  },

  async getRegime(market: string = 'IN') {
    const res = await fetch(`${API_BASE}/regime?market=${market}`);
    return res.json();
  },

  async getTradePlan(market: string = 'IN', date?: string): Promise<TradePlan> {
    const url = date ? `${API_BASE}/plan?market=${market}&date=${date}` : `${API_BASE}/plan?market=${market}`;
    const res = await fetch(url);
    return res.json();
  },

  async runScan(market: string = 'IN'): Promise<TradePlan> {
    const res = await fetch(`${API_BASE}/scan/run?market=${market}`, { method: 'POST' });
    return res.json();
  },

  async getSignalDetail(id: number): Promise<Signal> {
    const res = await fetch(`${API_BASE}/signals/${id}`);
    return res.json();
  },

  async getWatchlist(market: string = 'IN') {
    const res = await fetch(`${API_BASE}/watchlist?market=${market}`);
    return res.json();
  },

  async getWatchlists(market: string = 'IN') {
    const res = await fetch(`${API_BASE}/watchlists?market=${market}`);
    return res.json();
  },

  async createWatchlist(name: string, market: string = 'IN') {
    const res = await fetch(`${API_BASE}/watchlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, market }),
    });
    return res.json();
  },

  async deleteWatchlist(id: number) {
    const res = await fetch(`${API_BASE}/watchlists/${id}`, { method: 'DELETE' });
    return res.json();
  },

  async getWatchlistItems(watchlistId: number) {
    const res = await fetch(`${API_BASE}/watchlists/${watchlistId}/items`);
    return res.json();
  },

  async addWatchlistItem(watchlistId: number, data: { symbol: string; notes?: string; source?: string }) {
    const res = await fetch(`${API_BASE}/watchlists/${watchlistId}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async removeWatchlistItem(watchlistId: number, itemId: number) {
    const res = await fetch(`${API_BASE}/watchlists/${watchlistId}/items/${itemId}`, { method: 'DELETE' });
    return res.json();
  },

  async importWatchlistSymbols(watchlistId: number, rawText: string, sourceTag: string = 'MANUAL_IMPORT') {
    const res = await fetch(`${API_BASE}/watchlists/${watchlistId}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: rawText, source_tag: sourceTag }),
    });
    return res.json();
  },

  async getBars(symbol: string, market: string = 'IN', tfOrN: string | number = '1d', n: number = 250): Promise<BarsResponse> {
    const tf = typeof tfOrN === 'string' ? tfOrN : '1d';
    const limit = typeof tfOrN === 'number' ? tfOrN : n;
    const res = await fetch(`${API_BASE}/bars/${symbol}?market=${market}&tf=${tf}&n=${limit}`);
    if (!res.ok) {
      const errText = await res.text();
      try {
        const errJson = JSON.parse(errText);
        throw new Error(errJson.detail || `Server returned ${res.status}`);
      } catch {
        throw new Error(`Server returned ${res.status}: ${errText.slice(0, 100)}`);
      }
    }
    return res.json();
  },

  async getPositions(status: string = 'OPEN', market?: string): Promise<Position[]> {
    const url = market ? `${API_BASE}/positions?status=${status}&market=${market}` : `${API_BASE}/positions?status=${status}`;
    const res = await fetch(url);
    return res.json();
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
    const res = await fetch(`${API_BASE}/positions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updatePosition(id: number, data: { active_stop?: number; target1?: number; notes?: string }) {
    const res = await fetch(`${API_BASE}/positions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async closePosition(id: number, data: { exit_price: number; exit_reason: string; qty?: number; note?: string }) {
    const res = await fetch(`${API_BASE}/positions/${id}/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async getJournal(): Promise<JournalEntry[]> {
    const res = await fetch(`${API_BASE}/journal`);
    return res.json();
  },

  async getStats() {
    const res = await fetch(`${API_BASE}/stats`);
    return res.json();
  },

  async getPortfolioValuation() {
    const res = await fetch(`${API_BASE}/portfolio/valuation`);
    return res.json();
  },

  async getPortfolioStatus() {
    const res = await fetch(`${API_BASE}/portfolio/status`);
    return res.json();
  },

  async syncPortfolio() {
    const res = await fetch(`${API_BASE}/portfolio/sync`, { method: 'POST' });
    return res.json();
  },

  async getKiteLoginUrl() {
    const res = await fetch(`${API_BASE}/portfolio/kite/login-url`);
    return res.json();
  },

  async runBacktest(params: {
    market: string;
    start_date?: string;
    end_date?: string;
    capital?: number;
    setup_filter?: string;
  }) {
    const res = await fetch(`${API_BASE}/backtests`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return res.json();
  },

  async getNews(symbol?: string, days: number = 14) {
    try {
      const url = symbol ? `${API_BASE}/news?symbol=${symbol}&days=${days}` : `${API_BASE}/news?days=${days}`;
      const res = await fetch(url);
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
    const res = await fetch(`${API_BASE}/settings`);
    return res.json();
  },

  async updateSettings(data: any) {
    const res = await fetch(`${API_BASE}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async getAlerts() {
    const res = await fetch(`${API_BASE}/alerts`);
    return res.json();
  },

  async ackAlert(id: number) {
    const res = await fetch(`${API_BASE}/alerts/${id}/ack`, { method: 'POST' });
    return res.json();
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
    const res = await fetch(`${API_BASE}/scenario-lab`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return res.json();
  },

  async getEarningsAnalysis(symbol: string, market: string = 'IN') {
    const res = await fetch(`${API_BASE}/earnings/analysis?symbol=${symbol}&market=${market}`);
    return res.json();
  },

  async getDecisionAudits(symbol?: string, market: string = 'IN') {
    const url = symbol ? `${API_BASE}/decision-audits?symbol=${symbol}&market=${market}` : `${API_BASE}/decision-audits?market=${market}`;
    const res = await fetch(url);
    return res.json();
  },

  async getNeonServices() {
    try {
      const res = await fetch(`${API_BASE}/neon/services`);
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  },

  async getTelegramStatus() {
    const res = await fetch(`${API_BASE}/telegram/status`);
    if (!res.ok) {
      throw new Error(`Failed to fetch Telegram status: ${res.statusText}`);
    }
    return res.json();
  },

  async testTelegram() {
    const res = await fetch(`${API_BASE}/telegram/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to send Telegram test message');
    }
    return data;
  },

  async getMarketPulse(market: string = 'IN') {
    const res = await fetch(`${API_BASE}/market/pulse?market=${market}`);
    return res.json();
  },

  async searchSymbols(query: string, market: string = 'IN') {
    const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}&market=${market}`);
    return res.json();
  },

  async getCustomAlerts(market?: string, activeOnly?: boolean) {
    let url = `${API_BASE}/alerts/custom`;
    const params = new URLSearchParams();
    if (market) params.append('market', market);
    if (activeOnly) params.append('active_only', 'true');
    const qs = params.toString();
    if (qs) url += `?${qs}`;
    const res = await fetch(url);
    return res.json();
  },

  async createCustomAlert(data: {
    symbol: string;
    market: string;
    target_price: number;
    condition: string;
    notes?: string;
  }) {
    const res = await fetch(`${API_BASE}/alerts/custom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to create alert');
    }
    return res.json();
  },

  async deleteCustomAlert(id: number) {
    const res = await fetch(`${API_BASE}/alerts/custom/${id}`, {
      method: 'DELETE',
    });
    return res.json();
  },
};

