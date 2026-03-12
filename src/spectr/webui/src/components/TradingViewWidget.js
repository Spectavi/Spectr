import React, { useEffect, useRef, useMemo, useState } from 'react';

let tradingViewLoaded = false;
let widgetInstance = null;

function TradingViewWidget({ data, ticker }) {
  const containerRef = useRef(null);
  const [isReady, setIsReady] = useState(false);

  const chartConfig = useMemo(() => ({
    symbol: data.symbol,
    chartData: data.data || [],
    containerId: `tradingview_chart_${ticker}`
  }), [data, ticker]);

  useEffect(() => {
    if (!containerRef.current) return;

    const initializeWidget = () => {
      if (widgetInstance && typeof widgetInstance.cleanup === 'function') {
        widgetInstance.cleanup();
      }
      widgetInstance = null;

      widgetInstance = new window.TradingView.widget({
        autosize: true,
        symbol: chartConfig.symbol,
        interval: '1',
        timezone: 'Etc/UTC',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#f1f3f6',
        enable_publishing: false,
        allow_symbol_change: true,
        container_id: chartConfig.containerId,
        datafeed: {
          getBars: function(symbolInfo, resolution, from, to, callback) {
            if (chartConfig.chartData.length === 0) {
              callback([]);
              return;
            }
            
            const bars = chartConfig.chartData.map(bar => ({
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
    };

    if (tradingViewLoaded && window.TradingView) {
      initializeWidget();
      setIsReady(true);
    } else {
      const script = document.createElement('script');
      script.type = 'text/javascript';
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.defer = true;
      script.onload = () => {
        tradingViewLoaded = true;
        if (window.TradingView) {
          initializeWidget();
          setIsReady(true);
        }
      };
      document.head.appendChild(script);
    }

    return () => {
      if (widgetInstance && typeof widgetInstance.cleanup === 'function') {
        widgetInstance.cleanup();
      }
      widgetInstance = null;
    };
  }, [chartConfig.containerId, chartConfig.symbol, chartConfig.chartData.length]);

  return (
    <div
      id={chartConfig.containerId}
      ref={containerRef}
      style={{ flex: 1, width: '100%', height: '100%' }}
    />
  );
}

export default TradingViewWidget;
