import React from 'react';
import { OrderSide } from './OrderDialog';

function TickerChartHeader({
  selectedTicker,
  tickers,
  tickerDetails,
  onTickerChange,
  onToggleWatchlistDialog,
  strategyControls,
  headerTradeControls,
  buttonContainerStyle,
  orderButtonStyle,
  setOrderDialogSide,
  setOrderDialogTicker,
  setOrderDialogTradeAmount
}) {
  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      flexWrap: 'wrap',
      gap: '10px',
      padding: '10px 20px',
      borderBottom: '1px solid #30363d',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <select
          value={selectedTicker}
          onChange={(e) => onTickerChange(e.target.value)}
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
          {tickers.map((t) => (
            <option key={t} value={t}>
              {tickerDetails[t] ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <img src={tickerDetails[t]} alt="" style={{ width: '20px', height: '20px' }} />
                  <span>{t}</span>
                </div>
              ) : (
                t
              )}
            </option>
          ))}
        </select>
        <button
          onClick={onToggleWatchlistDialog}
          title="Watchlist"
          style={{
            padding: '8px',
            borderRadius: '6px',
            border: '1px solid #30363d',
            backgroundColor: '#161b22',
            color: '#c9d1d9',
            cursor: 'pointer',
          }}
        >
          ⚙️
        </button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {strategyControls}
        {headerTradeControls}
      </div>
      <div style={buttonContainerStyle}>
        <button
          onClick={() => {
            setOrderDialogTicker(selectedTicker);
            setOrderDialogTradeAmount(null);
            setOrderDialogSide(OrderSide.BUY);
          }}
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
          onClick={() => {
            setOrderDialogTicker(selectedTicker);
            setOrderDialogTradeAmount(null);
            setOrderDialogSide(OrderSide.SELL);
          }}
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
  );
}

export default TickerChartHeader;
