import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import ChartContainer from './components/ChartContainer';

function App() {
  const [tickers, setTickers] = useState([]);
  const [selectedTicker, setSelectedTicker] = useState('AAPL');

  useEffect(() => {
    fetch('/api/tickers')
      .then(res => res.json())
      .then(data => {
        if (data.length > 0) {
          setTickers(data);
          if (!data.includes(selectedTicker)) {
            setSelectedTicker(data[0]);
          }
        }
      })
      .catch(err => console.error('Failed to load tickers:', err));

    const handleTickersUpdated = () => {
      fetch('/api/tickers')
        .then(res => res.json())
        .then(data => {
          setTickers(data);
          if (data.length > 0 && !data.includes(selectedTicker)) {
            setSelectedTicker(data[0]);
          }
        })
        .catch(err => console.error('Failed to reload tickers:', err));
    };

    window.addEventListener('tickersUpdated', handleTickersUpdated);

    return () => {
      window.removeEventListener('tickersUpdated', handleTickersUpdated);
    };
  }, [selectedTicker]);

  const handleSelect = useCallback((ticker) => {
    setSelectedTicker(ticker);
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <Sidebar
        tickers={tickers}
        selectedTicker={selectedTicker}
        onSelect={handleSelect}
      />
      <ChartContainer ticker={selectedTicker} />
    </div>
  );
}

export default App;
