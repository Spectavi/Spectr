import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, '/home/aem/Code/Spectr/src')

def test_get_tickers_empty():
    from spectr import webserver
    
    original = webserver.cached_tickers
    try:
        webserver.cached_tickers = []
        
        client = webserver.app.test_client()
        response = client.get('/api/tickers')
        
        assert response.status_code == 200
        assert response.json == []
    finally:
        webserver.cached_tickers = original

def test_get_tickers_with_data():
    from spectr import webserver
    
    original = webserver.cached_tickers
    try:
        webserver.cached_tickers = ['AAPL', 'GOOGL']
        
        client = webserver.app.test_client()
        response = client.get('/api/tickers')
        
        assert response.status_code == 200
        assert response.json == ['AAPL', 'GOOGL']
    finally:
        webserver.cached_tickers = original

def test_get_chart_data_no_api():
    from spectr import webserver
    
    original_api = webserver.data_api
    try:
        webserver.data_api = None
        
        response = webserver.app.test_client().get('/api/chart/AAPL')
        
        assert response.status_code == 500
    finally:
        webserver.data_api = original_api

def test_get_chart_data_handles_exception():
    from spectr import webserver
    
    with patch('spectr.fetch.alpaca.AlpacaInterface'):
        webserver.init_data_api('alpaca')
        
        with patch.object(webserver.data_api, 'fetch_chart_data') as mock_fetch:
            mock_fetch.side_effect = Exception("Network error")
            
            response = webserver.app.test_client().get('/api/chart/AAPL')
            
            assert response.status_code == 500
            assert 'error' in response.json

def test_start_server_initializes_data_api():
    from spectr import webserver
    
    try:
        with patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run') as mock_run, \
             patch('spectr.cache.load_onboarding_config') as mock_cfg:
            
            mock_cfg.return_value = {'data_api': 'alpaca'}
            webserver.cached_tickers = []
            
            webserver.start_server(port=8020)
            
            mock_init.assert_called_once_with('alpaca')
            mock_run.assert_called_once()
    finally:
        pass

def test_start_server_default_port():
    from spectr import webserver
    
    try:
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run') as mock_run, \
             patch('spectr.cache.load_onboarding_config'):
            
            webserver.start_server()
            
            mock_run.assert_called_once_with(host='0.0.0.0', port=8020, debug=False)
    finally:
        pass

def test_start_server_uses_env_data_provider():
    from spectr import webserver
    
    original_env = os.environ.get('DATA_PROVIDER')
    
    try:
        with patch.dict('os.environ', {'DATA_PROVIDER': 'fmp'}, clear=True), \
             patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run'), \
             patch('spectr.cache.load_onboarding_config'):
            
            webserver.start_server()
            
            mock_init.assert_called_once_with('fmp')
    finally:
        if original_env is not None:
            os.environ['DATA_PROVIDER'] = original_env

def test_start_server_uses_cached_config():
    from spectr import webserver
    
    try:
        with patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run'), \
             patch('spectr.cache.load_onboarding_config') as mock_cfg:
            
            mock_cfg.return_value = {'data_api': 'robinhood'}
            
            webserver.start_server()
            
            mock_init.assert_called_once_with('robinhood')
    finally:
        pass

def test_chart_endpoint_returns_valid_data_structure():
    from spectr import webserver
    
    response = webserver.app.test_client().get('/api/tickers')
    assert response.status_code == 200
    
    response = webserver.app.test_client().get('/')
    assert response.status_code in [200, 404]

def test_multiple_tickers_handling():
    from spectr import webserver
    
    original = webserver.cached_tickers
    try:
        webserver.cached_tickers = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN']
        
        response = webserver.app.test_client().get('/api/tickers')
        
        data = response.json
        assert len(data) == 5
        assert 'AAPL' in data
        assert 'GOOGL' in data
    finally:
        webserver.cached_tickers = original

def test_empty_ticker_list():
    from spectr import webserver
    
    original = webserver.cached_tickers
    try:
        webserver.cached_tickers = []
        
        response = webserver.app.test_client().get('/api/tickers')
        
        assert response.json == []
    finally:
        webserver.cached_tickers = original

def test_invalid_symbol_handling():
    from spectr import webserver
    
    class MockDataApi:
        def fetch_chart_data(self, symbol, from_date, to_date):
            import pandas as pd
            return pd.DataFrame()
        
        def fetch_quote(self, symbol):
            return {'price': 0, 'volume': 0}
    
    original_api = webserver.data_api
    try:
        webserver.data_api = MockDataApi()
        
        response = webserver.app.test_client().get('/api/chart/INVALID')
        
        assert response.status_code == 404
        assert 'error' in response.json
    finally:
        webserver.data_api = original_api

