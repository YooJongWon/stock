"""Central, shared strategy settings for the US swing screener."""
from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    market_cap_min: float = 2_000_000_000
    pe_min: float = 0.0
    pe_max: float = 40.0
    roe_min: float = 0.15
    sales_growth_5y_min: float = 0.05
    price_min: float = 10.0
    avg_volume_min: float = 1_000_000
    avg_dollar_volume_min: float = 30_000_000
    rsi_length: int = 14
    rsi_min: float = 55.0
    rsi_max: float = 68.0
    atr_length: int = 14
    atr_stop_mult: float = 1.5
    max_stop_loss_pct: float = 5.0
    pullback_atr_max: float = 0.25
    sma_pullback: int = 50
    sma_long: int = 200
    ema_trend: int = 20
    ema_entry: int = 10
    roc_length: int = 63
    volume_dryup_ratio: float = 0.90
    volume_expansion_ratio: float = 1.10
    score_min: int = 7
    watch_score_min: int = 6
    max_holding_days: int = 20
    sec_requests_per_second: float = 5.0
    yfinance_max_retries: int = 3
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "USStockScreener/1.0 contact@example.com")
    cache_dir: Path = ROOT / "cache"
    # Cloud runs can stage results outside the checked-out working tree.
    output_dir: Path = Path(os.getenv("SCREENER_OUTPUT_DIR", ROOT / "output")).resolve()


SETTINGS = Settings()
