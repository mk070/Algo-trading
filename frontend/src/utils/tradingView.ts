export function tradingViewChartUrl(symbol: string, market: string) {
  const clean = symbol.trim().replace(/^(NSE|BSE|NASDAQ|NYSE):/i, '');
  const tvSymbol = market === 'IN' ? `NSE:${clean}` : symbol.trim();
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;
}
