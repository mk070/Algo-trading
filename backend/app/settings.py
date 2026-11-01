import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"


class MarketConfig(BaseModel):
    enabled: bool = True
    currency: str = "INR"
    capital: float = 17500.0
    index_symbol: str = "^NSEI"
    universe: List[str] = ["NIFTY100", "NIFTYMIDCAP150"]
    min_avg_traded_value: float = 100000000.0
    min_price: float = 50.0
    tick: float = 0.05
    data_providers: List[str] = ["angelone", "yfinance"]
    max_open_positions: int = 2
    risk_per_trade_pct: float = 0.5
    max_portfolio_heat_pct: float = 2.0
    small_account_mode: Dict[str, Any] = {"enabled": False, "risk_per_trade_pct": 1.5, "max_portfolio_heat_pct": 3.0}
    slippage_pct: float = 0.10


class RiskConfig(BaseModel):
    risk_per_trade_pct: float = 0.5
    max_position_pct: float = 33.0
    max_portfolio_heat_pct: float = 2.0
    max_per_sector: int = 1
    corr_threshold: float = 0.75
    daily_new_trades_max: int = 2
    max_atr_pct: float = 6.0
    max_share_price_pct_of_capital: float = 25.0
    max_cost_in_R: float = 0.25


class RegimeConfig(BaseModel):
    block_new_entries: bool = True
    caution_size_mult: float = 0.5


class ScreenConfig(BaseModel):
    rs_lookback_days: int = 126
    rs_min_rank: float = 0.70
    top_n_per_market: int = 6
    valid_sessions: int = 1


class PullbackConfig(BaseModel):
    enabled: bool = False
    shadow_mode: bool = True
    ema_len: int = 20
    touch_tolerance: float = 1.01
    rsi_len: int = 14
    rsi_dip_below: float = 45.0
    swing_low_bars: int = 7
    trigger_atr_buffer: float = 0.1
    stop_atr_buffer: float = 0.2
    min_risk_atr: float = 1.0
    max_risk_atr: float = 3.0
    min_pullback_from_high55: float = 0.03


class TrendTemplateConfig(BaseModel):
    sma_fast: int = 50
    sma_mid: int = 150
    sma_slow: int = 200
    sma200_rising_bars: int = 21
    min_above_52w_low: float = 1.30
    max_below_52w_high: float = 0.25
    prefer_below_52w_high_v: float = 0.15
    rs_blend: List[float] = [0.5, 0.5]
    extension_ret21_max: float = 0.30
    max_above_sma50: float = 1.25


class VcpConfig(BaseModel):
    enabled: bool = True
    base_min_bars: int = 15
    base_max_bars: int = 40
    max_base_depth_pct: float = 20.0
    atr_contraction_ratio: float = 0.85
    min_contractions: int = 2
    tight_5d_pct: float = 5.0
    volume_dryup_ratio: float = 0.9
    pivot_proximity_pct: float = 3.0
    approach_pct: float = 1.5
    trigger_atr_buffer: float = 0.1
    entry_zone_atr: float = 0.5
    stop_bars: int = 10
    stop_atr_buffer: float = 0.2
    min_risk_atr: float = 1.0
    max_risk_atr: float = 2.5
    max_stop_pct: float = 8.0
    min_rr_to_resistance: float = 1.5
    volume_pace_min: float = 1.5
    confirm_timeframe_min: int = 15
    require_contraction: bool = True
    chase_limit_atr: float = 1.0


class ExitConfig(BaseModel):
    breakeven_at_R: float = 1.0
    trail_atr_mult: float = 3.0
    partial_at_R: float = 2.0
    partial_fraction: float = 0.5
    trend_break_sma: int = 50
    time_stop_sessions: int = 15
    time_stop_min_R: float = 0.5


class NewsConfig(BaseModel):
    earnings_block_days: int = 7
    earnings_warn_trading_days: int = 2
    block_on_red: bool = True
    unknown_policy: str = "warn"
    dedupe_window_hours: int = 48
    max_source_age_min: int = 60
    macro_event_caution: bool = True
    ai_summaries: Dict[str, Any] = {"enabled": False, "monthly_budget_usd": 0}


