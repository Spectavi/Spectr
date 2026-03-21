import React, { useState, useEffect, useCallback, useMemo } from 'react';
import TradingViewWidget from './TradingViewWidget';
import OrderDialog from './OrderDialog';
import SettingsDialog from './SettingsDialog';
import StrategyDialog from './StrategyDialog';
import WatchlistDialog from './WatchlistDialog';
import TickerChartHeader from './TickerChartHeader';
import { OrderSide } from './OrderDialog';

const chartCache = new Map();
const CACHE_DURATION = 5 * 60 * 1000;

function TickerChartWidget({ ticker, onTickerChange }) {
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [strategyActive, setStrategyActive] = useState(false);
  const [strategyAutoTradeEnabled, setStrategyAutoTradeEnabled] = useState(false);
  const [strategyTradeAmount, setStrategyTradeAmount] = useState('');
  const [chartData, setChartData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [orderDialogSide, setOrderDialogSide] = useState(null);
  const [orderDialogTicker, setOrderDialogTicker] = useState(ticker);
  const [orderDialogTradeAmount, setOrderDialogTradeAmount] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showStrategyDialog, setShowStrategyDialog] = useState(false);
  const [showWatchlistDialog, setShowWatchlistDialog] = useState(false);
  const [tickers, setTickers] = useState([]);
  const [tickerDetails, setTickerDetails] = useState({});
  const [selectedTicker, setSelectedTicker] = useState(ticker);
  const [strategyCode, setStrategyCode] = useState('');
  const [strategyCodeLoading, setStrategyCodeLoading] = useState(false);
  const [strategyCodeError, setStrategyCodeError] = useState('');

  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const res = await fetch('/api/strategies');
        const data = await res.json();
        setStrategies(data.strategies || []);
        if (data.current) {
          setSelectedStrategy(data.current);
        }
        setStrategyActive(data.active || false);
        setStrategyAutoTradeEnabled(Boolean(data.autoTradeEnabled));
        setStrategyTradeAmount(
          data.tradeAmount !== undefined && data.tradeAmount !== null ? String(data.tradeAmount) : ''
        );
      } catch (err) {
        console.error('Failed to load strategies:', err);
      }
    };
    fetchStrategies();
  }, []);

  useEffect(() => {
    const fetchTickers = async () => {
      try {
        const res = await fetch('/api/tickers');
        const data = await res.json();
        if (data.length > 0) setTickers(data);
      } catch (err) { console.error('Failed to load tickers:', err); }
    };
    fetchTickers();
  }, []);

  useEffect(() => {
    if (tickers.length > 0) {
      const promises = tickers.map((ticker) =>
        fetch(`/api/profile/${ticker}`)
          .then(res => res.json())
          .then(data => { if (data && data.logo) return { ticker, logo: data.logo }; return null; })
          .catch(err => { console.error(`Failed to fetch profile for ${ticker}:`, err); return null; })
      );
      Promise.all(promises).then(results => {
        const details = {};
        results.forEach(result => { if (result) details[result.ticker] = result.logo; });
        setTickerDetails(details);
      });
    }
  }, [tickers]);

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

  useEffect(() => {
    setOrderDialogTicker(selectedTicker);
  }, [selectedTicker]);

  useEffect(() => {
    if (selectedTicker !== ticker) setSelectedTicker(ticker);
  }, [ticker]);

  const handleTickerChange = useCallback((newTicker) => {
    if (newTicker !== ticker && onTickerChange) { onTickerChange(newTicker); }
    setSelectedTicker(newTicker);
  }, [ticker, onTickerChange]);

  const handleStrategySelect = useCallback((strategyName) => {
    if (!strategyName) return;

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
  }, []);

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

  const playVoiceAlert = useCallback(async (text) => {
    try {
      const response = await fetch('/api/voice-agent/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) {
        throw new Error(`Voice alert failed (${response.status})`);
      }
      const audioBlob = await response.blob();
      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      audio.onerror = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (err) {
      console.error('Unable to play signal alert:', err);
    }
  }, []);

  const handleTradeAmountChange = useCallback((value) => {
    setStrategyTradeAmount(value);

    fetch('/api/strategies/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tradeAmount: value === '' ? 0 : value }),
    })
      .then(res => res.json())
      .then(data => {
        if (data.tradeAmount !== undefined && data.tradeAmount !== null) {
          setStrategyTradeAmount(String(data.tradeAmount));
        }
      })
      .catch(err => console.error('Failed to save trade amount:', err));
  }, []);

  const handleToggleAutoTrade = useCallback(() => {
    const nextState = !strategyAutoTradeEnabled;
    setStrategyAutoTradeEnabled(nextState);

    fetch('/api/strategies/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        autoTradeEnabled: nextState,
        tradeAmount: strategyTradeAmount === '' ? 0 : strategyTradeAmount,
      }),
    })
      .then(res => res.json())
      .then(data => {
        if (data.autoTradeEnabled !== undefined) {
          setStrategyAutoTradeEnabled(Boolean(data.autoTradeEnabled));
        }
        if (data.active !== undefined) {
          setStrategyActive(Boolean(data.active));
        }
      })
      .catch(err => console.error('Failed to toggle auto-trade:', err));
  }, [strategyAutoTradeEnabled, strategyTradeAmount]);

  const loadStrategyCode = useCallback(async (strategyName) => {
    if (!strategyName) {
      setStrategyCode('');
      setStrategyCodeError('');
      return;
    }

    setStrategyCodeLoading(true);
    setStrategyCodeError('');
    try {
      const res = await fetch(`/api/strategies/${strategyName}/code`);
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to load strategy code');
      }
      setStrategyCode(data.code || '');
    } catch (err) {
      setStrategyCodeError(err.message);
    } finally {
      setStrategyCodeLoading(false);
    }
  }, []);

  const handleFormatCode = useCallback(async () => {
    setStrategyCodeError('');
    try {
      const res = await fetch('/api/strategies/format-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: strategyCode }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to format code');
      }
      setStrategyCode(data.code || '');
    } catch (err) {
      setStrategyCodeError(err.message);
    }
  }, [strategyCode]);

  const handleSaveCode = useCallback(async () => {
    if (!selectedStrategy) return;
    setStrategyCodeError('');
    try {
      const res = await fetch(`/api/strategies/${selectedStrategy}/code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: strategyCode }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to save code');
      }
    } catch (err) {
      setStrategyCodeError(err.message);
    }
  }, [selectedStrategy, strategyCode]);

  useEffect(() => {
    loadStrategyCode(selectedStrategy);
  }, [selectedStrategy]);

  useEffect(() => {
    if (!ticker || !strategyActive || !selectedStrategy) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/strategies/evaluate/${ticker}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json();
        if (!res.ok || !data.success || !data.signal || !data.isNew) {
          return;
        }

        const signal = (data.signal.signal || '').toLowerCase();
        if (signal !== 'buy' && signal !== 'sell') {
          return;
        }

        const signalLabel = signal === 'buy' ? 'Buy' : 'Sell';
        const signalSymbol = (data.signal.symbol || ticker).toUpperCase();
        const reason = data.signal.reason ? `. ${data.signal.reason}` : '';
        const hasTradeAmount = parseFloat(strategyTradeAmount || '0') > 0;
        const autoTradingNow = Boolean(data.autoTradeEnabled) && hasTradeAmount;
        const autoTradeExecuted = Boolean(data.execution && data.execution.submitted);

        if (autoTradeExecuted) {
          playVoiceAlert(`Auto-trade ${signalLabel.toLowerCase()} signal executed for ${signalSymbol}${reason}`);
          return;
        }

        if (autoTradingNow) {
          playVoiceAlert(`${signalLabel} signal for ${signalSymbol}${reason}`);
          return;
        }

        if (signal === 'buy') {
          setOrderDialogTicker(signalSymbol);
          setOrderDialogTradeAmount(strategyTradeAmount === '' ? null : parseFloat(strategyTradeAmount));
          setOrderDialogSide(OrderSide.BUY);
        }

        playVoiceAlert(`${signalLabel} signal for ${signalSymbol}${reason}`);
      } catch (err) {
        console.error('Failed to evaluate strategy signal:', err);
      }
    }, 15000);

    return () => clearInterval(interval);
  }, [ticker, selectedStrategy, strategyActive, strategyTradeAmount, playVoiceAlert]);

  const strategyControls = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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
  );

  const headerTradeControls = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <label style={{ fontSize: '12px', color: '#8b949e' }}>Trade Amount</label>
        <input
          type="number"
          min="0"
          step="0.01"
          value={strategyTradeAmount}
          onChange={(e) => handleTradeAmountChange(e.target.value)}
          style={{
            width: '75px',
            padding: '6px 8px',
            borderRadius: '4px',
            border: '1px solid #30363d',
            backgroundColor: '#161b22',
            color: '#c9d1d9',
            fontSize: '13px',
          }}
          placeholder="0.00"
        />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <label style={{ fontSize: '12px', color: '#8b949e' }}>Auto-Trade</label>
        <button
          onClick={handleToggleAutoTrade}
          aria-pressed={strategyAutoTradeEnabled}
          title={strategyAutoTradeEnabled ? 'Disable auto-trade' : 'Enable auto-trade'}
          style={{
            width: '48px',
            height: '26px',
            borderRadius: '999px',
            border: '1px solid #30363d',
            cursor: 'pointer',
            padding: '2px',
            display: 'inline-flex',
            alignItems: 'center',
            backgroundColor: strategyAutoTradeEnabled ? '#238636' : '#30363d',
            transition: 'background-color 0.2s ease',
          }}
        >
          <span
            style={{
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              backgroundColor: '#ffffff',
              transform: strategyAutoTradeEnabled ? 'translateX(22px)' : 'translateX(0)',
              transition: 'transform 0.2s ease',
            }}
          />
        </button>
      </div>
    </div>
  );

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
          <TickerChartHeader
            selectedTicker={selectedTicker}
            tickers={tickers}
            tickerDetails={tickerDetails}
            onTickerChange={handleTickerChange}
            showWatchlistDialog={showWatchlistDialog}
            onToggleWatchlistDialog={() => setShowWatchlistDialog(true)}
            strategyControls={strategyControls}
            headerTradeControls={headerTradeControls}
            buttonContainerStyle={buttonContainerStyle}
            orderButtonStyle={orderButtonStyle}
            setOrderDialogSide={setOrderDialogSide}
            setOrderDialogTicker={setOrderDialogTicker}
            setOrderDialogTradeAmount={setOrderDialogTradeAmount}
          />
          <TradingViewWidget data={chartData} ticker={ticker} />
          {orderDialogSide && (
            <OrderDialog
              ticker={orderDialogTicker}
              side={orderDialogSide}
              defaultTradeAmount={orderDialogTradeAmount}
              onClose={() => {
                setOrderDialogSide(null);
                setOrderDialogTradeAmount(null);
              }}
            />
          )}
          {showSettings && (
            <SettingsDialog onClose={() => setShowSettings(false)} />
          )}
          {showStrategyDialog && (
            <StrategyDialog
              open={showStrategyDialog}
              onClose={() => setShowStrategyDialog(false)}
              strategies={strategies}
              selectedStrategy={selectedStrategy}
              strategyActive={strategyActive}
              autoTradeEnabled={strategyAutoTradeEnabled}
              tradeAmount={strategyTradeAmount}
              strategyCode={strategyCode}
              codeLoading={strategyCodeLoading}
              codeError={strategyCodeError}
              onStrategySelect={handleStrategySelect}
              onToggleStrategy={handleToggleStrategy}
              onToggleAutoTrade={handleToggleAutoTrade}
              onTradeAmountChange={handleTradeAmountChange}
              onCodeChange={setStrategyCode}
              onFormatCode={handleFormatCode}
              onSaveCode={handleSaveCode}
            />
          )}
        </>
      );
    }

return (
        <>
          <TickerChartHeader
            selectedTicker={selectedTicker}
            tickers={tickers}
            tickerDetails={tickerDetails}
            onTickerChange={handleTickerChange}
            showWatchlistDialog={showWatchlistDialog}
            onToggleWatchlistDialog={() => setShowWatchlistDialog(true)}
            strategyControls={strategyControls}
            headerTradeControls={headerTradeControls}
            buttonContainerStyle={buttonContainerStyle}
            orderButtonStyle={orderButtonStyle}
            setOrderDialogSide={setOrderDialogSide}
            setOrderDialogTicker={setOrderDialogTicker}
            setOrderDialogTradeAmount={setOrderDialogTradeAmount}
          />
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '24px', color: '#58a6ff', marginBottom: '10px' }}>
              Loading chart data...
            </div>
            <div style={{ fontSize: '14px', color: '#8b949e' }}>Fetching data for {ticker}</div>
          </div>
        </div>
        {showStrategyDialog && (
          <StrategyDialog
            open={showStrategyDialog}
            onClose={() => setShowStrategyDialog(false)}
            strategies={strategies}
            selectedStrategy={selectedStrategy}
            strategyActive={strategyActive}
            autoTradeEnabled={strategyAutoTradeEnabled}
            tradeAmount={strategyTradeAmount}
            strategyCode={strategyCode}
            codeLoading={strategyCodeLoading}
            codeError={strategyCodeError}
            onStrategySelect={handleStrategySelect}
            onToggleStrategy={handleToggleStrategy}
            onToggleAutoTrade={handleToggleAutoTrade}
            onTradeAmountChange={handleTradeAmountChange}
            onCodeChange={setStrategyCode}
            onFormatCode={handleFormatCode}
            onSaveCode={handleSaveCode}
          />
        )}
      </>
    );
  }, [
    error,
    chartData,
    ticker,
    orderDialogSide,
    orderDialogTicker,
    orderDialogTradeAmount,
    showSettings,
    strategies,
    selectedStrategy,
    strategyActive,
    showStrategyDialog,
    strategyAutoTradeEnabled,
    strategyTradeAmount,
    strategyCode,
    strategyCodeLoading,
    strategyCodeError,
    strategyControls,
    handleStrategySelect,
    handleToggleAutoTrade,
    handleTradeAmountChange,
    handleFormatCode,
    handleSaveCode,
  ]);

  return (
    <>
      {showWatchlistDialog && (
        <WatchlistDialog
          onClose={() => setShowWatchlistDialog(false)}
          tickers={tickers}
          onAddTicker={(ticker) => {
            fetch('/api/watchlist', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ ticker }),
            }).then(res => res.json()).then(data => {
              if (data.success && data.tickers) {
                setTickers(data.tickers);
                window.dispatchEvent(new CustomEvent('tickersUpdated'));
              }
            }).catch(err => console.error('Failed to add ticker:', err));
          }}
          onRemoveTicker={(ticker) => {
            fetch(`/api/watchlist/${ticker}`, { method: 'DELETE' })
              .then(res => res.json())
              .then(data => {
                if (data.success && data.tickers) {
                  setTickers(data.tickers);
                  window.dispatchEvent(new CustomEvent('tickersUpdated'));
                }
              })
              .catch(err => console.error('Failed to remove ticker:', err));
          }}
          onReorderTicker={(newOrder) => {
            fetch('/api/watchlist/reorder', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ tickers: newOrder }),
            })
              .then(res => res.json())
              .then(data => {
                if (data.success && data.tickers) {
                  setTickers(data.tickers);
                  window.dispatchEvent(new CustomEvent('tickersUpdated'));
                }
              })
              .catch(err => console.error('Failed to reorder tickers:', err));
          }}
        />
      )}
      <div style={containerStyle}>{renderContent}</div>
    </>
  );
}

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

export default TickerChartWidget;
