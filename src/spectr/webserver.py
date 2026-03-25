import requests
from flask import Flask, jsonify, send_from_directory, request, Response
import os
import sys
import pandas as pd
import logging
from datetime import datetime
import tempfile
import threading
import pathlib
import importlib

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
strategy_configs = {}
_last_strategy_signal_keys = {}
_default_strategy_name = ""
_default_trade_amount = 0.0

try:
    from . import cache

    cached_strategy = cache.load_selected_strategy()
    if cached_strategy:
        _default_strategy_name = str(cached_strategy)
    cached_trade_amount = cache.load_trade_amount()
    if cached_trade_amount is not None:
        _default_trade_amount = max(0.0, float(cached_trade_amount))
    
    afterhours_enabled = cache.load_afterhours_enabled()
    if afterhours_enabled is None:
        afterhours_enabled = False
    loaded_configs = cache.load_strategy_configs()
    if isinstance(loaded_configs, dict):
        strategy_configs = loaded_configs
except Exception:
    pass


def _normalize_ticker(ticker: str | None) -> str:
    return str(ticker or "").upper().strip()


def _base_strategy_config() -> dict:
    return {
        "current": _default_strategy_name,
        "active": False,
        "autoTradeEnabled": False,
        "tradeAmount": _default_trade_amount,
    }


def _normalize_strategy_config(raw_cfg: dict | None) -> dict:
    cfg = _base_strategy_config()
    if not isinstance(raw_cfg, dict):
        return cfg
    cfg["current"] = str(raw_cfg.get("current") or cfg["current"] or "")
    cfg["active"] = bool(raw_cfg.get("active", cfg["active"]))
    cfg["autoTradeEnabled"] = bool(
        raw_cfg.get("autoTradeEnabled", cfg["autoTradeEnabled"])
    )
    try:
        cfg["tradeAmount"] = max(
            0.0, float(raw_cfg.get("tradeAmount", cfg["tradeAmount"]) or 0.0)
        )
    except Exception:
        cfg["tradeAmount"] = 0.0
    return cfg


def _save_strategy_configs() -> None:
    try:
        from . import cache

        cache.save_strategy_configs(strategy_configs)
    except Exception:
        pass


def _get_strategy_config(ticker: str | None, *, create: bool = True) -> dict:
    symbol = _normalize_ticker(ticker)
    if not symbol:
        return _base_strategy_config()
    cfg = strategy_configs.get(symbol)
    if cfg is None:
        if not create:
            return _base_strategy_config()
        cfg = _base_strategy_config()
        strategy_configs[symbol] = cfg
    else:
        cfg = _normalize_strategy_config(cfg)
        strategy_configs[symbol] = cfg
    return cfg


def _resolve_ticker_context(payload: dict | None = None) -> str:
    data = payload or {}
    ticker = _normalize_ticker(
        data.get("ticker")
        or data.get("symbol")
        or request.args.get("ticker")
        or request.args.get("symbol")
    )
    if ticker:
        return ticker
    if cached_tickers:
        return _normalize_ticker(cached_tickers[0])
    return ""


def _sync_strategy_configs_with_watchlist() -> None:
    watchlist_set = {_normalize_ticker(t) for t in cached_tickers if _normalize_ticker(t)}
    stale = [symbol for symbol in strategy_configs if symbol not in watchlist_set]
    for symbol in stale:
        strategy_configs.pop(symbol, None)
        _last_strategy_signal_keys.pop(symbol, None)
    for symbol in watchlist_set:
        _get_strategy_config(symbol, create=True)


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
        _get_strategy_config(ticker, create=True)
        _save_strategy_configs()
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
            strategy_configs.pop(ticker, None)
            _last_strategy_signal_keys.pop(ticker, None)
            _save_strategy_configs()
            _save_cached_tickers()
        
        return jsonify({"success": True, "message": f"Removed {ticker} from watchlist", "tickers": cached_tickers})
    except Exception as e:
        log.error(f"Failed to remove ticker: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/profile/<symbol>", methods=["GET"])