class MonitorConfig(BaseModel):
    mode: str = "websocket"
    polling_interval_sec: int = 30
    heartbeat_timeout_sec: int = 30
    reconnect_backoff_sec: List[int] = [1, 2, 5, 10, 30]
    freshness: Dict[str, Any] = {
        "websocket_tick_max_age_sec": 20,
        "rest_quote_max_age_sec": 60,
        "persistent_stale_alert_sec": 120,
        "clock_skew_warn_sec": 2,
        "delayed_feed_policy": "informational_only",
    }


class CostModelConfig(BaseModel):
    preset: str = "zerodha"
    brokerage: Dict[str, Any] = {"type": "flat", "flat": 0}
    stt_pct_buy: float = 0.1
    stt_pct_sell: float = 0.1
    exchange_txn_pct: float = 0.003
    sebi_per_crore: float = 10.0
    stamp_buy_pct: float = 0.015
    dp_flat_per_scrip_sell: float = 13.5
    gst_pct: float = 18.0
    commission_per_order: float = 0.0
    regulatory_pct: float = 0.003
    fx_spread_pct: float = 0.5
    fixed_per_trade: float = 0.0


class PortfolioConfig(BaseModel):
    provider: str = "kite_personal"
    sync_interval_min: int = 5
    capital_source: str = "manual"
    swing_capital_cap: float = 17500.0
    auto_track_unmatched_holdings: bool = False
    import_zerodha_csv: bool = True


