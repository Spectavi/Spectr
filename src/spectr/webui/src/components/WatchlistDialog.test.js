import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import WatchlistDialog from './WatchlistDialog';

describe('WatchlistDialog Search', () => {
  const mockTickers = ['AAPL', 'GOOGL'];
  
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn().mockResolvedValue({
      json: () => Promise.resolve({ data: [] })
    });
  });

  afterEach(() => {
    global.fetch.mockRestore();
  });

  test('should not throw error when search box is used', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    
    const onClose = jest.fn();
    const onAddTicker = jest.fn();

    render(
      <WatchlistDialog 
        onClose={onClose} 
        tickers={mockTickers}
        onAddTicker={onAddTicker}
        onRemoveTicker={() => {}}
      />
    );

    const searchInput = screen.getByPlaceholderText('Search tickers...');
    
    fireEvent.change(searchInput, { target: { value: 'MS' } });
    
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/search-tickers?query=MS');
    });

    expect(consoleErrorSpy).not.toHaveBeenCalledWith(
      expect.stringContaining('No onAutocomplete handler provided'),
      expect.any(Object)
    );

    consoleErrorSpy.mockRestore();
  });
});
