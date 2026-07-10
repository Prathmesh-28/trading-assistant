"""All settings, loaded from .env — no other module reads os.environ directly."""

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_WATCHLIST = (
    "RELIANCE,HDFCBANK,ICICIBANK,INFY,TCS,SBIN,TATAMOTORS,LT,AXISBANK,BHARTIARTL"
)


def _s(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _b(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Groww (data + optional orders)
    groww_api_key: str = field(default_factory=lambda: _s("GROWW_API_KEY"))
    groww_api_secret: str = field(default_factory=lambda: _s("GROWW_API_SECRET"))
    groww_totp_secret: str = field(default_factory=lambda: _s("GROWW_TOTP_SECRET"))

    # Telegram (phone alerts); blank -> console fallback
    telegram_token: str = field(default_factory=lambda: _s("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _s("TELEGRAM_CHAT_ID"))

    # Dashboard login (web UI + API). Override in production via env.
    auth_username: str = field(default_factory=lambda: _s("AUTH_USERNAME", "prathmesh"))
    auth_password: str = field(default_factory=lambda: _s("AUTH_PASSWORD", "trade@2026"))

    # Universe + risk
    watchlist: list = field(
        default_factory=lambda: [
            s.strip().upper() for s in _s("WATCHLIST", DEFAULT_WATCHLIST).split(",") if s.strip()
        ]
    )
    capital: float = field(default_factory=lambda: _f("CAPITAL", 100_000.0))
    risk_per_trade_pct: float = field(default_factory=lambda: _f("RISK_PER_TRADE_PCT", 0.5))
    max_position_value: float = field(default_factory=lambda: _f("MAX_POSITION_VALUE", 50_000.0))
    allow_shorts: bool = field(default_factory=lambda: _b("ALLOW_SHORTS", False))

    # One-tap execution: when true, the engine may place REAL orders through
    # Groww when (and only when) you explicitly tell it to — per idea, per
    # exit, or per manual ticket. Recommend-only remains the default. In
    # synthetic/demo mode orders are always paper-filled regardless.
    execute_enabled: bool = field(default_factory=lambda: _b("EXECUTE_ENABLED", False))

    # Circuit breaker: pause NEW ideas for the day once realized+open loss
    # exceeds this % of equity (monitoring of open positions continues).
    daily_loss_limit_pct: float = field(default_factory=lambda: _f("DAILY_LOSS_LIMIT_PCT", 3.0))

    # Portfolio-level risk (Van Tharp / Turtle heat caps): cap concurrent
    # positions and total open risk (sum of entry-to-stop risk across open
    # positions) as % of capital, on top of per-trade sizing above.
    max_open_positions: int = field(default_factory=lambda: _i("MAX_OPEN_POSITIONS", 6))
    max_portfolio_risk_pct: float = field(default_factory=lambda: _f("MAX_PORTFOLIO_RISK_PCT", 6.0))

    # Index regime gate (Faber 200-DMA rule): positional entries only while
    # this NSE-tradeable index proxy closes above its 200-day SMA. NIFTYBEES
    # is the Nifty 50 ETF, so it flows through the normal equity data path.
    index_symbol: str = field(default_factory=lambda: _s("INDEX_SYMBOL", "NIFTYBEES"))

    # Backtest slippage assumption, % of turnover per side
    slippage_pct: float = field(default_factory=lambda: _f("SLIPPAGE_PCT", 0.05))

    # Intraday strategy
    poll_seconds: int = field(default_factory=lambda: _i("POLL_SECONDS", 20))
    # Paper defaults (SSRN 4729284): OR = first 5-min bar, target = 2R
    orb_minutes: int = field(default_factory=lambda: _i("ORB_MINUTES", 5))
    bar_minutes: int = field(default_factory=lambda: _i("BAR_MINUTES", 5))
    risk_reward: float = field(default_factory=lambda: _f("RISK_REWARD", 2.0))

    # Journal: sqlite file by default; set DATABASE_URL for Postgres (see journal.py)
    database_url: str = field(default_factory=lambda: _s("DATABASE_URL"))
    journal_path: str = field(default_factory=lambda: _s("JOURNAL_PATH", "journal.db"))

    # Execute mode only
    live: bool = field(default_factory=lambda: _b("LIVE", False))

    @property
    def has_groww(self) -> bool:
        return bool(self.groww_api_key and self.groww_totp_secret)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)
