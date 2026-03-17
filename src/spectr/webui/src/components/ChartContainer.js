import React, { useState, useEffect, useCallback, useMemo } from 'react';
import TradingViewWidget from './TradingViewWidget';
import OrderDialog from './OrderDialog';
import SettingsDialog from './SettingsDialog';
import { OrderSide } from './OrderDialog';

const chartCache = new Map();
const CACHE_DURATION = 5 * 60 * 1000;

function ChartContainer({ ticker }) {
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [strategyActive, setStrategyActive] = useState(false);
  const [chartData, setChartData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [orderDialogSide, setOrderDialogSide] = useState(null);
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const res = await fetch('/api/strategies');
        const data = await res.json();
        setStrategies(data.strategies || []);
        setSelectedStrategy(data.current || '');
        setStrategyActive(data.active || false);
      } catch (err) {
        console.error('Failed to load strategies:', err);
      }
    };
    fetchStrategies();
  }, []);

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

  const handleStrategySelect = useCallback((strategyName) => {
    if (!strategyName) return;
    
    const wasActive = strategyActive;
    
    fetch(`/api/strategies/${strategyName}`, { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deactivatePrevious: true })
    })
      .then(res => {
        if (!res.ok) throw new Error(`Failed to select strategy: ${res.statusText}`);
        return res.json();
      })
      .then(data => {
        console.log('Strategy selected:', data);
        setSelectedStrategy(strategyName);
        if (data.active !== undefined) {
          setStrategyActive(data.active);
        }
      })
      .catch(err => {
        console.error('Failed to select strategy:', err);
      });
  }, [strategyActive]);

  const handleToggleStrategy = () => {
    const newActiveState = !strategyActive;
    setStrategyActive(newActiveState);
    fetch(`/api/strategies/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: newActiveState })
    })
      .then(res => res.json())
      .catch(err => console.error('Failed to toggle strategy:', err));
  };

  const renderContent = useMemo(() => {
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
          <header style={headerStyle}>
            <h2 style={{ margin: 0 }}>{chartData.symbol} - 1 Minute</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <select key="strategy-select-loaded"
                value={selectedStrategy}
                onChange={(e) => handleStrategySelect(e.target.value)}
                style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  border: '1px solid #30363d',
                  backgroundColor: '#161b22',
                  color: '#c9d1d9',
                  fontSize: '14px',
                  cursor: 'pointer',
                }}
              >
                <option value="">Select strategy...</option>
                {strategies.map((strategy) => (
                  <option key={strategy} value={strategy}>
                    {strategy}
                  </option>
                ))}
              </select>
              <button
                onClick={handleToggleStrategy}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '14px',
                  color: '#ffffff',
                  backgroundColor: strategyActive ? '#238636' : '#da3633',
                  transition: 'opacity 0.2s, transform 0.1s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.9'; }}
                onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.98)'; }}
                onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
              >
                {strategyActive ? 'Deactivate' : 'Activate'}
              </button>
            </div>
            <div style={buttonContainerStyle}>
              <button
                onClick={() => setOrderDialogSide(OrderSide.BUY)}
                style={{
                  ...orderButtonStyle,
                  backgroundColor: '#238636',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.9'; }}
                onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.98)'; }}
                onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
              >
                BUY
              </button>
              <button
                onClick={() => setOrderDialogSide(OrderSide.SELL)}
                style={{
                  ...orderButtonStyle,
                  backgroundColor: '#da3633',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.9'; }}
                onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
                onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.98)'; }}
                onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
              >
            SELL
              </button>
            </div>
          </header>
          <TradingViewWidget data={chartData} ticker={ticker} />
          {orderDialogSide && (
            <OrderDialog
              ticker={ticker}
              side={orderDialogSide}
              onClose={() => setOrderDialogSide(null)}
            />
          )}
          {showSettings && (
            <SettingsDialog onClose={() => setShowSettings(false)} />
          )}
        </>
      );
    }

    return (
      <>
        <header style={headerStyle}>
          <h2 style={{ margin: 0 }}>{ticker} - 1 Minute</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <select
              value={selectedStrategy}
              onChange={(e) => handleStrategySelect(e.target.value)}
              style={{
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #30363d',
                backgroundColor: '#161b22',
                color: '#c9d1d9',
                fontSize: '14px',
                cursor: 'pointer',
              }}
            >
              <option value="">Select strategy...</option>
              {strategies.map((strategy) => (
                <option key={strategy} value={strategy}>
                  {strategy}
                </option>
              ))}
            </select>
            <button
              onClick={handleToggleStrategy}
              style={{
                padding: '8px 16px',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: '14px',
                color: '#ffffff',
                backgroundColor: strategyActive ? '#238636' : '#da3633',
                transition: 'opacity 0.2s, transform 0.1s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.9'; }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
              onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.98)'; }}
              onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
            >
              {strategyActive ? 'Deactivate' : 'Activate'}
            </button>
          </div>
          <div style={buttonContainerStyle}>
            <button
              onClick={() => setOrderDialogSide(OrderSide.BUY)}
              style={{
                ...orderButtonStyle,
                backgroundColor: '#238636',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.9'; }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
              onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.98)'; }}
              onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
            >
              BUY
            </button>
            <button
              onClick={() => setOrderDialogSide(OrderSide.SELL)}
              style={{
                ...orderButtonStyle,
                backgroundColor: '#da3633',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.9'; }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
              onMouseDown={(e) => { e.currentTarget.style.transform = 'scale(0.98)'; }}
              onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
            >
          SELL
            </button>
          </div>
        </header>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '24px', color: '#58a6ff', marginBottom: '10px' }}>
              Loading chart data...
            </div>
            <div style={{ fontSize: '14px', color: '#8b949e' }}>Fetching data for {ticker}</div>
          </div>
        </div>
      </>
    );
  }, [loading, error, chartData, ticker, orderDialogSide, showSettings, strategies, selectedStrategy, strategyActive]);

  return <div style={containerStyle}>{renderContent}</div>;
}

const headerStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '10px 20px',
  borderBottom: '1px solid #30363d',
};

const buttonContainerStyle = {
  display: 'flex',
  gap: '10px',
};

const orderButtonStyle = {
  padding: '8px 20px',
  borderRadius: '6px',
  border: 'none',
  cursor: 'pointer',
  fontWeight: '600',
  fontSize: '14px',
  color: '#ffffff',
  transition: 'opacity 0.2s, transform 0.1s',
};

const containerStyle = {
  flex: 1,
  backgroundColor: '#0d1117',
  display: 'flex',
  flexDirection: 'column',
};

export default ChartContainer;
