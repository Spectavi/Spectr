import React, { useState, useEffect, useCallback, useMemo } from 'react';
import TradingViewWidget from './TradingViewWidget';

const chartCache = new Map();
const CACHE_DURATION = 5 * 60 * 1000;

function ChartContainer({ ticker }) {
  const [chartData, setChartData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticker) return;

    setLoading(true);
    setError(null);
    setChartData(null);

    if (chartCache.has(ticker) && Date.now() - chartCache.get(ticker).time < CACHE_DURATION) {
      const cachedData = chartCache.get(ticker).data;
      setChartData(cachedData);
      setLoading(false);
      setError(null);
      return;
    }

    const fetchData = async () => {
      try {
        const res = await fetch(`/api/chart/${ticker}`);
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        const data = await res.json();
        
        chartCache.set(ticker, { data, time: Date.now() });
        setChartData(data);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [ticker]);

  const renderContent = useMemo(() => {
    if (loading && !chartData) {
      return (
        <div style={containerStyle}>
          <p style={{ textAlign: 'center', marginTop: '50px' }}>Loading chart data...</p>
        </div>
      );
    }

    if (error && !chartData) {
      return (
        <div style={containerStyle}>
          <p style={{ color: '#f85149', textAlign: 'center', marginTop: '50px' }}>
            Error: {error}
          </p>
        </div>
      );
    }

    if (chartData) {
      return (
        <>
          <h2 style={{ margin: '0 0 10px 0', padding: '10px 20px' }}>
            {chartData.symbol} - 1 Minute
          </h2>
          <TradingViewWidget data={chartData} ticker={ticker} />
        </>
      );
    }

    return null;
  }, [loading, error, chartData, ticker]);

  return <div style={containerStyle}>{renderContent}</div>;
}

const containerStyle = {
  flex: 1,
  backgroundColor: '#0d1117',
  display: 'flex',
  flexDirection: 'column',
};

export default ChartContainer;