def get_profile(symbol):
    global data_api
    
    profile = {}
    if data_api and hasattr(data_api, 'fetch_company_profile'):
        try:
            profile = data_api.fetch_company_profile(symbol.upper())
        except Exception as e:
            log.error(f"Failed to fetch profile for {symbol}: {e}")
    
    logo_url = (
        profile.get('image') or
        profile.get('logo') or
        profile.get('companyLogo') or
        ''
    )
    
    return jsonify({
        'symbol': symbol.upper(),
        'logo': logo_url,
        **{k: v for k, v in profile.items() if k not in ['image', 'logo', 'companyLogo']}
    })

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
                        "id": str(row.get("id", "")),
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
                    "id": str(getattr(order, "id", "")),
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
    
    global afterhours_enabled
    
    return jsonify({
        "broker": broker_name,
        "hasPaperCredentials": has_paper_credentials,
        "hasLiveCredentials": has_live_credentials,
        "defaultToPaper": default_to_paper,
        "afterhours_enabled": afterhours_enabled,
    })


@app.route("/api/settings/afterhours", methods=["POST"])
def update_afterhours():
    global afterhours_enabled
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "success": False,
                "error": "Invalid JSON data"
            }), 400
        
        enabled = data.get('afterhours_enabled')
        if enabled is None:
            return jsonify({
                "success": False,
                "error": "Missing afterhours_enabled field"
            }), 400
        
        from . import cache
        cache.save_afterhours_enabled(enabled)
        afterhours_enabled = bool(enabled)
        
        # Also update the main app's afterhours setting if it exists
        try:
            from .spectr import SpectrApp
            # Try to get the running app instance if available
            import gc
            for obj in gc.get_objects():
                if isinstance(obj, SpectrApp):
                    obj.afterhours_enabled = bool(enabled)
                    break
        except Exception:
            pass
        
        return jsonify({
            "success": True,
            "afterhours_enabled": afterhours_enabled
        })
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error(f"Failed to update after-hours setting: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/strategies", methods=["GET"])
def get_strategies():
    global cached_strategies
    
    if not cached_strategies:
        try:
            from .strategies import list_strategies
            cached_strategies = list(list_strategies().keys())
        except Exception:
            cached_strategies = []

    ticker = _resolve_ticker_context()
    cfg = _get_strategy_config(ticker, create=bool(ticker))
    
    return jsonify({
        "strategies": cached_strategies,
        "ticker": ticker,
        "current": cfg.get("current", ""),
        "active": bool(cfg.get("active", False)),
        "autoTradeEnabled": bool(cfg.get("autoTradeEnabled", False)),
        "tradeAmount": float(cfg.get("tradeAmount", 0.0)),
        "configs": {
            symbol: _normalize_strategy_config(raw_cfg)
            for symbol, raw_cfg in strategy_configs.items()
        },
    })


