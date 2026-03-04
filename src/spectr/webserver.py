from flask import Flask, jsonify, send_from_directory
import os
import sys
from datetime import datetime

# Determine the correct path to the build directory
_script_dir = os.path.dirname(os.path.abspath(__file__))
_build_dir = os.path.join(_script_dir, "webui", "build")
if not os.path.exists(_build_dir):
    # Fallback for development mode when running from different directory
    _build_dir = os.path.join(os.path.dirname(_script_dir), "src", "spectr", "webui", "build")

app = Flask(__name__, static_folder=_build_dir, static_url_path="")

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
        balance = data_api.get_balance() or {}
        positions = data_api.get_positions() or []
        orders = data_api.get_all_orders() or []
        
        positions_data = []
        for pos in positions:
            pos_dict = {
                "symbol": getattr(pos, "symbol", ""),
                "qty": float(getattr(pos, "qty", 0) or 0),
                "market_value": float(getattr(pos, "market_value", 0) or 0),
                "avg_entry_price": float(getattr(pos, "avg_entry_price", 0) or 0)
            }
            positions_data.append(pos_dict)
        
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
                value = float(order.qty) * float(price)
            except Exception:
                value = 0.0
            
            order_dict = {
                "datetime": dt_str,
                "symbol": getattr(order, "symbol", ""),
                "side": getattr(order, "side", ""),
                "qty": float(getattr(order, "qty", 0) or 0),
                "value": value,
                "order_type": getattr(order, "order_type", ""),
                "status": getattr(order, "status", "")
            }
            orders_data.append(order_dict)
        
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
    full_path = os.path.join(app.static_folder, path) if path else app.static_folder
    
    if path and os.path.isfile(full_path):
        return send_from_directory(app.static_folder, path)
    
    # Otherwise serve index.html for SPA routing
    index_path = os.path.join(app.static_folder, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, "index.html")

    return jsonify({"error": "Not found"}), 404


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
