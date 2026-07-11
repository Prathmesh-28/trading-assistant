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
    # Optional: sha256 hex of the password. When set, it wins over the
    # plaintext field so the real secret never sits in env. Generate with:
    #   python -c "import hashlib;print(hashlib.sha256(b'yourpass').hexdigest())"
    auth_password_hash: str = field(default_factory=lambda: _s("AUTH_PASSWORD_HASH"))

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

    # Cap on how many fresh ideas the engine emits per calendar day (0 = no
    # cap). Guards against overtrading on a busy signal day.
    max_ideas_per_day: int = field(default_factory=lambda: _i("MAX_IDEAS_PER_DAY", 0))

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

    # Fundamental gate for POSITIONAL (multi-week) ideas — quality filter on
    # top of the technical setup. Off by default (needs fundamentals data);
    # fails OPEN when a symbol's fundamentals are unavailable.
    fundamental_gate_enabled: bool = field(default_factory=lambda: _b("FUNDAMENTAL_GATE", False))
    min_fundamental_score: float = field(default_factory=lambda: _f("MIN_FUNDAMENTAL_SCORE", 45))
    max_fundamental_de: float = field(default_factory=lambda: _f("MAX_FUNDAMENTAL_DE", 200))

    # screener.in scraping (operator-owned ToS decision; default OFF). When
    # on, fundamentals prefer screener.in and fall back to yfinance.
    screener_scrape_enabled: bool = field(default_factory=lambda: _b("SCREENER_SCRAPE_ENABLED", False))

    # Control-center toggles: mute all Telegram pushes without stopping the
    # engine; disable individual strategies by keyword (matched vs idea reason).
    alerts_muted: bool = field(default_factory=lambda: _b("ALERTS_MUTED", False))
    disabled_strategies: list = field(default_factory=lambda: [
        s.strip().lower() for s in _s("DISABLED_STRATEGIES").split(",") if s.strip()
    ])

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

    def validate(self) -> list:
        """Boot-time sanity check. Returns a list of human-readable warnings
        (empty = all good); never raises — the app must still start degraded."""
        warns = []
        if self.auth_password == "trade@2026" and not self.auth_password_hash:
            warns.append("AUTH_PASSWORD is the shipped default — change it in production")
        if not (0.05 <= self.risk_per_trade_pct <= 5.0):
            warns.append(f"risk_per_trade_pct={self.risk_per_trade_pct} outside 0.05-5.0")
        if self.capital <= 0:
            warns.append(f"capital={self.capital} must be positive")
        if self.max_open_positions < 1:
            warns.append("max_open_positions < 1 blocks all trading")
        if self.execute_enabled and not self.has_groww:
            warns.append("execute_enabled but no Groww creds — orders will fail")
        if not self.has_telegram:
            warns.append("no Telegram creds — phone alerts go to console only")
        return warns

    @property
    def has_groww(self) -> bool:
        return bool(self.groww_api_key and self.groww_totp_secret)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)
