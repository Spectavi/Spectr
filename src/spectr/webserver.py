import requests
from flask import Flask, jsonify, send_from_directory, request
import os
import sys
import pandas as pd
import logging
from datetime import datetime

log = logging.getLogger(__name__)

_script_dir = os.path.dirname(os.path.abspath(__file__))
_build_dir = os.path.join(_script_dir, "webui", "build")
if not os.path.exists(_build_dir):
    _build_dir = os.path.join(os.path.dirname(_script_dir), "src", "spectr", "webui", "build")

app = Flask(__name__, static_folder=None, static_url_path=None)

data_api = None
broker_api = None
cached_tickers = []
cached_strategies = []
current_strategy = None
strategy_active = False


def init_data_api(data_provider: str):
    global data_api, broker_api
    if data_provider == "alpaca":
        from .fetch.alpaca import AlpacaInterface
        data_api = AlpacaInterface(real_trades=False)
        broker_api = data_api
    elif data_provider == "robinhood":
        from .fetch.robinhood import RobinhoodInterface
        data_api = RobinhoodInterface()
        broker_api = data_api
    elif data_provider == "fmp":
        from .fetch.fmp import FMPInterface
        data_api = FMPInterface()
        try:
            from .fetch.alpaca import AlpacaInterface, PAPER_KEY, PAPER_SECRET
            if PAPER_KEY and PAPER_SECRET:
                broker_api = AlpacaInterface(real_trades=False)
        except Exception:
            pass


@app.route("/api/tickers", methods=["GET"])
def get_tickers():
    if not cached_tickers:
        return jsonify([])
    return jsonify(cached_tickers)


@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    if not cached_tickers:
        return jsonify([])
    return jsonify(cached_tickers)


@app.route("/api/watchlist", methods=["POST"])
def add_to_watchlist():
    global cached_tickers
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Invalid JSON data"}), 400
        
        ticker = data.get('ticker')
        if not ticker:
            return jsonify({"success": False, "error": "Missing ticker"}), 400
        
        ticker = ticker.upper().strip()
        
        if ticker in cached_tickers:
            return jsonify({"success": True, "message": f"{ticker} already in watchlist"})
        
        cached_tickers.append(ticker)
        _save_cached_tickers()
        
        return jsonify({"success": True, "message": f"Added {ticker} to watchlist", "tickers": cached_tickers})
    except Exception as e:
        log.error(f"Failed to add ticker: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/watchlist/<ticker>", methods=["DELETE"])
def remove_from_watchlist(ticker):
    global cached_tickers
    try:
        ticker = ticker.upper().strip()
        
        if ticker in cached_tickers:
            cached_tickers.remove(ticker)
            _save_cached_tickers()
        
        return jsonify({"success": True, "message": f"Removed {ticker} from watchlist", "tickers": cached_tickers})
    except Exception as e:
        log.error(f"Failed to remove ticker: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/search-tickers", methods=["GET"])
