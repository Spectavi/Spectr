from flask import Flask, jsonify, send_from_directory, request
import os
import sys
import pandas as pd
from datetime import datetime

# Determine the correct path to the build directory
_script_dir = os.path.dirname(os.path.abspath(__file__))
_build_dir = os.path.join(_script_dir, "webui", "build")
if not os.path.exists(_build_dir):
    # Fallback for development mode when running from different directory
    _build_dir = os.path.join(os.path.dirname(_script_dir), "src", "spectr", "webui", "build")

app = Flask(__name__, static_folder=None, static_url_path=None)

data_api = None
cached_tickers = []


def init_data_api(data_provider: str):
    global data_api
    if data_provider == "alpaca":
        from .fetch.alpaca import AlpacaInterface

        data_api = AlpacaInterface(real_trades=False)
    elif data_provider == "robinhood":
        from .fetch.robinhood import RobinhoodInterface

        data_api = RobinhoodInterface()
    elif data_provider == "fmp":
        from .fetch.fmp import FMPInterface

        data_api = FMPInterface()


@app.route("/api/tickers", methods=["GET"])
def get_tickers():
    if not cached_tickers:
        return jsonify([])
    return jsonify(cached_tickers)


@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    global data_api
    if not data_api:
        return jsonify({
            "balance": {},
            "positions": [],
            "orders": []
        })
    
    try:
        is_live = request.args.get('live', 'false').lower() == 'true'
        
        # Create broker API instance for the requested account type
        from .fetch.alpaca import AlpacaInterface
        
        # Always use AlpacaInterface for broker operations (paper or live trading)
        broker_api = AlpacaInterface(real_trades=is_live)
        
        balance = broker_api.get_balance() or {}
        positions = broker_api.get_positions() or []
        
        # Process positions
        positions_data = []
        for pos in positions:
            pos_dict = {
                "symbol": getattr(pos, "symbol", ""),
                "qty": float(getattr(pos, "qty", 0) or 0),
                "market_value": float(getattr(pos, "market_value", 0) or 0),
                "avg_entry_price": float(getattr(pos, "avg_entry_price", 0) or 0)
            }
            positions_data.append(pos_dict)
        
        # Get orders with appropriate method
        if hasattr(broker_api, 'get_all_orders'):
            try:
                orders = broker_api.get_all_orders(real_trades=is_live)
            except TypeError:
                orders = broker_api.get_all_orders()
        else:
            orders = []
        
        # Handle both DataFrame (from AlpacaInterface) and list of objects
        print(f"DEBUG: orders is DataFrame? {isinstance(orders, pd.DataFrame)}, type={type(orders)}")
        if isinstance(orders, pd.DataFrame):
            if not orders.empty:
                # Convert DataFrame to list of dicts for JSON serialization
                orders_data = []
                for _, row in orders.iterrows():
                    dt = (
                        getattr(row, "submitted_at", None)
                        or getattr(row, "created_at", None)
                        or getattr(row, "filled_at", None)
                    )
                    if hasattr(dt, "strftime"):
                        dt_str = dt.strftime("%Y-%m-%d %H:%M")
                    else:
                        dt_str = str(dt) if dt else ""
                    
                    price = (
                        getattr(row, "filled_avg_price", None)
                        or getattr(row, "limit_price", None)
                        or getattr(row, "price", None)
                        or 0.0
                    )
                    try:
                        value = float(row.get("qty", 0) or 0) * float(price)
                    except Exception:
                        value = 0.0
                    
                    order_dict = {
                        "datetime": dt_str,
                        "symbol": str(row.get("symbol", "")),
                        "side": str(row.get("side", "")) if isinstance(row.get("side"), str) else getattr(row.get("side"), 'value', str(row.get("side", ""))),
                        "qty": float(row.get("qty", 0) or 0),
                        "value": value,
                        "order_type": str(row.get("order_type", "")) if isinstance(row.get("order_type"), str) else getattr(row.get("order_type"), 'value', str(row.get("order_type", ""))),
                        "status": str(row.get("status", ""))
                    }
                    orders_data.append(order_dict)
            else:
                orders_data = []
        elif isinstance(orders, list):
            # Legacy code for list of order objects
            orders_data = []
            for order in orders:
                dt = (
                    getattr(order, "submitted_at", None)
                    or getattr(order, "created_at", None)
                    or getattr(order, "filled_at", None)
                )
                if hasattr(dt, "strftime"):
                    dt_str = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    dt_str = str(dt) if dt else ""
                
                price = (
                    getattr(order, "filled_avg_price", None)
                    or getattr(order, "limit_price", None)
                    or getattr(order, "price", None)
                    or 0.0
                )
                try:
                    value = float(getattr(order, "qty", 0) or 0) * float(price)
                except Exception:
                    value = 0.0
                
                order_dict = {
                    "datetime": dt_str,
                    "symbol": getattr(order, "symbol", ""),
                    "side": str(getattr(order, "side", "")) if isinstance(getattr(order, "side", ""), str) else getattr(getattr(order, "side", None), 'value', str(getattr(order, "side", ""))),
                    "qty": float(getattr(order, "qty", 0) or 0),
                    "value": value,
                    "order_type": str(getattr(order, "order_type", "")) if isinstance(getattr(order, "order_type", ""), str) else getattr(getattr(order, "order_type", None), 'value', str(getattr(order, "order_type", ""))),
                    "status": getattr(order, "status", "")
                }
                orders_data.append(order_dict)
        else:
            orders_data = []
        
        return jsonify({
            "balance": balance,
            "positions": positions_data,
            "orders": orders_data
        })
    except Exception as e:
        return jsonify({
            "balance": {},
            "positions": [],
            "orders": [],
            "error": str(e)
        }), 500