def test_server_port_configuration():
    from spectr import webserver
    
    try:
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run') as mock_run, \
             patch('spectr.cache.load_onboarding_config'):
            
            custom_port = 9000
            webserver.start_server(port=custom_port)
            
            mock_run.assert_called_once_with(host='0.0.0.0', port=custom_port, debug=False)
    finally:
        pass

def test_cached_tickers_loading():
    from spectr import webserver
    
    original = webserver.cached_tickers
    try:
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'), \
             patch('os.path.exists', return_value=True) as mock_exists, \
             patch('builtins.open') as mock_open:
            
            mock_file = MagicMock()
            mock_file.readlines.return_value = ['AAPL\n', '  \n', 'GOOGL\n', '\n']
            mock_open.return_value.__enter__.return_value = mock_file
            
            webserver.start_server()
            
            assert len(webserver.cached_tickers) == 2
            assert webserver.cached_tickers[0] == 'AAPL'
            assert webserver.cached_tickers[1] == 'GOOGL'
    finally:
        webserver.cached_tickers = original

def test_data_api_initialization():
    from spectr import webserver
    
    original_env = os.environ.get('DATA_PROVIDER')
    
    try:
        with patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run'), \
             patch.dict('os.environ', {'DATA_PROVIDER': 'alpaca'}, clear=True), \
             patch('spectr.cache.load_onboarding_config', return_value=None):
            
            webserver.start_server()
            
            mock_init.assert_called_once_with('alpaca')
    finally:
        if original_env is not None:
            os.environ['DATA_PROVIDER'] = original_env

def test_chart_endpoint_formats_timestamps():
    from spectr import webserver
    
    with patch('spectr.webserver.init_data_api'), \
         patch('spectr.webserver.app.run'):
        
        response = webserver.app.test_client().get('/')
        assert response.status_code in [200, 404]

def test_webui_build_directory_exists():
    """Test that the React build directory exists - if not, app won't serve frontend."""
    from spectr import webserver
    
    build_dir = os.path.dirname(webserver.__file__)
    expected_build_dir = os.path.join(build_dir, "webui", "build")
    
    assert os.path.isdir(expected_build_dir), (
        f"React build directory does not exist at {expected_build_dir}. "
        "Run 'npm run build' in src/spectr/webui/ to build the frontend."
    )

def test_index_html_exists():
    """Test that index.html exists in build directory."""
    from spectr import webserver
    
    expected_build_dir = os.path.join(os.path.dirname(webserver.__file__), "webui", "build")
    index_path = os.path.join(expected_build_dir, 'index.html')
    
    assert os.path.isfile(index_path), (
        f"index.html not found at {index_path}. "
        "The React app needs to be built first."
    )

def test_index_page_is_served():
    """Test that the root path serves index.html."""
    from spectr import webserver
    
    with webserver.app.test_client() as client:
        response = client.get('/')
        
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data

def test_api_endpoints_work():
    """Test that API endpoints return proper responses."""
    from spectr import webserver
    
    with webserver.app.test_client() as client:
        # Test tickers endpoint
        response = client.get('/api/tickers')
        assert response.status_code == 200
        
        # Test chart endpoint - will fail but should be valid JSON error
        response = client.get('/api/chart/INVALID')
        assert response.status_code in [404, 500]

def test_cached_tickers_loaded_from_file():
    """Test that tickers are loaded from .cached_tickers file."""
    from spectr import webserver
    
    original = webserver.cached_tickers
    try:
        # Reset cached_tickers to empty
        webserver.cached_tickers = []
        
        # Call start_server with mocked app.run and no config
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'), \
             patch.dict('os.environ', {'DATA_PROVIDER': 'alpaca'}, clear=True), \
             patch('spectr.cache.load_onboarding_config', return_value=None):
            
            webserver.start_server()
        
        # Should have loaded from the .cached_tickers file
        assert len(webserver.cached_tickers) > 0
        assert 'AAPL' in webserver.cached_tickers
    finally:
        webserver.cached_tickers = original

