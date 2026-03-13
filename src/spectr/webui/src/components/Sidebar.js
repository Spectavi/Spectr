import React, { useState } from 'react';
import WatchlistDialog from './WatchlistDialog';

function Sidebar({ tickers, selectedTicker, onSelect }) {
  const [collapsed, setCollapsed] = useState(false);
  const [showWatchlistDialog, setShowWatchlistDialog] = useState(false);

  const handleAddTicker = (ticker) => {
    fetch('/api/watchlist', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ticker }),
    })
      .then(res => res.json())
      .then(data => {
        if (data.success && data.tickers) {
          window.dispatchEvent(new CustomEvent('tickersUpdated'));
        }
      })
      .catch(err => console.error('Failed to add ticker:', err));
  };

  const handleRemoveTicker = (ticker) => {
    fetch(`/api/watchlist/${ticker}`, {
      method: 'DELETE',
    })
      .then(res => res.json())
      .then(data => {
        if (data.success && data.tickers) {
          window.dispatchEvent(new CustomEvent('tickersUpdated'));
        }
      })
      .catch(err => console.error('Failed to remove ticker:', err));
  };

  if (tickers.length === 0) {
    return (
      <div style={sidebarStyle}>
        <p style={{ textAlign: 'center', padding: '20px' }}>No tickers available</p>
      </div>
    );
  }

  return (
    <>
      <div style={collapsed ? collapsedStyle : sidebarStyle}>
        <button
          onClick={() => setCollapsed(!collapsed)}
          style={{
            ...toggleButtonStyle,
            position: collapsed ? 'static' : { right: '0', top: '0' },
            ...(collapsed ? {} : { position: 'absolute', right: '0', top: '0' })
          }}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? '»' : '«'}
        </button>

        {!collapsed && (
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
            <div style={{ position: 'relative', margin: '40px 0 10px' }}>
              <h3 style={{ textAlign: 'center', margin: 0 }}>Watchlist</h3>
              <button
                onClick={() => setShowWatchlistDialog(true)}
                style={{
                  position: 'absolute',
                  right: '-5px',
                  top: '0',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '16px',
                  color: '#8b949e',
                  padding: '5px 10px',
                }}
                title="Manage Watchlist"
              >
                ⚙️
              </button>
            </div>
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

      {showWatchlistDialog && (
        <WatchlistDialog
          onClose={() => setShowWatchlistDialog(false)}
          tickers={tickers}
          onAddTicker={handleAddTicker}
          onRemoveTicker={handleRemoveTicker}
        />
      )}
    </>
  );
}

const sidebarStyle = {
  width: '200px',
  backgroundColor: '#161b22',
  borderRight: '1px solid #30363d',
  display: 'flex',
  flexDirection: 'column',
  position: 'relative',
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
  padding: '0',
  margin: '0',
};

const tickerItemStyle = {
  padding: '8px',
  cursor: 'pointer',
  textAlign: 'center',
  transition: 'background-color 0.2s',
};

export default Sidebar;