@app.route("/api/strategies/<strategy_name>", methods=["POST"])
def select_strategy(strategy_name):
    try:
        data = request.get_json() or {}
        ticker = _resolve_ticker_context(data)
        if not ticker:
            return jsonify({"success": False, "error": "Missing ticker"}), 400
        deactivate_previous = bool(data.get('deactivatePrevious', False))

        from .strategies import load_strategy
        load_strategy(strategy_name)

        cfg = _get_strategy_config(ticker, create=True)
        if deactivate_previous and cfg.get("active", False):
            cfg["active"] = False
        cfg["current"] = strategy_name
        _last_strategy_signal_keys[ticker] = None
        _save_strategy_configs()
        
        return jsonify({
            "success": True,
            "message": f"Strategy '{strategy_name}' selected for {ticker}",
            "ticker": ticker,
            "current": strategy_name,
            "active": bool(cfg.get("active", False)),
            "autoTradeEnabled": bool(cfg.get("autoTradeEnabled", False)),
            "tradeAmount": float(cfg.get("tradeAmount", 0.0)),
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route("/api/strategies/toggle", methods=["POST"])
def toggle_strategy():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "success": False,
                "error": "Invalid JSON data"
            }), 400

        ticker = _resolve_ticker_context(data)
        if not ticker:
            return jsonify({"success": False, "error": "Missing ticker"}), 400

        cfg = _get_strategy_config(ticker, create=True)
        new_state = bool(data.get('active', not cfg.get("active", False)))
        cfg["active"] = new_state
        _save_strategy_configs()
        
        return jsonify({
            "success": True,
            "message": f"Strategy {'activated' if new_state else 'deactivated'} for {ticker}",
            "ticker": ticker,
            "active": bool(cfg.get("active", False)),
            "current": cfg.get("current", ""),
            "autoTradeEnabled": bool(cfg.get("autoTradeEnabled", False)),
            "tradeAmount": float(cfg.get("tradeAmount", 0.0)),
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/strategies/auto-trade", methods=["POST"])
def toggle_auto_trade():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "success": False,
                "error": "Invalid JSON data"
            }), 400

        ticker = _resolve_ticker_context(data)
        if not ticker:
            return jsonify({"success": False, "error": "Missing ticker"}), 400

        cfg = _get_strategy_config(ticker, create=True)
        new_state = bool(data.get('enabled', False))
        cfg["autoTradeEnabled"] = new_state
        if new_state and not cfg.get("active", False):
            cfg["active"] = True
        _save_strategy_configs()
        
        return jsonify({
            "success": True,
            "message": f"Auto-trade {'enabled' if new_state else 'disabled'} for {ticker}",
            "ticker": ticker,
            "autoTradeEnabled": new_state,
            "active": bool(cfg.get("active", False)),
            "current": cfg.get("current", ""),
            "tradeAmount": float(cfg.get("tradeAmount", 0.0)),
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/strategies/config", methods=["POST"])
def update_strategy_config():
    try:
        data = request.get_json() or {}
        ticker = _resolve_ticker_context(data)
        if not ticker:
            return jsonify({"success": False, "error": "Missing ticker"}), 400

        cfg = _get_strategy_config(ticker, create=True)
        trade_amount = data.get("tradeAmount")
        auto_trade_enabled = data.get("autoTradeEnabled")
        active = data.get("active")

        if trade_amount is not None:
            try:
                cfg["tradeAmount"] = max(0.0, float(trade_amount))
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid tradeAmount"}), 400

        if auto_trade_enabled is not None:
            cfg["autoTradeEnabled"] = bool(auto_trade_enabled)
            if cfg["autoTradeEnabled"]:
                cfg["active"] = True
        if active is not None:
            cfg["active"] = bool(active)

        _save_strategy_configs()

        return jsonify(
            {
                "success": True,
                "ticker": ticker,
                "current": cfg.get("current", ""),
                "tradeAmount": float(cfg.get("tradeAmount", 0.0)),
                "autoTradeEnabled": bool(cfg.get("autoTradeEnabled", False)),
                "active": bool(cfg.get("active", False)),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _resolve_strategy_file_path(strategy_name: str) -> pathlib.Path:
    strategies_dir = pathlib.Path(__file__).resolve().parent / "strategies"
    for path in strategies_dir.glob("*.py"):
        if path.stem in {"__init__", "trading_strategy", "metrics"}:
            continue
        try:
            contents = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if f"class {strategy_name}" in contents:
            return path
    raise FileNotFoundError(f"Unable to locate source file for strategy {strategy_name}")


@app.route("/api/strategies/<strategy_name>/code", methods=["GET"])
def get_strategy_code(strategy_name):
    try:
        from .strategies import load_strategy

        load_strategy(strategy_name)
        path = _resolve_strategy_file_path(strategy_name)
        code = path.read_text(encoding="utf-8")
        return jsonify({"success": True, "code": code, "strategy": strategy_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/strategies/<strategy_name>/code", methods=["POST"])
def save_strategy_code(strategy_name):
    try:
        data = request.get_json() or {}
        code = data.get("code")
        if not isinstance(code, str):
            return jsonify({"success": False, "error": "Missing code"}), 400

        from .strategies import load_strategy

        load_strategy(strategy_name)
        path = _resolve_strategy_file_path(strategy_name)
        path.write_text(code, encoding="utf-8")

        module_name = f"spectr.strategies.{path.stem}"
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            importlib.import_module(module_name)

        return jsonify({"success": True, "message": "Strategy saved", "strategy": strategy_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/strategies/format-code", methods=["POST"])
def format_strategy_code():
    try:
        data = request.get_json() or {}
        code = data.get("code")
        if not isinstance(code, str):
            return jsonify({"success": False, "error": "Missing code"}), 400

        try:
            import black
        except Exception as e:
            return jsonify({"success": False, "error": f"Black formatter unavailable: {e}"}), 500

        formatted = black.format_str(code, mode=black.FileMode())
        return jsonify({"success": True, "code": formatted})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/strategies/evaluate/<symbol>", methods=["POST"])
def evaluate_strategy_signal(symbol):
    global data_api, broker_api

    symbol = _normalize_ticker(symbol)
    cfg = _get_strategy_config(symbol, create=False)
    strategy_active = bool(cfg.get("active", False))
    current_strategy = str(cfg.get("current") or "")
    strategy_auto_trade_enabled = bool(cfg.get("autoTradeEnabled", False))
    strategy_trade_amount = float(cfg.get("tradeAmount", 0.0) or 0.0)

    if not strategy_active or not current_strategy:
        return jsonify(
            {
                "success": True,
                "signal": None,
                "isNew": False,
                "ticker": symbol,
                "active": strategy_active,
                "current": current_strategy,
                "autoTradeEnabled": strategy_auto_trade_enabled,
                "tradeAmount": strategy_trade_amount,
            }
        )

    if not data_api:
        return jsonify({"success": False, "error": "Data API not initialized"}), 500

    try:
        from .strategies import load_strategy, metrics
        from .fetch.broker_interface import OrderSide
        from . import broker_tools

        strategy_cls = load_strategy(current_strategy)

        today = datetime.now().date()
        from_date = today.strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")
        df = data_api.fetch_chart_data(symbol, from_date=from_date, to_date=to_date)
        if df.empty:
            return jsonify({"success": True, "signal": None, "isNew": False})

        df = df.copy()
        idx = pd.to_datetime(df.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
        df.index = idx

        specs = strategy_cls.get_indicators()
        if specs:
            df = metrics.analyze_indicators(df, specs)

        position = None
        if broker_api and hasattr(broker_api, "get_position"):
            try:
                position = broker_api.get_position(symbol)
            except Exception:
                position = None

        signal = strategy_cls.detect_signals(df, symbol, position=position, orders=[])
        if not signal:
            return jsonify({"success": True, "signal": None, "isNew": False})

        signal_side = (signal.get("signal") or "").lower()
        signal_ts = df.index[-1].isoformat() if len(df.index) else ""
        signal_key = f"{current_strategy}:{symbol}:{signal_side}:{signal_ts}"
        last_signal_key = _last_strategy_signal_keys.get(symbol)
        is_new = signal_key != last_signal_key
        if is_new:
            _last_strategy_signal_keys[symbol] = signal_key

        execution = None
        if is_new and strategy_auto_trade_enabled and strategy_trade_amount > 0 and signal_side in {"buy", "sell"}:
            if not broker_api and data_api:
                broker_api = data_api
            if broker_api:
                side = OrderSide.BUY if signal_side == "buy" else OrderSide.SELL
                try:
                    price = float(signal.get("price") or 0.0)
                except (TypeError, ValueError):
                    price = 0.0

                order = broker_tools.submit_order(
                    broker_api,
                    symbol,
                    side,
                    price,
                    strategy_trade_amount,
                    True,
                    success_sound_path=None,
                )
                execution = {
                    "submitted": bool(order),
                    "orderId": getattr(order, "id", None) if order else None,
                    "side": side.name,
                }

        return jsonify(
            {
                "success": True,
                "signal": signal,
                "isNew": is_new,
                "ticker": symbol,
                "active": strategy_active,
                "current": current_strategy,
                "autoTradeEnabled": strategy_auto_trade_enabled,
                "tradeAmount": strategy_trade_amount,
                "execution": execution,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _save_cached_tickers():
    _sync_strategy_configs_with_watchlist()
    _save_strategy_configs()
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
    _sync_strategy_configs_with_watchlist()
    _save_strategy_configs()

    print(f"Starting web server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)


@app.route("/api/orders/cancel", methods=["POST"])
def cancel_order():
    global broker_api
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "success": False,
                "error": "Invalid JSON data"
            }), 400
        
        order_id = data.get('order_id')
        if not order_id:
            return jsonify({
                "success": False,
                "error": "Missing order_id"
            }), 400
        
        if not broker_api:
            from .fetch.alpaca import AlpacaInterface
            broker_api = AlpacaInterface(real_trades=False)
        
        if not broker_api:
            return jsonify({
                "success": False,
                "error": "Broker API not initialized"
            }), 500
        
        success = broker_api.cancel_order(order_id)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Order {order_id} cancelled successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Failed to cancel order {order_id}"
            }), 500
            
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error(f"Failed to cancel order: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


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
        
        from . import broker_tools
        
        # Use broker_tools to determine appropriate order type based on market hours
        # and after-hours settings. This will return MARKET or LIMIT with a limit price.
        global afterhours_enabled
        order_type, limit_price = broker_tools.prepare_order_details(
            symbol, side, broker_api, afterhours_enabled
        )
        
        if order_type == OrderType.MARKET:
            order = broker_api.submit_order(
                symbol=symbol,
                side=side,
                type=order_type,
                quantity=float(quantity),
                market_price=None
            )
        else:
            # For LIMIT orders, we need a limit price
            if limit_price is None:
                return jsonify({
                    "success": False,
                    "error": f"Cannot place {symbol} order - no quote available for extended hours trading"
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


voice_agent = None
voice_markdown_payload = None
voice_markdown_version = 0
voice_markdown_lock = threading.Lock()


def _store_voice_markdown(markdown: str, title: str | None = None):
    global voice_markdown_payload, voice_markdown_version

    payload = {
        "title": title,
        "markdown": markdown or "",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    with voice_markdown_lock:
        voice_markdown_version += 1
        payload["version"] = voice_markdown_version
        voice_markdown_payload = payload
    return {"status": "shown", "version": payload["version"]}


def _get_voice_markdown_since(version: int):
    with voice_markdown_lock:
        if voice_markdown_payload and voice_markdown_version > version:
            return dict(voice_markdown_payload)
    return None


def _get_voice_agent():
    global voice_agent

    if not voice_agent:
        from .agent import VoiceAgent
        voice_agent = VoiceAgent(
            broker_api=broker_api,
            data_api=data_api,
            show_markdown=_store_voice_markdown,
        )
    return voice_agent


@app.route("/api/voice-agent", methods=["POST"])
def handle_voice_agent():
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Invalid JSON data"}), 400
        
        transcript = data.get('transcript', '')
        
        if not transcript.strip():
            return jsonify({"success": False, "error": "No transcript provided"}), 400
        
        with voice_markdown_lock:
            start_markdown_version = voice_markdown_version

        voice_agent = _get_voice_agent()
        result = voice_agent.ask_with_text(transcript, speak=False)
        markdown_payload = _get_voice_markdown_since(start_markdown_version)
        
        return jsonify({
            "success": True,
            "response": result,
            "markdown": markdown_payload,
        })
    except Exception as e:
        log.error(f"Failed to handle voice agent: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/voice-agent/audio", methods=["POST"])
def handle_voice_agent_audio():
    tmp_path = None

    try:
        audio_file = request.files.get("audio")
        if audio_file is None:
            return jsonify({"success": False, "error": "Missing audio upload"}), 400

        suffix = os.path.splitext(audio_file.filename or "")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        with voice_markdown_lock:
            start_markdown_version = voice_markdown_version

        voice_agent = _get_voice_agent()
        with open(tmp_path, "rb") as f:
            transcription = voice_agent.client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=f,
            )

        transcript = (getattr(transcription, "text", "") or "").strip()
        if not transcript:
            return jsonify({"success": False, "error": "No speech detected in audio"}), 400

        result = voice_agent.ask_with_text(transcript, speak=False)
        markdown_payload = _get_voice_markdown_since(start_markdown_version)
        return jsonify({
            "success": True,
            "transcript": transcript,
            "response": result,
            "markdown": markdown_payload,
        })
    except Exception as e:
        log.error(f"Failed to handle voice agent audio: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.route("/api/voice-agent/tts", methods=["POST"])
def handle_voice_agent_tts():
    try:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"success": False, "error": "No text provided"}), 400

        voice_agent = _get_voice_agent()
        audio_bytes = voice_agent.synthesize_speech(text)
        if not audio_bytes:
            return jsonify({"success": False, "error": "No audio generated"}), 500

        return Response(
            audio_bytes,
            mimetype="audio/mpeg",
            headers={
                "Cache-Control": "no-store",
            },
        )
    except Exception as e:
        log.error(f"Failed to synthesize voice-agent speech: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/voice-agent/markdown", methods=["GET"])
def get_voice_agent_markdown():
    with voice_markdown_lock:
        payload = dict(voice_markdown_payload) if voice_markdown_payload else None
    return jsonify({
        "success": True,
        "markdown": payload,
    })


@app.route("/api/voice-agent/speaking", methods=["GET"])
def check_voice_agent_speaking():
    try:
        voice_agent = _get_voice_agent()
        is_speaking = voice_agent.is_speaking() if voice_agent else False
        return jsonify({
            "success": True,
            "speaking": is_speaking,
        })
    except Exception as e:
        log.error(f"Failed to check voice agent speaking status: {e}")
        return jsonify({"success": False, "speaking": False})


if __name__ == "__main__":
    start_server()