def search_tickers():
    global data_api
    if not data_api:
        return jsonify([])
    
    query = request.args.get('query', '').strip()
    if not query or len(query) < 2:
        return jsonify([])
    
    try:
        url = f"https://financialmodelingprep.com/api/v3/search?query={query}&limit=5&apikey={data_api.api_key}"
        resp = requests.get(url, timeout=10)
        data_api._check_rate_limit(resp)
        results = resp.json()
        
        if isinstance(results, list):
            filtered_results = []
            seen = set()
            for item in results:
                symbol = item.get('symbol', '').upper()
                name = item.get('name', '')
                exchange = item.get('exchange', '')
                
                if symbol and symbol not in seen and not any(ex in exchange.upper() for ex in ['OTC', 'PINK', 'BLOOMBERG']):
                    filtered_results.append({'symbol': symbol, 'name': name})
                    seen.add(symbol)
            
            return jsonify(filtered_results[:5])
        
        return jsonify([])
    except Exception as e:
        log.error(f"Failed to search tickers: {e}")
        return jsonify([])


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
        
        from .fetch.alpaca import AlpacaInterface
        broker_api = AlpacaInterface(real_trades=is_live)
        
        balance = broker_api.get_balance() or {}
        positions = broker_api.get_positions() or []
        
        positions_data = []
        for pos in positions:
            pos_dict = {
                "symbol": getattr(pos, "symbol", ""),
                "qty": float(getattr(pos, "qty", 0) or 0),
                "market_value": float(getattr(pos, "market_value", 0) or 0),
                "avg_entry_price": float(getattr(pos, "avg_entry_price", 0) or 0)
            }
            positions_data.append(pos_dict)
        
        if hasattr(broker_api, 'get_all_orders'):
            try:
                orders = broker_api.get_all_orders(real_trades=is_live)
            except TypeError:
                orders = broker_api.get_all_orders()
        else:
            orders = []
        
        if isinstance(orders, pd.DataFrame):
            if not orders.empty:
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
                        "side": getattr(row.get("side"), 'value', str(row.get("side", ""))) if hasattr(row.get("side", None), 'value') and row.get("side") is not None else str(row.get("side", "")),
                        "qty": float(row.get("qty", 0) or 0),
                        "value": value,
                        "order_type": getattr(row.get("order_type"), 'value', str(row.get("order_type", ""))) if hasattr(row.get("order_type", None), 'value') and row.get("order_type") is not None else str(row.get("order_type", "")),
                        "status": str(row.get("status", ""))
                    }
                    orders_data.append(order_dict)
            else:
                orders_data = []
        elif isinstance(orders, list):
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
                    "side": getattr(getattr(order, "side", None), 'value', str(getattr(order, "side", ""))) if hasattr(getattr(order, "side", None), 'value') and getattr(order, "side", None) is not None else str(getattr(order, "side", "")),
                    "qty": float(getattr(order, "qty", 0) or 0),
                    "value": value,
                    "order_type": getattr(getattr(order, "order_type", None), 'value', str(getattr(order, "order_type", ""))) if hasattr(getattr(order, "order_type", None), 'value') and getattr(order, "order_type", None) is not None else str(getattr(order, "order_type", "")),
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
    if path:
        full_path = os.path.join(_build_dir, path)
        if os.path.isfile(full_path):
            return send_from_directory(_build_dir, path)
    
    index_path = os.path.join(_build_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(_build_dir, "index.html")

    return jsonify({"error": "Not found"}), 404


@app.route("/api/account-info", methods=["GET"])
def get_account_info():
    cfg = None
    try:
        from . import cache
        cfg = cache.load_onboarding_config()
    except Exception:
        pass
    
    data_provider = os.getenv("DATA_PROVIDER")
    if not data_provider and cfg:
        data_provider = cfg.get("data_api")
    if not data_provider:
        data_provider = "alpaca"
    
    broker_names = {
        "alpaca": "Alpaca",
        "robinhood": "Robinhood",
        "fmp": "FMP",
    }
    broker_name = broker_names.get(data_provider, "Unknown")
    
    has_paper_credentials = bool(
        (os.getenv("PAPER_API_KEY") and os.getenv("PAPER_SECRET"))
        or (cfg and cfg.get("paper_key") and cfg.get("paper_secret"))
        or (os.getenv("ALPACA_API_KEY_PAPER") and os.getenv("ALPACA_SECRET_KEY_PAPER"))
    )
    
    has_live_credentials = bool(
        (os.getenv("BROKER_API_KEY") and os.getenv("BROKER_SECRET"))
        or (cfg and cfg.get("broker_key") and cfg.get("broker_secret"))
        or (os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
    )
    
    default_to_paper = True
    
    return jsonify({
        "broker": broker_name,
        "hasPaperCredentials": has_paper_credentials,
        "hasLiveCredentials": has_live_credentials,
        "defaultToPaper": default_to_paper,
    })


@app.route("/api/strategies", methods=["GET"])
def get_strategies():
    global cached_strategies, current_strategy, strategy_active
    
    if not cached_strategies:
        try:
            from .strategies import list_strategies
            cached_strategies = list(list_strategies().keys())
        except Exception:
            cached_strategies = []
    
    return jsonify({
        "strategies": cached_strategies,
        "current": current_strategy or "",
        "active": strategy_active
    })


@app.route("/api/strategies/<strategy_name>", methods=["POST"])
def select_strategy(strategy_name):
    global current_strategy, strategy_active
    
    try:
        data = request.get_json() or {}
        deactivate_previous = bool(data.get('deactivatePrevious', False))
        
        if deactivate_previous and strategy_active:
            strategy_active = False
        
        from .strategies import load_strategy
        load_strategy(strategy_name)
        
        current_strategy = strategy_name
        
        return jsonify({
            "success": True,
            "message": f"Strategy '{strategy_name}' selected",
            "current": strategy_name,
            "active": strategy_active
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route("/api/strategies/toggle", methods=["POST"])
def toggle_strategy():
    global strategy_active
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "success": False,
                "error": "Invalid JSON data"
            }), 400
        
        new_state = bool(data.get('active', not strategy_active))
        strategy_active = new_state
        
        return jsonify({
            "success": True,
            "message": f"Strategy {'activated' if strategy_active else 'deactivated'}",
            "active": strategy_active
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/strategies/auto-trade", methods=["POST"])
def toggle_auto_trade():
    global strategy_active
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "success": False,
                "error": "Invalid JSON data"
            }), 400
        
        new_state = bool(data.get('enabled', False))
        
        if new_state and not strategy_active:
            strategy_active = True
        
        return jsonify({
            "success": True,
            "message": f"Auto-trade {'enabled' if new_state else 'disabled'}",
            "autoTradeEnabled": new_state,
            "active": strategy_active
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def _save_cached_tickers():
    project_root = os.path.join(_script_dir, "..", "..")
    cached_tickers_path = os.path.join(project_root, ".cached_tickers")
    
    with open(cached_tickers_path, "w") as f:
        for ticker in cached_tickers:
            f.write(f"{ticker}\n")


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

    project_root = os.path.join(_script_dir, "..", "..")
    cached_tickers_path = os.path.join(project_root, ".cached_tickers")
    
    if os.path.exists(cached_tickers_path):
        with open(cached_tickers_path, "r") as f:
            global cached_tickers
            cached_tickers = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Starting web server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


@app.route("/api/orders", methods=["POST"])
def submit_order():
    global data_api, broker_api
    
    if broker_api and hasattr(broker_api, 'mock_calls'):
        broker_api = None
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "success": False,
                "error": "Invalid JSON data"
            }), 400
        
        symbol = data.get('symbol')
        side_name = data.get('side')
        order_type_name = data.get('type')
        quantity = data.get('quantity')
        limit_price = data.get('limit_price')
        
        if not all([symbol, side_name, order_type_name, quantity]):
            return jsonify({
                "success": False,
                "error": "Missing required fields: symbol, side, type, quantity"
            }), 400
        
        from .fetch.broker_interface import OrderSide, OrderType
        
        try:
            side = OrderSide[side_name]
            order_type = OrderType[order_type_name]
        except KeyError:
            return jsonify({
                "success": False,
                "error": f"Invalid side or type. Valid sides: {[s.name for s in OrderSide]}. Valid types: {[t.name for t in OrderType]}"
            }), 400
        
        if not broker_api and data_api:
            broker_api = data_api
        if not broker_api:
            from .fetch.alpaca import AlpacaInterface
            broker_api = AlpacaInterface(real_trades=False)
        
        if not broker_api:
            return jsonify({
                "success": False,
                "error": "Trading is not configured. Please set up a broker in the onboarding dialog."
            }), 400
        
        broker_side = side.name.lower()
        broker_type = order_type
        
        if order_type == OrderType.MARKET:
            order = broker_api.submit_order(
                symbol=symbol,
                side=side,
                type=order_type,
                quantity=float(quantity),
                market_price=None
            )
        else:
            if limit_price is None:
                return jsonify({
                    "success": False,
                    "error": "limit_price is required for LIMIT orders"
                }), 400
            order = broker_api.submit_order(
                symbol=symbol,
                side=side,
                type=order_type,
                quantity=float(quantity),
                limit_price=float(limit_price)
            )
        
        return jsonify({
            "success": True,
            "message": f"Order submitted: {side.name.upper()} {quantity} of {symbol.upper()} @ {limit_price if order_type == OrderType.LIMIT else 'MKT'}",
            "order_id": getattr(order, "id", None),
            "status": str(getattr(order, "status", "")) if hasattr(order, 'status') else "submitted"
        })
        
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error(f"Order submission failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    start_server()
