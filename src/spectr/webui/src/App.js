import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChartContainer from './components/ChartContainer';

function App() {
  const [tickers, setTickers] = useState([]);
  const [selectedTicker, setSelectedTicker] = useState('AAPL');
  const [loading, setLoading] = useState(false);

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
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <Sidebar
        tickers={tickers}
        selectedTicker={selectedTicker}
        onSelect={setSelectedTicker}
      />
      <ChartContainer ticker={selectedTicker} loading={loading} />
    </div>
  );
}

export default App;
