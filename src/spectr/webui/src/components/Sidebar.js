import React, { useState } from 'react';

function Sidebar({ tickers, selectedTicker, onSelect }) {
  const [collapsed, setCollapsed] = useState(false);

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
