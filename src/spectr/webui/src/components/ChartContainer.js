import React, { useState, useEffect } from 'react';
import TradingViewWidget from './TradingViewWidget';

function ChartContainer({ ticker, loading }) {
  const [chartData, setChartData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;

    setLoading(true);
    setError(null);

    fetch(`/api/chart/${ticker}`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
      })
      .then(data => {
        setChartData(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [ticker]);

  if (loading) {
    return (
      <div style={containerStyle}>
        <p style={{ textAlign: 'center', marginTop: '50px' }}>Loading chart data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={containerStyle}>
        <p style={{ color: '#f85149', textAlign: 'center', marginTop: '50px' }}>
          Error: {error}
        </p>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      {chartData && (
        <>
          <h2 style={{ margin: '0 0 10px 0', padding: '10px 20px' }}>
            {chartData.symbol} - 1 Minute
          </h2>
          <TradingViewWidget data={chartData} />
        </>
      )}
    </div>
  );
}

const containerStyle = {
  flex: 1,
  backgroundColor: '#0d1117',
  display: 'flex',
  flexDirection: 'column',
};

function setLoading(isLoading) {
  if (isLoading) {
    document.body.style.cursor = 'wait';
  } else {
    document.body.style.cursor = 'default';
  }
}

export default ChartContainer;
