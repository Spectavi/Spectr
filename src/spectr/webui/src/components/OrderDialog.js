import React, { useState, useEffect } from 'react';

const OrderType = {
  MARKET: 'MARKET',
  LIMIT: 'LIMIT'
};

const OrderSide = {
  BUY: 'BUY',
  SELL: 'SELL'
};

function OrderDialog({ ticker, side, defaultTradeAmount = null, onClose }) {
  const [symbol, setSymbol] = useState(ticker);
  const [price, setPrice] = useState(0);
  const [qty, setQty] = useState('');
  const [qtyTouched, setQtyTouched] = useState(false);
  const [limitPrice, setLimitPrice] = useState('');
  const [orderType, setOrderType] = useState(OrderType.MARKET);
  const [posQty, setPosQty] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setSymbol(ticker);
    setQtyTouched(false);
  }, [ticker]);

  useEffect(() => {
    if (side === OrderSide.BUY) {
      if (defaultTradeAmount === null || defaultTradeAmount === undefined || defaultTradeAmount === 'SELL_ALL') return;
      if (qtyTouched) return;
      if (!price || price <= 0) return;

      const amount = parseFloat(defaultTradeAmount);
      if (!Number.isFinite(amount) || amount <= 0) return;
      setQty((amount / price).toFixed(5));
    } else if (side === OrderSide.SELL && defaultTradeAmount === 'SELL_ALL') {
      if (qtyTouched) return;
      if (posQty !== null && posQty > 0) {
        setQty(posQty.toFixed(5));
      }
    }
  }, [defaultTradeAmount, side, qtyTouched, price, posQty]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [symbol]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`/api/chart/${symbol}`);
      if (!res.ok) throw new Error('Failed to fetch chart data');
      const data = await res.json();
      
      if (data.current_price > 0) {
        setPrice(data.current_price);
      }
      
      const posRes = await fetch('/api/portfolio');
      if (posRes.ok) {
        const portfolioData = await posRes.json();
        const position = portfolioData.positions?.find(p => p.symbol === symbol.toUpperCase());
        if (position) {
          setPosQty(parseFloat(position.qty));
        } else {
          setPosQty(0);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const calculateTotal = () => {
    if (orderType === OrderType.MARKET) {
      return parseFloat(qty || 0) * price;
    } else {
      return parseFloat(qty || 0) * parseFloat(limitPrice || 0);
    }
  };

  const handleSubmit = async () => {
    setLoading(true);
    
    try {
      const payload = {
        symbol: symbol.toUpperCase(),
        side: side,
        type: orderType,
        quantity: parseFloat(qty),
        limit_price: orderType === OrderType.LIMIT ? parseFloat(limitPrice) : null
      };

      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || 'Failed to submit order');
      }

      onClose();
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(value || 0);
  };

  if (loading && price === 0) {
    return (
      <div style={overlayStyle}>
        <div style={dialogStyle}>
          <h2>{side.toUpperCase()} {symbol}</h2>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  const total = calculateTotal();

  return (
    <div style={overlayStyle}>
      <div style={dialogStyle}>
        <h2 style={{ margin: '0 0 15px 0', color: '#c9d1d9' }}>
          {side.toUpperCase()} {symbol}
        </h2>

        {error && (
          <p style={{ color: '#f85149', marginBottom: '15px' }}>{error}</p>
        )}

        <div style={formRowStyle}>
          <label style={formLabelStyle}>Symbol:</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            style={{ ...inputStyle, textTransform: 'uppercase' }}
            placeholder="Enter ticker symbol"
          />
        </div>

        <div style={infoContainerStyle}>
          {defaultTradeAmount !== null && defaultTradeAmount !== undefined && (
            <p style={infoTextStyle}>
              Trade amount preset:{' '}
              <span style={{ color: '#58a6ff' }}>
                {formatCurrency(parseFloat(defaultTradeAmount) || 0)}
              </span>
            </p>
          )}
          <p style={infoTextStyle}>
            Price: <span style={{ color: '#58a6ff' }}>{formatCurrency(price)}</span>{' '}
            <span style={{ color: '#8b949e', fontSize: '12px' }}>
              (auto-updates every 10 secs)
            </span>
          </p>

          <p style={infoTextStyle}>
            Current position:{' '}
            {posQty === null ? (
              <span style={{ color: '#f85149' }}>N/A (fetching)</span>
            ) : posQty > 0 ? (
              <span style={{ color: '#58a6ff' }}>
                {posQty} @ {formatCurrency(price)}
              </span>
            ) : (
              <span style={{ color: '#d29922' }}>NO POSITION!</span>
            )}
          </p>
        </div>

        <div style={formRowStyle}>
          <label style={formLabelStyle}>Type:</label>
          <select
            value={orderType}
            onChange={(e) => setOrderType(e.target.value)}
            style={inputStyle}
          >
            <option value={OrderType.MARKET}>Market</option>
            <option value={OrderType.LIMIT}>Limit</option>
          </select>
        </div>

        <div style={formRowStyle}>
          <label style={formLabelStyle}>Qty:</label>
          <input
            type="number"
            step="any"
            placeholder="0"
            value={qty}
            onChange={(e) => {
              setQtyTouched(true);
              setQty(e.target.value);
            }}
            style={inputStyle}
          />
        </div>

        {orderType === OrderType.LIMIT && (
          <div style={formRowStyle}>
            <label style={formLabelStyle}>Limit $:</label>
            <input
              type="number"
              step="0.01"
              placeholder="0.00"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              style={inputStyle}
            />
          </div>
        )}

        <p style={totalTextStyle}>
          {orderType === OrderType.MARKET 
            ? `Market Order total: ${formatCurrency(total)}`
            : `Limit Order total: ${formatCurrency(total)}`}
        </p>

        <div style={buttonRowStyle}>
          <button
            onClick={handleSubmit}
            style={{
              ...toggleButtonStyle,
              flex: 1,
              backgroundColor: '#238636',
              padding: '12px',
              borderRadius: '6px',
              border: 'none',
              cursor: 'pointer',
              fontWeight: '600',
            }}
          >
            {side.toUpperCase()}
          </button>
          <button
            onClick={onClose}
            style={{
              ...toggleButtonStyle,
              flex: 1,
              backgroundColor: '#da3633',
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
  maxWidth: '500px',
  width: '90%',
  maxHeight: '90vh',
  overflowY: 'auto',
};

const infoContainerStyle = {
  marginBottom: '20px',
  padding: '15px',
  backgroundColor: '#0d1117',
  borderRadius: '6px',
};

const infoTextStyle = {
  margin: '8px 0',
  color: '#c9d1d9',
  fontSize: '14px',
};

const formRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
  marginBottom: '15px',
};

const formLabelStyle = {
  minWidth: '80px',
  color: '#c9d1d9',
  fontWeight: '600',
};

const inputStyle = {
  flex: 1,
  padding: '10px',
  borderRadius: '6px',
  border: '1px solid #30363d',
  backgroundColor: '#161b22',
  color: '#c9d1d9',
  fontSize: '14px',
};

const totalTextStyle = {
  margin: '15px 0',
  padding: '15px',
  backgroundColor: '#0d1117',
  borderRadius: '6px',
  textAlign: 'center',
  color: '#d29922',
  fontSize: '16px',
  fontWeight: '600',
};

const buttonRowStyle = {
  display: 'flex',
  gap: '10px',
  marginTop: '20px',
};

const toggleButtonStyle = {
  padding: '10px',
  background: 'none',
  border: 'none',
  color: '#c9d1d9',
  cursor: 'pointer',
  fontSize: '14px',
  fontWeight: '600',
};

export { OrderSide, OrderType };

export default OrderDialog;
