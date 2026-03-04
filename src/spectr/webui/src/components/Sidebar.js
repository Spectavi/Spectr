import React, { useState, useEffect } from 'react';
import PortfolioDialog from './PortfolioDialog';

function Sidebar({ tickers, selectedTicker, onSelect }) {
  const [collapsed, setCollapsed] = useState(false);
  const [showPortfolio, setShowPortfolio] = useState(false);

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
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <button
            onClick={() => setShowPortfolio(true)}
            style={portfolioButtonStyle}
          >
            Portfolio
          </button>
          
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
        </div>
      )}
      
      {showPortfolio && (
        <PortfolioDialog onClose={() => setShowPortfolio(false)} />
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

const portfolioButtonStyle = {
  margin: '10px',
  padding: '8px 12px',
  backgroundColor: '#58a6ff',
  color: '#ffffff',
  border: 'none',
  borderRadius: '6px',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: '600',
};

const tickerListStyle = {
  listStyle: 'none',
  padding: '5px',
  margin: '0',
};

const tickerItemStyle = {
  padding: '10px',
  cursor: 'pointer',
  textAlign: 'center',
  transition: 'background-color 0.2s',
};

export default Sidebar;
