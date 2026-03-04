import React, { useEffect, useRef } from 'react';

function TradingViewWidget({ data }) {
  const containerRef = useRef(null);
  const scriptRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !data) return;

    const symbol = data.symbol;
    const chartData = data.data || [];

    if (scriptRef.current) {
      scriptRef.current.remove();
    }

    const script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.defer = true;
    script.onload = () => {
      if (window.TradingView) {
        new window.TradingView.widget({
          autosize: true,
          symbol: symbol,
          interval: '1',
          timezone: 'Etc/UTC',
          theme: 'dark',
          style: '1',
          locale: 'en',
          toolbar_bg: '#f1f3f6',
          enable_publishing: false,
          allow_symbol_change: true,
          container_id: containerRef.current.id,
          datafeed: {
            getBars: function(symbolInfo, resolution, from, to, callback) {
              if (chartData.length === 0) {
                callback([]);
                return;
              }
              
              const bars = chartData.map(bar => ({
                time: new Date(bar.timestamp).getTime(),
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close,
                volume: bar.volume
              }));
              
              callback(bars);
            },
            subscribe: function(symbolInfo, onTick, onResetCache) {
              onTick({});
            },
            unsubscribe: function() {}
          }
        });
      }
    };

    scriptRef.current = script;
    containerRef.current.appendChild(script);

    return () => {
      if (scriptRef.current) {
        scriptRef.current.remove();
      }
    };
  }, [data]);

  return (
    <div
      id="tradingview_chart"
      ref={containerRef}
      style={{ flex: 1, width: '100%', height: '100%' }}
    />
  );
}

export default TradingViewWidget;
