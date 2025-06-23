import argparse
import os
import sys

from dotenv import load_dotenv

from . import cache
from .views.setup_app import SetupApp


def main() -> None:
    """Entry point for the Spectr application."""
    # Import heavy modules lazily to avoid circular imports
    from . import spectr as appmod

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        type=str,
        default="AAPL,AMZN,META,MSFT,NVDA,TSLA,GOOG,VTI,GLD,BTCUSD",
        help="List of ticker symbols (e.g. NVDA,TSLA,AAPL)",
    )
    parser.add_argument(
        "--candles", action="store_true", default=True, help="Show candlestick chart."
    )
    parser.add_argument("--macd_thresh", type=float, default=0.002, help="MACD threshold")
    parser.add_argument("--bb_period", type=int, default=200, help="Bollinger Band period")
    parser.add_argument("--bb_dev", type=float, default=2.0, help="Bollinger Band std dev")
    parser.add_argument(
        "--real_trades", action="store_true", help="Enable live trading (vs paper)"
    )
    parser.add_argument("--interval", default="1min")
    parser.add_argument("--stop_loss_pct", type=float, default=0.01, help="Stop loss pct")
    parser.add_argument(
        "--take_profit_pct", type=float, default=0.05, help="Take profit pct"
    )
    parser.add_argument(
        "--lookback_period", type=int, default=1000, help="Lookback period"
    )
    parser.add_argument("--scale", type=float, default=0.5, help="Scale factor")
    parser.add_argument(
        "--broker",
        type=str,
        choices=["alpaca", "robinhood"],
        default=None,
        help="Choose which broker to use (Alpaca, Robinhood)",
    )
    parser.add_argument(
        "--data_api",
        type=str,
        choices=["alpaca", "robinhood", "fmp"],
        default=None,
        help="Choose which data provider to use (Alpaca, Robinhood, or FMP)",
    )
    parser.add_argument(
        "--listen", action="store_true", help="Enable real-time voice agent listening for a wake word"
    )
    parser.add_argument(
        "--wake_word", default="spectr", help="Wake word that triggers the voice agent"
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if "--symbols" not in sys.argv:
        cached = cache.load_symbols_cache()
        if cached:
            args.symbols = ",".join(cached)

    args.symbols = [s.strip().upper() for s in args.symbols.split(",")]
    args.symbol = args.symbols[0]  # set initial active symbol
    appmod.log.debug(f"Loading symbols: {args.symbols}")

    # Loading from .env file
    load_dotenv()

    cfg = None
    if not args.broker or not args.data_api:
        cfg = cache.load_onboarding_config()
        if cfg:
            if not args.broker:
                args.broker = cfg.get("broker")
            if not args.data_api:
                args.data_api = cfg.get("data_api")
            os.environ.setdefault("BROKER_API_KEY", cfg.get("broker_key", ""))
            os.environ.setdefault("BROKER_SECRET", cfg.get("broker_secret", ""))
            os.environ.setdefault("PAPER_API_KEY", cfg.get("paper_key", ""))
            os.environ.setdefault("PAPER_SECRET", cfg.get("paper_secret", ""))
            os.environ.setdefault("DATA_API_KEY", cfg.get("data_key", ""))
            os.environ.setdefault("DATA_SECRET", cfg.get("data_secret", ""))
            os.environ.setdefault("OPENAI_API_KEY", cfg.get("openai_key", ""))
            os.environ.setdefault("DATA_PROVIDER", cfg.get("data_api", ""))

    if not args.broker or not args.data_api:
        setup = SetupApp()
        setup.run()
        if setup.result:
            cache.save_onboarding_config(setup.result)
            args.broker = setup.result.get("broker")
            args.data_api = setup.result.get("data_api")
            os.environ["PAPER_API_KEY"] = setup.result.get("paper_key", "")
            os.environ["PAPER_SECRET"] = setup.result.get("paper_secret", "")
            if setup.result.get("broker_key"):
                os.environ["BROKER_API_KEY"] = setup.result["broker_key"]
            if setup.result.get("broker_secret"):
                os.environ["BROKER_SECRET"] = setup.result["broker_secret"]
            if setup.result.get("data_key"):
                os.environ["DATA_API_KEY"] = setup.result["data_key"]
            if setup.result.get("data_secret"):
                os.environ["DATA_SECRET"] = setup.result["data_secret"]
            if setup.result.get("openai_key"):
                os.environ["OPENAI_API_KEY"] = setup.result["openai_key"]
            if setup.result.get("data_api"):
                os.environ["DATA_PROVIDER"] = setup.result["data_api"]
        else:
            print("Setup cancelled.")
            return
    else:
        # If the user provided CLI options, ensure DATA_PROVIDER is set
        os.environ.setdefault("DATA_PROVIDER", args.data_api)

    if args.broker == "alpaca":
        from .fetch.alpaca import AlpacaInterface

        appmod.BROKER_API = AlpacaInterface(real_trades=args.real_trades)
    elif args.broker == "robinhood":
        from .fetch.robinhood import RobinhoodInterface

        appmod.BROKER_API = RobinhoodInterface()
    elif args.broker == "fmp":
        raise ValueError("Invalid broker: FMP does not support broker services, only data.")
    else:
        raise ValueError(f"Unknown broker: {args.broker}")

    if args.data_api == "alpaca":
        from .fetch.alpaca import AlpacaInterface

        if args.broker == "alpaca":
            appmod.DATA_API = appmod.BROKER_API
        else:
            appmod.DATA_API = AlpacaInterface(real_trades=args.real_trades)
    elif args.data_api == "robinhood":
        from .fetch.robinhood import RobinhoodInterface

        if args.broker == "robinhood":
            appmod.DATA_API = appmod.BROKER_API
        else:
            appmod.DATA_API = RobinhoodInterface()
    elif args.data_api == "fmp":
        from .fetch.fmp import FMPInterface

        # FMP can only be a data_api, not valid for broker.
        appmod.DATA_API = FMPInterface()

    config = appmod.AppConfig(
        macd_thresh=args.macd_thresh,
        bb_period=args.bb_period,
        bb_dev=args.bb_dev,
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        lookback_period=args.lookback_period,
        interval=args.interval,
        scale=args.scale,
    )

    app = appmod.SpectrApp(args, config)
    app.run()


if __name__ == "__main__":
    main()