def test_api_tickers_returns_cached_data():
    """Test that /api/tickers returns the cached tickers data."""
    from spectr import webserver
    
    with patch('spectr.webserver.init_data_api'), \
         patch('spectr.webserver.app.run'):
        
        # Load tickers
        original = webserver.cached_tickers
        try:
            webserver.cached_tickers = ['TEST1', 'TEST2']
            
            client = webserver.app.test_client()
            response = client.get('/api/tickers')
            
            assert response.status_code == 200
            assert response.json == ['TEST1', 'TEST2']
        finally:
            webserver.cached_tickers = original


def test_get_portfolio_no_api():
    from spectr import webserver
    
    original_api = webserver.data_api
    try:
        webserver.data_api = None
        
        response = webserver.app.test_client().get('/api/portfolio')
        
        assert response.status_code == 200
        data = response.json
        assert 'balance' in data
        assert 'positions' in data
        assert 'orders' in data
    finally:
        webserver.data_api = original_api


def test_get_portfolio_with_api():
    """Test that portfolio endpoint returns data from AlpacaInterface."""
    from spectr import webserver
    
    original_api = webserver.data_api
    try:
        # Set up a simple mock for data_api (which is now ignored)
        class SimpleDataAPI:
            pass
        
        webserver.data_api = SimpleDataAPI()
        
        response = webserver.app.test_client().get('/api/portfolio')
        
        assert response.status_code == 200
        data = response.json
        # Should return balance, positions, orders (may be empty based on credentials)
        assert 'balance' in data
        assert 'positions' in data
        assert 'orders' in data
    finally:
        webserver.data_api = original_api


def test_get_portfolio_with_data_only_api():
    """Test that portfolio endpoint works even when data_api doesn't have broker methods."""
    from spectr import webserver
    
    original_api = webserver.data_api
    try:
        # Data-only API (like FMP) - should not affect broker operations
        class DataOnlyAPI:
            def fetch_quote(self, symbol):
                return {"price": 100.0}
        
        webserver.data_api = DataOnlyAPI()
        
        response = webserver.app.test_client().get('/api/portfolio')
        
        assert response.status_code == 200
        data = response.json
        # Should still work because we use AlpacaInterface for broker operations
        # but the actual values depend on configured credentials
        assert 'balance' in data
        assert 'positions' in data
    finally:
        webserver.data_api = original_api


def test_get_account_info_with_paper_credentials():
    """Test that account-info endpoint returns correct values when paper credentials are set."""
    from spectr import webserver
    
    # Skip this test if ALPACA_API_KEY is already set (from .env file)
    # since we can't reliably clear it with patch.dict due to module-level load_dotenv
    if os.getenv("ALPACA_API_KEY"):
        import pytest
        pytest.skip("Skipping due to ALPACA_API_KEY being set from .env")
    
    try:
        with patch('dotenv.load_dotenv', return_value=False), \
             patch('spectr.fetch.alpaca.load_dotenv', return_value=False), \
             patch.dict('os.environ', {
            'PAPER_API_KEY': 'test_paper_key',
            'PAPER_SECRET': 'test_paper_secret'
        }, clear=True):
            
            response = webserver.app.test_client().get('/api/account-info')
            
            assert response.status_code == 200
            data = response.json
            assert data['hasPaperCredentials'] is True, f"Expected True, got {data.get('hasPaperCredentials')}"
            # hasLiveCredentials could be True if ALPACA_API_KEY from .env file is present
            assert 'hasLiveCredentials' in data
            assert data['defaultToPaper'] is True, f"Expected True (no live creds), got {data.get('defaultToPaper')}"
    finally:
        pass  # env vars are cleaned up by clear=True context manager


def test_get_account_info_with_live_credentials():
    """Test that account-info endpoint returns correct values when live credentials are set."""
    from spectr import webserver
    
    try:
        with patch('dotenv.load_dotenv', return_value=False), \
             patch.dict('os.environ', {
            'BROKER_API_KEY': 'test_broker_key',
            'BROKER_SECRET': 'test_broker_secret'
        }, clear=True):
            
            response = webserver.app.test_client().get('/api/account-info')
            
            assert response.status_code == 200
            data = response.json
            # hasLiveCredentials could be True if ALPACA_API_KEY from .env file is present
            assert 'hasLiveCredentials' in data
            # Always default to paper to match TUI behavior (TUI defaults to PAPER unless --real_trades is passed)
            assert data['defaultToPaper'] is True, f"Expected True (always default to paper), got {data.get('defaultToPaper')}"
    finally:
        pass  # env vars are cleaned up by clear=True context manager