@app.route("/api/chart/<symbol>", methods=["GET"])
def get_chart_data(symbol):
    global data_api
    if not data_api:
        return jsonify({"error": "Data API not initialized"}), 500

    try:
        today = datetime.now().date()
        from_date = today.strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")

        df = data_api.fetch_chart_data(symbol, from_date=from_date, to_date=to_date)

        if df.empty:
            return jsonify({"error": f"No chart data found for {symbol}"}), 404

        df.index = df.index.tz_localize(None)
        df["timestamp"] = df.index.strftime("%Y-%m-%dT%H:%M:%S")

        result = {
            "symbol": symbol.upper(),
            "data": df[["timestamp", "open", "high", "low", "close", "volume"]]
            .to_dict(orient="records"),
            "current_price": 0,
            "current_volume": 0,
        }

        try:
            quote = data_api.fetch_quote(symbol)
            result["current_price"] = quote.get("price", 0)
            result["current_volume"] = quote.get("volume", 0)
        except Exception:
            pass

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    # Always try to serve the requested path first if it exists
    if path:
        full_path = os.path.join(_build_dir, path)
        if os.path.isfile(full_path):
            return send_from_directory(_build_dir, path)
    
    # Otherwise serve index.html for SPA routing
    index_path = os.path.join(_build_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(_build_dir, "index.html")

    return jsonify({"error": "Not found"}), 404


@app.route("/api/account-info", methods=["GET"])
def get_account_info():
    """Return information about the configured account (paper vs live)."""
    cfg = None
    try:
        from . import cache
        cfg = cache.load_onboarding_config()
    except Exception:
        pass
    
    # Determine broker name from config or environment
    data_provider = os.getenv("DATA_PROVIDER")
    if not data_provider and cfg:
        data_provider = cfg.get("data_api")
    if not data_provider:
        data_provider = "alpaca"
    
    # Map provider to display name
    broker_names = {
        "alpaca": "Alpaca",
        "robinhood": "Robinhood",
        "fmp": "FMP",
    }
    broker_name = broker_names.get(data_provider, "Unknown")
    
    # Determine if paper credentials are configured
    has_paper_credentials = bool(
        (os.getenv("PAPER_API_KEY") and os.getenv("PAPER_SECRET"))
        or (cfg and cfg.get("paper_key") and cfg.get("paper_secret"))
        or (os.getenv("ALPACA_API_KEY_PAPER") and os.getenv("ALPACA_SECRET_KEY_PAPER"))
    )
    
    # Determine if live credentials are configured  
    has_live_credentials = bool(
        (os.getenv("BROKER_API_KEY") and os.getenv("BROKER_SECRET"))
        or (cfg and cfg.get("broker_key") and cfg.get("broker_secret"))
        or (os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
    )
    
    # Default to paper to match TUI behavior (TUI defaults to PAPER unless --real_trades is passed)
    default_to_paper = True
    
    return jsonify({
        "broker": broker_name,
        "hasPaperCredentials": has_paper_credentials,
        "hasLiveCredentials": has_live_credentials,
        "defaultToPaper": default_to_paper,
    })


def start_server(port: int = 8020):
    global cached_tickers

    from dotenv import load_dotenv

    load_dotenv()

    cfg = None
    data_provider = os.getenv("DATA_PROVIDER")
    if not data_provider:
        from . import cache

        cfg = cache.load_onboarding_config()
        if cfg:
            data_provider = cfg.get("data_api")

    if not data_provider:
        data_provider = "alpaca"

    # Set environment variables from onboarding config to ensure credentials are available
    # This ensures both TUI and web UI use the same account (paper vs live)
    if cfg:
        paper_key = cfg.get("paper_key")
        if paper_key:
            os.environ.setdefault("PAPER_API_KEY", str(paper_key))
        paper_secret = cfg.get("paper_secret")
        if paper_secret:
            os.environ.setdefault("PAPER_SECRET", str(paper_secret))
        broker_key = cfg.get("broker_key")
        if broker_key:
            os.environ.setdefault("BROKER_API_KEY", str(broker_key))
        broker_secret = cfg.get("broker_secret")
        if broker_secret:
            os.environ.setdefault("BROKER_SECRET", str(broker_secret))
        data_key = cfg.get("data_key")
        if data_key:
            os.environ.setdefault("DATA_API_KEY", str(data_key))
        data_secret = cfg.get("data_secret")
        if data_secret:
            os.environ.setdefault("DATA_SECRET", str(data_secret))
        openai_key = cfg.get("openai_key")
        if openai_key:
            os.environ.setdefault("OPENAI_API_KEY", str(openai_key))

    init_data_api(data_provider)

    # Load cached tickers from the project root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(script_dir, "..", "..")
    cached_tickers_path = os.path.join(project_root, ".cached_tickers")
    
    if os.path.exists(cached_tickers_path):
        with open(cached_tickers_path, "r") as f:
            global cached_tickers
            cached_tickers = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Starting web server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    start_server()
