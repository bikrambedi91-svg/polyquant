"""Pydantic settings loaded from .env file."""

from typing import Literal, Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # --- Mode ---
    MODE: Literal["paper", "live"] = "paper"

    # --- Bankroll ---
    BANKROLL_USDC: float = 10000.0

    # --- API Keys (data sources) ---
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    CRYPTOQUANT_API_KEY: Optional[str] = None
    DERIBIT_CLIENT_ID: Optional[str] = None
    DERIBIT_CLIENT_SECRET: Optional[str] = None

    # --- Polymarket ---
    POLY_PRIVATE_KEY: str = ""
    POLY_FUNDER_ADDRESS: str = ""
    POLY_SIGNATURE_TYPE: int = 1
    POLY_CHAIN_ID: int = 137

    # --- Risk Parameters ---
    MAX_SINGLE_POSITION_PCT: float = 0.12
    MAX_PER_ASSET_PCT: float = 0.25
    MAX_TOTAL_EXPOSURE_PCT: float = 0.60
    DAILY_DRAWDOWN_HALT_PCT: float = 0.08
    DAILY_LOSS_HALT_USD: float = 100.0   # Fixed USD daily loss halt
    MIN_POSITION_USD: float = 5.0
    POSITION_SIZE_USD: float = 20.0      # Fixed $20 per trade (no Kelly)
    MIN_EDGE_THRESHOLD: float = 0.08
    MIN_CONFIDENCE: int = 55
    KELLY_FRACTION_DEFAULT: float = 0.25

    # --- TP/SL Defaults ---
    TP_OFFSET_DEFAULT: float = 0.05
    SL_5M: float = 0.08
    SL_15M: float = 0.10
    SL_1H: float = 0.12
    SL_4H: float = 0.15
    TIME_DECAY_EXIT_PCT: float = 0.15
    TIME_DECAY_FORCE_EXIT_PCT: float = 0.05

    # --- Learning Engine ---
    LEARNING_ENABLED: bool = True
    RECALIBRATION_TRADE_INTERVAL: int = 50
    RECALIBRATION_TIME_INTERVAL_HOURS: int = 168  # Weekly
    MIN_TRADES_FOR_SL_OPTIMIZATION: int = 30
    MIN_TRADES_FOR_PARAM_MUTATION: int = 80
    MIN_SHADOW_TRADES: int = 30
    MAX_PARAM_CHANGE_PCT: float = 0.50
    OPTUNA_QUICK_TRIALS: int = 50
    OPTUNA_DEEP_TRIALS: int = 200
    BRIER_WARNING_THRESHOLD: float = 0.28
    BRIER_CRITICAL_THRESHOLD: float = 0.35
    MAX_ENSEMBLE_MODELS: int = 8

    # --- Database ---
    DB_URL: str = "sqlite:///polyquant.db"

    # --- Alerts (optional) ---
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    DISCORD_WEBHOOK_URL: Optional[str] = None

    # --- Dashboard ---
    STREAMLIT_PORT: int = 8501
    DASHBOARD_REFRESH_SECONDS: int = 10

    # --- Graduation ---
    MIN_PAPER_TRADES: int = 100
    MIN_PAPER_WIN_RATE: float = 0.54
    MIN_PAPER_SHARPE: float = 0.8
    MAX_CALIBRATION_ERROR: float = 0.15
    MIN_PAPER_DAYS: int = 14
    MIN_RECALIBRATION_CYCLES: int = 2

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
