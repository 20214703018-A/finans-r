from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "AI Market Pattern Scanner"
    app_env: str = Field(default="development")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/finansor"
    )
    sync_database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/finansor"
    )

    kraken_base_url: str = Field(default="https://api.kraken.com")
    alpaca_api_key: str = Field(default="")
    alpaca_api_secret: str = Field(default="")
    alpaca_base_url: str = Field(default="https://paper-api.alpaca.markets")

    yolo_model_path: str = Field(default="models/stockmarket_yolov8.pt")
    yolo_conf_min: float = Field(default=0.40)
    yolo_hf_repo: str = Field(default="foduucom/stockmarket-pattern-detection-yolov8")
    yolo_hf_filename: str = Field(default="model.pt")
    yolo_auto_download: bool = Field(default=True)

    reasoning_provider: str = Field(default="openai")  # openai | gemini | none
    openai_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")

    # Scanner defaults
    default_limit: int = Field(default=300)
    reasoning_score_threshold: int = Field(default=70)

    # Timeframes in minutes
    timeframes: dict[str, int] = Field(
        default={
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
        }
    )

    # Supported crypto (MVP)
    crypto_symbols: list[str] = Field(
        default=[
            "BTCUSD",
            "ETHUSD",
            "SOLUSD",
            "XRPUSD",
            "BNBUSD",
            "DOGEUSD",
            "ADAUSD",
            "AVAXUSD",
            "LINKUSD",
            "SUIUSD",
        ]
    )
    # Full asset universe (includes Nasdaq/BIST placeholders – validated via registry)
    supported_symbols: list[str] = Field(
        default=[
            "BTCUSD",
            "ETHUSD",
            "SOLUSD",
            "XRPUSD",
            "BNBUSD",
            "DOGEUSD",
            "ADAUSD",
            "AVAXUSD",
            "LINKUSD",
            "SUIUSD",
            # Nasdaq examples
            "AAPL",
            "MSFT",
            "NVDA",
            "TSLA",
            # BIST examples
            "THYAO",
            "GARAN",
            "AKBNK",
        ]
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
