import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from './App';

jest.mock('./components/TradingViewWidget.js', () => {
  return function MockTradingViewWidget({ data, ticker }) {
    return (
      <div data-testid="mock-tradingview" data-ticker={ticker} data-symbol={data?.symbol}>
        TradingView Chart
      </div>
    );
  };
});

jest.mock('./components/PortfolioDialog.js', () => {
  return function MockPortfolioDialog({ onClose }) {
    return (
      <div data-testid="mock-portfolio">
        Portfolio
        <button onClick={onClose}>Close</button>
      </div>
    );
  };
});

jest.mock('./components/Sidebar.js', () => {
  return function MockSidebar({ tickers, onSelect }) {
    return (
      <div data-testid="mock-sidebar">
        {tickers.map((ticker) => (
          <button key={ticker} onClick={() => onSelect(ticker)}>
            {ticker}
          </button>
        ))}
      </div>
    );
  };
});

describe('App Navigation', () => {
  const mockTickers = ['AAPL', 'GOOGL', 'MSFT', 'TSLA'];
  
  const mockChartResponse = (ticker) => ({
    symbol: ticker,
    data: [
      { timestamp: '2024-01-01', open: 100, high: 105, low: 98, close: 103, volume: 1000 },
      { timestamp: '2024-01-02', open: 103, high: 108, low: 101, close: 106, volume: 1500 },
    ]
  });

  beforeEach(() => {
    jest.clearAllMocks();
    window.fetch = jest.fn().mockImplementation((url) => {
      const requestUrl = String(url);

      if (requestUrl.includes('/api/tickers')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockTickers)
        });
      }

      if (requestUrl.includes('/api/strategies/evaluate/')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, signal: null, isNew: false })
        });
      }

      if (requestUrl.includes('/api/strategies')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            strategies: ['CustomStrategy'],
            current: '',
            active: false,
            autoTradeEnabled: false,
            tradeAmount: 0
          })
        });
      }

      const ticker = requestUrl.split('/').pop();
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockChartResponse(ticker))
      });
    });
  });

  afterEach(() => {
    window.fetch.mockRestore();
  });

  test('renders with initial ticker AAPL and chart loads', async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByText('TradingView Chart')).toBeInTheDocument(), { timeout: 5000 });
  });

  test('navigates to different ticker and chart loads successfully', async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByText('TradingView Chart')).toBeInTheDocument(), { timeout: 5000 });

    await waitFor(() => expect(screen.getByText('GOOGL')).toBeInTheDocument(), { timeout: 5000 });
    const goojlTicker = screen.getByText('GOOGL');
    fireEvent.click(goojlTicker);

    await waitFor(() => {
      expect(screen.getByTestId('mock-tradingview')).toHaveAttribute('data-ticker', 'GOOGL');
    }, { timeout: 5000 });
  });

  test('navigates through multiple tickers successfully', async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByText('TradingView Chart')).toBeInTheDocument(), { timeout: 5000 });
    await waitFor(() => expect(screen.getByText('GOOGL')).toBeInTheDocument(), { timeout: 5000 });

    for (let i = 1; i < mockTickers.length; i++) {
      const ticker = mockTickers[i];
      
      const tickerElement = screen.getByText(ticker);
      fireEvent.click(tickerElement);

      await waitFor(() => {
        expect(screen.getByTestId('mock-tradingview')).toHaveAttribute('data-ticker', ticker);
      }, { timeout: 5000 });
    }
  });

  test('handles chart loading error gracefully', async () => {
    window.fetch.mockImplementation((url) => {
      const requestUrl = String(url);

      if (requestUrl.includes('/api/tickers')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(['ERR1'])
        });
      }
      if (requestUrl.includes('/api/strategies')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            strategies: ['CustomStrategy'],
            current: '',
            active: false,
            autoTradeEnabled: false,
            tradeAmount: 0
          })
        });
      }
      if (requestUrl.includes('/api/chart/')) {
        return Promise.resolve({ ok: false, status: 404, statusText: 'Not Found' });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true, signal: null, isNew: false })
      });
    });

    render(<App />);

    await waitFor(() => expect(screen.getByText('ERR1')).toBeInTheDocument(), { timeout: 5000 });
    fireEvent.click(screen.getByText('ERR1'));
    await waitFor(() => expect(screen.getByText(/Error:/)).toBeInTheDocument());
  });
});
