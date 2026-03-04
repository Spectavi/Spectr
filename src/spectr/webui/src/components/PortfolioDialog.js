import React, { useState, useEffect } from 'react';

function PortfolioDialog({ onClose }) {
  const [balance, setBalance] = useState({});
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/api/portfolio')
      .then(res => res.json())
      .then(data => {
        setBalance(data.balance || {});
        setPositions(data.positions || []);
        setOrders(data.orders || []);
        setLoading(false);
        setError(data.error || null);
      })
      .catch(err => {
        console.error('Failed to load portfolio:', err);
        setError('Failed to load portfolio data');
        setLoading(false);
      });
  }, []);

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(value || 0);
  };

  if (loading) {
    return (
      <div style={overlayStyle}>
        <div style={dialogStyle}>
          <h2>Portfolio</h2>
          <p>Loading...</p>
          <button onClick={onClose} style={closeButtonStyle}>Close</button>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={overlayStyle}>
        <div style={dialogStyle}>
          <h2>Portfolio</h2>
          <p style={{ color: '#f85149' }}>{error}</p>
          <button onClick={onClose} style={closeButtonStyle}>Close</button>
        </div>
      </div>
    );
  }

  const cash = balance.cash || 0;
  const buying_power = balance.buying_power || 0;
  const portfolio_value = balance.portfolio_value || 0;

  return (
    <div style={overlayStyle}>
      <div style={dialogStyle}>
        <h2>Portfolio</h2>
        
        <div style={balancesContainerStyle}>
          <div style={balanceBoxStyle}>
            <span>Cash:</span>
            <strong>{formatCurrency(cash)}</strong>
          </div>
          <div style={balanceBoxStyle}>
            <span>Buying Power:</span>
            <strong>{formatCurrency(buying_power)}</strong>
          </div>
          <div style={balanceBoxStyle}>
            <span>Portfolio Value:</span>
            <strong>{formatCurrency(portfolio_value)}</strong>
          </div>
        </div>

        <h3>Positions</h3>
        {positions.length > 0 ? (
          <table style={tableStyle}>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Value</th>
                <th>Avg Cost</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, idx) => (
                <tr key={idx}>
                  <td>{pos.symbol}</td>
                  <td>{pos.qty}</td>
                  <td>{formatCurrency(pos.market_value)}</td>
                  <td>{formatCurrency(pos.avg_entry_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No positions</p>
        )}

        <h3>Transaction History</h3>
        {orders.length > 0 ? (
          <table style={tableStyle}>
            <thead>
              <tr>
                <th>Date/Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Value</th>
                <th>Type</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order, idx) => (
                <tr key={idx}>
                  <td>{order.datetime}</td>
                  <td>{order.symbol}</td>
                  <td>{order.side}</td>
                  <td>{order.qty}</td>
                  <td>{formatCurrency(order.value)}</td>
                  <td>{order.order_type}</td>
                  <td>{order.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No transactions</p>
        )}

        <button onClick={onClose} style={closeButtonStyle}>Close</button>
      </div>
    </div>
  );
}

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
  padding: '24px',
  maxWidth: '700px',
  width: '90%',
  maxHeight: '90vh',
  overflowY: 'auto',
};

const balancesContainerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  marginBottom: '20px',
  padding: '15px',
  backgroundColor: '#0d1117',
  borderRadius: '6px',
};

const balanceBoxStyle = {
  textAlign: 'center',
};

const tableStyle = {
  width: '100%',
  borderCollapse: 'collapse',
  marginTop: '10px',
  marginBottom: '20px',
};

const closeButtonStyle = {
  backgroundColor: '#da3633',
  color: '#ffffff',
  border: 'none',
  padding: '8px 16px',
  borderRadius: '6px',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: '600',
};

export default PortfolioDialog;
