import React, { useState, useEffect } from 'react';
import PortfolioDialog from './PortfolioDialog';

function Sidebar({ tickers, selectedTicker, onSelect, onStrategyChange }) {
  const [collapsed, setCollapsed] = useState(false);
  const [showPortfolio, setShowPortfolio] = useState(false);
  const [showOrder, setShowOrder] = useState(false);
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [strategyActive, setStrategyActive] = useState(false);
  const [autoTradeEnabled, setAutoTradeEnabled] = useState(false);

  useEffect(() => {
    fetch('/api/strategies')
      .then(res => res.json())
      .then(data => {
        setStrategies(data.strategies || []);
        setSelectedStrategy(data.current || '');
        setStrategyActive(data.active || false);
        setAutoTradeEnabled(data.autoTradeEnabled || false);
      })
      .catch(err => console.error('Failed to load strategies:', err));
  }, []);

  const handleStrategySelect = (strategyName) => {
    setSelectedStrategy(strategyName);
    fetch(`/api/strategies/${strategyName}`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        if (data.success && onStrategyChange) {
          onStrategyChange(strategyName, data.active);
        }
      })
      .catch(err => console.error('Failed to select strategy:', err));
  };

  const handleToggleStrategy = () => {
    const newActiveState = !strategyActive;
    setStrategyActive(newActiveState);
    fetch(`/api/strategies/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: newActiveState })
    })
      .then(res => res.json())
      .then(data => {
        if (data.success && onStrategyChange) {
          onStrategyChange(selectedStrategy, newActiveState);
        }
      })
      .catch(err => console.error('Failed to toggle strategy:', err));
  };

  const handleToggleAutoTrade = () => {
    const newEnabledState = !autoTradeEnabled;
    setAutoTradeEnabled(newEnabledState);
    fetch(`/api/strategies/auto-trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: newEnabledState })
    })
      .then(res => res.json())
      .catch(err => console.error('Failed to toggle auto-trade:', err));
  };

  if (tickers.length === 0) {
    return (
      <div style={sidebarStyle}>
        <p style={{ textAlign: 'center', padding: '20px' }}>No tickers available</p>
      </div>
    );
  }

  return (
    <div style={collapsed ? collapsedStyle : sidebarStyle}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        style={toggleButtonStyle}
        title={collapsed ? "Expand" : "Collapse"}
      >
        {collapsed ? '»' : '«'}
      </button>

      {!collapsed && (
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          <h3
            onClick={() => setShowPortfolio(true)}
            style={portfolioStyle}
          >
            Portfolio
          </h3>

          <h3
            onClick={() => setShowOrder(true)}
            style={{ ...portfolioStyle, cursor: 'pointer' }}
          >
            Order
          </h3>

          <h3 style={{ textAlign: 'center', margin: '10px 0' }}>Tickers</h3>
          <ul style={tickerListStyle}>
            {tickers.map((ticker) => (
              <li
                key={ticker}
                style={{
                  ...tickerItemStyle,
                  backgroundColor:
                    selectedTicker === ticker ? '#238636' : 'transparent',
                }}
                onClick={() => onSelect(ticker)}
              >
                {ticker}
              </li>
            ))}
          </ul>

          <div style={{ padding: '10px' }}>
            <select
              value={selectedStrategy}
              onChange={(e) => handleStrategySelect(e.target.value)}
              style={selectStyle}
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
                ...toggleButtonStyle,
                width: '100%',
                marginTop: '5px',
                backgroundColor: strategyActive ? '#238636' : '#da3633',
                color: 'white',
                padding: '8px',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {strategyActive ? 'Deactivate' : 'Activate'}
            </button>

            <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '12px', color: '#c9d1d9' }}>Auto-trade</span>
              <button
                onClick={handleToggleAutoTrade}
                style={{
                  ...toggleButtonStyle,
                  width: '50px',
                  height: '24px',
                  backgroundColor: autoTradeEnabled ? '#238636' : '#333',
                  borderRadius: '12px',
                  position: 'relative',
                  padding: 0,
                }}
              >
                <div
                  style={{
                    width: '16px',
                    height: '16px',
                    backgroundColor: 'white',
                    borderRadius: '50%',
                    position: 'absolute',
                    left: autoTradeEnabled ? '28px' : '4px',
                    top: '4px',
                    transition: 'left 0.2s',
                  }}
                />
              </button>
            </div>
          </div>
        </div>
      )}

      {showPortfolio && (
        <PortfolioDialog onClose={() => setShowPortfolio(false)} />
      )}

      {showOrder && (
        <div style={overlayStyle}>
          <div style={dialogStyle}>
            <h2 style={{ margin: '0 0 15px 0', color: '#c9d1d9' }}>Place Order - {selectedTicker}</h2>
            <p style={{ color: '#8b949e', marginBottom: '20px' }}>
              Select order type and quantity to place a trade
            </p>
            
            <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
              <button
                onClick={() => setShowOrder(false)}
                style={{
                  ...toggleButtonStyle,
                  flex: 1,
                  backgroundColor: '#333',
                  color: '#c9d1d9',
                  padding: '12px',
                  borderRadius: '6px',
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: '600',
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const sidebarStyle = {
  width: '200px',
  backgroundColor: '#161b22',
  borderRight: '1px solid #30363d',
  display: 'flex',
  flexDirection: 'column',
};

const collapsedStyle = {
  width: '40px',
  backgroundColor: '#161b22',
  borderRight: '1px solid #30363d',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
};

const toggleButtonStyle = {
  padding: '10px',
  background: 'none',
  border: 'none',
  color: '#8b949e',
  cursor: 'pointer',
  fontSize: '16px',
};

const portfolioStyle = {
  margin: '10px 0',
  textAlign: 'center',
  color: '#58a6ff',
  cursor: 'pointer',
  fontWeight: '600',
  textDecoration: 'none',
};

const tickerListStyle = {
  listStyle: 'none',
  padding: '0',
  margin: '0',
};

const tickerItemStyle = {
  padding: '8px',
  cursor: 'pointer',
  textAlign: 'center',
  transition: 'background-color 0.2s',
};

const selectStyle = {
  width: '100%',
  padding: '8px',
  borderRadius: '4px',
  border: '1px solid #30363d',
  backgroundColor: '#161b22',
  color: '#c9d1d9',
  marginBottom: '5px',
};

const overlayStyle = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.7)',
  zIndex: 1000,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

const dialogStyle = {
  backgroundColor: '#161b22',
  border: '1px solid #30363d',
  borderRadius: '8px',
  padding: '25px',
  minWidth: '400px',
  maxWidth: '500px',
  boxShadow: '0 10px 30px rgba(0, 0, 0, 0.3)',
};

export default Sidebar;