class AppSettings(BaseSettings):
    # App Auth & Basic Config
    app_token: str = Field(default="demo-token-change-in-prod", alias="APP_TOKEN")
    env: str = Field(default="development", alias="ENV")
    database_url: str = Field(
        default="postgresql://neondb_owner:YOUR_PASSWORD@ep-sample-123456.us-east-2.aws.neon.tech/neondb?sslmode=require",
        alias="DATABASE_URL"
    )
    database_url_unpooled: Optional[str] = Field(default=None, alias="DATABASE_URL_UNPOOLED")

    # Neon Cloud Services (Auth, Realtime, Branch)
    neon_branch: Optional[str] = Field(default=None, alias="NEON_BRANCH")
    neon_auth_base_url: Optional[str] = Field(default=None, alias="NEON_AUTH_BASE_URL")
    neon_auth_jwks_url: Optional[str] = Field(default=None, alias="NEON_AUTH_JWKS_URL")
    neon_realtime_url: Optional[str] = Field(default=None, alias="NEON_REALTIME_URL")
    neon_realtime_secret: Optional[str] = Field(default=None, alias="NEON_REALTIME_SECRET")

    @property
    def normalized_database_url(self) -> str:
        """Converts postgres:// or postgresql:// to postgresql+psycopg2:// for SQLAlchemy.
        Strictly rejects SQLite per architecture requirements.
        """
        url = (self.database_url or "").strip()
        if not url or url.startswith("sqlite"):
            raise ValueError(
                "SQLite is strictly not supported. Neon PostgreSQL is the exclusive database platform. "
                "Please configure a valid Neon PostgreSQL connection string in DATABASE_URL."
            )
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    @property
    def normalized_unpooled_database_url(self) -> str:
        """Direct (unpooled) PostgreSQL URL for schema migrations (Alembic) and DDL."""
        raw = (self.database_url_unpooled or self.database_url or "").strip()
        if not raw or raw.startswith("sqlite"):
            return self.normalized_database_url
        if raw.startswith("postgres://"):
            raw = raw.replace("postgres://", "postgresql+psycopg2://", 1)
        elif raw.startswith("postgresql://") and not raw.startswith("postgresql+"):
            raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)
        return raw
    
    # Angel One SmartAPI (Core Market Data)
    angelone_api_key: Optional[str] = Field(default=None, alias="ANGELONE_API_KEY")
    angelone_client_code: Optional[str] = Field(default=None, alias="ANGELONE_CLIENT_CODE")
    angelone_pin: Optional[str] = Field(default=None, alias="ANGELONE_PIN")
    angelone_totp_secret: Optional[str] = Field(default=None, alias="ANGELONE_TOTP_SECRET")

    # Zerodha Kite Connect Personal (Core Read-only Portfolio)
    kite_api_key: Optional[str] = Field(default=None, alias="KITE_API_KEY")
    kite_api_secret: Optional[str] = Field(default=None, alias="KITE_API_SECRET")
    kite_redirect_url: str = Field(
        default="http://127.0.0.1:8000/api/portfolio/kite/callback",
        alias="KITE_REDIRECT_URL",
    )
    kite_access_token: Optional[str] = Field(default=None, alias="KITE_ACCESS_TOKEN")

    # US Provider (Alpaca candidate)
    alpaca_api_key: Optional[str] = Field(default=None, alias="ALPACA_API_KEY")
    alpaca_secret_key: Optional[str] = Field(default=None, alias="ALPACA_SECRET_KEY")
    alpaca_endpoint: str = Field(default="https://paper-api.alpaca.markets", alias="ALPACA_ENDPOINT")

    # Notifications
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")

    # News & Regulatory Disclosures
    sec_user_agent: str = Field(
        default="AlgoTrading Research research@example.com",
        alias="SEC_USER_AGENT"
    )
    finnhub_api_key: Optional[str] = Field(default=None, alias="FINNHUB_API_KEY")

    # Strategy / Risk / Engine configs from YAML
    strategy_config: Dict[str, Any] = Field(default_factory=dict)
    news_rules: Dict[str, Any] = Field(default_factory=dict)
    news_sources: Dict[str, Any] = Field(default_factory=dict)
    macro_calendar: Dict[str, Any] = Field(default_factory=dict)

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def load_yaml_configs(self):
        strategy_file = CONFIG_DIR / "strategy.yaml"
        if strategy_file.exists():
            with open(strategy_file, "r", encoding="utf-8") as f:
                self.strategy_config = yaml.safe_load(f) or {}

        news_rules_file = CONFIG_DIR / "news_rules.yaml"
        if news_rules_file.exists():
            with open(news_rules_file, "r", encoding="utf-8") as f:
                self.news_rules = yaml.safe_load(f) or {}

        news_sources_file = CONFIG_DIR / "news_sources.yaml"
        if news_sources_file.exists():
            with open(news_sources_file, "r", encoding="utf-8") as f:
                self.news_sources = yaml.safe_load(f) or {}

        macro_cal_file = CONFIG_DIR / "macro_calendar.yaml"
        if macro_cal_file.exists():
            with open(macro_cal_file, "r", encoding="utf-8") as f:
                self.macro_calendar = yaml.safe_load(f) or {}

    def get_market_config(self, market: str) -> MarketConfig:
        mkts = self.strategy_config.get("markets", {})
        mkt_dict = mkts.get(market.upper(), {})
        return MarketConfig(**mkt_dict) if mkt_dict else MarketConfig()

    def get_cost_config(self, market: str) -> CostModelConfig:
        costs = self.strategy_config.get("costs", {})
        mkt_costs = costs.get(market.upper(), {})
        return CostModelConfig(**mkt_costs) if mkt_costs else CostModelConfig()

    def get_risk_config(self) -> RiskConfig:
        r = self.strategy_config.get("risk", {})
        return RiskConfig(**r) if r else RiskConfig()

    def get_vcp_config(self) -> VcpConfig:
        v = self.strategy_config.get("vcp", {})
        return VcpConfig(**v) if v else VcpConfig()

    def get_pullback_config(self) -> PullbackConfig:
        p = self.strategy_config.get("pullback", {})
        return PullbackConfig(**p) if p else PullbackConfig()

    def get_trend_template_config(self) -> TrendTemplateConfig:
        t = self.strategy_config.get("trend_template", {})
        return TrendTemplateConfig(**t) if t else TrendTemplateConfig()

    def get_exit_config(self) -> ExitConfig:
        e = self.strategy_config.get("exits", {})
        return ExitConfig(**e) if e else ExitConfig()

    def get_news_config(self) -> NewsConfig:
        n = self.strategy_config.get("news", {})
        return NewsConfig(**n) if n else NewsConfig()

    def get_monitor_config(self) -> MonitorConfig:
        m = self.strategy_config.get("monitor", {})
        return MonitorConfig(**m) if m else MonitorConfig()

    def get_portfolio_config(self) -> PortfolioConfig:
        p = self.strategy_config.get("portfolio", {})
        return PortfolioConfig(**p) if p else PortfolioConfig()

    def get_news_sources_config(self) -> Dict[str, Any]:
        return self.news_sources.get("sources", {})

    def get_macro_calendar(self) -> Dict[str, Any]:
        return self.macro_calendar


settings = AppSettings()
settings.load_yaml_configs()

