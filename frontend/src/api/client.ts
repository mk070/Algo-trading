import { BacktestMetrics, JournalEntry, Position, Signal, TradePlan } from '../types';

const API_BASE = '/api';

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

  async getBars(symbol: string, market: string = 'IN', n: number = 250) {
    const res = await fetch(`${API_BASE}/bars/${symbol}?market=${market}&n=${n}`);
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
    const url = symbol ? `${API_BASE}/news?symbol=${symbol}&days=${days}` : `${API_BASE}/news?days=${days}`;
    const res = await fetch(url);
    return res.json();
  },

  async getNewsSourcesHealth() {
    const res = await fetch(`${API_BASE}/news/sources/health`);
    return res.json();
  },

  async getMacroCalendar() {
    const res = await fetch(`${API_BASE}/news/macro`);
    return res.json();
  },

  async getCoverageGaps() {
    const res = await fetch(`${API_BASE}/news/coverage-gaps`);
    return res.json();
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
};

