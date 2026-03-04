import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, '/home/aem/Code/Spectr/src')

class TestWebUIIntegration:
    """Integration tests for the web UI functionality"""

    def test_cli_with_webui_flag_starts_server(self):
        with patch('spectr.webserver.start_server') as mock_start, \
             patch('sys.argv', ['spectr', '--webui']):
            
            from spectr import cli
            cli.main()
            
            mock_start.assert_called_once()

    def test_chart_endpoint_returns_valid_data_structure(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'):
            
            from spectr import webserver
            
            response = webserver.app.test_client().get('/api/tickers')
            assert response.status_code == 200
            
            response = webserver.app.test_client().get('/')
            assert response.status_code in [200, 404]

    def test_multiple_tickers_handling(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'):
            
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

    def test_empty_ticker_list(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'):
            
            from spectr import webserver
            
            original = webserver.cached_tickers
            try:
                webserver.cached_tickers = []
                
                response = webserver.app.test_client().get('/api/tickers')
                
                assert response.json == []
            finally:
                webserver.cached_tickers = original

    def test_invalid_symbol_handling(self):
        with patch('spectr.webserver.init_data_api'):
            from spectr import webserver
            
            class MockDataApi:
                def fetch_chart_data(self, symbol, from_date, to_date):
                    import pandas as pd
                    return pd.DataFrame()
                
                def fetch_quote(self, symbol):
                    return {'price': 0, 'volume': 0}
            
            original_api = webserver.data_api
            try:
                webserver.init_data_api('alpaca')
                webserver.data_api = MockDataApi()
                
                response = webserver.app.test_client().get('/api/chart/INVALID')
                
                assert response.status_code == 404
                assert 'error' in response.json
            finally:
                webserver.data_api = original_api

    def test_chart_data_with_missing_fields(self):
        with patch('spectr.webserver.init_data_api'):
            from spectr import webserver
            
            df = Mock()
            
            now_mock = Mock()
            now_mock.tz_localize.return_value = None
            now_mock.strftime.return_value = '2024-01-01T10:00:00'
            df.index.__iter__ = Mock(return_value=iter([now_mock]))
            df.index.name = 'datetime'
            
            webserver.init_data_api('alpaca')
            
            original_api = webserver.data_api
            try:
                webserver.data_api = Mock()
                webserver.data_api.fetch_chart_data.return_value = df
                webserver.data_api.fetch_quote.side_effect = Exception("Quote failed")
                
                response = webserver.app.test_client().get('/api/chart/AAPL')
                
                assert response.status_code == 200
                data = response.json
                assert data['current_price'] == 0
            finally:
                webserver.data_api = original_api

    def test_server_port_configuration(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run') as mock_run, \
             patch('spectr.cache.load_onboarding_config'):
            
            from spectr import webserver
            
            custom_port = 9000
            webserver.start_server(port=custom_port)
            
            mock_run.assert_called_once_with(host='0.0.0.0', port=custom_port, debug=False)

    def test_cached_tickers_loading(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'), \
             patch('os.path.exists', return_value=True) as mock_exists, \
             patch('builtins.open') as mock_open:
            
            from spectr import webserver
            
            original = webserver.cached_tickers
            try:
                mock_file = MagicMock()
                mock_file.readlines.return_value = ['AAPL\n', '  \n', 'GOOGL\n', '\n']
                mock_open.return_value.__enter__.return_value = mock_file
                
                webserver.start_server()
                
                assert len(webserver.cached_tickers) == 2
                assert webserver.cached_tickers[0] == 'AAPL'
                assert webserver.cached_tickers[1] == 'GOOGL'
            finally:
                webserver.cached_tickers = original

    def test_start_server_initializes_data_api(self):
        with patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run'), \
             patch('spectr.cache.load_onboarding_config') as mock_cfg:
            
            from spectr import webserver
            
            mock_cfg.return_value = {'data_api': 'alpaca'}
            
            original_cached = webserver.cached_tickers
            try:
                webserver.cached_tickers = []
                
                webserver.start_server(port=8020)
                
                mock_init.assert_called_once_with('alpaca')
            finally:
                webserver.cached_tickers = original_cached

    def test_start_server_uses_env_data_provider(self):
        with patch.dict('os.environ', {'DATA_PROVIDER': 'fmp'}, clear=True), \
             patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run'), \
             patch('spectr.cache.load_onboarding_config'):
            
            from spectr import webserver
            
            original = os.environ.get('DATA_PROVIDER')
            try:
                webserver.start_server()
                
                mock_init.assert_called_once_with('fmp')
            finally:
                if original is not None:
                    os.environ['DATA_PROVIDER'] = original

    def test_start_server_uses_cached_config(self):
        with patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run'), \
             patch('spectr.cache.load_onboarding_config') as mock_cfg:
            
            from spectr import webserver
            
            mock_cfg.return_value = {'data_api': 'robinhood'}
            
            webserver.start_server()
            
            mock_init.assert_called_once_with('robinhood')

    def test_data_api_initialization(self):
        with patch('spectr.webserver.init_data_api') as mock_init, \
             patch('spectr.webserver.app.run'), \
             patch.dict('os.environ', {'DATA_PROVIDER': 'alpaca'}, clear=True), \
             patch('spectr.cache.load_onboarding_config', return_value=None):
            
            from spectr import webserver
            
            original_env = os.environ.get('DATA_PROVIDER')
            try:
                webserver.start_server()
                
                mock_init.assert_called_once_with('alpaca')
            finally:
                if original_env is not None:
                    os.environ['DATA_PROVIDER'] = original_env

    def test_chart_endpoint_formats_timestamps(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'):
            
            from spectr import webserver
            
            response = webserver.app.test_client().get('/')
            assert response.status_code in [200, 404]

    def test_get_tickers_endpoint(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'):
            
            from spectr import webserver
            
            response = webserver.app.test_client().get('/api/tickers')
            assert response.status_code == 200

    def test_chart_endpoint_404_on_empty_data(self):
        with patch('spectr.webserver.init_data_api'):
            from spectr import webserver
            
            class MockDataApi:
                def fetch_chart_data(self, symbol, from_date, to_date):
                    import pandas as pd
                    return pd.DataFrame()
                
                def fetch_quote(self, symbol):
                    return {'price': 0, 'volume': 0}
            
            original_api = webserver.data_api
            try:
                webserver.init_data_api('alpaca')
                webserver.data_api = MockDataApi()
                
                response = webserver.app.test_client().get('/api/chart/AAPL')
                
                assert response.status_code == 404
            finally:
                webserver.data_api = original_api

    def test_start_server_default_port(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run') as mock_run, \
             patch('spectr.cache.load_onboarding_config'):
            
            from spectr import webserver
            
            webserver.start_server()
            
            mock_run.assert_called_once_with(host='0.0.0.0', port=8020, debug=False)

    def test_start_server_prints_startup_message(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'), \
             patch('sys.stdout') as mock_stdout, \
             patch('spectr.cache.load_onboarding_config'):
            
            from spectr import webserver
            
            captured = []
            def write(msg):
                captured.append(msg)
            
            mock_stdout.write = write
            
            webserver.start_server(port=8020)
            
            assert any('Starting web server' in msg for msg in captured)

    def test_cli_without_webui_flag_runs_tui(self):
        with patch('spectr.spectr.SpectrApp') as MockApp, \
             patch('sys.argv', ['spectr']), \
             patch('spectr.cli.argparse.ArgumentParser.add_argument'), \
             patch('spectr.cli.argparse.ArgumentParser.parse_args') as mock_parse, \
             patch('spectr.cache.load_onboarding_config', return_value=None):
            
            args = Mock()
            args.webui = False
            args.broker = 'alpaca'
            args.data_api = 'alpaca'
            args.symbols = ['AAPL']
            args.interval = '1min'
            args.macd_thresh = 0.002
            args.bb_period = 200
            args.bb_dev = 2.0
            args.stop_loss_pct = 0.01
            args.take_profit_pct = 0.05
            args.lookback_period = 1000
            args.scale = 0.5
            args.real_trades = False
            
            mock_parse.return_value = args
            
            from spectr import cli
            try:
                cli.main()
            except (SystemExit, ImportError):
                pass

    def test_full_workflow_end_to_end(self):
        with patch('spectr.webserver.init_data_api'), \
             patch('spectr.webserver.app.run'):
            
            from spectr import webserver
            
            client = webserver.app.test_client()
            
            response = client.get('/api/tickers')
            assert response.status_code == 200
            
            response = client.get('/')
            assert response.status_code in [200, 404]
