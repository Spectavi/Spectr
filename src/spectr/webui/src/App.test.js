import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
      if (url.includes('/api/tickers')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockTickers)
        });
      }
      
      const ticker = url.split('/').pop();
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
    const responses = [
      Promise.resolve({ ok: true, json: () => Promise.resolve(mockTickers) }),
      Promise.resolve({ ok: true, json: () => Promise.resolve(mockChartResponse('AAPL')) }),
      Promise.resolve({ ok: true, json: () => Promise.resolve(mockChartResponse('GOOGL')) })
    ];

    for (const response of responses) {
      window.fetch.mockResolvedValueOnce(response);
    }

    render(<App />);

    await waitFor(() => expect(screen.getByText('TradingView Chart')).toBeInTheDocument(), { timeout: 5000 });

    const goojlTicker = screen.getByText('GOOGL');
    fireEvent.click(goojlTicker);

    await waitFor(() => {
      expect(screen.getByTestId('mock-tradingview')).toHaveAttribute('data-ticker', 'GOOGL');
    }, { timeout: 5000 });
  });

  test('navigates through multiple tickers successfully', async () => {
    const responses = [
      Promise.resolve({ ok: true, json: () => Promise.resolve(mockTickers) }),
      ...mockTickers.map(ticker => 
        Promise.resolve({ ok: true, json: () => Promise.resolve(mockChartResponse(ticker)) })
      )
    ];

    for (const response of responses) {
      window.fetch.mockResolvedValueOnce(response);
    }

    render(<App />);

    await waitFor(() => expect(screen.getByText('TradingView Chart')).toBeInTheDocument(), { timeout: 5000 });

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
    window.fetch
      .mockResolvedValueOnce(Promise.resolve({ ok: true, json: () => Promise.resolve(mockTickers) }))
      .mockResolvedValueOnce(Promise.resolve({ ok: false, status: 404 }));

    render(<App />);

    await waitFor(() => expect(screen.getByText(/Error:/)).toBeInTheDocument());
  });
});
