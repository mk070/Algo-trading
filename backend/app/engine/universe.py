import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from pydantic import BaseModel

from app.settings import settings, DATA_DIR

logger = logging.getLogger(__name__)


class UniverseStock(BaseModel):
    symbol: str
    name: str
    sector: str
    industry: str
    market: str


class UniverseFilterResult(BaseModel):
    symbol: str
    passed: bool
    rejection_reasons: List[str]
    last_price: float
    avg_turnover: float
    atr_pct: float
    is_affordable: bool


class UniverseManager:
    """Manages constituent universes for IN (Nifty 100, Midcap 150) and US (S&P 500, S&P 400)."""

    def __init__(self):
        self.universe_dir = DATA_DIR / "universe"
        self.universe_dir.mkdir(parents=True, exist_ok=True)

    def load_universe(self, market: str = "IN") -> List[UniverseStock]:
        stocks: List[UniverseStock] = []
        seen = set()

        if market.upper() == "IN":
            files = ["nifty100.csv", "niftymidcap150.csv"]
        else:
            files = ["sp500.csv", "sp400.csv"]

        for f_name in files:
            path = self.universe_dir / f_name
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            sym = row.get("symbol", "").strip().upper()
                            if sym and sym not in seen:
                                seen.add(sym)
                                stocks.append(
                                    UniverseStock(
                                        symbol=sym,
                                        name=row.get("name", sym),
                                        sector=row.get("sector", "General"),
                                        industry=row.get("industry", "General"),
                                        market=market.upper(),
                                    )
                                )
                except Exception as e:
                    logger.error(f"Error reading universe file {path}: {e}")

        return stocks

    def filter_stock(
        self,
        symbol: str,
        df: pd.DataFrame,
        market: str = "IN",
        capital: Optional[float] = None,
    ) -> UniverseFilterResult:
        """Applies liquidity, price floor, volatility cap and affordability filters."""
        mkt_cfg = settings.get_market_config(market)
        risk_cfg = settings.get_risk_config()
        cap = capital or mkt_cfg.capital

        rejections = []
        if df is None or len(df) < 20:
            return UniverseFilterResult(
                symbol=symbol,
                passed=False,
                rejection_reasons=["Insufficient history (< 20 bars)"],
                last_price=0.0,
                avg_turnover=0.0,
                atr_pct=0.0,
                is_affordable=False,
            )

        last_row = df.iloc[-1]
        last_price = float(last_row["close"])

        # 1. Price floor
        if last_price < mkt_cfg.min_price:
            rejections.append(f"Price {last_price:.2f} below min price floor {mkt_cfg.min_price}")

        # 2. Liquidity (20-day average traded value = close * volume)
        turnover_20d = (df["close"].iloc[-20:] * df["volume"].iloc[-20:]).mean()
        if turnover_20d < mkt_cfg.min_avg_traded_value:
            rejections.append(
                f"Avg 20d turnover {turnover_20d:,.0f} below min {mkt_cfg.min_avg_traded_value:,.0f}"
            )

        # 3. Volatility Cap: ATR14 / price <= max_atr_pct (6%)
        atr = float(last_row.get("atr14", 0.0))
        atr_pct = (atr / last_price * 100.0) if last_price > 0 else 0.0
        if atr_pct > risk_cfg.max_atr_pct:
            rejections.append(
                f"ATR% {atr_pct:.2f}% exceeds max volatility cap {risk_cfg.max_atr_pct}%"
            )

        # 4. Affordability: 1 share <= max_share_price_pct_of_capital (25%) of capital
        max_share_price = cap * (risk_cfg.max_share_price_pct_of_capital / 100.0)
        is_affordable = last_price <= max_share_price
        if not is_affordable:
            rejections.append(
                f"Price {last_price:.2f} exceeds affordability cap {max_share_price:.2f} ({risk_cfg.max_share_price_pct_of_capital}% of capital)"
            )

        passed = len(rejections) == 0
        return UniverseFilterResult(
            symbol=symbol,
            passed=passed,
            rejection_reasons=rejections,
            last_price=last_price,
            avg_turnover=turnover_20d,
            atr_pct=atr_pct,
            is_affordable=is_affordable,
        )


universe_manager = UniverseManager()

